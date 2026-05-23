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
        "PyYAML is required for retrieval evaluation config loading."
    ) from exc


DEFAULT_CONFIG_PATH = Path("configs/retrieval_eval_v1.yaml")
DEFAULT_REPORT_PATH = Path("artifacts/reports/evaluation/retrieval_eval_latest.json")
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/validation")


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Retrieval eval config not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        payload = yaml.safe_load(f) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Retrieval eval config must be a YAML mapping: {path}")
    return payload


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"JSON report not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON report must be an object: {path}")
    return payload


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        value = float(value)
        if not math.isfinite(value):
            return default
        return value
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def get_metric(report: dict[str, Any], mode: str, metric: str) -> float:
    return safe_float(((report.get("mode_summary") or {}).get(mode) or {}).get(metric), default=0.0)


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


def expected_modes_from_config(config: dict[str, Any]) -> list[str]:
    defaults = config.get("defaults") or {}
    return [str(x) for x in defaults.get("modes") or ["lexical", "dense", "hybrid", "hybrid_ranked"]]


def primary_k_from_config(config: dict[str, Any]) -> int:
    defaults = config.get("defaults") or {}
    return safe_int(defaults.get("primary_k"), default=10)


def build_checks(
    *,
    report: dict[str, Any],
    config: dict[str, Any],
    report_path: Path,
    strict: bool,
) -> dict[str, bool]:
    thresholds = config.get("thresholds") or {}
    expected_modes = expected_modes_from_config(config)
    primary_k = primary_k_from_config(config)

    summary = report.get("summary") or {}
    mode_summary = report.get("mode_summary") or {}
    cases = report.get("cases") or []

    enabled_cases_count = safe_int(summary.get("enabled_cases_count"))
    executed_cases_count = safe_int(summary.get("executed_cases_count"))

    all_modes_present = all(mode in mode_summary for mode in expected_modes)

    all_cases_have_all_modes = True
    no_runtime_errors = True
    for case in cases:
        runs = case.get("runs") or []
        run_modes = {run.get("mode") for run in runs}
        if not all(mode in run_modes for mode in expected_modes):
            all_cases_have_all_modes = False
        if any(run.get("error") for run in runs):
            no_runtime_errors = False

    hybrid_summary = mode_summary.get("hybrid") or {}
    empty_result_rate = safe_float(hybrid_summary.get("empty_result_rate"), default=1.0)
    hybrid_hit = safe_float(hybrid_summary.get(f"hit_at_{primary_k}"), default=0.0)
    hybrid_mrr = safe_float(hybrid_summary.get(f"mrr_at_{primary_k}"), default=0.0)
    hybrid_recall = safe_float(hybrid_summary.get(f"recall_at_{primary_k}"), default=0.0)

    return {
        "report_path_exists": report_path.exists(),
        "schema_version_ok": report.get("schema_version") == "retrieval_eval_v1",
        "runtime_ready": bool((report.get("runtime") or {}).get("ready", True)),
        "enabled_cases_min_met": enabled_cases_count >= safe_int(thresholds.get("min_enabled_cases"), default=1),
        "executed_cases_match_enabled": executed_cases_count == enabled_cases_count and enabled_cases_count > 0,
        "all_expected_modes_present": all_modes_present,
        "all_cases_have_all_expected_modes": all_cases_have_all_modes,
        "no_runtime_errors": no_runtime_errors,
        "metrics_finite": all_numbers_finite(report),
        "hybrid_empty_result_rate_within_threshold": empty_result_rate <= safe_float(thresholds.get("max_empty_result_rate"), default=1.0),
        f"hybrid_hit_at_{primary_k}_minimum_met": hybrid_hit >= safe_float(thresholds.get(f"min_hybrid_hit_at_{primary_k}"), default=0.0),
        f"hybrid_mrr_at_{primary_k}_minimum_met": hybrid_mrr >= safe_float(thresholds.get(f"min_hybrid_mrr_at_{primary_k}"), default=0.0),
        f"hybrid_recall_at_{primary_k}_minimum_met": hybrid_recall >= safe_float(thresholds.get(f"min_hybrid_recall_at_{primary_k}"), default=0.0),
    }


def required_check_names(*, strict: bool, primary_k: int) -> list[str]:
    base = [
        "report_path_exists",
        "schema_version_ok",
        "runtime_ready",
        "enabled_cases_min_met",
        "executed_cases_match_enabled",
        "all_expected_modes_present",
        "all_cases_have_all_expected_modes",
        "no_runtime_errors",
        "metrics_finite",
    ]

    if strict:
        base.extend(
            [
                "hybrid_empty_result_rate_within_threshold",
                f"hybrid_hit_at_{primary_k}_minimum_met",
                f"hybrid_mrr_at_{primary_k}_minimum_met",
                f"hybrid_recall_at_{primary_k}_minimum_met",
            ]
        )

    return base


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []

    lines.append("# Retrieval evaluation quality check")
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
        for key in report["required_failed_checks"]:
            lines.append(f"- `{key}`")
        lines.append("")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate latest retrieval evaluation report.")
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

    primary_k = primary_k_from_config(config)
    checks = build_checks(
        report=report,
        config=config,
        report_path=args.report_path,
        strict=args.strict,
    )
    required = required_check_names(strict=args.strict, primary_k=primary_k)
    required_failed = [name for name in required if not checks.get(name)]

    mode_summary = report.get("mode_summary") or {}
    hybrid_summary = mode_summary.get("hybrid") or {}

    quality_report = {
        "schema_version": "retrieval_eval_quality_v1",
        "report_name": "check_retrieval_eval",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "strict": bool(args.strict),
        "inputs": {
            "config_path": normalize_path(args.config_path),
            "report_path": normalize_path(args.report_path),
        },
        "extracted_values": {
            "eval_schema_version": report.get("schema_version"),
            "backend_mode": (report.get("runtime") or {}).get("backend_mode"),
            "build_id": (report.get("runtime") or {}).get("build_id"),
            "corpus_doc_count": (report.get("runtime") or {}).get("corpus_doc_count"),
            "enabled_cases_count": safe_int((report.get("summary") or {}).get("enabled_cases_count")),
            "executed_cases_count": safe_int((report.get("summary") or {}).get("executed_cases_count")),
            "primary_k": primary_k,
            f"hybrid_hit_at_{primary_k}": hybrid_summary.get(f"hit_at_{primary_k}"),
            f"hybrid_recall_at_{primary_k}": hybrid_summary.get(f"recall_at_{primary_k}"),
            f"hybrid_mrr_at_{primary_k}": hybrid_summary.get(f"mrr_at_{primary_k}"),
            f"hybrid_ndcg_at_{primary_k}": hybrid_summary.get(f"ndcg_at_{primary_k}"),
            "hybrid_empty_result_rate": hybrid_summary.get("empty_result_rate"),
        },
        "checks": checks,
        "required_checks": required,
        "required_failed_count": len(required_failed),
        "required_failed_checks": required_failed,
        "ok": len(required_failed) == 0,
    }

    output_dir = args.output_dir
    latest_json = output_dir / "retrieval_eval_quality_latest.json"
    latest_md = output_dir / "retrieval_eval_quality_latest.md"
    hist_json = output_dir / "history" / f"retrieval_eval_quality_{run_ts}.json"
    hist_md = output_dir / "history" / f"retrieval_eval_quality_{run_ts}.md"

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
