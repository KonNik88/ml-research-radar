"""Validate Qdrant vs file-dense comparison report."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "qdrant_file_dense_comparison_quality_v1"
INPUT_SCHEMA_VERSION = "qdrant_file_dense_comparison_v1"
DEFAULT_REPORT_PATH = Path("artifacts/reports/evaluation/qdrant_file_dense_comparison_latest.json")
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/validation")


def utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def dump_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def in_range(value: Any, low: float, high: float) -> bool:
    return is_finite_number(value) and low <= float(value) <= high


def build_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    checks = report["checks"]
    verdict = report["verdict"]
    lines = [
        "# Qdrant vs File Dense Comparison Quality",
        "",
        f"- schema_version: `{report['schema_version']}`",
        f"- input_schema_version: `{summary.get('input_schema_version')}`",
        f"- strict: `{verdict['strict']}`",
        f"- ok: `{verdict['ok']}`",
        f"- required_failed_count: `{verdict['required_failed_count']}`",
        f"- required_failed_checks: `{verdict['required_failed_checks']}`",
        "",
        "## Summary",
        "",
        f"- build_id: `{summary.get('build_id')}`",
        f"- collection_name: `{summary.get('collection_name')}`",
        f"- enabled_queries_count: `{summary.get('enabled_queries_count')}`",
        f"- query_count: `{summary.get('query_count')}`",
        f"- error_count: `{summary.get('error_count')}`",
        f"- mean_overlap_ratio_at_k: `{summary.get('mean_overlap_ratio_at_k')}`",
        f"- min_overlap_ratio_at_k: `{summary.get('min_overlap_ratio_at_k')}`",
        f"- exact_same_order_count: `{summary.get('exact_same_order_count')}`",
        "",
        "## Checks",
        "",
    ]
    for name, value in checks.items():
        lines.append(f"- {'✅' if value else '❌'} `{name}` = `{value}`")
    if report.get("bad_queries"):
        lines.extend(["", "## Bad queries", ""])
        for row in report["bad_queries"][:20]:
            lines.append(f"- `{row}`")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--min-mean-overlap", type=float, default=0.99)
    parser.add_argument("--min-min-overlap", type=float, default=0.95)
    args = parser.parse_args(argv)

    run_ts = utc_ts()
    report_exists = args.report_path.exists()
    source: dict[str, Any] = load_json(args.report_path) if report_exists else {}
    summary_src = source.get("summary", {}) or {}
    overlap = source.get("overlap_summary", {}) or {}
    latency = source.get("latency_summary", {}) or {}
    query_results = source.get("query_results", []) or []
    errors = source.get("errors", []) or []

    enabled_queries_count = int(summary_src.get("enabled_queries_count") or 0)
    query_count = int(summary_src.get("query_count") or 0)
    error_count = int(summary_src.get("error_count") or len(errors))
    mean_overlap = overlap.get("mean_overlap_ratio_at_k")
    min_overlap = overlap.get("min_overlap_ratio_at_k")
    exact_same_order_count = int(overlap.get("exact_same_order_count") or 0)

    bad_queries: list[str] = []
    for row in query_results:
        qid = row.get("query_id")
        qdrant_count = row.get("qdrant_returned_count")
        file_count = row.get("file_dense_returned_count")
        row_overlap = (row.get("overlap") or {}).get("overlap_ratio_at_k")
        exact_same_order = (row.get("overlap") or {}).get("exact_same_order")
        if not qid:
            bad_queries.append("missing query_id")
        if not isinstance(qdrant_count, int) or qdrant_count <= 0:
            bad_queries.append(f"{qid}:qdrant_returned_count={qdrant_count}")
        if not isinstance(file_count, int) or file_count <= 0:
            bad_queries.append(f"{qid}:file_dense_returned_count={file_count}")
        if not in_range(row_overlap, 0.0, 1.0):
            bad_queries.append(f"{qid}:overlap_ratio_at_k={row_overlap}")
        if not isinstance(exact_same_order, bool):
            bad_queries.append(f"{qid}:exact_same_order={exact_same_order}")

    checks = {
        "report_exists": report_exists,
        "input_schema_version_ok": source.get("schema_version") == INPUT_SCHEMA_VERSION,
        "build_id_present": bool(summary_src.get("build_id")),
        "collection_name_present": bool(summary_src.get("collection_name")),
        "enabled_queries_positive": enabled_queries_count > 0,
        "query_count_matches_enabled": query_count == enabled_queries_count and query_count > 0,
        "error_count_zero": error_count == 0,
        "mean_overlap_in_range": in_range(mean_overlap, 0.0, 1.0),
        "min_overlap_in_range": in_range(min_overlap, 0.0, 1.0),
        "mean_overlap_above_threshold": is_finite_number(mean_overlap) and float(mean_overlap) >= args.min_mean_overlap,
        "min_overlap_above_threshold": is_finite_number(min_overlap) and float(min_overlap) >= args.min_min_overlap,
        "exact_same_order_count_valid": 0 <= exact_same_order_count <= max(query_count, enabled_queries_count),
        "latency_qdrant_present": isinstance(latency.get("qdrant"), dict) and latency.get("qdrant", {}).get("count") == query_count,
        "latency_file_dense_present": isinstance(latency.get("file_dense"), dict) and latency.get("file_dense", {}).get("count") == query_count,
        "per_query_results_valid": len(bad_queries) == 0,
    }

    required_check_names = [
        "report_exists",
        "input_schema_version_ok",
        "build_id_present",
        "collection_name_present",
        "enabled_queries_positive",
        "query_count_matches_enabled",
        "error_count_zero",
        "mean_overlap_in_range",
        "min_overlap_in_range",
        "per_query_results_valid",
    ]
    if args.strict:
        required_check_names.extend(
            [
                "mean_overlap_above_threshold",
                "min_overlap_above_threshold",
                "latency_qdrant_present",
                "latency_file_dense_present",
            ]
        )

    required_failed = [name for name in required_check_names if not checks.get(name, False)]
    verdict = {
        "ok": len(required_failed) == 0,
        "strict": bool(args.strict),
        "required_failed_count": len(required_failed),
        "required_failed_checks": required_failed,
    }
    summary = {
        "input_schema_version": source.get("schema_version"),
        "build_id": summary_src.get("build_id"),
        "collection_name": summary_src.get("collection_name"),
        "enabled_queries_count": enabled_queries_count,
        "query_count": query_count,
        "error_count": error_count,
        "mean_overlap_ratio_at_k": mean_overlap,
        "min_overlap_ratio_at_k": min_overlap,
        "exact_same_order_count": exact_same_order_count,
    }
    quality_report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "run_ts": run_ts,
        "report_path": str(args.report_path),
        "summary": summary,
        "checks": checks,
        "bad_queries": bad_queries,
        "verdict": verdict,
    }

    latest_json = args.output_dir / "qdrant_file_dense_comparison_quality_latest.json"
    latest_md = args.output_dir / "qdrant_file_dense_comparison_quality_latest.md"
    history_json = args.output_dir / "history" / f"qdrant_file_dense_comparison_quality_{run_ts}.json"
    history_md = args.output_dir / "history" / f"qdrant_file_dense_comparison_quality_{run_ts}.md"

    dump_json(latest_json, quality_report)
    dump_json(history_json, quality_report)
    markdown = build_markdown(quality_report)
    dump_text(latest_md, markdown)
    dump_text(history_md, markdown)

    print(f"[OK] report_path={args.report_path}")
    print(f"[OK] schema_version={SCHEMA_VERSION}")
    print(f"[OK] input_schema_version={source.get('schema_version')}")
    print(f"[OK] strict={args.strict}")
    print(f"[OK] build_id={summary.get('build_id')}")
    print(f"[OK] collection_name={summary.get('collection_name')}")
    print(f"[OK] enabled_queries_count={enabled_queries_count}")
    print(f"[OK] query_count={query_count}")
    print(f"[OK] error_count={error_count}")
    print(f"[OK] mean_overlap_ratio_at_k={mean_overlap}")
    print(f"[OK] min_overlap_ratio_at_k={min_overlap}")
    print(f"[OK] required_failed_count={verdict['required_failed_count']}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")

    if args.strict and required_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
