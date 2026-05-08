from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_SIMILAR_REPORT_PATH = Path("artifacts/reports/retrieval/similar_papers_latest.json")
DEFAULT_REPORTS_DIR = Path("artifacts/reports/retrieval")


REQUIRED_RESULT_FIELDS = {
    "canonical_id",
    "title",
    "semantic_similarity",
    "semantic_similarity_norm",
    "radar_adjusted_similarity",
    "rank_score",
    "radar_score",
    "implementation_readiness_score",
}


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


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def is_number(value: Any) -> bool:
    try:
        float(value)
        return True
    except Exception:
        return False


def in_range(value: Any, low: float, high: float) -> bool:
    try:
        numeric = float(value)
    except Exception:
        return False
    return low <= numeric <= high


def sorted_desc(values: list[float]) -> bool:
    return all(values[i] >= values[i + 1] for i in range(len(values) - 1))


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Similar papers quality check")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at_utc']}`")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Strict: `{report['strict']}`")
    lines.append("")

    lines.append("## Inputs")
    for key, value in report["inputs"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Summary")
    for key, value in report["summary"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Counters")
    for key, value in report["counters"].items():
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
    parser = argparse.ArgumentParser(
        description="Validate latest similar papers report."
    )
    parser.add_argument(
        "--similar-report-path",
        type=Path,
        default=DEFAULT_SIMILAR_REPORT_PATH,
    )
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    report_exists = args.similar_report_path.exists()
    source_report: dict[str, Any] = load_json(args.similar_report_path) if report_exists else {}

    results = source_report.get("results") or []
    target_canonical_id = source_report.get("target_canonical_id")
    rank_by = source_report.get("rank_by")
    top_k = source_report.get("top_k")
    returned_rows_count = source_report.get("returned_rows_count")

    result_ids = [row.get("canonical_id") for row in results if row.get("canonical_id")]
    duplicate_ids = sorted({x for x in result_ids if result_ids.count(x) > 1})

    missing_required_fields: list[dict[str, Any]] = []
    semantic_range_violations: list[str] = []
    semantic_norm_range_violations: list[str] = []
    adjusted_range_violations: list[str] = []
    rank_score_missing_or_bad: list[str] = []

    for row in results:
        canonical_id = row.get("canonical_id")

        missing = sorted(field for field in REQUIRED_RESULT_FIELDS if field not in row)
        if missing:
            missing_required_fields.append(
                {
                    "canonical_id": canonical_id,
                    "missing": missing,
                }
            )

        if "semantic_similarity" in row and not in_range(row.get("semantic_similarity"), -1.000001, 1.000001):
            semantic_range_violations.append(str(canonical_id))

        if "semantic_similarity_norm" in row and not in_range(row.get("semantic_similarity_norm"), 0.0, 1.0):
            semantic_norm_range_violations.append(str(canonical_id))

        if "radar_adjusted_similarity" in row and not in_range(row.get("radar_adjusted_similarity"), 0.0, 1.0):
            adjusted_range_violations.append(str(canonical_id))

        if not is_number(row.get("rank_score")):
            rank_score_missing_or_bad.append(str(canonical_id))

    if rank_by == "semantic":
        sort_values = [float(row.get("semantic_similarity")) for row in results if is_number(row.get("semantic_similarity"))]
    elif rank_by == "radar_adjusted":
        sort_values = [
            float(row.get("radar_adjusted_similarity"))
            for row in results
            if is_number(row.get("radar_adjusted_similarity"))
        ]
    else:
        sort_values = []

    dense_artifacts = source_report.get("dense_artifacts") or {}

    checks = {
        "similar_report_exists": report_exists,
        "report_name_ok": source_report.get("report_name") == "similar_papers",
        "mode_ok": source_report.get("mode") == "similar_papers",
        "target_canonical_id_present": bool(target_canonical_id),
        "target_found": bool(source_report.get("target_found")),
        "target_present": bool(source_report.get("target")),
        "rank_by_supported": rank_by in {"semantic", "radar_adjusted"},
        "input_rows_non_empty": int(source_report.get("input_rows_count") or 0) > 0,
        "results_non_empty": len(results) > 0,
        "returned_rows_match_results_count": returned_rows_count == len(results),
        "returned_rows_le_top_k": len(results) <= int(top_k or 0),
        "self_not_in_results": target_canonical_id not in result_ids,
        "canonical_ids_present": len(result_ids) == len(results),
        "canonical_ids_unique": len(duplicate_ids) == 0,
        "required_result_fields_present": len(missing_required_fields) == 0,
        "semantic_similarity_in_range": len(semantic_range_violations) == 0,
        "semantic_similarity_norm_in_range": len(semantic_norm_range_violations) == 0,
        "radar_adjusted_similarity_in_range": len(adjusted_range_violations) == 0,
        "rank_scores_present": len(rank_score_missing_or_bad) == 0,
        "sorted_correctly": len(sort_values) == len(results) and sorted_desc(sort_values),
        "embedding_path_present": bool(dense_artifacts.get("embedding_path")),
        "embedding_shape_present": bool(dense_artifacts.get("embedding_shape")),
        "ids_count_matches_input_rows": int(dense_artifacts.get("ids_count") or 0)
        == int(source_report.get("input_rows_count") or -1),
    }

    required_failed_checks = [name for name, ok in checks.items() if not ok]

    quality_report = {
        "report_name": "similar_papers_quality",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "strict": bool(args.strict),
        "inputs": {
            "similar_report_path": normalize_path(args.similar_report_path),
            "reports_dir": normalize_path(args.reports_dir),
        },
        "summary": {
            "target_canonical_id": target_canonical_id,
            "target_title": (source_report.get("target") or {}).get("title"),
            "rank_by": rank_by,
            "top_k": top_k,
            "input_rows_count": source_report.get("input_rows_count"),
            "returned_rows_count": returned_rows_count,
            "results_count": len(results),
        },
        "counters": {
            "duplicate_ids": duplicate_ids,
            "missing_required_fields_count": len(missing_required_fields),
            "semantic_range_violations_count": len(semantic_range_violations),
            "semantic_norm_range_violations_count": len(semantic_norm_range_violations),
            "adjusted_range_violations_count": len(adjusted_range_violations),
            "rank_score_missing_or_bad_count": len(rank_score_missing_or_bad),
        },
        "checks": checks,
        "verdict": {
            "ok": len(required_failed_checks) == 0,
            "required_failed_count": len(required_failed_checks),
            "required_failed_checks": required_failed_checks,
        },
    }

    latest_json = args.reports_dir / "similar_papers_quality_latest.json"
    latest_md = args.reports_dir / "similar_papers_quality_latest.md"
    history_json = args.reports_dir / "history" / f"similar_papers_quality_{run_ts}.json"
    history_md = args.reports_dir / "history" / f"similar_papers_quality_{run_ts}.md"

    dump_json(latest_json, quality_report)
    dump_text(latest_md, build_markdown(quality_report))
    dump_json(history_json, quality_report)
    dump_text(history_md, build_markdown(quality_report))

    for key, value in quality_report["summary"].items():
        print(f"[OK] {key}={value}")

    for key, value in checks.items():
        print(f"[OK] {key}={value}")

    print(f"[OK] ok={quality_report['verdict']['ok']}")
    print(f"[OK] required_failed_count={quality_report['verdict']['required_failed_count']}")
    print(f"[OK] required_failed_checks={quality_report['verdict']['required_failed_checks']}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {history_json}")
    print(f"[OK] history Markdown: {history_md}")

    if args.strict and not quality_report["verdict"]["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()