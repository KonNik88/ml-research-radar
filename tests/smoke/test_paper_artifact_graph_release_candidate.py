from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.validation.check_paper_artifact_graph_release_candidate import (
    check_release_candidate,
    main,
)


def _write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _write_checksums(graph_dir: Path) -> None:
    checksum_lines = []
    for name in [
        "nodes.jsonl",
        "edges.jsonl",
        "schema.json",
        "manifest.json",
        "data_quality_summary.json",
        "README.md",
    ]:
        checksum_lines.append(f"{_sha256(graph_dir / name)}  {name}")
    (graph_dir / "checksums.txt").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")


def _make_graph_fixture(base: Path) -> tuple[Path, Path, Path]:
    graph_dir = base / "data/graphs/paper_artifact_graph/v0.1"
    report_dir = base / "artifacts/reports/validation"
    graph_dir.mkdir(parents=True)
    report_dir.mkdir(parents=True)

    nodes = [
        {"node_id": "paper:p1", "node_type": "paper", "label": "Paper 1", "properties": {"title": "Paper 1"}},
        {"node_id": "paper:p2", "node_type": "paper", "label": "Paper 2", "properties": {"title": "Paper 2"}},
        {"node_id": "artifact:a1", "node_type": "artifact", "label": "repo", "properties": {"provider": "github"}},
        {"node_id": "provider:github", "node_type": "provider", "label": "github", "properties": {"provider": "github"}},
        {"node_id": "source_family:arxiv", "node_type": "source_family", "label": "arxiv", "properties": {"source_family": "arxiv"}},
        {"node_id": "topic_cluster:7", "node_type": "topic_cluster", "label": "Topic cluster 7", "properties": {"cluster_id": 7}},
    ]
    edges = [
        {"edge_id": "e1", "edge_type": "paper_has_artifact", "source_node_id": "paper:p1", "target_node_id": "artifact:a1", "properties": {}, "provenance": {}},
        {"edge_id": "e2", "edge_type": "paper_has_artifact", "source_node_id": "paper:p2", "target_node_id": "artifact:a1", "properties": {}, "provenance": {}},
        {"edge_id": "e3", "edge_type": "artifact_from_provider", "source_node_id": "artifact:a1", "target_node_id": "provider:github", "properties": {"provider": "github"}, "provenance": {}},
        {"edge_id": "e4", "edge_type": "paper_observed_in_source_family", "source_node_id": "paper:p1", "target_node_id": "source_family:arxiv", "properties": {}, "provenance": {}},
        {"edge_id": "e5", "edge_type": "paper_assigned_to_topic_cluster", "source_node_id": "paper:p1", "target_node_id": "topic_cluster:7", "properties": {}, "provenance": {}},
    ]

    _write_jsonl(graph_dir / "nodes.jsonl", nodes)
    _write_jsonl(graph_dir / "edges.jsonl", edges)
    _write_json(
        graph_dir / "manifest.json",
        {
            "builder": {
                "input_mode": "file",
                "live_db_dependency": False,
                "create_latest_pointer": False,
            },
            "graph": {
                "canonical_truth": False,
                "may_be_used_as_reconcile_input": False,
                "publication_ready": False,
            },
            "dry_run": False,
            "publication_ready": False,
            "canonical_truth": False,
            "may_be_used_as_reconcile_input": False,
        },
    )
    _write_json(graph_dir / "schema.json", {"schema_version": "test"})
    _write_json(graph_dir / "data_quality_summary.json", {"ok": True})
    (graph_dir / "README.md").write_text("# test graph\n", encoding="utf-8")
    _write_checksums(graph_dir)

    inspection_report = report_dir / "paper_artifact_graph_inspection_latest.json"
    _write_json(
        inspection_report,
        {
            "ok": True,
            "required_failed_count": 0,
            "papers_with_artifacts_count": 2,
            "topic_clusters_with_artifact_ready_papers_count": 1,
        },
    )
    return graph_dir, report_dir, inspection_report


