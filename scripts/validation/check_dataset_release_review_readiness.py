from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    import yaml
except ImportError as exc:  # pragma: no cover - project env is expected to include PyYAML
    yaml = None
    YAML_IMPORT_ERROR = exc
else:
    YAML_IMPORT_ERROR = None


REPORT_SCHEMA_VERSION = "dataset_release_review_readiness_v2"
DEFAULT_CONFIG_PATH = Path("configs/dataset_release.yaml")
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/validation")
DEFAULT_OUTPUT_VALIDATION_REPORT = DEFAULT_OUTPUT_DIR / "dataset_release_output_latest.json"
DEFAULT_POLICY_VALIDATION_REPORT = DEFAULT_OUTPUT_DIR / "public_metadata_release_policy_latest.json"
EXPECTED_POLICY_REPORT_SCHEMA_VERSION = "public_metadata_release_policy_quality_v1"
EXPECTED_OUTPUT_REPORT_SCHEMA_VERSION = "dataset_release_output_quality_v2"
EXPECTED_DATA_QUALITY_SUMMARY_SCHEMA_VERSION = "dataset_release_data_quality_summary_v1"
REQUIRED_REVIEW_FILES = {
    "manifest.json",
    "schema.json",
    "README.md",
    "DATASET_CARD.md",
    "ATTRIBUTION.md",
    "field_release_policy.json",
    "source_attribution.json",
    "kaggle_metadata.template.json",
    "data_quality_summary.json",
    "checksums.txt",
}
CORE_DATA_QUALITY_KEYS = {
    "schema_version",
    "row_count",
    "column_count",
    "canonical_id",
    "field_coverage",
    "source_family_counts",
    "publication_type_counts",
    "language_counts",
    "top_primary_categories",
    "source_count_distribution",
    "unique_source_count_distribution",
    "public_release_policy",
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


def as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def add_check(
    checks: list[CheckResult],
    *,
    name: str,
    ok: bool,
    message: str,
    severity: str = "required",
    details: dict[str, Any] | None = None,
) -> None:
    checks.append(CheckResult(name=name, ok=bool(ok), severity=severity, message=message, details=details))


def load_config(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML is required to read dataset release config") from YAML_IMPORT_ERROR
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Dataset release config must be a YAML mapping")
    return payload


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return payload


def project_root_from_config(config_path: Path) -> Path:
    return config_path.parent.parent if config_path.parent.name == "configs" else Path(".")


def release_dir_from_config(config: Mapping[str, Any], *, config_path: Path) -> Path:
    release = as_mapping(config.get("release"))
    export = as_mapping(config.get("export"))
    dataset_name = str(release.get("dataset_name") or "").strip()
    version = str(release.get("version") or "").strip()
    output_root = Path(str(export.get("output_root") or "data/datasets_release"))
    template = str(export.get("dataset_dir_template") or "{dataset_name}/{version}")
    rel_dir = template.format(dataset_name=dataset_name, version=version)
    return project_root_from_config(config_path) / output_root / rel_dir


def expected_row_count_from_config(config: Mapping[str, Any]) -> int | None:
    value = as_mapping(config.get("source_checkpoint")).get("expected_canonical_doc_count")
    return value if isinstance(value, int) else None


def read_json_if_exists(path: Path) -> tuple[dict[str, Any], bool, str | None]:
    if not path.exists():
        return {}, False, "file does not exist"
    try:
        return load_json(path), True, None
    except Exception as exc:  # pragma: no cover - defensive detail is reported
        return {}, False, str(exc)


def validate_review_readiness(
    config: Mapping[str, Any],
    *,
    config_path: Path,
    release_dir: Path,
    output_validation_report_path: Path,
    policy_validation_report_path: Path,
) -> list[CheckResult]:
    checks: list[CheckResult] = []
    safety = as_mapping(config.get("safety"))
    license_review = as_mapping(config.get("license_review"))

    add_check(
        checks,
        name="release_dir_exists",
        ok=release_dir.exists() and release_dir.is_dir(),
        message="Release directory exists",
        details={"release_dir": normalize_path(release_dir)},
    )

    existing_files = {path.name for path in release_dir.iterdir()} if release_dir.exists() else set()
    missing_review_files = sorted(REQUIRED_REVIEW_FILES - existing_files)
    add_check(
        checks,
        name="review_required_files_exist",
        ok=not missing_review_files,
        message=(
            "All review-readiness files exist"
            if not missing_review_files
            else "Review-readiness files are missing"
        ),
        details={"missing": missing_review_files},
    )

    manifest_path = release_dir / "manifest.json"
    schema_path = release_dir / "schema.json"
    readme_path = release_dir / "README.md"
    dataset_card_path = release_dir / "DATASET_CARD.md"
    attribution_path = release_dir / "ATTRIBUTION.md"
    data_quality_summary_path = release_dir / "data_quality_summary.json"

    manifest, manifest_ok, manifest_error = read_json_if_exists(manifest_path)
    add_check(
        checks,
        name="manifest_json_readable",
        ok=manifest_ok,
        message="manifest.json is readable",
        details={"error": manifest_error},
    )

    schema, schema_ok, schema_error = read_json_if_exists(schema_path)
    add_check(
        checks,
        name="schema_json_readable",
        ok=schema_ok,
        message="schema.json is readable",
        details={"error": schema_error},
    )

    data_quality_summary, data_quality_ok, data_quality_error = read_json_if_exists(data_quality_summary_path)
    add_check(
        checks,
        name="data_quality_summary_json_readable",
        ok=data_quality_ok,
        message="data_quality_summary.json is readable",
        details={"error": data_quality_error},
    )

    if readme_path.exists():
        readme_text = readme_path.read_text(encoding="utf-8")
        readme_lower = readme_text.lower()
        readme_mentions_boundary = (
            "not published" in readme_lower
            and (
                "release decision" in readme_lower
                or "manual_release_decision_required" in readme_lower
            )
            and "does not perform" in readme_lower
        )
    else:
        readme_mentions_boundary = False
    add_check(
        checks,
        name="readme_manual_review_boundary",
        ok=readme_mentions_boundary,
        message="README.md states that the candidate is not published and requires an explicit release decision",
    )

    dataset_card_text = dataset_card_path.read_text(encoding="utf-8") if dataset_card_path.exists() else ""
    add_check(
        checks,
        name="dataset_card_review_boundary",
        ok=(
            "not_published" in dataset_card_text.lower()
            and "final_compilation_license" in dataset_card_text.lower()
            and "attribution" in dataset_card_text.lower()
        ),
        message="DATASET_CARD.md records publication, licensing, and attribution boundaries",
    )
    attribution_text = attribution_path.read_text(encoding="utf-8") if attribution_path.exists() else ""
    add_check(
        checks,
        name="attribution_review_material_present",
        ok=(
            "arxiv" in attribution_text.lower()
            and "openalex" in attribution_text.lower()
            and "crossref" in attribution_text.lower()
            and "semantic scholar" in attribution_text.lower()
            and "acl anthology" in attribution_text.lower()
        ),
        message="ATTRIBUTION.md contains provider-level review material",
    )

    if manifest:
        manifest_safety = as_mapping(manifest.get("safety"))
        manifest_license_review = as_mapping(manifest.get("license_review"))
        manifest_files = as_mapping(manifest.get("files"))
        add_check(
            checks,
            name="manifest_schema_version",
            ok=manifest.get("schema_version") == "dataset_release_manifest_v2",
            message="manifest schema_version is dataset_release_manifest_v2",
            details={"actual": manifest.get("schema_version")},
        )
        add_check(
            checks,
            name="manifest_candidate_local_export_status",
            ok=manifest.get("status") == "candidate_local_export",
            message="manifest status is candidate_local_export",
            details={"actual": manifest.get("status")},
        )
        add_check(
            checks,
            name="manifest_not_published",
            ok=manifest.get("publication_status") == "not_published",
            message="manifest states that the dataset is not published",
            details={"actual": manifest.get("publication_status")},
        )
        add_check(
            checks,
            name="manifest_manual_review_required",
            ok=manifest.get("manual_review_required_before_publication") is True,
            message="manifest requires manual review before publication",
            details={"actual": manifest.get("manual_review_required_before_publication")},
        )
        add_check(
            checks,
            name="manifest_license_review_blocks_publication",
            ok=manifest_license_review.get("publication_allowed_before_review") is False,
            message="manifest license_review blocks publication before review",
            details={"actual": manifest_license_review.get("publication_allowed_before_review")},
        )
        add_check(
            checks,
            name="manifest_publish_without_manual_review_false",
            ok=manifest_safety.get("publish_without_manual_review") is False,
            message="manifest safety.publish_without_manual_review is False",
            details={"actual": manifest_safety.get("publish_without_manual_review")},
        )
        add_check(
            checks,
            name="manifest_canonical_truth_impact_none",
            ok=manifest_safety.get("canonical_truth_impact") == "none",
            message="manifest safety.canonical_truth_impact is none",
            details={"actual": manifest_safety.get("canonical_truth_impact")},
        )
        manifest_policy = as_mapping(manifest.get("public_release_policy"))
        add_check(
            checks,
            name="manifest_public_policy_ready",
            ok=(
                manifest.get("public_release_policy_validated_before_review") is True
                and manifest_policy.get("schema_version") == "public_metadata_release_policy_v1"
                and manifest_policy.get("publication_action_in_scope") is False
            ),
            message="manifest records a validated non-publishing public metadata policy",
            details={"public_release_policy": dict(manifest_policy)},
        )
        add_check(
            checks,
            name="manifest_lists_review_files",
            ok=(
                manifest_files.get("schema") == "schema.json"
                and manifest_files.get("manifest") == "manifest.json"
                and manifest_files.get("readme") == "README.md"
                and manifest_files.get("dataset_card") == "DATASET_CARD.md"
                and manifest_files.get("attribution") == "ATTRIBUTION.md"
                and manifest_files.get("field_release_policy") == "field_release_policy.json"
                and manifest_files.get("source_attribution") == "source_attribution.json"
                and manifest_files.get("kaggle_metadata_template") == "kaggle_metadata.template.json"
                and manifest_files.get("data_quality_summary") == "data_quality_summary.json"
                and manifest_files.get("checksums") == "checksums.txt"
            ),
            message="manifest files section lists all review-readiness files",
            details={"files": dict(manifest_files)},
        )

    add_check(
        checks,
        name="config_publish_without_manual_review_false",
        ok=safety.get("publish_without_manual_review") is False,
        message="config safety.publish_without_manual_review is False",
        details={"actual": safety.get("publish_without_manual_review")},
    )
    add_check(
        checks,
        name="config_publication_allowed_before_review_false",
        ok=license_review.get("publication_allowed_before_review") is False,
        message="config license_review.publication_allowed_before_review is False",
        details={"actual": license_review.get("publication_allowed_before_review")},
    )

    if data_quality_summary:
        missing_quality_keys = sorted(CORE_DATA_QUALITY_KEYS - set(data_quality_summary.keys()))
        canonical_id_summary = as_mapping(data_quality_summary.get("canonical_id"))
        expected_row_count = expected_row_count_from_config(config)
        add_check(
            checks,
            name="data_quality_summary_schema_version",
            ok=data_quality_summary.get("schema_version") == EXPECTED_DATA_QUALITY_SUMMARY_SCHEMA_VERSION,
            message=f"data_quality_summary schema_version is {EXPECTED_DATA_QUALITY_SUMMARY_SCHEMA_VERSION}",
            details={"actual": data_quality_summary.get("schema_version")},
        )
        add_check(
            checks,
            name="data_quality_summary_core_metrics_present",
            ok=not missing_quality_keys,
            message="data_quality_summary contains core review metrics",
            details={"missing": missing_quality_keys},
        )
        add_check(
            checks,
            name="data_quality_summary_expected_row_count",
            ok=(expected_row_count is None or data_quality_summary.get("row_count") == expected_row_count),
            message="data_quality_summary row_count matches expected canonical checkpoint",
            details={"expected": expected_row_count, "actual": data_quality_summary.get("row_count")},
        )
        add_check(
            checks,
            name="data_quality_summary_no_duplicate_canonical_ids",
            ok=canonical_id_summary.get("duplicate_count") == 0,
            message="data_quality_summary reports zero duplicate canonical IDs",
            details={"duplicate_count": canonical_id_summary.get("duplicate_count")},
        )

    output_report, output_report_ok, output_report_error = read_json_if_exists(output_validation_report_path)
    add_check(
        checks,
        name="output_validation_report_readable",
        ok=output_report_ok,
        message="Dataset release output validation report is readable",
        details={"path": normalize_path(output_validation_report_path), "error": output_report_error},
    )
    if output_report:
        add_check(
            checks,
            name="output_validation_report_schema_version",
            ok=output_report.get("schema_version") == EXPECTED_OUTPUT_REPORT_SCHEMA_VERSION,
            message=f"Output validation report schema_version is {EXPECTED_OUTPUT_REPORT_SCHEMA_VERSION}",
            details={"actual": output_report.get("schema_version")},
        )
        add_check(
            checks,
            name="output_validation_report_ok",
            ok=output_report.get("ok") is True,
            message="Output validation report is green",
            details={"actual": output_report.get("ok")},
        )
        add_check(
            checks,
            name="output_validation_report_required_failed_count_zero",
            ok=output_report.get("required_failed_count") == 0,
            message="Output validation report has no required failures",
            details={"actual": output_report.get("required_failed_count")},
        )
        report_release_dir = output_report.get("release_dir")
        add_check(
            checks,
            name="output_validation_report_release_dir_matches",
            ok=report_release_dir == normalize_path(release_dir),
            message="Output validation report points to the same release directory",
            details={"expected": normalize_path(release_dir), "actual": report_release_dir},
        )

    policy_report, policy_report_ok, policy_report_error = read_json_if_exists(
        policy_validation_report_path
    )
    add_check(
        checks,
        name="policy_validation_report_readable",
        ok=policy_report_ok,
        message="Public metadata release policy validation report is readable",
        details={"path": normalize_path(policy_validation_report_path), "error": policy_report_error},
    )
    if policy_report:
        add_check(
            checks,
            name="policy_validation_report_schema_version",
            ok=policy_report.get("schema_version") == EXPECTED_POLICY_REPORT_SCHEMA_VERSION,
            message=f"Policy validation report schema_version is {EXPECTED_POLICY_REPORT_SCHEMA_VERSION}",
            details={"actual": policy_report.get("schema_version")},
        )
        add_check(
            checks,
            name="policy_validation_report_ok",
            ok=policy_report.get("ok") is True,
            message="Public metadata release policy validation report is green",
            details={"actual": policy_report.get("ok")},
        )
        add_check(
            checks,
            name="policy_validation_report_required_failed_count_zero",
            ok=policy_report.get("required_failed_count") == 0,
            message="Public metadata release policy report has no required failures",
            details={"actual": policy_report.get("required_failed_count")},
        )
        policy_ref = as_mapping(config.get("public_release_policy"))
        add_check(
            checks,
            name="policy_validation_report_path_matches",
            ok=policy_report.get("policy_path") == policy_ref.get("path"),
            message="Policy validation report points to the configured policy path",
            details={"expected": policy_ref.get("path"), "actual": policy_report.get("policy_path")},
        )
        add_check(
            checks,
            name="policy_validation_report_no_publication_action",
            ok=policy_report.get("publication_action_in_scope") is False,
            message="Policy validation report confirms publication action is out of scope",
            details={"actual": policy_report.get("publication_action_in_scope")},
        )

    if schema:
        primary_key = as_list(schema.get("primary_key"))
        add_check(
            checks,
            name="schema_primary_key_canonical_id",
            ok=primary_key == ["canonical_id"],
            message="schema.json primary key is canonical_id",
            details={"actual": primary_key},
        )

    return checks


def build_report(
    *,
    config_path: Path,
    release_dir: Path,
    output_validation_report_path: Path,
    policy_validation_report_path: Path,
    output_dir: Path,
    checks: Sequence[CheckResult],
    strict: bool,
) -> dict[str, Any]:
    required_failed = [check for check in checks if check.severity == "required" and not check.ok]
    warnings = [check for check in checks if check.severity == "warning" and not check.ok]
    technical_candidate_ready = len(required_failed) == 0
    public_policy_ready = technical_candidate_ready
    manual_review_required = True
    manual_release_decision_required = True
    publication_ready = False
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "report_name": "check_dataset_release_review_readiness",
        "generated_at_utc": utc_now_iso(),
        "strict": bool(strict),
        "config_path": normalize_path(config_path),
        "release_dir": normalize_path(release_dir),
        "output_validation_report_path": normalize_path(output_validation_report_path),
        "policy_validation_report_path": normalize_path(policy_validation_report_path),
        "technical_candidate_ready": technical_candidate_ready,
        "public_policy_ready": public_policy_ready,
        "manual_review_required": manual_review_required,
        "manual_release_decision_required": manual_release_decision_required,
        "publication_ready": publication_ready,
        "publication_block_reason": "public_release_decision_not_completed",
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
        "ok": technical_candidate_ready,
        "outputs": {
            "output_dir": normalize_path(output_dir),
            "latest_json": normalize_path(output_dir / "dataset_release_review_readiness_latest.json"),
            "latest_markdown": normalize_path(output_dir / "dataset_release_review_readiness_latest.md"),
        },
    }


def build_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Dataset Release Review Readiness",
        "",
        f"- schema_version: `{report.get('schema_version')}`",
        f"- generated_at_utc: `{report.get('generated_at_utc')}`",
        f"- ok: **{report.get('ok')}**",
        f"- strict: `{report.get('strict')}`",
        f"- technical_candidate_ready: `{report.get('technical_candidate_ready')}`",
        f"- public_policy_ready: `{report.get('public_policy_ready')}`",
        f"- manual_review_required: `{report.get('manual_review_required')}`",
        f"- manual_release_decision_required: `{report.get('manual_release_decision_required')}`",
        f"- publication_ready: `{report.get('publication_ready')}`",
        f"- publication_block_reason: `{report.get('publication_block_reason')}`",
        f"- config_path: `{report.get('config_path')}`",
        f"- release_dir: `{report.get('release_dir')}`",
        f"- output_validation_report_path: `{report.get('output_validation_report_path')}`",
        f"- policy_validation_report_path: `{report.get('policy_validation_report_path')}`",
        f"- required_failed_count: `{report.get('required_failed_count')}`",
        f"- warning_count: `{report.get('warning_count')}`",
        "",
        "## Interpretation",
        "",
        "A green report means the local candidate package and source-aware policy are technically ready for an explicit release decision.",
        "It does not approve or perform public publication.",
        "",
        "## Checks",
        "",
    ]
    for check in report.get("checks") or []:
        icon = "✅" if check.get("ok") else "❌"
        lines.append(f"- {icon} `{check.get('name')}` ({check.get('severity')}): {check.get('message')}")
    lines.append("")
    failed = report.get("required_failed_checks") or []
    if failed:
        lines.append("## Required failures")
        lines.append("")
        for name in failed:
            lines.append(f"- `{name}`")
        lines.append("")
    return "\n".join(lines) + "\n"


