from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from scripts.validation.check_ranking_evaluation import (
    build_checks as build_ranking_evaluation_checks,
    required_check_names as ranking_evaluation_required_check_names,
)
from scripts.validation.check_ranking_evaluation_freshness import (
    build_freshness_report,
)


DEFAULT_CONFIG_PATH = Path("configs/ranking_evaluation_v1.yaml")
DEFAULT_REPORT_PATH = Path(
    "artifacts/reports/evaluation/ranking_evaluation_latest.json"
)
DEFAULT_RETRIEVAL_MANIFEST_PATH = Path(
    "artifacts/retrieval/manifests/latest.json"
)
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
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def load_yaml_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"YAML config not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Expected YAML mapping: {path}")
    return payload


def load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def config_permitted_outcomes(config: dict[str, Any]) -> set[str]:
    return {
        str(value)
        for value in (
            (config.get("decision_policy") or {}).get(
                "permitted_outcomes"
            )
            or []
        )
    }


def build_ranking_evidence_regression_report(
    *,
    config: dict[str, Any],
    evaluation_report: dict[str, Any],
    retrieval_manifest: dict[str, Any],
    config_path: Path,
    report_path: Path,
    retrieval_manifest_path: Path,
    strict: bool = True,
) -> dict[str, Any]:
    evaluation_checks, evaluation_diagnostics, extracted = (
        build_ranking_evaluation_checks(
            config=config,
            report=evaluation_report,
            report_path=report_path,
        )
    )
    evaluation_required = ranking_evaluation_required_check_names(
        strict=strict
    )
    evaluation_failed = [
        name
        for name in evaluation_required
        if not evaluation_checks.get(name, False)
    ]

    freshness_report = build_freshness_report(
        evaluation_report=evaluation_report,
        retrieval_manifest=retrieval_manifest,
        report_path=report_path,
        retrieval_manifest_path=retrieval_manifest_path,
    )
    freshness_checks = freshness_report.get("checks") or {}
    freshness_failed = list(
        freshness_report.get("required_failed_checks") or []
    )

    decision = evaluation_report.get("decision") or {}
    summary = evaluation_report.get("summary") or {}
    runtime = evaluation_report.get("runtime") or {}

    permitted_outcomes = config_permitted_outcomes(config)
    recommended_outcome = str(decision.get("recommended_outcome") or "")

    regression_checks = {
        "ranking_evaluation_integrity_passed": (
            len(evaluation_failed) == 0
        ),
        "ranking_evaluation_freshness_passed": (
            len(freshness_failed) == 0
        ),
        "recommended_outcome_is_permitted": (
            recommended_outcome in permitted_outcomes
        ),
        "public_behavior_change_disabled": (
            not bool(decision.get("automatic_public_change_allowed"))
            and not bool(
                (config.get("metadata") or {}).get(
                    "public_behavior_change"
                )
            )
            and not bool(
                (config.get("decision_policy") or {}).get(
                    "change_public_default_during_evaluation"
                )
            )
        ),
        "evidence_has_nonzero_runs": safe_int(
            summary.get("runs_count")
        )
        > 0,
        "evidence_has_no_runtime_errors": safe_int(
            summary.get("error_count"),
            -1,
        )
        == 0,
        "evidence_has_no_determinism_failures": safe_int(
            summary.get("determinism_failure_count"),
            -1,
        )
        == 0,
        "runtime_build_matches_manifest": (
            runtime.get("build_id")
            == retrieval_manifest.get("build_id")
        ),
    }

    regression_failed = [
        name for name, value in regression_checks.items() if not value
    ]

    required_failed = (
        [f"integrity::{name}" for name in evaluation_failed]
        + [f"freshness::{name}" for name in freshness_failed]
        + [f"regression::{name}" for name in regression_failed]
    )

    return {
        "schema_version": "ranking_evidence_regression_v1",
        "report_name": "check_ranking_evidence_regression",
        "generated_at_utc": utc_now_iso(),
        "strict": bool(strict),
        "inputs": {
            "config_path": normalize_path(config_path),
            "report_path": normalize_path(report_path),
            "retrieval_manifest_path": normalize_path(
                retrieval_manifest_path
            ),
        },
        "extracted_values": {
            "evaluation_build_id": runtime.get("build_id"),
            "manifest_build_id": retrieval_manifest.get("build_id"),
            "evaluation_corpus_doc_count": runtime.get(
                "corpus_doc_count"
            ),
            "manifest_corpus_doc_count": retrieval_manifest.get(
                "corpus_doc_count"
            ),
            "evaluation_embedding_model_name": runtime.get(
                "embedding_model_name"
            ),
            "manifest_embedding_model_name": retrieval_manifest.get(
                "embedding_model_name"
            ),
            "retrieval_corpus_fingerprint": retrieval_manifest.get(
                "corpus_fingerprint"
            ),
            "runs_count": summary.get("runs_count"),
            "error_count": summary.get("error_count"),
            "determinism_failure_count": summary.get(
                "determinism_failure_count"
            ),
            "candidate_pool_sensitivity_rows_count": summary.get(
                "candidate_pool_sensitivity_rows_count"
            ),
            "recommended_outcome": recommended_outcome,
            "best_ranked_profile": decision.get("best_ranked_profile"),
            "unranked_quality_composite": decision.get(
                "unranked_quality_composite"
            ),
            "current_quality_composite": decision.get(
                "current_quality_composite"
            ),
            "current_relevant_removed_from_top_k_count": decision.get(
                "current_relevant_removed_from_top_k_count"
            ),
        },
        "checks": {
            "regression": regression_checks,
            "integrity": evaluation_checks,
            "freshness": freshness_checks,
        },
        "diagnostics": {
            "integrity": evaluation_diagnostics,
            "freshness": freshness_report.get("diagnostics") or {},
        },
        "required_failed_count": len(required_failed),
        "required_failed_checks": required_failed,
        "ok": len(required_failed) == 0,
    }


