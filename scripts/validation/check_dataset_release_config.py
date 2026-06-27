from __future__ import annotations

import argparse
import json
import yaml
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "dataset_release_config_v1"
REPORT_SCHEMA_VERSION = "dataset_release_config_quality_v1"

DEFAULT_CONFIG_PATH = Path("configs/dataset_release.yaml")
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/validation")

ALLOWED_RELEASE_FAMILIES = {
    "clean_research_metadata",
    "paper_artifact_links",
    "topic_discovery_artifacts",
    "research_graph_export",
    "temporal_trends",
    "retrieval_evaluation_dataset",
}

ALLOWED_EXPORT_FORMATS = {
    "parquet",
    "csv",
    "jsonl",
}

REQUIRED_TOP_LEVEL_KEYS = {
    "schema_version",
    "release",
    "source_checkpoint",
    "export",
    "columns",
    "validation",
    "license_review",
    "safety",
}

REQUIRED_RELEASE_KEYS = {
    "dataset_name",
    "version",
    "release_family",
    "status",
}

REQUIRED_SOURCE_CHECKPOINT_KEYS = {
    "canonical_corpus_path",
    "expected_canonical_doc_count",
}

REQUIRED_COLUMN_NAMES = {
    "canonical_id",
    "title",
    "authors",
    "year",
    "source_count",
    "unique_source_count",
}

FORBIDDEN_V0_1_EXPORT_FLAGS = {
    "include_embeddings": False,
    "include_raw_provider_payloads": False,
    "include_source_records": False,
    "include_full_text": False,
    "include_pdfs": False,
    "include_private_notes": False,
}

