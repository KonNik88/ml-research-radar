from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.contracts.scientific_entity_semantic_typer_h2_independent_inference import (
    ScientificEntityH2IndependentInferenceError,
)
from radar_core.entities.scientific_entity_semantic_typer_h2_independent_inference import (
    DEFAULT_CANONICAL,
    DEFAULT_CONFIG,
    PROJECT_ROOT,
    REPORT_NAME,
    plan_or_execute_h2_independent_inference,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Plan or execute the one-shot frozen H2 v0.3 independent inference after "
            "prediction-blind human reference freeze. PLAN never runs model inference."
        )
    )
    parser.add_argument("--sample-dir", type=Path, required=True)
    parser.add_argument("--reference-dir", type=Path, required=True)
    parser.add_argument("--development-package-dir", type=Path, required=True)
    parser.add_argument("--previous-heldout-sample-dir", type=Path, required=True)
    parser.add_argument("--frozen-candidate-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--inference-id")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--model-cache-dir", type=Path, default=None)
    parser.add_argument("--allow-model-download", action="store_true")
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = plan_or_execute_h2_independent_inference(
            project_root=PROJECT_ROOT,
            config_path=args.config,
            sample_dir=args.sample_dir,
            reference_dir=args.reference_dir,
            development_package_dir=args.development_package_dir,
            previous_heldout_sample_dir=args.previous_heldout_sample_dir,
            frozen_candidate_dir=args.frozen_candidate_dir,
            canonical_path=args.canonical,
            inference_id=args.inference_id,
            output_root=args.output_root,
            model_cache_dir=args.model_cache_dir,
            allow_model_download=args.allow_model_download,
            execute=args.execute,
        )
    except (FileNotFoundError, FileExistsError, OSError, ValueError, ScientificEntityH2IndependentInferenceError) as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 2

    preferred = (
        "report", "mode", "phase_complete", "candidate_id", "candidate_fingerprint_sha256",
        "sample_id", "review_id", "reference_validation_required_failed_count",
        "reference_frozen_before_inference", "input_document_count", "inference_id",
        "one_shot_already_executed", "plan_runs_model_inference",
        "upstream_model_inference_executed", "semantic_typer_model_inference_executed",
        "frozen_h2_policy_applied", "reference_labels_used_for_case_construction",
        "reference_labels_used_as_model_features", "upstream_raw_mention_count",
        "baseline_prediction_count", "semantic_typer_case_count", "semantic_typer_scored_count",
        "semantic_typer_fallback_count", "typer_coverage", "h2_override_count",
        "threshold_tuning_executed", "policy_revision_executed", "span_mutated",
        "evaluation_executed", "acceptance_decision_made", "canonical_truth_mutated",
        "production_extractor_selected", "full_corpus_build_authorized",
        "runtime_device_name", "model_artifact_verified", "backbone_config_verified",
        "inference_duration_seconds", "peak_cuda_memory_bytes", "output_dir", "next_slice",
    )
    for key in preferred:
        if key in report:
            print(f"[OK] {key}={report[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
