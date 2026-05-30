from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PyYAML is required for search quality experiment validation.") from exc


DEFAULT_CONFIG_PATH = Path("configs/search_quality_experiments_v1.yaml")
DEFAULT_REPORT_PATH = Path("artifacts/reports/evaluation/search_quality_experiments_latest.json")
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/validation")


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Config must be a YAML mapping: {path}")
    return payload


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"JSON report not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON report must be an object: {path}")
    return payload


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def all_numbers_finite(value: Any) -> bool:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return True
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(all_numbers_finite(x) for x in value)
    if isinstance(value, dict):
        return all(all_numbers_finite(v) for v in value.values())
    return True


def build_checks(
    *,
    config: dict[str, Any],
    report: dict[str, Any],
    report_path: Path,
) -> dict[str, bool]:
    thresholds = config.get("thresholds") or {}

    mode_table = report.get("mode_table") or []
    rankings = report.get("rankings") or {}
    pareto = report.get("pareto_frontier") or []
    pairwise = report.get("pairwise_summary") or []
    query_signal = report.get("query_signal_summary") or {}
    recommendations = report.get("recommendations") or []
    group_recommendations = report.get("group_mode_recommendations") or []
    input_eval = report.get("input_retrieval_eval") or {}

    min_modes_count = safe_int(thresholds.get("min_modes_count"), 1)
    min_queries_count = safe_int(thresholds.get("min_queries_count"), 1)

    return {
        "report_path_exists": report_path.exists(),
        "schema_version_ok": report.get("schema_version") == "search_quality_experiments_v1",
        "input_retrieval_eval_schema_ok": input_eval.get("schema_version") == "retrieval_eval_v1",
        "input_retrieval_eval_cases_min_met": safe_int(input_eval.get("enabled_cases_count")) >= min_queries_count,
        "mode_table_present": bool(mode_table),
        "mode_table_min_modes_met": len(mode_table) >= min_modes_count,
        "rankings_present": bool(rankings),
        "pareto_frontier_present": bool(pareto),
        "pairwise_summary_present": bool(pairwise),
        "query_signal_summary_present": bool(query_signal),
        "recommendations_present": bool(recommendations),
        "group_mode_recommendations_present": bool(group_recommendations),
        "group_mode_recommendations_non_empty": bool(group_recommendations),
        "group_mode_recommendations_have_best_modes": all(
            bool(item.get("group"))
            and bool(item.get("best_mode_by_composite"))
            and bool(item.get("best_mode_by_recall"))
            for item in group_recommendations
            if isinstance(item, dict)
        ),
        "metrics_finite": all_numbers_finite(report),
    }


def required_check_names(*, strict: bool) -> list[str]:
    base = [
        "report_path_exists",
        "schema_version_ok",
        "input_retrieval_eval_schema_ok",
        "input_retrieval_eval_cases_min_met",
        "mode_table_present",
        "mode_table_min_modes_met",
        "rankings_present",
        "pairwise_summary_present",
        "query_signal_summary_present",
        "metrics_finite",
    ]

    if strict:
        base.extend(
            [
                "pareto_frontier_present",
                "recommendations_present",
                "group_mode_recommendations_present",
                "group_mode_recommendations_non_empty",
                "group_mode_recommendations_have_best_modes",
            ]
        )

    return base


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Search quality experiments quality check")
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

    if report["required_failed_checks"]:
        lines.append("## Required failures")
        for item in report["required_failed_checks"]:
            lines.append(f"- `{item}`")
        lines.append("")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate latest search quality experiments report.")
    parser.add_argument("--config-path", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_ts = utc_now_ts()

    config = load_yaml(args.config_path)
    report = load_json(args.report_path)

    checks = build_checks(config=config, report=report, report_path=args.report_path)
    required = required_check_names(strict=args.strict)
    required_failed = [name for name in required if not checks.get(name, False)]

    mode_table = report.get("mode_table") or []
    pareto = report.get("pareto_frontier") or []
    recommendations = report.get("recommendations") or []
    group_recommendations = report.get("group_mode_recommendations") or []
    input_eval = report.get("input_retrieval_eval") or {}
    query_signal = report.get("query_signal_summary") or {}

    quality_report = {
        "schema_version": "search_quality_experiments_quality_v1",
        "report_name": "check_search_quality_experiments",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "strict": bool(args.strict),
        "inputs": {
            "config_path": normalize_path(args.config_path),
            "report_path": normalize_path(args.report_path),
        },
        "extracted_values": {
            "experiment_schema_version": report.get("schema_version"),
            "input_retrieval_eval_schema": input_eval.get("schema_version"),
            "build_id": input_eval.get("build_id"),
            "corpus_doc_count": input_eval.get("corpus_doc_count"),
            "enabled_cases_count": input_eval.get("enabled_cases_count"),
            "mode_table_count": len(mode_table),
            "pareto_frontier_count": len(pareto),
            "recommendations_count": len(recommendations),
            "group_mode_recommendations_count": len(group_recommendations),
            "failed_mode_counts": query_signal.get("failed_mode_counts") or {},
            "note_counts": query_signal.get("note_counts") or {},
        },
        "checks": checks,
        "required_checks": required,
        "required_failed_count": len(required_failed),
        "required_failed_checks": required_failed,
        "ok": len(required_failed) == 0,
    }

    output_dir = args.output_dir
    latest_json = output_dir / "search_quality_experiments_quality_latest.json"
    latest_md = output_dir / "search_quality_experiments_quality_latest.md"
    hist_json = output_dir / "history" / f"search_quality_experiments_quality_{run_ts}.json"
    hist_md = output_dir / "history" / f"search_quality_experiments_quality_{run_ts}.md"

    dump_json(latest_json, quality_report)
    dump_text(latest_md, build_markdown(quality_report))
    dump_json(hist_json, quality_report)
    dump_text(hist_md, build_markdown(quality_report))

    print(f"[OK] report_path={args.report_path}")
    print(f"[OK] schema_version={report.get('schema_version')}")
    print(f"[OK] strict={args.strict}")
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