REQUIRED_SAFETY_FLAGS = {
    "canonical_truth_impact": "none",
    "may_overwrite_operational_latest": False,
    "may_be_used_as_reconcile_input": False,
    "may_include_full_text": False,
    "may_include_pdfs": False,
    "may_include_embeddings_without_review": False,
    "publish_without_manual_review": False,
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
    checks.append(
        CheckResult(
            name=name,
            ok=bool(ok),
            severity=severity,
            message=message,
            details=details,
        )
    )


def load_config(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError(
            "PyYAML is required to read dataset release config"
        ) from YAML_IMPORT_ERROR

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Dataset release config must be a YAML mapping")
    return payload


def validate_config(
    config: Mapping[str, Any],
    *,
    config_path: Path,
    check_paths: bool = False,
) -> list[CheckResult]:
    checks: list[CheckResult] = []

    missing_top = sorted(REQUIRED_TOP_LEVEL_KEYS - set(config.keys()))
    add_check(
        checks,
        name="required_top_level_keys",
        ok=not missing_top,
        message=(
            "All required top-level sections are present"
            if not missing_top
            else "Missing required top-level sections"
        ),
        details={"missing": missing_top},
    )

    add_check(
        checks,
        name="schema_version",
        ok=config.get("schema_version") == SCHEMA_VERSION,
        message=f"schema_version must be {SCHEMA_VERSION}",
        details={"actual": config.get("schema_version")},
    )

    release = as_mapping(config.get("release"))
    missing_release = sorted(REQUIRED_RELEASE_KEYS - set(release.keys()))
    add_check(
        checks,
        name="release_required_fields",
        ok=not missing_release,
        message=(
            "Release metadata contains required fields"
            if not missing_release
            else "Release metadata is missing required fields"
        ),
        details={"missing": missing_release},
    )

    dataset_name = release.get("dataset_name")
    add_check(
        checks,
        name="release_dataset_name",
        ok=isinstance(dataset_name, str) and bool(dataset_name.strip()),
        message="release.dataset_name must be a non-empty string",
        details={"actual": dataset_name},
    )

    version = release.get("version")
    add_check(
        checks,
        name="release_version",
        ok=isinstance(version, str) and version.startswith("v"),
        message="release.version must be a version string starting with 'v'",
        details={"actual": version},
    )

    family = release.get("release_family")
    add_check(
        checks,
        name="release_family",
        ok=family in ALLOWED_RELEASE_FAMILIES,
        message="release.release_family must be an allowed release family",
        details={
            "actual": family,
            "allowed": sorted(ALLOWED_RELEASE_FAMILIES),
        },
    )

    publication_targets = as_list(release.get("publication_targets"))
    add_check(
        checks,
        name="publication_targets",
        ok=all(isinstance(item, str) and item for item in publication_targets),
        message="publication_targets must be a list of non-empty strings",
        details={"actual": publication_targets},
        severity="warning",
    )

    source = as_mapping(config.get("source_checkpoint"))
    missing_source = sorted(REQUIRED_SOURCE_CHECKPOINT_KEYS - set(source.keys()))
    add_check(
        checks,
        name="source_checkpoint_required_fields",
        ok=not missing_source,
        message=(
            "Source checkpoint contains required fields"
            if not missing_source
            else "Source checkpoint is missing required fields"
        ),
        details={"missing": missing_source},
    )

    expected_count = source.get("expected_canonical_doc_count")
    add_check(
        checks,
        name="expected_canonical_doc_count",
        ok=isinstance(expected_count, int) and expected_count > 0,
        message="expected_canonical_doc_count must be a positive integer",
        details={"actual": expected_count},
    )

    retrieval_count = source.get("retrieval_corpus_doc_count")
    if retrieval_count is not None:
        add_check(
            checks,
            name="retrieval_corpus_doc_count",
            ok=isinstance(retrieval_count, int) and retrieval_count > 0,
            message="retrieval_corpus_doc_count must be a positive integer when provided",
            details={"actual": retrieval_count},
        )

    retrieval_build_id = source.get("retrieval_build_id")
    add_check(
        checks,
        name="retrieval_build_id_present",
        ok=isinstance(retrieval_build_id, str) and bool(retrieval_build_id.strip()),
        message="retrieval_build_id should be recorded for the current metadata release contract",
        details={"actual": retrieval_build_id},
    )

    export = as_mapping(config.get("export"))
    export_format = export.get("format")
    add_check(
        checks,
        name="export_format",
        ok=export_format in ALLOWED_EXPORT_FORMATS,
        message="export.format must be one of the allowed formats",
        details={
            "actual": export_format,
            "allowed": sorted(ALLOWED_EXPORT_FORMATS),
        },
    )

    output_root = export.get("output_root")
    add_check(
        checks,
        name="output_root",
        ok=isinstance(output_root, str) and bool(output_root.strip()),
        message="export.output_root must be a non-empty string",
        details={"actual": output_root},
    )

    deterministic_order_by = as_list(export.get("deterministic_order_by"))
    add_check(
        checks,
        name="deterministic_order_by",
        ok="canonical_id" in deterministic_order_by,
        message="export.deterministic_order_by should include canonical_id",
        details={"actual": deterministic_order_by},
    )

    for flag, expected in FORBIDDEN_V0_1_EXPORT_FLAGS.items():
        add_check(
            checks,
            name=f"export_{flag}",
            ok=export.get(flag) is expected,
            message=f"export.{flag} must be {expected} for metadata-only v0.1",
            details={"actual": export.get(flag), "expected": expected},
        )

    columns = as_mapping(config.get("columns"))
    required_columns = set(str(item) for item in as_list(columns.get("required")))
    optional_columns = set(str(item) for item in as_list(columns.get("optional")))
    forbidden_columns = set(str(item) for item in as_list(columns.get("forbidden")))

    missing_required_columns = sorted(REQUIRED_COLUMN_NAMES - required_columns)
    add_check(
        checks,
        name="required_columns",
        ok=not missing_required_columns,
        message=(
            "Required release columns contain the minimum contract"
            if not missing_required_columns
            else "Required release columns miss minimum contract columns"
        ),
        details={
            "missing": missing_required_columns,
            "minimum_required": sorted(REQUIRED_COLUMN_NAMES),
        },
    )

    add_check(
        checks,
        name="canonical_id_not_forbidden",
        ok="canonical_id" not in forbidden_columns,
        message="canonical_id must not be listed as forbidden",
        details={"forbidden_columns": sorted(forbidden_columns)},
    )

    overlap_required_forbidden = sorted(required_columns & forbidden_columns)
    add_check(
        checks,
        name="required_forbidden_overlap",
        ok=not overlap_required_forbidden,
        message=(
            "Required and forbidden columns do not overlap"
            if not overlap_required_forbidden
            else "Required and forbidden columns overlap"
        ),
        details={"overlap": overlap_required_forbidden},
    )

    overlap_optional_forbidden = sorted(optional_columns & forbidden_columns)
    add_check(
        checks,
        name="optional_forbidden_overlap",
        ok=not overlap_optional_forbidden,
        message=(
            "Optional and forbidden columns do not overlap"
            if not overlap_optional_forbidden
            else "Optional and forbidden columns overlap"
        ),
        details={"overlap": overlap_optional_forbidden},
    )

    validation = as_mapping(config.get("validation"))
    required_validation_flags = {
        "require_unique_canonical_id",
        "require_expected_row_count",
        "require_non_empty_title",
        "require_manifest_json",
        "require_schema_json",
        "require_checksums_txt",
        "require_readme_md",
        "require_data_file",
        "require_data_quality_summary_json",
        "require_deterministic_order",
        "require_no_forbidden_columns",
        "require_build_metadata",
    }

    missing_validation_flags = sorted(
        name
        for name in required_validation_flags
        if validation.get(name) is not True
    )
    add_check(
        checks,
        name="validation_required_flags",
        ok=not missing_validation_flags,
        message=(
            "Validation requirements include required release-output gates"
            if not missing_validation_flags
            else "Validation requirements are missing required true flags"
        ),
        details={"missing_or_not_true": missing_validation_flags},
    )

    license_review = as_mapping(config.get("license_review"))
    add_check(
        checks,
        name="license_review_required",
        ok=license_review.get("status") == "required_before_publication",
        message="license_review.status must be required_before_publication",
        details={"actual": license_review.get("status")},
    )

    add_check(
        checks,
        name="publication_blocked_before_review",
        ok=license_review.get("publication_allowed_before_review") is False,
        message="publication_allowed_before_review must be false",
        details={"actual": license_review.get("publication_allowed_before_review")},
    )

    safety = as_mapping(config.get("safety"))
    for name, expected in REQUIRED_SAFETY_FLAGS.items():
        add_check(
            checks,
            name=f"safety_{name}",
            ok=safety.get(name) == expected,
            message=f"safety.{name} must be {expected!r}",
            details={"actual": safety.get(name), "expected": expected},
        )

    outputs = as_mapping(config.get("outputs"))
    expected_layout = set(
        str(item)
        for item in as_list(outputs.get("expected_release_layout"))
    )
    required_layout = {
        "data.parquet",
        "schema.json",
        "manifest.json",
        "README.md",
        "data_quality_summary.json",
        "checksums.txt",
    }
    missing_layout = sorted(required_layout - expected_layout)
    add_check(
        checks,
        name="expected_release_layout",
        ok=not missing_layout,
        message=(
            "Expected release layout contains required files"
            if not missing_layout
            else "Expected release layout is missing required files"
        ),
        details={"missing": missing_layout},
    )

    if check_paths:
        root = config_path.parent.parent if config_path.parent.name == "configs" else Path(".")
        canonical_path = root / str(source.get("canonical_corpus_path", ""))
        manifest_path = root / str(source.get("retrieval_manifest_path", ""))
        add_check(
            checks,
            name="path_canonical_corpus_exists",
            ok=canonical_path.exists(),
            message="canonical_corpus_path exists",
            details={"path": normalize_path(canonical_path)},
        )
        add_check(
            checks,
            name="path_retrieval_manifest_exists",
            ok=manifest_path.exists(),
            message="retrieval_manifest_path exists",
            details={"path": normalize_path(manifest_path)},
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
    required_failed = [
        check
        for check in checks
        if check.severity == "required" and not check.ok
    ]
    warnings = [
        check
        for check in checks
        if check.severity == "warning" and not check.ok
    ]

    release = as_mapping(config.get("release"))
    source = as_mapping(config.get("source_checkpoint"))
    export = as_mapping(config.get("export"))

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "report_name": "check_dataset_release_config",
        "generated_at_utc": utc_now_iso(),
        "strict": bool(strict),
        "check_paths": bool(check_paths),
        "config_path": normalize_path(config_path),
        "summary": {
            "dataset_name": release.get("dataset_name"),
            "version": release.get("version"),
            "release_family": release.get("release_family"),
            "status": release.get("status"),
            "expected_canonical_doc_count": source.get("expected_canonical_doc_count"),
            "retrieval_build_id": source.get("retrieval_build_id"),
            "export_format": export.get("format"),
            "include_embeddings": export.get("include_embeddings"),
            "include_full_text": export.get("include_full_text"),
            "include_pdfs": export.get("include_pdfs"),
            "include_raw_provider_payloads": export.get("include_raw_provider_payloads"),
        },
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
            "output_dir": normalize_path(output_dir),
            "latest_json": normalize_path(output_dir / "dataset_release_config_latest.json"),
            "latest_markdown": normalize_path(output_dir / "dataset_release_config_latest.md"),
        },
    }


def build_markdown(report: Mapping[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Dataset Release Config Validation")
    lines.append("")
    lines.append(f"- schema_version: `{report.get('schema_version')}`")
    lines.append(f"- generated_at_utc: `{report.get('generated_at_utc')}`")
    lines.append(f"- ok: **{report.get('ok')}**")
    lines.append(f"- strict: `{report.get('strict')}`")
    lines.append(f"- check_paths: `{report.get('check_paths')}`")
    lines.append(f"- required_failed_count: `{report.get('required_failed_count')}`")
    lines.append(f"- warning_count: `{report.get('warning_count')}`")
    lines.append("")

    summary = as_mapping(report.get("summary"))
    lines.append("## Summary")
    lines.append("")
    for name, value in summary.items():
        lines.append(f"- {name}: `{value}`")
    lines.append("")

    lines.append("## Checks")
    lines.append("")
    for check in report.get("checks") or []:
        icon = "✅" if check.get("ok") else "❌"
        lines.append(
            f"- {icon} `{check.get('name')}` "
            f"({check.get('severity')}): {check.get('message')}"
        )
    lines.append("")

    failed = report.get("required_failed_checks") or []
    if failed:
        lines.append("## Required failures")
        lines.append("")
        for name in failed:
            lines.append(f"- `{name}`")
        lines.append("")

    warnings = report.get("warnings") or []
    if warnings:
        lines.append("## Warnings")
        lines.append("")
        for name in warnings:
            lines.append(f"- `{name}`")
        lines.append("")

    return "\n".join(lines) + "\n"


def write_reports(report: Mapping[str, Any], output_dir: Path) -> tuple[Path, Path, Path, Path]:
    latest_json = output_dir / "dataset_release_config_latest.json"
    latest_md = output_dir / "dataset_release_config_latest.md"
    history_dir = output_dir / "history"
    ts = utc_now_ts()
    history_json = history_dir / f"dataset_release_config_{ts}.json"
    history_md = history_dir / f"dataset_release_config_{ts}.md"

    markdown = build_markdown(report)

    dump_json(latest_json, report)
    dump_text(latest_md, markdown)
    dump_json(history_json, report)
    dump_text(history_md, markdown)

    return latest_json, latest_md, history_json, history_md


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the ML Research Radar dataset-release configuration "
            "contract. This does not export or publish a dataset."
        )
    )
    parser.add_argument(
        "--config-path",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Run the accepted strict config gate. Warnings do not fail the gate.",
    )
    parser.add_argument(
        "--check-paths",
        action="store_true",
        help="Also verify configured source paths exist in the local checkout.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = Path(args.config_path)
    output_dir = Path(args.output_dir)

    config = load_config(config_path)
    checks = validate_config(
        config,
        config_path=config_path,
        check_paths=bool(args.check_paths),
    )
    report = build_report(
        config_path=config_path,
        output_dir=output_dir,
        config=config,
        checks=checks,
        strict=bool(args.strict),
        check_paths=bool(args.check_paths),
    )
    latest_json, latest_md, history_json, history_md = write_reports(
        report,
        output_dir,
    )

    status = "OK" if report["ok"] else "FAILED"
    print(f"[{status}] schema_version={report['schema_version']}")
    print(f"[{status}] required_failed_count={report['required_failed_count']}")
    print(f"[{status}] latest JSON: {latest_json}")
    print(f"[{status}] latest Markdown: {latest_md}")
    print(f"[{status}] history JSON: {history_json}")
    print(f"[{status}] history Markdown: {history_md}")

    if report["required_failed_count"]:
        print("[FAILED] Required checks:")
        for name in report["required_failed_checks"]:
            print(f"- {name}")

    if report["warning_count"]:
        print("[WARN] Warnings:")
        for name in report["warnings"]:
            print(f"- {name}")

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
