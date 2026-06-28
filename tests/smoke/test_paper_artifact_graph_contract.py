from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from scripts.validation.check_paper_artifact_graph_contract import validate_config


def build_valid_config() -> dict[str, Any]:
    return {
        "schema_version": "paper_artifact_graph_config_v1",
        "graph": {
            "name": "ml_research_radar_paper_artifact_graph",
            "version": "v0.1",
            "status": "contract_only",
            "graph_family": "paper_artifact_evidence_graph",
            "description": (
                "Contract-only definition for a future derived "
                "paper-artifact evidence graph."
            ),
        },
        "source_checkpoint": {
            "canonical_corpus_path": "data/analytics/reconciled/canonical_documents.jsonl",
            "expected_canonical_doc_count": 60954,
            "retrieval_manifest_path": "artifacts/retrieval/manifests/latest.json",
            "retrieval_build_id": "20260504T164021Z",
            "artifact_entities_db_count": 7333,
            "artifact_observations_db_count": 38246,
            "paper_artifact_links_db_count": 7430,
            "paper_features_path": "data/features/paper_features_latest.jsonl",
            "topic_clusters_latest_path": "artifacts/clusters/topic/latest.json",
            "topic_clusters_count": 80,
            "topic_assignments_count": 60954,
        },
        "nodes": {
            "required_types": [
                "paper",
                "artifact",
                "provider",
                "source_family",
                "topic_cluster",
            ],
            "id_policy": {
                "paper": "paper:<canonical_id>",
                "artifact": "artifact:<artifact_id>",
                "provider": "provider:<provider>",
                "source_family": "source_family:<source_family>",
                "topic_cluster": "topic_cluster:<cluster_id>",
            },
            "fields": {
                "paper": {
                    "required": [
                        "node_id",
                        "node_type",
                        "canonical_id",
                        "title",
                        "year",
                        "source_count",
                        "unique_source_count",
                    ],
                    "optional": [
                        "doi",
                        "arxiv_id",
                        "primary_category",
                        "publication_type",
                        "metadata_completeness_score",
                        "has_trusted_artifact",
                        "topic_cluster_id",
                    ],
                },
                "artifact": {
                    "required": [
                        "node_id",
                        "node_type",
                        "artifact_id",
                        "provider",
                        "artifact_type",
                        "normalized_url",
                    ],
                    "optional": [
                        "owner",
                        "name",
                        "title",
                        "description",
                        "license",
                        "stars",
                        "forks",
                        "downloads",
                        "likes",
                        "topics",
                        "tags",
                        "archived",
                        "github_status",
                        "huggingface_status",
                        "last_seen_at",
                        "fetched_at",
                        "created_at",
                        "updated_at",
                        "pushed_at",
                    ],
                },
                "provider": {
                    "required": ["node_id", "node_type", "provider"],
                    "value_policy": "derived_from_artifact_entities_provider",
                },
                "source_family": {
                    "required": ["node_id", "node_type", "source_family"],
                    "value_policy": (
                        "derived_from_canonical_provenance_sources_not_source_ids_only"
                    ),
                },
                "topic_cluster": {
                    "required": ["node_id", "node_type", "cluster_id"],
                    "optional": [
                        "label",
                        "label_candidates",
                        "size",
                        "cluster_build_id",
                        "retrieval_build_id",
                        "mean_radar_score",
                        "artifact_ready_count",
                    ],
                },
            },
        },
        "edges": {
            "required_types": [
                "paper_has_artifact",
                "artifact_from_provider",
                "paper_observed_in_source_family",
                "paper_assigned_to_topic_cluster",
            ],
            "id_policy": {
                "default": "typed_source_target_hash",
            },
            "common_required_fields": [
                "edge_id",
                "edge_type",
                "source_node_id",
                "target_node_id",
                "provenance_kind",
                "source_layer",
                "confidence",
            ],
            "fields": {
                "paper_has_artifact": {
                    "source": "paper_artifact_links",
                    "required": [
                        "canonical_id",
                        "artifact_id",
                        "provider",
                        "artifact_type",
                        "relation_type",
                        "confidence",
                        "evidence_source",
                    ],
                    "notes": [
                        (
                            "Trusted graph edges must be derived from "
                            "paper_artifact_links, not directly from broad "
                            "artifact_observations."
                        ),
                    ],
                },
                "artifact_from_provider": {
                    "source": "artifact_entities",
                    "required": ["artifact_id", "provider"],
                },
                "paper_observed_in_source_family": {
                    "source": "canonical_documents",
                    "required": ["canonical_id", "source_family"],
                    "notes": [
                        (
                            "sources are row-level provenance; source_ids is a "
                            "merged identifier map and must not be treated as "
                            "strict provenance by itself."
                        ),
                    ],
                },
                "paper_assigned_to_topic_cluster": {
                    "source": "topic_clusters",
                    "required": [
                        "canonical_id",
                        "cluster_id",
                        "cluster_build_id",
                        "retrieval_build_id",
                    ],
                },
            },
        },
        "provenance": {
            "required_kinds": [
                "canonical_provenance",
                "artifact_evidence",
                "provider_metadata",
                "topic_assignment",
                "derived_summary",
            ],
            "allowed_source_layers": [
                "canonical_documents",
                "artifact_db",
                "artifact_extraction",
                "provider_enrichment",
                "paper_features",
                "topic_clusters",
                "topic_projection",
            ],
            "policies": {
                "artifact_metadata_not_paper_truth": True,
                "graph_not_reconcile_input": True,
                "source_ids_not_strict_provenance": True,
                "trusted_artifact_edges_from_paper_artifact_links": True,
            },
        },
        "safety": {
            "canonical_truth_impact": "none",
            "may_overwrite_operational_latest": False,
            "may_be_used_as_reconcile_input": False,
            "may_change_api_behavior": False,
            "may_change_retrieval_behavior": False,
            "may_change_qdrant_behavior": False,
            "may_change_ranking_behavior": False,
            "may_publish_without_manual_review": False,
        },
        "outputs": {
            "status": "future_layout_only",
            "generated_in_this_slice": False,
            "expected_future_layout": [
                "nodes.parquet",
                "edges.parquet",
                "schema.json",
                "manifest.json",
                "README.md",
                "data_quality_summary.json",
                "checksums.txt",
            ],
        },
        "validation": {
            "require_schema_version": True,
            "require_contract_only_status": True,
            "require_source_checkpoint": True,
            "require_required_node_types": True,
            "require_required_edge_types": True,
            "require_identity_policy": True,
            "require_provenance_kinds": True,
            "require_safety_flags": True,
            "require_future_layout_only_outputs": True,
            "require_no_publication": True,
        },
    }