def test_release_candidate_passes_on_complete_fixture(tmp_path: Path) -> None:
    graph_dir, report_dir, inspection_report = _make_graph_fixture(tmp_path)

    result = check_release_candidate(
        graph_dir=graph_dir,
        report_dir=report_dir,
        inspection_report_path=inspection_report,
        strict=True,
        expected_graph_counts={
            "nodes_count": 6,
            "edges_count": 5,
            "node_paper_count": 2,
            "node_artifact_count": 1,
            "node_provider_count": 1,
            "node_source_family_count": 1,
            "node_topic_cluster_count": 1,
            "edge_paper_has_artifact_count": 2,
            "edge_artifact_from_provider_count": 1,
            "edge_paper_observed_in_source_family_count": 1,
            "edge_paper_assigned_to_topic_cluster_count": 1,
        },
        expected_inspection_counts={
            "papers_with_artifacts_count": 2,
            "topic_clusters_with_artifact_ready_papers_count": 1,
        },
        expected_provider_smoke={"provider": "github", "artifacts": 1, "paper_artifact_links": 2},
        write_reports=True,
    )

    assert result["summary"]["ok"] is True
    assert result["summary"]["warning_count"] == 0
    assert result["verdict"]["technical_graph_candidate_ready"] is True
    assert (report_dir / "paper_artifact_graph_release_candidate_latest.json").exists()
    assert (report_dir / "paper_artifact_graph_release_candidate_latest.md").exists()


def test_release_candidate_fails_on_checksum_mismatch(tmp_path: Path) -> None:
    graph_dir, report_dir, inspection_report = _make_graph_fixture(tmp_path)
    (graph_dir / "README.md").write_text("# changed\n", encoding="utf-8")

    result = check_release_candidate(
        graph_dir=graph_dir,
        report_dir=report_dir,
        inspection_report_path=inspection_report,
        strict=True,
        expected_graph_counts=None,
        expected_inspection_counts=None,
        expected_provider_smoke=None,
        write_reports=False,
    )

    assert result["summary"]["ok"] is False
    assert "checksums_match" in result["verdict"]["required_failed_checks"]


def test_missing_inspection_report_is_required_only_in_strict_mode(tmp_path: Path) -> None:
    graph_dir, report_dir, inspection_report = _make_graph_fixture(tmp_path)
    inspection_report.unlink()

    non_strict = check_release_candidate(
        graph_dir=graph_dir,
        report_dir=report_dir,
        inspection_report_path=inspection_report,
        strict=False,
        expected_graph_counts=None,
        expected_inspection_counts=None,
        expected_provider_smoke=None,
        write_reports=False,
    )
    strict = check_release_candidate(
        graph_dir=graph_dir,
        report_dir=report_dir,
        inspection_report_path=inspection_report,
        strict=True,
        expected_graph_counts=None,
        expected_inspection_counts=None,
        expected_provider_smoke=None,
        write_reports=False,
    )

    assert non_strict["summary"]["ok"] is True
    assert non_strict["summary"]["warning_count"] == 1
    assert strict["summary"]["ok"] is False
    assert "inspection_report_exists" in strict["verdict"]["required_failed_checks"]


def test_manifest_safety_flags_are_required(tmp_path: Path) -> None:
    graph_dir, report_dir, inspection_report = _make_graph_fixture(tmp_path)
    _write_json(
        graph_dir / "manifest.json",
        {
            "builder": {
                "input_mode": "file",
                "live_db_dependency": False,
                "create_latest_pointer": False,
            },
            "canonical_truth": True,
            "may_be_used_as_reconcile_input": False,
            "publication_ready": False,
            "dry_run": False,
        },
    )
    _write_checksums(graph_dir)

    result = check_release_candidate(
        graph_dir=graph_dir,
        report_dir=report_dir,
        inspection_report_path=inspection_report,
        strict=True,
        expected_graph_counts=None,
        expected_inspection_counts=None,
        expected_provider_smoke=None,
        write_reports=False,
    )

    assert result["summary"]["ok"] is False
    assert "manifest_safety_flags" in result["verdict"]["required_failed_checks"]


def test_cli_no_write_reports(tmp_path: Path) -> None:
    graph_dir, report_dir, inspection_report = _make_graph_fixture(tmp_path)
    rc = main(
        [
            "--graph-dir",
            str(graph_dir),
            "--report-dir",
            str(report_dir),
            "--inspection-report",
            str(inspection_report),
            "--strict",
            "--skip-accepted-counts",
            "--skip-provider-smoke",
            "--skip-inspection-diagnostic-counts",
            "--no-write-reports",
        ]
    )

    assert rc == 0
