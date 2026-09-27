from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.contracts.scientific_entity_semantic_typer_h2_independent_evaluation import (
    ScientificEntityH2IndependentEvaluationError,
)
from radar_core.entities.scientific_entity_semantic_typer_h2_independent_evaluation import (
    DEFAULT_CANONICAL,
    DEFAULT_CONFIG,
    PROJECT_ROOT,
    REPORT_NAME,
    plan_or_execute_h2_independent_evaluation,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Plan or execute one-shot H2 v0.3 independent comparative evaluation."
        )
    )
    parser.add_argument("--inference-dir", type=Path, required=True)
    parser.add_argument("--sample-dir", type=Path, required=True)
    parser.add_argument("--reference-dir", type=Path, required=True)
    parser.add_argument("--development-package-dir", type=Path, required=True)
    parser.add_argument("--previous-heldout-sample-dir", type=Path, required=True)
    parser.add_argument("--frozen-candidate-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = plan_or_execute_h2_independent_evaluation(
            project_root=PROJECT_ROOT,
            config_path=args.config,
            sample_dir=args.sample_dir,
            reference_dir=args.reference_dir,
            development_package_dir=args.development_package_dir,
            previous_heldout_sample_dir=args.previous_heldout_sample_dir,
            frozen_candidate_dir=args.frozen_candidate_dir,
            canonical_path=args.canonical,
            inference_dir=args.inference_dir,
            execute=args.execute,
        )
    except (
        FileNotFoundError,
        OSError,
        ValueError,
        ScientificEntityH2IndependentEvaluationError,
    ) as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 1

    print(f"[OK] report={report['report']}")
    preferred = (
        "mode",
        "phase_complete",
        "candidate_id",
        "candidate_fingerprint_sha256",
        "sample_id",
        "review_id",
        "inference_id",
        "document_count",
        "reference_mention_count",
        "baseline_prediction_count",
        "h2_prediction_count",
        "inference_validation_required_failed_count",
        "gate_config_sha256",
        "base_evaluator_config_sha256",
        "evaluation_id",
        "one_shot_already_executed",
        "plan_runs_evaluation",
        "plan_exposes_quality_metrics",
        "model_inference_executed_in_this_slice",
        "threshold_tuning_executed",
        "policy_revision_executed",
        "reference_labels_used_for_evaluation",
        "reference_labels_used_for_filtering",
        "evaluation_executed",
        "acceptance_decision_made",
        "canonical_truth_mutated",
        "production_extractor_selected",
        "full_corpus_build_authorized",
    )
    for key in preferred:
        if key in report:
            print(f"[OK] {key}={report[key]}")

    quality = (
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
    )
    for key in quality:
        if key in report:
            print(f"[OK] {key}={report[key]}")

    print(f"[OK] output_dir={report['output_dir']}")
    print(f"[OK] next_slice={report['next_slice']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