def build_markdown(report: dict[str, Any]) -> str:
    extracted = report.get("extracted_values") or {}
    checks = report.get("checks") or {}

    lines: list[str] = []
    lines.append("# Ranking evidence regression check")
    lines.append("")
    lines.append(f"- Generated at: `{report.get('generated_at_utc')}`")
    lines.append(f"- Strict: `{report.get('strict')}`")
    lines.append(f"- OK: **{report.get('ok')}**")
    lines.append(
        f"- Required failed count: "
        f"`{report.get('required_failed_count')}`"
    )
    lines.append("")

    lines.append("## Evidence identity")
    lines.append("")
    for key in (
        "evaluation_build_id",
        "manifest_build_id",
        "evaluation_corpus_doc_count",
        "manifest_corpus_doc_count",
        "evaluation_embedding_model_name",
        "manifest_embedding_model_name",
        "retrieval_corpus_fingerprint",
    ):
        lines.append(f"- {key}: `{extracted.get(key)}`")
    lines.append("")

    lines.append("## Evaluation outcome")
    lines.append("")
    for key in (
        "runs_count",
        "error_count",
        "determinism_failure_count",
        "candidate_pool_sensitivity_rows_count",
        "recommended_outcome",
        "best_ranked_profile",
        "unranked_quality_composite",
        "current_quality_composite",
        "current_relevant_removed_from_top_k_count",
    ):
        lines.append(f"- {key}: `{extracted.get(key)}`")
    lines.append("")

    lines.append("## Regression checks")
    lines.append("")
    for name, value in (checks.get("regression") or {}).items():
        lines.append(f"- {name}: `{value}`")
    lines.append("")

    if report.get("required_failed_checks"):
        lines.append("## Required failures")
        lines.append("")
        for name in report.get("required_failed_checks") or []:
            lines.append(f"- `{name}`")
        lines.append("")

    lines.append("## Semantics")
    lines.append("")
    lines.append(
        "This wrapper is the lightweight milestone gate for accepted ranking "
        "evidence. It does not rerun the heavy evaluator. It verifies the "
        "existing evidence report, checks that it belongs to the current "
        "retrieval build, and confirms that the accepted decision is explicit "
        "and non-mutating for public search behavior."
    )
    lines.append("")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the lightweight regression gate for accepted ranking "
            "evidence: strict integrity + retrieval-build freshness."
        )
    )
    parser.add_argument(
        "--config-path",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=DEFAULT_REPORT_PATH,
    )
    parser.add_argument(
        "--retrieval-manifest-path",
        type=Path,
        default=DEFAULT_RETRIEVAL_MANIFEST_PATH,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )
    parser.add_argument(
        "--non-strict",
        action="store_true",
        help=(
            "Use only base integrity requirements. Default is strict because "
            "this command is intended as a milestone regression gate."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_ts = utc_now_ts()

    config = load_yaml_object(args.config_path)
    evaluation_report = load_json_object(args.report_path)
    retrieval_manifest = load_json_object(args.retrieval_manifest_path)

    report = build_ranking_evidence_regression_report(
        config=config,
        evaluation_report=evaluation_report,
        retrieval_manifest=retrieval_manifest,
        config_path=args.config_path,
        report_path=args.report_path,
        retrieval_manifest_path=args.retrieval_manifest_path,
        strict=not args.non_strict,
    )

    output_dir = args.output_dir
    latest_json = output_dir / "ranking_evidence_regression_latest.json"
    latest_md = output_dir / "ranking_evidence_regression_latest.md"
    history_json = (
        output_dir
        / "history"
        / f"ranking_evidence_regression_{run_ts}.json"
    )
    history_md = (
        output_dir
        / "history"
        / f"ranking_evidence_regression_{run_ts}.md"
    )

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(history_json, report)
    dump_text(history_md, build_markdown(report))

    extracted = report.get("extracted_values") or {}

    print(f"[OK] strict={report.get('strict')}")
    print(
        "[OK] evaluation_build_id="
        f"{extracted.get('evaluation_build_id')}"
    )
    print(
        "[OK] manifest_build_id="
        f"{extracted.get('manifest_build_id')}"
    )
    print(
        "[OK] recommended_outcome="
        f"{extracted.get('recommended_outcome')}"
    )
    print(f"[OK] required_failed_count={report['required_failed_count']}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {history_json}")
    print(f"[OK] history Markdown: {history_md}")

    if not report["ok"]:
        print("[FAIL] required_failed_checks:")
        for name in report["required_failed_checks"]:
            print(f"  - {name}")
        sys.exit(1)


if __name__ == "__main__":
    main()
