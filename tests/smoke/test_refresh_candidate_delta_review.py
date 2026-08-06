from __future__ import annotations

import json
from pathlib import Path

from scripts.validation import check_refresh_candidate_delta as delta


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
    sources: list[dict[str, object]] | None = None,
    source_ids: dict[str, str] | None = None,
    unique_source_count: int = 1,
) -> dict[str, object]:
    return {
        "canonical_id": canonical_id,
        "title": title or f"Paper {canonical_id}",
        "doi": doi,
        "arxiv_id": arxiv_id,
        "openalex_id": openalex_id,
        "semantic_scholar_id": semantic_scholar_id,
        "reconciliation_key": reconciliation_key or canonical_id,
        "sources": sources or [{"source": "arxiv", "source_record_id": canonical_id}],
        "source_ids": source_ids or {"arxiv": canonical_id},
        "source_count": unique_source_count,
        "unique_source_count": unique_source_count,
    }


def test_candidate_delta_review_reports_additions_and_source_family_delta(
    tmp_path: Path,
) -> None:
    canonical_path = tmp_path / "data/analytics/reconciled/canonical_documents.jsonl"
    candidate_path = tmp_path / "data/analytics/reconciled/candidate.jsonl"

    _write_jsonl(
        canonical_path,
        [
            _row("paper-a", doi="10.0000/a"),
            _row("paper-b", doi="10.0000/b"),
        ],
    )
    _write_jsonl(
        candidate_path,
        [
            _row("paper-a", doi="10.0000/a"),
            _row("paper-b", doi="10.0000/b"),
            _row(
                "paper-c",
                doi="10.0000/c",
                sources=[{"source": "semantic_scholar", "source_record_id": "s2-c"}],
                source_ids={"semantic_scholar": "s2-c"},
            ),
        ],
    )

    report = delta.build_report(
        canonical_path=canonical_path,
        candidate_path=candidate_path,
        reports_dir=tmp_path / "reports",
        strict=True,
        max_removed=0,
        max_identifier_churn=0,
        sample_limit=5,
    )

    assert report["schema_version"] == delta.SCHEMA_VERSION
    assert report["read_only"] is True
    assert report["promotion_executed"] is False
    assert report["derived_layers_rebuilt"] is False
    assert report["verdict"]["ok"] is True
    assert report["summary"]["baseline_doc_count"] == 2
    assert report["summary"]["candidate_doc_count"] == 3
    assert report["summary"]["doc_count_delta"] == 1
    assert report["summary"]["added_count"] == 1
    assert report["summary"]["removed_count"] == 0
    assert report["delta"]["source_family_delta"]["semantic_scholar"] == 1
    assert report["delta"]["samples"]["added"][0]["canonical_id"] == "paper-c"


def test_candidate_delta_review_flags_removed_ids_and_identifier_churn(
    tmp_path: Path,
) -> None:
    canonical_path = tmp_path / "data/analytics/reconciled/canonical_documents.jsonl"
    candidate_path = tmp_path / "data/analytics/reconciled/candidate.jsonl"

    _write_jsonl(
        canonical_path,
        [
            _row("paper-a", doi="10.0000/a"),
            _row("paper-b", doi="10.0000/b", openalex_id="W1"),
        ],
    )
    _write_jsonl(
        candidate_path,
        [
            _row("paper-b", doi="10.0000/b-new", openalex_id="W1"),
        ],
    )

    report = delta.build_report(
        canonical_path=canonical_path,
        candidate_path=candidate_path,
        reports_dir=tmp_path / "reports",
        strict=True,
        max_removed=0,
        max_identifier_churn=0,
        sample_limit=5,
    )

    assert report["verdict"]["ok"] is False
    assert "candidate_not_smaller_than_canonical" in report["verdict"][
        "required_failed_checks"
    ]
    assert "removed_count_within_threshold" in report["verdict"][
        "required_failed_checks"
    ]
    assert "identifier_churn_within_threshold" in report["verdict"][
        "required_failed_checks"
    ]
    assert report["summary"]["removed_count"] == 1
    assert report["summary"]["identifier_churn_count"] == 1
    assert report["verdict"]["manual_review_required"] is True


def test_candidate_delta_review_writes_latest_and_history_reports(
    tmp_path: Path,
) -> None:
    canonical_path = tmp_path / "canonical.jsonl"
    candidate_path = tmp_path / "candidate.jsonl"
    reports_dir = tmp_path / "reports"

    _write_jsonl(canonical_path, [_row("paper-a")])
    _write_jsonl(candidate_path, [_row("paper-a"), _row("paper-b")])

    report = delta.build_report(
        canonical_path=canonical_path,
        candidate_path=candidate_path,
        reports_dir=reports_dir,
        strict=False,
        max_removed=0,
        max_identifier_churn=0,
        sample_limit=5,
    )
    latest_json, latest_md, hist_json, hist_md = delta.write_reports(
        report,
        reports_dir,
    )

    assert latest_json.exists()
    assert latest_md.exists()
    assert hist_json.exists()
    assert hist_md.exists()
    assert "Refresh candidate delta review" in latest_md.read_text(encoding="utf-8")
