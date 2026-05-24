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
    raise RuntimeError(
        "PyYAML is required for controlled search quality experiments validation."
    ) from exc


DEFAULT_CONFIG_PATH = Path("configs/search_quality_controlled_experiments_v1.yaml")
DEFAULT_REPORT_PATH = Path("artifacts/reports/evaluation/search_quality_controlled_experiments_latest.json")
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

    summary = report.get("summary") or {}
    variants = report.get("variants") or []
    variant_summary = report.get("variant_summary") or []
    rankings = report.get("rankings") or {}
    pareto = report.get("pareto_frontier") or []
    rank_effects = report.get("rank_effects") or []
    weight_effects = report.get("weight_effects") or []
    query_winners = report.get("query_winners") or []
    recommendations = report.get("recommendations") or []

    min_enabled_cases = safe_int(thresholds.get("min_enabled_cases"), 1)
    min_variants_count = safe_int(thresholds.get("min_variants_count"), 1)
    min_hybrid_variants_count = safe_int(thresholds.get("min_hybrid_variants_count"), 1)

    baseline_modes = {
        item.get("mode")
        for item in variant_summary
        if item.get("variant_type") == "baseline"
    }

    return {
        "report_path_exists": report_path.exists(),
        "schema_version_ok": report.get("schema_version") == "search_quality_controlled_experiments_v1",
        "runtime_ready": bool((report.get("runtime") or {}).get("ready", True)),
        "enabled_cases_min_met": safe_int(summary.get("enabled_cases_count")) >= min_enabled_cases,
        "variants_min_met": safe_int(summary.get("variants_count")) >= min_variants_count,
        "hybrid_variants_min_met": safe_int(summary.get("hybrid_variants_count")) >= min_hybrid_variants_count,
        "runs_count_matches": safe_int(summary.get("runs_count")) == (
            safe_int(summary.get("enabled_cases_count")) * safe_int(summary.get("variants_count"))
        ),
        "no_runtime_errors": safe_int(summary.get("error_count")) == 0,
        "variants_present": bool(variants),
        "variant_summary_present": bool(variant_summary),
        "rankings_present": bool(rankings),
        "pareto_frontier_present": bool(pareto),
        "rank_effects_present": bool(rank_effects),
        "weight_effects_present": bool(weight_effects),
        "query_winners_present": bool(query_winners),
        "recommendations_present": bool(recommendations),
        "baseline_lexical_present": "lexical" in baseline_modes,
        "baseline_dense_present": "dense" in baseline_modes,
        "metrics_finite": all_numbers_finite(report),
    }


def required_check_names(*, strict: bool) -> list[str]:
    base = [
        "report_path_exists",
        "schema_version_ok",
        "runtime_ready",
        "enabled_cases_min_met",
        "variants_min_met",
        "hybrid_variants_min_met",
        "runs_count_matches",
        "no_runtime_errors",
        "variants_present",
        "variant_summary_present",
        "rankings_present",
        "weight_effects_present",
        "query_winners_present",
        "baseline_lexical_present",
        "baseline_dense_present",
        "metrics_finite",
    ]

    if strict:
        base.extend(
            [
                "pareto_frontier_present",
                "rank_effects_present",
                "recommendations_present",
            ]
        )

    return base


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Controlled search quality experiments quality check")
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
    parser = argparse.ArgumentParser(
        description="Validate latest controlled search quality experiments report."
    )
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

    summary = report.get("summary") or {}
    pareto = report.get("pareto_frontier") or []
    recommendations = report.get("recommendations") or []

    quality_report = {
        "schema_version": "search_quality_controlled_experiments_quality_v1",
        "report_name": "check_search_quality_controlled_experiments",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "strict": bool(args.strict),
        "inputs": {
            "config_path": normalize_path(args.config_path),
            "report_path": normalize_path(args.report_path),
        },
        "extracted_values": {
            "experiment_schema_version": report.get("schema_version"),
            "backend_mode": (report.get("runtime") or {}).get("backend_mode"),
            "build_id": (report.get("runtime") or {}).get("build_id"),
            "corpus_doc_count": (report.get("runtime") or {}).get("corpus_doc_count"),
            "enabled_cases_count": summary.get("enabled_cases_count"),
            "variants_count": summary.get("variants_count"),
            "hybrid_variants_count": summary.get("hybrid_variants_count"),
            "runs_count": summary.get("runs_count"),
            "error_count": summary.get("error_count"),
            "pareto_frontier_count": len(pareto),
            "recommendations_count": len(recommendations),
        },
        "checks": checks,
        "required_checks": required,
        "required_failed_count": len(required_failed),
        "required_failed_checks": required_failed,
        "ok": len(required_failed) == 0,
    }

    output_dir = args.output_dir
    latest_json = output_dir / "search_quality_controlled_experiments_quality_latest.json"
    latest_md = output_dir / "search_quality_controlled_experiments_quality_latest.md"
    hist_json = output_dir / "history" / f"search_quality_controlled_experiments_quality_{run_ts}.json"
    hist_md = output_dir / "history" / f"search_quality_controlled_experiments_quality_{run_ts}.md"

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
