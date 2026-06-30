from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

from scripts.graph.query_paper_artifact_graph import (
    attach_meta,
    load_graph_index,
    query_graph,
    render_markdown,
)


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


def make_graph_output(tmp_path: Path) -> tuple[Path, Path]:
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
            "node_id": "paper:paper_2",
            "node_type": "paper",
            "label": "Paper 2",
            "properties": {"canonical_id": "paper_2"},
        },
        {
            "node_id": "artifact:artifact_1",
            "node_type": "artifact",
            "label": "example/repo",
            "properties": {
                "artifact_id": "artifact_1",
                "provider": "github",
                "artifact_type": "github_repository",
                "url": "https://github.com/example/repo",
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
            "edge_id": "edge:paper1-artifact1",
            "edge_type": "paper_has_artifact",
            "source_node_id": "paper:paper_1",
            "target_node_id": "artifact:artifact_1",
            "properties": {
                "relation_type": "code",
                "confidence": 0.9,
            },
            "provenance": {},
        },
        {
            "edge_id": "edge:paper2-artifact1",
            "edge_type": "paper_has_artifact",
            "source_node_id": "paper:paper_2",
            "target_node_id": "artifact:artifact_1",
            "properties": {
                "relation_type": "code",
                "confidence": 0.8,
            },
            "provenance": {},
        },
        {
            "edge_id": "edge:artifact-provider",
            "edge_type": "artifact_from_provider",
            "source_node_id": "artifact:artifact_1",
            "target_node_id": "provider:github",
            "properties": {"provider": "github"},
            "provenance": {},
        },
        {
            "edge_id": "edge:paper1-source",
            "edge_type": "paper_observed_in_source_family",
            "source_node_id": "paper:paper_1",
            "target_node_id": "source_family:arxiv",
            "properties": {"source_family": "arxiv"},
            "provenance": {},
        },
        {
            "edge_id": "edge:paper1-topic",
            "edge_type": "paper_assigned_to_topic_cluster",
            "source_node_id": "paper:paper_1",
            "target_node_id": "topic_cluster:7",
            "properties": {"topic_cluster_id": "7"},
            "provenance": {},
        },
    ]

    manifest = {
        "schema_version": "paper_artifact_graph_manifest_v1",
        "dry_run": False,
        "canonical_truth": False,
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
            "trusted_links_used_count": 2,
            "topic_edges_count": 1,
        },
    }

    write_yaml(config_path, config)
    write_jsonl(graph_dir / "nodes.jsonl", nodes)
    write_jsonl(graph_dir / "edges.jsonl", edges)
    write_json(graph_dir / "manifest.json", manifest)
    write_json(graph_dir / "data_quality_summary.json", quality)

    return config_path, graph_dir


def test_query_by_paper_returns_artifacts(tmp_path: Path):
    config_path, _graph_dir = make_graph_output(tmp_path)
    index = load_graph_index(config_path=config_path)

    result = query_graph(index, paper_id="paper_1", top_k=10)

    assert result["query_type"] == "paper"
    assert result["found"] is True
    assert result["counts"]["artifacts"] == 1
    assert result["artifacts"][0]["artifact_id"] == "artifact_1"
    assert result["artifacts"][0]["provider"] == "github"


def test_query_by_artifact_returns_linked_papers(tmp_path: Path):
    config_path, _graph_dir = make_graph_output(tmp_path)
    index = load_graph_index(config_path=config_path)

    result = query_graph(index, artifact_id="artifact_1", top_k=10)

    assert result["query_type"] == "artifact"
    assert result["found"] is True
    assert result["counts"]["linked_papers"] == 2
    assert {row["canonical_id"] for row in result["papers"]} == {"paper_1", "paper_2"}


def test_query_by_provider_ranks_artifacts_by_linked_papers(tmp_path: Path):
    config_path, _graph_dir = make_graph_output(tmp_path)
    index = load_graph_index(config_path=config_path)

    result = query_graph(index, provider="github", top_k=10)

    assert result["query_type"] == "provider"
    assert result["found"] is True
    assert result["counts"]["artifacts"] == 1
    assert result["counts"]["paper_artifact_links"] == 2
    assert result["artifacts"][0]["artifact_id"] == "artifact_1"
    assert result["artifacts"][0]["linked_papers_count"] == 2


def test_query_by_topic_cluster_returns_artifact_ready_papers(tmp_path: Path):
    config_path, _graph_dir = make_graph_output(tmp_path)
    index = load_graph_index(config_path=config_path)

    result = query_graph(index, topic_cluster="7", top_k=10)

    assert result["query_type"] == "topic_cluster"
    assert result["found"] is True
    assert result["counts"]["papers"] == 1
    assert result["counts"]["artifact_ready_papers"] == 1
    assert result["artifact_ready_papers"][0]["canonical_id"] == "paper_1"
    assert result["artifact_ready_papers"][0]["artifacts"][0]["artifact_id"] == "artifact_1"


def test_markdown_render_contains_counts(tmp_path: Path):
    config_path, _graph_dir = make_graph_output(tmp_path)
    index = load_graph_index(config_path=config_path)
    result = query_graph(index, provider="github", top_k=10)
    payload = attach_meta(result, index)

    rendered = render_markdown(payload)

    assert "# Paper-Artifact Graph Query" in rendered
    assert "paper_artifact_links" in rendered
    assert "example/repo" in rendered


def test_cli_json_output(tmp_path: Path):
    config_path, _graph_dir = make_graph_output(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.graph.query_paper_artifact_graph",
            "--config",
            str(config_path),
            "--paper-id",
            "paper_1",
            "--top-k",
            "5",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)

    assert payload["schema_version"] == "paper_artifact_graph_query_cli_result_v1"
    assert payload["result"]["query_type"] == "paper"
    assert payload["result"]["counts"]["artifacts"] == 1


def test_cli_requires_exactly_one_selector(tmp_path: Path):
    config_path, _graph_dir = make_graph_output(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.graph.query_paper_artifact_graph",
            "--config",
            str(config_path),
            "--paper-id",
            "paper_1",
            "--provider",
            "github",
        ],
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "Exactly one query selector is required" in completed.stderr