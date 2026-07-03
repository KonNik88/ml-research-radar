from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts.validation.check_paper_artifact_graph_analytics import main, validate_graph_analytics


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def _write_yaml(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(obj, sort_keys=False), encoding="utf-8")


def _make_fixture(tmp_path: Path) -> Path:
    graph_dir = tmp_path / "data/graphs/paper_artifact_graph/v0.1"
    config_path = tmp_path / "configs/paper_artifact_graph_analytics.yaml"
    report_dir = tmp_path / "artifacts/reports/validation"

    nodes = [
        {"node_id": "paper:p1", "node_type": "paper", "label": "Paper 1", "properties": {"canonical_id": "p1"}},
        {"node_id": "paper:p2", "node_type": "paper", "label": "Paper 2", "properties": {"canonical_id": "p2"}},
        {"node_id": "artifact:a1", "node_type": "artifact", "label": "example/repo", "properties": {"artifact_id": "a1", "provider": "github"}},
        {"node_id": "artifact:a2", "node_type": "artifact", "label": "dataset", "properties": {"artifact_id": "a2", "provider": "zenodo"}},
        {"node_id": "provider:github", "node_type": "provider", "label": "github", "properties": {"provider": "github"}},
        {"node_id": "provider:zenodo", "node_type": "provider", "label": "zenodo", "properties": {"provider": "zenodo"}},
        {"node_id": "source_family:arxiv", "node_type": "source_family", "label": "arxiv", "properties": {"source_family": "arxiv"}},
        {"node_id": "topic_cluster:7", "node_type": "topic_cluster", "label": "Topic cluster 7", "properties": {"topic_cluster_id": "7"}},
    ]
    edges = [
        {"edge_id": "e1", "edge_type": "paper_has_artifact", "source_node_id": "paper:p1", "target_node_id": "artifact:a1", "properties": {"relation_type": "code"}, "provenance": {}},
        {"edge_id": "e2", "edge_type": "paper_has_artifact", "source_node_id": "paper:p2", "target_node_id": "artifact:a1", "properties": {"relation_type": "code"}, "provenance": {}},
        {"edge_id": "e3", "edge_type": "paper_has_artifact", "source_node_id": "paper:p2", "target_node_id": "artifact:a2", "properties": {"relation_type": "dataset"}, "provenance": {}},
        {"edge_id": "e4", "edge_type": "artifact_from_provider", "source_node_id": "artifact:a1", "target_node_id": "provider:github", "properties": {"provider": "github"}, "provenance": {}},
        {"edge_id": "e5", "edge_type": "artifact_from_provider", "source_node_id": "artifact:a2", "target_node_id": "provider:zenodo", "properties": {"provider": "zenodo"}, "provenance": {}},
        {"edge_id": "e6", "edge_type": "paper_observed_in_source_family", "source_node_id": "paper:p1", "target_node_id": "source_family:arxiv", "properties": {"source_family": "arxiv"}, "provenance": {}},
        {"edge_id": "e7", "edge_type": "paper_observed_in_source_family", "source_node_id": "paper:p2", "target_node_id": "source_family:arxiv", "properties": {"source_family": "arxiv"}, "provenance": {}},
        {"edge_id": "e8", "edge_type": "paper_assigned_to_topic_cluster", "source_node_id": "paper:p1", "target_node_id": "topic_cluster:7", "properties": {"topic_cluster_id": "7"}, "provenance": {}},
        {"edge_id": "e9", "edge_type": "paper_assigned_to_topic_cluster", "source_node_id": "paper:p2", "target_node_id": "topic_cluster:7", "properties": {"topic_cluster_id": "7"}, "provenance": {}},
    ]
    manifest = {
        "schema_version": "paper_artifact_graph_manifest_v1",
        "canonical_truth": False,
        "may_be_used_as_reconcile_input": False,
        "publication_ready": False,
        "builder": {"input_mode": "file", "live_db_dependency": False},
    }
    quality = {"schema_version": "paper_artifact_graph_data_quality_summary_v1", "ok": True}

    _write_jsonl(graph_dir / "nodes.jsonl", nodes)
    _write_jsonl(graph_dir / "edges.jsonl", edges)
    _write_json(graph_dir / "manifest.json", manifest)
    _write_json(graph_dir / "data_quality_summary.json", quality)

    config = {
        "schema_version": "paper_artifact_graph_analytics_config_v1",
        "analytics": {
            "name": "paper_artifact_graph_analytics",
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
        },
        "validation": {"report_dir": str(report_dir)},
        "expected_counts": {
            "nodes_count": 8,
            "edges_count": 9,
            "node_paper_count": 2,
            "node_artifact_count": 2,
            "node_provider_count": 2,
            "node_source_family_count": 1,
            "node_topic_cluster_count": 1,
            "edge_paper_has_artifact_count": 3,
            "edge_artifact_from_provider_count": 2,
            "edge_paper_observed_in_source_family_count": 2,
            "edge_paper_assigned_to_topic_cluster_count": 2,
        },
        "expected_analytics": {
            "min_papers_with_artifacts_count": 1,
            "min_artifacts_with_linked_papers_count": 1,
            "min_provider_count": 1,
            "min_topic_clusters_with_artifact_ready_papers_count": 1,
            "required_provider_smoke": {"provider": "github", "min_artifacts": 1, "min_paper_artifact_links": 1},
        },
        "safety": {
            "read_only_analytics": True,
            "rebuild_graph": False,
            "rebuild_package": False,
            "mutate_canonical_documents": False,
            "mutate_artifact_inputs": False,
            "mutate_topic_inputs": False,
            "mutate_retrieval_artifacts": False,
            "mutate_qdrant": False,
            "mutate_postgres": False,
            "mutate_api": False,
            "mutate_ui": False,
            "mutate_ranking": False,
            "publish_dataset": False,
            "create_latest_pointer": False,
            "create_graph_runtime": False,
            "may_be_used_as_reconcile_input": False,
        },
    }
    _write_yaml(config_path, config)
    return config_path


