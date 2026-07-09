from __future__ import annotations

from pathlib import Path

import pytest

from services.api.citation_graph_store import CitationGraphStore


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "citation_graph_v0_1"


def load_store() -> CitationGraphStore:
    return CitationGraphStore.load(FIXTURE_DIR)


def test_fixture_store_loads_graph_summary():
    store = load_store()

    summary = store.graph_summary()

    assert summary["name"] == "citation_reference_graph"
    assert summary["version"] == "v0.1"
    assert summary["nodes_count"] == 6
    assert summary["edges_count"] == 5
    assert summary["paper_nodes"] == 3
    assert summary["external_reference_nodes"] == 1
    assert summary["source_family_nodes"] == 2
    assert summary["paper_references_paper_edges"] == 2
    assert summary["paper_references_external_edges"] == 1
    assert summary["reference_resolution_ratio"] == pytest.approx(0.666667)
    assert summary["metadata_reference_fields_only"] is True
    assert summary["full_text_parsed"] is False
    assert summary["publication_ready"] is False


def test_outgoing_references_include_resolved_and_external_items():
    store = load_store()

    result = store.outgoing_references("paper:a", limit=10).to_dict()

    assert result["found"] is True
    assert result["page"] == {
        "limit": 10,
        "offset": 0,
        "returned": 2,
        "total_estimate": 2,
    }
    assert [item["edge_type"] for item in result["items"]] == [
        "paper_references_paper",
        "paper_references_external",
    ]
    assert result["items"][0]["resolved"] is True
    assert result["items"][0]["target_canonical_id"] == "paper:b"
    assert result["items"][1]["resolved"] is False
    assert result["items"][1]["external_reference_id"] == (
        "external_reference:doi:10.9999/external-one"
    )


def test_incoming_citations_include_only_resolved_internal_edges():
    store = load_store()

    result = store.incoming_citations("paper:b", limit=10).to_dict()

    assert result["found"] is True
    assert result["page"]["returned"] == 2
    assert [item["source_canonical_id"] for item in result["items"]] == [
        "paper:a",
        "paper:c",
    ]
    assert all(item["edge_type"] == "paper_references_paper" for item in result["items"])
    assert {item["reference_type"] for item in result["items"]} == {"doi"}


def test_external_reference_lookup_returns_referencing_papers():
    store = load_store()

    result = store.external_reference_papers(
        "external_reference:doi:10.9999/external-one",
        limit=10,
    ).to_dict()

    assert result["found"] is True
    assert result["page"]["returned"] == 1
    assert result["items"][0]["source_canonical_id"] == "paper:a"
    assert result["items"][0]["external_reference_id"] == (
        "external_reference:doi:10.9999/external-one"
    )

    by_reference_key = store.external_reference_papers(
        "doi:10.9999/external-one",
        limit=10,
    ).to_dict()
    assert by_reference_key["found"] is True
    assert by_reference_key["page"]["returned"] == 1

    by_normalized_value = store.external_reference_papers(
        "10.9999/external-one",
        limit=10,
    ).to_dict()
    assert by_normalized_value["found"] is True
    assert by_normalized_value["page"]["returned"] == 1


def test_source_family_and_top_queries_are_bounded_and_caveated_by_store_contract():
    store = load_store()

    source_families = store.source_family_diagnostics(limit=10).to_dict()
    assert source_families["found"] is True
    assert source_families["page"]["returned"] == 2
    assert source_families["items"][0]["source_family"] == "openalex"
    assert source_families["items"][0]["reference_edge_count"] == 2

    top_papers = store.top_referenced_papers(limit=10).to_dict()
    assert top_papers["found"] is True
    assert top_papers["items"][0]["canonical_id"] == "paper:b"
    assert top_papers["items"][0]["incoming_resolved_reference_count"] == 2
    assert top_papers["items"][0]["source_families"] == [
        "openalex",
        "semantic_scholar",
    ]

    top_external = store.top_external_references(limit=10).to_dict()
    assert top_external["found"] is True
    assert top_external["items"][0]["external_reference_id"] == (
        "external_reference:doi:10.9999/external-one"
    )
    assert top_external["items"][0]["referencing_paper_count"] == 1


def test_unknown_ids_return_found_false_without_throwing():
    store = load_store()

    outgoing = store.outgoing_references("paper:missing").to_dict()
    incoming = store.incoming_citations("paper:missing").to_dict()
    external = store.external_reference_papers("doi:missing").to_dict()

    assert outgoing["found"] is False
    assert incoming["found"] is False
    assert external["found"] is False
    assert outgoing["items"] == []
    assert incoming["items"] == []
    assert external["items"] == []


def test_pagination_and_limit_validation():
    store = load_store()

    page = store.outgoing_references("paper:a", limit=1, offset=1).to_dict()
    assert page["page"] == {
        "limit": 1,
        "offset": 1,
        "returned": 1,
        "total_estimate": 2,
    }
    assert page["items"][0]["edge_type"] == "paper_references_external"

    with pytest.raises(ValueError, match="limit must be >= 1"):
        store.outgoing_references("paper:a", limit=0)

    with pytest.raises(ValueError, match="limit must be <="):
        store.outgoing_references("paper:a", limit=101)

    with pytest.raises(ValueError, match="offset must be >= 0"):
        store.outgoing_references("paper:a", offset=-1)
