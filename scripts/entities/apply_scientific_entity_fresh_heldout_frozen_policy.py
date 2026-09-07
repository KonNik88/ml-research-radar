from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.entities.scientific_entity_fresh_heldout_frozen_policy import (
    DEFAULT_CANONICAL,
    DEFAULT_CONFIG,
    PROJECT_ROOT,
    plan_or_execute_frozen_policy,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan or execute the frozen v0.2c policy exactly once on fresh-heldout raw predictions."
    )
    parser.add_argument("--sample-dir", type=Path, required=True)
    parser.add_argument("--reference-dir", type=Path, required=True)
    parser.add_argument("--development-package-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--model-cache-dir", type=Path, default=None)
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = plan_or_execute_frozen_policy(
        project_root=PROJECT_ROOT,
        config_path=args.config,
        sample_dir=args.sample_dir,
        reference_dir=args.reference_dir,
        development_package_dir=args.development_package_dir,
        canonical_path=args.canonical,
        model_cache_dir=args.model_cache_dir,
        execute=args.execute,
    )
    for key in (
        "report", "mode", "phase_complete", "candidate_id", "sample_id", "review_id",
        "raw_build_id", "raw_mention_count", "raw_extractor_fingerprint",
        "raw_validation_required_failed_count", "frozen_policy_config_sha256",
        "calibration_id", "selected_trial_id", "title_threshold", "abstract_threshold",
        "entity_type_overrides", "build_id", "one_shot_already_executed",
        "plan_runs_policy_filtering", "model_inference_executed", "policy_applied",
        "selected_prediction_count", "rejected_prediction_count", "policy_extractor_fingerprint",
        "threshold_tuning_executed", "reference_labels_used_for_filtering",
        "evaluation_executed", "acceptance_decision_made", "canonical_truth_mutated",
        "production_extractor_selected", "full_corpus_build_authorized", "output_dir", "next_slice",
    ):
        if key in report:
            print(f"[OK] {key}={report.get(key)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
