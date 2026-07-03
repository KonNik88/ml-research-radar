from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path
from typing import Any

import yaml

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "validation" / "check_citation_reference_graph_contract.py"
spec = importlib.util.spec_from_file_location("check_citation_reference_graph_contract", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _base_config() -> dict[str, Any]:
    return {
        "schema_version": "citation_reference_graph_config_v1",
        "graph": {
            "name": "citation_reference_graph",
            "version": "v0.1",
            "status": "contract_only",
            "graph_family": "paper_reference_evidence_graph",
        },
        "source_checkpoint": {
            "canonical_corpus_path": "data/analytics/reconciled/canonical_documents.jsonl",
            "expected_canonical_doc_count": 60954,
            "retrieval_manifest_path": "artifacts/retrieval/manifests/latest.json",
            "retrieval_build_id": "20260504T164021Z",
            "reference_fields": [
                "referenced_ids",
                "referenced_dois",
                "referenced_arxiv_ids",
                "references_count",
                "cited_by_count",
            ],
            "source_provenance_field": "sources",
        },
        "nodes": {
            "required_types": ["paper", "external_reference", "source_family"],
            "id_policy": {
                "paper": "paper:<canonical_id>",
                "external_reference": "external_reference:<reference_key_hash>",
                "source_family": "source_family:<source_family>",
            },
            "fields": {
                "paper": {"required": ["node_id", "node_type", "canonical_id", "title", "year", "doi", "arxiv_id"]},
                "external_reference": {
                    "required": ["node_id", "node_type", "reference_key", "reference_type", "normalized_value", "resolution_status"],
                    "allowed_reference_types": ["doi", "arxiv_id", "openalex_id", "semantic_scholar_id", "raw_external_id"],
                    "allowed_resolution_statuses": ["resolved_to_canonical", "unresolved_external"],
                },
                "source_family": {
                    "required": ["node_id", "node_type", "source_family"],
                    "value_policy": "derived_from_canonical_provenance_sources_not_source_ids_only",
                },
            },
        },
        "edges": {
            "required_types": ["paper_references_paper", "paper_references_external", "paper_has_reference_source_family"],
            "id_policy": {"default": "typed_source_target_hash"},
            "common_required_fields": ["edge_id", "edge_type", "source_node_id", "target_node_id", "provenance_kind", "source_layer", "confidence"],
            "fields": {
                "paper_references_paper": {
                    "source": "canonical_documents",
                    "match_policy": "resolved_reference_identifier_to_canonical_paper",
                    "target_node_type": "paper",
                },
                "paper_references_external": {
                    "source": "canonical_documents",
                    "match_policy": "unresolved_reference_identifier_preserved_as_external_reference",
                    "target_node_type": "external_reference",
                },
                "paper_has_reference_source_family": {
                    "source": "canonical_documents",
                    "match_policy": "derived_from_reference_bearing_canonical_provenance",
                    "target_node_type": "source_family",
                },
            },
        },
        "provenance": {
            "required_kinds": ["canonical_reference", "external_identifier_reference", "source_family_reference", "derived_summary"],
            "allowed_source_layers": ["canonical_documents", "canonical_reference_fields", "source_provenance"],
            "policies": {
                "graph_not_reconcile_input": True,
                "reference_edges_derived_from_canonical_fields": True,
                "unresolved_references_stay_external": True,
                "citation_count_not_edge_truth": True,
                "source_ids_not_strict_provenance": True,
                "references_count_is_diagnostic_not_edge_count_gate": True,
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
        "outputs": {
            "status": "future_layout_only",
            "generated_in_this_slice": False,
            "expected_future_output_dir": "data/graphs/citation_reference_graph/v0.1",
            "expected_future_output_layout": ["nodes.jsonl", "edges.jsonl", "schema.json", "manifest.json", "README.md", "data_quality_summary.json", "checksums.txt"],
        },
        "validation": {
            "report_dir": "artifacts/reports/validation",
            "require_schema_version": True,
            "require_contract_only_status": True,
            "require_source_checkpoint": True,
            "require_required_node_types": True,
            "require_required_edge_types": True,
            "require_identity_policy": True,
            "require_reference_field_policy": True,
            "require_provenance_policy": True,
            "require_safety_flags": True,
            "require_future_layout_only_outputs": True,
            "require_no_publication": True,
        },
    }


def _write_config(tmp_path: Path, config: dict[str, Any]) -> Path:
    path = tmp_path / "configs" / "citation_reference_graph.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def _validate(tmp_path: Path, config: dict[str, Any], *, check_paths: bool = False) -> dict[str, Any]:
    config_path = _write_config(tmp_path, config)
    return module.validate_contract(
        config_path=config_path,
        check_paths=check_paths,
        write_reports=False,
    )


def test_valid_contract_config_passes(tmp_path: Path) -> None:
    report = _validate(tmp_path, _base_config())
    assert report["summary"]["ok"] is True
    assert report["summary"]["required_failed_count"] == 0
    assert report["verdict"]["contract_only"] is True
    assert report["verdict"]["graph_outputs_generated"] is False


def test_bad_schema_version_fails(tmp_path: Path) -> None:
    config = _base_config()
    config["schema_version"] = "wrong"
    report = _validate(tmp_path, config)
    assert report["summary"]["ok"] is False
    assert "schema_version_ok" in report["verdict"]["required_failed_checks"]


def test_non_contract_status_fails(tmp_path: Path) -> None:
    config = _base_config()
    config["graph"]["status"] = "generated"
    report = _validate(tmp_path, config)
    assert report["summary"]["ok"] is False
    assert "graph_status_contract_only" in report["verdict"]["required_failed_checks"]


def test_missing_external_reference_node_type_fails(tmp_path: Path) -> None:
    config = _base_config()
    config["nodes"]["required_types"].remove("external_reference")
    report = _validate(tmp_path, config)
    assert report["summary"]["ok"] is False
    assert "required_node_types_present" in report["verdict"]["required_failed_checks"]


def test_missing_reference_field_fails(tmp_path: Path) -> None:
    config = _base_config()
    config["source_checkpoint"]["reference_fields"].remove("referenced_dois")
    report = _validate(tmp_path, config)
    assert report["summary"]["ok"] is False
    assert "reference_fields_present" in report["verdict"]["required_failed_checks"]


def test_unsafe_db_schema_change_fails(tmp_path: Path) -> None:
    config = _base_config()
    config["safety"]["may_change_db_schema"] = True
    report = _validate(tmp_path, config)
    assert report["summary"]["ok"] is False
    assert "safety_false_flags_ok" in report["verdict"]["required_failed_checks"]
    assert report["verdict"]["db_schema_change_allowed"] is True


def test_generated_outputs_in_contract_slice_fail(tmp_path: Path) -> None:
    config = _base_config()
    config["outputs"]["generated_in_this_slice"] = True
    report = _validate(tmp_path, config)
    assert report["summary"]["ok"] is False
    assert "outputs_not_generated_in_this_slice" in report["verdict"]["required_failed_checks"]
    assert report["verdict"]["graph_outputs_generated"] is True


def test_check_paths_requires_local_inputs(tmp_path: Path) -> None:
    config = _base_config()
    report = _validate(tmp_path, config, check_paths=True)
    assert report["summary"]["ok"] is False
    assert "canonical_corpus_path_exists" in report["verdict"]["required_failed_checks"]
    assert "retrieval_manifest_path_exists" in report["verdict"]["required_failed_checks"]


def test_check_paths_passes_when_inputs_exist(tmp_path: Path) -> None:
    config = _base_config()
    (tmp_path / "data" / "analytics" / "reconciled").mkdir(parents=True)
    (tmp_path / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "artifacts" / "retrieval" / "manifests").mkdir(parents=True)
    (tmp_path / "artifacts" / "retrieval" / "manifests" / "latest.json").write_text("{}", encoding="utf-8")
    report = _validate(tmp_path, config, check_paths=True)
    assert report["summary"]["ok"] is True
    assert report["summary"]["required_failed_count"] == 0


def test_publication_without_manual_review_fails(tmp_path: Path) -> None:
    config = _base_config()
    config["safety"]["may_publish_without_manual_review"] = True
    report = _validate(tmp_path, config)
    assert report["summary"]["ok"] is False
    assert "safety_false_flags_ok" in report["verdict"]["required_failed_checks"]
    assert report["verdict"]["publication_allowed"] is True