def write_reports(report: Mapping[str, Any], output_dir: Path) -> tuple[Path, Path, Path, Path]:
    latest_json = output_dir / "dataset_release_review_readiness_latest.json"
    latest_md = output_dir / "dataset_release_review_readiness_latest.md"
    history_dir = output_dir / "history"
    ts = utc_now_ts()
    history_json = history_dir / f"dataset_release_review_readiness_{ts}.json"
    history_md = history_dir / f"dataset_release_review_readiness_{ts}.md"
    markdown = build_markdown(report)

    dump_json(latest_json, report)
    dump_text(latest_md, markdown)
    dump_json(history_json, report)
    dump_text(history_md, markdown)
    return latest_json, latest_md, history_json, history_md


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Check whether a generated local candidate dataset release is technically ready "
            "for manual review. This does not approve public publication."
        )
    )
    parser.add_argument("--config-path", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--release-dir", type=Path, default=None)
    parser.add_argument("--output-validation-report", type=Path, default=DEFAULT_OUTPUT_VALIDATION_REPORT)
    parser.add_argument("--policy-validation-report", type=Path, default=DEFAULT_POLICY_VALIDATION_REPORT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = Path(args.config_path)
    config = load_config(config_path)
    release_dir = Path(args.release_dir) if args.release_dir else release_dir_from_config(config, config_path=config_path)
    output_validation_report_path = Path(args.output_validation_report)
    policy_validation_report_path = Path(args.policy_validation_report)
    output_dir = Path(args.output_dir)

    checks = validate_review_readiness(
        config,
        config_path=config_path,
        release_dir=release_dir,
        output_validation_report_path=output_validation_report_path,
        policy_validation_report_path=policy_validation_report_path,
    )
    report = build_report(
        config_path=config_path,
        release_dir=release_dir,
        output_validation_report_path=output_validation_report_path,
        policy_validation_report_path=policy_validation_report_path,
        output_dir=output_dir,
        checks=checks,
        strict=bool(args.strict),
    )
    latest_json, latest_md, history_json, history_md = write_reports(report, output_dir)

    status = "OK" if report["ok"] else "FAILED"
    print(f"[{status}] schema_version={report['schema_version']}")
    print(f"[{status}] technical_candidate_ready={report['technical_candidate_ready']}")
    print(f"[{status}] public_policy_ready={report['public_policy_ready']}")
    print(f"[{status}] manual_release_decision_required={report['manual_release_decision_required']}")
    print(f"[{status}] manual_review_required={report['manual_review_required']}")
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
