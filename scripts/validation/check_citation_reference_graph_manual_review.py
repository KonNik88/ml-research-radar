"""Validate the Citation / Reference Graph manual-review checklist gate.

This validator is intentionally read-only. It checks that the manual-review
checklist for the local Citation / Reference Graph v0.1 package is structurally
valid, that the completed line checkpoint and package manifest remain safe, and
that publication is correctly blocked until manual review is completed.

Important v0.1 semantics:
- pending manual-review categories block publication;
- pending categories do not fail this validator;
- ``summary.ok`` means the manual-review gate is structurally valid and safely
  blocks publication, not that human review has been completed.

The validator does not rebuild graph output, rebuild packages, mutate canonical
truth, touch Postgres/Qdrant/retrieval/ranking/API/UI, parse full text, parse
PDFs or bibliography sections, create a runtime graph, or publish anything.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


SCHEMA_VERSION = "citation_reference_graph_manual_review_v1"
CONFIG_SCHEMA_VERSION = "citation_reference_graph_manual_review_config_v1"
DEFAULT_CONFIG_PATH = Path("configs/citation_reference_graph_manual_review.yaml")
DEFAULT_REPORT_DIR = Path("artifacts/reports/validation")

VALID_APPROVAL_STATES = {
    "not_reviewed",
    "in_progress",
    "approved",
    "rejected",
}

VALID_CATEGORY_STATUSES = {
    "pending",
    "in_progress",
    "passed",
    "failed",
    "not_applicable",
}

COMPLETED_CATEGORY_STATUSES = {
    "passed",
    "not_applicable",
}

REQUIRED_CATEGORY_IDS = [
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

SAFETY_EXPECTED = {
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
}

PACKAGE_BOUNDARY_EXPECTED = {
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
}

CITATION_CAVEATS_EXPECTED = {
    "metadata_reference_fields_only": True,
    "full_text_parsed": False,
    "pdfs_parsed": False,
    "bibliography_sections_parsed": False,
    "raw_reference_strings_without_identifiers_parsed": False,
    "unresolved_references_preserved_as_external_reference_nodes": True,
    "reference_resolution_ratio": 0.00869,
}


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    required: bool
    message: str
    details: dict[str, Any] | None = None

    @property
    def status(self) -> str:
        if self.ok:
            return "passed"
        if self.required:
            return "failed"
        return "warning"


def utc_now_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def resolve_path(raw: Any) -> Path:
    path = Path(str(raw))
    if path.is_absolute():
        return path
    return Path.cwd() / path


def load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"YAML root must be a mapping: {path}")
    return payload


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return payload


def make_check(name: str, ok: bool, required: bool, message: str, details: dict[str, Any] | None = None) -> CheckResult:
    return CheckResult(name=name, ok=bool(ok), required=required, message=message, details=details)


def as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def category_rows(config: dict[str, Any]) -> list[dict[str, Any]]:
    manual = as_mapping(config.get("manual_review"))
    rows = as_list(manual.get("categories"))
    return [row for row in rows if isinstance(row, dict)]


def category_status_counts(categories: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for category in categories:
        status = str(category.get("status") or "<missing>")
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def required_categories_complete(categories: list[dict[str, Any]]) -> bool:
    for category in categories:
        if category.get("required") is not True:
            continue
        if category.get("status") not in COMPLETED_CATEGORY_STATUSES:
            return False
    return True


def manual_review_complete_from_state(config: dict[str, Any]) -> bool:
    review = as_mapping(config.get("review"))
    if review.get("approval_state") != "approved":
        return False
    return required_categories_complete(category_rows(config))


def expected_publication_block_reason(config: dict[str, Any]) -> str:
    review = as_mapping(config.get("review"))
    approval_state = review.get("approval_state")
    complete = manual_review_complete_from_state(config)

    if approval_state == "rejected":
        return "manual_review_rejected"
    if complete:
        # v0.1 validates the manual-review gate only. Publication is deliberately
        # a separate future action/slice even if the checklist is approved.
        return "publication_action_not_in_scope"
    return "manual_review_not_completed"


def line_checkpoint_report_green(path: Path) -> tuple[bool, dict[str, Any]]:
    if not path.exists():
        return False, {"path": normalize_path(path), "exists": False}
    try:
        report = load_json(path)
    except Exception as exc:  # noqa: BLE001
        return False, {"path": normalize_path(path), "exists": True, "read_error": str(exc)}

    summary = as_mapping(report.get("summary"))
    verdict = as_mapping(report.get("verdict"))
    ok = (
        summary.get("ok") is True
        and summary.get("required_failed_count") == 0
        and verdict.get("citation_reference_graph_line_complete") is True
        and verdict.get("line_checkpoint_ready") is True
        and verdict.get("manual_review_required") is True
        and verdict.get("manual_review_complete") is False
        and verdict.get("publication_ready") is False
    )
    return ok, {
        "path": normalize_path(path),
        "exists": True,
        "schema_version": report.get("schema_version"),
        "summary_ok": summary.get("ok"),
        "required_failed_count": summary.get("required_failed_count"),
        "warning_count": summary.get("warning_count"),
        "citation_reference_graph_line_complete": verdict.get("citation_reference_graph_line_complete"),
        "line_checkpoint_ready": verdict.get("line_checkpoint_ready"),
        "manual_review_required": verdict.get("manual_review_required"),
        "manual_review_complete": verdict.get("manual_review_complete"),
        "publication_ready": verdict.get("publication_ready"),
        "publication_block_reason": verdict.get("publication_block_reason"),
    }


def optional_report_green(path: Path) -> tuple[bool, dict[str, Any]]:
    if not path.exists():
        return True, {"path": normalize_path(path), "exists": False, "skipped": True}
    try:
        report = load_json(path)
    except Exception as exc:  # noqa: BLE001
        return False, {"path": normalize_path(path), "exists": True, "read_error": str(exc)}
    summary = as_mapping(report.get("summary"))
    ok = summary.get("ok") is True and summary.get("required_failed_count") == 0
    return ok, {
        "path": normalize_path(path),
        "exists": True,
        "schema_version": report.get("schema_version"),
        "summary_ok": summary.get("ok"),
        "required_failed_count": summary.get("required_failed_count"),
        "warning_count": summary.get("warning_count"),
    }


def package_manifest_safety(path: Path) -> tuple[bool, dict[str, Any]]:
    if not path.exists():
        return False, {"path": normalize_path(path), "exists": False}
    try:
        manifest = load_json(path)
    except Exception as exc:  # noqa: BLE001
        return False, {"path": normalize_path(path), "exists": True, "read_error": str(exc)}

    package = as_mapping(manifest.get("package"))
    boundaries = as_mapping(manifest.get("boundaries"))

    package_flags = {
        "publication_ready": package.get("publication_ready"),
        "manual_review_required": package.get("manual_review_required"),
        "may_be_used_as_reconcile_input": package.get("may_be_used_as_reconcile_input"),
    }
    package_ok = (
        package_flags["publication_ready"] is False
        and package_flags["manual_review_required"] is True
        and package_flags["may_be_used_as_reconcile_input"] is False
    )
    boundary_mismatches = {
        key: {"expected": expected, "actual": boundaries.get(key)}
        for key, expected in PACKAGE_BOUNDARY_EXPECTED.items()
        if boundaries.get(key) is not expected
    }
    ok = manifest.get("schema_version") == "citation_reference_graph_package_manifest_v1" and package_ok and not boundary_mismatches
    return ok, {
        "path": normalize_path(path),
        "exists": True,
        "schema_version": manifest.get("schema_version"),
        "package_flags": package_flags,
        "boundary_mismatches": boundary_mismatches,
    }


def validate_manual_review(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    report_dir: Path | None = None,
    strict: bool = False,
    write_reports: bool = True,
) -> dict[str, Any]:
    checks: list[CheckResult] = []
    config = load_yaml(config_path)

    checks.append(make_check(
        "config_schema",
        config.get("schema_version") == CONFIG_SCHEMA_VERSION,
        True,
        "Manual-review config schema is correct"
        if config.get("schema_version") == CONFIG_SCHEMA_VERSION
        else "Manual-review config schema is incorrect",
        {"schema_version": config.get("schema_version")},
    ))

    review = as_mapping(config.get("review"))
    inputs = as_mapping(config.get("inputs"))
    manual = as_mapping(config.get("manual_review"))
    safety = as_mapping(config.get("safety"))
    citation_caveats = as_mapping(config.get("expected_citation_reference_caveats"))
    categories = category_rows(config)

    report_dir = report_dir or resolve_path(as_mapping(config.get("validation")).get("report_dir", DEFAULT_REPORT_DIR))

    review_expected = {
        "name": "citation_reference_graph_manual_review",
        "version": "v0.1",
        "status": "local_manual_review_gate",
        "graph_version": "v0.1",
        "manual_review_required": True,
        "publication_ready": False,
        "may_be_used_as_reconcile_input": False,
    }
    review_mismatches: dict[str, dict[str, Any]] = {}
    for key, expected in review_expected.items():
        actual = review.get(key)
        matches = actual is expected if isinstance(expected, bool) else actual == expected
        if not matches:
            review_mismatches[key] = {"expected": expected, "actual": actual}
    checks.append(make_check(
        "review_metadata",
        not review_mismatches,
        True,
        "Review metadata preserves manual-review gate boundaries" if not review_mismatches else "Review metadata is inconsistent",
        {"mismatches": review_mismatches},
    ))

    approval_state = review.get("approval_state")
    checks.append(make_check(
        "approval_state_valid",
        approval_state in VALID_APPROVAL_STATES,
        True,
        "Approval state is valid" if approval_state in VALID_APPROVAL_STATES else "Approval state is invalid",
        {"approval_state": approval_state, "valid_states": sorted(VALID_APPROVAL_STATES)},
    ))

    configured_allowed_statuses = set(str(value) for value in as_list(manual.get("allowed_category_statuses")))
    allowed_statuses_ok = configured_allowed_statuses == VALID_CATEGORY_STATUSES
    checks.append(make_check(
        "allowed_category_statuses",
        allowed_statuses_ok,
        True,
        "Allowed category statuses match v0.1 policy" if allowed_statuses_ok else "Allowed category statuses do not match v0.1 policy",
        {"expected": sorted(VALID_CATEGORY_STATUSES), "actual": sorted(configured_allowed_statuses)},
    ))

    required_ids_from_config = [str(value) for value in as_list(manual.get("required_category_ids"))]
    required_ids_ok = required_ids_from_config == REQUIRED_CATEGORY_IDS
    checks.append(make_check(
        "required_category_ids",
        required_ids_ok,
        True,
        "Required category IDs match v0.1 policy" if required_ids_ok else "Required category IDs do not match v0.1 policy",
        {"expected": REQUIRED_CATEGORY_IDS, "actual": required_ids_from_config},
    ))

    category_ids = [str(category.get("id")) for category in categories if category.get("id")]
    duplicate_category_ids = sorted({item for item in category_ids if category_ids.count(item) > 1})
    missing_category_ids = [item for item in REQUIRED_CATEGORY_IDS if item not in set(category_ids)]
    checks.append(make_check(
        "required_categories_present",
        not missing_category_ids and not duplicate_category_ids,
        True,
        "Required manual-review categories are present" if not missing_category_ids and not duplicate_category_ids else "Required manual-review categories are missing or duplicated",
        {"missing_category_ids": missing_category_ids, "duplicate_category_ids": duplicate_category_ids},
    ))

    invalid_category_statuses = {
        str(category.get("id")): category.get("status")
        for category in categories
        if category.get("status") not in VALID_CATEGORY_STATUSES
    }
    checks.append(make_check(
        "category_statuses_valid",
        not invalid_category_statuses,
        True,
        "Category statuses are valid" if not invalid_category_statuses else "Invalid category statuses found",
        {"invalid_statuses": invalid_category_statuses, "valid_statuses": sorted(VALID_CATEGORY_STATUSES)},
    ))

    required_flag_errors = {
        str(category.get("id")): category.get("required")
        for category in categories
        if category.get("id") in REQUIRED_CATEGORY_IDS and category.get("required") is not True
    }
    checks.append(make_check(
        "required_category_flags",
        not required_flag_errors,
        True,
        "Required category flags are correct" if not required_flag_errors else "Required category flags are incorrect",
        {"required_flag_errors": required_flag_errors},
    ))

    completed_category_note_errors = {
        str(category.get("id")): category.get("reviewer_note")
        for category in categories
        if category.get("required") is True
        and category.get("status") in COMPLETED_CATEGORY_STATUSES
        and not str(category.get("reviewer_note") or "").strip()
    }
    checks.append(make_check(
        "completed_categories_have_reviewer_notes",
        not completed_category_note_errors,
        True,
        "Completed categories have explicit human reviewer rationale"
        if not completed_category_note_errors
        else "Completed categories are missing human reviewer rationale",
        {"missing_reviewer_notes": completed_category_note_errors},
    ))

    derived_complete = manual_review_complete_from_state(config)
    configured_complete = review.get("manual_review_complete")
    complete_consistent = configured_complete is None or configured_complete is derived_complete
    checks.append(make_check(
        "manual_review_complete_consistent",
        complete_consistent,
        True,
        "Manual-review completion flag is consistent" if complete_consistent else "Manual-review completion flag is inconsistent",
        {"configured": configured_complete, "derived": derived_complete},
    ))

    approved_with_incomplete_categories = approval_state == "approved" and not required_categories_complete(categories)
    checks.append(make_check(
        "approved_requires_completed_categories",
        not approved_with_incomplete_categories,
        True,
        "Approved state is consistent with completed required categories"
        if not approved_with_incomplete_categories
        else "Approved state is inconsistent with pending/failed required categories",
        {
            "approval_state": approval_state,
            "required_categories_complete": required_categories_complete(categories),
            "category_status_counts": category_status_counts(categories),
        },
    ))

    decision_record_raw = inputs.get("decision_record") or review.get("decision_record")
    decision_record_path = resolve_path(decision_record_raw) if decision_record_raw else None
    reviewed_at = review.get("reviewed_at")
    reviewed_at_valid = False
    if reviewed_at:
        try:
            datetime.fromisoformat(str(reviewed_at).replace("Z", "+00:00"))
            reviewed_at_valid = True
        except ValueError:
            reviewed_at_valid = False
    decision_record_markers_missing: list[str] = []
    if decision_record_path and decision_record_path.exists():
        decision_text = decision_record_path.read_text(encoding="utf-8").lower()
        for marker in (
            "approval_state = approved",
            "manual_review_complete = true",
            "publication_ready = false",
            "publication action remains separate",
        ):
            if marker.lower() not in decision_text:
                decision_record_markers_missing.append(marker)
    approved_review_record_ok = (
        approval_state != "approved"
        or (
            bool(str(review.get("reviewer_role") or "").strip())
            and reviewed_at_valid
            and decision_record_path is not None
            and decision_record_path.exists()
            and not decision_record_markers_missing
        )
    )
    checks.append(make_check(
        "approved_review_record_complete",
        approved_review_record_ok,
        True,
        "Approved review has reviewer metadata and a complete decision record"
        if approved_review_record_ok
        else "Approved review is missing reviewer metadata or a complete decision record",
        {
            "approval_state": approval_state,
            "reviewer_role": review.get("reviewer_role"),
            "reviewed_at": reviewed_at,
            "reviewed_at_valid": reviewed_at_valid,
            "decision_record": normalize_path(decision_record_path),
            "decision_record_exists": bool(decision_record_path and decision_record_path.exists()),
            "decision_record_markers_missing": decision_record_markers_missing,
        },
    ))

    expected_block_reason = expected_publication_block_reason(config)
    configured_block_reason = review.get("publication_block_reason")
    publication_block_ok = configured_block_reason == expected_block_reason and review.get("publication_ready") is False
    checks.append(make_check(
        "publication_block_consistent",
        publication_block_ok,
        True,
        "Publication is correctly blocked" if publication_block_ok else "Publication block reason is inconsistent",
        {
            "publication_ready": review.get("publication_ready"),
            "configured_publication_block_reason": configured_block_reason,
            "expected_publication_block_reason": expected_block_reason,
        },
    ))

    status_policy = as_mapping(manual.get("status_policy"))
    status_policy_expected = {
        "pending_blocks_publication": True,
        "pending_fails_validator": False,
        "approved_does_not_publish": True,
    }
    status_policy_mismatches = {
        key: {"expected": expected, "actual": status_policy.get(key)}
        for key, expected in status_policy_expected.items()
        if status_policy.get(key) is not expected
    }
    checks.append(make_check(
        "status_policy",
        not status_policy_mismatches,
        True,
        "Manual-review status policy matches v0.1 semantics" if not status_policy_mismatches else "Manual-review status policy is inconsistent",
        {"mismatches": status_policy_mismatches},
    ))

    caveat_mismatches = {}
    for key, expected in CITATION_CAVEATS_EXPECTED.items():
        actual = citation_caveats.get(key)
        if isinstance(expected, float):
            matches = actual is not None and abs(float(actual) - expected) < 1e-12
        else:
            matches = actual is expected
        if not matches:
            caveat_mismatches[key] = {"expected": expected, "actual": actual}
    checks.append(make_check(
        "citation_reference_caveats",
        not caveat_mismatches,
        True,
        "Citation/reference caveats match v0.1 review policy" if not caveat_mismatches else "Citation/reference caveats are incomplete or inconsistent",
        {"mismatches": caveat_mismatches},
    ))

    for input_key in ["line_checkpoint_report", "package_manifest"]:
        checks.append(make_check(
            f"{input_key}_configured",
            bool(inputs.get(input_key)),
            True,
            f"{input_key} is configured" if inputs.get(input_key) else f"{input_key} is missing from inputs",
        ))

    if inputs.get("line_checkpoint_report"):
        path = resolve_path(inputs["line_checkpoint_report"])
        ok, details = line_checkpoint_report_green(path)
        checks.append(make_check(
            "line_checkpoint_report_green",
            ok,
            True,
            "Line checkpoint report is green and publication-blocked" if ok else "Line checkpoint report is not green or not publication-blocked",
            details,
        ))

    if inputs.get("package_manifest"):
        path = resolve_path(inputs["package_manifest"])
        ok, details = package_manifest_safety(path)
        checks.append(make_check(
            "package_manifest_safety",
            ok,
            True,
            "Package manifest safety flags preserve local candidate boundaries" if ok else "Package manifest safety flags are unsafe or unreadable",
            details,
        ))

    for input_key, check_name in [
        ("package_report", "package_report_diagnostic_green"),
        ("release_candidate_report", "release_candidate_report_diagnostic_green"),
        ("inspection_report", "inspection_report_diagnostic_green"),
    ]:
        if not inputs.get(input_key):
            continue
        path = resolve_path(inputs[input_key])
        if not path.exists():
            continue
        ok, details = optional_report_green(path)
        checks.append(make_check(
            check_name,
            ok,
            False,
            f"{input_key} is green" if ok else f"{input_key} is not green",
            details,
        ))

    safety_mismatches = {
        key: {"expected": expected, "actual": safety.get(key)}
        for key, expected in SAFETY_EXPECTED.items()
        if safety.get(key) is not expected
    }
    checks.append(make_check(
        "manual_review_safety_config",
        not safety_mismatches,
        True,
        "Manual-review safety flags preserve project boundaries" if not safety_mismatches else "Manual-review safety flags do not preserve project boundaries",
        {"mismatches": safety_mismatches},
    ))

    required_failed = [check for check in checks if check.required and not check.ok]
    warnings = [check for check in checks if not check.required and not check.ok]
    ok = not required_failed

    result = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config_path": normalize_path(config_path),
        "summary": {
            "ok": ok,
            "strict": strict,
            "required_failed_count": len(required_failed),
            "warning_count": len(warnings),
            "total_checks": len(checks),
        },
        "manual_review": {
            "approval_state": approval_state,
            "manual_review_required": True,
            "manual_review_complete": derived_complete,
            "category_status_counts": category_status_counts(categories),
            "required_category_count": len(REQUIRED_CATEGORY_IDS),
            "reviewer_role": review.get("reviewer_role"),
            "reviewed_at": review.get("reviewed_at"),
            "decision_record": normalize_path(decision_record_path),
            "citation_reference_caveats": citation_caveats,
        },
        "checks": [
            {
                "name": check.name,
                "status": check.status,
                "ok": check.ok,
                "required": check.required,
                "message": check.message,
                "details": check.details or {},
            }
            for check in checks
        ],
        "verdict": {
            "manual_review_gate_valid": ok,
            "manual_review_required": True,
            "manual_review_complete": derived_complete,
            "publication_ready": False,
            "publication_block_reason": expected_block_reason,
            "pending_categories_block_publication": True,
            "pending_categories_fail_validator": False,
            "publication_action_in_scope": False,
            "review_decision_recorded": approval_state == "approved" and derived_complete,
            "required_failed_checks": [check.name for check in required_failed],
            "warning_checks": [check.name for check in warnings],
        },
        "boundaries": {
            "read_only_validator": True,
            "manual_review_gate_only": True,
            "derived_graph_only": True,
            "rebuilds_graph": False,
            "rebuilds_package": False,
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
    }

    if write_reports:
        write_validation_reports(result, report_dir)

    return result


def render_markdown(result: dict[str, Any]) -> str:
    summary = result["summary"]
    verdict = result["verdict"]
    manual = result["manual_review"]
    lines = [
        "# Citation / Reference Graph Manual Review Checklist",
        "",
        f"- schema_version: `{result['schema_version']}`",
        f"- generated_at: `{result['generated_at']}`",
        f"- config_path: `{result['config_path']}`",
        f"- ok: `{summary['ok']}`",
        f"- strict: `{summary['strict']}`",
        f"- required_failed_count: `{summary['required_failed_count']}`",
        f"- warning_count: `{summary['warning_count']}`",
        "",
        "## Verdict",
        "",
        f"- manual_review_gate_valid: `{verdict['manual_review_gate_valid']}`",
        f"- manual_review_required: `{verdict['manual_review_required']}`",
        f"- manual_review_complete: `{verdict['manual_review_complete']}`",
        f"- publication_ready: `{verdict['publication_ready']}`",
        f"- publication_block_reason: `{verdict['publication_block_reason']}`",
        f"- pending_categories_block_publication: `{verdict['pending_categories_block_publication']}`",
        f"- pending_categories_fail_validator: `{verdict['pending_categories_fail_validator']}`",
        "",
        "## Manual review",
        "",
        f"- approval_state: `{manual['approval_state']}`",
        f"- required_category_count: `{manual['required_category_count']}`",
        "- category_status_counts:",
    ]
    for key, value in manual.get("category_status_counts", {}).items():
        lines.append(f"  - {key}: `{value}`")
    caveats = manual.get("citation_reference_caveats", {})
    if caveats:
        lines.extend(["", "## Citation/reference caveats", ""])
        for key, value in caveats.items():
            lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Checks", "", "| Check | Required | Status | Message |", "|---|---:|---|---|"])
    for check in result["checks"]:
        message = str(check["message"]).replace("|", "\\|")
        lines.append(f"| `{check['name']}` | `{check['required']}` | `{check['status']}` | {message} |")
    lines.extend(["", "## Boundaries", ""])
    for key, value in result["boundaries"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    return "\n".join(lines)


def write_validation_reports(result: dict[str, Any], report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    history_dir = report_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    run_ts = utc_now_compact()
    latest_json = report_dir / "citation_reference_graph_manual_review_latest.json"
    latest_md = report_dir / "citation_reference_graph_manual_review_latest.md"
    history_json = history_dir / f"citation_reference_graph_manual_review_{run_ts}.json"
    history_md = history_dir / f"citation_reference_graph_manual_review_{run_ts}.md"
    json_text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    md_text = render_markdown(result)
    latest_json.write_text(json_text, encoding="utf-8")
    latest_md.write_text(md_text, encoding="utf-8")
    history_json.write_text(json_text, encoding="utf-8")
    history_md.write_text(md_text, encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate the Citation / Reference Graph manual-review checklist gate.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--report-dir", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--no-write-reports", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = validate_manual_review(
        config_path=args.config,
        report_dir=args.report_dir,
        strict=args.strict,
        write_reports=not args.no_write_reports,
    )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2, sort_keys=True))
    if not result["summary"]["ok"]:
        print("required_failed_checks:", ", ".join(result["verdict"]["required_failed_checks"]))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
