from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from radar_core.contracts.canonical_document import CanonicalDocument


DEFAULT_CANONICAL_PATH = Path("data/analytics/reconciled/canonical_documents.jsonl")
DEFAULT_REPORTS_DIR = Path("artifacts/reports/validation")

REPORT_NAME = "canonical_contract"


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_path(path: Path) -> str:
    return str(path).replace("\\", "/")


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def dump_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def compact_validation_errors(exc: ValidationError, *, limit: int = 12) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []

    for err in exc.errors(include_url=False)[:limit]:
        compact.append(
            {
                "type": err.get("type"),
                "loc": list(err.get("loc", [])),
                "msg": err.get("msg"),
            }
        )

    return compact


def truncate_text(value: Any, *, limit: int = 180) -> str | None:
    if value is None:
        return None

    text = str(value)
    if len(text) <= limit:
        return text

    return text[: limit - 3] + "..."


def load_and_validate_canonical(
    canonical_path: Path,
    *,
    sample_limit: int,
) -> dict[str, Any]:
    allowed_fields = set(CanonicalDocument.model_fields.keys())

    rows_count = 0
    valid_rows_count = 0

    json_load_errors: list[dict[str, Any]] = []
    validation_errors: list[dict[str, Any]] = []

    bad_row_numbers: set[int] = set()

    extra_field_counts: Counter[str] = Counter()
    extra_field_rows_count = 0
    extra_field_row_samples: list[dict[str, Any]] = []

    missing_canonical_id_count = 0
    missing_canonical_id_samples: list[dict[str, Any]] = []

    canonical_id_counts: Counter[str] = Counter()
    duplicate_canonical_id_samples: list[dict[str, Any]] = []

    doc_ids_not_list_count = 0
    doc_ids_not_list_samples: list[dict[str, Any]] = []

    duplicate_doc_ids_within_row_count = 0
    duplicate_doc_ids_within_row_samples: list[dict[str, Any]] = []

    doc_id_to_canonical_ids: dict[str, set[str]] = defaultdict(set)

    validation_error_type_counts: Counter[str] = Counter()

    if not canonical_path.exists():
        return {
            "canonical_path_exists": False,
            "rows_count": 0,
            "valid_rows_count": 0,
            "json_load_errors_count": 0,
            "validation_errors_count": 0,
            "bad_rows_count": 0,
            "extra_fields_count": 0,
            "extra_field_rows_count": 0,
            "extra_field_counts": {},
            "missing_canonical_id_count": 0,
            "duplicate_canonical_id_count": 0,
            "duplicate_doc_id_values_across_canonical_count": 0,
            "doc_ids_not_list_count": 0,
            "duplicate_doc_ids_within_row_count": 0,
            "samples": {},
            "validation_error_type_counts": {},
        }

    with canonical_path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            raw_line = line.strip()
            if not raw_line:
                continue

            rows_count += 1

            try:
                row = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                bad_row_numbers.add(line_number)

                if len(json_load_errors) < sample_limit:
                    json_load_errors.append(
                        {
                            "line_number": line_number,
                            "error": str(exc),
                            "line_sample": truncate_text(raw_line),
                        }
                    )
                continue

            if not isinstance(row, dict):
                bad_row_numbers.add(line_number)

                if len(validation_errors) < sample_limit:
                    validation_errors.append(
                        {
                            "line_number": line_number,
                            "canonical_id": None,
                            "title": None,
                            "errors": [
                                {
                                    "type": "not_a_json_object",
                                    "loc": [],
                                    "msg": f"Expected JSON object, got {type(row).__name__}",
                                }
                            ],
                        }
                    )
                continue

            canonical_id = row.get("canonical_id")
            title = row.get("title")

            if not canonical_id:
                missing_canonical_id_count += 1
                if len(missing_canonical_id_samples) < sample_limit:
                    missing_canonical_id_samples.append(
                        {
                            "line_number": line_number,
                            "title": truncate_text(title),
                            "keys": sorted(row.keys()),
                        }
                    )
            else:
                canonical_id_counts[str(canonical_id)] += 1

            raw_extra_fields = sorted(set(row.keys()) - allowed_fields)
            if raw_extra_fields:
                bad_row_numbers.add(line_number)
                extra_field_rows_count += 1
                extra_field_counts.update(raw_extra_fields)

                if len(extra_field_row_samples) < sample_limit:
                    extra_field_row_samples.append(
                        {
                            "line_number": line_number,
                            "canonical_id": canonical_id,
                            "title": truncate_text(title),
                            "extra_fields": raw_extra_fields,
                        }
                    )

            raw_doc_ids = row.get("doc_ids", [])
            if not isinstance(raw_doc_ids, list):
                doc_ids_not_list_count += 1
                if len(doc_ids_not_list_samples) < sample_limit:
                    doc_ids_not_list_samples.append(
                        {
                            "line_number": line_number,
                            "canonical_id": canonical_id,
                            "title": truncate_text(title),
                            "doc_ids_type": type(raw_doc_ids).__name__,
                        }
                    )
            else:
                doc_id_counts_within_row = Counter(
                    str(doc_id) for doc_id in raw_doc_ids if doc_id
                )
                duplicated_within_row = sorted(
                    doc_id
                    for doc_id, count in doc_id_counts_within_row.items()
                    if count > 1
                )

                if duplicated_within_row:
                    duplicate_doc_ids_within_row_count += 1
                    if len(duplicate_doc_ids_within_row_samples) < sample_limit:
                        duplicate_doc_ids_within_row_samples.append(
                            {
                                "line_number": line_number,
                                "canonical_id": canonical_id,
                                "title": truncate_text(title),
                                "duplicate_doc_ids": duplicated_within_row[:20],
                            }
                        )

                if canonical_id:
                    for doc_id in doc_id_counts_within_row:
                        doc_id_to_canonical_ids[doc_id].add(str(canonical_id))

            try:
                CanonicalDocument.model_validate(row)
                valid_rows_count += 1
            except ValidationError as exc:
                bad_row_numbers.add(line_number)

                for err in exc.errors(include_url=False):
                    validation_error_type_counts[str(err.get("type"))] += 1

                if len(validation_errors) < sample_limit:
                    validation_errors.append(
                        {
                            "line_number": line_number,
                            "canonical_id": canonical_id,
                            "title": truncate_text(title),
                            "errors": compact_validation_errors(exc),
                        }
                    )

    duplicate_canonical_ids = sorted(
        canonical_id for canonical_id, count in canonical_id_counts.items() if count > 1
    )

    for canonical_id in duplicate_canonical_ids[:sample_limit]:
        duplicate_canonical_id_samples.append(
            {
                "canonical_id": canonical_id,
                "count": canonical_id_counts[canonical_id],
            }
        )

    duplicate_doc_id_values_across_canonical: dict[str, list[str]] = {
        doc_id: sorted(canonical_ids)
        for doc_id, canonical_ids in doc_id_to_canonical_ids.items()
        if len(canonical_ids) > 1
    }

    duplicate_doc_id_values_across_canonical_samples = [
        {
            "doc_id": doc_id,
            "canonical_ids": canonical_ids[:20],
            "canonical_ids_count": len(canonical_ids),
        }
        for doc_id, canonical_ids in list(
            sorted(duplicate_doc_id_values_across_canonical.items())
        )[:sample_limit]
    ]

    return {
        "canonical_path_exists": True,
        "rows_count": rows_count,
        "valid_rows_count": valid_rows_count,
        "json_load_errors_count": len(json_load_errors),
        "validation_errors_count": len(validation_errors)
        if len(validation_errors) < sample_limit
        else sum(validation_error_type_counts.values()),
        "bad_rows_count": len(bad_row_numbers),
        "extra_fields_count": sum(extra_field_counts.values()),
        "extra_field_rows_count": extra_field_rows_count,
        "extra_field_counts": dict(sorted(extra_field_counts.items())),
        "missing_canonical_id_count": missing_canonical_id_count,
        "duplicate_canonical_id_count": len(duplicate_canonical_ids),
        "duplicate_doc_id_values_across_canonical_count": len(
            duplicate_doc_id_values_across_canonical
        ),
        "doc_ids_not_list_count": doc_ids_not_list_count,
        "duplicate_doc_ids_within_row_count": duplicate_doc_ids_within_row_count,
        "validation_error_type_counts": dict(
            sorted(validation_error_type_counts.items())
        ),
        "samples": {
            "json_load_errors": json_load_errors,
            "validation_errors": validation_errors,
            "extra_field_rows": extra_field_row_samples,
            "missing_canonical_id": missing_canonical_id_samples,
            "duplicate_canonical_ids": duplicate_canonical_id_samples,
            "doc_ids_not_list": doc_ids_not_list_samples,
            "duplicate_doc_ids_within_row": duplicate_doc_ids_within_row_samples,
            "duplicate_doc_id_values_across_canonical": (
                duplicate_doc_id_values_across_canonical_samples
            ),
        },
    }


