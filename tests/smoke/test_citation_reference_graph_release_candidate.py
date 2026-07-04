from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.validation.check_citation_reference_graph_release_candidate import (
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


def _make_graph_fixture(base: Path) -> tuple[Path, Path, Path, Path, Path]:
    graph_dir = base / "data/graphs/citation_reference_graph/v0.1"
    report_dir = base / "artifacts/reports/validation"
    query_cli_path = base / "scripts/graph/query_citation_reference_graph.py"
    graph_dir.mkdir(parents=True)
    report_dir.mkdir(parents=True)
    query_cli_path.parent.mkdir(parents=True)
    query_cli_path.write_text("# query cli placeholder\n", encoding="utf-8")

    nodes = [
        {
            "node_id": "paper:p1",
            "node_type": "paper",
            "canonical_id": "p1",
            "title": "Paper 1",
            "year": 2024,
            "doi": "10.1000/p1",
            "arxiv_id": "2401.00001",
        },
        {
            "node_id": "paper:p2",
            "node_type": "paper",
            "canonical_id": "p2",
            "title": "Paper 2",
            "year": 2024,
            "doi": "10.1000/p2",
            "arxiv_id": "2401.00002",
        },
        {
            "node_id": "external_reference:openalex-w999",
            "node_type": "external_reference",
            "reference_key": "openalex_id:W999",
            "reference_type": "openalex_id",
            "normalized_value": "W999",
            "resolution_status": "unresolved_external",
        },
        {
            "node_id": "source_family:openalex_alignment",
            "node_type": "source_family",
            "source_family": "openalex_alignment",
        },
    ]
    edges = [
        {
            "edge_id": "edge:paper_references_paper:1",
            "edge_type": "paper_references_paper",
            "source_node_id": "paper:p2",
            "target_node_id": "paper:p1",
            "source_canonical_id": "p2",
            "target_canonical_id": "p1",
            "reference_type": "openalex_id",
            "reference_value": "W123",
            "reference_field": "referenced_ids",
            "resolution_status": "resolved_to_canonical",
            "provenance_kind": "canonical_reference",
            "source_layer": "canonical_reference_fields",
            "confidence": 1.0,
        },
        {
            "edge_id": "edge:paper_references_external:1",
            "edge_type": "paper_references_external",
            "source_node_id": "paper:p1",
            "target_node_id": "external_reference:openalex-w999",
            "source_canonical_id": "p1",
            "target_reference_key": "openalex_id:W999",
            "reference_type": "openalex_id",
            "reference_value": "W999",
            "reference_field": "referenced_ids",
            "resolution_status": "unresolved_external",
            "provenance_kind": "external_identifier_reference",
            "source_layer": "canonical_reference_fields",
            "confidence": 0.8,
        },
        {
            "edge_id": "edge:paper_has_reference_source_family:1",
            "edge_type": "paper_has_reference_source_family",
            "source_node_id": "paper:p1",
            "target_node_id": "source_family:openalex_alignment",
            "source_canonical_id": "p1",
            "source_family": "openalex_alignment",
            "provenance_kind": "source_family_reference",
            "source_layer": "source_provenance",
            "confidence": 1.0,
        },
    ]

    _write_jsonl(graph_dir / "nodes.jsonl", nodes)
    _write_jsonl(graph_dir / "edges.jsonl", edges)
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
            "builder": {"input_mode": "file", "live_db_dependency": False, "limit": None},
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
                "paper_nodes_count": 2,
                "external_reference_nodes_count": 1,
                "source_family_nodes_count": 1,
                "paper_references_paper_edges_count": 1,
                "paper_references_external_edges_count": 1,
                "paper_has_reference_source_family_edges_count": 1,
            },
        },
    )
    (graph_dir / "README.md").write_text("# Citation / Reference Graph fixture\n", encoding="utf-8")
    _write_checksums(graph_dir)

    output_report = report_dir / "citation_reference_graph_output_latest.json"
    inspection_report = report_dir / "citation_reference_graph_inspection_latest.json"
    _write_json(
        output_report,
        {
            "schema_version": "citation_reference_graph_output_quality_v1",
            "summary": {"ok": True, "required_failed_count": 0, "warning_count": 0, "total_checks": 36},
        },
    )
    _write_json(
        inspection_report,
        {
            "schema_version": "citation_reference_graph_inspection_report_v1",
            "summary": {
                "ok": True,
                "required_failed_count": 0,
                "warning_count": 0,
                "total_checks": 35,
                "nodes_count": 4,
                "edges_count": 3,
                "paper_references_paper_edges_count": 1,
                "paper_references_external_edges_count": 1,
            },
            "inspection": {
                "resolved_reference_edges_count": 1,
                "unresolved_reference_edges_count": 1,
                "reference_resolution_ratio": 0.5,
            },
        },
    )
    return graph_dir, report_dir, output_report, inspection_report, query_cli_path


