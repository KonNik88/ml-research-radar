from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from scripts.validation.check_paper_artifact_graph_output import validate_output


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


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def write_checksums(graph_dir: Path) -> None:
    files = [
        "nodes.jsonl",
        "edges.jsonl",
        "schema.json",
        "manifest.json",
        "data_quality_summary.json",
        "README.md",
    ]
    rows = [f"{sha256_file(graph_dir / filename)}  {filename}" for filename in files]
    (graph_dir / "checksums.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")


def make_valid_output(tmp_path: Path) -> tuple[Path, Path]:
    graph_dir = tmp_path / "data" / "graphs" / "paper_artifact_graph" / "v0.1"
    config_path = tmp_path / "configs" / "paper_artifact_graph_builder.yaml"

    config = {
        "schema_version": "paper_artifact_graph_builder_config_v1",
        "trusted_links": {
            "policy_version": "artifact_trusted_links_policy_v1",
        },
        "outputs": {
            "graph_dir": str(graph_dir),
            "nodes_path": str(graph_dir / "nodes.jsonl"),
            "edges_path": str(graph_dir / "edges.jsonl"),
            "schema_path": str(graph_dir / "schema.json"),
            "manifest_path": str(graph_dir / "manifest.json"),
            "data_quality_summary_path": str(graph_dir / "data_quality_summary.json"),
            "readme_path": str(graph_dir / "README.md"),
            "checksums_path": str(graph_dir / "checksums.txt"),
        },
        "expected_counts": {
            "canonical_papers": 1,
            "artifact_entities_file": 1,
            "artifact_observations_file": 1,
            "trusted_unique_paper_artifact_links": 1,
            "topic_assignments": 1,
            "topic_clusters": 1,
        },
    }

    nodes = [
        {"node_id": "paper:paper_1", "node_type": "paper", "label": "Paper", "properties": {}},
        {"node_id": "artifact:artifact_1", "node_type": "artifact", "label": "Artifact", "properties": {}},
        {"node_id": "provider:github", "node_type": "provider", "label": "github", "properties": {}},
        {"node_id": "source_family:arxiv", "node_type": "source_family", "label": "arxiv", "properties": {}},
        {"node_id": "topic_cluster:7", "node_type": "topic_cluster", "label": "Topic cluster 7", "properties": {}},
    ]

    edges = [
        {
            "edge_id": "edge:1",
            "edge_type": "paper_has_artifact",
            "source_node_id": "paper:paper_1",
            "target_node_id": "artifact:artifact_1",
            "properties": {},
            "provenance": {},
        },
        {
            "edge_id": "edge:2",
            "edge_type": "artifact_from_provider",
            "source_node_id": "artifact:artifact_1",
            "target_node_id": "provider:github",
            "properties": {},
            "provenance": {},
        },
        {
            "edge_id": "edge:3",
            "edge_type": "paper_observed_in_source_family",
            "source_node_id": "paper:paper_1",
            "target_node_id": "source_family:arxiv",
            "properties": {},
            "provenance": {},
        },
        {
            "edge_id": "edge:4",
            "edge_type": "paper_assigned_to_topic_cluster",
            "source_node_id": "paper:paper_1",
            "target_node_id": "topic_cluster:7",
            "properties": {},
            "provenance": {},
        },
    ]

    schema = {
        "schema_version": "paper_artifact_graph_output_schema_v1",
    }

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
        "trusted_links": {
            "policy_version": "artifact_trusted_links_policy_v1",
            "runtime_policy_version": "artifact_trusted_links_policy_v1",
        },
        "safety": {
            "write_latest_pointer": False,
            "create_global_trusted_links_file": False,
        },
    }

    quality = {
        "schema_version": "paper_artifact_graph_data_quality_summary_v1",
        "ok": True,
        "quality": {
            "nodes_count": 5,
            "edges_count": 4,
            "node_type_counts": {
                "artifact": 1,
                "paper": 1,
                "provider": 1,
                "source_family": 1,
                "topic_cluster": 1,
            },
            "edge_type_counts": {
                "artifact_from_provider": 1,
                "paper_assigned_to_topic_cluster": 1,
                "paper_has_artifact": 1,
                "paper_observed_in_source_family": 1,
            },
            "canonical_papers_loaded": 1,
            "canonical_papers_with_ids": 1,
            "artifact_entities_loaded": 1,
            "artifact_entities_with_ids": 1,
            "artifact_observations_loaded": 1,
            "trusted_links_raw_count": 1,
            "trusted_links_used_count": 1,
            "skipped_trusted_links_missing_paper": 0,
            "skipped_trusted_links_missing_artifact": 0,
            "topic_assignments_loaded": 1,
            "topic_assignments_valid": 1,
            "topic_edges_count": 1,
            "topic_assignments_missing_paper": 0,
            "topic_assignments_missing_cluster": 0,
        },
    }

    write_yaml(config_path, config)
    write_jsonl(graph_dir / "nodes.jsonl", nodes)
    write_jsonl(graph_dir / "edges.jsonl", edges)
    write_json(graph_dir / "schema.json", schema)
    write_json(graph_dir / "manifest.json", manifest)
    write_json(graph_dir / "data_quality_summary.json", quality)
    (graph_dir / "README.md").write_text("# Test graph\n", encoding="utf-8")
    write_checksums(graph_dir)

    return config_path, graph_dir


