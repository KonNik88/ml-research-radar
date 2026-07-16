from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts.validation.check_citation_reference_graph_manual_review_evidence import (
    main,
    validate_manual_review_evidence,
)


CATEGORY_IDS = [
    "license_redistribution",
    "source_provider_terms",
    "reference_metadata_caveats",
    "explicit_reference_fields_only",
    "unresolved_external_reference_caveats",
    "low_resolution_ratio_caveat",
    "openalex_normalization_review",
    "doi_reference_policy_review",
    "source_family_reference_distribution_review",
    "top_internal_referenced_papers_review",
    "top_external_references_review",
    "full_text_not_parsed_caveat",
    "bibliography_not_parsed_caveat",
    "package_manifest_checksum_review",
    "readme_clarity",
    "known_limitations",
    "publication_target_decision",
    "manual_approval_state",
]

AUTOMATED_IDS = CATEGORY_IDS[2:14] + ["known_limitations"]
HUMAN_IDS = [
    "license_redistribution",
    "source_provider_terms",
    "readme_clarity",
    "publication_target_decision",
    "manual_approval_state",
]


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _green_report(schema_version: str) -> dict:
    return {
        "schema_version": schema_version,
        "summary": {"ok": True, "required_failed_count": 0, "warning_count": 0},
        "verdict": {
            "manual_review_required": True,
            "manual_review_complete": False,
            "publication_ready": False,
            "publication_block_reason": "manual_review_not_completed",
        },
    }


