from __future__ import annotations

import json
from pathlib import Path

from scripts.validation import check_refresh_alignment_coverage as alignment


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _canonical_row(
    canonical_id: str,
    *,
    doi: str | None = "10.0000/example",
    arxiv_id: str | None = "2401.00001v1",
    openalex_id: str | None = None,
    source_ids: dict[str, str] | None = None,
) -> dict[str, object]:
    resolved_source_ids = source_ids or {"arxiv": arxiv_id or canonical_id}
    sources = [
        {"source": source, "source_record_id": source_id}
        for source, source_id in sorted(resolved_source_ids.items())
    ]
    return {
        "canonical_id": canonical_id,
        "title": f"Paper {canonical_id}",
        "doi": doi,
        "arxiv_id": arxiv_id,
        "openalex_id": openalex_id,
        "sources": sources,
        "source_ids": resolved_source_ids,
        "source_count": len(resolved_source_ids),
        "unique_source_count": len(resolved_source_ids),
    }


def _merge_report(
    root: Path,
    source_name: str,
    snapshot_rows: list[dict[str, object]],
) -> Path:
    snapshot_path = root / "data/normalized" / source_name / "documents.20260808T000000Z.jsonl"
    report_path = root / "artifacts/reports/update" / f"merge_{source_name}_latest.json"
    _write_jsonl(snapshot_path, snapshot_rows)
    _write_json(
        report_path,
        {
            "source_name": source_name,
            "output": {"merged_snapshot": str(snapshot_path)},
            "stats": {"merged_output_rows": len(snapshot_rows)},
        },
    )
    return report_path


def _build_report(
    tmp_path: Path,
    *,
    snapshot_rows: list[dict[str, object]],
) -> dict[str, object]:
    canonical_path = tmp_path / "canonical.jsonl"
    candidate_path = tmp_path / "candidate.jsonl"
    baseline = _canonical_row(
        "paper-1",
        openalex_id="https://openalex.org/W1",
        source_ids={
            "arxiv": "2401.00001v1",
            "openalex": "https://openalex.org/W1",
        },
    )
    candidate = _canonical_row(
        "paper-1",
        openalex_id=None,
        source_ids={"arxiv": "2401.00001v1"},
    )
    _write_jsonl(canonical_path, [baseline])
    _write_jsonl(candidate_path, [candidate])

    openalex_report = _merge_report(tmp_path, "openalex_alignment", snapshot_rows)

    return alignment.build_report(
        canonical_path=canonical_path,
        candidate_path=candidate_path,
        merge_report_specs={"openalex_alignment": openalex_report},
        reports_dir=tmp_path / "reports",
        delta_report_path=None,
        sample_limit=10,
    )


def test_alignment_coverage_classifies_missing_from_merged_snapshot(
    tmp_path: Path,
) -> None:
    report = _build_report(
        tmp_path,
        snapshot_rows=[
            {
                "doc_id": "unrelated",
                "source": "openalex_alignment",
                "doi": "10.0000/other",
                "openalex_id": "https://openalex.org/W2",
            }
        ],
    )

    assert report["read_only"] is True
    assert report["promotion_executed"] is False
    assert report["summary"]["retained_alignment_source_loss_docs_count"] == 1
    assert report["summary"]["lost_alignment_source_observation_count"] == 1
    assert report["summary"]["missing_from_merged_snapshot_count"] == 1
    assert (
        report["diagnostics"]["signals"][
            "likely_merged_snapshots_missing_baseline_coverage"
        ]
        is True
    )


def test_alignment_coverage_classifies_present_without_bridge_keys(
    tmp_path: Path,
) -> None:
    report = _build_report(
        tmp_path,
        snapshot_rows=[
            {
                "doc_id": "openalex-W1",
                "source": "openalex_alignment",
                "openalex_id": "https://openalex.org/W1",
                "source_ids": {"openalex": "https://openalex.org/W1"},
            }
        ],
    )

    assert report["summary"]["present_without_reconcile_bridge_keys_count"] == 1
    assert (
        report["diagnostics"]["signals"]["likely_alignment_rows_present_but_unjoinable"]
        is True
    )


def test_alignment_coverage_classifies_present_with_bridge_keys(
    tmp_path: Path,
) -> None:
    report = _build_report(
        tmp_path,
        snapshot_rows=[
            {
                "doc_id": "openalex-W1",
                "source": "openalex_alignment",
                "doi": "https://doi.org/10.0000/example",
                "arxiv_id": "2401.00001",
                "openalex_id": "https://openalex.org/W1",
                "source_ids": {"openalex": "https://openalex.org/W1"},
            }
        ],
    )

    assert report["summary"]["present_with_reconcile_bridge_keys_count"] == 1
    assert (
        report["diagnostics"]["signals"][
            "likely_reconcile_or_identifier_semantics_issue"
        ]
        is True
    )


def test_alignment_coverage_uses_delta_report_paths_and_writes_reports(
    tmp_path: Path,
) -> None:
    canonical_path = tmp_path / "canonical.jsonl"
    candidate_path = tmp_path / "candidate.jsonl"
    reports_dir = tmp_path / "reports"
    delta_report_path = reports_dir / "refresh_candidate_delta_review_latest.json"
    _write_jsonl(canonical_path, [_canonical_row("paper-1")])
    _write_jsonl(candidate_path, [_canonical_row("paper-1")])
    _write_json(
        delta_report_path,
        {
            "inputs": {
                "canonical_path": str(canonical_path),
                "candidate_path": str(candidate_path),
            },
            "summary": {"identifier_churn_count": 0},
            "verdict": {"required_failed_checks": []},
        },
    )
    openalex_report = _merge_report(tmp_path, "openalex_alignment", [])
    delta_report = alignment.read_json(delta_report_path)
    resolved_canonical, resolved_candidate = alignment.resolve_paths_from_delta_report(
        delta_report,
        canonical_path=None,
        candidate_path=None,
    )
    report = alignment.build_report(
        canonical_path=resolved_canonical,
        candidate_path=resolved_candidate,
        merge_report_specs={"openalex_alignment": openalex_report},
        reports_dir=reports_dir,
        delta_report_path=delta_report_path,
        sample_limit=5,
    )
    latest_json, latest_md, hist_json, hist_md = alignment.write_reports(
        report,
        reports_dir,
    )

    assert report["delta_gate_context"]["exists"] is True
    assert latest_json.exists()
    assert latest_md.exists()
    assert hist_json.exists()
    assert hist_md.exists()
    assert "Refresh alignment coverage diagnostics" in latest_md.read_text(
        encoding="utf-8"
    )
