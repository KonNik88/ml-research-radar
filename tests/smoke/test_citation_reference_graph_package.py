from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from scripts.export.package_citation_reference_graph import package_citation_reference_graph
from scripts.validation.check_citation_reference_graph_package import main as validator_main
from scripts.validation.check_citation_reference_graph_package import validate_package


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
    graph_dir = base / "data/graphs/citation_reference_graph/v0.1"
    report_dir = base / "artifacts/reports/validation"
    package_dir = base / "data/graphs/citation_reference_graph/packages/v0.1"
    config_path = base / "configs/citation_reference_graph_package.yaml"

    graph_dir.mkdir(parents=True)
    report_dir.mkdir(parents=True)
    package_dir.mkdir(parents=True)
    config_path.parent.mkdir(parents=True)

    _write_jsonl(
        graph_dir / "nodes.jsonl",
        [
            {"node_id": "paper:p1", "node_type": "paper", "canonical_id": "p1", "title": "Paper 1", "year": 2024},
            {"node_id": "paper:p2", "node_type": "paper", "canonical_id": "p2", "title": "Paper 2", "year": 2024},
            {
                "node_id": "external_reference:r1",
                "node_type": "external_reference",
                "reference_key": "doi:10.0000/example",
                "reference_type": "doi",
                "normalized_value": "10.0000/example",
                "resolution_status": "unresolved_external",
            },
            {"node_id": "source_family:openalex_alignment", "node_type": "source_family", "source_family": "openalex_alignment"},
        ],
    )
    _write_jsonl(
        graph_dir / "edges.jsonl",
        [
            {
                "edge_id": "e1",
                "edge_type": "paper_references_paper",
                "source_node_id": "paper:p1",
                "target_node_id": "paper:p2",
                "confidence": 1.0,
                "provenance_kind": "canonical_reference",
                "source_layer": "canonical_reference_fields",
            },
            {
                "edge_id": "e2",
                "edge_type": "paper_references_external",
                "source_node_id": "paper:p1",
                "target_node_id": "external_reference:r1",
                "confidence": 1.0,
                "provenance_kind": "external_identifier_reference",
                "source_layer": "canonical_reference_fields",
            },
            {
                "edge_id": "e3",
                "edge_type": "paper_has_reference_source_family",
                "source_node_id": "paper:p1",
                "target_node_id": "source_family:openalex_alignment",
                "confidence": 1.0,
                "provenance_kind": "source_family_reference",
                "source_layer": "source_provenance",
            },
        ],
    )
    _write_json(
        graph_dir / "schema.json",
        {
            "schema_version": "citation_reference_graph_schema_v1",
            "graph": {"name": "citation_reference_graph", "version": "v0.1"},
        },
    )
    _write_json(
        graph_dir / "manifest.json",
        {
            "schema_version": "citation_reference_graph_manifest_v1",
            "graph": {"name": "citation_reference_graph", "version": "v0.1", "status": "local_derived_output"},
            "generated_at": "2026-07-04T00:00:00+00:00",
            "builder": {
                "script": "scripts/export/build_citation_reference_graph.py",
                "input_mode": "file",
                "live_db_dependency": False,
                "limit": None,
            },
            "counts": {
                "nodes_count": 4,
                "edges_count": 3,
                "paper_nodes_count": 2,
                "external_reference_nodes_count": 1,
                "source_family_nodes_count": 1,
                "paper_references_paper_edges_count": 1,
                "paper_references_external_edges_count": 1,
                "paper_has_reference_source_family_edges_count": 1,
            },
            "quality": {
                "ok": True,
                "reference_type_counts": {"doi": 1},
                "source_family_reference_paper_counts": {"openalex_alignment": 1},
                "stats": {},
            },
            "safety": {
                "canonical_truth_impact": "none",
                "may_overwrite_operational_latest": False,
                "may_be_used_as_reconcile_input": False,
                "may_change_db_schema": False,
                "may_change_api_behavior": False,
                "may_change_streamlit_behavior": False,
                "may_change_retrieval_behavior": False,
                "may_change_qdrant_behavior": False,
                "may_change_ranking_behavior": False,
                "may_require_graph_runtime": False,
                "may_publish_without_manual_review": False,
            },
        },
    )
    _write_json(
        graph_dir / "data_quality_summary.json",
        {
            "schema_version": "citation_reference_graph_data_quality_summary_v1",
            "summary": {
                "ok": True,
                "nodes_count": 4,
                "edges_count": 3,
            },
        },
    )
    (graph_dir / "README.md").write_text("# Graph fixture\n", encoding="utf-8")
    _write_graph_checksums(graph_dir)

    _write_json(
        report_dir / "citation_reference_graph_release_candidate_latest.json",
        {
            "schema_version": "citation_reference_graph_release_candidate_v1",
            "summary": {
                "ok": True,
                "required_failed_count": 0,
                "warning_count": 0,
            },
            "verdict": {
                "technical_graph_candidate_ready": True,
                "manual_review_required": True,
                "manual_review_complete": False,
                "publication_ready": False,
                "publication_block_reason": "manual_review_not_completed",
            },
        },
    )
    (report_dir / "citation_reference_graph_release_candidate_latest.md").write_text("# RC report\n", encoding="utf-8")

    config = {
        "schema_version": "citation_reference_graph_package_config_v1",
        "package": {
            "name": "citation_reference_graph",
            "version": "v0.1",
            "status": "local_package_candidate",
            "archive_name": "citation_reference_graph_v0.1.zip",
            "archive_root": "citation_reference_graph_v0.1",
            "publication_ready": False,
            "manual_review_required": True,
            "may_be_used_as_reconcile_input": False,
        },
        "inputs": {
            "graph_dir": str(graph_dir),
            "release_candidate_report_json": str(report_dir / "citation_reference_graph_release_candidate_latest.json"),
            "release_candidate_report_md": str(report_dir / "citation_reference_graph_release_candidate_latest.md"),
        },
        "outputs": {
            "package_dir": str(package_dir),
            "zip_path": str(package_dir / "citation_reference_graph_v0.1.zip"),
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
            "nodes_count": 4,
            "edges_count": 3,
            "node_paper_count": 2,
            "node_external_reference_count": 1,
            "node_source_family_count": 1,
            "edge_paper_references_paper_count": 1,
            "edge_paper_references_external_count": 1,
            "edge_paper_has_reference_source_family_count": 1,
        },
        "safety": {
            "read_only_graph_input": True,
            "rebuild_graph": False,
            "mutate_canonical_documents": False,
            "mutate_retrieval_artifacts": False,
            "mutate_qdrant": False,
            "mutate_postgres": False,
            "mutate_db_schema": False,
            "mutate_api": False,
            "mutate_ui": False,
            "mutate_ranking": False,
            "publish_dataset": False,
            "publish_graph": False,
            "create_latest_pointer": False,
            "create_graph_runtime": False,
            "require_networkx_runtime": False,
            "require_neo4j_runtime": False,
            "require_graphrag_runtime": False,
            "parse_full_text": False,
            "parse_pdfs": False,
            "parse_bibliography_sections": False,
        },
    }
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return config_path


