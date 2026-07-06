from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts.validation.check_graph_review_evidence_pack import (
    main,
    validate_graph_review_evidence_pack,
)


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_yaml(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(obj, sort_keys=False), encoding="utf-8")


def _ok_report(*, manual_review_required: bool = True, manual_review_complete: bool = False) -> dict:
    return {
        "schema_version": "fixture_report_v1",
        "summary": {
            "ok": True,
            "required_failed_count": 0,
            "warning_count": 0,
        },
        "verdict": {
            "manual_review_required": manual_review_required,
            "manual_review_complete": manual_review_complete,
            "publication_ready": False,
            "publication_block_reason": "manual_review_not_completed",
        },
    }


def _make_manifest(*, nodes: int, edges: int, node_counts: dict, edge_counts: dict) -> dict:
    return {
        "schema_version": "graph_manifest_v1",
        "canonical_truth": False,
        "may_be_used_as_reconcile_input": False,
        "publication_ready": False,
        "graph": {
            "canonical_truth": False,
            "may_be_used_as_reconcile_input": False,
            "publication_ready": False,
        },
        "quality_summary": {
            "nodes_count": nodes,
            "edges_count": edges,
            "node_type_counts": node_counts,
            "edge_type_counts": edge_counts,
        },
    }


def _make_fixture(tmp_path: Path) -> Path:
    report_dir = tmp_path / "artifacts/reports/validation"
    history_dir = report_dir / "history"

    citation_graph_dir = tmp_path / "data/graphs/citation_reference_graph/v0.1"
    paper_artifact_graph_dir = tmp_path / "data/graphs/paper_artifact_graph/v0.1"

    _write_json(
        citation_graph_dir / "manifest.json",
        _make_manifest(
            nodes=529295,
            edges=745516,
            node_counts={
                "paper": 60954,
                "external_reference": 468336,
                "source_family": 5,
            },
            edge_counts={
                "paper_references_paper": 6165,
                "paper_references_external": 703234,
                "paper_has_reference_source_family": 36117,
            },
        ),
    )
    _write_json(citation_graph_dir / "data_quality_summary.json", {"ok": True})

    _write_json(
        paper_artifact_graph_dir / "manifest.json",
        _make_manifest(
            nodes=68385,
            edges=163757,
            node_counts={
                "paper": 60954,
                "artifact": 7336,
                "provider": 10,
                "source_family": 5,
                "topic_cluster": 80,
            },
            edge_counts={
                "paper_has_artifact": 7430,
                "artifact_from_provider": 7336,
                "paper_observed_in_source_family": 88037,
                "paper_assigned_to_topic_cluster": 60954,
            },
        ),
    )
    _write_json(paper_artifact_graph_dir / "data_quality_summary.json", {"ok": True})

    for prefix in ("citation_reference_graph", "paper_artifact_graph"):
        for name in (
            "release_candidate",
            "package",
            "line_checkpoint",
            "manual_review",
            "analytics",
        ):
            _write_json(report_dir / f"{prefix}_{name}_latest.json", _ok_report())

    config = {
        "schema_version": "graph_review_evidence_pack_config_v1",
        "pack": {
            "name": "graph_review_evidence_pack",
            "version": "v0.1",
            "status": "local_read_only_review_evidence",
            "publication_ready": False,
            "manual_review_required": True,
            "may_be_used_as_reconcile_input": False,
        },
        "inputs": {
            "citation_reference_graph": {
                "manifest_path": str(citation_graph_dir / "manifest.json"),
                "data_quality_summary_path": str(citation_graph_dir / "data_quality_summary.json"),
                "release_candidate_report_path": str(report_dir / "citation_reference_graph_release_candidate_latest.json"),
                "package_report_path": str(report_dir / "citation_reference_graph_package_latest.json"),
                "line_checkpoint_report_path": str(report_dir / "citation_reference_graph_line_checkpoint_latest.json"),
                "manual_review_report_path": str(report_dir / "citation_reference_graph_manual_review_latest.json"),
                "analytics_report_path": str(report_dir / "citation_reference_graph_analytics_latest.json"),
            },
            "paper_artifact_graph": {
                "manifest_path": str(paper_artifact_graph_dir / "manifest.json"),
                "data_quality_summary_path": str(paper_artifact_graph_dir / "data_quality_summary.json"),
                "release_candidate_report_path": str(report_dir / "paper_artifact_graph_release_candidate_latest.json"),
                "package_report_path": str(report_dir / "paper_artifact_graph_package_latest.json"),
                "line_checkpoint_report_path": str(report_dir / "paper_artifact_graph_line_checkpoint_latest.json"),
                "manual_review_report_path": str(report_dir / "paper_artifact_graph_manual_review_latest.json"),
                "analytics_report_path": str(report_dir / "paper_artifact_graph_analytics_latest.json"),
            },
        },
        "outputs": {
            "report_dir": str(report_dir),
            "latest_json_name": "graph_review_evidence_pack_latest.json",
            "latest_md_name": "graph_review_evidence_pack_latest.md",
            "history_dir": str(history_dir),
        },
        "expected_graphs": {
            "citation_reference_graph": {
                "display_name": "Citation / Reference Graph v0.1",
                "nodes_count": 529295,
                "edges_count": 745516,
                "publication_ready": False,
                "manual_review_required": True,
                "manual_review_complete": False,
                "counters": {
                    "paper_nodes": 60954,
                    "external_reference_nodes": 468336,
                    "source_family_nodes": 5,
                    "paper_references_paper_edges": 6165,
                    "paper_references_external_edges": 703234,
                    "paper_has_reference_source_family_edges": 36117,
                },
                "caveats": {
                    "metadata_reference_fields_only": True,
                    "expected_reference_resolution_ratio": 0.00869,
                },
            },
            "paper_artifact_graph": {
                "display_name": "Paper–Artifact Graph v0.1",
                "nodes_count": 68385,
                "edges_count": 163757,
                "publication_ready": False,
                "manual_review_required": True,
                "manual_review_complete": False,
                "counters": {
                    "paper_nodes": 60954,
                    "artifact_nodes": 7336,
                    "provider_nodes": 10,
                    "source_family_nodes": 5,
                    "topic_cluster_nodes": 80,
                    "paper_has_artifact_edges": 7430,
                    "artifact_from_provider_edges": 7336,
                    "paper_observed_in_source_family_edges": 88037,
                    "paper_assigned_to_topic_cluster_edges": 60954,
                },
                "caveats": {
                    "trusted_artifact_links_only": True,
                },
            },
        },
        "safety": {
            "read_only_pack": True,
            "rebuild_graph": False,
            "rebuild_package": False,
            "mutate_canonical_documents": False,
            "mutate_reconcile_outputs": False,
            "mutate_artifact_inputs": False,
            "mutate_reference_inputs": False,
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
            "implement_public_graph_api": False,
            "implement_graphrag": False,
            "may_be_used_as_reconcile_input": False,
        },
    }

    config_path = tmp_path / "configs/graph_review_evidence_pack.yaml"
    _write_yaml(config_path, config)
    return config_path