def build_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    checks = report["checks"]
    verdict = report["verdict"]

    lines: list[str] = []
    lines.append("# Canonical contract check")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at_utc']}`")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Strict: `{report['strict']}`")
    lines.append("")
    lines.append("## Inputs")
    lines.append(f"- canonical_path: `{report['inputs']['canonical_path']}`")
    lines.append("")
    lines.append("## Summary")
    for key, value in summary.items():
        if key == "samples":
            continue
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Checks")
    for key, value in checks.items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Verdict")
    for key, value in verdict.items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    extra_field_counts = summary.get("extra_field_counts") or {}
    if extra_field_counts:
        lines.append("## Extra field counts")
        for key, value in extra_field_counts.items():
            lines.append(f"- {key}: `{value}`")
        lines.append("")

    validation_error_type_counts = summary.get("validation_error_type_counts") or {}
    if validation_error_type_counts:
        lines.append("## Validation error type counts")
        for key, value in validation_error_type_counts.items():
            lines.append(f"- {key}: `{value}`")
        lines.append("")

    samples = summary.get("samples") or {}
    non_empty_samples = {
        key: value for key, value in samples.items() if value
    }

    if non_empty_samples:
        lines.append("## Samples")
        for key, value in non_empty_samples.items():
            lines.append(f"### {key}")
            lines.append("```json")
            lines.append(json.dumps(value, ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate canonical_documents.jsonl against the CanonicalDocument "
            "contract and write machine/human-readable reports."
        )
    )
    parser.add_argument(
        "--canonical-path",
        type=Path,
        default=DEFAULT_CANONICAL_PATH,
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=DEFAULT_REPORTS_DIR,
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=20,
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if required contract checks fail.",
    )
    parser.add_argument(
        "--require-unique-doc-ids",
        action="store_true",
        help=(
            "Treat duplicate source-level doc_ids across canonical documents as "
            "a blocking failure. By default this is diagnostic only."
        ),
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    summary = load_and_validate_canonical(
        args.canonical_path,
        sample_limit=max(1, args.sample_limit),
    )

    checks: dict[str, bool] = {
        "canonical_path_exists": bool(summary["canonical_path_exists"]),
        "rows_non_empty": int(summary["rows_count"]) > 0,
        "no_json_load_errors": int(summary["json_load_errors_count"]) == 0,
        "all_rows_valid_canonical_document": int(summary["bad_rows_count"]) == 0,
        "no_validation_errors": int(summary["bad_rows_count"]) == 0,
        "no_extra_fields": int(summary["extra_fields_count"]) == 0,
        "canonical_ids_present": int(summary["missing_canonical_id_count"]) == 0,
        "canonical_ids_unique": int(summary["duplicate_canonical_id_count"]) == 0,
        "doc_ids_shape_ok": int(summary["doc_ids_not_list_count"]) == 0,
        "no_duplicate_doc_ids_within_row": (
            int(summary["duplicate_doc_ids_within_row_count"]) == 0
        ),
        "no_duplicate_doc_ids_across_canonical": (
            int(summary["duplicate_doc_id_values_across_canonical_count"]) == 0
        ),
    }

    required_check_names = [
        "canonical_path_exists",
        "rows_non_empty",
        "no_json_load_errors",
        "all_rows_valid_canonical_document",
        "no_validation_errors",
        "no_extra_fields",
        "canonical_ids_present",
        "canonical_ids_unique",
    ]

    if args.require_unique_doc_ids:
        required_check_names.append("no_duplicate_doc_ids_across_canonical")

    required_failed_checks = [
        name for name in required_check_names if not checks.get(name, False)
    ]

    verdict = {
        "required_check_count": len(required_check_names),
        "required_failed_count": len(required_failed_checks),
        "required_failed_checks": required_failed_checks,
        "ok": len(required_failed_checks) == 0,
        "strict": bool(args.strict),
        "require_unique_doc_ids": bool(args.require_unique_doc_ids),
    }

    report = {
        "report_name": REPORT_NAME,
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "strict": bool(args.strict),
        "inputs": {
            "canonical_path": normalize_path(args.canonical_path),
        },
        "summary": summary,
        "checks": checks,
        "verdict": verdict,
    }

    latest_json = args.reports_dir / f"{REPORT_NAME}_latest.json"
    latest_md = args.reports_dir / f"{REPORT_NAME}_latest.md"
    hist_json = args.reports_dir / "history" / f"{REPORT_NAME}_{run_ts}.json"
    hist_md = args.reports_dir / "history" / f"{REPORT_NAME}_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(hist_json, report)
    dump_text(hist_md, build_markdown(report))

    print(f"[OK] canonical_path={normalize_path(args.canonical_path)}")
    print(f"[OK] rows_count={summary['rows_count']}")
    print(f"[OK] valid_rows_count={summary['valid_rows_count']}")
    print(f"[OK] bad_rows_count={summary['bad_rows_count']}")
    print(f"[OK] extra_fields_count={summary['extra_fields_count']}")
    print(f"[OK] extra_field_rows_count={summary['extra_field_rows_count']}")
    print(f"[OK] missing_canonical_id_count={summary['missing_canonical_id_count']}")
    print(f"[OK] duplicate_canonical_id_count={summary['duplicate_canonical_id_count']}")
    print(
        "[OK] duplicate_doc_id_values_across_canonical_count="
        f"{summary['duplicate_doc_id_values_across_canonical_count']}"
    )
    for key, value in checks.items():
        print(f"[OK] {key}={value}")
    print(f"[OK] contract_ok={verdict['ok']}")
    print(f"[OK] required_failed_count={verdict['required_failed_count']}")
    print(f"[OK] required_failed_checks={verdict['required_failed_checks']}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {hist_json}")
    print(f"[OK] history Markdown: {hist_md}")

    if args.strict and not verdict["ok"]:
        sys.exit(1)


if __name__ == "__main__":
    main()