def _assert_failed(report: dict, check_name: str) -> None:
    assert report["summary"]["ok"] is False
    assert check_name in report["verdict"]["required_failed_checks"]


def test_graph_analytics_default_fixture_passes_and_writes_reports(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)

    report = validate_graph_analytics(config_path=config_path, strict=True)

    assert report["summary"]["ok"] is True
    assert report["summary"]["required_failed_count"] == 0
    assert report["verdict"]["publication_ready"] is False
    assert report["analytics"]["counts"]["papers_with_artifacts_count"] == 2
    assert report["analytics"]["counts"]["multi_paper_artifacts_count"] == 1
    assert report["analytics"]["provider_distribution"]["paper_artifact_links"]["github"] == 2
    assert (tmp_path / "artifacts/reports/validation/paper_artifact_graph_analytics_latest.json").exists()
    assert (tmp_path / "artifacts/reports/validation/paper_artifact_graph_analytics_latest.md").exists()


def test_graph_analytics_no_write_reports(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)

    report = validate_graph_analytics(config_path=config_path, strict=True, write_reports=False)

    assert report["summary"]["ok"] is True
    assert not (tmp_path / "artifacts/reports/validation/paper_artifact_graph_analytics_latest.json").exists()


def test_graph_analytics_fails_on_missing_required_edge_type(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    edges_path = Path(config["inputs"]["edges_path"])
    rows = [json.loads(line) for line in edges_path.read_text(encoding="utf-8").splitlines()]
    rows = [row for row in rows if row["edge_type"] != "paper_has_artifact"]
    _write_jsonl(edges_path, rows)

    report = validate_graph_analytics(config_path=config_path, strict=True, write_reports=False)

    _assert_failed(report, "required_edge_types_present")
    _assert_failed(report, "paper_has_artifact_edges_present")


def test_graph_analytics_fails_on_count_mismatch(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["expected_counts"]["nodes_count"] = 999
    _write_yaml(config_path, config)

    report = validate_graph_analytics(config_path=config_path, strict=True, write_reports=False)

    _assert_failed(report, "expected_nodes_count_matches")


def test_graph_analytics_fails_on_manifest_publication_ready(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    manifest_path = Path(config["inputs"]["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["publication_ready"] = True
    _write_json(manifest_path, manifest)

    report = validate_graph_analytics(config_path=config_path, strict=True, write_reports=False)

    _assert_failed(report, "manifest_safety_flags")


def test_graph_analytics_fails_on_unsafe_config_flag(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["safety"]["rebuild_graph"] = True
    _write_yaml(config_path, config)

    report = validate_graph_analytics(config_path=config_path, strict=True, write_reports=False)

    _assert_failed(report, "safety_flags_all_false")


def test_graph_analytics_provider_smoke_failure(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["expected_analytics"]["required_provider_smoke"]["provider"] = "huggingface"
    _write_yaml(config_path, config)

    report = validate_graph_analytics(config_path=config_path, strict=True, write_reports=False)

    _assert_failed(report, "provider_smoke_artifacts_minimum")
    _assert_failed(report, "provider_smoke_links_minimum")


def test_graph_analytics_cli_no_write_reports(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)

    rc = main(["--config", str(config_path), "--strict", "--no-write-reports"])

    assert rc == 0