def test_release_candidate_passes_with_expected_fixture_counts_and_writes_reports(tmp_path: Path) -> None:
    graph_dir, report_dir, output_report, inspection_report, query_cli_path = _make_graph_fixture(tmp_path)

    result = check_release_candidate(
        graph_dir=graph_dir,
        report_dir=report_dir,
        output_report_path=output_report,
        inspection_report_path=inspection_report,
        query_cli_path=query_cli_path,
        strict=True,
        expected_graph_counts={
            "nodes_count": 4,
            "edges_count": 3,
            "node_paper_count": 2,
            "node_external_reference_count": 1,
            "node_source_family_count": 1,
            "edge_paper_references_paper_count": 1,
            "edge_paper_references_external_count": 1,
            "edge_paper_has_reference_source_family_count": 1,
        },
        expected_inspection_counts={
            "resolved_reference_edges_count": 1,
            "unresolved_reference_edges_count": 1,
            "reference_resolution_ratio": 0.5,
        },
        write_reports=True,
    )

    assert result["summary"]["ok"] is True
    assert result["summary"]["warning_count"] == 0
    assert result["verdict"]["technical_graph_candidate_ready"] is True
    assert result["verdict"]["manual_review_required"] is True
    assert result["verdict"]["publication_ready"] is False
    assert (report_dir / "citation_reference_graph_release_candidate_latest.json").exists()
    assert (report_dir / "citation_reference_graph_release_candidate_latest.md").exists()


def test_release_candidate_fails_on_checksum_mismatch(tmp_path: Path) -> None:
    graph_dir, report_dir, output_report, inspection_report, query_cli_path = _make_graph_fixture(tmp_path)
    (graph_dir / "README.md").write_text("# changed\n", encoding="utf-8")

    result = check_release_candidate(
        graph_dir=graph_dir,
        report_dir=report_dir,
        output_report_path=output_report,
        inspection_report_path=inspection_report,
        query_cli_path=query_cli_path,
        strict=True,
        expected_graph_counts=None,
        expected_inspection_counts=None,
        write_reports=False,
    )

    assert result["summary"]["ok"] is False
    assert "checksums_match" in result["verdict"]["required_failed_checks"]


def test_missing_reports_are_required_only_in_strict_mode(tmp_path: Path) -> None:
    graph_dir, report_dir, output_report, inspection_report, query_cli_path = _make_graph_fixture(tmp_path)
    output_report.unlink()
    inspection_report.unlink()

    non_strict = check_release_candidate(
        graph_dir=graph_dir,
        report_dir=report_dir,
        output_report_path=output_report,
        inspection_report_path=inspection_report,
        query_cli_path=query_cli_path,
        strict=False,
        expected_graph_counts=None,
        expected_inspection_counts=None,
        write_reports=False,
    )
    strict = check_release_candidate(
        graph_dir=graph_dir,
        report_dir=report_dir,
        output_report_path=output_report,
        inspection_report_path=inspection_report,
        query_cli_path=query_cli_path,
        strict=True,
        expected_graph_counts=None,
        expected_inspection_counts=None,
        write_reports=False,
    )

    assert non_strict["summary"]["ok"] is True
    assert non_strict["summary"]["warning_count"] == 2
    assert strict["summary"]["ok"] is False
    assert "output_validator_report_exists" in strict["verdict"]["required_failed_checks"]
    assert "inspection_report_exists" in strict["verdict"]["required_failed_checks"]


def test_manifest_safety_flags_are_required(tmp_path: Path) -> None:
    graph_dir, report_dir, output_report, inspection_report, query_cli_path = _make_graph_fixture(tmp_path)
    manifest = json.loads((graph_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["safety"]["may_be_used_as_reconcile_input"] = True
    _write_json(graph_dir / "manifest.json", manifest)
    _write_checksums(graph_dir)

    result = check_release_candidate(
        graph_dir=graph_dir,
        report_dir=report_dir,
        output_report_path=output_report,
        inspection_report_path=inspection_report,
        query_cli_path=query_cli_path,
        strict=True,
        expected_graph_counts=None,
        expected_inspection_counts=None,
        write_reports=False,
    )

    assert result["summary"]["ok"] is False
    assert "manifest_safety_flags" in result["verdict"]["required_failed_checks"]


def test_openalex_reference_must_not_be_classified_as_doi(tmp_path: Path) -> None:
    graph_dir, report_dir, output_report, inspection_report, query_cli_path = _make_graph_fixture(tmp_path)
    edges = [json.loads(line) for line in (graph_dir / "edges.jsonl").read_text(encoding="utf-8").splitlines()]
    edges[1]["reference_type"] = "doi"
    edges[1]["reference_value"] = "https://openalex.org/W999"
    edges[1]["target_reference_key"] = "doi:https://openalex.org/W999"
    _write_jsonl(graph_dir / "edges.jsonl", edges)
    _write_checksums(graph_dir)

    result = check_release_candidate(
        graph_dir=graph_dir,
        report_dir=report_dir,
        output_report_path=output_report,
        inspection_report_path=inspection_report,
        query_cli_path=query_cli_path,
        strict=True,
        expected_graph_counts=None,
        expected_inspection_counts=None,
        write_reports=False,
    )

    assert result["summary"]["ok"] is False
    assert "openalex_reference_normalization" in result["verdict"]["required_failed_checks"]


def test_cli_no_write_reports(tmp_path: Path) -> None:
    graph_dir, report_dir, output_report, inspection_report, query_cli_path = _make_graph_fixture(tmp_path)
    rc = main(
        [
            "--graph-dir",
            str(graph_dir),
            "--report-dir",
            str(report_dir),
            "--output-report",
            str(output_report),
            "--inspection-report",
            str(inspection_report),
            "--query-cli-path",
            str(query_cli_path),
            "--strict",
            "--skip-accepted-counts",
            "--skip-inspection-diagnostic-counts",
            "--no-write-reports",
        ]
    )

    assert rc == 0
    assert not (report_dir / "citation_reference_graph_release_candidate_latest.json").exists()
