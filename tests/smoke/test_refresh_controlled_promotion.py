from __future__ import annotations

import json
from pathlib import Path

from scripts.update import run_refresh_controlled_promotion as promotion


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _sample_project(tmp_path: Path) -> dict[str, Path]:
    canonical_dir = tmp_path / "data/analytics/reconciled"
    update_dir = tmp_path / "artifacts/reports/update"
    validation_dir = tmp_path / "artifacts/reports/validation"
    latest_path = canonical_dir / "canonical_documents.jsonl"
    candidate_path = (
        canonical_dir / "canonical_documents.rehearsal_candidate.20260816T085337Z.jsonl"
    )
    readiness_path = validation_dir / "refresh_promotion_readiness_latest.json"

    _write_jsonl(
        latest_path,
        [{"canonical_id": "paper-a", "title": "Paper A", "unique_source_count": 1}],
    )
    _write_jsonl(
        candidate_path,
        [
            {"canonical_id": "paper-a", "title": "Paper A", "unique_source_count": 1},
            {"canonical_id": "paper-b", "title": "Paper B", "unique_source_count": 1},
        ],
    )

    _write_json(
        readiness_path,
        {
            "report_name": "refresh_promotion_readiness",
            "summary": {
                "candidate_path": str(candidate_path).replace("\\", "/"),
                "candidate_doc_count": 2,
                "baseline_doc_count": 1,
                "doc_count_delta": 1,
                "removed_count": 0,
                "destructive_identifier_churn_count": 0,
            },
            "verdict": {
                "ok": True,
                "promotion_ready": True,
                "required_failed_count": 0,
                "required_failed_checks": [],
            },
        },
    )

    return {
        "canonical_dir": canonical_dir,
        "latest_path": latest_path,
        "candidate_path": candidate_path,
        "update_dir": update_dir,
        "validation_dir": validation_dir,
        "readiness_path": readiness_path,
    }


def _build(
    paths: dict[str, Path],
    *,
    candidate_path: Path | None = None,
    execute: bool = False,
    runner=promotion.run_step,
):
    return promotion.build_report(
        candidate_path=candidate_path,
        canonical_dir=paths["canonical_dir"],
        update_dir=paths["update_dir"],
        validation_dir=paths["validation_dir"],
        readiness_report_path=paths["readiness_path"],
        execute=execute,
        require_db_smoke=False,
        runner=runner,
    )


def test_controlled_promotion_dry_run_is_safe_when_readiness_is_green(
    tmp_path: Path,
) -> None:
    paths = _sample_project(tmp_path)

    report = _build(paths)

    assert report["schema_version"] == promotion.SCHEMA_VERSION
    assert report["mode"] == "dry_run"
    assert report["verdict"]["ok"] is True
    assert report["verdict"]["safe_to_execute"] is True
    assert report["verdict"]["controlled_promotion_complete"] is False
    assert report["verdict"]["canonical_latest_mutated"] is False
    assert report["summary"]["candidate_doc_count"] == 2
    assert report["summary"]["previous_latest_doc_count"] == 1
    assert report["planned_steps"][1]["name"] == "promote_candidate"
    assert "--execute" not in report["planned_steps"][1]["cmd"]


def test_controlled_promotion_blocks_failed_readiness(tmp_path: Path) -> None:
    paths = _sample_project(tmp_path)
    readiness = json.loads(paths["readiness_path"].read_text(encoding="utf-8"))
    readiness["verdict"]["promotion_ready"] = False
    readiness["verdict"]["required_failed_count"] = 1
    readiness["verdict"]["required_failed_checks"] = ["source_regression_absent"]
    _write_json(paths["readiness_path"], readiness)

    report = _build(paths)

    assert report["verdict"]["ok"] is False
    assert report["verdict"]["safe_to_execute"] is False
    assert "precheck::readiness_promotion_ready" in report["verdict"][
        "required_failed_checks"
    ]


def test_controlled_promotion_blocks_explicit_candidate_mismatch(tmp_path: Path) -> None:
    paths = _sample_project(tmp_path)
    other_candidate = paths["canonical_dir"] / "other_candidate.jsonl"
    _write_jsonl(other_candidate, [{"canonical_id": "paper-z"}])

    report = _build(paths, candidate_path=other_candidate)

    assert report["verdict"]["ok"] is False
    assert report["verdict"]["safe_to_execute"] is False
    assert "precheck::candidate_path_matches_readiness" in report["verdict"][
        "required_failed_checks"
    ]


def test_controlled_promotion_execute_runs_steps_and_validates_postchecks(
    tmp_path: Path,
) -> None:
    paths = _sample_project(tmp_path)
    seen_steps: list[str] = []

    def fake_runner(name: str, cmd: list[str]) -> dict[str, object]:
        seen_steps.append(name)
        if name == "promote_candidate":
            assert "--execute" in cmd
            _write_json(
                paths["update_dir"] / "promote_canonical_candidate_latest.json",
                {
                    "report_name": "promote_canonical_candidate",
                    "execution_summary": {
                        "executed": True,
                        "backup_created": True,
                        "promotion_performed": True,
                        "postcheck_match": True,
                    },
                    "new_latest_summary": {"doc_count": 2},
                },
            )
        if name == "canonical_provenance_consistency":
            _write_json(
                paths["validation_dir"] / "canonical_provenance_consistency_latest.json",
                {
                    "report_name": "canonical_provenance_consistency_v2",
                    "summary": {"all_error_checks_clean": True},
                },
            )
        if name == "canonical_contract_check":
            _write_json(
                paths["validation_dir"] / "canonical_contract_latest.json",
                {
                    "report_name": "canonical_contract",
                    "summary": {"rows_count": 2},
                    "verdict": {"ok": True},
                },
            )
        return {
            "name": name,
            "cmd": " ".join(cmd),
            "returncode": 0,
            "ok": True,
            "stdout_tail": "",
            "stderr_tail": "",
            "duration_sec": 0.0,
        }

    report = _build(paths, execute=True, runner=fake_runner)

    assert seen_steps == promotion.STEP_ORDER
    assert report["verdict"]["ok"] is True
    assert report["verdict"]["controlled_promotion_complete"] is True
    assert report["verdict"]["canonical_latest_mutated"] is True
    assert report["post_execution_checks"]["promote_backup_created"] is True
    assert report["post_execution_checks"]["canonical_contract_doc_count_matches_candidate"] is True


def test_controlled_promotion_writes_latest_and_history_reports(tmp_path: Path) -> None:
    paths = _sample_project(tmp_path)
    report = _build(paths)

    latest_json, latest_md, hist_json, hist_md = promotion.write_reports(
        report,
        paths["update_dir"],
    )

    assert latest_json.exists()
    assert latest_md.exists()
    assert hist_json.exists()
    assert hist_md.exists()
    assert "Refresh controlled promotion" in latest_md.read_text(encoding="utf-8")
