from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.contracts.scientific_entity_fresh_heldout_frozen_policy import (
    ScientificEntityFreshHeldoutFrozenPolicyError,
)
from radar_core.entities.scientific_entity_fresh_heldout_frozen_policy import (
    DEFAULT_CANONICAL,
    DEFAULT_CONFIG,
    PROJECT_ROOT,
    REPORT_NAME,
    FreshHeldoutPolicyBuildError,
    plan_or_execute_frozen_policy,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan or execute the frozen v0.2c policy on the already-materialized fresh-heldout raw predictions."
    )
    parser.add_argument("--sample-dir", type=Path, required=True)
    parser.add_argument("--reference-dir", type=Path, required=True)
    parser.add_argument("--development-package-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = plan_or_execute_frozen_policy(
            project_root=PROJECT_ROOT,
            config_path=args.config,
            sample_dir=args.sample_dir,
            reference_dir=args.reference_dir,
            development_package_dir=args.development_package_dir,
            canonical_path=args.canonical,
            execute=args.execute,
        )
    except (FileNotFoundError, FileExistsError, OSError, ValueError, FreshHeldoutPolicyBuildError, ScientificEntityFreshHeldoutFrozenPolicyError) as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 2

    for key in (
        "report", "mode", "phase_complete", "candidate_id", "sample_id", "review_id",
        "parent_build_id", "parent_raw_mention_count", "parent_raw_extractor_fingerprint",
        "reference_mention_count", "raw_inference_validation_required_failed_count",
        "fresh_policy_config_sha256", "development_policy_config_sha256", "calibration_id", "selected_trial_id",
        "title_threshold", "abstract_threshold", "entity_type_overrides",
        "selected_prediction_count", "rejected_prediction_count", "build_id",
        "policy_already_applied", "plan_runs_model_inference", "new_model_inference_executed",
        "threshold_tuning_executed", "reference_comparison_executed", "evaluation_executed",
        "acceptance_decision_made", "canonical_truth_mutated", "production_extractor_selected",
        "full_corpus_build_authorized", "output_dir", "next_slice",
    ):
        print(f"[OK] {key}={report.get(key)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
