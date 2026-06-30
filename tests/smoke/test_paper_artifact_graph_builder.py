from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scripts.export.build_paper_artifact_graph import build_graph


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def make_fixture_config(tmp_path: Path) -> Path:
    canonical_path = tmp_path / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"
    entities_path = tmp_path / "data" / "enriched" / "artifact_links" / "artifact_entities_latest.jsonl"
    links_path = tmp_path / "data" / "enriched" / "artifact_links" / "artifact_links_latest.jsonl"
    topic_latest_path = tmp_path / "artifacts" / "clusters" / "topic" / "latest.json"
    topic_assignments_path = tmp_path / "artifacts" / "clusters" / "topic" / "runs" / "run1" / "assignments.jsonl"
    output_dir = tmp_path / "data" / "graphs" / "paper_artifact_graph" / "v0.1"

    write_jsonl(
        canonical_path,
        [
            {
                "canonical_id": "paper_1",
                "title": "First Paper",
                "year": 2024,
                "sources": [
                    {"source": "arxiv", "source_doc_id": "1234.5678"},
                    {"source_family": "openalex", "source_doc_id": "W123"},
                ],
            },
            {
                "canonical_id": "paper_2",
                "title": "Second Paper",
                "year": 2025,
                "sources": [
                    {"source": "semantic_scholar", "source_doc_id": "S123"},
                ],
            },
        ],
    )

    write_jsonl(
        entities_path,
        [
            {
                "artifact_id": "artifact_1",
                "artifact_type": "github_repository",
                "provider": "github",
                "normalized_url": "https://github.com/example/repo",
                "canonical_url": "https://github.com/example/repo",
                "name": "example/repo",
            },
            {
                "artifact_id": "artifact_2",
                "artifact_type": "generic_code_url",
                "provider": "generic",
                "normalized_url": "https://example.org/project",
                "canonical_url": "https://example.org/project",
            },
        ],
    )

    write_jsonl(
        links_path,
        [
            {
                "observation_id": "obs_1",
                "artifact_id": "artifact_1",
                "artifact_type": "github_repository",
                "provider": "github",
                "raw_url": "https://github.com/example/repo",
                "normalized_url": "https://github.com/example/repo",
                "canonical_id": "paper_1",
                "source_layer": "canonical",
                "source_name": "arxiv",
                "source_doc_id": "1234.5678",
                "source_field": "code_links",
                "relation_type": "code",
                "confidence": 0.8,
            },
            {
                "observation_id": "obs_2",
                "artifact_id": "artifact_1",
                "artifact_type": "github_repository",
                "provider": "github",
                "raw_url": "https://github.com/example/repo",
                "normalized_url": "https://github.com/example/repo",
                "canonical_id": "paper_1",
                "source_layer": "canonical",
                "source_name": "openalex",
                "source_doc_id": "W123",
                "source_field": "repo_url",
                "relation_type": "code",
                "confidence": 0.95,
            },
            {
                "observation_id": "obs_untrusted",
                "artifact_id": "artifact_2",
                "artifact_type": "generic_code_url",
                "provider": "generic",
                "raw_url": "https://example.org/project",
                "normalized_url": "https://example.org/project",
                "canonical_id": "paper_2",
                "source_layer": "canonical",
                "source_name": "semantic_scholar",
                "source_doc_id": "S123",
                "source_field": "abstract",
                "relation_type": "code",
                "confidence": 0.99,
            },
        ],
    )

    write_json(
        topic_latest_path,
        {
            "schema_version": "topic_clusters_latest_v1",
            "cluster_build_id": "topic_build_1",
            "retrieval_build_id": "retrieval_1",
            "assignments_path": str(topic_assignments_path),
        },
    )

    write_jsonl(
        topic_assignments_path,
        [
            {"canonical_id": "paper_1", "cluster_id": 7, "score": 0.9},
            {"canonical_id": "paper_2", "cluster_id": 8, "score": 0.8},
        ],
    )

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
            "config_path": str(tmp_path / "configs" / "paper_artifact_graph.yaml"),
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
            "graph_dir": str(output_dir),
            "nodes_path": str(output_dir / "nodes.jsonl"),
            "edges_path": str(output_dir / "edges.jsonl"),
            "schema_path": str(output_dir / "schema.json"),
            "manifest_path": str(output_dir / "manifest.json"),
            "data_quality_summary_path": str(output_dir / "data_quality_summary.json"),
            "readme_path": str(output_dir / "README.md"),
            "checksums_path": str(output_dir / "checksums.txt"),
        },
        "expected_counts": {},
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
    write_yaml(config_path, config)
    return config_path


