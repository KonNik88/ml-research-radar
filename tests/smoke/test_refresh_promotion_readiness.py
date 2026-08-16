from __future__ import annotations

import json
from pathlib import Path

from scripts.validation import check_refresh_promotion_readiness as readiness


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _sample_reports(tmp_path: Path) -> dict[str, Path]:
    canonical_path = tmp_path / "data/analytics/reconciled/canonical_documents.jsonl"
    candidate_path = (
        tmp_path
        / "data/analytics/reconciled/canonical_documents.rehearsal_candidate.1.jsonl"
    )
    update_dir = tmp_path / "artifacts/reports/update"
    validation_dir = tmp_path / "artifacts/reports/validation"

    _write_jsonl(
        canonical_path,
        [{"canonical_id": "paper-a", "title": "Paper A", "unique_source_count": 1}],
    )
    _write_jsonl(
        candidate_path,
        [
            {"canonical_id": "paper-a", "title": "Paper A", "unique_source_count": 1},
            {"canonical_id": "paper-b", "title": "Paper B", "unique_source_count": 1},
        ],
    )

    candidate_text = str(candidate_path).replace("\\", "/")
    canonical_text = str(canonical_path).replace("\\", "/")

    _write_json(
        update_dir / "refresh_preflight_contract_latest.json",
        {
            "report_name": "check_refresh_preflight_contract",
            "inputs": {
                "canonical_path": canonical_text,
                "candidate_path": candidate_text,
            },
            "checks": {
                "merge_snapshots_cover_baseline_alignment_sources": True,
                "promote_script_keeps_backup": True,
                "db_smoke_ok": False,
                "db_ping_true": False,
                "db_doc_count_matches_canonical": False,
            },
            "verdict": {
                "ok": True,
                "required_failed_count": 0,
                "required_failed_checks": [],
            },
        },
    )

    _write_json(
        update_dir / "run_refresh_pipeline_v1_latest.json",
        {
            "report_name": "run_refresh_pipeline_v1",
            "mode": "execute",
            "pipeline_mode": "candidate_rehearsal",
            "stop_after": "candidate_delta_review",
            "inputs": {"candidate_rehearsal": True},
            "candidate": {"path": candidate_text, "exists": True},
            "candidate_summary": {"doc_count": 2, "multisource_docs": 1},
            "execution_summary": {
                "failed_count": 0,
                "failed_step_names": [],
                "all_successful": True,
            },
        },
    )

    _write_json(
        validation_dir / "refresh_candidate_delta_review_latest.json",
        {
            "report_name": "refresh_candidate_delta_review",
            "inputs": {
                "canonical_path": canonical_text,
                "candidate_path": candidate_text,
            },
            "summary": {
                "baseline_doc_count": 1,
                "candidate_doc_count": 2,
                "doc_count_delta": 1,
                "added_count": 1,
                "removed_count": 0,
                "additive_identifier_churn_count": 1,
                "destructive_identifier_churn_count": 0,
            },
            "verdict": {
                "ok": True,
                "required_failed_count": 0,
                "required_failed_checks": [],
                "promotion_delta_review_ready": True,
                "manual_review_required": False,
            },
        },
    )

    _write_json(
        validation_dir / "refresh_alignment_coverage_diagnostics_latest.json",
        {
            "report_name": "refresh_alignment_coverage_diagnostics",
            "inputs": {
                "canonical_path": canonical_text,
                "candidate_path": candidate_text,
            },
            "summary": {
                "lost_alignment_source_observation_count": 0,
                "missing_from_merged_snapshot_count": 0,
            },
            "diagnostics": {
                "signals": {
                    "alignment_coverage_regression_detected": False,
                },
            },
            "verdict": {
                "promotion_safe": True,
                "manual_review_required": False,
            },
        },
    )

    _write_json(
        validation_dir / "refresh_source_coverage_diagnostics_latest.json",
        {
            "report_name": "refresh_source_coverage_diagnostics",
            "inputs": {
                "canonical_path": canonical_text,
                "candidate_path": candidate_text,
            },
            "summary": {
                "added_count": 1,
                "removed_count": 0,
                "retained_source_family_changed_count": 1,
                "retained_identifier_loss_count": 0,
                "retained_source_id_loss_count": 0,
                "retained_multisource_to_arxiv_only_count": 0,
            },
            "diagnostics": {
                "signals": {
                    "source_coverage_regression_detected": False,
                    "additive_source_coverage_detected": True,
                },
            },
            "verdict": {
                "promotion_safe": True,
                "manual_review_required": False,
            },
        },
    )

    return {
        "canonical_path": canonical_path,
        "candidate_path": candidate_path,
        "update_dir": update_dir,
        "validation_dir": validation_dir,
        "reports_dir": validation_dir,
    }


