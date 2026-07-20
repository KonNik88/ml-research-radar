from __future__ import annotations

from radar_core.contracts.document import NormalizedDocument
from scripts.validation.check_source_observation_non_contributing import (
    build_canonical_indexes,
    build_report,
    classify_observation,
)


def _doc(
    *,
    source: str = "openalex",
    source_record_id: str = "W1",
    doi: str | None = None,
    arxiv_id: str | None = None,
    title: str = "Example Paper",
    year: int = 2024,
) -> NormalizedDocument:
    return NormalizedDocument(
        doc_id=f"doc-{source_record_id}",
        canonical_url=f"https://example.org/{source_record_id}",
        content_hash=f"hash-{source_record_id}",
        source=source,
        source_id=source_record_id,
        source_record_id=source_record_id,
        source_record_url=f"https://example.org/{source_record_id}",
        doi=doi,
        arxiv_id=arxiv_id,
        title=title,
        year=year,
        pipeline_version="test",
    )


def _summary(doc: NormalizedDocument, observation_id: str = "obs-1") -> dict:
    return {
        "source": doc.source,
        "source_observation_id": observation_id,
        "source_record_id": doc.source_record_id,
        "source_id": doc.source_id,
        "doc_id": doc.doc_id,
        "source_record_url": str(doc.source_record_url),
        "canonical_url": str(doc.canonical_url),
        "title": doc.title,
        "year": doc.year,
        "doi": doc.doi,
        "arxiv_id": doc.arxiv_id,
    }


def _canonical(
    *,
    canonical_id: str,
    reconciliation_key: str,
    doi: str | None = None,
    arxiv_id: str | None = None,
    title: str = "Example Paper",
    year: int = 2024,
) -> dict:
    return {
        "canonical_id": canonical_id,
        "reconciliation_key": reconciliation_key,
        "doi": doi,
        "arxiv_id": arxiv_id,
        "title": title,
        "year": year,
        "sources": [],
    }


def test_same_reconciliation_key_not_contributing() -> None:
    doc = _doc(doi="10.1234/example")
    indexes = build_canonical_indexes(
        [
            _canonical(
                canonical_id="paper-1",
                reconciliation_key="doi::10.1234/example",
                doi="10.1234/example",
            )
        ]
    )

    row = classify_observation(
        source_observation_id="obs-1",
        document=doc,
        summary=_summary(doc),
        canonical_indexes=indexes,
        db_observation_ids={"obs-1"},
    )

    assert row["classification"] == "same_reconciliation_key_not_contributing"
    assert row["match_basis"] == "reconciliation_key"
    assert row["matched_canonical_count"] == 1
    assert row["db_materialized"] is True


def test_strong_identity_match_when_promoted_key_differs() -> None:
    doc = _doc(doi="10.1234/example")
    indexes = build_canonical_indexes(
        [
            _canonical(
                canonical_id="paper-1",
                reconciliation_key="doi_conflict::10.1234/example",
                doi="10.1234/example",
            )
        ]
    )

    row = classify_observation(
        source_observation_id="obs-1",
        document=doc,
        summary=_summary(doc),
        canonical_indexes=indexes,
        db_observation_ids=set(),
    )

    assert row["classification"] == "strong_identity_match_not_contributing"
    assert row["match_basis"] == "doi"
    assert row["db_materialized"] is False


def test_title_year_match_not_contributing() -> None:
    doc = _doc(
        source="acl_anthology",
        source_record_id="2024.acl-long.1",
        title="A Useful NLP Paper",
        year=2024,
    )
    indexes = build_canonical_indexes(
        [
            _canonical(
                canonical_id="paper-1",
                reconciliation_key="arxiv::2401.00001",
                title="A Useful NLP Paper",
                year=2024,
            )
        ]
    )

    row = classify_observation(
        source_observation_id="obs-1",
        document=doc,
        summary=_summary(doc),
        canonical_indexes=indexes,
        db_observation_ids=None,
    )

    assert row["classification"] == "title_year_match_not_contributing"
    assert row["match_basis"] == "title_year"
    assert row["db_materialized"] is None
    assert row["review_hint"] == "acl_filtered_candidate_identity_overlap_review"


def test_ambiguous_title_year_match() -> None:
    doc = _doc(title="Repeated Title", year=2024)
    indexes = build_canonical_indexes(
        [
            _canonical(
                canonical_id="paper-1",
                reconciliation_key="arxiv::2401.00001",
                title="Repeated Title",
                year=2024,
            ),
            _canonical(
                canonical_id="paper-2",
                reconciliation_key="arxiv::2401.00002",
                title="Repeated Title",
                year=2024,
            ),
        ]
    )

    row = classify_observation(
        source_observation_id="obs-1",
        document=doc,
        summary=_summary(doc),
        canonical_indexes=indexes,
        db_observation_ids=None,
    )

    assert row["classification"] == "ambiguous_title_year_match"
    assert row["matched_canonical_count"] == 2


def test_no_matching_promoted_canonical_identity() -> None:
    doc = _doc(
        source="acl_anthology",
        source_record_id="2024.acl-long.2",
        title="Unique Unpromoted Paper",
        year=2024,
    )
    indexes = build_canonical_indexes([])

    row = classify_observation(
        source_observation_id="obs-1",
        document=doc,
        summary=_summary(doc),
        canonical_indexes=indexes,
        db_observation_ids=None,
    )

    assert row["classification"] == "no_matching_promoted_canonical_identity"
    assert row["matched_canonical_count"] == 0
    assert (
        row["review_hint"]
        == "acl_not_present_in_promoted_canonical_identity_indexes"
    )


def test_build_report_reconciles_counts() -> None:
    doc = _doc(doi="10.1234/example")
    indexes = build_canonical_indexes(
        [
            _canonical(
                canonical_id="paper-1",
                reconciliation_key="doi::10.1234/example",
                doi="10.1234/example",
            )
        ]
    )
    row = classify_observation(
        source_observation_id="obs-1",
        document=doc,
        summary=_summary(doc),
        canonical_indexes=indexes,
        db_observation_ids={"obs-1"},
    )

    report = build_report(
        selected_count=2,
        canonical_count=1,
        provenance_count=1,
        rows=[row],
        selected_errors=[],
        provenance_errors=[],
        db_errors=[],
        selected_snapshots={"openalex": __import__("pathlib").Path("snapshot.jsonl")},
        canonical_path=__import__("pathlib").Path("canonical.jsonl"),
        db_checked=True,
        sample_limit=20,
    )

    assert report["verdict"]["ok"] is True
    assert report["summary"]["non_contributing_observation_count"] == 1
    assert report["summary"]["db_presence_counts"] == {"materialized": 1}