def _make_fixture(base: Path) -> Path:
    config_path = base / "configs/citation_reference_graph_manual_review_evidence.yaml"
    manual_config_path = base / "configs/citation_reference_graph_manual_review.yaml"
    reports = base / "artifacts/reports/validation"
    graph_dir = base / "data/graphs/citation_reference_graph/v0.1"
    package_dir = base / "data/graphs/citation_reference_graph/packages/v0.1"
    docs = base / "docs"

    manual_config = {
        "schema_version": "citation_reference_graph_manual_review_config_v1",
        "review": {
            "name": "citation_reference_graph_manual_review",
            "version": "v0.1",
            "status": "local_manual_review_gate",
            "graph_version": "v0.1",
            "approval_state": "approved",
            "manual_review_required": True,
            "manual_review_complete": True,
            "publication_ready": False,
            "publication_block_reason": "publication_action_not_in_scope",
            "may_be_used_as_reconcile_input": False,
            "reviewer_role": "project_owner_maintainer",
            "reviewed_at": "2026-07-16",
            "decision_record": str(docs / "citation_reference_graph_manual_review_decision_record_v0.1.md"),
        },
        "manual_review": {
            "required_category_ids": list(CATEGORY_IDS),
            "categories": [
                {
                    "id": category_id,
                    "title": category_id.replace("_", " ").title(),
                    "required": True,
                    "status": "passed",
                    "reviewer_note": f"Passed by human reviewer: {category_id}",
                }
                for category_id in CATEGORY_IDS
            ],
        },
    }
    _write_yaml(manual_config_path, manual_config)

    manual_report = _green_report("citation_reference_graph_manual_review_v1")
    manual_report["verdict"].update(
        {
            "manual_review_complete": True,
            "publication_block_reason": "publication_action_not_in_scope",
        }
    )
    manual_report["manual_review"] = {
        "approval_state": "approved",
        "category_status_counts": {"passed": 18},
        "manual_review_required": True,
        "manual_review_complete": True,
        "required_category_count": 18,
    }
    _write_json(reports / "citation_reference_graph_manual_review_latest.json", manual_report)

    external_samples = [
        {
            "source_canonical_id": "p1",
            "target_reference_key": "openalex_id:W1",
            "reference_type": "openalex_id",
            "reference_field": "referenced_ids",
        },
        {
            "source_canonical_id": "p2",
            "target_reference_key": "doi:10.1/example",
            "reference_type": "doi",
            "reference_field": "referenced_dois",
        },
    ]
    internal_samples = [
        {
            "source_canonical_id": "p3",
            "target_canonical_id": "p4",
            "reference_type": "openalex_id",
            "reference_field": "referenced_ids",
        },
        {
            "source_canonical_id": "p5",
            "target_canonical_id": "p6",
            "reference_type": "doi",
            "reference_field": "referenced_dois",
        },
    ]
    analytics = _green_report("citation_reference_graph_analytics_v1")
    analytics.update(
        {
            "analytics": {
                "counts": {
                    "reference_edges_count": 709399,
                    "resolved_reference_edges_count": 6165,
                    "unresolved_reference_edges_count": 703234,
                    "external_reference_nodes_count": 468336,
                    "source_family_count": 5,
                },
                "reference_resolution_ratio": 0.00869,
                "reference_field_distribution": {
                    "referenced_dois": 269355,
                    "referenced_ids": 440044,
                },
                "reference_type_distribution": {
                    "doi": 269355,
                    "openalex_id": 440044,
                },
                "source_family_distribution": {
                    "acl_anthology": 3,
                    "arxiv": 9144,
                    "crossref": 8859,
                    "openalex": 9050,
                    "semantic_scholar": 9061,
                },
                "top_referenced_papers": [{"canonical_id": "p4", "count": 103}],
                "top_external_references": [
                    {"reference_key": "openalex_id:W1", "count": 1013}
                ],
                "samples": {
                    "paper_to_external_edges": external_samples,
                    "paper_to_paper_edges": internal_samples,
                    "reference_source_family_edges": [
                        {"source_canonical_id": "p1", "source_family": "arxiv"}
                    ],
                },
            },
            "manual_review_caveats": {
                "metadata_reference_fields_only": True,
                "full_text_parsed": False,
                "pdfs_parsed": False,
                "bibliography_sections_parsed": False,
                "raw_reference_strings_without_identifiers_parsed": False,
                "unresolved_references_preserved_as_external_reference_nodes": True,
                "low_resolution_ratio_expected_in_v0_1": True,
                "reference_resolution_ratio": 0.00869,
            },
        }
    )
    _write_json(reports / "citation_reference_graph_analytics_latest.json", analytics)

    inspection = _green_report("citation_reference_graph_inspection_report_v1")
    _write_json(reports / "citation_reference_graph_inspection_latest.json", inspection)

    release_candidate = _green_report("citation_reference_graph_release_candidate_v1")
    release_candidate["checks"] = [
        {"name": "openalex_reference_normalization", "ok": True}
    ]
    release_candidate["verdict"]["technical_graph_candidate_ready"] = True
    _write_json(
        reports / "citation_reference_graph_release_candidate_latest.json",
        release_candidate,
    )

    package_report = _green_report("citation_reference_graph_package_validation_v1")
    package_report["checks"] = [
        {"name": "package_checksums_match", "ok": True}
    ]
    _write_json(reports / "citation_reference_graph_package_latest.json", package_report)
    _write_json(
        reports / "citation_reference_graph_line_checkpoint_latest.json",
        _green_report("citation_reference_graph_line_checkpoint_validation_v1"),
    )

    live = _green_report("citation_graph_live_smoke_v1")
    live["checks"] = {
        "top_referenced_endpoint_200": True,
        "top_external_endpoint_200": True,
    }
    _write_json(reports / "citation_graph_live_smoke_latest.json", live)
    _write_json(
        reports / "citation_graph_api_regression_latest.json",
        _green_report("citation_graph_api_regression_v1"),
    )
    _write_json(
        reports / "graph_review_evidence_pack_latest.json",
        _green_report("graph_review_evidence_pack_v1"),
    )

    _write_json(
        graph_dir / "manifest.json",
        {
            "schema_version": "citation_reference_graph_manifest_v1",
            "graph": {
                "name": "citation_reference_graph",
                "version": "v0.1",
                "status": "local_derived_output",
            },
        },
    )
    _write_json(graph_dir / "data_quality_summary.json", {"summary": {"ok": True}})
    _write_json(
        package_dir / "package_manifest.json",
        {
            "schema_version": "citation_reference_graph_package_manifest_v1",
            "package": {
                "name": "citation_reference_graph",
                "version": "v0.1",
                "status": "local_package_candidate",
                "manual_review_required": True,
                "publication_ready": False,
                "may_be_used_as_reconcile_input": False,
            },
            "included_files": [
                {
                    "archive_path": "citation_reference_graph_v0.1/nodes.jsonl",
                    "kind": "graph_file",
                    "sha256": "abc",
                    "size_bytes": 100,
                }
            ],
            "zip": {"sha256": "ziphash", "size_bytes": 200},
        },
    )

    graph_readme = """# Citation / Reference Graph v0.1 local output
local derived citation/reference graph
not canonical truth
not a reconcile input
not a runtime graph
not a public API/UI artifact
"""
    package_readme = """# Citation / Reference Graph Package v0.1
Local package candidate
not canonical truth
not a reconcile input
not a runtime graph
not a publication-ready dataset
manual_review_required: True
publication_ready: False
explicit canonical metadata reference fields only
does not parse full text
does not publish a dataset or graph
"""
    _write_text(graph_dir / "README.md", graph_readme)
    _write_text(package_dir / "README.md", package_readme)

    known_issues = """
metadata_reference_fields_only = true
not_a_complete_citation_index = true
reference_resolution_ratio = 0.00869
manual_review_required = true
manual_review_complete = false
publication_ready = false
full_graph_runtime_loader = not implemented
graph_db_materialization = not implemented
graphrag = not implemented
"""
    _write_text(docs / "citation_graph_known_issues_v0.1.md", known_issues)
    _write_text(docs / "source_matrix.md", "arxiv openalex crossref semantic_scholar acl_anthology")
    _write_text(docs / "merge_policy.md", "DOI and OpenAlex reference identity are conservative")
    decision_record = """
non-commercial educational and portfolio
Kaggle
GitHub
public Radar website
does not redistribute PDFs
does not redistribute full text
attribution
publication action remains separate
approval_state = approved
manual_review_complete = true
publication_ready = false
"""
    _write_text(
        docs / "citation_reference_graph_manual_review_decision_record_v0.1.md",
        decision_record,
    )

    config = {
        "schema_version": "citation_reference_graph_manual_review_evidence_config_v1",
        "evidence": {
            "name": "citation_reference_graph_manual_review_evidence",
            "version": "v0.1",
            "status": "local_read_only_manual_review_evidence",
            "graph_version": "v0.1",
            "manual_review_support": True,
            "automated_approval": False,
            "mutates_manual_review_state": False,
            "manual_review_required": True,
            "publication_ready": False,
            "may_be_used_as_reconcile_input": False,
        },
        "inputs": {
            "manual_review_config": str(manual_config_path),
            "manual_review_report": str(reports / "citation_reference_graph_manual_review_latest.json"),
            "analytics_report": str(reports / "citation_reference_graph_analytics_latest.json"),
            "inspection_report": str(reports / "citation_reference_graph_inspection_latest.json"),
            "release_candidate_report": str(reports / "citation_reference_graph_release_candidate_latest.json"),
            "package_report": str(reports / "citation_reference_graph_package_latest.json"),
            "line_checkpoint_report": str(reports / "citation_reference_graph_line_checkpoint_latest.json"),
            "package_manifest": str(package_dir / "package_manifest.json"),
            "graph_manifest": str(graph_dir / "manifest.json"),
            "data_quality_summary": str(graph_dir / "data_quality_summary.json"),
            "graph_readme": str(graph_dir / "README.md"),
            "package_readme": str(package_dir / "README.md"),
            "known_issues_doc": str(docs / "citation_graph_known_issues_v0.1.md"),
            "source_matrix_doc": str(docs / "source_matrix.md"),
            "merge_policy_doc": str(docs / "merge_policy.md"),
            "live_smoke_report": str(reports / "citation_graph_live_smoke_latest.json"),
            "api_regression_report": str(reports / "citation_graph_api_regression_latest.json"),
            "graph_review_evidence_pack_report": str(reports / "graph_review_evidence_pack_latest.json"),
            "decision_record_doc": str(docs / "citation_reference_graph_manual_review_decision_record_v0.1.md"),
        },
        "validation": {"report_dir": str(reports), "strict_default": True},
        "category_policy": {
            "required_category_count": 18,
            "automated_support_category_ids": list(AUTOMATED_IDS),
            "human_decision_category_ids": list(HUMAN_IDS),
        },
        "expected": {
            "approval_state": "approved",
            "required_category_status_counts": {"passed": 18},
            "manual_review_complete": True,
            "manual_review_required": True,
            "publication_ready": False,
            "publication_block_reason": "publication_action_not_in_scope",
            "reference_resolution_ratio": 0.00869,
            "resolved_reference_edges_count": 6165,
            "unresolved_reference_edges_count": 703234,
            "reference_field_distribution": {
                "referenced_dois": 269355,
                "referenced_ids": 440044,
            },
            "reference_type_distribution": {
                "doi": 269355,
                "openalex_id": 440044,
            },
            "required_source_families": [
                "acl_anthology",
                "arxiv",
                "crossref",
                "openalex",
                "semantic_scholar",
            ],
        },
        "readme_required_markers": {
            "graph": [
                "local derived citation/reference graph",
                "not canonical truth",
                "not a reconcile input",
                "not a runtime graph",
                "not a public API/UI artifact",
            ],
            "package": [
                "Local package candidate",
                "not canonical truth",
                "not a reconcile input",
                "not a runtime graph",
                "not a publication-ready dataset",
                "manual_review_required",
                "publication_ready",
                "explicit canonical metadata reference fields only",
                "does not parse full text",
                "does not publish a dataset or graph",
            ],
        },
        "decision_record_required_markers": [
            "non-commercial educational and portfolio",
            "Kaggle",
            "GitHub",
            "public Radar website",
            "does not redistribute PDFs",
            "does not redistribute full text",
            "attribution",
            "publication action remains separate",
        ],
        "safety": {
            "read_only_evidence": True,
            "rebuild_graph": False,
            "rebuild_package": False,
            "mutate_manual_review_config": False,
            "mutate_manual_review_report": False,
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
            "create_latest_pointer_outside_report_dir": False,
            "create_graph_runtime": False,
            "require_networkx_runtime": False,
            "require_neo4j_runtime": False,
            "require_graphrag_runtime": False,
            "parse_full_text": False,
            "parse_pdfs": False,
            "parse_bibliography_sections": False,
            "automated_category_approval": False,
            "automated_manual_approval": False,
            "may_be_used_as_reconcile_input": False,
        },
    }
    _write_yaml(config_path, config)
    return config_path