def _build(paths: dict[str, Path], *, require_db_smoke: bool = False):
    return readiness.build_report(
        canonical_path=paths["canonical_path"],
        candidate_path=None,
        update_dir=paths["update_dir"],
        validation_dir=paths["validation_dir"],
        reports_dir=paths["reports_dir"],
        require_db_smoke=require_db_smoke,
        strict=True,
    )


def test_promotion_readiness_passes_green_rehearsal_without_db_smoke(
    tmp_path: Path,
) -> None:
    paths = _sample_reports(tmp_path)

    report = _build(paths)

    assert report["schema_version"] == readiness.SCHEMA_VERSION
    assert report["read_only"] is True
    assert report["promotion_executed"] is False
    assert report["verdict"]["promotion_ready"] is True
    assert report["verdict"]["required_failed_count"] == 0
    assert report["summary"]["candidate_doc_count"] == 2
    assert report["summary"]["added_count"] == 1
    assert report["summary"]["additive_source_coverage_detected"] is True


def test_promotion_readiness_can_require_db_smoke_explicitly(
    tmp_path: Path,
) -> None:
    paths = _sample_reports(tmp_path)

    report = _build(paths, require_db_smoke=True)

    assert report["verdict"]["promotion_ready"] is False
    assert "db_smoke_ok" in report["verdict"]["required_failed_checks"]
    assert "db_ping_true" in report["verdict"]["required_failed_checks"]
    assert "db_doc_count_matches_canonical" in report["verdict"][
        "required_failed_checks"
    ]


def test_promotion_readiness_blocks_destructive_source_loss(tmp_path: Path) -> None:
    paths = _sample_reports(tmp_path)
    source_path = (
        paths["validation_dir"] / "refresh_source_coverage_diagnostics_latest.json"
    )
    source_report = json.loads(source_path.read_text(encoding="utf-8"))
    source_report["summary"]["retained_identifier_loss_count"] = 1
    source_report["diagnostics"]["signals"]["source_coverage_regression_detected"] = True
    source_report["verdict"]["promotion_safe"] = False
    _write_json(source_path, source_report)

    report = _build(paths)

    assert report["verdict"]["promotion_ready"] is False
    assert "source_promotion_safe" in report["verdict"]["required_failed_checks"]
    assert "source_regression_absent" in report["verdict"]["required_failed_checks"]
    assert "source_identifier_loss_zero" in report["verdict"]["required_failed_checks"]


def test_promotion_readiness_blocks_stale_candidate_report(tmp_path: Path) -> None:
    paths = _sample_reports(tmp_path)
    alignment_path = (
        paths["validation_dir"] / "refresh_alignment_coverage_diagnostics_latest.json"
    )
    alignment_report = json.loads(alignment_path.read_text(encoding="utf-8"))
    alignment_report["inputs"]["candidate_path"] = str(
        tmp_path / "data/analytics/reconciled/stale_candidate.jsonl"
    ).replace("\\", "/")
    _write_json(alignment_path, alignment_report)

    report = _build(paths)

    assert report["verdict"]["promotion_ready"] is False
    assert "alignment_report_matches_candidate" in report["verdict"][
        "required_failed_checks"
    ]


def test_promotion_readiness_writes_latest_and_history_reports(tmp_path: Path) -> None:
    paths = _sample_reports(tmp_path)
    report = _build(paths)

    latest_json, latest_md, hist_json, hist_md = readiness.write_reports(
        report,
        paths["reports_dir"],
    )

    assert latest_json.exists()
    assert latest_md.exists()
    assert hist_json.exists()
    assert hist_md.exists()
    assert "Refresh promotion readiness" in latest_md.read_text(encoding="utf-8")
