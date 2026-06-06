"""Validate the Qdrant search-profile sweep report.

Strict mode requires exact Qdrant parity with the production file-dense
reference, zero integrity defects, classified/stable ANN differences, and the
configured overlap thresholds for every evaluated profile.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "qdrant_search_profile_sweep_quality_v1"
INPUT_SCHEMA_VERSION = "qdrant_search_profile_sweep_v1"
DEFAULT_REPORT_PATH = Path(
    "artifacts/reports/evaluation/qdrant_search_profile_sweep_latest.json"
)
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/validation")


def utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def dump_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def in_unit_interval(value: Any) -> bool:
    return is_finite_number(value) and 0.0 <= float(value) <= 1.0


def build_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    verdict = report["verdict"]
    lines = [
        "# Qdrant Search Profile Sweep Quality",
        "",
        f"- schema_version: `{report['schema_version']}`",
        f"- input_schema_version: `{summary.get('input_schema_version')}`",
        f"- strict: `{verdict.get('strict')}`",
        f"- ok: `{verdict.get('ok')}`",
        f"- required_failed_count: `{verdict.get('required_failed_count')}`",
        f"- required_failed_checks: `{verdict.get('required_failed_checks')}`",
        "",
        "## Summary",
        "",
        f"- build_id: `{summary.get('build_id')}`",
        f"- collection_name: `{summary.get('collection_name')}`",
        f"- enabled_queries_count: `{summary.get('enabled_queries_count')}`",
        f"- query_count: `{summary.get('query_count')}`",
        f"- error_count: `{summary.get('error_count')}`",
        f"- exact_profile_name: `{summary.get('exact_profile_name')}`",
        f"- exact_profile_full_match: `{summary.get('exact_profile_full_match')}`",
        f"- profile_count: `{summary.get('profile_count')}`",
        "",
        "## Checks",
        "",
    ]
    for name, value in report.get("checks", {}).items():
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
    parser.add_argument("--min-mean-overlap", type=float, default=None)
    parser.add_argument("--min-query-overlap", type=float, default=None)
    args = parser.parse_args(argv)

    run_ts = utc_ts()
    report_exists = args.report_path.exists()
    source: dict[str, Any] = load_json(args.report_path) if report_exists else {}

    summary_src = source.get("summary") or {}
    config = source.get("config") or {}
    quality_cfg = config.get("quality") or {}
    profile_cfg = config.get("profiles") or []
    profile_summaries = source.get("profile_summaries") or []
    query_results = source.get("query_results") or []
    errors = source.get("errors") or []

    min_mean_overlap = float(
        args.min_mean_overlap
        if args.min_mean_overlap is not None
        else quality_cfg.get("min_mean_overlap_at_k", 0.99)
    )
    min_query_overlap = float(
        args.min_query_overlap
        if args.min_query_overlap is not None
        else quality_cfg.get("min_query_overlap_at_k", 0.95)
    )
    max_error_count = int(quality_cfg.get("max_error_count", 0))
    require_exact_full_match = bool(
        quality_cfg.get("require_exact_profile_full_match", True)
    )

    enabled_queries_count = int(summary_src.get("enabled_queries_count") or 0)
    query_count = int(summary_src.get("query_count") or 0)
    error_count = int(summary_src.get("error_count") or len(errors))
    exact_profile_name = str(summary_src.get("exact_profile_name") or "")
    exact_profile_full_match = bool(summary_src.get("exact_profile_full_match"))

    expected_profile_names = [
        str(row.get("name"))
        for row in profile_cfg
        if isinstance(row, Mapping) and row.get("name")
    ]
    actual_profile_names = [
        str(row.get("profile", {}).get("name"))
        for row in profile_summaries
        if isinstance(row, Mapping)
    ]

    problems: list[str] = []
    blocking_classifications: list[str] = []
    profile_threshold_failures: list[str] = []

    summary_by_name: dict[str, dict[str, Any]] = {}
    for row in profile_summaries:
        if not isinstance(row, dict):
            problems.append("profile_summary_not_object")
            continue
        profile = row.get("profile") or {}
        name = str(profile.get("name") or "")
        if not name:
            problems.append("profile_summary_missing_name")
            continue
        summary_by_name[name] = row

        profile_query_count = row.get("query_count")
        mean_overlap = row.get("mean_overlap_at_k")
        min_overlap = row.get("min_overlap_at_k")
        exact_count = row.get("exact_same_order_count")
        mismatch_count = row.get("mismatch_count")
        mapping_failure_count = row.get("mapping_failure_count")
        latency = row.get("latency") or {}

        if profile_query_count != query_count:
            problems.append(
                f"{name}:query_count={profile_query_count},expected={query_count}"
            )
        if not in_unit_interval(mean_overlap):
            problems.append(f"{name}:invalid_mean_overlap={mean_overlap}")
        if not in_unit_interval(min_overlap):
            problems.append(f"{name}:invalid_min_overlap={min_overlap}")
        if not isinstance(exact_count, int) or not 0 <= exact_count <= max(query_count, 0):
            problems.append(f"{name}:invalid_exact_same_order_count={exact_count}")
        if not isinstance(mismatch_count, int) or mismatch_count < 0:
            problems.append(f"{name}:invalid_mismatch_count={mismatch_count}")
        if mapping_failure_count != 0:
            problems.append(f"{name}:mapping_failure_count={mapping_failure_count}")
        if latency.get("count") != query_count:
            problems.append(
                f"{name}:latency_count={latency.get('count')},expected={query_count}"
            )

        if is_finite_number(mean_overlap) and float(mean_overlap) < min_mean_overlap:
            profile_threshold_failures.append(
                f"{name}:mean_overlap={mean_overlap}<{min_mean_overlap}"
            )
        if is_finite_number(min_overlap) and float(min_overlap) < min_query_overlap:
            profile_threshold_failures.append(
                f"{name}:min_overlap={min_overlap}<{min_query_overlap}"
            )

    exact_summary = summary_by_name.get(exact_profile_name)
    exact_summary_valid = bool(exact_summary)
    if exact_summary:
        exact_summary_valid = (
            exact_summary.get("mean_overlap_at_k") == 1.0
            and exact_summary.get("min_overlap_at_k") == 1.0
            and exact_summary.get("mismatch_count") == 0
            and exact_summary.get("exact_same_order_count") == query_count
            and exact_summary.get("mapping_failure_count") == 0
        )

    query_vectors_valid = True
    per_query_profiles_valid = True
    mismatch_repeats_valid = True

    expected_embedding_dim = None
    embedding_shape = summary_src.get("embedding_shape")
    if isinstance(embedding_shape, list) and len(embedding_shape) == 2:
        expected_embedding_dim = embedding_shape[1]

    for query_row in query_results:
        if not isinstance(query_row, dict):
            problems.append("query_result_not_object")
            query_vectors_valid = False
            per_query_profiles_valid = False
            continue

        query_id = str(query_row.get("query_id") or "<missing-query-id>")
        vector = query_row.get("query_vector") or {}
        dimension = vector.get("dimension")
        norm = vector.get("norm")
        all_finite = vector.get("all_finite")
        dtype = vector.get("dtype")
        sha256 = vector.get("sha256")

        vector_ok = (
            isinstance(dimension, int)
            and dimension > 0
            and (expected_embedding_dim is None or dimension == expected_embedding_dim)
            and is_finite_number(norm)
            and abs(float(norm) - 1.0) <= 1e-4
            and all_finite is True
            and dtype == "float32"
            and isinstance(sha256, str)
            and len(sha256) == 64
        )
        if not vector_ok:
            query_vectors_valid = False
            problems.append(f"{query_id}:invalid_query_vector_metadata={vector}")

        profiles = query_row.get("profiles") or {}
        if set(profiles.keys()) != set(expected_profile_names):
            per_query_profiles_valid = False
            problems.append(
                f"{query_id}:profile_names={sorted(profiles.keys())},"
                f"expected={sorted(expected_profile_names)}"
            )

        for profile_name, payload in profiles.items():
            comparison = payload.get("comparison") or {}
            mapping_audit = payload.get("mapping_audit") or {}
            classification = payload.get("classification") or {}
            determinism = payload.get("determinism")

            overlap = comparison.get("overlap_ratio")
            if not in_unit_interval(overlap):
                per_query_profiles_valid = False
                problems.append(f"{query_id}/{profile_name}:invalid_overlap={overlap}")
            elif float(overlap) < min_query_overlap:
                profile_threshold_failures.append(
                    f"{query_id}/{profile_name}:overlap={overlap}<{min_query_overlap}"
                )

            if mapping_audit.get("failure_count") != 0:
                per_query_profiles_valid = False
                problems.append(
                    f"{query_id}/{profile_name}:mapping_failure_count="
                    f"{mapping_audit.get('failure_count')}"
                )

            severity = classification.get("severity")
            classification_name = classification.get("classification")
            if severity == "blocking":
                blocking_classifications.append(
                    f"{query_id}/{profile_name}:{classification_name}"
                )

            if not comparison.get("exact_same_order"):
                if determinism is None:
                    mismatch_repeats_valid = False
                    problems.append(f"{query_id}/{profile_name}:missing_determinism")
                elif determinism.get("stable_order") is not True:
                    mismatch_repeats_valid = False
                    problems.append(
                        f"{query_id}/{profile_name}:stable_order="
                        f"{determinism.get('stable_order')}"
                    )

    checks = {
        "report_exists": report_exists,
        "input_schema_version_ok": source.get("schema_version") == INPUT_SCHEMA_VERSION,
        "build_id_present": bool(summary_src.get("build_id")),
        "collection_name_present": bool(summary_src.get("collection_name")),
        "enabled_queries_positive": enabled_queries_count > 0,
        "query_count_matches_enabled": (
            query_count == enabled_queries_count and query_count > 0
        ),
        "error_count_within_limit": error_count <= max_error_count,
        "errors_array_consistent": error_count == len(errors),
        "profile_names_match_config": (
            expected_profile_names == actual_profile_names
            and len(expected_profile_names) > 0
        ),
        "exact_profile_present": bool(exact_profile_name) and exact_summary is not None,
        "exact_profile_summary_valid": exact_summary_valid,
        "exact_profile_full_match": (
            exact_profile_full_match if require_exact_full_match else True
        ),
        "query_vectors_valid": query_vectors_valid,
        "per_query_profiles_valid": per_query_profiles_valid,
        "mismatch_repeats_valid": mismatch_repeats_valid,
        "no_blocking_classifications": len(blocking_classifications) == 0,
        "profile_overlap_thresholds_pass": len(profile_threshold_failures) == 0,
        "no_structural_problems": len(problems) == 0,
    }

    required_check_names = [
        "report_exists",
        "input_schema_version_ok",
        "build_id_present",
        "collection_name_present",
        "enabled_queries_positive",
        "query_count_matches_enabled",
        "error_count_within_limit",
        "errors_array_consistent",
        "profile_names_match_config",
        "exact_profile_present",
        "query_vectors_valid",
        "per_query_profiles_valid",
        "no_structural_problems",
    ]
    if args.strict:
        required_check_names.extend(
            [
                "exact_profile_summary_valid",
                "exact_profile_full_match",
                "mismatch_repeats_valid",
                "no_blocking_classifications",
                "profile_overlap_thresholds_pass",
            ]
        )

    required_failed_checks = [
        name for name in required_check_names if not checks.get(name, False)
    ]
    verdict = {
        "ok": len(required_failed_checks) == 0,
        "strict": bool(args.strict),
        "required_failed_count": len(required_failed_checks),
        "required_failed_checks": required_failed_checks,
    }

    quality_report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_iso(),
        "run_ts": run_ts,
        "report_path": str(args.report_path),
        "summary": {
            "input_schema_version": source.get("schema_version"),
            "build_id": summary_src.get("build_id"),
            "collection_name": summary_src.get("collection_name"),
            "enabled_queries_count": enabled_queries_count,
            "query_count": query_count,
            "error_count": error_count,
            "profile_count": len(profile_summaries),
            "exact_profile_name": exact_profile_name,
            "exact_profile_full_match": exact_profile_full_match,
            "min_mean_overlap": min_mean_overlap,
            "min_query_overlap": min_query_overlap,
        },
        "checks": checks,
        "blocking_classifications": blocking_classifications,
        "profile_threshold_failures": profile_threshold_failures,
        "problems": problems,
        "verdict": verdict,
    }

    latest_json = args.output_dir / "qdrant_search_profile_sweep_quality_latest.json"
    latest_md = args.output_dir / "qdrant_search_profile_sweep_quality_latest.md"
    history_json = (
        args.output_dir
        / "history"
        / f"qdrant_search_profile_sweep_quality_{run_ts}.json"
    )
    history_md = (
        args.output_dir
        / "history"
        / f"qdrant_search_profile_sweep_quality_{run_ts}.md"
    )

    markdown = build_markdown(quality_report)
    dump_json(latest_json, quality_report)
    dump_text(latest_md, markdown)
    dump_json(history_json, quality_report)
    dump_text(history_md, markdown)

    print(f"[OK] report_path={args.report_path}")
    print(f"[OK] schema_version={SCHEMA_VERSION}")
    print(f"[OK] input_schema_version={source.get('schema_version')}")
    print(f"[OK] strict={args.strict}")
    print(f"[OK] build_id={summary_src.get('build_id')}")
    print(f"[OK] collection_name={summary_src.get('collection_name')}")
    print(f"[OK] query_count={query_count}")
    print(f"[OK] error_count={error_count}")
    print(f"[OK] exact_profile_name={exact_profile_name}")
    print(f"[OK] exact_profile_full_match={exact_profile_full_match}")
    print(f"[OK] required_failed_count={verdict['required_failed_count']}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")

    if args.strict and required_failed_checks:
        sys.exit(1)


if __name__ == "__main__":
    main()
