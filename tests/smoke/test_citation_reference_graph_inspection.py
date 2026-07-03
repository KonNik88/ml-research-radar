from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts.validation.check_citation_reference_graph_inspection import inspect_graph, main


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _write_config(path: Path, graph_dir: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "citation_reference_graph_contract_v1",
                "outputs": {"expected_future_output_dir": str(graph_dir)},
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _make_graph(tmp_path: Path, *, unsafe: bool = False, bad_quality: bool = False, dangling: bool = False) -> tuple[Path, Path]:
    graph_dir = tmp_path / "data" / "graphs" / "citation_reference_graph" / "v0.1"
    config_path = tmp_path / "configs" / "citation_reference_graph.yaml"
    _write_config(config_path, graph_dir)

    nodes = [
        {"node_id": "paper:p1", "node_type": "paper", "canonical_id": "p1", "title": "A", "source_layer": "canonical_documents"},
        {"node_id": "paper:p2", "node_type": "paper", "canonical_id": "p2", "title": "B", "source_layer": "canonical_documents"},
        {"node_id": "external_reference:e1", "node_type": "external_reference", "reference_key": "doi:10.1/x", "reference_type": "doi", "normalized_value": "10.1/x", "resolution_status": "unresolved_external", "source_layer": "canonical_reference_fields"},
        {"node_id": "source_family:arxiv", "node_type": "source_family", "source_family": "arxiv", "source_layer": "source_provenance"},
    ]
    edges = [
        {"edge_id": "e1", "edge_type": "paper_references_paper", "source_node_id": "paper:p1", "target_node_id": "paper:p2", "source_canonical_id": "p1", "target_canonical_id": "p2", "reference_type": "arxiv_id", "reference_field": "referenced_arxiv_ids", "provenance_kind": "canonical_reference", "source_layer": "canonical_reference_fields", "confidence": 1.0},
        {"edge_id": "e2", "edge_type": "paper_references_external", "source_node_id": "paper:p1", "target_node_id": "external_reference:e1", "source_canonical_id": "p1", "target_reference_key": "doi:10.1/x", "reference_type": "doi", "reference_field": "referenced_dois", "provenance_kind": "external_identifier_reference", "source_layer": "canonical_reference_fields", "confidence": 0.8},
        {"edge_id": "e3", "edge_type": "paper_has_reference_source_family", "source_node_id": "paper:p1", "target_node_id": "source_family:arxiv", "source_canonical_id": "p1", "source_family": "arxiv", "provenance_kind": "source_family_reference", "source_layer": "source_provenance", "confidence": 1.0},
    ]
    if dangling:
        edges[0] = {**edges[0], "target_node_id": "paper:missing"}

    _write_jsonl(graph_dir / "nodes.jsonl", nodes)
    _write_jsonl(graph_dir / "edges.jsonl", edges)
    _write_json(
        graph_dir / "schema.json",
        {
            "node_types": {"paper": {}, "external_reference": {}, "source_family": {}},
            "edge_types": {"paper_references_paper": {}, "paper_references_external": {}, "paper_has_reference_source_family": {}},
        },
    )
    _write_json(
        graph_dir / "manifest.json",
        {
            "builder": {"input_mode": "file", "live_db_dependency": False},
            "counts": {"nodes_count": len(nodes), "edges_count": len(edges), "paper_nodes_count": 2},
            "safety": {
                "may_overwrite_operational_latest": False,
                "may_be_used_as_reconcile_input": False,
                "may_change_db_schema": False,
                "may_change_api_behavior": False,
                "may_change_streamlit_behavior": False,
                "may_change_retrieval_behavior": False,
                "may_change_qdrant_behavior": False,
                "may_change_ranking_behavior": False,
                "may_require_graph_runtime": False,
                "may_publish_without_manual_review": False,
            },
        },
    )
    if unsafe:
        manifest = json.loads((graph_dir / "manifest.json").read_text(encoding="utf-8"))
        manifest["safety"]["may_change_db_schema"] = True
        _write_json(graph_dir / "manifest.json", manifest)
    _write_json(graph_dir / "data_quality_summary.json", {"summary": {"ok": not bad_quality}})
    (graph_dir / "README.md").write_text("# graph\n", encoding="utf-8")
    (graph_dir / "checksums.txt").write_text("dummy  nodes.jsonl\n", encoding="utf-8")
    return config_path, graph_dir


def test_valid_graph_inspection_passes_and_reports_metrics(tmp_path: Path) -> None:
    config_path, graph_dir = _make_graph(tmp_path)
    report = inspect_graph(config_path=config_path, graph_dir=graph_dir, write_reports=False)
    assert report["summary"]["ok"] is True
    assert report["inspection"]["resolved_reference_edges_count"] == 1
    assert report["inspection"]["unresolved_reference_edges_count"] == 1
    assert report["inspection"]["reference_resolution_ratio"] == 0.5
    assert report["inspection"]["papers_with_outgoing_reference_edges_count"] == 1
    assert report["inspection"]["top_referenced_papers"][0]["canonical_id"] == "p2"


def test_report_writing(tmp_path: Path) -> None:
    config_path, graph_dir = _make_graph(tmp_path)
    report_dir = tmp_path / "reports"
    report = inspect_graph(config_path=config_path, graph_dir=graph_dir, report_dir=report_dir)
    assert report["summary"]["ok"] is True
    assert (report_dir / "citation_reference_graph_inspection_latest.json").exists()
    assert (report_dir / "citation_reference_graph_inspection_latest.md").exists()
    assert any((report_dir / "history").glob("citation_reference_graph_inspection_*.json"))


def test_missing_required_file_fails(tmp_path: Path) -> None:
    config_path, graph_dir = _make_graph(tmp_path)
    (graph_dir / "edges.jsonl").unlink()
    report = inspect_graph(config_path=config_path, graph_dir=graph_dir, write_reports=False)
    assert report["summary"]["ok"] is False
    assert any(c["name"] == "required_file_exists:edges.jsonl" for c in report["failed_required_checks"])


def test_unsafe_manifest_fails(tmp_path: Path) -> None:
    config_path, graph_dir = _make_graph(tmp_path, unsafe=True)
    report = inspect_graph(config_path=config_path, graph_dir=graph_dir, write_reports=False)
    assert report["summary"]["ok"] is False
    assert any(c["name"] == "manifest_safety_flags_false" for c in report["failed_required_checks"])


def test_bad_data_quality_fails(tmp_path: Path) -> None:
    config_path, graph_dir = _make_graph(tmp_path, bad_quality=True)
    report = inspect_graph(config_path=config_path, graph_dir=graph_dir, write_reports=False)
    assert report["summary"]["ok"] is False
    assert any(c["name"] == "data_quality_summary_ok" for c in report["failed_required_checks"])


def test_dangling_edge_fails(tmp_path: Path) -> None:
    config_path, graph_dir = _make_graph(tmp_path, dangling=True)
    report = inspect_graph(config_path=config_path, graph_dir=graph_dir, write_reports=False)
    assert report["summary"]["ok"] is False
    assert any(c["name"] == "edge_endpoints_resolve" for c in report["failed_required_checks"])


def test_cli_returns_zero_for_valid_graph(tmp_path: Path) -> None:
    config_path, graph_dir = _make_graph(tmp_path)
    report_dir = tmp_path / "reports"
    exit_code = main(["--config-path", str(config_path), "--graph-dir", str(graph_dir), "--report-dir", str(report_dir), "--strict"])
    assert exit_code == 0
