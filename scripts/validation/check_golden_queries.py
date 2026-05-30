from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_QUERIES_PATH = Path("data/eval/retrieval/golden_queries.jsonl")
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/validation")

ALLOWED_GRADES = {1, 2, 3}
WEAK_RELEVANCE_FIELDS = (
    "title_substrings",
    "title_any_substrings",
    "must_have_any_terms",
)


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def safe_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def has_weak_relevance(expected: dict[str, Any]) -> bool:
    for field in WEAK_RELEVANCE_FIELDS:
        values = expected.get(field)
        if isinstance(values, list) and any(str(item).strip() for item in values):
            return True
    return False


def has_explicit_relevance(row: dict[str, Any]) -> bool:
    expected = row.get("expected") or {}
    expected_ids = safe_list(expected.get("canonical_ids"))
    graded = safe_list(row.get("graded_relevance"))
    return bool(expected_ids or graded)


def read_jsonl(path: Path) -> tuple[list[tuple[int, dict[str, Any]]], list[str]]:
    rows: list[tuple[int, dict[str, Any]]] = []
    errors: list[str] = []

    if not path.exists():
        return rows, [f"queries file not found: {path}"]

    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue

        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_no}: JSON error: {exc}")
            continue

        if not isinstance(row, dict):
            errors.append(f"line {line_no}: row must be a JSON object")
            continue

        rows.append((line_no, row))

    return rows, errors


def validate_rows(rows: list[tuple[int, dict[str, Any]]]) -> dict[str, Any]:
    query_ids: list[str] = []
    missing_query_id_lines: list[int] = []
    enabled_query_ids: list[str] = []
    disabled_query_ids: list[str] = []

    explicit_enabled: list[str] = []
    weak_enabled: list[str] = []
    bad_enabled: list[str] = []

    duplicate_expected_ids: list[str] = []
    duplicate_graded_ids: list[str] = []
    malformed_expected_ids: list[str] = []
    malformed_weak_patterns: list[str] = []
    malformed_graded_relevance: list[str] = []
    invalid_grades: list[str] = []
    enabled_with_null_grades: list[str] = []

    for line_no, row in rows:
        qid = row.get("query_id")
        if not isinstance(qid, str) or not qid.strip():
            missing_query_id_lines.append(line_no)
            qid = f"<missing@line:{line_no}>"
        else:
            qid = qid.strip()

        query_ids.append(qid)

        expected = row.get("expected")
        if expected is None:
            expected = {}
        if not isinstance(expected, dict):
            malformed_expected_ids.append(qid)
            expected = {}

        expected_ids = expected.get("canonical_ids", [])
        if expected_ids is None:
            expected_ids = []
        if not isinstance(expected_ids, list):
            malformed_expected_ids.append(qid)
            expected_ids = []

        expected_ids_str = [str(item).strip() for item in expected_ids if str(item).strip()]
        if len(expected_ids_str) != len(set(expected_ids_str)):
            duplicate_expected_ids.append(qid)

        for field in WEAK_RELEVANCE_FIELDS:
            value = expected.get(field)
            if value is not None and not isinstance(value, list):
                malformed_weak_patterns.append(qid)
                break

        graded = row.get("graded_relevance", [])
        if graded is None:
            graded = []
        if not isinstance(graded, list):
            malformed_graded_relevance.append(qid)
            graded = []

        graded_ids: list[str] = []
        row_has_invalid_grade = False
        row_has_null_grade = False

        for idx, item in enumerate(graded):
            if not isinstance(item, dict):
                malformed_graded_relevance.append(qid)
                continue

            canonical_id = item.get("canonical_id")
            if not isinstance(canonical_id, str) or not canonical_id.strip():
                malformed_graded_relevance.append(qid)
            else:
                graded_ids.append(canonical_id.strip())

            grade = item.get("grade")
            if grade is None:
                row_has_null_grade = True
            elif grade not in ALLOWED_GRADES:
                row_has_invalid_grade = True

        if len(graded_ids) != len(set(graded_ids)):
            duplicate_graded_ids.append(qid)

        if row_has_invalid_grade:
            invalid_grades.append(qid)

        enabled = row.get("enabled") is True
        if enabled:
            enabled_query_ids.append(qid)

            explicit = bool(expected_ids_str or graded)
            weak = has_weak_relevance(expected)

            if explicit:
                explicit_enabled.append(qid)
            elif weak:
                weak_enabled.append(qid)
            else:
                bad_enabled.append(qid)

            if graded and row_has_null_grade:
                enabled_with_null_grades.append(qid)
        else:
            disabled_query_ids.append(qid)

    duplicate_query_ids = sorted(
        qid for qid, count in Counter(query_ids).items()
        if count > 1 and not qid.startswith("<missing@line:")
    )

    return {
        "query_ids": query_ids,
        "missing_query_id_lines": missing_query_id_lines,
        "duplicate_query_ids": duplicate_query_ids,
        "enabled_query_ids": enabled_query_ids,
        "disabled_query_ids": disabled_query_ids,
        "explicit_enabled": explicit_enabled,
        "weak_enabled": weak_enabled,
        "bad_enabled": bad_enabled,
        "duplicate_expected_ids": sorted(set(duplicate_expected_ids)),
        "duplicate_graded_ids": sorted(set(duplicate_graded_ids)),
        "malformed_expected_ids": sorted(set(malformed_expected_ids)),
        "malformed_weak_patterns": sorted(set(malformed_weak_patterns)),
        "malformed_graded_relevance": sorted(set(malformed_graded_relevance)),
        "invalid_grades": sorted(set(invalid_grades)),
        "enabled_with_null_grades": sorted(set(enabled_with_null_grades)),
    }


