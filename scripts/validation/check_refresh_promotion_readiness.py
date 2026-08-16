from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


REPORT_NAME = "refresh_promotion_readiness"
SCHEMA_VERSION = "refresh_promotion_readiness_v0.1"

DEFAULT_CANONICAL_PATH = Path("data/analytics/reconciled/canonical_documents.jsonl")
DEFAULT_UPDATE_DIR = Path("artifacts/reports/update")
DEFAULT_VALIDATION_DIR = Path("artifacts/reports/validation")


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def paths_match(left: Path | str | None, right: Path | str | None) -> bool:
    left_text = normalize_path(left)
    right_text = normalize_path(right)
    if not left_text or not right_text:
        return False
    if left_text == right_text:
        return True
    return left_text.endswith(f"/{right_text}") or right_text.endswith(f"/{left_text}")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: Mapping[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        return payload
    return {}


def as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def dig(data: Any, *keys: str, default: Any = None) -> Any:
    cur = data
    for key in keys:
        if not isinstance(cur, Mapping):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def report_ok(report: Mapping[str, Any]) -> bool:
    if not report:
        return False
    if "ok" in report:
        return bool(report.get("ok"))
    verdict_ok = dig(report, "verdict", "ok", default=None)
    if verdict_ok is not None:
        return bool(verdict_ok)
    return safe_int(dig(report, "verdict", "required_failed_count", default=1)) == 0


def report_required_failed_count(report: Mapping[str, Any]) -> int:
    if not report:
        return 1
    return safe_int(dig(report, "verdict", "required_failed_count", default=1), default=1)


def report_required_failed_checks(report: Mapping[str, Any]) -> list[str]:
    value = dig(report, "verdict", "required_failed_checks", default=[])
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def report_candidate_path(report: Mapping[str, Any]) -> str | None:
    return (
        dig(report, "inputs", "candidate_path", default=None)
        or dig(report, "candidate", "path", default=None)
    )


def candidate_path_from_pipeline(pipeline: Mapping[str, Any]) -> str | None:
    return dig(pipeline, "candidate", "path", default=None)


def build_checks(
    *,
    canonical_path: Path,
    candidate_path: Path | None,
    preflight: Mapping[str, Any],
    pipeline: Mapping[str, Any],
    delta: Mapping[str, Any],
    alignment: Mapping[str, Any],
    source: Mapping[str, Any],
    require_db_smoke: bool,
) -> dict[str, bool]:
    preflight_candidate_path = report_candidate_path(preflight)
    pipeline_candidate_path = candidate_path_from_pipeline(pipeline)
    delta_candidate_path = report_candidate_path(delta)
    alignment_candidate_path = report_candidate_path(alignment)
    source_candidate_path = report_candidate_path(source)
    resolved_candidate_text = normalize_path(candidate_path) or pipeline_candidate_path
    resolved_candidate = Path(str(resolved_candidate_text)) if resolved_candidate_text else None

    delta_summary = as_mapping(delta.get("summary"))
    alignment_summary = as_mapping(alignment.get("summary"))
    source_summary = as_mapping(source.get("summary"))
    alignment_signals = as_mapping(dig(alignment, "diagnostics", "signals", default={}))
    source_signals = as_mapping(dig(source, "diagnostics", "signals", default={}))
    preflight_checks = as_mapping(preflight.get("checks"))
    pipeline_execution = as_mapping(pipeline.get("execution_summary"))

    checks = {
        "preflight_report_exists": bool(preflight),
        "preflight_ok": report_ok(preflight),
        "preflight_required_failed_count_zero": report_required_failed_count(preflight) == 0,
        "preflight_merge_snapshots_cover_baseline": bool(
            preflight_checks.get("merge_snapshots_cover_baseline_alignment_sources")
        ),
        "preflight_promote_script_keeps_backup": bool(
            preflight_checks.get("promote_script_keeps_backup")
        ),
        "pipeline_report_exists": bool(pipeline),
        "pipeline_execute_mode": pipeline.get("mode") == "execute",
        "pipeline_candidate_rehearsal": bool(
            pipeline.get("pipeline_mode") == "candidate_rehearsal"
            or dig(pipeline, "inputs", "candidate_rehearsal", default=False)
        ),
        "pipeline_stopped_at_candidate_delta_review": (
            pipeline.get("stop_after") == "candidate_delta_review"
        ),
        "pipeline_failed_count_zero": (
            safe_int(pipeline_execution.get("failed_count"), default=1) == 0
        ),
        "pipeline_failed_step_names_empty": not bool(
            pipeline_execution.get("failed_step_names") or []
        ),
        "pipeline_all_successful": bool(
            pipeline_execution.get("all_successful", False)
        ),
        "candidate_path_resolved": resolved_candidate is not None,
        "candidate_path_exists": bool(resolved_candidate and resolved_candidate.exists()),
        "candidate_path_differs_from_canonical": bool(
            resolved_candidate is not None
            and not paths_match(resolved_candidate, canonical_path)
        ),
        "preflight_report_matches_candidate": paths_match(
            preflight_candidate_path,
            resolved_candidate,
        ),
        "delta_report_exists": bool(delta),
        "delta_report_matches_candidate": paths_match(delta_candidate_path, resolved_candidate),
        "delta_verdict_ok": report_ok(delta),
        "delta_required_failed_count_zero": report_required_failed_count(delta) == 0,
        "delta_promotion_ready": bool(
            dig(delta, "verdict", "promotion_delta_review_ready", default=False)
        ),
        "delta_manual_review_not_required": not bool(
            dig(delta, "verdict", "manual_review_required", default=True)
        ),
        "delta_removed_count_zero": safe_int(delta_summary.get("removed_count")) == 0,
        "delta_destructive_identifier_churn_zero": safe_int(
            delta_summary.get("destructive_identifier_churn_count")
        )
        == 0,
        "delta_candidate_not_smaller_than_canonical": safe_int(
            delta_summary.get("doc_count_delta")
        )
        >= 0,
        "alignment_report_exists": bool(alignment),
        "alignment_report_matches_candidate": paths_match(
            alignment_candidate_path,
            resolved_candidate,
        ),
        "alignment_promotion_safe": bool(
            dig(alignment, "verdict", "promotion_safe", default=False)
        ),
        "alignment_regression_absent": not bool(
            alignment_signals.get("alignment_coverage_regression_detected")
        ),
        "alignment_lost_observations_zero": safe_int(
            alignment_summary.get("lost_alignment_source_observation_count")
        )
        == 0,
        "source_report_exists": bool(source),
        "source_report_matches_candidate": paths_match(
            source_candidate_path,
            resolved_candidate,
        ),
        "source_promotion_safe": bool(
            dig(source, "verdict", "promotion_safe", default=False)
        ),
        "source_regression_absent": not bool(
            source_signals.get("source_coverage_regression_detected")
        ),
        "source_removed_count_zero": safe_int(source_summary.get("removed_count")) == 0,
        "source_identifier_loss_zero": safe_int(
            source_summary.get("retained_identifier_loss_count")
        )
        == 0,
        "source_id_loss_zero": safe_int(
            source_summary.get("retained_source_id_loss_count")
        )
        == 0,
        "source_multisource_collapse_zero": safe_int(
            source_summary.get("retained_multisource_to_arxiv_only_count")
        )
        == 0,
    }

    if require_db_smoke:
        checks.update(
            {
                "db_smoke_ok": bool(preflight_checks.get("db_smoke_ok")),
                "db_ping_true": bool(preflight_checks.get("db_ping_true")),
                "db_doc_count_matches_canonical": bool(
                    preflight_checks.get("db_doc_count_matches_canonical")
                ),
            }
        )

    return checks


def build_required_check_names(require_db_smoke: bool) -> list[str]:
    names = [
        "preflight_report_exists",
        "preflight_ok",
        "preflight_required_failed_count_zero",
        "preflight_merge_snapshots_cover_baseline",
        "preflight_promote_script_keeps_backup",
        "pipeline_report_exists",
        "pipeline_execute_mode",
        "pipeline_candidate_rehearsal",
        "pipeline_stopped_at_candidate_delta_review",
        "pipeline_failed_count_zero",
        "pipeline_failed_step_names_empty",
        "pipeline_all_successful",
        "candidate_path_resolved",
        "candidate_path_exists",
        "candidate_path_differs_from_canonical",
        "preflight_report_matches_candidate",
        "delta_report_exists",
        "delta_report_matches_candidate",
        "delta_verdict_ok",
        "delta_required_failed_count_zero",
        "delta_promotion_ready",
        "delta_manual_review_not_required",
        "delta_removed_count_zero",
        "delta_destructive_identifier_churn_zero",
        "delta_candidate_not_smaller_than_canonical",
        "alignment_report_exists",
        "alignment_report_matches_candidate",
        "alignment_promotion_safe",
        "alignment_regression_absent",
        "alignment_lost_observations_zero",
        "source_report_exists",
        "source_report_matches_candidate",
        "source_promotion_safe",
        "source_regression_absent",
        "source_removed_count_zero",
        "source_identifier_loss_zero",
        "source_id_loss_zero",
        "source_multisource_collapse_zero",
    ]
    if require_db_smoke:
        names.extend(
            [
                "db_smoke_ok",
                "db_ping_true",
                "db_doc_count_matches_canonical",
            ]
        )
    return names


def build_report(
    *,
    canonical_path: Path,
    candidate_path: Path | None,
    update_dir: Path,
    validation_dir: Path,
    reports_dir: Path,
    require_db_smoke: bool,
    strict: bool,
) -> dict[str, Any]:
    preflight_path = update_dir / "refresh_preflight_contract_latest.json"
    pipeline_path = update_dir / "run_refresh_pipeline_v1_latest.json"
    delta_path = validation_dir / "refresh_candidate_delta_review_latest.json"
    alignment_path = validation_dir / "refresh_alignment_coverage_diagnostics_latest.json"
    source_path = validation_dir / "refresh_source_coverage_diagnostics_latest.json"

    preflight = read_json(preflight_path)
    pipeline = read_json(pipeline_path)
    delta = read_json(delta_path)
    alignment = read_json(alignment_path)
    source = read_json(source_path)

    resolved_candidate_path = candidate_path
    if resolved_candidate_path is None:
        raw_candidate = candidate_path_from_pipeline(pipeline)
        resolved_candidate_path = Path(str(raw_candidate)) if raw_candidate else None

    checks = build_checks(
        canonical_path=canonical_path,
        candidate_path=resolved_candidate_path,
        preflight=preflight,
        pipeline=pipeline,
        delta=delta,
        alignment=alignment,
        source=source,
        require_db_smoke=require_db_smoke,
    )
    required_check_names = build_required_check_names(require_db_smoke)
    required_failed_checks = [
        name for name in required_check_names if not checks.get(name, False)
    ]

    delta_summary = as_mapping(delta.get("summary"))
    source_summary = as_mapping(source.get("summary"))
    alignment_summary = as_mapping(alignment.get("summary"))
    pipeline_candidate_summary = as_mapping(pipeline.get("candidate_summary"))
    source_signals = as_mapping(dig(source, "diagnostics", "signals", default={}))

    promotion_ready = not required_failed_checks

    return {
        "report_name": REPORT_NAME,
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "run_ts": utc_now_ts(),
        "strict": bool(strict),
        "status": "read_only_validation",
        "read_only": True,
        "canonical_truth_mutated": False,
        "promotion_executed": False,
        "derived_layers_rebuilt": False,
        "inputs": {
            "canonical_path": normalize_path(canonical_path),
            "candidate_path": normalize_path(resolved_candidate_path),
            "update_dir": normalize_path(update_dir),
            "validation_dir": normalize_path(validation_dir),
            "reports_dir": normalize_path(reports_dir),
            "require_db_smoke": bool(require_db_smoke),
        },
        "reports": {
            "preflight": {
                "path": normalize_path(preflight_path),
                "exists": bool(preflight),
                "ok": report_ok(preflight),
                "required_failed_count": report_required_failed_count(preflight),
                "required_failed_checks": report_required_failed_checks(preflight),
                "candidate_path": report_candidate_path(preflight),
            },
            "pipeline": {
                "path": normalize_path(pipeline_path),
                "exists": bool(pipeline),
                "mode": pipeline.get("mode"),
                "pipeline_mode": pipeline.get("pipeline_mode"),
                "stop_after": pipeline.get("stop_after"),
                "failed_count": safe_int(
                    dig(pipeline, "execution_summary", "failed_count", default=1),
                    default=1,
                ),
                "failed_step_names": dig(
                    pipeline,
                    "execution_summary",
                    "failed_step_names",
                    default=[],
                ),
                "candidate_path": candidate_path_from_pipeline(pipeline),
            },
            "candidate_delta": {
                "path": normalize_path(delta_path),
                "exists": bool(delta),
                "ok": report_ok(delta),
                "required_failed_count": report_required_failed_count(delta),
                "required_failed_checks": report_required_failed_checks(delta),
                "candidate_path": report_candidate_path(delta),
            },
            "alignment_coverage": {
                "path": normalize_path(alignment_path),
                "exists": bool(alignment),
                "promotion_safe": dig(
                    alignment,
                    "verdict",
                    "promotion_safe",
                    default=False,
                ),
                "candidate_path": report_candidate_path(alignment),
            },
            "source_coverage": {
                "path": normalize_path(source_path),
                "exists": bool(source),
                "promotion_safe": dig(source, "verdict", "promotion_safe", default=False),
                "candidate_path": report_candidate_path(source),
            },
        },
        "checks": checks,
        "summary": {
            "promotion_ready": promotion_ready,
            "required_failed_count": len(required_failed_checks),
            "candidate_path": normalize_path(resolved_candidate_path),
            "candidate_doc_count": safe_int(
                pipeline_candidate_summary.get("doc_count"),
                default=safe_int(delta_summary.get("candidate_doc_count")),
            ),
            "baseline_doc_count": safe_int(delta_summary.get("baseline_doc_count")),
            "doc_count_delta": safe_int(delta_summary.get("doc_count_delta")),
            "added_count": safe_int(delta_summary.get("added_count")),
            "removed_count": safe_int(delta_summary.get("removed_count")),
            "destructive_identifier_churn_count": safe_int(
                delta_summary.get("destructive_identifier_churn_count")
            ),
            "additive_identifier_churn_count": safe_int(
                delta_summary.get("additive_identifier_churn_count")
            ),
            "retained_source_family_changed_count": safe_int(
                source_summary.get("retained_source_family_changed_count")
            ),
            "additive_source_coverage_detected": bool(
                source_signals.get("additive_source_coverage_detected")
            ),
            "lost_alignment_source_observation_count": safe_int(
                alignment_summary.get("lost_alignment_source_observation_count")
            ),
            "require_db_smoke": bool(require_db_smoke),
        },
        "verdict": {
            "ok": promotion_ready,
            "promotion_ready": promotion_ready,
            "required_failed_count": len(required_failed_checks),
            "required_failed_checks": required_failed_checks,
            "canonical_truth_mutation_required": False,
            "derived_layer_mutation_required": False,
            "manual_review_required": not promotion_ready,
        },
    }


def build_markdown(report: Mapping[str, Any]) -> str:
    lines: list[str] = [
        "# Refresh promotion readiness v0.1",
        "",
        f"- Generated at: `{report['generated_at_utc']}`",
        f"- Run ts: `{report['run_ts']}`",
        f"- Strict: `{report['strict']}`",
        f"- Read only: `{report['read_only']}`",
        "",
        "## Summary",
        "",
    ]

    for name, value in report["summary"].items():
        lines.append(f"- {name}: `{value}`")

    lines.extend(["", "## Required Checks", ""])
    for name, value in report["checks"].items():
        lines.append(f"- {name}: `{value}`")

    lines.extend(["", "## Verdict", ""])
    for name, value in report["verdict"].items():
        lines.append(f"- {name}: `{value}`")

    lines.extend(["", "## Reports", ""])
    for name, value in report["reports"].items():
        lines.append(f"- {name}: `{value}`")

    return "\n".join(lines)


def write_reports(
    report: Mapping[str, Any],
    reports_dir: Path,
) -> tuple[Path, Path, Path, Path]:
    run_ts = str(report["run_ts"])
    latest_json = reports_dir / f"{REPORT_NAME}_latest.json"
    latest_md = reports_dir / f"{REPORT_NAME}_latest.md"
    hist_json = reports_dir / "history" / f"{REPORT_NAME}_{run_ts}.json"
    hist_md = reports_dir / "history" / f"{REPORT_NAME}_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(hist_json, report)
    dump_text(hist_md, build_markdown(report))

    return latest_json, latest_md, hist_json, hist_md


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate latest refresh rehearsal reports into one read-only "
            "promotion-readiness gate."
        )
    )
    parser.add_argument(
        "--canonical-path",
        type=Path,
        default=DEFAULT_CANONICAL_PATH,
        help="Current stable canonical JSONL path.",
    )
    parser.add_argument(
        "--candidate-path",
        type=Path,
        default=None,
        help="Expected candidate path. Defaults to the latest pipeline report candidate.",
    )
    parser.add_argument(
        "--update-dir",
        type=Path,
        default=DEFAULT_UPDATE_DIR,
        help="Directory containing latest update reports.",
    )
    parser.add_argument(
        "--validation-dir",
        type=Path,
        default=DEFAULT_VALIDATION_DIR,
        help="Directory containing latest validation reports.",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=DEFAULT_VALIDATION_DIR,
        help="Directory where readiness reports are written.",
    )
    parser.add_argument(
        "--require-db-smoke",
        action="store_true",
        help="Treat preflight DB smoke checks as promotion-readiness requirements.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when promotion readiness checks fail.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = build_report(
        canonical_path=args.canonical_path,
        candidate_path=args.candidate_path,
        update_dir=args.update_dir,
        validation_dir=args.validation_dir,
        reports_dir=args.reports_dir,
        require_db_smoke=bool(args.require_db_smoke),
        strict=bool(args.strict),
    )
    latest_json, latest_md, hist_json, hist_md = write_reports(report, args.reports_dir)

    verdict = report["verdict"]
    summary = report["summary"]
    status = "OK" if verdict["ok"] else "FAILED"
    print(f"[{status}] report={REPORT_NAME}")
    print(f"[{status}] read_only=True")
    print(f"[{status}] promotion_ready={verdict['promotion_ready']}")
    print(f"[{status}] candidate_path={summary['candidate_path']}")
    print(f"[{status}] baseline_doc_count={summary['baseline_doc_count']}")
    print(f"[{status}] candidate_doc_count={summary['candidate_doc_count']}")
    print(f"[{status}] doc_count_delta={summary['doc_count_delta']}")
    print(f"[{status}] added_count={summary['added_count']}")
    print(f"[{status}] removed_count={summary['removed_count']}")
    print(
        f"[{status}] destructive_identifier_churn_count="
        f"{summary['destructive_identifier_churn_count']}"
    )
    print(
        f"[{status}] lost_alignment_source_observation_count="
        f"{summary['lost_alignment_source_observation_count']}"
    )
    print(
        f"[{status}] retained_source_family_changed_count="
        f"{summary['retained_source_family_changed_count']}"
    )
    print(
        f"[{status}] additive_source_coverage_detected="
        f"{summary['additive_source_coverage_detected']}"
    )
    print(f"[{status}] required_failed_count={verdict['required_failed_count']}")
    print(f"[{status}] required_failed_checks={verdict['required_failed_checks']}")
    print(f"[{status}] latest JSON: {latest_json}")
    print(f"[{status}] latest Markdown: {latest_md}")
    print(f"[{status}] history JSON: {hist_json}")
    print(f"[{status}] history Markdown: {hist_md}")

    if args.strict and not verdict["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
