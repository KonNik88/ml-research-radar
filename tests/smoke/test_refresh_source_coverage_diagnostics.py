from __future__ import annotations

import json
from pathlib import Path

from scripts.validation import check_refresh_source_coverage as coverage


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _row(
    canonical_id: str,
    *,
    title: str | None = None,
    doi: str | None = None,
    arxiv_id: str | None = None,
    openalex_id: str | None = None,
    semantic_scholar_id: str | None = None,
    reconciliation_key: str | None = None,
    source_ids: dict[str, str] | None = None,
) -> dict[str, object]:
    resolved_source_ids = source_ids or {"arxiv": canonical_id}
    sources = [
        {"source": source_family, "source_record_id": source_id}
        for source_family, source_id in sorted(resolved_source_ids.items())
    ]
    return {
        "canonical_id": canonical_id,
        "title": title or f"Paper {canonical_id}",
        "doi": doi,
        "arxiv_id": arxiv_id,
        "openalex_id": openalex_id,
        "semantic_scholar_id": semantic_scholar_id,
        "reconciliation_key": reconciliation_key or canonical_id,
        "sources": sources,
        "source_ids": resolved_source_ids,
        "source_count": len(resolved_source_ids),
        "unique_source_count": len(resolved_source_ids),
    }


def test_refresh_source_coverage_diagnoses_acl_removals_and_arxiv_collapse(
    tmp_path: Path,
) -> None:
    canonical_path = tmp_path / "canonical.jsonl"
    candidate_path = tmp_path / "candidate.jsonl"

    _write_jsonl(
        canonical_path,
        [
            _row(
                "paper-acl",
                doi="10.18653/v1/2024.acl-long.109",
                source_ids={"acl_anthology": "2024.acl-long.109"},
            ),
            _row(
                "paper-multi",
                doi="10.0000/multi",
                arxiv_id="2401.00001v1",
                openalex_id="https://openalex.org/W1",
                semantic_scholar_id="s2-1",
                source_ids={
                    "arxiv": "2401.00001v1",
                    "crossref": "10.0000/multi",
                    "openalex": "https://openalex.org/W1",
                    "semantic_scholar": "s2-1",
                },
            ),
        ],
    )
    _write_jsonl(
        candidate_path,
        [
            _row(
                "paper-multi",
                arxiv_id="2401.00001v1",
                source_ids={"arxiv": "2401.00001v1"},
            ),
        ],
    )

    report = coverage.build_report(
        canonical_path=canonical_path,
        candidate_path=candidate_path,
        reports_dir=tmp_path / "reports",
        delta_report_path=None,
        sample_limit=10,
    )

    assert report["read_only"] is True
    assert report["promotion_executed"] is False
    assert report["verdict"]["promotion_safe"] is False
    assert report["summary"]["removed_count"] == 1
    assert report["summary"]["acl_only_removed_count"] == 1
    assert report["summary"]["retained_multisource_to_arxiv_only_count"] == 1
    assert report["summary"]["retained_identifier_loss_count"] == 1
    assert report["summary"]["retained_source_id_loss_count"] == 1
    assert report["diagnostics"]["signals"]["likely_missing_acl_input"] is True
    assert (
        report["diagnostics"]["signals"]["likely_multisource_collapse_to_arxiv_only"]
        is True
    )
    assert report["diagnostics"]["removed"]["by_family_combo"] == {"acl_anthology": 1}
    assert report["diagnostics"]["retained"]["lost_source_family_counts"] == {
        "crossref": 1,
        "openalex": 1,
        "semantic_scholar": 1,
    }
    assert report["diagnostics"]["retained"]["identifier_loss"]["by_field"] == {
        "doi": 1,
        "openalex_id": 1,
        "semantic_scholar_id": 1,
    }


