from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.entities.scientific_entity_semantic_typer_h2_full_corpus_candidate import (
    DEFAULT_CANONICAL,
    DEFAULT_CONFIG,
    PROJECT_ROOT,
    REPORT_NAME,
    plan_or_execute_h2_full_corpus_candidate,
)


def _print_report(report: dict) -> None:
    preferred = (
        "report", "mode", "phase_complete", "authorization_id",
        "authorization_validation_required_failed_count", "authorization_validation_total_checks",
        "candidate_id", "candidate_fingerprint_sha256", "canonical_sha256",
        "canonical_document_count", "canonical_snapshot_matches_authorization",
        "authorization_already_consumed", "consumed_by_build_id", "plan_runs_model_inference",
        "plan_writes_candidate", "candidate_build_executed", "full_corpus_model_inference_executed",
        "human_reference_mentions_read", "threshold_tuning_executed", "policy_revision_executed",
        "canonical_truth_mutated", "production_latest_promotion_authorized", "build_id",
        "upstream_raw_mention_count", "baseline_prediction_count", "baseline_method_count",
        "semantic_typer_scored_count", "semantic_typer_fallback_count",
        "typer_coverage_over_method_cases", "h2_override_count", "final_mention_count",
        "materialization_fingerprint_sha256", "duration_seconds", "output_dir", "next_slice",
    )
    for key in preferred:
        if key in report:
            print(f"[OK] {key}={report[key]}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build one authorized timestamped H2 v0.3 full-corpus candidate materialization")
    parser.add_argument("--authorization-dir", required=True, type=Path)
    parser.add_argument("--decision-dir", required=True, type=Path)
    parser.add_argument("--evaluation-dir", required=True, type=Path)
    parser.add_argument("--inference-dir", required=True, type=Path)
    parser.add_argument("--sample-dir", required=True, type=Path)
    parser.add_argument("--reference-dir", required=True, type=Path)
    parser.add_argument("--development-package-dir", required=True, type=Path)
    parser.add_argument("--previous-heldout-sample-dir", required=True, type=Path)
    parser.add_argument("--frozen-candidate-dir", required=True, type=Path)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--build-id")
    parser.add_argument("--allow-model-download", action="store_true")
    parser.add_argument("--model-cache-dir", type=Path)
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = plan_or_execute_h2_full_corpus_candidate(
            project_root=PROJECT_ROOT,
            config_path=args.config,
            authorization_dir=args.authorization_dir,
            decision_dir=args.decision_dir,
            evaluation_dir=args.evaluation_dir,
            inference_dir=args.inference_dir,
            sample_dir=args.sample_dir,
            reference_dir=args.reference_dir,
            development_package_dir=args.development_package_dir,
            previous_heldout_sample_dir=args.previous_heldout_sample_dir,
            frozen_candidate_dir=args.frozen_candidate_dir,
            canonical_path=args.canonical,
            output_root=args.output_root,
            build_id=args.build_id,
            execute=args.execute,
            allow_model_download=args.allow_model_download,
            model_cache_dir=args.model_cache_dir,
        )
    except Exception as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 2
    _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
