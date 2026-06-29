from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml

from scripts.validation.check_paper_artifact_graph_builder_config import validate_config


def write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}\n", encoding="utf-8")
    return path


def valid_contract_config() -> dict:
    return {
        "schema_version": "paper_artifact_graph_config_v1",
        "graph": {
            "name": "ml_research_radar_paper_artifact_graph",
            "version": "v0.1",
            "status": "contract_only",
            "graph_family": "paper_artifact_evidence_graph",
        },
        "source_checkpoint": {
            "expected_canonical_doc_count": 60954,
            "artifact_entities_db_count": 7333,
            "artifact_observations_db_count": 38246,
            "paper_artifact_links_db_count": 7430,
            "topic_clusters_count": 80,
            "topic_assignments_count": 60954,
        },
        "outputs": {
            "status": "future_layout_only",
            "generated_in_this_slice": False,
        },
    }


def valid_builder_config(tmp_path: Path, *, with_existing_inputs: bool = False) -> tuple[dict, Path]:
    contract_path = tmp_path / "configs" / "paper_artifact_graph.yaml"
    write_yaml(contract_path, valid_contract_config())

    if with_existing_inputs:
        canonical_path = touch(tmp_path / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl")
        entities_path = touch(tmp_path / "data" / "enriched" / "artifact_links" / "artifact_entities_latest.jsonl")
        links_path = touch(tmp_path / "data" / "enriched" / "artifact_links" / "artifact_links_latest.jsonl")
        topic_latest_path = touch(tmp_path / "artifacts" / "clusters" / "topic" / "latest.json")
    else:
        canonical_path = tmp_path / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"
        entities_path = tmp_path / "data" / "enriched" / "artifact_links" / "artifact_entities_latest.jsonl"
        links_path = tmp_path / "data" / "enriched" / "artifact_links" / "artifact_links_latest.jsonl"
        topic_latest_path = tmp_path / "artifacts" / "clusters" / "topic" / "latest.json"

    config = {
        "schema_version": "paper_artifact_graph_builder_config_v1",
        "builder": {
            "name": "paper_artifact_graph_builder",
            "version": "v0.1",
            "status": "local_derived_builder",
            "input_mode": "file",
            "live_db_dependency": False,
            "output_format": "jsonl",
            "create_latest_pointer": False,
        },
        "contract": {
            "config_path": str(contract_path),
            "required_schema_version": "paper_artifact_graph_config_v1",
            "required_graph_status": "contract_only",
            "required_outputs_status": "future_layout_only",
        },
        "graph": {
            "name": "ml_research_radar_paper_artifact_graph",
            "version": "v0.1",
            "graph_family": "paper_artifact_evidence_graph",
            "canonical_truth": False,
            "may_be_used_as_reconcile_input": False,
            "publication_ready": False,
        },
        "inputs": {
            "canonical_documents_path": str(canonical_path),
            "artifact_entities_path": str(entities_path),
            "artifact_links_path": str(links_path),
            "topic_clusters_latest_path": str(topic_latest_path),
        },
        "optional_inputs": {
            "github_metadata_path": str(tmp_path / "missing" / "github.jsonl"),
            "huggingface_metadata_path": str(tmp_path / "missing" / "hf.jsonl"),
            "paper_features_path": str(tmp_path / "missing" / "paper_features.jsonl"),
        },
        "features": {
            "include_topic_clusters": True,
            "include_paper_features": False,
            "include_provider_metadata": False,
        },
        "trusted_links": {
            "source": "artifact_links_latest",
            "policy_source": "radar_core.artifacts.trusted_links",
            "policy_version": "artifact_trusted_links_policy_v1",
            "create_global_trusted_links_file": False,
            "dedupe_key": ["canonical_id", "artifact_id", "relation_type"],
        },
        "outputs": {
            "graph_dir": "data/graphs/paper_artifact_graph/v0.1",
            "nodes_path": "data/graphs/paper_artifact_graph/v0.1/nodes.jsonl",
            "edges_path": "data/graphs/paper_artifact_graph/v0.1/edges.jsonl",
            "schema_path": "data/graphs/paper_artifact_graph/v0.1/schema.json",
            "manifest_path": "data/graphs/paper_artifact_graph/v0.1/manifest.json",
            "data_quality_summary_path": "data/graphs/paper_artifact_graph/v0.1/data_quality_summary.json",
            "readme_path": "data/graphs/paper_artifact_graph/v0.1/README.md",
            "checksums_path": "data/graphs/paper_artifact_graph/v0.1/checksums.txt",
        },
        "expected_counts": {
            "canonical_papers": 60954,
            "artifact_entities_file": 7336,
            "artifact_entities_db_reference": 7333,
            "artifact_observations_file": 38246,
            "trusted_unique_paper_artifact_links": 7430,
            "topic_assignments": 60954,
            "topic_clusters": 80,
        },
        "safety": {
            "mutate_canonical_documents": False,
            "mutate_artifact_inputs": False,
            "mutate_topic_inputs": False,
            "mutate_retrieval_artifacts": False,
            "mutate_qdrant": False,
            "mutate_postgres": False,
            "mutate_api": False,
            "mutate_ranking": False,
            "write_latest_pointer": False,
            "create_global_trusted_links_file": False,
        },
    }

    config_path = tmp_path / "configs" / "paper_artifact_graph_builder.yaml"
    return config, config_path


def validate_payload(tmp_path: Path, payload: dict, *, check_paths: bool = False) -> dict:
    config_path = tmp_path / "configs" / "paper_artifact_graph_builder.yaml"
    write_yaml(config_path, payload)
    return validate_config(config_path, check_paths=check_paths)


def assert_required_check_failed(report: dict, check_name: str) -> None:
    assert report["ok"] is False
    assert check_name in report["required_failed_checks"]


def test_valid_builder_config_passes_without_path_checks(tmp_path: Path):
    payload, config_path = valid_builder_config(tmp_path)
    write_yaml(config_path, payload)

    report = validate_config(config_path)

    assert report["ok"] is True
    assert report["required_failed_count"] == 0


def test_valid_builder_config_passes_with_path_checks(tmp_path: Path):
    payload, config_path = valid_builder_config(tmp_path, with_existing_inputs=True)
    write_yaml(config_path, payload)

    report = validate_config(config_path, check_paths=True)

    assert report["ok"] is True
    assert report["required_failed_count"] == 0


def test_live_db_dependency_fails(tmp_path: Path):
    payload, _ = valid_builder_config(tmp_path)
    payload["builder"]["live_db_dependency"] = True

    report = validate_payload(tmp_path, payload)

    assert_required_check_failed(report, "builder_live_db_dependency_false")


def test_input_mode_must_be_file(tmp_path: Path):
    payload, _ = valid_builder_config(tmp_path)
    payload["builder"]["input_mode"] = "db"

    report = validate_payload(tmp_path, payload)

    assert_required_check_failed(report, "builder_input_mode_file")


def test_latest_pointer_is_forbidden(tmp_path: Path):
    payload, _ = valid_builder_config(tmp_path)
    payload["builder"]["create_latest_pointer"] = True
    payload["safety"]["write_latest_pointer"] = True

    report = validate_payload(tmp_path, payload)

    assert_required_check_failed(report, "builder_create_latest_pointer_false")
    assert_required_check_failed(report, "safety_flags_all_false")


def test_global_trusted_links_file_is_forbidden(tmp_path: Path):
    payload, _ = valid_builder_config(tmp_path)
    payload["trusted_links"]["create_global_trusted_links_file"] = True
    payload["safety"]["create_global_trusted_links_file"] = True

    report = validate_payload(tmp_path, payload)

    assert_required_check_failed(report, "trusted_links_no_global_file")
    assert_required_check_failed(report, "safety_flags_all_false")


def test_paper_features_are_disabled_for_v01(tmp_path: Path):
    payload, _ = valid_builder_config(tmp_path)
    payload["features"]["include_paper_features"] = True

    report = validate_payload(tmp_path, payload)

    assert_required_check_failed(report, "include_paper_features_false")


def test_provider_metadata_is_disabled_for_v01(tmp_path: Path):
    payload, _ = valid_builder_config(tmp_path)
    payload["features"]["include_provider_metadata"] = True

    report = validate_payload(tmp_path, payload)

    assert_required_check_failed(report, "include_provider_metadata_false")


def test_trusted_link_policy_source_must_use_shared_helper(tmp_path: Path):
    payload, _ = valid_builder_config(tmp_path)
    payload["trusted_links"]["policy_source"] = "scripts.export.export_artifacts_postgres_v1"

    report = validate_payload(tmp_path, payload)

    assert_required_check_failed(report, "trusted_links_policy_source_ok")


def test_outputs_must_stay_under_data_graphs(tmp_path: Path):
    payload, _ = valid_builder_config(tmp_path)
    payload["outputs"]["graph_dir"] = "artifacts/graphs/paper_artifact_graph/v0.1"

    report = validate_payload(tmp_path, payload)

    assert_required_check_failed(report, "outputs_under_expected_graph_dir")


def test_raw_primary_input_is_forbidden(tmp_path: Path):
    payload, _ = valid_builder_config(tmp_path)
    payload["inputs"]["canonical_documents_path"] = "data/raw/arxiv/example.jsonl"

    report = validate_payload(tmp_path, payload)

    assert_required_check_failed(report, "primary_inputs_avoid_forbidden_prefixes")


def test_contract_must_remain_contract_only(tmp_path: Path):
    payload, _ = valid_builder_config(tmp_path)
    contract_path = Path(payload["contract"]["config_path"])
    contract = deepcopy(valid_contract_config())
    contract["graph"]["status"] = "generated"
    write_yaml(contract_path, contract)

    report = validate_payload(tmp_path, payload)

    assert_required_check_failed(report, "contract_graph_status_contract_only")


def test_required_input_paths_are_checked_when_enabled(tmp_path: Path):
    payload, _ = valid_builder_config(tmp_path, with_existing_inputs=False)

    report = validate_payload(tmp_path, payload, check_paths=True)

    assert_required_check_failed(report, "canonical_documents_path_exists")
    assert_required_check_failed(report, "artifact_entities_path_exists")
    assert_required_check_failed(report, "artifact_links_path_exists")
    assert_required_check_failed(report, "topic_clusters_latest_path_exists")


def test_expected_counts_must_match_contract(tmp_path: Path):
    payload, _ = valid_builder_config(tmp_path)
    payload["expected_counts"]["trusted_unique_paper_artifact_links"] = 999

    report = validate_payload(tmp_path, payload)

    assert_required_check_failed(report, "expected_trusted_links_matches_contract")