def test_refresh_source_coverage_treats_additive_semantic_scholar_as_safe(
    tmp_path: Path,
) -> None:
    canonical_path = tmp_path / "canonical.jsonl"
    candidate_path = tmp_path / "candidate.jsonl"

    _write_jsonl(
        canonical_path,
        [
            _row(
                "paper-a",
                arxiv_id="2501.00001v1",
                source_ids={"arxiv": "2501.00001v1"},
            ),
            _row(
                "paper-b",
                arxiv_id="2501.00002v1",
                openalex_id="https://openalex.org/W2",
                source_ids={
                    "arxiv": "2501.00002v1",
                    "openalex": "https://openalex.org/W2",
                    "crossref": "10.0000/b",
                },
            ),
        ],
    )
    _write_jsonl(
        candidate_path,
        [
            _row(
                "paper-a",
                arxiv_id="2501.00001v1",
                semantic_scholar_id="s2-a",
                source_ids={
                    "arxiv": "2501.00001v1",
                    "semantic_scholar": "s2-a",
                },
            ),
            _row(
                "paper-b",
                arxiv_id="2501.00002v1",
                openalex_id="https://openalex.org/W2",
                semantic_scholar_id="s2-b",
                source_ids={
                    "arxiv": "2501.00002v1",
                    "openalex": "https://openalex.org/W2",
                    "crossref": "10.0000/b",
                    "semantic_scholar": "s2-b",
                },
            ),
        ],
    )

    report = coverage.build_report(
        canonical_path=canonical_path,
        candidate_path=candidate_path,
        reports_dir=tmp_path / "reports",
        delta_report_path=None,
        sample_limit=10,
    )

    assert report["summary"]["retained_source_family_changed_count"] == 2
    assert report["summary"]["retained_identifier_loss_count"] == 0
    assert report["summary"]["retained_source_id_loss_count"] == 0
    assert report["diagnostics"]["retained"]["lost_source_family_counts"] == {}
    assert report["diagnostics"]["retained"]["gained_source_family_counts"] == {
        "semantic_scholar": 2
    }
    assert report["diagnostics"]["signals"]["source_coverage_regression_detected"] is False
    assert report["diagnostics"]["signals"]["additive_source_coverage_detected"] is True
    assert report["verdict"]["promotion_safe"] is True


def test_refresh_source_coverage_uses_delta_report_paths_and_writes_reports(
    tmp_path: Path,
) -> None:
    canonical_path = tmp_path / "canonical.jsonl"
    candidate_path = tmp_path / "candidate.jsonl"
    reports_dir = tmp_path / "reports"
    delta_report_path = reports_dir / "refresh_candidate_delta_review_latest.json"

    _write_jsonl(canonical_path, [_row("paper-a")])
    _write_jsonl(candidate_path, [_row("paper-a"), _row("paper-b")])
    delta_report_path.parent.mkdir(parents=True, exist_ok=True)
    delta_report_path.write_text(
        json.dumps(
            {
                "inputs": {
                    "canonical_path": str(canonical_path),
                    "candidate_path": str(candidate_path),
                },
                "summary": {"removed_count": 0, "identifier_churn_count": 0},
                "verdict": {"required_failed_checks": []},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    delta_report = coverage.read_json(delta_report_path)
    resolved_canonical_path, resolved_candidate_path = (
        coverage.resolve_paths_from_delta_report(
            delta_report,
            canonical_path=None,
            candidate_path=None,
        )
    )
    report = coverage.build_report(
        canonical_path=resolved_canonical_path,
        candidate_path=resolved_candidate_path,
        reports_dir=reports_dir,
        delta_report_path=delta_report_path,
        sample_limit=5,
    )
    latest_json, latest_md, hist_json, hist_md = coverage.write_reports(
        report,
        reports_dir,
    )

    assert report["summary"]["added_count"] == 1
    assert report["delta_gate_context"]["exists"] is True
    assert latest_json.exists()
    assert latest_md.exists()
    assert hist_json.exists()
    assert hist_md.exists()
    assert "Refresh source coverage diagnostics" in latest_md.read_text(
        encoding="utf-8"
    )
