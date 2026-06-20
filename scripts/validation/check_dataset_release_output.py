from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    import pandas as pd
except ImportError as exc:  # pragma: no cover - project env is expected to include pandas
    pd = None
    PANDAS_IMPORT_ERROR = exc
else:
    PANDAS_IMPORT_ERROR = None

try:
    import yaml
except ImportError as exc:  # pragma: no cover - project env is expected to include PyYAML
    yaml = None
    YAML_IMPORT_ERROR = exc
else:
    YAML_IMPORT_ERROR = None


REPORT_SCHEMA_VERSION = "dataset_release_output_quality_v1"
DEFAULT_CONFIG_PATH = Path("configs/dataset_release.yaml")
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/validation")
REQUIRED_OUTPUT_FILES = {
    "data.parquet",
    "schema.json",
    "manifest.json",
    "README.md",
    "data_quality_summary.json",
    "checksums.txt",
}
REQUIRED_SAFETY_VALUES = {
    "canonical_truth_impact": "none",
    "may_overwrite_operational_latest": False,
    "may_be_used_as_reconcile_input": False,
    "may_include_full_text": False,
    "may_include_pdfs": False,
    "may_include_embeddings_without_review": False,
    "publish_without_manual_review": False,
}
REQUIRED_EXPORT_FALSE_FLAGS = {
    "include_embeddings": False,
    "include_raw_provider_payloads": False,
    "include_source_records": False,
    "include_full_text": False,
    "include_pdfs": False,
    "include_private_notes": False,
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


def expected_columns_from_config(config: Mapping[str, Any]) -> list[str]:
    columns = as_mapping(config.get("columns"))
    selected: list[str] = []
    seen: set[str] = set()
    for item in as_list(columns.get("required")) + as_list(columns.get("optional")):
        name = str(item)
        if name and name not in seen:
            selected.append(name)
            seen.add(name)
    return selected


def forbidden_columns_from_config(config: Mapping[str, Any]) -> set[str]:
    columns = as_mapping(config.get("columns"))
    return {str(item) for item in as_list(columns.get("forbidden")) if str(item)}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_checksums(path: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2:
            raise ValueError(f"Invalid checksum line {line_no}: {line}")
        digest, filename = parts
        checksums[filename] = digest
    return checksums


def is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def load_parquet(path: Path):
    if pd is None:
        raise RuntimeError("pandas is required to validate the dataset export") from PANDAS_IMPORT_ERROR
    return pd.read_parquet(path)


def validate_release_output(
    config: Mapping[str, Any],
    *,
    config_path: Path,
    release_dir: Path,
) -> list[CheckResult]:
    checks: list[CheckResult] = []
    export = as_mapping(config.get("export"))
    validation = as_mapping(config.get("validation"))
    source = as_mapping(config.get("source_checkpoint"))
    safety = as_mapping(config.get("safety"))

    add_check(
        checks,
        name="release_dir_exists",
        ok=release_dir.exists() and release_dir.is_dir(),
        message="Release directory exists",
        details={"release_dir": normalize_path(release_dir)},
    )

    output_root = project_root_from_config(config_path) / str(export.get("output_root") or "data/datasets_release")
    add_check(
        checks,
        name="release_dir_under_output_root",
        ok=is_under(release_dir, output_root),
        message="Release directory is under configured data/datasets_release output root",
        details={
            "release_dir": normalize_path(release_dir),
            "output_root": normalize_path(output_root),
        },
    )

    existing_files = {path.name for path in release_dir.iterdir()} if release_dir.exists() else set()
    missing_files = sorted(REQUIRED_OUTPUT_FILES - existing_files)
    add_check(
        checks,
        name="required_output_files",
        ok=not missing_files,
        message="All required release output files exist" if not missing_files else "Release output is missing required files",
        details={"missing": missing_files},
    )

    data_path = release_dir / "data.parquet"
    schema_path = release_dir / "schema.json"
    manifest_path = release_dir / "manifest.json"
    readme_path = release_dir / "README.md"
    data_quality_summary_path = release_dir / "data_quality_summary.json"
    checksums_path = release_dir / "checksums.txt"

    frame = None
    if data_path.exists():
        try:
            frame = load_parquet(data_path)
            parquet_ok = True
            parquet_error = None
        except Exception as exc:  # pragma: no cover - defensive detail is reported
            parquet_ok = False
            parquet_error = str(exc)
        add_check(
            checks,
            name="data_parquet_readable",
            ok=parquet_ok,
            message="data.parquet is readable",
            details={"error": parquet_error},
        )

    schema: dict[str, Any] = {}
    if schema_path.exists():
        try:
            schema = load_json(schema_path)
            schema_ok = True
            schema_error = None
        except Exception as exc:  # pragma: no cover - defensive detail is reported
            schema_ok = False
            schema_error = str(exc)
        add_check(
            checks,
            name="schema_json_readable",
            ok=schema_ok,
            message="schema.json is readable",
            details={"error": schema_error},
        )

    manifest: dict[str, Any] = {}
    if manifest_path.exists():
        try:
            manifest = load_json(manifest_path)
            manifest_ok = True
            manifest_error = None
        except Exception as exc:  # pragma: no cover - defensive detail is reported
            manifest_ok = False
            manifest_error = str(exc)
        add_check(
            checks,
            name="manifest_json_readable",
            ok=manifest_ok,
            message="manifest.json is readable",
            details={"error": manifest_error},
        )


    data_quality_summary: dict[str, Any] = {}
    if data_quality_summary_path.exists():
        try:
            data_quality_summary = load_json(data_quality_summary_path)
            data_quality_summary_ok = True
            data_quality_summary_error = None
        except Exception as exc:  # pragma: no cover - defensive detail is reported
            data_quality_summary_ok = False
            data_quality_summary_error = str(exc)
        add_check(
            checks,
            name="data_quality_summary_json_readable",
            ok=data_quality_summary_ok,
            message="data_quality_summary.json is readable",
            details={"error": data_quality_summary_error},
        )

    if readme_path.exists():
        readme_text = readme_path.read_text(encoding="utf-8")
        add_check(
            checks,
            name="readme_non_empty",
            ok=bool(readme_text.strip()),
            message="README.md is non-empty",
        )
        add_check(
            checks,
            name="readme_non_publication_warning",
            ok="not published" in readme_text.lower() and "manual" in readme_text.lower(),
            message="README.md states non-publication and manual-review boundary",
        )

    expected_columns = expected_columns_from_config(config)
    forbidden_columns = forbidden_columns_from_config(config)

    if frame is not None:
        actual_columns = list(frame.columns)
        add_check(
            checks,
            name="data_columns_match_config",
            ok=actual_columns == expected_columns,
            message="data.parquet columns match required+optional config columns in order",
            details={
                "expected": expected_columns,
                "actual": actual_columns,
            },
        )

        forbidden_present = sorted(forbidden_columns & set(actual_columns))
        add_check(
            checks,
            name="no_forbidden_columns",
            ok=not forbidden_present,
            message="data.parquet does not contain forbidden columns",
            details={"forbidden_present": forbidden_present},
        )

        if validation.get("require_unique_canonical_id") is True and "canonical_id" in frame.columns:
            duplicate_count = int(frame["canonical_id"].duplicated().sum())
            add_check(
                checks,
                name="unique_canonical_id",
                ok=duplicate_count == 0,
                message="canonical_id values are unique",
                details={"duplicate_count": duplicate_count},
            )

        if validation.get("require_non_empty_title") is True and "title" in frame.columns:
            non_empty_title = frame["title"].fillna("").astype(str).str.strip().ne("")
            empty_title_count = int((~non_empty_title).sum())
            add_check(
                checks,
                name="non_empty_title",
                ok=empty_title_count == 0,
                message="All title values are non-empty",
                details={"empty_title_count": empty_title_count},
            )

        if validation.get("require_deterministic_order") is True:
            order_by = [str(item) for item in as_list(export.get("deterministic_order_by"))]
            if order_by and all(column in frame.columns for column in order_by):
                sorted_frame = frame.sort_values(order_by, kind="mergesort").reset_index(drop=True)
                deterministic_ok = frame.reset_index(drop=True)[order_by].equals(sorted_frame[order_by])
            else:
                deterministic_ok = False
            add_check(
                checks,
                name="deterministic_order",
                ok=deterministic_ok,
                message="Rows follow configured deterministic order",
                details={"order_by": order_by},
            )

        expected_count = source.get("expected_canonical_doc_count")
        manifest_row_count = as_mapping(manifest.get("source_checkpoint")).get("actual_exported_row_count")
        add_check(
            checks,
            name="manifest_row_count_matches_data",
            ok=manifest_row_count == len(frame),
            message="manifest actual_exported_row_count matches data.parquet row count",
            details={"manifest_row_count": manifest_row_count, "data_row_count": len(frame)},
        )
        if validation.get("require_expected_row_count") is True and isinstance(expected_count, int):
            max_rows = export.get("max_rows")
            if max_rows is None:
                row_count_ok = len(frame) == expected_count
            else:
                row_count_ok = len(frame) <= expected_count
            add_check(
                checks,
                name="expected_row_count",
                ok=row_count_ok,
                message="data.parquet row count is consistent with expected canonical checkpoint",
                details={"expected": expected_count, "actual": len(frame), "max_rows": max_rows},
            )


    if frame is not None and data_quality_summary:
        summary_row_count = data_quality_summary.get("row_count")
        summary_column_count = data_quality_summary.get("column_count")
        canonical_id_summary = as_mapping(data_quality_summary.get("canonical_id"))
        duplicate_count = int(frame["canonical_id"].duplicated().sum()) if "canonical_id" in frame.columns else None
        unique_count = int(frame["canonical_id"].nunique(dropna=True)) if "canonical_id" in frame.columns else None
        add_check(
            checks,
            name="data_quality_summary_schema_version",
            ok=data_quality_summary.get("schema_version") == "dataset_release_data_quality_summary_v1",
            message="data_quality_summary.json schema_version is dataset_release_data_quality_summary_v1",
            details={"actual": data_quality_summary.get("schema_version")},
        )
        add_check(
            checks,
            name="data_quality_summary_row_count_matches_data",
            ok=summary_row_count == len(frame),
            message="data_quality_summary row_count matches data.parquet row count",
            details={"summary_row_count": summary_row_count, "data_row_count": len(frame)},
        )
        add_check(
            checks,
            name="data_quality_summary_column_count_matches_data",
            ok=summary_column_count == len(frame.columns),
            message="data_quality_summary column_count matches data.parquet column count",
            details={"summary_column_count": summary_column_count, "data_column_count": len(frame.columns)},
        )
        add_check(
            checks,
            name="data_quality_summary_canonical_id_stats_match_data",
            ok=(
                canonical_id_summary.get("duplicate_count") == duplicate_count
                and canonical_id_summary.get("unique_count") == unique_count
            ),
            message="data_quality_summary canonical_id stats match data.parquet",
            details={
                "summary_duplicate_count": canonical_id_summary.get("duplicate_count"),
                "data_duplicate_count": duplicate_count,
                "summary_unique_count": canonical_id_summary.get("unique_count"),
                "data_unique_count": unique_count,
            },
        )

    if schema:
        schema_columns = [as_mapping(item).get("name") for item in as_list(schema.get("columns"))]
        add_check(
            checks,
            name="schema_columns_match_config",
            ok=schema_columns == expected_columns,
            message="schema.json columns match config columns",
            details={"expected": expected_columns, "actual": schema_columns},
        )
        add_check(
            checks,
            name="schema_primary_key",
            ok=as_list(schema.get("primary_key")) == ["canonical_id"],
            message="schema.json records canonical_id as primary key",
            details={"actual": schema.get("primary_key")},
        )

    if manifest:
        add_check(
            checks,
            name="manifest_schema_version",
            ok=manifest.get("schema_version") == "dataset_release_manifest_v1",
            message="manifest schema_version is dataset_release_manifest_v1",
            details={"actual": manifest.get("schema_version")},
        )
        add_check(
            checks,
            name="manifest_not_published",
            ok=manifest.get("publication_status") == "not_published",
            message="manifest states that public upload was not performed",
            details={"actual": manifest.get("publication_status")},
        )
        add_check(
            checks,
            name="manifest_manual_review_required",
            ok=manifest.get("manual_review_required_before_publication") is True,
            message="manifest requires manual review before publication",
            details={"actual": manifest.get("manual_review_required_before_publication")},
        )


        manifest_files = as_mapping(manifest.get("files"))
        add_check(
            checks,
            name="manifest_lists_data_quality_summary_file",
            ok=manifest_files.get("data_quality_summary") == "data_quality_summary.json",
            message="manifest files include data_quality_summary.json",
            details={"actual": manifest_files.get("data_quality_summary")},
        )

        manifest_export = as_mapping(manifest.get("export"))
        for flag, expected in REQUIRED_EXPORT_FALSE_FLAGS.items():
            add_check(
                checks,
                name=f"manifest_export_{flag}",
                ok=manifest_export.get(flag) is expected,
                message=f"manifest export.{flag} must be {expected}",
                details={"actual": manifest_export.get(flag), "expected": expected},
            )

        manifest_safety = as_mapping(manifest.get("safety"))
        for flag, expected in REQUIRED_SAFETY_VALUES.items():
            add_check(
                checks,
                name=f"manifest_safety_{flag}",
                ok=manifest_safety.get(flag) == expected,
                message=f"manifest safety.{flag} must be {expected!r}",
                details={"actual": manifest_safety.get(flag), "expected": expected},
            )

    if checksums_path.exists():
        try:
            checksums = read_checksums(checksums_path)
            checksum_parse_ok = True
            checksum_error = None
        except Exception as exc:
            checksums = {}
            checksum_parse_ok = False
            checksum_error = str(exc)
        add_check(
            checks,
            name="checksums_readable",
            ok=checksum_parse_ok,
            message="checksums.txt is readable",
            details={"error": checksum_error},
        )
        required_checksum_files = sorted(REQUIRED_OUTPUT_FILES - {"checksums.txt"})
        missing_checksum_entries = [name for name in required_checksum_files if name not in checksums]
        add_check(
            checks,
            name="checksums_required_entries",
            ok=not missing_checksum_entries,
            message="checksums.txt contains all required file entries except itself",
            details={"missing": missing_checksum_entries},
        )
        mismatched: list[str] = []
        for filename in required_checksum_files:
            path = release_dir / filename
            if path.exists() and filename in checksums and sha256_file(path) != checksums[filename]:
                mismatched.append(filename)
        add_check(
            checks,
            name="checksums_match_files",
            ok=not mismatched,
            message="checksums.txt SHA256 values match generated files",
            details={"mismatched": mismatched},
        )

    return checks


def build_report(
    *,
    config_path: Path,
    release_dir: Path,
    output_dir: Path,
    checks: Sequence[CheckResult],
    strict: bool,
) -> dict[str, Any]:
    required_failed = [check for check in checks if check.severity == "required" and not check.ok]
    warnings = [check for check in checks if check.severity == "warning" and not check.ok]
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "report_name": "check_dataset_release_output",
        "generated_at_utc": utc_now_iso(),
        "strict": bool(strict),
        "config_path": normalize_path(config_path),
        "release_dir": normalize_path(release_dir),
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
            "latest_json": normalize_path(output_dir / "dataset_release_output_latest.json"),
            "latest_markdown": normalize_path(output_dir / "dataset_release_output_latest.md"),
        },
    }