def write_config(tmp_path: Path, config: dict[str, Any]) -> Path:
    config_path = tmp_path / "paper_artifact_graph.yaml"
    config_path.write_text(
        yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return config_path


def run_validation(
    tmp_path: Path,
    config: dict[str, Any],
    *,
    check_paths: bool = False,
) -> dict[str, Any]:
    config_path = write_config(tmp_path, config)
    return validate_config(
        config,
        config_path=config_path,
        check_paths=check_paths,
    )


def assert_required_check_failed(
    report: dict[str, Any],
    check_name: str,
) -> None:
    assert report["verdict"]["ok"] is False
    assert report["verdict"]["required_failed_count"] > 0
    assert check_name in report["verdict"]["required_failed_checks"]


def test_valid_graph_contract_config_passes(tmp_path: Path) -> None:
    report = run_validation(tmp_path, build_valid_config())

    assert report["verdict"]["ok"] is True
    assert report["verdict"]["required_failed_count"] == 0
    assert report["verdict"]["required_failed_checks"] == []


def test_missing_required_node_type_fails(tmp_path: Path) -> None:
    config = build_valid_config()
    config["nodes"]["required_types"].remove("topic_cluster")

    report = run_validation(tmp_path, config)

    assert_required_check_failed(report, "required_node_types_present")


def test_missing_required_edge_type_fails(tmp_path: Path) -> None:
    config = build_valid_config()
    config["edges"]["required_types"].remove("paper_assigned_to_topic_cluster")

    report = run_validation(tmp_path, config)

    assert_required_check_failed(report, "required_edge_types_present")


def test_bad_graph_status_fails(tmp_path: Path) -> None:
    config = build_valid_config()
    config["graph"]["status"] = "builder_enabled"

    report = run_validation(tmp_path, config)

    assert_required_check_failed(report, "graph_status_contract_only")


def test_bad_identity_policy_fails(tmp_path: Path) -> None:
    config = build_valid_config()
    config["nodes"]["id_policy"]["paper"] = "canonical:<canonical_id>"

    report = run_validation(tmp_path, config)

    assert_required_check_failed(report, "node_id_policy_present")


def test_bad_safety_flag_fails(tmp_path: Path) -> None:
    config = build_valid_config()
    config["safety"]["may_change_api_behavior"] = True

    report = run_validation(tmp_path, config)

    assert_required_check_failed(report, "safety_flags_ok")
    assert_required_check_failed(report, "no_api_behavior_change")


def test_hardcoded_provider_enum_fails(tmp_path: Path) -> None:
    config = build_valid_config()
    config["provider_enum"] = ["github", "huggingface_hub"]

    report = run_validation(tmp_path, config)

    assert_required_check_failed(report, "no_hardcoded_provider_enum")


def test_paper_has_artifact_must_use_trusted_links(tmp_path: Path) -> None:
    config = build_valid_config()
    config["edges"]["fields"]["paper_has_artifact"]["source"] = (
        "artifact_observations"
    )

    report = run_validation(tmp_path, config)

    assert_required_check_failed(report, "paper_has_artifact_source_is_trusted_links")


def test_outputs_must_be_future_layout_only(tmp_path: Path) -> None:
    config = build_valid_config()
    config["outputs"]["status"] = "generated"
    config["outputs"]["generated_in_this_slice"] = True

    report = run_validation(tmp_path, config)

    assert_required_check_failed(report, "outputs_future_layout_only")
    assert_required_check_failed(report, "outputs_not_generated_in_this_slice")


def test_missing_future_layout_file_fails(tmp_path: Path) -> None:
    config = build_valid_config()
    config["outputs"]["expected_future_layout"].remove("checksums.txt")

    report = run_validation(tmp_path, config)

    assert_required_check_failed(report, "expected_future_output_layout_present")


def test_check_paths_passes_for_existing_configured_files(tmp_path: Path) -> None:
    config = copy.deepcopy(build_valid_config())

    canonical_path = tmp_path / "canonical_documents.jsonl"
    manifest_path = tmp_path / "latest.json"
    features_path = tmp_path / "paper_features_latest.jsonl"
    topic_latest_path = tmp_path / "topic_latest.json"

    for path in [canonical_path, manifest_path, features_path, topic_latest_path]:
        path.write_text("{}", encoding="utf-8")

    config["source_checkpoint"]["canonical_corpus_path"] = str(canonical_path)
    config["source_checkpoint"]["retrieval_manifest_path"] = str(manifest_path)
    config["source_checkpoint"]["paper_features_path"] = str(features_path)
    config["source_checkpoint"]["topic_clusters_latest_path"] = str(topic_latest_path)

    report = run_validation(tmp_path, config, check_paths=True)

    assert report["verdict"]["ok"] is True
    assert report["verdict"]["required_failed_count"] == 0


def test_check_paths_fails_for_missing_configured_file(tmp_path: Path) -> None:
    config = copy.deepcopy(build_valid_config())

    missing_path = tmp_path / "missing_canonical_documents.jsonl"
    config["source_checkpoint"]["canonical_corpus_path"] = str(missing_path)

    report = run_validation(tmp_path, config, check_paths=True)

    assert_required_check_failed(report, "canonical_corpus_path_exists")