from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.graph.query_citation_reference_graph import (
    attach_meta,
    load_graph_index,
    query_graph,
    render_markdown,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def make_graph_output(tmp_path: Path) -> Path:
    graph_dir = tmp_path / "data" / "graphs" / "citation_reference_graph" / "v0.1"

    nodes = [
        {
            "node_id": "paper:paper_1",
            "node_type": "paper",
            "canonical_id": "paper_1",
            "title": "Paper 1",
            "year": 2024,
            "doi": "10.1000/paper1",
            "arxiv_id": "2401.00001",
            "source_layer": "canonical_documents",
        },
        {
            "node_id": "paper:paper_2",
            "node_type": "paper",
            "canonical_id": "paper_2",
            "title": "Paper 2",
            "year": 2023,
            "doi": "10.1000/paper2",
            "arxiv_id": "2301.00002",
            "source_layer": "canonical_documents",
        },
        {
            "node_id": "paper:paper_3",
            "node_type": "paper",
            "canonical_id": "paper_3",
            "title": "Paper 3",
            "year": 2022,
            "doi": None,
            "arxiv_id": "2201.00003",
            "source_layer": "canonical_documents",
        },
        {
            "node_id": "external_reference:ext1",
            "node_type": "external_reference",
            "reference_key": "doi:10.9999/external",
            "reference_type": "doi",
            "normalized_value": "10.9999/external",
            "resolution_status": "unresolved_external",
            "source_layer": "canonical_reference_fields",
        },
        {
            "node_id": "source_family:openalex_alignment",
            "node_type": "source_family",
            "source_family": "openalex_alignment",
            "source_layer": "source_provenance",
        },
    ]

    edges = [
        {
            "edge_id": "edge:paper1-paper2",
            "edge_type": "paper_references_paper",
            "source_node_id": "paper:paper_1",
            "target_node_id": "paper:paper_2",
            "source_canonical_id": "paper_1",
            "target_canonical_id": "paper_2",
            "reference_type": "doi",
            "reference_value": "10.1000/paper2",
            "reference_field": "referenced_dois",
            "resolution_status": "resolved_to_canonical",
            "provenance_kind": "canonical_reference",
            "source_layer": "canonical_reference_fields",
            "confidence": 1.0,
        },
        {
            "edge_id": "edge:paper1-ext1",
            "edge_type": "paper_references_external",
            "source_node_id": "paper:paper_1",
            "target_node_id": "external_reference:ext1",
            "source_canonical_id": "paper_1",
            "target_reference_key": "doi:10.9999/external",
            "reference_type": "doi",
            "reference_value": "10.9999/external",
            "reference_field": "referenced_dois",
            "resolution_status": "unresolved_external",
            "provenance_kind": "external_identifier_reference",
            "source_layer": "canonical_reference_fields",
            "confidence": 0.8,
        },
        {
            "edge_id": "edge:paper3-ext1",
            "edge_type": "paper_references_external",
            "source_node_id": "paper:paper_3",
            "target_node_id": "external_reference:ext1",
            "source_canonical_id": "paper_3",
            "target_reference_key": "doi:10.9999/external",
            "reference_type": "doi",
            "reference_value": "10.9999/external",
            "reference_field": "referenced_ids",
            "resolution_status": "unresolved_external",
            "provenance_kind": "external_identifier_reference",
            "source_layer": "canonical_reference_fields",
            "confidence": 0.8,
        },
        {
            "edge_id": "edge:paper1-source",
            "edge_type": "paper_has_reference_source_family",
            "source_node_id": "paper:paper_1",
            "target_node_id": "source_family:openalex_alignment",
            "source_canonical_id": "paper_1",
            "source_family": "openalex_alignment",
            "provenance_kind": "source_family_reference",
            "source_layer": "source_provenance",
            "confidence": 1.0,
        },
    ]

    manifest = {
        "schema_version": "citation_reference_graph_manifest_v1",
        "graph": {"name": "citation_reference_graph", "version": "v0.1", "status": "local_derived_output"},
        "counts": {
            "nodes_count": len(nodes),
            "edges_count": len(edges),
            "paper_nodes_count": 3,
            "external_reference_nodes_count": 1,
            "source_family_nodes_count": 1,
            "paper_references_paper_edges_count": 1,
            "paper_references_external_edges_count": 2,
            "paper_has_reference_source_family_edges_count": 1,
        },
        "safety": {
            "may_be_used_as_reconcile_input": False,
            "may_change_db_schema": False,
            "may_change_api_behavior": False,
        },
    }
    quality = {
        "schema_version": "citation_reference_graph_data_quality_summary_v1",
        "summary": {"ok": True, "nodes_count": len(nodes), "edges_count": len(edges)},
        "quality": {"ok": True},
    }

    write_jsonl(graph_dir / "nodes.jsonl", nodes)
    write_jsonl(graph_dir / "edges.jsonl", edges)
    write_json(graph_dir / "manifest.json", manifest)
    write_json(graph_dir / "data_quality_summary.json", quality)
    return graph_dir


def test_query_by_paper_returns_outgoing_internal_and_external_refs(tmp_path: Path):
    graph_dir = make_graph_output(tmp_path)
    index = load_graph_index(graph_dir)

    result = query_graph(index, paper_id="paper_1", top_k=10)

    assert result["query_type"] == "paper"
    assert result["found"] is True
    assert result["counts"]["internal_references"] == 1
    assert result["counts"]["external_references"] == 1
    assert result["internal_references"][0]["canonical_id"] == "paper_2"
    assert result["external_references"][0]["reference_key"] == "doi:10.9999/external"


def test_query_by_cited_paper_returns_incoming_internal_refs(tmp_path: Path):
    graph_dir = make_graph_output(tmp_path)
    index = load_graph_index(graph_dir)

    result = query_graph(index, cited_paper_id="paper_2", top_k=10)

    assert result["query_type"] == "cited_paper"
    assert result["found"] is True
    assert result["counts"]["incoming_internal_references"] == 1
    assert result["citing_papers"][0]["canonical_id"] == "paper_1"


def test_query_by_external_reference_returns_citing_papers(tmp_path: Path):
    graph_dir = make_graph_output(tmp_path)
    index = load_graph_index(graph_dir)

    result = query_graph(index, external_reference="doi:10.9999/external", top_k=10)

    assert result["query_type"] == "external_reference"
    assert result["found"] is True
    assert result["counts"]["matched_external_reference_nodes"] == 1
    assert result["counts"]["citing_papers"] == 2
    assert {row["canonical_id"] for row in result["citing_papers"]} == {"paper_1", "paper_3"}


def test_top_referenced_papers_ranks_by_incoming_internal_refs(tmp_path: Path):
    graph_dir = make_graph_output(tmp_path)
    index = load_graph_index(graph_dir)

    result = query_graph(index, top_referenced_papers=True, top_k=5)

    assert result["query_type"] == "top_referenced_papers"
    assert result["found"] is True
    assert result["papers"][0]["canonical_id"] == "paper_2"
    assert result["papers"][0]["incoming_internal_references_count"] == 1


def test_top_external_references_ranks_by_citing_papers(tmp_path: Path):
    graph_dir = make_graph_output(tmp_path)
    index = load_graph_index(graph_dir)

    result = query_graph(index, top_external_references=True, top_k=5)

    assert result["query_type"] == "top_external_references"
    assert result["found"] is True
    assert result["external_references"][0]["reference_key"] == "doi:10.9999/external"
    assert result["external_references"][0]["citing_papers_count"] == 2


def test_source_family_query_returns_reference_bearing_papers(tmp_path: Path):
    graph_dir = make_graph_output(tmp_path)
    index = load_graph_index(graph_dir)

    result = query_graph(index, source_family="openalex_alignment", top_k=10)

    assert result["query_type"] == "source_family"
    assert result["found"] is True
    assert result["counts"]["reference_bearing_papers"] == 1
    assert result["papers"][0]["canonical_id"] == "paper_1"


def test_markdown_render_contains_caveat_and_counts(tmp_path: Path):
    graph_dir = make_graph_output(tmp_path)
    index = load_graph_index(graph_dir)
    result = query_graph(index, top_external_references=True, top_k=5)
    payload = attach_meta(result, index)

    rendered = render_markdown(payload)

    assert "# Citation / Reference Graph Query" in rendered
    assert "does not parse paper full text" in rendered
    assert "reference_resolution_ratio" in rendered
    assert "doi:10.9999/external" in rendered


def test_cli_json_invocation_returns_payload(tmp_path: Path):
    graph_dir = make_graph_output(tmp_path)

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.graph.query_citation_reference_graph",
            "--graph-dir",
            str(graph_dir),
            "--top-external-references",
            "--top-k",
            "5",
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    payload = json.loads(proc.stdout)

    assert payload["query_type"] == "top_external_references"
    assert payload["found"] is True
    assert payload["meta"]["read_only"] is True