def test_build_paper_artifact_graph_from_tiny_fixtures(tmp_path: Path):
    config_path = make_fixture_config(tmp_path)

    result = build_graph(config_path=config_path)

    graph_dir = Path(result["graph_dir"])
    assert graph_dir.exists()

    nodes = read_jsonl(graph_dir / "nodes.jsonl")
    edges = read_jsonl(graph_dir / "edges.jsonl")
    manifest = json.loads((graph_dir / "manifest.json").read_text(encoding="utf-8"))
    quality = json.loads((graph_dir / "data_quality_summary.json").read_text(encoding="utf-8"))

    node_types = {row["node_type"] for row in nodes}
    edge_types = {row["edge_type"] for row in edges}

    assert {"paper", "artifact", "provider", "source_family", "topic_cluster"}.issubset(node_types)
    assert {
        "paper_has_artifact",
        "artifact_from_provider",
        "paper_observed_in_source_family",
        "paper_assigned_to_topic_cluster",
    }.issubset(edge_types)

    paper_artifact_edges = [
        row for row in edges if row["edge_type"] == "paper_has_artifact"
    ]
    assert len(paper_artifact_edges) == 1
    assert paper_artifact_edges[0]["source_node_id"] == "paper:paper_1"
    assert paper_artifact_edges[0]["target_node_id"] == "artifact:artifact_1"
    assert paper_artifact_edges[0]["properties"]["confidence"] == 0.95
    assert paper_artifact_edges[0]["provenance"]["trusted_link_policy_version"] == "artifact_trusted_links_policy_v1"

    assert manifest["canonical_truth"] is False
    assert manifest["may_be_used_as_reconcile_input"] is False
    assert manifest["dry_run"] is False

    assert quality["ok"] is True
    assert quality["quality"]["trusted_links_raw_count"] == 1
    assert quality["quality"]["trusted_links_used_count"] == 1
    assert quality["quality"]["topic_edges_count"] == 2


def test_dry_run_does_not_write_outputs(tmp_path: Path):
    config_path = make_fixture_config(tmp_path)

    result = build_graph(config_path=config_path, dry_run=True)

    assert result["dry_run"] is True
    assert result["quality_summary"]["trusted_links_used_count"] == 1

    graph_dir = tmp_path / "data" / "graphs" / "paper_artifact_graph" / "v0.1"
    assert not graph_dir.exists()

def test_existing_output_dir_requires_force(tmp_path: Path):
    config_path = make_fixture_config(tmp_path)

    first_result = build_graph(config_path=config_path)
    graph_dir = Path(first_result["graph_dir"])
    assert graph_dir.exists()

    with pytest.raises(FileExistsError, match="Use --force"):
        build_graph(config_path=config_path)

    second_result = build_graph(config_path=config_path, force=True)

    assert Path(second_result["graph_dir"]).exists()
    assert (graph_dir / "nodes.jsonl").exists()
    assert (graph_dir / "edges.jsonl").exists()


def test_missing_topic_assignments_path_fails_when_topic_clusters_enabled(tmp_path: Path):
    config_path = make_fixture_config(tmp_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    topic_latest_path = Path(config["inputs"]["topic_clusters_latest_path"])
    write_json(
        topic_latest_path,
        {
            "schema_version": "topic_clusters_latest_v1",
            "cluster_build_id": "topic_build_1",
            "retrieval_build_id": "retrieval_1",
        },
    )

    with pytest.raises(ValueError, match="assignments_path"):
        build_graph(config_path=config_path)