def _assert_failed(report: dict, check_name: str) -> None:
    assert report["summary"]["ok"] is False
    assert check_name in report["verdict"]["required_failed_checks"]


def test_graph_review_evidence_pack_default_fixture_passes_and_writes_reports(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)

    report = validate_graph_review_evidence_pack(config_path=config_path, strict=True)

    assert report["summary"]["ok"] is True
    assert report["summary"]["required_failed_count"] == 0
    assert report["verdict"]["publication_ready"] is False
    assert report["verdict"]["manual_review_required"] is True
    assert report["graphs"]["citation_reference_graph"]["counts"]["nodes_count"] == 529295
    assert report["graphs"]["paper_artifact_graph"]["counts"]["paper_has_artifact_edges"] == 7430
    assert (tmp_path / "artifacts/reports/validation/graph_review_evidence_pack_latest.json").exists()
    assert (tmp_path / "artifacts/reports/validation/graph_review_evidence_pack_latest.md").exists()




def test_graph_review_evidence_pack_accepts_legacy_manifest_without_direct_boundary_flags(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    manifest_path = Path(config["inputs"]["citation_reference_graph"]["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("canonical_truth", None)
    manifest.pop("may_be_used_as_reconcile_input", None)
    manifest.pop("publication_ready", None)
    manifest.pop("graph", None)
    _write_json(manifest_path, manifest)

    report = validate_graph_review_evidence_pack(
        config_path=config_path,
        strict=True,
        write_reports=False,
    )

    assert report["summary"]["ok"] is True
    assert report["graphs"]["citation_reference_graph"]["manifest_flags"]["canonical_truth"] is False
    assert (
        report["graphs"]["citation_reference_graph"]["manifest_flags"]["canonical_truth_source"]
        == "green_downstream_reports"
    )


def test_graph_review_evidence_pack_no_write_reports(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)

    report = validate_graph_review_evidence_pack(
        config_path=config_path,
        strict=True,
        write_reports=False,
    )

    assert report["summary"]["ok"] is True
    assert not (tmp_path / "artifacts/reports/validation/graph_review_evidence_pack_latest.json").exists()


def test_graph_review_evidence_pack_fails_on_unsafe_manifest(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    manifest_path = Path(config["inputs"]["citation_reference_graph"]["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["canonical_truth"] = True
    _write_json(manifest_path, manifest)

    report = validate_graph_review_evidence_pack(
        config_path=config_path,
        strict=True,
        write_reports=False,
    )

    _assert_failed(report, "citation_reference_graph_manifest_canonical_truth_false")


def test_graph_review_evidence_pack_fails_on_count_mismatch(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["expected_graphs"]["paper_artifact_graph"]["edges_count"] = 1
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    report = validate_graph_review_evidence_pack(
        config_path=config_path,
        strict=True,
        write_reports=False,
    )

    _assert_failed(report, "paper_artifact_graph_edges_count_matches_expected")


def test_graph_review_evidence_pack_fails_on_publication_ready_report(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    manual_review_path = Path(config["inputs"]["paper_artifact_graph"]["manual_review_report_path"])
    report = json.loads(manual_review_path.read_text(encoding="utf-8"))
    report["verdict"]["publication_ready"] = True
    _write_json(manual_review_path, report)

    result = validate_graph_review_evidence_pack(
        config_path=config_path,
        strict=True,
        write_reports=False,
    )

    _assert_failed(result, "paper_artifact_graph_publication_ready_matches_expected")
