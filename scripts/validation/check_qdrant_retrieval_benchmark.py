from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REPORT_PATH = Path("artifacts/reports/evaluation/qdrant_retrieval_benchmark_latest.json")
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/validation")
SCHEMA_VERSION = "qdrant_retrieval_benchmark_quality_v1"
EXPECTED_INPUT_SCHEMA_VERSION = "qdrant_retrieval_benchmark_v1"


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def normalize_path(path: str | Path | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"JSON report not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in report: {path}")
    return payload


def finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        x = float(value)
    except Exception:
        return None
    if not math.isfinite(x):
        return None
    return x


def in_range(value: Any, lo: float = 0.0, hi: float = 1.0) -> bool:
    x = finite_number(value)
    return x is not None and lo <= x <= hi


def has_number(value: Any) -> bool:
    return finite_number(value) is not None


def quality_metrics_ok(item: dict[str, Any]) -> bool:
    if not item:
        return True
    for key in ("hit_rate_at_k", "recall_at_k", "mrr_at_k", "ndcg_at_k"):
        if key in item and not in_range(item.get(key)):
            return False
    return True


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Qdrant retrieval benchmark quality check")
    lines.append("")
    lines.append(f"- Generated at: {report['generated_at_utc']}")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Strict: `{report['strict']}`")
    lines.append(f"- Input report: `{report['input_report_path']}`")
    lines.append("")

    lines.append("## Summary")
    for key, value in report["summary"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Checks")
    for key, value in report["checks"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Verdict")
    for key, value in report["verdict"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate Qdrant retrieval benchmark report.")
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    report_path: Path = args.report_path
    output_dir: Path = args.output_dir

    latest_json = output_dir / "qdrant_retrieval_benchmark_quality_latest.json"
    latest_md = output_dir / "qdrant_retrieval_benchmark_quality_latest.md"
    hist_json = output_dir / "history" / f"qdrant_retrieval_benchmark_quality_{run_ts}.json"
    hist_md = output_dir / "history" / f"qdrant_retrieval_benchmark_quality_{run_ts}.md"

    report = load_json(report_path)

    manifest = report.get("manifest") or {}
    dense = report.get("dense_artifacts") or {}
    upload = report.get("upload_summary") or {}
    qsummary = report.get("query_summary") or {}
    latency = report.get("latency_summary") or {}
    quality = report.get("quality_summary") or {}
    overlap = report.get("overlap_summary") or {}
    query_results = report.get("query_results") or []
    verdict_in = report.get("verdict") or {}

    corpus_doc_count = int(manifest.get("corpus_doc_count") or 0)
    uploaded_count = int(upload.get("uploaded_count") or 0)
    points_count = upload.get("collection_points_count")
    points_count_int = int(points_count) if points_count is not None else None
    enabled_queries_count = int(qsummary.get("enabled_queries_count") or report.get("enabled_queries_count") or 0)
    query_count = int(qsummary.get("query_count") or report.get("query_count") or 0)
    explicit_relevance_queries_count = int(qsummary.get("explicit_relevance_queries_count") or 0)
    weak_pattern_queries_count = int(qsummary.get("weak_pattern_queries_count") or 0)
    unknown_relevance_queries_count = int(qsummary.get("unknown_relevance_queries_count") or 0)
    error_count = int(qsummary.get("error_count") or 0)
    queries_without_results = qsummary.get("queries_without_results") or []
    is_partial = bool(upload.get("is_partial") or dense.get("is_partial"))
    failed_batch_count = int(upload.get("failed_batch_count") or 0)

    checks = {
        "report_exists": report_path.exists(),
        "schema_version_ok": report.get("schema_version") == EXPECTED_INPUT_SCHEMA_VERSION,
        "manifest_build_id_present": bool(manifest.get("build_id")),
        "corpus_doc_count_positive": corpus_doc_count > 0,
        "embedding_shape_present": isinstance(dense.get("embedding_shape"), list) and len(dense.get("embedding_shape")) == 2,
        "ids_count_positive": int(dense.get("ids_count") or 0) > 0,
        "qdrant_collection_name_present": bool((report.get("qdrant") or {}).get("collection_name")),
        "uploaded_count_positive": uploaded_count > 0,
        "collection_points_count_present": points_count_int is not None,
        "collection_points_match_uploaded": points_count_int == uploaded_count,
        "failed_batch_count_zero": failed_batch_count == 0,
        "query_count_positive": query_count > 0,
        "query_count_matches_enabled": query_count == enabled_queries_count,
        "explicit_or_weak_cases_cover_enabled": (explicit_relevance_queries_count + weak_pattern_queries_count == enabled_queries_count),
        "unknown_relevance_queries_zero": unknown_relevance_queries_count == 0,
        "error_count_zero": error_count == 0,
        "all_queries_return_results": len(queries_without_results) == 0,
        "qdrant_latency_p50_present": has_number((latency.get("qdrant_query_ms") or {}).get("p50")),
        "qdrant_latency_p95_present": has_number((latency.get("qdrant_query_ms") or {}).get("p95")),
        "qdrant_quality_metrics_in_range": quality_metrics_ok(quality.get("qdrant") or {}),
        "file_dense_quality_metrics_in_range": quality_metrics_ok(quality.get("file_dense") or {}),
        "overlap_mean_in_range": (
            overlap.get("mean_overlap_ratio_at_k") is None
            or in_range(overlap.get("mean_overlap_ratio_at_k"))
        ),
        "benchmark_only": verdict_in.get("benchmark_only") is True,
        "production_default_not_changed": verdict_in.get("production_default_changed") is False,
    }

    # Full strict benchmark should upload the complete dense corpus, not a debug subset.
    checks["not_partial_upload"] = not is_partial
    checks["uploaded_count_matches_corpus"] = uploaded_count == corpus_doc_count
    checks["points_count_matches_corpus"] = points_count_int == corpus_doc_count

    per_query_bad: list[str] = []
    for item in query_results:
        qid = str(item.get("query_id"))
        if int(item.get("qdrant_returned_count") or 0) <= 0:
            per_query_bad.append(qid)
        for metric_key in ("qdrant_metrics", "file_dense_metrics"):
            qm = item.get(metric_key) or {}
            for key in ("hit_at_k", "recall_at_k", "mrr_at_k", "ndcg_at_k"):
                if key in qm and not in_range(qm.get(key)):
                    per_query_bad.append(f"{qid}:{metric_key}.{key}={qm.get(key)!r}")
                    break
    checks["per_query_results_valid"] = len(per_query_bad) == 0

    required_check_names = [
        "report_exists",
        "schema_version_ok",
        "manifest_build_id_present",
        "corpus_doc_count_positive",
        "embedding_shape_present",
        "ids_count_positive",
        "qdrant_collection_name_present",
        "uploaded_count_positive",
        "collection_points_count_present",
        "collection_points_match_uploaded",
        "failed_batch_count_zero",
        "query_count_positive",
        "query_count_matches_enabled",
        "explicit_or_weak_cases_cover_enabled",
        "unknown_relevance_queries_zero",
        "error_count_zero",
        "all_queries_return_results",
        "qdrant_latency_p50_present",
        "qdrant_latency_p95_present",
        "qdrant_quality_metrics_in_range",
        "file_dense_quality_metrics_in_range",
        "overlap_mean_in_range",
        "benchmark_only",
        "production_default_not_changed",
        "per_query_results_valid",
    ]

    if args.strict:
        required_check_names.extend(
            [
                "not_partial_upload",
                "uploaded_count_matches_corpus",
                "points_count_matches_corpus",
            ]
        )

    required_failed = [name for name in required_check_names if checks.get(name) is not True]

    summary = {
        "input_schema_version": report.get("schema_version"),
        "build_id": manifest.get("build_id"),
        "corpus_doc_count": corpus_doc_count,
        "uploaded_count": uploaded_count,
        "collection_points_count": points_count_int,
        "failed_batch_count": failed_batch_count,
        "enabled_queries_count": enabled_queries_count,
        "query_count": query_count,
        "explicit_relevance_queries_count": explicit_relevance_queries_count,
        "weak_pattern_queries_count": weak_pattern_queries_count,
        "unknown_relevance_queries_count": unknown_relevance_queries_count,
        "error_count": error_count,
        "queries_without_results": queries_without_results,
        "is_partial": is_partial,
        "qdrant_quality": quality.get("qdrant") or {},
        "file_dense_quality": quality.get("file_dense") or {},
        "overlap_summary": overlap,
        "per_query_bad": per_query_bad,
    }

    verdict = {
        "ok": len(required_failed) == 0,
        "strict": bool(args.strict),
        "required_failed_count": len(required_failed),
        "required_failed_checks": required_failed,
    }

    quality_report = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "strict": bool(args.strict),
        "input_report_path": normalize_path(report_path),
        "summary": summary,
        "checks": checks,
        "required_check_names": required_check_names,
        "verdict": verdict,
        "artifacts": {
            "latest_json": normalize_path(latest_json),
            "latest_markdown": normalize_path(latest_md),
            "history_json": normalize_path(hist_json),
            "history_markdown": normalize_path(hist_md),
        },
    }

    markdown = build_markdown(quality_report)
    dump_json(latest_json, quality_report)
    dump_json(hist_json, quality_report)
    dump_text(latest_md, markdown)
    dump_text(hist_md, markdown)

    print(f"[OK] report_path={report_path}")
    print(f"[OK] schema_version={SCHEMA_VERSION}")
    print(f"[OK] input_schema_version={report.get('schema_version')}")
    print(f"[OK] strict={args.strict}")
    print(f"[OK] build_id={manifest.get('build_id')}")
    print(f"[OK] corpus_doc_count={corpus_doc_count}")
    print(f"[OK] uploaded_count={uploaded_count}")
    print(f"[OK] collection_points_count={points_count_int}")
    print(f"[OK] enabled_queries_count={enabled_queries_count}")
    print(f"[OK] query_count={query_count}")
    print(f"[OK] error_count={error_count}")
    print(f"[OK] required_failed_count={len(required_failed)}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")

    if required_failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
