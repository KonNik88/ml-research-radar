from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

SCHEMA_VERSION = "public_metadata_release_policy_v1"
REPORT_SCHEMA_VERSION = "public_metadata_release_policy_quality_v1"
DEFAULT_POLICY_PATH = Path("configs/public_metadata_release_policy_v0.1.yaml")
DEFAULT_DATASET_CONFIG_PATH = Path("configs/dataset_release.yaml")
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/validation")

REQUIRED_TOP_LEVEL_KEYS = {
    "schema_version",
    "policy",
    "dataset_boundary",
    "compilation_license",
    "source_policies",
    "field_policies",
    "packaging",
}
REQUIRED_SOURCE_FAMILIES = {
    "arxiv",
    "openalex",
    "crossref",
    "semantic_scholar",
    "acl_anthology",
}
REQUIRED_FORBIDDEN_CONTENT = {
    "pdf_binary",
    "article_full_text",
    "raw_provider_payload",
    "raw_source_record",
    "source_snapshot",
    "embedding_vector",
    "private_notes",
}
REQUIRED_PACKAGING_FILES = {
    "DATASET_CARD.md",
    "ATTRIBUTION.md",
    "field_release_policy.json",
    "source_attribution.json",
    "kaggle_metadata.template.json",
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


def as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: Mapping[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"YAML file must contain a mapping: {path}")
    return payload


def selected_columns_from_dataset_config(config: Mapping[str, Any]) -> list[str]:
    columns = as_mapping(config.get("columns"))
    selected: list[str] = []
    seen: set[str] = set()
    for item in as_list(columns.get("required")) + as_list(columns.get("optional")):
        name = str(item).strip()
        if name and name not in seen:
            selected.append(name)
            seen.add(name)
    return selected


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


def validate_policy(
    policy: Mapping[str, Any],
    *,
    policy_path: Path,
    dataset_config: Mapping[str, Any] | None = None,
    dataset_config_path: Path | None = None,
    check_paths: bool = False,
) -> list[CheckResult]:
    checks: list[CheckResult] = []

    missing_top = sorted(REQUIRED_TOP_LEVEL_KEYS - set(policy.keys()))
    add_check(
        checks,
        name="required_top_level_keys",
        ok=not missing_top,
        message="Public metadata release policy contains all required sections",
        details={"missing": missing_top},
    )
    add_check(
        checks,
        name="schema_version",
        ok=policy.get("schema_version") == SCHEMA_VERSION,
        message=f"schema_version is {SCHEMA_VERSION}",
        details={"actual": policy.get("schema_version")},
    )

    policy_meta = as_mapping(policy.get("policy"))
    add_check(
        checks,
        name="policy_id",
        ok=bool(str(policy_meta.get("policy_id") or "").strip()),
        message="policy.policy_id is present",
        details={"actual": policy_meta.get("policy_id")},
    )
    add_check(
        checks,
        name="policy_status",
        ok=policy_meta.get("status") == "approved_for_local_candidate_packaging",
        message="policy is approved for local candidate packaging",
        details={"actual": policy_meta.get("status")},
    )
    add_check(
        checks,
        name="publication_action_not_in_scope",
        ok=policy_meta.get("publication_action_in_scope") is False,
        message="policy does not perform a publication action",
        details={"actual": policy_meta.get("publication_action_in_scope")},
    )
    targets = {str(item) for item in as_list(policy_meta.get("publication_targets"))}
    add_check(
        checks,
        name="kaggle_target_recorded",
        ok="kaggle" in targets,
        message="Kaggle is recorded as a candidate publication target",
        details={"targets": sorted(targets)},
    )
    add_check(
        checks,
        name="attribution_required_for_all_sources",
        ok=policy_meta.get("attribution_required_for_all_sources") is True,
        message="project policy requires attribution for every contributing source",
        details={"actual": policy_meta.get("attribution_required_for_all_sources")},
    )

    boundary = as_mapping(policy.get("dataset_boundary"))
    forbidden = {str(item) for item in as_list(boundary.get("forbidden_content"))}
    add_check(
        checks,
        name="forbidden_content_boundary",
        ok=REQUIRED_FORBIDDEN_CONTENT.issubset(forbidden),
        message="policy forbids high-risk content classes",
        details={"missing": sorted(REQUIRED_FORBIDDEN_CONTENT - forbidden)},
    )
    add_check(
        checks,
        name="unknown_field_fail_closed",
        ok=boundary.get("unknown_field_action") == "exclude_or_null",
        message="unknown fields fail closed by exclusion or nulling",
        details={"actual": boundary.get("unknown_field_action")},
    )
    add_check(
        checks,
        name="external_links_not_mirrored",
        ok=boundary.get("external_link_action") == "link_only_no_mirroring",
        message="external publication content is linked rather than mirrored",
        details={"actual": boundary.get("external_link_action")},
    )
    add_check(
        checks,
        name="canonical_truth_impact_none",
        ok=boundary.get("canonical_truth_impact") == "none",
        message="public release policy has no canonical truth impact",
        details={"actual": boundary.get("canonical_truth_impact")},
    )
    add_check(
        checks,
        name="public_rows_not_reconcile_input",
        ok=boundary.get("public_rows_may_be_used_as_reconcile_input") is False,
        message="public rows may not become reconciliation input",
        details={"actual": boundary.get("public_rows_may_be_used_as_reconcile_input")},
    )

    license_cfg = as_mapping(policy.get("compilation_license"))
    add_check(
        checks,
        name="compilation_license_pending_decision",
        ok=license_cfg.get("status") == "pending_explicit_release_decision",
        message="final compilation license remains an explicit release decision",
        details={"actual": license_cfg.get("status")},
    )
    add_check(
        checks,
        name="single_cc0_claim_forbidden",
        ok=license_cfg.get("single_cc0_claim_allowed") is False,
        message="mixed-source package cannot be declared entirely CC0 by default",
        details={"actual": license_cfg.get("single_cc0_claim_allowed")},
    )

    source_policies = as_mapping(policy.get("source_policies"))
    missing_sources = sorted(REQUIRED_SOURCE_FAMILIES - set(source_policies.keys()))
    add_check(
        checks,
        name="required_source_policies",
        ok=not missing_sources,
        message="all current canonical source families have explicit policies",
        details={"missing": missing_sources},
    )
    for source_name in sorted(REQUIRED_SOURCE_FAMILIES):
        source_cfg = as_mapping(source_policies.get(source_name))
        terms_url = str(source_cfg.get("terms_url") or "")
        add_check(
            checks,
            name=f"source_{source_name}_terms_url",
            ok=terms_url.startswith("https://"),
            message=f"{source_name} has an HTTPS terms/source-policy URL",
            details={"actual": terms_url},
        )
        add_check(
            checks,
            name=f"source_{source_name}_attribution",
            ok=source_cfg.get("attribution_required") is True,
            message=f"{source_name} attribution is required by project policy",
            details={"actual": source_cfg.get("attribution_required")},
        )
        add_check(
            checks,
            name=f"source_{source_name}_raw_payload_forbidden",
            ok=source_cfg.get("raw_payload_allowed") is False,
            message=f"{source_name} raw payload redistribution is forbidden",
            details={"actual": source_cfg.get("raw_payload_allowed")},
        )
        add_check(
            checks,
            name=f"source_{source_name}_content_redistribution_forbidden",
            ok=source_cfg.get("pdf_or_full_text_redistribution_allowed") is False,
            message=f"{source_name} PDF/full-text redistribution is forbidden",
            details={"actual": source_cfg.get("pdf_or_full_text_redistribution_allowed")},
        )

    acl = as_mapping(source_policies.get("acl_anthology"))
    add_check(
        checks,
        name="acl_abstract_year_rule",
        ok=(
            acl.get("public_abstract_allowed") == "source_aware_by_year"
            and acl.get("public_abstract_min_year") == 2016
            and acl.get("pre_2016_abstract_action") == "null"
        ),
        message="ACL public abstract handling is source-aware and fail-closed before 2016",
        details={
            "public_abstract_allowed": acl.get("public_abstract_allowed"),
            "public_abstract_min_year": acl.get("public_abstract_min_year"),
            "pre_2016_abstract_action": acl.get("pre_2016_abstract_action"),
        },
    )

    field_policies = as_mapping(policy.get("field_policies"))
    add_check(
        checks,
        name="abstract_source_aware_policy",
        ok=(
            as_mapping(field_policies.get("abstract")).get("action")
            == "source_aware_include_or_null"
            and as_mapping(field_policies.get("abstract")).get("fallback_action") == "null"
        ),
        message="abstract field is source-aware and fails closed to null",
        details={"actual": dict(as_mapping(field_policies.get("abstract")))},
    )
    add_check(
        checks,
        name="pdf_url_link_only_policy",
        ok=as_mapping(field_policies.get("pdf_url")).get("action") == "include_link_only_no_binary",
        message="pdf_url is represented as an external link only",
        details={"actual": dict(as_mapping(field_policies.get("pdf_url")))},
    )

    if dataset_config is not None:
        selected_columns = selected_columns_from_dataset_config(dataset_config)
        missing_fields = sorted(set(selected_columns) - set(field_policies.keys()))
        extra_fields = sorted(set(field_policies.keys()) - set(selected_columns))
        add_check(
            checks,
            name="field_policy_covers_dataset_columns",
            ok=not missing_fields,
            message="field policy covers every selected dataset column",
            details={"missing": missing_fields, "extra": extra_fields},
        )
        policy_ref = as_mapping(dataset_config.get("public_release_policy"))
        add_check(
            checks,
            name="dataset_config_policy_reference",
            ok=(
                policy_ref.get("path") == normalize_path(policy_path)
                and policy_ref.get("expected_schema_version") == SCHEMA_VERSION
                and policy_ref.get("required") is True
            ),
            message="dataset config references the validated policy contract",
            details={"reference": dict(policy_ref)},
        )

    packaging = as_mapping(policy.get("packaging"))
    required_files = {str(item) for item in as_list(packaging.get("required_files"))}
    add_check(
        checks,
        name="required_packaging_files",
        ok=REQUIRED_PACKAGING_FILES.issubset(required_files),
        message="policy requires dataset-card, attribution, field-policy, source-attribution, and Kaggle template files",
        details={"missing": sorted(REQUIRED_PACKAGING_FILES - required_files)},
    )
    add_check(
        checks,
        name="kaggle_template_only",
        ok=(
            packaging.get("kaggle_metadata_is_template_only") is True
            and packaging.get("kaggle_upload_command_in_scope") is False
        ),
        message="Kaggle metadata remains a template and upload is out of scope",
        details={
            "kaggle_metadata_is_template_only": packaging.get("kaggle_metadata_is_template_only"),
            "kaggle_upload_command_in_scope": packaging.get("kaggle_upload_command_in_scope"),
        },
    )

    if check_paths:
        add_check(
            checks,
            name="policy_path_exists",
            ok=policy_path.exists(),
            message="policy file exists",
            details={"path": normalize_path(policy_path)},
        )
        if dataset_config_path is not None:
            add_check(
                checks,
                name="dataset_config_path_exists",
                ok=dataset_config_path.exists(),
                message="dataset release config exists",
                details={"path": normalize_path(dataset_config_path)},
            )

    return checks


def build_report(
    *,
    policy_path: Path,
    dataset_config_path: Path | None,
    output_dir: Path,
    policy: Mapping[str, Any],
    checks: Sequence[CheckResult],
    strict: bool,
    check_paths: bool,
) -> dict[str, Any]:
    required_failed = [check for check in checks if check.severity == "required" and not check.ok]
    warnings = [check for check in checks if check.severity == "warning" and not check.ok]
    meta = as_mapping(policy.get("policy"))
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "report_name": "check_public_metadata_release_policy",
        "generated_at_utc": utc_now_iso(),
        "strict": bool(strict),
        "check_paths": bool(check_paths),
        "policy_path": normalize_path(policy_path),
        "dataset_config_path": normalize_path(dataset_config_path),
        "policy_id": meta.get("policy_id"),
        "policy_version": meta.get("version"),
        "policy_status": meta.get("status"),
        "publication_action_in_scope": meta.get("publication_action_in_scope"),
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
            "latest_json": normalize_path(output_dir / "public_metadata_release_policy_latest.json"),
            "latest_markdown": normalize_path(output_dir / "public_metadata_release_policy_latest.md"),
            "history_dir": normalize_path(output_dir / "history"),
        },
    }


