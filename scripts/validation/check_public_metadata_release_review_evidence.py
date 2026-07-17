"""Prepare deterministic evidence for manual public-metadata release review.

The report produced here is a read-only evidence map for the 20-category manual
release checklist. It never changes category statuses, never chooses a license or
publication target, never approves a release, and never publishes anything.

Important semantics:
- evidence_ready=true means sufficient review material was found;
- passed category statuses come only from the human-owned review config;
- the evidence validator never performs or infers approval;
- completed manual review still does not authorize publication.
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

from scripts.validation.check_public_metadata_release_review import CATEGORY_IDS


CONFIG_SCHEMA_VERSION = "public_metadata_release_review_evidence_config_v1"
REPORT_SCHEMA_VERSION = "public_metadata_release_review_evidence_v1"
DEFAULT_CONFIG_PATH = Path("configs/public_metadata_release_review_evidence.yaml")
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/validation")
REPORT_BASENAME = "public_metadata_release_review_evidence"

EXPECTED_EVIDENCE_METADATA = {
    "name": "public_metadata_release_review_evidence",
    "version": "v0.1",
    "status": "local_read_only_manual_release_evidence",
    "dataset_name": "ml_research_radar_metadata",
    "dataset_version": "v0.1",
    "manual_review_support": True,
    "automated_approval": False,
    "mutates_manual_review_state": False,
    "manual_review_required": True,
    "publication_ready": False,
    "publication_action_in_scope": False,
    "may_be_used_as_reconcile_input": False,
}

EXPECTED_SAFETY = {
    "read_only_evidence": True,
    "rebuild_dataset": False,
    "mutate_release_package": False,
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
    "call_kaggle_api": False,
    "call_huggingface_api": False,
    "create_github_release": False,
    "automated_category_approval": False,
    "automated_manual_approval": False,
    "may_be_used_as_reconcile_input": False,
}

REQUIRED_INPUT_KEYS = {
    "manual_review_config",
    "manual_review_report",
    "dataset_release_config",
    "public_release_policy",
    "review_readiness_report",
    "policy_validation_report",
    "config_validation_report",
    "output_validation_report",
    "release_manifest",
    "release_schema",
    "data_quality_summary",
    "field_release_policy",
    "source_attribution",
    "release_readme",
    "dataset_card",
    "attribution",
    "kaggle_metadata_template",
    "checksums",
    "policy_doc",
    "dataset_release_doc",
    "dataset_strategy_doc",
    "source_matrix_doc",
    "provenance_semantics_doc",
    "merge_policy_doc",
    "decision_record_doc",
}

CATEGORY_TITLES = {
    "release_identity_checkpoint": "Release identity and checkpoint",
    "canonical_truth_boundary": "Canonical truth and reconcile boundary",
    "selected_field_policy_coverage": "Selected field policy coverage",
    "abstract_source_aware_handling": "Source-aware abstract handling",
    "bibliographic_metadata_contract": "Bibliographic metadata contract",
    "external_identifiers_and_links": "External identifiers and links",
    "taxonomy_and_counts_contract": "Taxonomy, derived flags, and count metadata",
    "excluded_content_boundary": "Excluded content boundary",
    "source_attribution_coverage": "Source attribution coverage",
    "arxiv_policy_evidence": "arXiv policy evidence",
    "openalex_policy_evidence": "OpenAlex policy evidence",
    "crossref_policy_evidence": "Crossref policy evidence",
    "semantic_scholar_policy_evidence": "Semantic Scholar policy evidence",
    "acl_anthology_policy_evidence": "ACL Anthology policy evidence",
    "package_manifest_checksums_kaggle_template": "Package manifest, checksums, and Kaggle template",
    "compilation_license_decision": "Final compilation license decision",
    "provider_terms_review": "Provider terms review",
    "dataset_card_and_attribution_wording": "Dataset card and attribution wording",
    "publication_target_decision": "Publication target decision",
    "manual_release_approval_state": "Final manual release approval state",
}


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


def safe_load_json(path: Path) -> tuple[dict[str, Any], bool, str | None]:
    if not path.exists():
        return {}, False, "file does not exist"
    try:
        return load_json(path), True, None
    except Exception as exc:  # pragma: no cover
        return {}, False, str(exc)


def safe_load_yaml(path: Path) -> tuple[dict[str, Any], bool, str | None]:
    if not path.exists():
        return {}, False, "file does not exist"
    try:
        return load_yaml(path), True, None
    except Exception as exc:  # pragma: no cover
        return {}, False, str(exc)


def safe_load_text(path: Path) -> tuple[str, bool, str | None]:
    if not path.exists():
        return "", False, "file does not exist"
    try:
        return path.read_text(encoding="utf-8"), True, None
    except Exception as exc:  # pragma: no cover
        return "", False, str(exc)


def marker_check(text: str, markers: Sequence[str]) -> tuple[bool, list[str]]:
    lower = text.lower()
    missing = [marker for marker in markers if marker.lower() not in lower]
    return not missing, missing


def checksum_entries(text: str) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) == 2:
            entries[parts[1]] = parts[0]
    return entries


def build_category(
    category_id: str,
    *,
    category_status: str,
    evidence_ready: bool,
    automated_support: bool,
    evidence_refs: Sequence[str],
    findings: Sequence[str],
) -> dict[str, Any]:
    return {
        "id": category_id,
        "title": CATEGORY_TITLES[category_id],
        "required": True,
        "category_status": category_status,
        "evidence_ready": bool(evidence_ready),
        "automated_support": bool(automated_support),
        "human_decision_required": not automated_support,
        "evidence_refs": list(evidence_refs),
        "findings": list(findings),
        "automated_decision": None,
    }


def validate_evidence(
    config: Mapping[str, Any],
    *,
    config_path: Path,
    check_paths: bool = True,
) -> tuple[list[CheckResult], list[dict[str, Any]]]:
    checks: list[CheckResult] = []
    categories: list[dict[str, Any]] = []

    add_check(
        checks,
        name="schema_version",
        ok=config.get("schema_version") == CONFIG_SCHEMA_VERSION,
        message=f"schema_version is {CONFIG_SCHEMA_VERSION}",
        details={"actual": config.get("schema_version")},
    )

    evidence_meta = as_mapping(config.get("evidence"))
    for key, expected in EXPECTED_EVIDENCE_METADATA.items():
        add_check(
            checks,
            name=f"evidence_{key}",
            ok=evidence_meta.get(key) == expected,
            message=f"evidence.{key} preserves the read-only evidence-preparation state",
            details={"expected": expected, "actual": evidence_meta.get(key)},
        )

    safety = as_mapping(config.get("safety"))
    for key, expected in EXPECTED_SAFETY.items():
        add_check(
            checks,
            name=f"safety_{key}",
            ok=safety.get(key) == expected,
            message=f"safety.{key} preserves the non-mutating, non-publishing boundary",
            details={"expected": expected, "actual": safety.get(key)},
        )

    category_policy = as_mapping(config.get("category_policy"))
    automated_ids = [str(item) for item in as_list(category_policy.get("automated_support_category_ids"))]
    human_ids = [str(item) for item in as_list(category_policy.get("human_decision_category_ids"))]
    add_check(
        checks,
        name="required_category_count",
        ok=category_policy.get("required_category_count") == len(CATEGORY_IDS),
        message="evidence policy requires exactly 20 manual-review categories",
        details={"expected": len(CATEGORY_IDS), "actual": category_policy.get("required_category_count")},
    )
    add_check(
        checks,
        name="category_partition",
        ok=(
            automated_ids + human_ids == CATEGORY_IDS
            and len(set(automated_ids) & set(human_ids)) == 0
        ),
        message="automated-support and human-decision categories form a deterministic non-overlapping partition",
        details={"automated": automated_ids, "human": human_ids},
    )

    inputs = as_mapping(config.get("inputs"))
    missing_keys = sorted(REQUIRED_INPUT_KEYS - set(inputs))
    add_check(
        checks,
        name="required_input_keys",
        ok=not missing_keys,
        message="all evidence input paths are configured",
        details={"missing": missing_keys},
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
                message=f"configured evidence input exists: {key}",
                details={"path": normalize_path(path)},
            )

    if not check_paths:
        return checks, categories

    expected = as_mapping(config.get("expected"))
    required_markers = as_mapping(config.get("required_markers"))

    manual_config, manual_config_ok, manual_config_error = safe_load_yaml(resolved["manual_review_config"])
    manual_report, manual_report_ok, manual_report_error = safe_load_json(resolved["manual_review_report"])
    dataset_config, dataset_config_ok, dataset_config_error = safe_load_yaml(resolved["dataset_release_config"])
    policy, policy_ok, policy_error = safe_load_yaml(resolved["public_release_policy"])
    readiness, readiness_ok, readiness_error = safe_load_json(resolved["review_readiness_report"])
    policy_report, policy_report_ok, policy_report_error = safe_load_json(resolved["policy_validation_report"])
    config_report, config_report_ok, config_report_error = safe_load_json(resolved["config_validation_report"])
    output_report, output_report_ok, output_report_error = safe_load_json(resolved["output_validation_report"])
    manifest, manifest_ok, manifest_error = safe_load_json(resolved["release_manifest"])
    schema, schema_ok, schema_error = safe_load_json(resolved["release_schema"])
    quality, quality_ok, quality_error = safe_load_json(resolved["data_quality_summary"])
    field_policy, field_policy_ok, field_policy_error = safe_load_json(resolved["field_release_policy"])
    source_attr, source_attr_ok, source_attr_error = safe_load_json(resolved["source_attribution"])
    kaggle, kaggle_ok, kaggle_error = safe_load_json(resolved["kaggle_metadata_template"])

    json_inputs = {
        "manual_review_report": (manual_report_ok, manual_report_error),
        "review_readiness_report": (readiness_ok, readiness_error),
        "policy_validation_report": (policy_report_ok, policy_report_error),
        "config_validation_report": (config_report_ok, config_report_error),
        "output_validation_report": (output_report_ok, output_report_error),
        "release_manifest": (manifest_ok, manifest_error),
        "release_schema": (schema_ok, schema_error),
        "data_quality_summary": (quality_ok, quality_error),
        "field_release_policy": (field_policy_ok, field_policy_error),
        "source_attribution": (source_attr_ok, source_attr_error),
        "kaggle_metadata_template": (kaggle_ok, kaggle_error),
    }
    yaml_inputs = {
        "manual_review_config": (manual_config_ok, manual_config_error),
        "dataset_release_config": (dataset_config_ok, dataset_config_error),
        "public_release_policy": (policy_ok, policy_error),
    }
    for key, (ok, error) in {**json_inputs, **yaml_inputs}.items():
        add_check(
            checks,
            name=f"{key}_readable",
            ok=ok,
            message=f"{key} is readable",
            details={"error": error},
        )

    text_payloads: dict[str, str] = {}
    text_marker_results: dict[str, bool] = {}
    for key in [
        "release_readme",
        "dataset_card",
        "attribution",
        "checksums",
        "policy_doc",
        "dataset_release_doc",
        "dataset_strategy_doc",
        "source_matrix_doc",
        "provenance_semantics_doc",
        "merge_policy_doc",
        "decision_record_doc",
    ]:
        text, ok, error = safe_load_text(resolved[key])
        text_payloads[key] = text
        add_check(
            checks,
            name=f"{key}_readable",
            ok=ok,
            message=f"{key} is readable",
            details={"error": error},
        )
        markers = [str(item) for item in as_list(required_markers.get(key))]
        markers_ok, missing = marker_check(text, markers)
        text_marker_results[key] = markers_ok
        add_check(
            checks,
            name=f"{key}_markers",
            ok=markers_ok,
            message=f"{key} contains required review markers",
            details={"missing": missing},
        )

    manual_review = as_mapping(manual_config.get("review"))
    manual_categories = [as_mapping(item) for item in as_list(as_mapping(manual_config.get("manual_review")).get("categories"))]
    manual_statuses = {str(item.get("id") or ""): item.get("status") for item in manual_categories}
    manual_status_counts = dict(sorted(Counter(str(status) for status in manual_statuses.values()).items()))
    expected_status_counts = {str(k): int(v) for k, v in as_mapping(expected.get("required_category_status_counts")).items()}
    actual_failed_ids = [category_id for category_id in CATEGORY_IDS if manual_statuses.get(category_id) == "failed"]
    expected_failed_ids = [str(item) for item in as_list(expected.get("failed_category_ids"))]
    manual_report_review = as_mapping(manual_report.get("review"))
    manual_gate_ok = (
        manual_config.get("schema_version") == "public_metadata_release_review_config_v1"
        and manual_review.get("approval_state") == expected.get("approval_state")
        and manual_review.get("manual_review_complete") is expected.get("manual_review_complete")
        and manual_review.get("publication_ready") is expected.get("publication_ready")
        and manual_review.get("publication_block_reason") == expected.get("publication_block_reason")
        and list(manual_statuses) == CATEGORY_IDS
        and manual_status_counts == expected_status_counts
        and actual_failed_ids == expected_failed_ids
        and manual_report.get("schema_version") == "public_metadata_release_review_v1"
        and manual_report.get("ok") is True
        and manual_report.get("required_failed_count") == 0
        and manual_report_review.get("approval_state") == expected.get("approval_state")
        and manual_report_review.get("category_status_counts") == expected_status_counts
        and manual_report.get("manual_review_complete") is expected.get("manual_review_complete")
        and manual_report.get("publication_ready") is expected.get("publication_ready")
        and manual_report.get("publication_block_reason") == expected.get("publication_block_reason")
    )
    add_check(
        checks,
        name="manual_review_gate_rejected_and_green",
        ok=manual_gate_ok,
        message="manual-review gate records a complete human rejection while publication remains blocked",
        details={
            "approval_state": manual_review.get("approval_state"),
            "manual_review_complete": manual_review.get("manual_review_complete"),
            "publication_ready": manual_review.get("publication_ready"),
            "category_statuses": manual_statuses,
            "category_status_counts": manual_status_counts,
            "failed_category_ids": actual_failed_ids,
            "report_schema_version": manual_report.get("schema_version"),
            "report_ok": manual_report.get("ok"),
        },
    )

    readiness_green = (
        readiness.get("schema_version") == "dataset_release_review_readiness_v2"
        and readiness.get("ok") is True
        and readiness.get("technical_candidate_ready") is True
        and readiness.get("public_policy_ready") is True
        and readiness.get("manual_release_decision_required") is True
        and readiness.get("publication_ready") is False
        and readiness.get("required_failed_count") == 0
    )
    reports_green = (
        config_report.get("schema_version") == "dataset_release_config_quality_v2"
        and config_report.get("ok") is True
        and config_report.get("required_failed_count") == 0
        and policy_report.get("schema_version") == "public_metadata_release_policy_quality_v1"
        and policy_report.get("ok") is True
        and policy_report.get("required_failed_count") == 0
        and policy_report.get("publication_action_in_scope") is False
        and output_report.get("schema_version") == "dataset_release_output_quality_v2"
        and output_report.get("ok") is True
        and output_report.get("required_failed_count") == 0
    )
    add_check(
        checks,
        name="upstream_validation_reports_green",
        ok=readiness_green and reports_green,
        message="config, policy, output, and review-readiness reports are green and non-publishing",
        details={
            "review_readiness": {
                "ok": readiness.get("ok"),
                "technical_candidate_ready": readiness.get("technical_candidate_ready"),
                "public_policy_ready": readiness.get("public_policy_ready"),
                "publication_ready": readiness.get("publication_ready"),
            },
            "config_report_ok": config_report.get("ok"),
            "policy_report_ok": policy_report.get("ok"),
            "output_report_ok": output_report.get("ok"),
        },
    )

    release_meta = as_mapping(dataset_config.get("release"))
    source_checkpoint = as_mapping(dataset_config.get("source_checkpoint"))
    manifest_release = as_mapping(manifest.get("release"))
    manifest_source = as_mapping(manifest.get("source_checkpoint"))
    release_identity_ok = (
        dataset_config.get("schema_version") == "dataset_release_config_v2"
        and release_meta.get("dataset_name") == evidence_meta.get("dataset_name")
        and release_meta.get("version") == evidence_meta.get("dataset_version")
        and source_checkpoint.get("expected_canonical_doc_count") == expected.get("canonical_doc_count")
        and manifest.get("schema_version") == "dataset_release_manifest_v2"
        and manifest_release.get("dataset_name") == evidence_meta.get("dataset_name")
        and manifest_release.get("version") == evidence_meta.get("dataset_version")
        and manifest_source.get("actual_exported_row_count") == expected.get("canonical_doc_count")
    )
    add_check(
        checks,
        name="release_identity_checkpoint",
        ok=release_identity_ok,
        message="config and manifest identify the same 60,954-row v0.1 release candidate",
        details={
            "config_release": release_meta,
            "config_source_checkpoint": source_checkpoint,
            "manifest_release": manifest_release,
            "manifest_source_checkpoint": manifest_source,
        },
    )

    manifest_safety = as_mapping(manifest.get("safety"))
    policy_boundary = as_mapping(policy.get("dataset_boundary"))
    canonical_boundary_ok = (
        manifest.get("publication_status") == "not_published"
        and manifest_safety.get("canonical_truth_impact") == "none"
        and manifest_safety.get("may_be_used_as_reconcile_input") is False
        and policy_boundary.get("canonical_truth_impact") == "none"
        and policy_boundary.get("public_rows_may_be_used_as_reconcile_input") is False
    )
    add_check(
        checks,
        name="canonical_truth_boundary",
        ok=canonical_boundary_ok,
        message="release artifacts remain derived and forbidden as reconciliation input",
        details={"manifest_safety": manifest_safety, "policy_boundary": policy_boundary},
    )

    schema_columns = [as_mapping(item).get("name") for item in as_list(schema.get("columns"))]
    policy_fields = as_list(field_policy.get("fields"))
    policy_field_names = [as_mapping(item).get("name") for item in policy_fields]
    selected_field_ok = (
        schema.get("schema_version") == "dataset_release_schema_v1"
        and field_policy.get("schema_version") == "dataset_field_release_policy_v1"
        and len(schema_columns) == expected.get("column_count")
        and schema_columns == policy_field_names
    )
    add_check(
        checks,
        name="selected_field_policy_coverage",
        ok=selected_field_ok,
        message="all 34 exported columns are covered by the field release policy in deterministic order",
        details={"schema_columns": schema_columns, "policy_field_names": policy_field_names},
    )

    field_by_name = {str(as_mapping(item).get("name") or ""): as_mapping(item) for item in policy_fields}
    abstract_policy = field_by_name.get("abstract", {})
    quality_policy = as_mapping(quality.get("public_release_policy"))
    transforms = as_mapping(quality_policy.get("field_transformations"))
    abstract_ok = (
        abstract_policy.get("action") == "source_aware_include_or_null"
        and abstract_policy.get("fallback_action") == "null"
        and abstract_policy.get("acl_min_year") == 2016
        and transforms.get("abstract_excluded_by_policy_count") == expected.get("abstract_excluded_by_policy_count")
    )
    add_check(
        checks,
        name="abstract_source_aware_handling",
        ok=abstract_ok,
        message="abstract handling is source-aware, fail-closed, and recorded in data quality evidence",
        details={"abstract_policy": abstract_policy, "field_transformations": transforms},
    )

    canonical_stats = as_mapping(quality.get("canonical_id"))
    quality_checkpoint_ok = (
        quality.get("schema_version") == "dataset_release_data_quality_summary_v1"
        and quality.get("row_count") == expected.get("canonical_doc_count")
        and quality.get("column_count") == expected.get("column_count")
        and canonical_stats.get("duplicate_count") == expected.get("duplicate_canonical_id_count")
        and canonical_stats.get("unique_count") == expected.get("canonical_doc_count")
    )
    add_check(
        checks,
        name="data_quality_checkpoint",
        ok=quality_checkpoint_ok,
        message="data quality matches the accepted row, column, and canonical-ID checkpoint",
        details={"row_count": quality.get("row_count"), "column_count": quality.get("column_count"), "canonical_id": canonical_stats},
    )

    forbidden = set(str(item) for item in as_list(policy_boundary.get("forbidden_content")))
    excluded_ok = {
        "pdf_binary",
        "article_full_text",
        "raw_provider_payload",
        "raw_source_record",
        "source_snapshot",
        "embedding_vector",
        "private_notes",
    }.issubset(forbidden)
    add_check(
        checks,
        name="excluded_content_boundary",
        ok=excluded_ok,
        message="policy explicitly excludes all high-risk content classes",
        details={"forbidden_content": sorted(forbidden)},
    )

    source_rows = [as_mapping(item) for item in as_list(source_attr.get("sources"))]
    source_by_family = {str(item.get("source_family") or ""): item for item in source_rows}
    required_sources = [str(item) for item in as_list(expected.get("required_source_families"))]
    source_coverage_ok = (
        source_attr.get("schema_version") == "dataset_source_attribution_v1"
        and source_attr.get("attribution_required_for_all_sources") is True
        and sorted(source_by_family) == sorted(required_sources)
    )
    add_check(
        checks,
        name="source_attribution_coverage",
        ok=source_coverage_ok,
        message="source attribution covers all five current canonical source families",
        details={"expected": required_sources, "actual": sorted(source_by_family)},
    )

    source_policy = as_mapping(policy.get("source_policies"))
    source_policy_results: dict[str, bool] = {}
    for source_name in required_sources:
        attr_row = source_by_family.get(source_name, {})
        policy_row = as_mapping(source_policy.get(source_name))
        source_policy_results[source_name] = (
            attr_row.get("attribution_required") is True
            and attr_row.get("raw_payload_allowed") is False
            and attr_row.get("pdf_or_full_text_redistribution_allowed") is False
            and str(attr_row.get("terms_url") or "").startswith("https://")
            and policy_row.get("attribution_required") is True
            and policy_row.get("raw_payload_allowed") is False
            and policy_row.get("pdf_or_full_text_redistribution_allowed") is False
            and str(policy_row.get("terms_url") or "").startswith("https://")
        )
    add_check(
        checks,
        name="source_policy_evidence",
        ok=all(source_policy_results.values()),
        message="all five source policies contain terms, attribution, and no-raw/no-full-text boundaries",
        details={"source_results": source_policy_results},
    )

    checksum_text = text_payloads.get("checksums", "")
    checksum_map = checksum_entries(checksum_text)
    required_checksum_files = [str(item) for item in as_list(expected.get("required_checksum_files"))]
    missing_checksum_files = [name for name in required_checksum_files if name not in checksum_map]
    manifest_files = as_mapping(manifest.get("files"))
    kaggle_licenses = [as_mapping(item).get("name") for item in as_list(kaggle.get("licenses"))]
    package_integrity_ok = (
        output_report.get("ok") is True
        and "checksums_match_files" not in as_list(output_report.get("required_failed_checks"))
        and not missing_checksum_files
        and len(manifest_files) == 11
        and kaggle.get("template_only") is True
        and kaggle.get("publication_action") == "not_performed"
        and str(kaggle.get("id") or "").startswith("__KAGGLE_OWNER__/")
        and kaggle_licenses == ["other"]
    )
    add_check(
        checks,
        name="package_manifest_checksums_kaggle_template",
        ok=package_integrity_ok,
        message="manifest, checksums, and Kaggle metadata preserve package integrity and non-publication",
        details={
            "manifest_files": manifest_files,
            "missing_checksum_files": missing_checksum_files,
            "kaggle": {
                "template_only": kaggle.get("template_only"),
                "publication_action": kaggle.get("publication_action"),
                "id": kaggle.get("id"),
                "licenses": kaggle_licenses,
            },
        },
    )

    compilation = as_mapping(manifest.get("compilation_license"))
    publication_targets = [str(item) for item in as_list(manifest_release.get("publication_targets"))]
    human_material_ok = (
        compilation.get("status") == "pending_explicit_release_decision"
        and compilation.get("single_cc0_claim_allowed") is False
        and source_coverage_ok
        and bool(text_payloads.get("dataset_card", "").strip())
        and bool(text_payloads.get("attribution", "").strip())
        and bool(text_payloads.get("decision_record_doc", "").strip())
        and text_marker_results.get("decision_record_doc") is True
        and bool(publication_targets)
        and manual_gate_ok
    )
    add_check(
        checks,
        name="human_decision_material_ready",
        ok=human_material_ok,
        message="license, provider terms, wording, target, and human approval decisions are documented without publication",
        details={
            "compilation_license": compilation,
            "publication_targets": publication_targets,
            "manual_gate_ok": manual_gate_ok,
        },
    )

    publication_separation_ok = (
        evidence_meta.get("publication_action_in_scope") is False
        and manifest.get("publication_status") == "not_published"
        and policy_report.get("publication_action_in_scope") is False
        and kaggle.get("publication_action") == "not_performed"
        and manual_review.get("publication_ready") is False
    )
    add_check(
        checks,
        name="publication_action_separation",
        ok=publication_separation_ok,
        message="evidence preparation, manual review, and actual publication remain separate actions",
        details={
            "manifest_publication_status": manifest.get("publication_status"),
            "policy_publication_action_in_scope": policy_report.get("publication_action_in_scope"),
            "kaggle_publication_action": kaggle.get("publication_action"),
            "manual_review_publication_ready": manual_review.get("publication_ready"),
        },
    )

    bibliographic_fields = ["title", "authors", "year", "venue", "journal", "conference", "publisher", "publication_type"]
    bibliographic_ok = all(name in schema_columns and name in field_by_name for name in bibliographic_fields)
    identifiers_links = ["doi", "arxiv_id", "openalex_id", "landing_page_url", "pdf_url", "external_ids_summary"]
    identifiers_ok = all(name in schema_columns and name in field_by_name for name in identifiers_links) and field_by_name.get("pdf_url", {}).get("action") == "include_link_only_no_binary"
    taxonomy_counts = ["primary_category", "categories", "concepts", "keywords", "tags", "cited_by_count", "references_count", "metadata_completeness_score", "is_preprint", "is_review", "is_survey", "is_withdrawn"]
    taxonomy_ok = all(name in schema_columns and name in field_by_name for name in taxonomy_counts)

    common_refs = {
        "release_identity_checkpoint": ["configs/dataset_release.yaml", "manifest.json", "data_quality_summary.json"],
        "canonical_truth_boundary": ["manifest.json", "public_metadata_release_policy_v0.1.yaml", "DATASET_CARD.md"],
        "selected_field_policy_coverage": ["schema.json", "field_release_policy.json", "dataset_release_output_latest.json"],
        "abstract_source_aware_handling": ["field_release_policy.json", "source_attribution.json", "data_quality_summary.json"],
        "bibliographic_metadata_contract": ["schema.json", "field_release_policy.json", "docs/merge_policy.md"],
        "external_identifiers_and_links": ["schema.json", "field_release_policy.json", "DATASET_CARD.md"],
        "taxonomy_and_counts_contract": ["schema.json", "data_quality_summary.json", "docs/source_matrix.md"],
        "excluded_content_boundary": ["public_metadata_release_policy_v0.1.yaml", "DATASET_CARD.md", "ATTRIBUTION.md"],
        "source_attribution_coverage": ["source_attribution.json", "ATTRIBUTION.md", "docs/source_matrix.md"],
        "arxiv_policy_evidence": ["source_attribution.json", "ATTRIBUTION.md", "public_metadata_release_policy_v0.1.yaml"],
        "openalex_policy_evidence": ["source_attribution.json", "ATTRIBUTION.md", "public_metadata_release_policy_v0.1.yaml"],
        "crossref_policy_evidence": ["source_attribution.json", "ATTRIBUTION.md", "public_metadata_release_policy_v0.1.yaml"],
        "semantic_scholar_policy_evidence": ["source_attribution.json", "ATTRIBUTION.md", "public_metadata_release_policy_v0.1.yaml"],
        "acl_anthology_policy_evidence": ["source_attribution.json", "ATTRIBUTION.md", "public_metadata_release_policy_v0.1.yaml"],
        "package_manifest_checksums_kaggle_template": ["manifest.json", "checksums.txt", "kaggle_metadata.template.json", "dataset_release_output_latest.json"],
        "compilation_license_decision": ["manifest.json", "DATASET_CARD.md", "docs/public_metadata_release_review_decision_v0.1.md"],
        "provider_terms_review": ["ATTRIBUTION.md", "source_attribution.json", "docs/public_metadata_release_review_decision_v0.1.md"],
        "dataset_card_and_attribution_wording": ["DATASET_CARD.md", "ATTRIBUTION.md", "docs/public_metadata_release_review_decision_v0.1.md"],
        "publication_target_decision": ["kaggle_metadata.template.json", "configs/public_metadata_release_review.yaml", "docs/public_metadata_release_review_decision_v0.1.md"],
        "manual_release_approval_state": ["configs/public_metadata_release_review.yaml", "public_metadata_release_review_latest.json", "docs/public_metadata_release_review_decision_v0.1.md"],
    }

    readiness_by_category = {
        "release_identity_checkpoint": release_identity_ok and quality_checkpoint_ok,
        "canonical_truth_boundary": canonical_boundary_ok and publication_separation_ok,
        "selected_field_policy_coverage": selected_field_ok,
        "abstract_source_aware_handling": abstract_ok,
        "bibliographic_metadata_contract": bibliographic_ok,
        "external_identifiers_and_links": identifiers_ok,
        "taxonomy_and_counts_contract": taxonomy_ok and quality_checkpoint_ok,
        "excluded_content_boundary": excluded_ok,
        "source_attribution_coverage": source_coverage_ok,
        "arxiv_policy_evidence": source_policy_results.get("arxiv", False),
        "openalex_policy_evidence": source_policy_results.get("openalex", False),
        "crossref_policy_evidence": source_policy_results.get("crossref", False),
        "semantic_scholar_policy_evidence": source_policy_results.get("semantic_scholar", False),
        "acl_anthology_policy_evidence": source_policy_results.get("acl_anthology", False) and abstract_ok,
        "package_manifest_checksums_kaggle_template": package_integrity_ok,
        "compilation_license_decision": human_material_ok,
        "provider_terms_review": human_material_ok and source_coverage_ok,
        "dataset_card_and_attribution_wording": human_material_ok,
        "publication_target_decision": human_material_ok and bool(publication_targets),
        "manual_release_approval_state": manual_gate_ok,
    }

    for category_id in CATEGORY_IDS:
        automated = category_id in automated_ids
        categories.append(
            build_category(
                category_id,
                category_status=str(manual_statuses.get(category_id) or "missing"),
                evidence_ready=readiness_by_category[category_id],
                automated_support=automated,
                evidence_refs=common_refs[category_id],
                findings=[
                    "Evidence material is present and consistent with the local candidate checkpoint."
                    if readiness_by_category[category_id]
                    else "Evidence material is missing, stale, or inconsistent.",
                    "Category status comes from the human-owned review config; no automated approval was performed.",
                ],
            )
        )

    not_ready = [item["id"] for item in categories if not item["evidence_ready"]]
    add_check(
        checks,
        name="all_categories_evidence_ready",
        ok=not not_ready,
        message="all 20 manual-review categories have deterministic evidence support",
        details={"not_ready": not_ready},
    )
    add_check(
        checks,
        name="evidence_does_not_approve_categories",
        ok=all(
            item["category_status"] == manual_statuses.get(item["id"])
            and item["automated_decision"] is None
            for item in categories
        ),
        message="evidence mirrors human-owned category statuses and makes no automated decision",
    )

    return checks, categories


def build_report(
    *,
    config_path: Path,
    output_dir: Path,
    config: Mapping[str, Any],
    checks: Sequence[CheckResult],
    categories: Sequence[Mapping[str, Any]],
    strict: bool,
    check_paths: bool,
) -> dict[str, Any]:
    required_failed = [check for check in checks if check.severity == "required" and not check.ok]
    warnings = [check for check in checks if check.severity == "warning" and not check.ok]
    category_policy = as_mapping(config.get("category_policy"))
    automated_ids = [str(item) for item in as_list(category_policy.get("automated_support_category_ids"))]
    human_ids = [str(item) for item in as_list(category_policy.get("human_decision_category_ids"))]
    evidence_ready_count = sum(1 for item in categories if item.get("evidence_ready") is True)
    evidence_ready = len(required_failed) == 0 and evidence_ready_count == len(CATEGORY_IDS)
    category_status_counts = dict(sorted(Counter(str(item.get("category_status")) for item in categories).items()))
    expected = as_mapping(config.get("expected"))

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "report_name": "check_public_metadata_release_review_evidence",
        "generated_at_utc": utc_now_iso(),
        "strict": bool(strict),
        "check_paths": bool(check_paths),
        "config_path": normalize_path(config_path),
        "evidence": {
            "name": as_mapping(config.get("evidence")).get("name"),
            "version": as_mapping(config.get("evidence")).get("version"),
            "dataset_name": as_mapping(config.get("evidence")).get("dataset_name"),
            "dataset_version": as_mapping(config.get("evidence")).get("dataset_version"),
            "required_category_count": len(CATEGORY_IDS),
            "evidence_ready_category_count": evidence_ready_count,
            "automated_support_category_count": len(automated_ids),
            "human_decision_category_count": len(human_ids),
            "category_status_counts": category_status_counts,
            "categories": list(categories),
        },
        "manual_review_evidence_ready": evidence_ready,
        "manual_review_required": True,
        "manual_review_complete": expected.get("manual_review_complete") is True,
        "publication_ready": False,
        "publication_block_reason": expected.get("publication_block_reason"),
        "publication_action_in_scope": False,
        "automated_category_approval": False,
        "automated_manual_approval": False,
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
        "ok": evidence_ready,
        "outputs": {
            "latest_json": normalize_path(output_dir / f"{REPORT_BASENAME}_latest.json"),
            "latest_markdown": normalize_path(output_dir / f"{REPORT_BASENAME}_latest.md"),
            "history_dir": normalize_path(output_dir / "history"),
        },
    }


def build_markdown(report: Mapping[str, Any]) -> str:
    evidence = as_mapping(report.get("evidence"))
    lines = [
        "# Public Metadata Release Manual-Review Evidence",
        "",
        f"- schema_version: `{report.get('schema_version')}`",
        f"- generated_at_utc: `{report.get('generated_at_utc')}`",
        f"- ok: **{report.get('ok')}**",
        f"- manual_review_evidence_ready: `{report.get('manual_review_evidence_ready')}`",
        f"- evidence_ready_category_count: `{evidence.get('evidence_ready_category_count')}` / `{evidence.get('required_category_count')}`",
        f"- automated_support_category_count: `{evidence.get('automated_support_category_count')}`",
        f"- human_decision_category_count: `{evidence.get('human_decision_category_count')}`",
        f"- manual_review_complete: `{report.get('manual_review_complete')}`",
        f"- publication_ready: `{report.get('publication_ready')}`",
        f"- publication_block_reason: `{report.get('publication_block_reason')}`",
        f"- required_failed_count: `{report.get('required_failed_count')}`",
        f"- warning_count: `{report.get('warning_count')}`",
        "",
        "## Interpretation",
        "",
        "Evidence readiness means the review material is present and internally consistent.",
        "It does not pass any category, approve the release, choose a license or target, or perform publication.",
        "All 20 category statuses remain pending until a separate human-review execution slice.",
        "",
        "## Categories",
        "",
    ]
    for category in evidence.get("categories") or []:
        icon = "✅" if category.get("evidence_ready") else "❌"
        mode = "automated support" if category.get("automated_support") else "human decision"
        lines.append(
            f"- {icon} `{category.get('id')}` — {category.get('title')} ({mode}); status=`{category.get('category_status')}`"
        )
    lines.extend(["", "## Checks", ""])
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
            "Prepare and validate deterministic manual-review evidence for the public "
            "metadata release candidate without approving or publishing it."
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
    checks, categories = validate_evidence(
        config,
        config_path=config_path,
        check_paths=bool(args.check_paths),
    )
    report = build_report(
        config_path=config_path,
        output_dir=output_dir,
        config=config,
        checks=checks,
        categories=categories,
        strict=bool(args.strict),
        check_paths=bool(args.check_paths),
    )
    latest_json, latest_md, history_json, history_md = write_reports(report, output_dir)

    status = "OK" if report["ok"] else "FAILED"
    evidence = as_mapping(report.get("evidence"))
    print(f"[{status}] schema_version={report['schema_version']}")
    print(f"[{status}] manual_review_evidence_ready={report['manual_review_evidence_ready']}")
    print(f"[{status}] evidence_ready_category_count={evidence.get('evidence_ready_category_count')}")
    print(f"[{status}] automated_support_category_count={evidence.get('automated_support_category_count')}")
    print(f"[{status}] human_decision_category_count={evidence.get('human_decision_category_count')}")
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