def build_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Dataset Release Output Validation",
        "",
        f"- schema_version: `{report.get('schema_version')}`",
        f"- generated_at_utc: `{report.get('generated_at_utc')}`",
        f"- ok: **{report.get('ok')}**",
        f"- strict: `{report.get('strict')}`",
        f"- config_path: `{report.get('config_path')}`",
        f"- release_dir: `{report.get('release_dir')}`",
        f"- required_failed_count: `{report.get('required_failed_count')}`",
        f"- warning_count: `{report.get('warning_count')}`",
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
    latest_json = output_dir / "dataset_release_output_latest.json"
    latest_md = output_dir / "dataset_release_output_latest.md"
    history_dir = output_dir / "history"
    ts = utc_now_ts()
    history_json = history_dir / f"dataset_release_output_{ts}.json"
    history_md = history_dir / f"dataset_release_output_{ts}.md"
    markdown = build_markdown(report)

    dump_json(latest_json, report)
    dump_text(latest_md, markdown)
    dump_json(history_json, report)
    dump_text(history_md, markdown)
    return latest_json, latest_md, history_json, history_md


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a generated ML Research Radar local candidate dataset release. "
            "This does not publish the dataset."
        )
    )
    parser.add_argument("--config-path", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--release-dir", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    config_path = Path(args.config_path)
    config = load_config(config_path)
    release_dir = Path(args.release_dir) if args.release_dir else release_dir_from_config(config, config_path=config_path)
    output_dir = Path(args.output_dir)

    checks = validate_release_output(config, config_path=config_path, release_dir=release_dir)
    report = build_report(
        config_path=config_path,
        release_dir=release_dir,
        output_dir=output_dir,
        checks=checks,
        strict=bool(args.strict),
    )
    latest_json, latest_md, history_json, history_md = write_reports(report, output_dir)

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

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
