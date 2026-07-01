from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from scripts.export.package_paper_artifact_graph import package_paper_artifact_graph
from scripts.validation.check_paper_artifact_graph_package import main as validator_main
from scripts.validation.check_paper_artifact_graph_package import validate_package


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _write_graph_checksums(graph_dir: Path) -> None:
    rows = []
    for name in [
        "nodes.jsonl",
        "edges.jsonl",
        "schema.json",
        "manifest.json",
        "data_quality_summary.json",
        "README.md",
    ]:
        rows.append(f"{_sha256(graph_dir / name)}  {name}")
    (graph_dir / "checksums.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")


def _make_fixture(base: Path) -> Path:
    graph_dir = base / "data/graphs/paper_artifact_graph/v0.1"
    report_dir = base / "artifacts/reports/validation"
    package_dir = base / "data/graphs/paper_artifact_graph/packages/v0.1"
    config_path = base / "configs/paper_artifact_graph_package.yaml"

    graph_dir.mkdir(parents=True)
    report_dir.mkdir(parents=True)
    package_dir.mkdir(parents=True)
    config_path.parent.mkdir(parents=True)

    _write_jsonl(
        graph_dir / "nodes.jsonl",
        [
            {"node_id": "paper:p1", "node_type": "paper", "label": "Paper 1", "properties": {}},
            {"node_id": "artifact:a1", "node_type": "artifact", "label": "Artifact 1", "properties": {}},
            {"node_id": "provider:github", "node_type": "provider", "label": "github", "properties": {}},
            {"node_id": "source_family:arxiv", "node_type": "source_family", "label": "arxiv", "properties": {}},
            {"node_id": "topic_cluster:7", "node_type": "topic_cluster", "label": "Topic cluster 7", "properties": {}},
        ],
    )
    _write_jsonl(
        graph_dir / "edges.jsonl",
        [
            {
                "edge_id": "e1",
                "edge_type": "paper_has_artifact",
                "source_node_id": "paper:p1",
                "target_node_id": "artifact:a1",
                "properties": {},
                "provenance": {},
            },
            {
                "edge_id": "e2",
                "edge_type": "artifact_from_provider",
                "source_node_id": "artifact:a1",
                "target_node_id": "provider:github",
                "properties": {},
                "provenance": {},
            },
            {
                "edge_id": "e3",
                "edge_type": "paper_observed_in_source_family",
                "source_node_id": "paper:p1",
                "target_node_id": "source_family:arxiv",
                "properties": {},
                "provenance": {},
            },
            {
                "edge_id": "e4",
                "edge_type": "paper_assigned_to_topic_cluster",
                "source_node_id": "paper:p1",
                "target_node_id": "topic_cluster:7",
                "properties": {},
                "provenance": {},
            },
        ],
    )
    _write_json(graph_dir / "schema.json", {"schema_version": "paper_artifact_graph_output_schema_v1"})
    _write_json(
        graph_dir / "manifest.json",
        {
            "schema_version": "paper_artifact_graph_manifest_v1",
            "run_ts": "20260701T000000Z",
            "builder": {
                "status": "local_derived_builder",
                "input_mode": "file",
                "live_db_dependency": False,
                "create_latest_pointer": False,
            },
            "graph": {
                "version": "v0.1",
                "canonical_truth": False,
                "may_be_used_as_reconcile_input": False,
                "publication_ready": False,
            },
            "quality_summary": {
                "nodes_count": 5,
                "edges_count": 4,
                "node_type_counts": {
                    "paper": 1,
                    "artifact": 1,
                    "provider": 1,
                    "source_family": 1,
                    "topic_cluster": 1,
                },
                "edge_type_counts": {
                    "paper_has_artifact": 1,
                    "artifact_from_provider": 1,
                    "paper_observed_in_source_family": 1,
                    "paper_assigned_to_topic_cluster": 1,
                },
                "trusted_links_used_count": 1,
                "topic_edges_count": 1,
            },
            "dry_run": False,
            "publication_ready": False,
            "canonical_truth": False,
            "may_be_used_as_reconcile_input": False,
        },
    )
    _write_json(
        graph_dir / "data_quality_summary.json",
        {
            "schema_version": "paper_artifact_graph_data_quality_summary_v1",
            "ok": True,
            "quality": {
                "nodes_count": 5,
                "edges_count": 4,
            },
        },
    )
    (graph_dir / "README.md").write_text("# Graph fixture\n", encoding="utf-8")
    _write_graph_checksums(graph_dir)

    _write_json(
        report_dir / "paper_artifact_graph_release_candidate_latest.json",
        {
            "schema_version": "paper_artifact_graph_release_candidate_v1",
            "summary": {
                "ok": True,
                "required_failed_count": 0,
                "warning_count": 0,
            },
            "verdict": {
                "technical_graph_candidate_ready": True,
                "manual_review_required": True,
                "publication_ready": False,
                "publication_block_reason": "manual_review_not_completed",
            },
        },
    )
    (report_dir / "paper_artifact_graph_release_candidate_latest.md").write_text("# RC report\n", encoding="utf-8")

    config = {
        "schema_version": "paper_artifact_graph_package_config_v1",
        "package": {
            "name": "paper_artifact_graph",
            "version": "v0.1",
            "status": "local_package_candidate",
            "archive_name": "paper_artifact_graph_v0.1.zip",
            "archive_root": "paper_artifact_graph_v0.1",
            "publication_ready": False,
            "manual_review_required": True,
            "may_be_used_as_reconcile_input": False,
        },
        "inputs": {
            "graph_dir": str(graph_dir),
            "release_candidate_report_json": str(report_dir / "paper_artifact_graph_release_candidate_latest.json"),
            "release_candidate_report_md": str(report_dir / "paper_artifact_graph_release_candidate_latest.md"),
        },
        "outputs": {
            "package_dir": str(package_dir),
            "zip_path": str(package_dir / "paper_artifact_graph_v0.1.zip"),
            "manifest_path": str(package_dir / "package_manifest.json"),
            "readme_path": str(package_dir / "README.md"),
            "checksums_path": str(package_dir / "checksums.txt"),
        },
        "validation": {
            "report_dir": str(report_dir),
        },
        "required_graph_files": [
            "nodes.jsonl",
            "edges.jsonl",
            "schema.json",
            "manifest.json",
            "data_quality_summary.json",
            "README.md",
            "checksums.txt",
        ],
        "expected_counts": {
            "nodes_count": 5,
            "edges_count": 4,
            "node_paper_count": 1,
            "node_artifact_count": 1,
            "node_provider_count": 1,
            "node_source_family_count": 1,
            "node_topic_cluster_count": 1,
            "edge_paper_has_artifact_count": 1,
            "edge_artifact_from_provider_count": 1,
            "edge_paper_observed_in_source_family_count": 1,
            "edge_paper_assigned_to_topic_cluster_count": 1,
        },
        "safety": {
            "read_only_graph_input": True,
            "rebuild_graph": False,
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
        },
    }
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return config_path


