from __future__ import annotations

import json
import zipfile
from pathlib import Path

import yaml

from scripts.validation.check_citation_reference_graph_line_checkpoint import check_line_checkpoint
from scripts.validation.check_citation_reference_graph_line_checkpoint import main as validator_main


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_fixture(base: Path) -> Path:
    graph_dir = base / "data/graphs/citation_reference_graph/v0.1"
    package_dir = base / "data/graphs/citation_reference_graph/packages/v0.1"
    report_dir = base / "artifacts/reports/validation"
    config_path = base / "configs/citation_reference_graph_line_checkpoint.yaml"

    graph_dir.mkdir(parents=True)
    package_dir.mkdir(parents=True)
    report_dir.mkdir(parents=True)
    config_path.parent.mkdir(parents=True)

    tracked_files = [
        config_path,
        base / "scripts/validation/check_citation_reference_graph_line_checkpoint.py",
        base / "tests/smoke/test_citation_reference_graph_line_checkpoint.py",
        base / "docs/citation_reference_graph_line_checkpoint_v0.md",
    ]
    for path in tracked_files[1:]:
        _write_text(path, "# tracked fixture\n")

    for name in ["nodes.jsonl", "edges.jsonl", "README.md", "checksums.txt"]:
        _write_text(graph_dir / name, "{}\n")
    _write_json(graph_dir / "schema.json", {"schema_version": "citation_reference_graph_schema_v1"})
    _write_json(
        graph_dir / "manifest.json",
        {
            "schema_version": "citation_reference_graph_manifest_v1",
            "generated_at": "2026-07-03T19:31:11+00:00",
            "builder": {
                "script": "scripts/export/build_citation_reference_graph.py",
                "input_mode": "file",
                "live_db_dependency": False,
                "limit": None,
            },
            "graph": {
                "name": "citation_reference_graph",
                "version": "v0.1",
                "status": "local_derived_output",
            },
            "counts": {
                "nodes_count": 8,
                "edges_count": 7,
                "paper_nodes_count": 2,
                "external_reference_nodes_count": 5,
                "source_family_nodes_count": 1,
                "paper_references_paper_edges_count": 1,
                "paper_references_external_edges_count": 5,
                "paper_has_reference_source_family_edges_count": 1,
            },
            "quality": {
                "ok": True,
                "stats": {
                    "resolved_reference_edges_count": 1,
                    "unresolved_reference_edges_count": 5,
                },
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
    _write_json(graph_dir / "data_quality_summary.json", {"ok": True})

    _write_json(report_dir / "citation_reference_graph_output_latest.json", {"ok": True, "required_failed_count": 0})
    _write_json(report_dir / "citation_reference_graph_inspection_latest.json", {"ok": True, "required_failed_count": 0})
    _write_json(
        report_dir / "citation_reference_graph_release_candidate_latest.json",
        {
            "summary": {"ok": True, "required_failed_count": 0, "warning_count": 0},
            "verdict": {
                "technical_graph_candidate_ready": True,
                "manual_review_required": True,
                "manual_review_complete": False,
                "publication_ready": False,
                "publication_block_reason": "manual_review_not_completed",
            },
        },
    )
    _write_json(
        report_dir / "citation_reference_graph_package_latest.json",
        {
            "summary": {"ok": True, "required_failed_count": 0, "warning_count": 0},
            "verdict": {
                "package_candidate_ready": True,
                "manual_review_required": True,
                "manual_review_complete": False,
                "publication_ready": False,
                "publication_block_reason": "manual_review_not_completed",
            },
        },
    )

    zip_path = package_dir / "citation_reference_graph_v0.1.zip"
    with zipfile.ZipFile(zip_path, mode="w") as archive:
        archive.writestr("citation_reference_graph_v0.1/README.md", "fixture\n")
    _write_text(package_dir / "README.md", "# Package fixture\n")
    _write_text(package_dir / "checksums.txt", "fixture  README.md\n")
    _write_json(
        package_dir / "package_manifest.json",
        {
            "schema_version": "citation_reference_graph_package_manifest_v1",
            "package": {
                "name": "citation_reference_graph",
                "version": "v0.1",
                "status": "local_package_candidate",
                "publication_ready": False,
                "manual_review_required": True,
                "may_be_used_as_reconcile_input": False,
            },
            "graph": {
                "counts": {
                    "nodes_count": 8,
                    "edges_count": 7,
                    "paper_nodes_count": 2,
                    "external_reference_nodes_count": 5,
                    "source_family_nodes_count": 1,
                    "paper_references_paper_edges_count": 1,
                    "paper_references_external_edges_count": 5,
                    "paper_has_reference_source_family_edges_count": 1,
                }
            },
            "release_candidate": {
                "summary_ok": True,
                "required_failed_count": 0,
                "technical_graph_candidate_ready": True,
                "manual_review_required": True,
                "manual_review_complete": False,
                "publication_ready": False,
            },
            "boundaries": {
                "local_package_candidate": True,
                "generated_output": True,
                "read_only_graph_input": True,
                "rebuilds_graph": False,
                "mutates_canonical_truth": False,
                "may_be_used_as_reconcile_input": False,
                "changes_postgres": False,
                "changes_db_schema": False,
                "changes_qdrant": False,
                "changes_retrieval": False,
                "changes_ranking": False,
                "changes_api": False,
                "changes_ui": False,
                "parses_full_text": False,
                "parses_pdfs": False,
                "parses_bibliography_sections": False,
                "requires_networkx_runtime": False,
                "requires_neo4j_runtime": False,
                "requires_graphrag_runtime": False,
                "publishes_graph": False,
                "publishes_dataset": False,
            },
        },
    )

    config = {
        "schema_version": "citation_reference_graph_line_checkpoint_config_v1",
        "checkpoint": {
            "name": "citation_reference_graph_line_checkpoint",
            "version": "v0.1",
            "status": "local_line_checkpoint",
            "publication_ready": False,
            "manual_review_required": True,
            "manual_review_complete": False,
            "may_be_used_as_reconcile_input": False,
        },
        "inputs": {
            "graph_dir": str(graph_dir),
            "package_dir": str(package_dir),
            "output_report_json": str(report_dir / "citation_reference_graph_output_latest.json"),
            "inspection_report_json": str(report_dir / "citation_reference_graph_inspection_latest.json"),
            "release_candidate_report_json": str(report_dir / "citation_reference_graph_release_candidate_latest.json"),
            "package_report_json": str(report_dir / "citation_reference_graph_package_latest.json"),
            "package_manifest_path": str(package_dir / "package_manifest.json"),
        },
        "validation": {"report_dir": str(report_dir)},
        "tracked_files": [str(path) for path in tracked_files],
        "required_graph_files": [
            "nodes.jsonl",
            "edges.jsonl",
            "schema.json",
            "manifest.json",
            "data_quality_summary.json",
            "README.md",
            "checksums.txt",
        ],
        "required_package_files": [
            "citation_reference_graph_v0.1.zip",
            "package_manifest.json",
            "README.md",
            "checksums.txt",
        ],
        "accepted_components": {
            "contract": "accepted_contract_only",
            "builder": "accepted_local_derived_builder",
            "output_validator": "accepted_strict_validator",
            "reference_normalization_fix": "accepted_openalex_reference_id_normalization",
            "inspection": "accepted_read_only_inspection",
            "query_cli": "accepted_read_only_query_cli",
            "docs_counter_refresh": "accepted_docs_counter_refresh",
            "release_candidate": "accepted_read_only_release_candidate",
            "package": "accepted_local_package_candidate",
        },
        "expected_counts": {
            "nodes_count": 8,
            "edges_count": 7,
            "node_paper_count": 2,
            "node_external_reference_count": 5,
            "node_source_family_count": 1,
            "edge_paper_references_paper_count": 1,
            "edge_paper_references_external_count": 5,
            "edge_paper_has_reference_source_family_count": 1,
        },
        "expected_quality": {
            "resolved_reference_edges_count": 1,
            "unresolved_reference_edges_count": 5,
            "reference_resolution_ratio": 0.2,
        },
        "safety": {
            "read_only_checkpoint": True,
            "read_existing_graph_output": True,
            "read_existing_package_output": True,
            "rebuild_graph": False,
            "rebuild_package": False,
            "mutate_canonical_documents": False,
            "mutate_retrieval_artifacts": False,
            "mutate_qdrant": False,
            "mutate_postgres": False,
            "mutate_db_schema": False,
            "mutate_api": False,
            "mutate_ui": False,
            "mutate_ranking": False,
            "publish_dataset": False,
            "publish_graph": False,
            "create_latest_pointer": False,
            "create_graph_runtime": False,
            "require_networkx_runtime": False,
            "require_neo4j_runtime": False,
            "require_graphrag_runtime": False,
            "parse_full_text": False,
            "parse_pdfs": False,
            "parse_bibliography_sections": False,
        },
    }
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return config_path


def test_line_checkpoint_passes_on_complete_fixture(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)

    result = check_line_checkpoint(config_path=config_path, strict=True)

    assert result["summary"]["ok"] is True
    assert result["summary"]["required_failed_count"] == 0
    assert result["verdict"]["citation_reference_graph_line_complete"] is True
    assert result["verdict"]["publication_ready"] is False


def test_failed_package_report_is_detected(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    report_path = tmp_path / "artifacts/reports/validation/citation_reference_graph_package_latest.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["summary"]["ok"] = False
    report["summary"]["required_failed_count"] = 1
    report["verdict"]["package_candidate_ready"] = False
    _write_json(report_path, report)

    result = check_line_checkpoint(config_path=config_path, strict=True, write_reports=False)

    assert result["summary"]["ok"] is False
    assert "package_report_green" in result["verdict"]["required_failed_checks"]


def test_graph_count_mismatch_is_detected(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    manifest_path = tmp_path / "data/graphs/citation_reference_graph/v0.1/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["counts"]["edges_count"] = 999
    _write_json(manifest_path, manifest)

    result = check_line_checkpoint(config_path=config_path, strict=True, write_reports=False)

    assert result["summary"]["ok"] is False
    assert "accepted_graph_counts" in result["verdict"]["required_failed_checks"]


def test_unsafe_package_manifest_is_detected(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    manifest_path = tmp_path / "data/graphs/citation_reference_graph/packages/v0.1/package_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["package"]["publication_ready"] = True
    _write_json(manifest_path, manifest)

    result = check_line_checkpoint(config_path=config_path, strict=True, write_reports=False)

    assert result["summary"]["ok"] is False
    assert "package_manifest_safety" in result["verdict"]["required_failed_checks"]


def test_validator_cli_no_write_reports_path(tmp_path: Path, monkeypatch) -> None:
    config_path = _make_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = validator_main(["--config", str(config_path), "--strict", "--no-write-reports"])

    assert exit_code == 0
