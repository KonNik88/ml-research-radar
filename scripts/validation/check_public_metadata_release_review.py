"""Validate the manual public-metadata release review gate.

This validator checks structure, safety boundaries, pending/approved/rejected state
consistency, and the green technical inputs needed for a human release decision.
It never approves categories, never publishes a dataset, and never mutates the
release package or canonical truth.

Important semantics:
- category outcomes are human-owned configuration, never inferred by this validator;
- approved manual review still does not publish the dataset;
- report ok=true means the recorded decision is structurally valid and its inputs are green;
- publication remains a separate explicit action.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml


CONFIG_SCHEMA_VERSION = "public_metadata_release_review_config_v1"
REPORT_SCHEMA_VERSION = "public_metadata_release_review_v1"
DEFAULT_CONFIG_PATH = Path("configs/public_metadata_release_review.yaml")
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/validation")
REPORT_BASENAME = "public_metadata_release_review"

CATEGORY_IDS = [
    "release_identity_checkpoint",
    "canonical_truth_boundary",
    "selected_field_policy_coverage",
    "abstract_source_aware_handling",
    "bibliographic_metadata_contract",
    "external_identifiers_and_links",
    "taxonomy_and_counts_contract",
    "excluded_content_boundary",
    "source_attribution_coverage",
    "arxiv_policy_evidence",
    "openalex_policy_evidence",
    "crossref_policy_evidence",
    "semantic_scholar_policy_evidence",
    "acl_anthology_policy_evidence",
    "package_manifest_checksums_kaggle_template",
    "compilation_license_decision",
    "provider_terms_review",
    "dataset_card_and_attribution_wording",
    "publication_target_decision",
    "manual_release_approval_state",
]

EXPECTED_REVIEW_METADATA = {
    "name": "public_metadata_release_review",
    "version": "v0.1",
    "status": "local_manual_release_review_gate",
    "dataset_name": "ml_research_radar_metadata",
    "dataset_version": "v0.1",
    "approval_state": "rejected",
    "manual_review_required": True,
    "manual_review_complete": True,
    "publication_ready": False,
    "publication_block_reason": "manual_release_rejected",
    "publication_action_in_scope": False,
    "may_be_used_as_reconcile_input": False,
    "reviewer_role": "project_owner_maintainer",
    "reviewed_at": "2026-07-17",
    "decision_record": "docs/public_metadata_release_review_decision_v0.1.md",
    "publication_purpose": "non_commercial_educational_portfolio",
    "compilation_license_decision": "not_selected_due_semantic_scholar_redistribution_blocker",
    "kaggle_license_name": "other_template_only",
    "primary_publication_target": "kaggle_dataset_after_remediation",
    "publication_targets": ["kaggle_dataset_after_remediation", "github_release_after_remediation"],
    "deferred_publication_targets": ["huggingface_datasets"],
    "attribution_required": True,
    "remediation_required": True,
    "blocking_source_family": "semantic_scholar",
    "redistributes_pdfs": False,
    "redistributes_full_text": False,
}

EXPECTED_SAFETY = {
    "read_only_review_gate": True,
    "rebuild_dataset": False,
    "mutate_release_package": False,
    "mutate_canonical_documents": False,
    "mutate_retrieval_artifacts": False,
    "mutate_qdrant": False,
    "mutate_postgres": False,
    "mutate_db_schema": False,
    "mutate_api": False,
    "mutate_ui": False,
    "mutate_ranking": False,
    "publish_dataset": False,
    "call_kaggle_api": False,
    "call_huggingface_api": False,
    "create_github_release": False,
    "automated_category_approval": False,
    "automated_manual_approval": False,
    "may_be_used_as_reconcile_input": False,
}

REQUIRED_INPUT_KEYS = {
    "dataset_release_config",
    "public_release_policy",
    "review_readiness_report",
    "policy_validation_report",
    "output_validation_report",
    "release_manifest",
    "data_quality_summary",
    "dataset_card",
    "attribution",
    "kaggle_metadata_template",
    "decision_record",
}

DECISION_RECORD_MARKERS = [
    "approval_state: rejected",
    "category_status_counts: passed = 15, failed = 5",
    "Semantic Scholar",
    "downloadable Kaggle dataset",
    "written permission",
    "exclude Semantic Scholar-derived data",
    "publication action remains separate",
]

ALLOWED_CATEGORY_STATUSES = {"pending", "passed", "failed"}
ALLOWED_APPROVAL_STATES = {"not_reviewed", "approved", "rejected"}


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    severity: str
    message: str
    details: dict[str, Any] | None = None


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def add_check(
    checks: list[CheckResult],
    *,
    name: str,
    ok: bool,
    message: str,
    severity: str = "required",
    details: dict[str, Any] | None = None,
) -> None:
    checks.append(CheckResult(name, bool(ok), severity, message, details))


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: Mapping[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


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


def resolve_path(raw: Any, *, config_path: Path) -> Path:
    path = Path(str(raw))
    if path.is_absolute():
        return path
    repo_root = config_path.parent.parent
    return (repo_root / path).resolve()


def read_json_if_exists(path: Path) -> tuple[dict[str, Any], bool, str | None]:
    if not path.exists():
        return {}, False, "file does not exist"
    try:
        return load_json(path), True, None
    except Exception as exc:  # pragma: no cover - defensive report detail
        return {}, False, str(exc)


def read_text_if_exists(path: Path) -> tuple[str, bool, str | None]:
    if not path.exists():
        return "", False, "file does not exist"
    try:
        return path.read_text(encoding="utf-8"), True, None
    except Exception as exc:  # pragma: no cover
        return "", False, str(exc)


def categories_from_config(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    manual = as_mapping(config.get("manual_review"))
    return [as_mapping(item) for item in as_list(manual.get("categories"))]


def status_counts(categories: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(str(category.get("status") or "missing") for category in categories)
    return dict(sorted(counts.items()))


def validate_review(
    config: Mapping[str, Any],
    *,
    config_path: Path,
    check_paths: bool = True,
) -> list[CheckResult]:
    checks: list[CheckResult] = []

    add_check(
        checks,
        name="schema_version",
        ok=config.get("schema_version") == CONFIG_SCHEMA_VERSION,
        message=f"schema_version is {CONFIG_SCHEMA_VERSION}",
        details={"actual": config.get("schema_version")},
    )

    review = as_mapping(config.get("review"))
    for key, expected in EXPECTED_REVIEW_METADATA.items():
        add_check(
            checks,
            name=f"review_{key}",
            ok=review.get(key) == expected,
            message=f"review.{key} matches the approved review-execution state",
            details={"expected": expected, "actual": review.get(key)},
        )

    safety = as_mapping(config.get("safety"))
    for key, expected in EXPECTED_SAFETY.items():
        add_check(
            checks,
            name=f"safety_{key}",
            ok=safety.get(key) == expected,
            message=f"safety.{key} preserves the read-only non-publishing boundary",
            details={"expected": expected, "actual": safety.get(key)},
        )

    validation = as_mapping(config.get("validation"))
    add_check(
        checks,
        name="pending_categories_do_not_fail_validator",
        ok=validation.get("pending_categories_fail_validator") is False,
        message="pending categories do not fail structural validation",
        details={"actual": validation.get("pending_categories_fail_validator")},
    )
    add_check(
        checks,
        name="pending_categories_block_publication",
        ok=validation.get("pending_categories_block_publication") is True,
        message="pending categories explicitly block publication",
        details={"actual": validation.get("pending_categories_block_publication")},
    )

    manual = as_mapping(config.get("manual_review"))
    required_ids = [str(item) for item in as_list(manual.get("required_category_ids"))]
    categories = categories_from_config(config)
    category_ids = [str(item.get("id") or "") for item in categories]

    add_check(
        checks,
        name="required_category_ids",
        ok=required_ids == CATEGORY_IDS,
        message="required category IDs match the deterministic 20-category contract",
        details={"expected": CATEGORY_IDS, "actual": required_ids},
    )
    add_check(
        checks,
        name="category_count",
        ok=len(categories) == len(CATEGORY_IDS),
        message="manual review contains exactly 20 categories",
        details={"expected": len(CATEGORY_IDS), "actual": len(categories)},
    )
    add_check(
        checks,
        name="category_ids_unique",
        ok=len(category_ids) == len(set(category_ids)),
        message="manual-review category IDs are unique",
        details={"category_ids": category_ids},
    )
    add_check(
        checks,
        name="categories_cover_required_ids",
        ok=category_ids == CATEGORY_IDS,
        message="categories cover required IDs in deterministic order",
        details={"expected": CATEGORY_IDS, "actual": category_ids},
    )

    invalid_statuses = {
        str(item.get("id") or ""): item.get("status")
        for item in categories
        if item.get("status") not in ALLOWED_CATEGORY_STATUSES
    }
    add_check(
        checks,
        name="category_status_values",
        ok=not invalid_statuses,
        message="category statuses are pending, passed, or failed",
        details={"invalid": invalid_statuses},
    )

    non_required = [str(item.get("id") or "") for item in categories if item.get("required") is not True]
    missing_titles = [str(item.get("id") or "") for item in categories if not str(item.get("title") or "").strip()]
    missing_notes = [str(item.get("id") or "") for item in categories if not str(item.get("reviewer_note") or "").strip()]
    add_check(
        checks,
        name="all_categories_required",
        ok=not non_required,
        message="all 20 categories are required",
        details={"not_required": non_required},
    )
    add_check(
        checks,
        name="category_titles_present",
        ok=not missing_titles,
        message="all categories have human-readable titles",
        details={"missing": missing_titles},
    )
    add_check(
        checks,
        name="reviewer_notes_present",
        ok=not missing_notes,
        message="all categories contain review guidance",
        details={"missing": missing_notes},
    )

    approval_state = review.get("approval_state")
    add_check(
        checks,
        name="approval_state_allowed",
        ok=approval_state in ALLOWED_APPROVAL_STATES,
        message="approval_state is one of not_reviewed, approved, or rejected",
        details={"actual": approval_state},
    )

    counts = status_counts(categories)
    all_pending = counts.get("pending", 0) == len(CATEGORY_IDS)
    all_passed = counts.get("passed", 0) == len(CATEGORY_IDS)
    any_failed = counts.get("failed", 0) > 0
    state_consistent = (
        (
            approval_state == "not_reviewed"
            and all_pending
            and review.get("manual_review_complete") is False
            and review.get("publication_ready") is False
            and review.get("publication_block_reason") == "public_release_decision_not_completed"
        )
        or (
            approval_state == "approved"
            and all_passed
            and review.get("manual_review_complete") is True
            and review.get("publication_ready") is False
            and review.get("publication_block_reason") == "publication_action_not_in_scope"
        )
        or (
            approval_state == "rejected"
            and any_failed
            and counts.get("pending", 0) == 0
            and counts.get("passed", 0) + counts.get("failed", 0) == len(CATEGORY_IDS)
            and review.get("manual_review_complete") is True
            and review.get("publication_ready") is False
            and review.get("publication_block_reason") == "manual_release_rejected"
        )
    )
    add_check(
        checks,
        name="review_state_consistency",
        ok=state_consistent,
        message="approval state, category statuses, completion, and publication block reason are consistent",
        details={
            "approval_state": approval_state,
            "category_status_counts": counts,
            "manual_review_complete": review.get("manual_review_complete"),
            "publication_ready": review.get("publication_ready"),
            "publication_block_reason": review.get("publication_block_reason"),
        },
    )

    inputs = as_mapping(config.get("inputs"))
    missing_input_keys = sorted(REQUIRED_INPUT_KEYS - set(inputs))
    add_check(
        checks,
        name="required_input_keys",
        ok=not missing_input_keys,
        message="all manual-review input paths are configured",
        details={"missing": missing_input_keys},
    )

    resolved: dict[str, Path] = {}
    for key in sorted(REQUIRED_INPUT_KEYS & set(inputs)):
        path = resolve_path(inputs[key], config_path=config_path)
        resolved[key] = path
        if check_paths:
            add_check(
                checks,
                name=f"input_{key}_exists",
                ok=path.exists(),
                message=f"configured input exists: {key}",
                details={"path": normalize_path(path)},
            )

    if not check_paths:
        return checks

    dataset_config, dataset_config_ok, dataset_config_error = ({}, False, "file does not exist")
    if resolved["dataset_release_config"].exists():
        try:
            dataset_config = load_yaml(resolved["dataset_release_config"])
            dataset_config_ok = True
            dataset_config_error = None
        except Exception as exc:  # pragma: no cover
            dataset_config = {}
            dataset_config_ok = False
            dataset_config_error = str(exc)
    add_check(
        checks,
        name="dataset_release_config_readable",
        ok=dataset_config_ok,
        message="dataset release config is readable",
        details={"error": dataset_config_error},
    )

    readiness, readiness_ok, readiness_error = read_json_if_exists(resolved["review_readiness_report"])
    add_check(
        checks,
        name="review_readiness_report_readable",
        ok=readiness_ok,
        message="dataset release review-readiness report is readable",
        details={"error": readiness_error},
    )
    if readiness:
        add_check(
            checks,
            name="review_readiness_report_green",
            ok=(
                readiness.get("schema_version") == "dataset_release_review_readiness_v2"
                and readiness.get("ok") is True
                and readiness.get("technical_candidate_ready") is True
                and readiness.get("public_policy_ready") is True
                and readiness.get("manual_release_decision_required") is True
                and readiness.get("publication_ready") is False
                and readiness.get("required_failed_count") == 0
            ),
            message="technical and policy readiness are green while publication remains blocked",
            details={
                "schema_version": readiness.get("schema_version"),
                "ok": readiness.get("ok"),
                "technical_candidate_ready": readiness.get("technical_candidate_ready"),
                "public_policy_ready": readiness.get("public_policy_ready"),
                "manual_release_decision_required": readiness.get("manual_release_decision_required"),
                "publication_ready": readiness.get("publication_ready"),
                "required_failed_count": readiness.get("required_failed_count"),
            },
        )

    policy_report, policy_ok, policy_error = read_json_if_exists(resolved["policy_validation_report"])
    add_check(
        checks,
        name="policy_validation_report_readable",
        ok=policy_ok,
        message="public metadata policy validation report is readable",
        details={"error": policy_error},
    )
    if policy_report:
        add_check(
            checks,
            name="policy_validation_report_green",
            ok=(
                policy_report.get("schema_version") == "public_metadata_release_policy_quality_v1"
                and policy_report.get("ok") is True
                and policy_report.get("required_failed_count") == 0
                and policy_report.get("publication_action_in_scope") is False
            ),
            message="public metadata policy report is green and non-publishing",
            details={
                "schema_version": policy_report.get("schema_version"),
                "ok": policy_report.get("ok"),
                "required_failed_count": policy_report.get("required_failed_count"),
                "publication_action_in_scope": policy_report.get("publication_action_in_scope"),
            },
        )

    output_report, output_ok, output_error = read_json_if_exists(resolved["output_validation_report"])
    add_check(
        checks,
        name="output_validation_report_readable",
        ok=output_ok,
        message="dataset output validation report is readable",
        details={"error": output_error},
    )
    if output_report:
        add_check(
            checks,
            name="output_validation_report_green",
            ok=(
                output_report.get("schema_version") == "dataset_release_output_quality_v2"
                and output_report.get("ok") is True
                and output_report.get("required_failed_count") == 0
            ),
            message="dataset output validation report is green",
            details={
                "schema_version": output_report.get("schema_version"),
                "ok": output_report.get("ok"),
                "required_failed_count": output_report.get("required_failed_count"),
            },
        )

    manifest, manifest_ok, manifest_error = read_json_if_exists(resolved["release_manifest"])
    add_check(
        checks,
        name="release_manifest_readable",
        ok=manifest_ok,
        message="release manifest is readable",
        details={"error": manifest_error},
    )
    if manifest:
        manifest_policy = as_mapping(manifest.get("public_release_policy"))
        compilation = as_mapping(manifest.get("compilation_license"))
        safety_manifest = as_mapping(manifest.get("safety"))
        add_check(
            checks,
            name="release_manifest_safe_candidate",
            ok=(
                manifest.get("schema_version") == "dataset_release_manifest_v2"
                and manifest.get("status") == "candidate_local_export"
                and manifest.get("publication_status") == "not_published"
                and manifest.get("manual_review_required_before_publication") is True
                and manifest_policy.get("publication_action_in_scope") is False
                and compilation.get("status") == "pending_explicit_release_decision"
                and compilation.get("single_cc0_claim_allowed") is False
                and safety_manifest.get("canonical_truth_impact") == "none"
                and safety_manifest.get("may_be_used_as_reconcile_input") is False
                and safety_manifest.get("publish_without_manual_review") is False
            ),
            message="manifest preserves local-candidate, pending-license, and non-publication boundaries",
            details={
                "schema_version": manifest.get("schema_version"),
                "status": manifest.get("status"),
                "publication_status": manifest.get("publication_status"),
                "manual_review_required_before_publication": manifest.get("manual_review_required_before_publication"),
                "public_release_policy": manifest_policy,
                "compilation_license": compilation,
                "safety": safety_manifest,
            },
        )

    quality, quality_ok, quality_error = read_json_if_exists(resolved["data_quality_summary"])
    add_check(
        checks,
        name="data_quality_summary_readable",
        ok=quality_ok,
        message="data quality summary is readable",
        details={"error": quality_error},
    )
    if quality:
        canonical = as_mapping(quality.get("canonical_id"))
        policy_summary = as_mapping(quality.get("public_release_policy"))
        transforms = as_mapping(policy_summary.get("field_transformations"))
        source_cfg = as_mapping(dataset_config.get("source_checkpoint"))
        columns_cfg = as_mapping(dataset_config.get("columns"))
        expected_row_count = source_cfg.get("expected_canonical_doc_count")
        expected_column_count = len(as_list(columns_cfg.get("required")) + as_list(columns_cfg.get("optional")))
        add_check(
            checks,
            name="data_quality_checkpoint",
            ok=(
                quality.get("schema_version") == "dataset_release_data_quality_summary_v1"
                and quality.get("row_count") == expected_row_count
                and quality.get("column_count") == expected_column_count
                and canonical.get("duplicate_count") == 0
                and canonical.get("unique_count") == expected_row_count
                and transforms.get("abstract_excluded_by_policy_count") == 0
            ),
            message="data quality matches the configured row/column and canonical-ID checkpoint",
            details={
                "expected_row_count": expected_row_count,
                "expected_column_count": expected_column_count,
                "schema_version": quality.get("schema_version"),
                "row_count": quality.get("row_count"),
                "column_count": quality.get("column_count"),
                "canonical_id": canonical,
                "field_transformations": transforms,
            },
        )

    dataset_card, card_ok, card_error = read_text_if_exists(resolved["dataset_card"])
    add_check(
        checks,
        name="dataset_card_readable",
        ok=card_ok,
        message="dataset card is readable",
        details={"error": card_error},
    )
    if dataset_card:
        lower = dataset_card.lower()
        add_check(
            checks,
            name="dataset_card_boundaries_present",
            ok=(
                "publication_status: not_published" in lower
                and "final_compilation_license: pending_explicit_release_decision" in lower
                and "article pdf binaries" in lower
                and "article full text" in lower
                and "release owner must review" in lower
            ),
            message="dataset card records publication, licensing, and excluded-content boundaries",
        )

    attribution, attribution_ok, attribution_error = read_text_if_exists(resolved["attribution"])
    add_check(
        checks,
        name="attribution_readable",
        ok=attribution_ok,
        message="attribution file is readable",
        details={"error": attribution_error},
    )
    if attribution:
        lower = attribution.lower()
        required_names = ["acl anthology", "arxiv", "crossref", "openalex", "semantic scholar"]
        missing = [name for name in required_names if name not in lower]
        add_check(
            checks,
            name="attribution_source_coverage",
            ok=not missing,
            message="attribution file covers all current source families",
            details={"missing": missing},
        )

    kaggle, kaggle_ok, kaggle_error = read_json_if_exists(resolved["kaggle_metadata_template"])
    add_check(
        checks,
        name="kaggle_template_readable",
        ok=kaggle_ok,
        message="Kaggle metadata template is readable",
        details={"error": kaggle_error},
    )
    if kaggle:
        licenses = as_list(kaggle.get("licenses"))
        license_names = [as_mapping(item).get("name") for item in licenses]
        add_check(
            checks,
            name="kaggle_template_non_publishing",
            ok=(
                kaggle.get("template_only") is True
                and kaggle.get("publication_action") == "not_performed"
                and str(kaggle.get("id") or "").startswith("__KAGGLE_OWNER__/")
                and license_names == ["other"]
            ),
            message="Kaggle metadata remains an unresolved, non-publishing template",
            details={
                "template_only": kaggle.get("template_only"),
                "publication_action": kaggle.get("publication_action"),
                "id": kaggle.get("id"),
                "license_names": license_names,
            },
        )

    decision_record, decision_ok, decision_error = read_text_if_exists(resolved["decision_record"])
    add_check(
        checks,
        name="decision_record_readable",
        ok=decision_ok,
        message="manual review decision record is readable",
        details={"error": decision_error},
    )
    if decision_record:
        lower = decision_record.lower()
        missing_markers = [marker for marker in DECISION_RECORD_MARKERS if marker.lower() not in lower]
        add_check(
            checks,
            name="decision_record_markers",
            ok=not missing_markers,
            message="decision record contains approval, license, target, attribution, and non-publication markers",
            details={"missing": missing_markers},
        )

    return checks


def build_report(
    *,
    config_path: Path,
    output_dir: Path,
    config: Mapping[str, Any],
    checks: Sequence[CheckResult],
    strict: bool,
    check_paths: bool,
) -> dict[str, Any]:
    required_failed = [check for check in checks if check.severity == "required" and not check.ok]
    warnings = [check for check in checks if check.severity == "warning" and not check.ok]
    review = as_mapping(config.get("review"))
    categories = categories_from_config(config)
    counts = status_counts(categories)

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "report_name": "check_public_metadata_release_review",
        "generated_at_utc": utc_now_iso(),
        "strict": bool(strict),
        "check_paths": bool(check_paths),
        "config_path": normalize_path(config_path),
        "review": {
            "name": review.get("name"),
            "version": review.get("version"),
            "dataset_name": review.get("dataset_name"),
            "dataset_version": review.get("dataset_version"),
            "approval_state": review.get("approval_state"),
            "required_category_count": len(CATEGORY_IDS),
            "category_status_counts": counts,
            "manual_review_required": review.get("manual_review_required"),
            "manual_review_complete": review.get("manual_review_complete"),
            "reviewer_role": review.get("reviewer_role"),
            "reviewed_at": review.get("reviewed_at"),
            "decision_record": review.get("decision_record"),
            "compilation_license_decision": review.get("compilation_license_decision"),
            "primary_publication_target": review.get("primary_publication_target"),
            "publication_targets": review.get("publication_targets"),
            "deferred_publication_targets": review.get("deferred_publication_targets"),
        },
        "manual_review_required": True,
        "manual_review_complete": review.get("manual_review_complete") is True,
        "publication_ready": False,
        "publication_block_reason": review.get("publication_block_reason"),
        "publication_action_in_scope": False,
        "pending_categories_block_publication": True,
        "pending_categories_fail_validator": False,
        "checks": [
            {
                "name": check.name,
                "ok": check.ok,
                "severity": check.severity,
                "message": check.message,
                "details": check.details or {},
            }
            for check in checks
        ],
        "required_failed_count": len(required_failed),
        "required_failed_checks": [check.name for check in required_failed],
        "warning_count": len(warnings),
        "warnings": [check.name for check in warnings],
        "ok": len(required_failed) == 0,
        "outputs": {
            "latest_json": normalize_path(output_dir / f"{REPORT_BASENAME}_latest.json"),
            "latest_markdown": normalize_path(output_dir / f"{REPORT_BASENAME}_latest.md"),
            "history_dir": normalize_path(output_dir / "history"),
        },
    }


def build_markdown(report: Mapping[str, Any]) -> str:
    review = as_mapping(report.get("review"))
    lines = [
        "# Public Metadata Release Manual Review",
        "",
        f"- schema_version: `{report.get('schema_version')}`",
        f"- generated_at_utc: `{report.get('generated_at_utc')}`",
        f"- ok: **{report.get('ok')}**",
        f"- approval_state: `{review.get('approval_state')}`",
        f"- required_category_count: `{review.get('required_category_count')}`",
        f"- category_status_counts: `{review.get('category_status_counts')}`",
        f"- manual_review_complete: `{report.get('manual_review_complete')}`",
        f"- publication_ready: `{report.get('publication_ready')}`",
        f"- publication_block_reason: `{report.get('publication_block_reason')}`",
        f"- required_failed_count: `{report.get('required_failed_count')}`",
        f"- warning_count: `{report.get('warning_count')}`",
        "",
        "## Interpretation",
        "",
        "A green report means the manual-review gate is structurally valid and its technical inputs are green.",
        "Pending categories do not fail this validator, but they continue to block publication.",
        "This report does not approve categories, choose a compilation license, select a publication target, or publish a dataset.",
        "",
        "## Checks",
        "",
    ]
    for check in report.get("checks") or []:
        icon = "✅" if check.get("ok") else "❌"
        lines.append(f"- {icon} `{check.get('name')}` ({check.get('severity')}): {check.get('message')}")
    lines.append("")
    return "\n".join(lines) + "\n"


def write_reports(report: Mapping[str, Any], output_dir: Path) -> tuple[Path, Path, Path, Path]:
    latest_json = output_dir / f"{REPORT_BASENAME}_latest.json"
    latest_md = output_dir / f"{REPORT_BASENAME}_latest.md"
    history_dir = output_dir / "history"
    ts = utc_now_ts()
    history_json = history_dir / f"{REPORT_BASENAME}_{ts}.json"
    history_md = history_dir / f"{REPORT_BASENAME}_{ts}.md"
    markdown = build_markdown(report)

    dump_json(latest_json, report)
    dump_text(latest_md, markdown)
    dump_json(history_json, report)
    dump_text(history_md, markdown)
    return latest_json, latest_md, history_json, history_md


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the human-owned public metadata release review decision while keeping "
            "actual publication out of scope."
        )
    )
    parser.add_argument("--config-path", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--check-paths", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = Path(args.config_path)
    output_dir = Path(args.output_dir)
    config = load_yaml(config_path)
    checks = validate_review(config, config_path=config_path, check_paths=bool(args.check_paths))
    report = build_report(
        config_path=config_path,
        output_dir=output_dir,
        config=config,
        checks=checks,
        strict=bool(args.strict),
        check_paths=bool(args.check_paths),
    )
    latest_json, latest_md, history_json, history_md = write_reports(report, output_dir)

    status = "OK" if report["ok"] else "FAILED"
    print(f"[{status}] schema_version={report['schema_version']}")
    print(f"[{status}] approval_state={report['review']['approval_state']}")
    print(f"[{status}] category_status_counts={report['review']['category_status_counts']}")
    print(f"[{status}] manual_review_complete={report['manual_review_complete']}")
    print(f"[{status}] publication_ready={report['publication_ready']}")
    print(f"[{status}] required_failed_count={report['required_failed_count']}")
    print(f"[{status}] latest JSON: {latest_json}")
    print(f"[{status}] latest Markdown: {latest_md}")
    print(f"[{status}] history JSON: {history_json}")
    print(f"[{status}] history Markdown: {history_md}")

    if report["required_failed_count"]:
        print("[FAILED] Required checks:")
        for name in report["required_failed_checks"]:
            print(f"- {name}")

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
