from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from radar_core.ranking.feature_ranking import ALLOWED_SORT_FIELDS


DEFAULT_RANKING_REPORT_PATH = Path("artifacts/reports/ranking/demo_radar_ranking_latest.json")
DEFAULT_REPORTS_DIR = Path("artifacts/reports/ranking")

SCORE_FIELDS = [
    "radar_score",
    "implementation_readiness_score",
    "source_confidence_score",
    "citation_signal_score",
    "recency_score",
]


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
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def is_score_in_range(value: Any) -> bool:
    numeric = safe_float(value, default=-1.0)
    return 0.0 <= numeric <= 1.0


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Ranking report quality check")
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
        if key == "samples":
            continue
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

    samples = report["summary"].get("samples") or {}
    non_empty_samples = {key: value for key, value in samples.items() if value}
    if non_empty_samples:
        lines.append("## Samples")
        for key, value in non_empty_samples.items():
            lines.append(f"### {key}")
            lines.append("```json")
            lines.append(json.dumps(value, ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("")

    return "\n".join(lines)


def check_ranking_mode(payload: dict[str, Any], *, sample_limit: int) -> dict[str, Any]:
    results = payload.get("results")
    if not isinstance(results, list):
        results = []

    sort_by = payload.get("sort_by")
    descending = bool(payload.get("descending", True))
    top_k = int(payload.get("top_k") or 0)
    input_rows_count = int(payload.get("input_rows_count") or 0)
    filtered_rows_count = int(payload.get("filtered_rows_count") or 0)
    returned_rows_count = int(payload.get("returned_rows_count") or 0)

    missing_canonical_id_count = 0
    duplicate_canonical_id_count = 0
    score_range_violations_count = 0
    missing_required_field_count = 0

    canonical_ids: list[str] = []
    score_range_samples: list[dict[str, Any]] = []
    missing_required_samples: list[dict[str, Any]] = []

    required_result_fields = [
        "canonical_id",
        "title",
        "year",
        "radar_score",
        "implementation_readiness_score",
        "source_confidence_score",
        "citation_signal_score",
        "recency_score",
    ]

    for idx, row in enumerate(results, start=1):
        if not isinstance(row, dict):
            missing_required_field_count += 1
            continue

        canonical_id = row.get("canonical_id")
        if canonical_id:
            canonical_ids.append(str(canonical_id))
        else:
            missing_canonical_id_count += 1

        missing_fields = [field for field in required_result_fields if field not in row]
        if missing_fields:
            missing_required_field_count += len(missing_fields)
            if len(missing_required_samples) < sample_limit:
                missing_required_samples.append(
                    {
                        "rank": idx,
                        "canonical_id": canonical_id,
                        "missing_fields": missing_fields,
                    }
                )

        for field in SCORE_FIELDS:
            if field not in row:
                continue
            if not is_score_in_range(row.get(field)):
                score_range_violations_count += 1
                if len(score_range_samples) < sample_limit:
                    score_range_samples.append(
                        {
                            "rank": idx,
                            "canonical_id": canonical_id,
                            "field": field,
                            "value": row.get(field),
                        }
                    )

    duplicate_ids = sorted(
        canonical_id
        for canonical_id in set(canonical_ids)
        if canonical_ids.count(canonical_id) > 1
    )
    duplicate_canonical_id_count = len(duplicate_ids)

    sorted_correctly = True
    if sort_by in ALLOWED_SORT_FIELDS and len(results) > 1:
        values = [safe_float(row.get(sort_by), default=0.0) for row in results if isinstance(row, dict)]
        if descending:
            sorted_correctly = all(values[i] >= values[i + 1] for i in range(len(values) - 1))
        else:
            sorted_correctly = all(values[i] <= values[i + 1] for i in range(len(values) - 1))

    summary = {
        "mode": "ranking",
        "sort_by": sort_by,
        "descending": descending,
        "top_k": top_k,
        "input_rows_count": input_rows_count,
        "filtered_rows_count": filtered_rows_count,
        "returned_rows_count": returned_rows_count,
        "actual_results_count": len(results),
        "missing_canonical_id_count": missing_canonical_id_count,
        "duplicate_canonical_id_count": duplicate_canonical_id_count,
        "score_range_violations_count": score_range_violations_count,
        "missing_required_field_count": missing_required_field_count,
        "samples": {
            "duplicate_canonical_ids": duplicate_ids[:sample_limit],
            "score_range_violations": score_range_samples,
            "missing_required_fields": missing_required_samples,
        },
    }

    checks = {
        "sort_by_supported": sort_by in ALLOWED_SORT_FIELDS,
        "input_rows_non_empty": input_rows_count > 0,
        "filtered_rows_ge_returned_rows": filtered_rows_count >= returned_rows_count,
        "returned_rows_match_results_count": returned_rows_count == len(results),
        "returned_rows_le_top_k": returned_rows_count <= top_k if top_k > 0 else False,
        "canonical_ids_present": missing_canonical_id_count == 0,
        "canonical_ids_unique": duplicate_canonical_id_count == 0,
        "scores_in_range": score_range_violations_count == 0,
        "required_result_fields_present": missing_required_field_count == 0,
        "sorted_correctly": sorted_correctly,
    }

    return {"summary": summary, "checks": checks}


def check_explain_mode(payload: dict[str, Any]) -> dict[str, Any]:
    explanation = payload.get("explanation")
    found = bool(payload.get("found"))

    scores = explanation.get("scores") if isinstance(explanation, dict) else {}
    if not isinstance(scores, dict):
        scores = {}

    score_range_violations_count = sum(
        1
        for field in SCORE_FIELDS
        if field in scores and not is_score_in_range(scores.get(field))
    )

    summary = {
        "mode": "explain",
        "canonical_id": payload.get("canonical_id"),
        "input_rows_count": payload.get("input_rows_count"),
        "found": found,
        "score_range_violations_count": score_range_violations_count,
        "samples": {},
    }

    checks = {
        "canonical_id_present": bool(payload.get("canonical_id")),
        "input_rows_non_empty": int(payload.get("input_rows_count") or 0) > 0,
        "paper_found": found,
        "explanation_present": isinstance(explanation, dict),
        "scores_present": bool(scores),
        "scores_in_range": score_range_violations_count == 0,
    }

    return {"summary": summary, "checks": checks}


def check_report(report_path: Path, *, sample_limit: int) -> dict[str, Any]:
    report_exists = report_path.exists()
    payload = load_json(report_path)

    mode = payload.get("mode")
    if mode == "explain":
        result = check_explain_mode(payload)
    else:
        result = check_ranking_mode(payload, sample_limit=sample_limit)

    checks = {
        "ranking_report_exists": report_exists,
        "report_name_ok": payload.get("report_name") == "demo_radar_ranking",
        "mode_supported": mode in {"ranking", "explain"},
        **result["checks"],
    }

    required_check_names = list(checks.keys())
    required_failed_checks = [name for name in required_check_names if not checks.get(name, False)]

    verdict = {
        "required_check_count": len(required_check_names),
        "required_failed_count": len(required_failed_checks),
        "required_failed_checks": required_failed_checks,
        "ok": len(required_failed_checks) == 0,
    }

    return {
        "summary": result["summary"],
        "checks": checks,
        "verdict": verdict,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate latest radar ranking report."
    )
    parser.add_argument(
        "--ranking-report-path",
        type=Path,
        default=DEFAULT_RANKING_REPORT_PATH,
    )
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--sample-limit", type=int, default=20)
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    result = check_report(
        args.ranking_report_path,
        sample_limit=max(1, args.sample_limit),
    )

    report = {
        "report_name": "ranking_report_quality",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "strict": bool(args.strict),
        "inputs": {
            "ranking_report_path": normalize_path(args.ranking_report_path),
            "reports_dir": normalize_path(args.reports_dir),
        },
        "summary": result["summary"],
        "checks": result["checks"],
        "verdict": result["verdict"],
    }

    latest_json = args.reports_dir / "ranking_report_quality_latest.json"
    latest_md = args.reports_dir / "ranking_report_quality_latest.md"
    history_json = args.reports_dir / "history" / f"ranking_report_quality_{run_ts}.json"
    history_md = args.reports_dir / "history" / f"ranking_report_quality_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(history_json, report)
    dump_text(history_md, build_markdown(report))

    summary = report["summary"]
    verdict = report["verdict"]

    print(f"[OK] mode={summary.get('mode')}")
    print(f"[OK] ranking_report_exists={report['checks']['ranking_report_exists']}")
    print(f"[OK] input_rows_count={summary.get('input_rows_count')}")
    print(f"[OK] returned_rows_count={summary.get('returned_rows_count')}")
    print(f"[OK] missing_canonical_id_count={summary.get('missing_canonical_id_count')}")
    print(f"[OK] duplicate_canonical_id_count={summary.get('duplicate_canonical_id_count')}")
    print(f"[OK] score_range_violations_count={summary.get('score_range_violations_count')}")

    for key, value in report["checks"].items():
        print(f"[OK] {key}={value}")

    print(f"[OK] ok={verdict['ok']}")
    print(f"[OK] required_failed_count={verdict['required_failed_count']}")
    print(f"[OK] required_failed_checks={verdict['required_failed_checks']}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {history_json}")
    print(f"[OK] history Markdown: {history_md}")

    if args.strict and not verdict["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()