def test_package_builder_and_validator_pass_on_fixture(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)

    package_result = package_paper_artifact_graph(config_path=config_path, force=True)
    assert package_result["ok"] is True
    assert Path(package_result["zip_path"]).exists()
    assert Path(package_result["manifest_path"]).exists()

    validation_result = validate_package(config_path=config_path, strict=True)
    assert validation_result["summary"]["ok"] is True
    assert validation_result["summary"]["required_failed_count"] == 0
    assert validation_result["verdict"]["package_candidate_ready"] is True


def test_package_builder_dry_run_does_not_write_package(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)

    result = package_paper_artifact_graph(config_path=config_path, dry_run=True)

    assert result["dry_run"] is True
    assert result["included_files_count"] == 9
    assert not (tmp_path / "data/graphs/paper_artifact_graph/packages/v0.1/paper_artifact_graph_v0.1.zip").exists()


def test_package_builder_rejects_failed_release_candidate(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    report_path = tmp_path / "artifacts/reports/validation/paper_artifact_graph_release_candidate_latest.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["summary"]["ok"] = False
    report_path.write_text(json.dumps(report), encoding="utf-8")

    try:
        package_paper_artifact_graph(config_path=config_path, force=True)
    except ValueError as exc:
        assert "Release-candidate report is not ready" in str(exc)
    else:
        raise AssertionError("Expected failed release-candidate report to be rejected")


def test_package_validator_fails_on_checksum_mismatch(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    package_paper_artifact_graph(config_path=config_path, force=True)

    readme_path = tmp_path / "data/graphs/paper_artifact_graph/packages/v0.1/README.md"
    readme_path.write_text("# changed\n", encoding="utf-8")

    result = validate_package(config_path=config_path, strict=True, write_reports=False)

    assert result["summary"]["ok"] is False
    assert "package_checksums_match" in result["verdict"]["required_failed_checks"]


def test_package_validator_cli_no_write_reports(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    package_paper_artifact_graph(config_path=config_path, force=True)

    rc = validator_main(["--config", str(config_path), "--strict", "--no-write-reports"])

    assert rc == 0