def build_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Public Metadata Release Policy Validation",
        "",
        f"- schema_version: `{report.get('schema_version')}`",
        f"- generated_at_utc: `{report.get('generated_at_utc')}`",
        f"- ok: **{report.get('ok')}**",
        f"- strict: `{report.get('strict')}`",
        f"- policy_id: `{report.get('policy_id')}`",
        f"- policy_version: `{report.get('policy_version')}`",
        f"- policy_status: `{report.get('policy_status')}`",
        f"- publication_action_in_scope: `{report.get('publication_action_in_scope')}`",
        f"- required_failed_count: `{report.get('required_failed_count')}`",
        f"- warning_count: `{report.get('warning_count')}`",
        "",
        "## Interpretation",
        "",
        "A green report approves the policy contract for local candidate packaging.",
        "It does not upload or publish a dataset and does not choose a final compilation license.",
        "",
        "## Checks",
        "",
    ]
    for check in report.get("checks") or []:
        icon = "✅" if check.get("ok") else "❌"
        lines.append(f"- {icon} `{check.get('name')}` ({check.get('severity')}): {check.get('message')}")
    lines.append("")
    return "\n".join(lines)


def write_reports(report: Mapping[str, Any], output_dir: Path) -> tuple[Path, Path, Path, Path]:
    timestamp = utc_now_ts()
    history_dir = output_dir / "history"
    latest_json = output_dir / "public_metadata_release_policy_latest.json"
    latest_md = output_dir / "public_metadata_release_policy_latest.md"
    history_json = history_dir / f"public_metadata_release_policy_{timestamp}.json"
    history_md = history_dir / f"public_metadata_release_policy_{timestamp}.md"
    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(history_json, report)
    dump_text(history_md, build_markdown(report))
    return latest_json, latest_md, history_json, history_md


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the public metadata release policy contract.")
    parser.add_argument("--policy-path", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--dataset-config-path", type=Path, default=DEFAULT_DATASET_CONFIG_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--check-paths", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    policy = load_yaml(args.policy_path)
    dataset_config = load_yaml(args.dataset_config_path)
    checks = validate_policy(
        policy,
        policy_path=args.policy_path,
        dataset_config=dataset_config,
        dataset_config_path=args.dataset_config_path,
        check_paths=bool(args.check_paths),
    )
    report = build_report(
        policy_path=args.policy_path,
        dataset_config_path=args.dataset_config_path,
        output_dir=args.output_dir,
        policy=policy,
        checks=checks,
        strict=bool(args.strict),
        check_paths=bool(args.check_paths),
    )
    latest_json, latest_md, _history_json, _history_md = write_reports(report, args.output_dir)
    print(
        json.dumps(
            {
                "ok": report["ok"],
                "policy_id": report["policy_id"],
                "policy_version": report["policy_version"],
                "publication_action_in_scope": report["publication_action_in_scope"],
                "required_failed_count": report["required_failed_count"],
                "warning_count": report["warning_count"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    print(f"[report] {normalize_path(latest_json)}")
    print(f"[report] {normalize_path(latest_md)}")
    if args.strict and not report["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