def test_package_builder_and_validator_pass_on_fixture(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)

    package_result = package_citation_reference_graph(config_path=config_path, force=True)
    assert package_result["ok"] is True
    assert Path(package_result["zip_path"]).exists()
    assert Path(package_result["manifest_path"]).exists()

    validation_result = validate_package(config_path=config_path, strict=True)
    assert validation_result["summary"]["ok"] is True
    assert validation_result["summary"]["required_failed_count"] == 0
    assert validation_result["verdict"]["package_candidate_ready"] is True


def test_package_builder_dry_run_does_not_write_package(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)

    result = package_citation_reference_graph(config_path=config_path, dry_run=True)

    assert result["dry_run"] is True
    assert result["included_files_count"] == 9
    package_dir = Path(result["would_write"]["package_dir"])
    assert not (package_dir / "citation_reference_graph_v0.1.zip").exists()


def test_package_builder_rejects_failed_release_candidate(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    report_path = Path(config["inputs"]["release_candidate_report_json"])
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["summary"]["ok"] = False
    report["summary"]["required_failed_count"] = 1
    report_path.write_text(json.dumps(report), encoding="utf-8")

    try:
        package_citation_reference_graph(config_path=config_path, force=True)
    except ValueError as exc:
        assert "Release-candidate report is not ready" in str(exc)
    else:  # pragma: no cover - defensive branch.
        raise AssertionError("package builder accepted a failed release-candidate report")


def test_package_validator_detects_checksum_mismatch(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    package_citation_reference_graph(config_path=config_path, force=True)

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    readme_path = Path(config["outputs"]["readme_path"])
    readme_path.write_text(readme_path.read_text(encoding="utf-8") + "\ncorruption\n", encoding="utf-8")

    result = validate_package(config_path=config_path, strict=True)

    assert result["summary"]["ok"] is False
    assert "package_checksums_match" in result["verdict"]["required_failed_checks"]


def test_package_validator_cli_no_write_reports(tmp_path: Path, monkeypatch) -> None:
    config_path = _make_fixture(tmp_path)
    package_citation_reference_graph(config_path=config_path, force=True)

    rc = validator_main(["--config", str(config_path), "--strict", "--no-write-reports"])

    assert rc == 0
    report_dir = tmp_path / "artifacts/reports/validation"
    assert not (report_dir / "citation_reference_graph_package_latest.json").exists()
