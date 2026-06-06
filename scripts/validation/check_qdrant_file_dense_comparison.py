"""Validate the Qdrant/file-dense comparison v2 report."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "qdrant_file_dense_comparison_quality_v2"
INPUT_SCHEMA_VERSION = "qdrant_file_dense_comparison_v2"
DEFAULT_REPORT_PATH = Path(
    "artifacts/reports/evaluation/qdrant_file_dense_comparison_latest.json"
)
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/validation")


def utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def dump_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def in_range(value: Any, low: float, high: float) -> bool:
    return is_finite_number(value) and low <= float(value) <= high


def validate_query_vector(payload: Any) -> bool:
    if not isinstance(payload, Mapping):
        return False
    dimension = payload.get("dimension")
    norm = payload.get("norm")
    return (
        isinstance(dimension, int)
        and dimension > 0
        and payload.get("dtype") == "float32"
        and payload.get("all_finite") is True
        and is_finite_number(norm)
        and abs(float(norm) - 1.0) <= 1e-4
        and isinstance(payload.get("sha256"), str)
        and len(str(payload.get("sha256"))) == 64
    )


def validate_profile_result(
    payload: Any,
    *,
    external_top_k: int,
    require_exact_match: bool,
    problems: list[str],
    prefix: str,
) -> None:
    if not isinstance(payload, Mapping):
        problems.append(f"{prefix}:missing_profile_result")
        return

    comparison = payload.get("comparison")
    mapping_audit = payload.get("mapping_audit")
    classification = payload.get("classification")
    results = payload.get("results")

    if not isinstance(comparison, Mapping):
        problems.append(f"{prefix}:missing_comparison")
    else:
        overlap = comparison.get("overlap_ratio")
        if not in_range(overlap, 0.0, 1.0):
            problems.append(f"{prefix}:invalid_overlap={overlap}")
        if not isinstance(comparison.get("exact_same_order"), bool):
            problems.append(f"{prefix}:invalid_exact_same_order")
        if require_exact_match and comparison.get("exact_same_order") is not True:
            problems.append(f"{prefix}:required_exact_match_failed")
        if comparison.get("top_k") != external_top_k:
            problems.append(f"{prefix}:unexpected_top_k={comparison.get('top_k')}")

    if not isinstance(mapping_audit, Mapping):
        problems.append(f"{prefix}:missing_mapping_audit")
    elif int(mapping_audit.get("failure_count") or 0) != 0:
        problems.append(
            f"{prefix}:mapping_failure_count={mapping_audit.get('failure_count')}"
        )

    if not isinstance(classification, Mapping):
        problems.append(f"{prefix}:missing_classification")
    elif classification.get("severity") == "blocking":
        problems.append(
            f"{prefix}:blocking_classification={classification.get('classification')}"
        )

    if not isinstance(results, list) or not results:
        problems.append(f"{prefix}:missing_results")
        return

    seen_ids: set[str] = set()
    for index, row in enumerate(results, start=1):
        if not isinstance(row, Mapping):
            problems.append(f"{prefix}:result_{index}_not_object")
            continue
        canonical_id = str(row.get("canonical_id") or "").strip()
        if not canonical_id:
            problems.append(f"{prefix}:result_{index}_missing_canonical_id")
        elif canonical_id in seen_ids:
            problems.append(f"{prefix}:duplicate_canonical_id={canonical_id}")
        else:
            seen_ids.add(canonical_id)
        if not is_finite_number(row.get("score")):
            problems.append(f"{prefix}:result_{index}_invalid_score")
        if row.get("rank") != index:
            problems.append(
                f"{prefix}:result_{index}_rank={row.get('rank')}"
            )


def evaluate_report(source: Mapping[str, Any], *, strict: bool) -> dict[str, Any]:
    summary_src = source.get("summary") or {}
    quality_policy = source.get("quality_policy") or {}
    selected_summary = source.get("selected_profile_summary") or {}
    exact_summary = source.get("exact_profile_summary") or {}
    latency = source.get("latency_summary") or {}
    query_results = source.get("query_results") or []
    errors = source.get("errors") or []
    blocking_classifications = source.get("blocking_classifications") or []

    enabled_queries_count = int(summary_src.get("enabled_queries_count") or 0)
    query_count = int(summary_src.get("query_count") or 0)
    error_count = int(summary_src.get("error_count") or len(errors))
    external_top_k = int(summary_src.get("external_top_k") or 0)

    max_error_count = int(quality_policy.get("max_error_count", 0))
    require_selected_full_match = bool(
        quality_policy.get("require_selected_profile_full_match", True)
    )
    require_exact_full_match = bool(
        quality_policy.get("require_exact_profile_full_match", True)
    )
    min_mean_overlap = float(quality_policy.get("min_mean_overlap_at_k", 0.99))
    min_query_overlap = float(quality_policy.get("min_query_overlap_at_k", 0.95))

    problems: list[str] = []
    for row_index, row in enumerate(query_results, start=1):
        if not isinstance(row, Mapping):
            problems.append(f"query_result_{row_index}:not_object")
            continue
        query_id = str(row.get("query_id") or f"row_{row_index}")
        if not validate_query_vector(row.get("query_vector")):
            problems.append(f"{query_id}:invalid_query_vector")
        file_reference = row.get("file_reference")
        if not isinstance(file_reference, Mapping):
            problems.append(f"{query_id}:missing_file_reference")
        else:
            results = file_reference.get("results")
            if not isinstance(results, list) or not results:
                problems.append(f"{query_id}:missing_file_reference_results")
        validate_profile_result(
            row.get("selected_profile"),
            external_top_k=external_top_k,
            require_exact_match=require_selected_full_match,
            problems=problems,
            prefix=f"{query_id}:selected",
        )
        validate_profile_result(
            row.get("exact_profile"),
            external_top_k=external_top_k,
            require_exact_match=require_exact_full_match,
            problems=problems,
            prefix=f"{query_id}:exact",
        )

        selected_result = row.get("selected_profile")
        if isinstance(selected_result, Mapping):
            comparison = selected_result.get("comparison") or {}
            if isinstance(comparison, Mapping) and not comparison.get("exact_same_order"):
                determinism = selected_result.get("determinism")
                if not isinstance(determinism, Mapping):
                    problems.append(f"{query_id}:selected_missing_determinism")
                else:
                    if determinism.get("stable_order") is not True:
                        problems.append(f"{query_id}:selected_unstable_order")
                    if int(determinism.get("recorded_runs") or 0) <= 0:
                        problems.append(f"{query_id}:selected_no_recorded_runs")

    selected_mean = selected_summary.get("mean_overlap_at_k")
    selected_min = selected_summary.get("min_overlap_at_k")
    exact_mean = exact_summary.get("mean_overlap_at_k")
    exact_min = exact_summary.get("min_overlap_at_k")

    latency_valid = True
    for name in ("file_reference", "selected_profile", "exact_profile"):
        block = latency.get(name)
        if not isinstance(block, Mapping) or block.get("count") != query_count:
            latency_valid = False

    checks = {
        "input_schema_version_ok": source.get("schema_version") == INPUT_SCHEMA_VERSION,
        "build_id_present": bool(summary_src.get("build_id")),
        "collection_name_present": bool(summary_src.get("collection_name")),
        "enabled_queries_positive": enabled_queries_count > 0,
        "query_count_matches_enabled": (
            query_count == enabled_queries_count and query_count > 0
        ),
        "error_count_within_limit": error_count <= max_error_count,
        "errors_array_consistent": len(errors) == error_count,
        "selected_profile_name_present": bool(summary_src.get("selected_profile_name")),
        "exact_profile_name_present": bool(summary_src.get("exact_profile_name")),
        "selected_profile_summary_valid": (
            selected_summary.get("query_count") == query_count
            and in_range(selected_mean, 0.0, 1.0)
            and in_range(selected_min, 0.0, 1.0)
        ),
        "exact_profile_summary_valid": (
            exact_summary.get("query_count") == query_count
            and in_range(exact_mean, 0.0, 1.0)
            and in_range(exact_min, 0.0, 1.0)
        ),
        "selected_profile_full_match": (
            summary_src.get("selected_profile_full_match") is True
            if require_selected_full_match
            else True
        ),
        "exact_profile_full_match": (
            summary_src.get("exact_profile_full_match") is True
            if require_exact_full_match
            else True
        ),
        "selected_overlap_thresholds_pass": (
            is_finite_number(selected_mean)
            and float(selected_mean) >= min_mean_overlap
            and is_finite_number(selected_min)
            and float(selected_min) >= min_query_overlap
        ),
        "exact_overlap_is_full": (
            is_finite_number(exact_mean)
            and float(exact_mean) == 1.0
            and is_finite_number(exact_min)
            and float(exact_min) == 1.0
        ),
        "no_blocking_classifications": (
            len(blocking_classifications) == 0
            and int(summary_src.get("blocking_classification_count") or 0) == 0
        ),
        "latency_sections_valid": latency_valid,
        "per_query_results_valid": len(problems) == 0,
    }

    required = [
        "input_schema_version_ok",
        "build_id_present",
        "collection_name_present",
        "enabled_queries_positive",
        "query_count_matches_enabled",
        "error_count_within_limit",
        "errors_array_consistent",
        "selected_profile_name_present",
        "exact_profile_name_present",
        "selected_profile_summary_valid",
        "exact_profile_summary_valid",
        "exact_profile_full_match",
        "exact_overlap_is_full",
        "no_blocking_classifications",
        "per_query_results_valid",
    ]
    if strict:
        required.extend(
            [
                "selected_profile_full_match",
                "selected_overlap_thresholds_pass",
                "latency_sections_valid",
            ]
        )

    required_failed = [name for name in required if not checks.get(name, False)]
    return {
        "checks": checks,
        "problems": problems,
        "required_failed_checks": required_failed,
        "ok": len(required_failed) == 0,
        "policy": {
            "max_error_count": max_error_count,
            "require_selected_profile_full_match": require_selected_full_match,
            "require_exact_profile_full_match": require_exact_full_match,
            "min_mean_overlap_at_k": min_mean_overlap,
            "min_query_overlap_at_k": min_query_overlap,
        },
    }


def build_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    checks = report["checks"]
    verdict = report["verdict"]
    lines = [
        "# Qdrant vs File Dense Comparison Quality v2",
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
        f"- selected_profile_name: `{summary.get('selected_profile_name')}`",
        f"- selected_profile_full_match: `{summary.get('selected_profile_full_match')}`",
        f"- exact_profile_name: `{summary.get('exact_profile_name')}`",
        f"- exact_profile_full_match: `{summary.get('exact_profile_full_match')}`",
        "",
        "## Checks",
        "",
    ]
    for name, value in checks.items():
        lines.append(f"- {'✅' if value else '❌'} `{name}` = `{value}`")
    if report.get("problems"):
        lines.extend(["", "## Problems", ""])
        for problem in report["problems"][:100]:
            lines.append(f"- `{problem}`")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    run_ts = utc_ts()
    report_exists = args.report_path.exists()
    source: dict[str, Any] = load_json(args.report_path) if report_exists else {}
    evaluation = evaluate_report(source, strict=bool(args.strict)) if report_exists else {
        "checks": {"report_exists": False},
        "problems": [f"report_not_found:{args.report_path}"],
        "required_failed_checks": ["report_exists"],
        "ok": False,
        "policy": {},
    }
    checks = dict(evaluation["checks"])
    checks["report_exists"] = report_exists
    required_failed = list(evaluation["required_failed_checks"])
    if not report_exists and "report_exists" not in required_failed:
        required_failed.insert(0, "report_exists")

    summary_src = source.get("summary") or {}
    summary = {
        "input_schema_version": source.get("schema_version"),
        "build_id": summary_src.get("build_id"),
        "collection_name": summary_src.get("collection_name"),
        "enabled_queries_count": int(summary_src.get("enabled_queries_count") or 0),
        "query_count": int(summary_src.get("query_count") or 0),
        "error_count": int(summary_src.get("error_count") or 0),
        "selected_profile_name": summary_src.get("selected_profile_name"),
        "selected_profile_full_match": summary_src.get("selected_profile_full_match"),
        "exact_profile_name": summary_src.get("exact_profile_name"),
        "exact_profile_full_match": summary_src.get("exact_profile_full_match"),
    }
    verdict = {
        "ok": len(required_failed) == 0,
        "strict": bool(args.strict),
        "required_failed_count": len(required_failed),
        "required_failed_checks": required_failed,
    }
    quality_report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_iso(),
        "run_ts": run_ts,
        "report_path": str(args.report_path).replace("\\", "/"),
        "summary": summary,
        "policy": evaluation.get("policy", {}),
        "checks": checks,
        "problems": evaluation.get("problems", []),
        "verdict": verdict,
    }

    latest_json = args.output_dir / "qdrant_file_dense_comparison_quality_latest.json"
    latest_md = args.output_dir / "qdrant_file_dense_comparison_quality_latest.md"
    history_json = (
        args.output_dir
        / "history"
        / f"qdrant_file_dense_comparison_quality_{run_ts}.json"
    )
    history_md = (
        args.output_dir
        / "history"
        / f"qdrant_file_dense_comparison_quality_{run_ts}.md"
    )

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
    print(f"[OK] enabled_queries_count={summary.get('enabled_queries_count')}")
    print(f"[OK] query_count={summary.get('query_count')}")
    print(f"[OK] error_count={summary.get('error_count')}")
    print(f"[OK] selected_profile_name={summary.get('selected_profile_name')}")
    print(
        "[OK] selected_profile_full_match="
        f"{summary.get('selected_profile_full_match')}"
    )
    print(f"[OK] exact_profile_name={summary.get('exact_profile_name')}")
    print(f"[OK] exact_profile_full_match={summary.get('exact_profile_full_match')}")
    print(f"[OK] required_failed_count={verdict['required_failed_count']}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")

    if args.strict and required_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