def _read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _assert_failed(report: dict, check_name: str) -> None:
    assert report["summary"]["ok"] is False
    assert check_name in report["verdict"]["required_failed_checks"]


def test_manual_review_evidence_green_fixture(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    report = validate_manual_review_evidence(
        config_path, strict=True, write_reports=False
    )

    assert report["summary"]["ok"] is True
    assert report["summary"]["required_failed_count"] == 0
    assert report["summary"]["categories_count"] == 18
    assert report["summary"]["automated_support_categories_count"] == 13
    assert report["summary"]["human_decision_categories_count"] == 5
    assert report["summary"]["evidence_ready_categories_count"] == 18
    assert report["verdict"]["approval_state"] == "approved"
    assert report["verdict"]["manual_review_complete"] is True
    assert report["verdict"]["manual_review_decisions_recorded"] is True
    assert report["verdict"]["publication_ready"] is False
    assert all(
        row["category_status"] == "passed"
        and row["automated_decision"] is False
        and row["reviewer_decision"] == "passed"
        and row["reviewer_note"]
        for row in report["category_evidence"]
    )


def test_manual_review_evidence_writes_latest_and_history_reports(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    report_dir = tmp_path / "custom-reports"
    report = validate_manual_review_evidence(
        config_path,
        strict=True,
        write_reports=True,
        report_dir_override=report_dir,
    )

    assert report["summary"]["ok"] is True
    assert (report_dir / "citation_reference_graph_manual_review_evidence_latest.json").is_file()
    assert (report_dir / "citation_reference_graph_manual_review_evidence_latest.md").is_file()
    assert list((report_dir / "history").glob("*.json"))
    assert list((report_dir / "history").glob("*.md"))


def test_manual_review_evidence_missing_required_input_fails(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    config = _read_yaml(config_path)
    Path(config["inputs"]["analytics_report"]).unlink()

    report = validate_manual_review_evidence(
        config_path, strict=True, write_reports=False
    )

    _assert_failed(report, "required_inputs_exist_and_readable")
    _assert_failed(report, "source_reports_green")


def test_manual_review_evidence_category_policy_overlap_fails(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    config = _read_yaml(config_path)
    config["category_policy"]["human_decision_category_ids"].append(
        "known_limitations"
    )
    _write_yaml(config_path, config)

    report = validate_manual_review_evidence(
        config_path, strict=True, write_reports=False
    )

    _assert_failed(report, "category_policy_covers_manual_review_categories")
    _assert_failed(report, "category_evidence_modes_match_policy")


def test_manual_review_evidence_source_status_change_fails(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    config = _read_yaml(config_path)
    manual_path = Path(config["inputs"]["manual_review_config"])
    manual_config = _read_yaml(manual_path)
    manual_config["manual_review"]["categories"][0]["status"] = "pending"
    _write_yaml(manual_path, manual_config)

    report = validate_manual_review_evidence(
        config_path, strict=True, write_reports=False
    )

    _assert_failed(report, "source_category_statuses_match_expected")


def test_manual_review_evidence_decision_record_marker_drift_fails(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    config = _read_yaml(config_path)
    decision_record = Path(config["inputs"]["decision_record_doc"])
    decision_record.write_text("approved only\n", encoding="utf-8")

    report = validate_manual_review_evidence(
        config_path, strict=True, write_reports=False
    )

    _assert_failed(report, "decision_record_complete")


def test_manual_review_evidence_readme_marker_drift_fails(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    config = _read_yaml(config_path)
    package_readme = Path(config["inputs"]["package_readme"])
    package_readme.write_text("Local package candidate only\n", encoding="utf-8")

    report = validate_manual_review_evidence(
        config_path, strict=True, write_reports=False
    )

    _assert_failed(report, "readme_boundary_markers_present")
    _assert_failed(report, "all_category_evidence_ready")


def test_manual_review_evidence_normalization_or_checksum_failure_blocks_pack(
    tmp_path: Path,
) -> None:
    config_path = _make_fixture(tmp_path)
    config = _read_yaml(config_path)

    release_path = Path(config["inputs"]["release_candidate_report"])
    release = json.loads(release_path.read_text(encoding="utf-8"))
    release["checks"][0]["ok"] = False
    _write_json(release_path, release)

    package_path = Path(config["inputs"]["package_report"])
    package = json.loads(package_path.read_text(encoding="utf-8"))
    package["checks"][0]["ok"] = False
    _write_json(package_path, package)

    report = validate_manual_review_evidence(
        config_path, strict=True, write_reports=False
    )

    _assert_failed(report, "all_category_evidence_ready")
    evidence = {row["category_id"]: row for row in report["category_evidence"]}
    assert evidence["openalex_normalization_review"]["evidence_ready"] is False
    assert evidence["package_manifest_checksum_review"]["evidence_ready"] is False


def test_manual_review_evidence_cli_no_write_reports(tmp_path: Path) -> None:
    config_path = _make_fixture(tmp_path)
    report_dir = tmp_path / "cli-reports"

    exit_code = main(
        [
            "--config-path",
            str(config_path),
            "--report-dir",
            str(report_dir),
            "--strict",
            "--no-write-reports",
        ]
    )

    assert exit_code == 0
    assert not report_dir.exists()