def assert_failed(report: dict, check_name: str) -> None:
    assert report["ok"] is False
    assert check_name in report["required_failed_checks"]


def test_valid_output_passes(tmp_path: Path):
    config_path, _ = make_valid_output(tmp_path)

    report = validate_output(config_path=config_path)

    assert report["ok"] is True
    assert report["required_failed_count"] == 0


def test_missing_output_file_fails(tmp_path: Path):
    config_path, graph_dir = make_valid_output(tmp_path)
    (graph_dir / "nodes.jsonl").unlink()

    report = validate_output(config_path=config_path)

    assert_failed(report, "required_output_files_exist")
    assert_failed(report, "nodes_path_exists")


def test_duplicate_node_id_fails(tmp_path: Path):
    config_path, graph_dir = make_valid_output(tmp_path)

    rows = [
        {"node_id": "paper:paper_1", "node_type": "paper", "label": "Paper", "properties": {}},
        {"node_id": "paper:paper_1", "node_type": "paper", "label": "Paper duplicate", "properties": {}},
        {"node_id": "artifact:artifact_1", "node_type": "artifact", "label": "Artifact", "properties": {}},
        {"node_id": "provider:github", "node_type": "provider", "label": "github", "properties": {}},
        {"node_id": "source_family:arxiv", "node_type": "source_family", "label": "arxiv", "properties": {}},
        {"node_id": "topic_cluster:7", "node_type": "topic_cluster", "label": "Topic cluster 7", "properties": {}},
    ]
    write_jsonl(graph_dir / "nodes.jsonl", rows)

    report = validate_output(config_path=config_path, check_checksums=False)

    assert_failed(report, "duplicate_node_ids_zero")


def test_missing_edge_endpoint_fails(tmp_path: Path):
    config_path, graph_dir = make_valid_output(tmp_path)

    edges = [
        {
            "edge_id": "edge:1",
            "edge_type": "paper_has_artifact",
            "source_node_id": "paper:missing",
            "target_node_id": "artifact:artifact_1",
            "properties": {},
            "provenance": {},
        },
        {
            "edge_id": "edge:2",
            "edge_type": "artifact_from_provider",
            "source_node_id": "artifact:artifact_1",
            "target_node_id": "provider:github",
            "properties": {},
            "provenance": {},
        },
        {
            "edge_id": "edge:3",
            "edge_type": "paper_observed_in_source_family",
            "source_node_id": "paper:paper_1",
            "target_node_id": "source_family:arxiv",
            "properties": {},
            "provenance": {},
        },
        {
            "edge_id": "edge:4",
            "edge_type": "paper_assigned_to_topic_cluster",
            "source_node_id": "paper:paper_1",
            "target_node_id": "topic_cluster:7",
            "properties": {},
            "provenance": {},
        },
    ]
    write_jsonl(graph_dir / "edges.jsonl", edges)

    report = validate_output(config_path=config_path, check_checksums=False)

    assert_failed(report, "edge_missing_source_nodes_zero")


def test_trusted_count_mismatch_fails(tmp_path: Path):
    config_path, graph_dir = make_valid_output(tmp_path)

    quality = json.loads((graph_dir / "data_quality_summary.json").read_text(encoding="utf-8"))
    quality["quality"]["trusted_links_used_count"] = 0
    write_json(graph_dir / "data_quality_summary.json", quality)

    report = validate_output(config_path=config_path, check_checksums=False)

    assert_failed(report, "trusted_links_used_matches_expected")


def test_manifest_canonical_truth_fails(tmp_path: Path):
    config_path, graph_dir = make_valid_output(tmp_path)

    manifest = json.loads((graph_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["canonical_truth"] = True
    write_json(graph_dir / "manifest.json", manifest)

    report = validate_output(config_path=config_path, check_checksums=False)

    assert_failed(report, "manifest_not_canonical_truth")


def test_checksum_mismatch_fails(tmp_path: Path):
    config_path, graph_dir = make_valid_output(tmp_path)

    with (graph_dir / "README.md").open("a", encoding="utf-8") as f:
        f.write("changed\n")

    report = validate_output(config_path=config_path)

    assert_failed(report, "checksums_valid")
    assert report["checksum_failures"]