def build_checks(*, path: Path, rows: list[tuple[int, dict[str, Any]]], parse_errors: list[str], stats: dict[str, Any]) -> dict[str, bool]:
    return {
        "queries_path_exists": path.exists(),
        "jsonl_parse_ok": not parse_errors,
        "rows_non_empty": len(rows) > 0,
        "query_ids_present": not stats["missing_query_id_lines"],
        "query_ids_unique": not stats["duplicate_query_ids"],
        "enabled_cases_present": len(stats["enabled_query_ids"]) > 0,
        "enabled_cases_have_relevance": not stats["bad_enabled"],
        "expected_canonical_ids_unique": not stats["duplicate_expected_ids"],
        "graded_relevance_canonical_ids_unique": not stats["duplicate_graded_ids"],
        "expected_canonical_ids_well_formed": not stats["malformed_expected_ids"],
        "weak_patterns_well_formed": not stats["malformed_weak_patterns"],
        "graded_relevance_well_formed": not stats["malformed_graded_relevance"],
        "grades_in_allowed_set": not stats["invalid_grades"],
        "enabled_graded_relevance_has_no_null_grades": not stats["enabled_with_null_grades"],
    }


def required_check_names(*, strict: bool) -> list[str]:
    base = [
        "queries_path_exists",
        "jsonl_parse_ok",
        "rows_non_empty",
        "query_ids_present",
        "query_ids_unique",
        "enabled_cases_present",
        "enabled_cases_have_relevance",
        "expected_canonical_ids_unique",
        "graded_relevance_well_formed",
        "grades_in_allowed_set",
    ]

    if strict:
        base.extend(
            [
                "graded_relevance_canonical_ids_unique",
                "expected_canonical_ids_well_formed",
                "weak_patterns_well_formed",
                "enabled_graded_relevance_has_no_null_grades",
            ]
        )

    return base


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []

    lines.append("# Golden queries quality check")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at_utc']}`")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Strict: `{report['strict']}`")
    lines.append(f"- OK: **{report['ok']}**")
    lines.append("")

    lines.append("## Inputs")
    for key, value in report["inputs"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Extracted values")
    for key, value in report["extracted_values"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Checks")
    for key, value in report["checks"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    samples = report.get("samples") or {}
    if samples:
        lines.append("## Samples")
        for key, value in samples.items():
            lines.append(f"- {key}: `{value}`")
        lines.append("")

    if report["required_failed_checks"]:
        lines.append("## Required failures")
        for item in report["required_failed_checks"]:
            lines.append(f"- `{item}`")
        lines.append("")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate retrieval golden queries JSONL.")
    parser.add_argument("--queries-path", type=Path, default=DEFAULT_QUERIES_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    rows, parse_errors = read_jsonl(args.queries_path)
    stats = validate_rows(rows)
    checks = build_checks(path=args.queries_path, rows=rows, parse_errors=parse_errors, stats=stats)

    required = required_check_names(strict=args.strict)
    required_failed = [name for name in required if not checks.get(name, False)]

    quality_report = {
        "schema_version": "golden_queries_quality_v1",
        "report_name": "check_golden_queries",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "strict": bool(args.strict),
        "inputs": {
            "queries_path": normalize_path(args.queries_path),
        },
        "extracted_values": {
            "rows_count": len(rows),
            "enabled_cases_count": len(stats["enabled_query_ids"]),
            "disabled_cases_count": len(stats["disabled_query_ids"]),
            "explicit_canonical_labeled_enabled_count": len(stats["explicit_enabled"]),
            "weak_pattern_enabled_count": len(stats["weak_enabled"]),
            "bad_enabled_cases_count": len(stats["bad_enabled"]),
            "duplicate_query_id_count": len(stats["duplicate_query_ids"]),
            "missing_query_id_count": len(stats["missing_query_id_lines"]),
            "parse_error_count": len(parse_errors),
            "duplicate_expected_ids_count": len(stats["duplicate_expected_ids"]),
            "duplicate_graded_ids_count": len(stats["duplicate_graded_ids"]),
            "invalid_grade_query_count": len(stats["invalid_grades"]),
        },
        "checks": checks,
        "required_checks": required,
        "required_failed_count": len(required_failed),
        "required_failed_checks": required_failed,
        "samples": {
            "parse_errors": parse_errors[:10],
            "duplicate_query_ids": stats["duplicate_query_ids"][:20],
            "bad_enabled_cases": stats["bad_enabled"][:20],
            "weak_pattern_cases": stats["weak_enabled"][:50],
            "invalid_grade_cases": stats["invalid_grades"][:20],
            "enabled_with_null_grades": stats["enabled_with_null_grades"][:20],
        },
        "ok": len(required_failed) == 0,
    }

    output_dir = args.output_dir
    latest_json = output_dir / "golden_queries_quality_latest.json"
    latest_md = output_dir / "golden_queries_quality_latest.md"
    hist_json = output_dir / "history" / f"golden_queries_quality_{run_ts}.json"
    hist_md = output_dir / "history" / f"golden_queries_quality_{run_ts}.md"

    dump_json(latest_json, quality_report)
    dump_text(latest_md, build_markdown(quality_report))
    dump_json(hist_json, quality_report)
    dump_text(hist_md, build_markdown(quality_report))

    print(f"[OK] queries_path={args.queries_path}")
    print(f"[OK] schema_version={quality_report['schema_version']}")
    print(f"[OK] strict={args.strict}")
    print(f"[OK] rows_count={len(rows)}")
    print(f"[OK] enabled_cases_count={len(stats['enabled_query_ids'])}")
    print(f"[OK] explicit_canonical_labeled_enabled_count={len(stats['explicit_enabled'])}")
    print(f"[OK] weak_pattern_enabled_count={len(stats['weak_enabled'])}")
    print(f"[OK] required_failed_count={len(required_failed)}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")

    if required_failed:
        print("[FAIL] required_failed_checks:")
        for name in required_failed:
            print(f"  - {name}")
        sys.exit(1)


if __name__ == "__main__":
    main()
