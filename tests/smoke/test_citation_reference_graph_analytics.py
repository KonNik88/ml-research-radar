from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts.validation.check_citation_reference_graph_analytics import main, validate_graph_analytics


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _write_yaml(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(obj, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _make_fixture(base: Path) -> Path:
    graph_dir = base / "data/graphs/citation_reference_graph/v0.1"
    report_dir = base / "artifacts/reports/validation"
    config_path = base / "configs/citation_reference_graph_analytics.yaml"

    nodes = [
        {"node_id": "paper:p1", "node_type": "paper", "canonical_id": "p1", "title": "Paper 1"},
        {"node_id": "paper:p2", "node_type": "paper", "canonical_id": "p2", "title": "Paper 2"},
        {"node_id": "paper:p3", "node_type": "paper", "canonical_id": "p3", "title": "Paper 3"},
        {
            "node_id": "external_reference:doi:10.1/example",
            "node_type": "external_reference",
            "reference_key": "doi:10.1/example",
        },
        {
            "node_id": "external_reference:openalex_id:W1",
            "node_type": "external_reference",
            "reference_key": "openalex_id:W1",
        },
        {"node_id": "source_family:arxiv", "node_type": "source_family", "source_family": "arxiv"},
        {"node_id": "source_family:openalex", "node_type": "source_family", "source_family": "openalex"},
    ]
    edges = [
        {
            "edge_id": "e1",
            "edge_type": "paper_references_paper",
            "source_node_id": "paper:p1",
            "target_node_id": "paper:p2",
            "source_canonical_id": "p1",
            "target_canonical_id": "p2",
            "reference_type": "doi",
            "reference_field": "referenced_dois",
            "confidence": 1.0,
        },
        {
            "edge_id": "e2",
            "edge_type": "paper_references_external",
            "source_node_id": "paper:p1",
            "target_node_id": "external_reference:doi:10.1/example",
            "source_canonical_id": "p1",
            "target_reference_key": "doi:10.1/example",
            "reference_type": "doi",
            "reference_field": "referenced_dois",
            "confidence": 1.0,
        },
        {
            "edge_id": "e3",
            "edge_type": "paper_references_external",
            "source_node_id": "paper:p2",
            "target_node_id": "external_reference:openalex_id:W1",
            "source_canonical_id": "p2",
            "target_reference_key": "openalex_id:W1",
            "reference_type": "openalex_id",
            "reference_field": "referenced_ids",
            "confidence": 1.0,
        },
        {
            "edge_id": "e4",
            "edge_type": "paper_has_reference_source_family",
            "source_node_id": "paper:p1",
            "target_node_id": "source_family:arxiv",
            "source_canonical_id": "p1",
            "source_family": "arxiv",
            "confidence": 1.0,
        },
        {
            "edge_id": "e5",
            "edge_type": "paper_has_reference_source_family",
            "source_node_id": "paper:p2",
            "target_node_id": "source_family:openalex",
            "source_canonical_id": "p2",
            "source_family": "openalex",
            "confidence": 1.0,
        },
    ]

    _write_jsonl(graph_dir / "nodes.jsonl", nodes)
    _write_jsonl(graph_dir / "edges.jsonl", edges)
    _write_json(
        graph_dir / "manifest.json",
        {
            "schema_version": "citation_reference_graph_manifest_v1",
            "graph": {
                "name": "citation_reference_graph",
                "version": "v0.1",
                "status": "local_derived_output",
            },
            "builder": {
                "input_mode": "file",
                "live_db_dependency": False,
                "script": "scripts/export/build_citation_reference_graph.py",
            },
            "counts": {
                "nodes_count": 7,
                "edges_count": 5,
                "paper_nodes_count": 3,
                "external_reference_nodes_count": 2,
                "source_family_nodes_count": 2,
                "paper_references_paper_edges_count": 1,
                "paper_references_external_edges_count": 2,
                "paper_has_reference_source_family_edges_count": 2,
            },
            "safety": {
                "canonical_truth_impact": "none",
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
    _write_json(graph_dir / "data_quality_summary.json", {"summary": {"ok": True}})
    _write_json(
        report_dir / "citation_reference_graph_manual_review_latest.json",
        {
            "schema_version": "citation_reference_graph_manual_review_v1",
            "summary": {"ok": True, "required_failed_count": 0, "warning_count": 0},
            "verdict": {
                "manual_review_required": True,
                "manual_review_complete": False,
                "publication_ready": False,
                "publication_block_reason": "manual_review_not_completed",
            },
        },
    )

    config = {
        "schema_version": "citation_reference_graph_analytics_config_v1",
        "analytics": {
            "name": "citation_reference_graph_analytics",
            "version": "v0.1",
            "status": "local_read_only_analytics",
            "graph_version": "v0.1",
            "publication_ready": False,
            "manual_review_support": True,
            "may_be_used_as_reconcile_input": False,
        },
        "inputs": {
            "graph_dir": str(graph_dir),
            "nodes_path": str(graph_dir / "nodes.jsonl"),
            "edges_path": str(graph_dir / "edges.jsonl"),
            "manifest_path": str(graph_dir / "manifest.json"),
            "data_quality_summary_path": str(graph_dir / "data_quality_summary.json"),
            "manual_review_report": str(report_dir / "citation_reference_graph_manual_review_latest.json"),
        },
        "validation": {"report_dir": str(report_dir), "strict_default": True},
        "expected_counts": {
            "nodes_count": 7,
            "edges_count": 5,
            "node_paper_count": 3,
            "node_external_reference_count": 2,
            "node_source_family_count": 2,
            "edge_paper_references_paper_count": 1,
            "edge_paper_references_external_count": 2,
            "edge_paper_has_reference_source_family_count": 2,
        },
        "expected_analytics": {
            "resolved_reference_edges_count": 1,
            "unresolved_reference_edges_count": 2,
            "reference_resolution_ratio": 0.333333,
            "min_papers_with_outgoing_reference_edges_count": 1,
            "min_papers_with_internal_reference_edges_count": 1,
            "min_papers_with_external_reference_edges_count": 1,
            "min_papers_with_incoming_internal_reference_edges_count": 1,
            "min_reference_type_count": 1,
            "min_reference_field_count": 1,
            "min_source_family_count": 1,
            "required_reference_types": ["doi", "openalex_id"],
            "required_source_families": ["arxiv", "openalex"],
        },
        "manual_review_caveats": {
            "metadata_reference_fields_only": True,
            "full_text_parsed": False,
            "pdfs_parsed": False,
            "bibliography_sections_parsed": False,
            "raw_reference_strings_without_identifiers_parsed": False,
            "unresolved_references_preserved_as_external_reference_nodes": True,
            "low_resolution_ratio_expected_in_v0_1": True,
            "reference_resolution_ratio": 0.333333,
        },
        "outputs": {
            "latest_json": str(report_dir / "citation_reference_graph_analytics_latest.json"),
            "latest_md": str(report_dir / "citation_reference_graph_analytics_latest.md"),
            "history_dir": str(report_dir / "history"),
        },
        "safety": {
            "read_only_analytics": True,
            "rebuild_graph": False,
            "rebuild_package": False,
            "approve_manual_review": False,
            "mutate_canonical_documents": False,
            "mutate_reconcile_inputs": False,
            "mutate_retrieval_artifacts": False,
            "mutate_qdrant": False,
            "mutate_postgres": False,
            "mutate_db_schema": False,
            "mutate_api": False,
            "mutate_streamlit": False,
            "mutate_ranking": False,
            "publish_dataset": False,
            "create_latest_pointer": False,
            "create_graph_runtime": False,
            "parse_full_text": False,
            "parse_pdfs": False,
            "parse_bibliography_sections": False,
            "may_be_used_as_reconcile_input": False,
        },
    }
    _write_yaml(config_path, config)
    return config_path


def _load_config(config_path: Path) -> dict:
    return yaml.safe_load(config_path.read_text(encoding="utf-8"))


def _write_config(config_path: Path, config: dict) -> None:
    _write_yaml(config_path, config)


def _assert_failed(result: dict, check_name: str) -> None:
    assert result["summary"]["ok"] is False
    assert check_name in result["verdict"]["required_failed_checks"]


def test_graph_analytics_green_path(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)

    result = validate_graph_analytics(config_path=config_path, strict=True, write_reports=False)

    assert result["summary"]["ok"] is True
    assert result["summary"]["required_failed_count"] == 0
    assert result["summary"]["reference_resolution_ratio"] == 0.333333
    assert result["verdict"]["manual_review_support"] is True
    assert result["verdict"]["publication_ready"] is False


def test_graph_analytics_no_write_reports(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)

    result = validate_graph_analytics(config_path=config_path, strict=True, write_reports=False)

    assert result["summary"]["ok"] is True
    assert not (tmp_path / "artifacts/reports/validation/citation_reference_graph_analytics_latest.json").exists()


def test_graph_analytics_fails_on_missing_required_edge_type(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    config = _load_config(config_path)
    edges_path = Path(config["inputs"]["edges_path"])
    rows = [json.loads(line) for line in edges_path.read_text(encoding="utf-8").splitlines()]
    rows = [row for row in rows if row["edge_type"] != "paper_references_external"]
    _write_jsonl(edges_path, rows)

    result = validate_graph_analytics(config_path=config_path, strict=True, write_reports=False)

    _assert_failed(result, "required_edge_types_present")
    _assert_failed(result, "accepted_graph_counts")


def test_graph_analytics_fails_on_count_mismatch(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    config = _load_config(config_path)
    config["expected_counts"]["nodes_count"] = 999
    _write_config(config_path, config)

    result = validate_graph_analytics(config_path=config_path, strict=True, write_reports=False)

    _assert_failed(result, "accepted_graph_counts")


def test_graph_analytics_fails_on_manifest_safety_flag(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    config = _load_config(config_path)
    manifest_path = Path(config["inputs"]["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["safety"]["may_change_api_behavior"] = True
    _write_json(manifest_path, manifest)

    result = validate_graph_analytics(config_path=config_path, strict=True, write_reports=False)

    _assert_failed(result, "manifest_safety_flags")


def test_graph_analytics_fails_on_data_quality_not_ok(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    config = _load_config(config_path)
    data_quality_path = Path(config["inputs"]["data_quality_summary_path"])
    _write_json(data_quality_path, {"summary": {"ok": False}})

    result = validate_graph_analytics(config_path=config_path, strict=True, write_reports=False)

    _assert_failed(result, "data_quality_summary_ok")


def test_graph_analytics_fails_on_manual_review_report_not_green(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    config = _load_config(config_path)
    report_path = Path(config["inputs"]["manual_review_report"])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["summary"]["ok"] = False
    _write_json(report_path, report)

    result = validate_graph_analytics(config_path=config_path, strict=True, write_reports=False)

    _assert_failed(result, "manual_review_report_green")


def test_graph_analytics_fails_on_unsafe_config_flag(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    config = _load_config(config_path)
    config["safety"]["rebuild_graph"] = True
    _write_config(config_path, config)

    result = validate_graph_analytics(config_path=config_path, strict=True, write_reports=False)

    _assert_failed(result, "analytics_safety_config")


def test_graph_analytics_fails_on_missing_required_reference_type(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    config = _load_config(config_path)
    config["expected_analytics"]["required_reference_types"] = ["doi", "semantic_scholar_id"]
    _write_config(config_path, config)

    result = validate_graph_analytics(config_path=config_path, strict=True, write_reports=False)

    _assert_failed(result, "required_reference_types_present")


def test_graph_analytics_fails_on_caveat_drift(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    config = _load_config(config_path)
    config["manual_review_caveats"]["full_text_parsed"] = True
    _write_config(config_path, config)

    result = validate_graph_analytics(config_path=config_path, strict=True, write_reports=False)

    _assert_failed(result, "manual_review_caveats")


def test_graph_analytics_cli_no_write_reports(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)

    rc = main(["--config", str(config_path), "--strict", "--no-write-reports"])

    assert rc == 0
