from __future__ import annotations

import json
import zipfile
from pathlib import Path

import yaml

from scripts.validation.check_paper_artifact_graph_line_checkpoint import main as checkpoint_main
from scripts.validation.check_paper_artifact_graph_line_checkpoint import validate_line_checkpoint


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_file(path: Path, text: str = "placeholder\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_graph_fixture(graph_dir: Path) -> None:
    graph_dir.mkdir(parents=True, exist_ok=True)
    for name in ["nodes.jsonl", "edges.jsonl", "schema.json", "data_quality_summary.json", "README.md", "checksums.txt"]:
        _write_file(graph_dir / name)

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


def _write_green_report(path: Path, schema: str = "report_v1") -> None:
    _write_json(
        path,
        {
            "schema_version": schema,
            "summary": {
                "ok": True,
                "required_failed_count": 0,
                "warning_count": 0,
            },
            "verdict": {},
        },
    )


def _write_package_fixture(package_dir: Path) -> None:
    package_dir.mkdir(parents=True, exist_ok=True)
    _write_file(package_dir / "README.md")
    _write_file(package_dir / "checksums.txt")
    _write_json(
        package_dir / "package_manifest.json",
        {
            "schema_version": "paper_artifact_graph_package_manifest_v1",
            "package": {
                "publication_ready": False,
                "manual_review_required": True,
                "may_be_used_as_reconcile_input": False,
            },
            "boundaries": {
                "local_package_candidate": True,
                "generated_output": True,
                "read_only_graph_input": True,
                "rebuilds_graph": False,
                "mutates_canonical_truth": False,
                "may_be_used_as_reconcile_input": False,
                "changes_postgres": False,
                "changes_qdrant": False,
                "changes_retrieval": False,
                "changes_ranking": False,
                "changes_api": False,
                "changes_ui": False,
                "publishes_dataset": False,
            },
            "release_candidate": {
                "summary_ok": True,
                "required_failed_count": 0,
                "technical_graph_candidate_ready": True,
                "manual_review_required": True,
                "publication_ready": False,
            },
        },
    )
    with zipfile.ZipFile(package_dir / "paper_artifact_graph_v0.1.zip", "w") as archive:
        archive.writestr("paper_artifact_graph_v0.1/README.md", "ok\n")


def _make_fixture(base: Path) -> Path:
    graph_dir = base / "data/graphs/paper_artifact_graph/v0.1"
    package_dir = base / "data/graphs/paper_artifact_graph/packages/v0.1"
    report_dir = base / "artifacts/reports/validation"
    config_path = base / "configs/paper_artifact_graph_line_checkpoint.yaml"

    required_tracked_files = [
        "configs/paper_artifact_graph.yaml",
        "configs/paper_artifact_graph_builder.yaml",
        "configs/paper_artifact_graph_package.yaml",
        "scripts/export/build_paper_artifact_graph.py",
        "scripts/validation/check_paper_artifact_graph_output.py",
        "scripts/validation/check_paper_artifact_graph_inspection.py",
        "scripts/graph/query_paper_artifact_graph.py",
        "scripts/validation/check_paper_artifact_graph_release_candidate.py",
        "scripts/export/package_paper_artifact_graph.py",
        "scripts/validation/check_paper_artifact_graph_package.py",
        "docs/paper_artifact_graph_v0.md",
        "docs/paper_artifact_graph_builder_v0.md",
        "docs/paper_artifact_graph_inspection_v0.md",
        "docs/paper_artifact_graph_query_cli_v0.md",
        "docs/paper_artifact_graph_release_candidate_v0.md",
        "docs/paper_artifact_graph_package_v0.md",
    ]
    for rel in required_tracked_files:
        _write_file(base / rel)

    _write_graph_fixture(graph_dir)
    _write_package_fixture(package_dir)

    _write_green_report(report_dir / "paper_artifact_graph_inspection_latest.json", "paper_artifact_graph_inspection_v1")
    _write_green_report(report_dir / "paper_artifact_graph_release_candidate_latest.json", "paper_artifact_graph_release_candidate_v1")
    _write_green_report(report_dir / "paper_artifact_graph_package_latest.json", "paper_artifact_graph_package_validation_v1")

    config = {
        "schema_version": "paper_artifact_graph_line_checkpoint_config_v1",
        "checkpoint": {
            "name": "paper_artifact_graph_line_checkpoint",
            "version": "v0.1",
            "status": "local_line_checkpoint",
            "publication_ready": False,
            "manual_review_required": True,
            "may_be_used_as_reconcile_input": False,
        },
        "inputs": {
            "graph_dir": str(graph_dir),
            "package_dir": str(package_dir),
            "inspection_report": str(report_dir / "paper_artifact_graph_inspection_latest.json"),
            "release_candidate_report": str(report_dir / "paper_artifact_graph_release_candidate_latest.json"),
            "package_report": str(report_dir / "paper_artifact_graph_package_latest.json"),
        },
        "validation": {
            "report_dir": str(report_dir),
        },
        "required_tracked_files": [str(base / rel) for rel in required_tracked_files],
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
            "paper_artifact_graph_v0.1.zip",
            "package_manifest.json",
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
            "trusted_links_used_count": 1,
            "topic_edges_count": 1,
        },
        "line_components": {
            "contract": "accepted",
            "builder": "accepted_local_derived_builder",
            "output_validator": "accepted_strict_validator",
            "inspection": "accepted_read_only_inspection",
            "query_cli": "accepted_read_only_query_cli",
            "release_candidate": "accepted_read_only_release_candidate",
            "package": "accepted_local_package_candidate",
        },
        "safety": {
            "read_only_checkpoint": True,
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


def test_line_checkpoint_passes_on_complete_fixture(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)

    result = validate_line_checkpoint(config_path=config_path, strict=True)

    assert result["summary"]["ok"] is True
    assert result["summary"]["required_failed_count"] == 0
    assert result["verdict"]["paper_artifact_graph_line_complete"] is True
    assert result["verdict"]["publication_ready"] is False


def test_line_checkpoint_fails_when_package_report_is_not_green(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    report_path = tmp_path / "artifacts/reports/validation/paper_artifact_graph_package_latest.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["summary"]["ok"] = False
    report_path.write_text(json.dumps(report), encoding="utf-8")

    result = validate_line_checkpoint(config_path=config_path, strict=True, write_reports=False)

    assert result["summary"]["ok"] is False
    assert "package_report_green" in result["verdict"]["required_failed_checks"]


def test_line_checkpoint_fails_on_graph_count_mismatch(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    manifest_path = tmp_path / "data/graphs/paper_artifact_graph/v0.1/manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["quality_summary"]["nodes_count"] = 999
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = validate_line_checkpoint(config_path=config_path, strict=True, write_reports=False)

    assert result["summary"]["ok"] is False
    assert "graph_counts_match_checkpoint" in result["verdict"]["required_failed_checks"]


def test_line_checkpoint_cli_no_write_reports(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)

    rc = checkpoint_main(["--config", str(config_path), "--strict", "--no-write-reports"])

    assert rc == 0
