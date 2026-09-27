from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.entities.scientific_entity_semantic_typer_h2_independent_evaluation import (
    DEFAULT_CANONICAL,
    DEFAULT_CONFIG,
    PROJECT_ROOT,
    REPORT_NAME,
    validate_h2_independent_evaluation,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Strictly validate immutable H2 v0.3 independent comparative evaluation."
    )
    parser.add_argument("--evaluation-dir", type=Path, required=True)
    parser.add_argument("--inference-dir", type=Path, required=True)
    parser.add_argument("--sample-dir", type=Path, required=True)
    parser.add_argument("--reference-dir", type=Path, required=True)
    parser.add_argument("--development-package-dir", type=Path, required=True)
    parser.add_argument("--previous-heldout-sample-dir", type=Path, required=True)
    parser.add_argument("--frozen-candidate-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--strict", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        checks, summary = validate_h2_independent_evaluation(
            project_root=PROJECT_ROOT,
            config_path=args.config,
            sample_dir=args.sample_dir,
            reference_dir=args.reference_dir,
            development_package_dir=args.development_package_dir,
            previous_heldout_sample_dir=args.previous_heldout_sample_dir,
            frozen_candidate_dir=args.frozen_candidate_dir,
            canonical_path=args.canonical,
            inference_dir=args.inference_dir,
            evaluation_dir=args.evaluation_dir,
        )
    except Exception as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 2

    for name, ok, detail in checks:
        prefix = "OK" if ok else "FAILED"
        print(f"[{prefix}] check={name} detail={detail}")

    preferred = (
        "report",
        "validation_scope",
        "evaluation_id",
        "inference_id",
        "candidate_id",
        "sample_id",
        "review_id",
        "document_count",
        "reference_mention_count",
        "baseline_prediction_count",
        "h2_prediction_count",
        "same_span_pair_count",
        "typer_coverage",
        "baseline_same_span_accuracy",
        "h2_same_span_accuracy",
        "same_span_accuracy_delta",
        "baseline_macro_f1",
        "h2_macro_f1",
        "macro_f1_delta",
        "corrected_errors",
        "introduced_regressions",
        "net_corrected_cases",
        "regression_rate",
        "baseline_model_to_method_count",
        "h2_model_to_method_count",
        "model_to_method_reduction_fraction",
        "h2_exact_f1",
        "h2_relaxed_f1",
        "evaluation_executed",
        "acceptance_decision_made",
        "total_checks",
        "required_failed_count",
        "next_slice",
    )
    for key in preferred:
        if key in summary:
            print(f"[OK] {key}={summary[key]}")

    if args.strict and summary.get("required_failed_count", 1) != 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
