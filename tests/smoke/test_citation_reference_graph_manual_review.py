from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts.validation.check_citation_reference_graph_manual_review import (
    REQUIRED_CATEGORY_IDS,
    main as manual_review_main,
    validate_manual_review,
)


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_yaml(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(obj, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _green_line_checkpoint_report(path: Path) -> None:
    _write_json(
        path,
        {
            "schema_version": "citation_reference_graph_line_checkpoint_validation_v1",
            "summary": {
                "ok": True,
                "strict": True,
                "required_failed_count": 0,
                "warning_count": 0,
                "total_checks": 20,
            },
            "verdict": {
                "citation_reference_graph_line_complete": True,
                "line_checkpoint_ready": True,
                "manual_review_required": True,
                "manual_review_complete": False,
                "publication_ready": False,
                "publication_block_reason": "manual_review_not_completed",
                "required_failed_checks": [],
                "warning_checks": [],
            },
        },
    )


def _safe_package_manifest(path: Path) -> None:
    _write_json(
        path,
        {
            "schema_version": "citation_reference_graph_package_manifest_v1",
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
                "changes_db_schema": False,
                "changes_qdrant": False,
                "changes_retrieval": False,
                "changes_ranking": False,
                "changes_api": False,
                "changes_ui": False,
                "parses_full_text": False,
                "parses_pdfs": False,
                "parses_bibliography_sections": False,
                "requires_networkx_runtime": False,
                "requires_neo4j_runtime": False,
                "requires_graphrag_runtime": False,
                "publishes_graph": False,
                "publishes_dataset": False,
            },
        },
    )


def _green_optional_report(path: Path, schema_version: str) -> None:
    _write_json(
        path,
        {
            "schema_version": schema_version,
            "summary": {
                "ok": True,
                "required_failed_count": 0,
                "warning_count": 0,
            },
            "verdict": {},
        },
    )


def _make_config(base: Path) -> Path:
    report_dir = base / "artifacts/reports/validation"
    package_dir = base / "data/graphs/citation_reference_graph/packages/v0.1"
    config_path = base / "configs/citation_reference_graph_manual_review.yaml"

    line_report = report_dir / "citation_reference_graph_line_checkpoint_latest.json"
    package_manifest = package_dir / "package_manifest.json"

    _green_line_checkpoint_report(line_report)
    _safe_package_manifest(package_manifest)
    _green_optional_report(report_dir / "citation_reference_graph_package_latest.json", "citation_reference_graph_package_validation_v1")
    _green_optional_report(report_dir / "citation_reference_graph_release_candidate_latest.json", "citation_reference_graph_release_candidate_v1")
    _green_optional_report(report_dir / "citation_reference_graph_inspection_latest.json", "citation_reference_graph_inspection_v1")
    decision_record = base / "docs/citation_reference_graph_manual_review_decision_record_v0.1.md"
    decision_record.parent.mkdir(parents=True, exist_ok=True)
    decision_record.write_text(
        "approval_state = approved\n"
        "manual_review_complete = true\n"
        "publication_ready = false\n"
        "publication action remains separate\n",
        encoding="utf-8",
    )

    config = {
        "schema_version": "citation_reference_graph_manual_review_config_v1",
        "review": {
            "name": "citation_reference_graph_manual_review",
            "version": "v0.1",
            "status": "local_manual_review_gate",
            "graph_version": "v0.1",
            "approval_state": "not_reviewed",
            "manual_review_required": True,
            "manual_review_complete": False,
            "publication_ready": False,
            "publication_block_reason": "manual_review_not_completed",
            "may_be_used_as_reconcile_input": False,
        },
        "inputs": {
            "line_checkpoint_report": str(line_report),
            "package_manifest": str(package_manifest),
            "package_report": str(report_dir / "citation_reference_graph_package_latest.json"),
            "release_candidate_report": str(report_dir / "citation_reference_graph_release_candidate_latest.json"),
            "inspection_report": str(report_dir / "citation_reference_graph_inspection_latest.json"),
            "decision_record": str(decision_record),
        },
        "validation": {
            "report_dir": str(report_dir),
        },
        "manual_review": {
            "status_policy": {
                "pending_blocks_publication": True,
                "pending_fails_validator": False,
                "approved_does_not_publish": True,
            },
            "allowed_category_statuses": [
                "pending",
                "in_progress",
                "passed",
                "failed",
                "not_applicable",
            ],
            "required_category_ids": list(REQUIRED_CATEGORY_IDS),
            "categories": [
                {
                    "id": category_id,
                    "title": category_id.replace("_", " ").title(),
                    "required": True,
                    "status": "pending",
                    "reviewer_note": "",
                }
                for category_id in REQUIRED_CATEGORY_IDS
            ],
        },
        "expected_citation_reference_caveats": {
            "metadata_reference_fields_only": True,
            "full_text_parsed": False,
            "pdfs_parsed": False,
            "bibliography_sections_parsed": False,
            "raw_reference_strings_without_identifiers_parsed": False,
            "unresolved_references_preserved_as_external_reference_nodes": True,
            "reference_resolution_ratio": 0.00869,
        },
        "safety": {
            "read_only_manual_review": True,
            "rebuild_graph": False,
            "rebuild_package": False,
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
            "may_be_used_as_reconcile_input": False,
        },
    }
    _write_yaml(config_path, config)
    return config_path


def _load_config(config_path: Path) -> dict:
    return yaml.safe_load(config_path.read_text(encoding="utf-8"))


def _write_config(config_path: Path, config: dict) -> None:
    _write_yaml(config_path, config)


def _assert_failed(result: dict, check_name: str) -> None:
    assert result["summary"]["ok"] is False
    assert check_name in result["verdict"]["required_failed_checks"]


def test_manual_review_default_pending_passes_but_publication_blocked(tmp_path: Path) -> None:
    config_path = _make_config(tmp_path)

    result = validate_manual_review(config_path=config_path, strict=True, write_reports=False)

    assert result["summary"]["ok"] is True
    assert result["summary"]["required_failed_count"] == 0
    assert result["verdict"]["manual_review_required"] is True
    assert result["verdict"]["manual_review_complete"] is False
    assert result["verdict"]["publication_ready"] is False
    assert result["verdict"]["publication_block_reason"] == "manual_review_not_completed"
    assert result["verdict"]["pending_categories_fail_validator"] is False


def test_manual_review_fails_when_required_category_missing(tmp_path: Path) -> None:
    config_path = _make_config(tmp_path)
    config = _load_config(config_path)
    config["manual_review"]["categories"] = [
        row for row in config["manual_review"]["categories"] if row["id"] != "reference_metadata_caveats"
    ]
    _write_config(config_path, config)

    result = validate_manual_review(config_path=config_path, strict=True, write_reports=False)

    _assert_failed(result, "required_categories_present")


def test_manual_review_fails_when_duplicate_category_id(tmp_path: Path) -> None:
    config_path = _make_config(tmp_path)
    config = _load_config(config_path)
    config["manual_review"]["categories"].append(dict(config["manual_review"]["categories"][0]))
    _write_config(config_path, config)

    result = validate_manual_review(config_path=config_path, strict=True, write_reports=False)

    _assert_failed(result, "required_categories_present")


def test_manual_review_fails_when_invalid_category_status(tmp_path: Path) -> None:
    config_path = _make_config(tmp_path)
    config = _load_config(config_path)
    config["manual_review"]["categories"][0]["status"] = "todo"
    _write_config(config_path, config)

    result = validate_manual_review(config_path=config_path, strict=True, write_reports=False)

    _assert_failed(result, "category_statuses_valid")


def test_manual_review_fails_when_line_checkpoint_not_green(tmp_path: Path) -> None:
    config_path = _make_config(tmp_path)
    config = _load_config(config_path)
    line_report_path = Path(config["inputs"]["line_checkpoint_report"])
    report = json.loads(line_report_path.read_text(encoding="utf-8"))
    report["summary"]["ok"] = False
    line_report_path.write_text(json.dumps(report), encoding="utf-8")

    result = validate_manual_review(config_path=config_path, strict=True, write_reports=False)

    _assert_failed(result, "line_checkpoint_report_green")


def test_manual_review_fails_when_package_manifest_publication_ready_true(tmp_path: Path) -> None:
    config_path = _make_config(tmp_path)
    config = _load_config(config_path)
    package_manifest_path = Path(config["inputs"]["package_manifest"])
    manifest = json.loads(package_manifest_path.read_text(encoding="utf-8"))
    manifest["package"]["publication_ready"] = True
    package_manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = validate_manual_review(config_path=config_path, strict=True, write_reports=False)

    _assert_failed(result, "package_manifest_safety")


def test_manual_review_fails_when_safety_flag_allows_graph_rebuild(tmp_path: Path) -> None:
    config_path = _make_config(tmp_path)
    config = _load_config(config_path)
    config["safety"]["rebuild_graph"] = True
    _write_config(config_path, config)

    result = validate_manual_review(config_path=config_path, strict=True, write_reports=False)

    _assert_failed(result, "manual_review_safety_config")


def test_manual_review_fails_when_full_text_caveat_is_wrong(tmp_path: Path) -> None:
    config_path = _make_config(tmp_path)
    config = _load_config(config_path)
    config["expected_citation_reference_caveats"]["full_text_parsed"] = True
    _write_config(config_path, config)

    result = validate_manual_review(config_path=config_path, strict=True, write_reports=False)

    _assert_failed(result, "citation_reference_caveats")


def test_manual_review_fails_when_approved_but_required_category_pending(tmp_path: Path) -> None:
    config_path = _make_config(tmp_path)
    config = _load_config(config_path)
    config["review"]["approval_state"] = "approved"
    config["review"]["publication_block_reason"] = "publication_action_not_in_scope"
    config["review"]["reviewer_role"] = "project_owner_maintainer"
    config["review"]["reviewed_at"] = "2026-07-16"
    config["review"]["decision_record"] = config["inputs"]["decision_record"]
    _write_config(config_path, config)

    result = validate_manual_review(config_path=config_path, strict=True, write_reports=False)

    _assert_failed(result, "approved_requires_completed_categories")


def test_manual_review_approved_complete_still_does_not_publish(tmp_path: Path) -> None:
    config_path = _make_config(tmp_path)
    config = _load_config(config_path)
    config["review"]["approval_state"] = "approved"
    config["review"]["manual_review_complete"] = True
    config["review"]["publication_block_reason"] = "publication_action_not_in_scope"
    config["review"]["reviewer_role"] = "project_owner_maintainer"
    config["review"]["reviewed_at"] = "2026-07-16"
    config["review"]["decision_record"] = config["inputs"]["decision_record"]
    for category in config["manual_review"]["categories"]:
        category["status"] = "passed"
        category["reviewer_note"] = f"Human reviewer passed {category['id']}"
    _write_config(config_path, config)

    result = validate_manual_review(config_path=config_path, strict=True, write_reports=False)

    assert result["summary"]["ok"] is True
    assert result["verdict"]["manual_review_complete"] is True
    assert result["verdict"]["publication_ready"] is False
    assert result["verdict"]["publication_block_reason"] == "publication_action_not_in_scope"
    assert result["verdict"]["review_decision_recorded"] is True


def test_manual_review_approved_fails_without_reviewer_notes(tmp_path: Path) -> None:
    config_path = _make_config(tmp_path)
    config = _load_config(config_path)
    config["review"].update(
        {
            "approval_state": "approved",
            "manual_review_complete": True,
            "publication_block_reason": "publication_action_not_in_scope",
            "reviewer_role": "project_owner_maintainer",
            "reviewed_at": "2026-07-16",
            "decision_record": config["inputs"]["decision_record"],
        }
    )
    for category in config["manual_review"]["categories"]:
        category["status"] = "passed"
        category["reviewer_note"] = ""
    _write_config(config_path, config)

    result = validate_manual_review(config_path=config_path, strict=True, write_reports=False)

    _assert_failed(result, "completed_categories_have_reviewer_notes")


def test_manual_review_approved_fails_without_decision_record(tmp_path: Path) -> None:
    config_path = _make_config(tmp_path)
    config = _load_config(config_path)
    config["review"].update(
        {
            "approval_state": "approved",
            "manual_review_complete": True,
            "publication_block_reason": "publication_action_not_in_scope",
            "reviewer_role": "project_owner_maintainer",
            "reviewed_at": "2026-07-16",
            "decision_record": config["inputs"]["decision_record"],
        }
    )
    for category in config["manual_review"]["categories"]:
        category["status"] = "passed"
        category["reviewer_note"] = f"Human reviewer passed {category['id']}"
    Path(config["inputs"]["decision_record"]).unlink()
    _write_config(config_path, config)

    result = validate_manual_review(config_path=config_path, strict=True, write_reports=False)

    _assert_failed(result, "approved_review_record_complete")


def test_manual_review_cli_no_write_reports(tmp_path: Path) -> None:
    config_path = _make_config(tmp_path)

    rc = manual_review_main(["--config", str(config_path), "--strict", "--no-write-reports"])

    assert rc == 0
