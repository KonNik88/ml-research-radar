from __future__ import annotations

import json
from pathlib import Path

from scripts.validation.check_source_observation_materialization_parity import (
    build_report,
    collect_file_evidence,
)


SOURCE_DIRS = {
    "arxiv": "arxiv",
    "openalex": "openalex_alignment",
    "semantic_scholar": "semantic_scholar_alignment",
    "crossref": "crossref_alignment",
    "acl_anthology": "acl_anthology",
}


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _source_row(source: str, record_id: str, doc_id: str) -> dict:
    return {
        "source": source,
        "source_record_id": record_id,
        "source_id": record_id,
        "doc_id": doc_id,
        "canonical_url": f"https://example.test/{doc_id}",
        "title": f"Title {source}",
    }


def _make_file_fixture(tmp_path: Path) -> tuple[dict[str, Path], Path]:
    rows = {
        "arxiv": _source_row("arxiv", "2401.00001", "shared-paper"),
        "openalex": _source_row("openalex", "W1", "shared-paper"),
        "semantic_scholar": _source_row(
            "semantic_scholar", "S1", "shared-paper"
        ),
        "crossref": _source_row("crossref", "10.1000/test", "shared-paper"),
        "acl_anthology": _source_row("acl_anthology", "P24-0001", "acl-paper"),
    }

    selected: dict[str, Path] = {}
    for source, directory in SOURCE_DIRS.items():
        path = tmp_path / "normalized" / directory / "documents.20260720T000000Z.jsonl"
        _write_jsonl(path, [rows[source]])
        selected[source] = path

    canonical_path = tmp_path / "canonical_documents.jsonl"
    _write_jsonl(
        canonical_path,
        [
            {
                "canonical_id": "paper-1",
                "sources": [
                    rows["arxiv"],
                    rows["openalex"],
                    rows["semantic_scholar"],
                    rows["crossref"],
                ],
            }
        ],
    )
    return selected, canonical_path


def _db_evidence(
    *,
    source_documents_count: int,
    links_count: int,
    null_links: int,
    missing_observations: int,
    full_identity_schema: bool,
    dangling: int = 0,
    source_mismatches: int = 0,
    canonical_pairs_missing: int = 0,
    db_pairs_missing: int = 0,
) -> dict:
    return {
        "db_ping": True,
        "schema": {
            "source_documents_has_source_observation_id": full_identity_schema,
            "canonical_source_links_has_source_observation_id": full_identity_schema,
        },
        "summary": {
            "source_documents_count": source_documents_count,
            "source_documents_by_source": {},
            "db_observation_identity_count": source_documents_count,
            "db_observation_identity_error_count": 0,
            "db_duplicate_observation_id_count": 0,
            "db_observation_source_counts": {},
            "canonical_source_links_count": links_count,
            "resolved_link_count": links_count - null_links,
            "null_link_count": null_links,
            "dangling_non_null_link_count": dangling,
            "joined_source_mismatch_count": source_mismatches,
            "links_by_source": {},
            "db_link_identity_count": links_count,
            "db_link_pair_count": links_count,
            "db_link_identity_error_count": 0,
            "db_duplicate_link_pair_count": 0,
            "selected_observation_missing_from_db_count": missing_observations,
            "selected_observation_missing_from_db_by_source": {},
            "unexpected_db_observation_count": 0,
            "canonical_pair_missing_from_db_count": canonical_pairs_missing,
            "db_pair_missing_from_canonical_count": db_pairs_missing,
        },
        "samples": {},
    }


def test_file_evidence_distinguishes_selected_and_contributing_rows(tmp_path: Path) -> None:
    selected, canonical_path = _make_file_fixture(tmp_path)

    evidence = collect_file_evidence(
        selected_snapshots=selected,
        canonical_path=canonical_path,
        sample_limit=10,
    )

    summary = evidence["summary"]
    assert summary["selected_observation_unique_count"] == 5
    assert summary["canonical_provenance_pair_count"] == 4
    assert summary["non_contributing_observation_count"] == 1
    assert summary["non_contributing_source_counts"] == {"acl_anthology": 1}
    assert summary["canonical_provenance_missing_from_selected_count"] == 0


def test_audit_mode_records_known_gap_without_failing(tmp_path: Path) -> None:
    selected, canonical_path = _make_file_fixture(tmp_path)
    files = collect_file_evidence(
        selected_snapshots=selected,
        canonical_path=canonical_path,
    )
    db = _db_evidence(
        source_documents_count=3,
        links_count=4,
        null_links=1,
        missing_observations=2,
        full_identity_schema=False,
    )

    report = build_report(
        file_evidence=files,
        db_evidence=db,
        require_full_parity=False,
        sample_limit=20,
    )

    assert report["verdict"]["ok"] is True
    assert report["verdict"]["full_parity_ok"] is False
    assert report["verdict"]["materialization_gap_detected"] is True
    assert report["verdict"]["strengthen_existing_materialization_candidate"] is True


def test_require_full_parity_fails_on_current_legacy_shape(tmp_path: Path) -> None:
    selected, canonical_path = _make_file_fixture(tmp_path)
    files = collect_file_evidence(
        selected_snapshots=selected,
        canonical_path=canonical_path,
    )
    db = _db_evidence(
        source_documents_count=3,
        links_count=4,
        null_links=1,
        missing_observations=2,
        full_identity_schema=False,
    )

    report = build_report(
        file_evidence=files,
        db_evidence=db,
        require_full_parity=True,
        sample_limit=20,
    )

    assert report["verdict"]["ok"] is False
    assert "source_documents_cover_all_selected_observations" in report["verdict"][
        "required_failed_checks"
    ]
    assert "canonical_links_are_fully_resolved" in report["verdict"][
        "required_failed_checks"
    ]


def test_require_full_parity_passes_for_candidate_shape(tmp_path: Path) -> None:
    selected, canonical_path = _make_file_fixture(tmp_path)
    files = collect_file_evidence(
        selected_snapshots=selected,
        canonical_path=canonical_path,
    )
    db = _db_evidence(
        source_documents_count=5,
        links_count=4,
        null_links=0,
        missing_observations=0,
        full_identity_schema=True,
    )

    report = build_report(
        file_evidence=files,
        db_evidence=db,
        require_full_parity=True,
        sample_limit=20,
    )

    assert report["verdict"]["ok"] is True
    assert report["verdict"]["full_parity_ok"] is True
    assert report["verdict"]["materialization_gap_detected"] is False


def test_dangling_link_is_always_audit_failure(tmp_path: Path) -> None:
    selected, canonical_path = _make_file_fixture(tmp_path)
    files = collect_file_evidence(
        selected_snapshots=selected,
        canonical_path=canonical_path,
    )
    db = _db_evidence(
        source_documents_count=5,
        links_count=4,
        null_links=0,
        missing_observations=0,
        full_identity_schema=True,
        dangling=1,
    )

    report = build_report(
        file_evidence=files,
        db_evidence=db,
        require_full_parity=False,
        sample_limit=20,
    )

    assert report["verdict"]["ok"] is False
    assert "no_dangling_non_null_links" in report["verdict"][
        "required_failed_checks"
    ]
