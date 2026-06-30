from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts.validation.check_paper_artifact_graph_inspection import validate_inspection


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def make_graph_output(tmp_path: Path, *, canonical_truth: bool = False, include_paper_artifact: bool = True) -> tuple[Path, Path]:
    graph_dir = tmp_path / "data" / "graphs" / "paper_artifact_graph" / "v0.1"
    config_path = tmp_path / "configs" / "paper_artifact_graph_builder.yaml"

    config = {
        "schema_version": "paper_artifact_graph_builder_config_v1",
        "outputs": {
            "graph_dir": str(graph_dir),
            "nodes_path": str(graph_dir / "nodes.jsonl"),
            "edges_path": str(graph_dir / "edges.jsonl"),
            "manifest_path": str(graph_dir / "manifest.json"),
            "data_quality_summary_path": str(graph_dir / "data_quality_summary.json"),
        },
    }

    nodes = [
        {
            "node_id": "paper:paper_1",
            "node_type": "paper",
            "label": "Paper 1",
            "properties": {"canonical_id": "paper_1"},
        },
        {
            "node_id": "artifact:artifact_1",
            "node_type": "artifact",
            "label": "example/repo",
            "properties": {
                "artifact_id": "artifact_1",
                "provider": "github",
                "artifact_type": "github_repository",
            },
        },
        {
            "node_id": "provider:github",
            "node_type": "provider",
            "label": "github",
            "properties": {"provider": "github"},
        },
        {
            "node_id": "source_family:arxiv",
            "node_type": "source_family",
            "label": "arxiv",
            "properties": {"source_family": "arxiv"},
        },
        {
            "node_id": "topic_cluster:7",
            "node_type": "topic_cluster",
            "label": "Topic cluster 7",
            "properties": {"topic_cluster_id": "7"},
        },
    ]

    edges = [
        {
            "edge_id": "edge:source",
            "edge_type": "paper_observed_in_source_family",
            "source_node_id": "paper:paper_1",
            "target_node_id": "source_family:arxiv",
            "properties": {"source_family": "arxiv"},
            "provenance": {},
        },
        {
            "edge_id": "edge:provider",
            "edge_type": "artifact_from_provider",
            "source_node_id": "artifact:artifact_1",
            "target_node_id": "provider:github",
            "properties": {"provider": "github"},
            "provenance": {},
        },
        {
            "edge_id": "edge:topic",
            "edge_type": "paper_assigned_to_topic_cluster",
            "source_node_id": "paper:paper_1",
            "target_node_id": "topic_cluster:7",
            "properties": {"topic_cluster_id": "7"},
            "provenance": {},
        },
    ]

    if include_paper_artifact:
        edges.append(
            {
                "edge_id": "edge:artifact",
                "edge_type": "paper_has_artifact",
                "source_node_id": "paper:paper_1",
                "target_node_id": "artifact:artifact_1",
                "properties": {
                    "relation_type": "code",
                    "confidence": 0.9,
                },
                "provenance": {},
            }
        )

    manifest = {
        "schema_version": "paper_artifact_graph_manifest_v1",
        "dry_run": False,
        "canonical_truth": canonical_truth,
        "may_be_used_as_reconcile_input": False,
        "publication_ready": False,
        "builder": {
            "input_mode": "file",
            "live_db_dependency": False,
            "create_latest_pointer": False,
        },
    }

    quality = {
        "schema_version": "paper_artifact_graph_data_quality_summary_v1",
        "ok": True,
        "quality": {
            "nodes_count": len(nodes),
            "edges_count": len(edges),
            "trusted_links_used_count": 1 if include_paper_artifact else 0,
            "topic_edges_count": 1,
        },
    }

    write_yaml(config_path, config)
    write_jsonl(graph_dir / "nodes.jsonl", nodes)
    write_jsonl(graph_dir / "edges.jsonl", edges)
    write_json(graph_dir / "manifest.json", manifest)
    write_json(graph_dir / "data_quality_summary.json", quality)

    return config_path, graph_dir


def assert_failed(report: dict, check_name: str) -> None:
    assert report["ok"] is False
    assert check_name in report["required_failed_checks"]


def test_valid_graph_inspection_passes(tmp_path: Path):
    config_path, _graph_dir = make_graph_output(tmp_path)

    report = validate_inspection(config_path=config_path)

    assert report["ok"] is True
    assert report["required_failed_count"] == 0
    assert report["summary"]["nodes_count"] == 5
    assert report["summary"]["edges_count"] == 4
    assert report["summary"]["papers_with_artifacts_count"] == 1
    assert report["summary"]["topic_clusters_with_artifact_ready_papers_count"] == 1


def test_graph_inspection_fails_if_manifest_claims_canonical_truth(tmp_path: Path):
    config_path, _graph_dir = make_graph_output(tmp_path, canonical_truth=True)

    report = validate_inspection(config_path=config_path)

    assert_failed(report, "manifest_not_canonical_truth")


def test_graph_inspection_fails_without_paper_artifact_edges(tmp_path: Path):
    config_path, _graph_dir = make_graph_output(tmp_path, include_paper_artifact=False)

    report = validate_inspection(config_path=config_path)

    assert_failed(report, "paper_has_artifact_edges_present")
    assert_failed(report, "topic_clusters_with_artifact_ready_papers_present")
    assert_failed(report, "sample_paper_artifact_edges_present")
