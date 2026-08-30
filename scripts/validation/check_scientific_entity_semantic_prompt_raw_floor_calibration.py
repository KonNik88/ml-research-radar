from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.entities.scientific_entity_semantic_prompt_raw_floor_calibration import (
    DEFAULT_CONFIG_PATH,
    validate_semantic_prompt_raw_floor_calibration,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate one immutable v0.2c raw-floor title-threshold calibration."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--calibration-dir", type=Path, required=True)
    parser.add_argument("--development-package-dir", type=Path, required=True)
    parser.add_argument("--baseline-raw-build-dir", type=Path, required=True)
    parser.add_argument("--raw-build-dir", type=Path, required=True)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--no-write-reports", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = validate_semantic_prompt_raw_floor_calibration(
        project_root=PROJECT_ROOT,
        config_path=args.config,
        calibration_dir=args.calibration_dir,
        development_package_dir=args.development_package_dir,
        baseline_raw_build_dir=args.baseline_raw_build_dir,
        raw_build_dir=args.raw_build_dir,
    )
    for key in (
        "report",
        "calibration_id",
        "trial_count",
        "eligible_trial_count",
        "baseline_raw_evidence_preserved",
        "baseline_raw_missing_count",
        "baseline_raw_score_changed_count",
        "new_at_or_above_baseline_floor_count",
        "new_selected_by_v02b_control_count",
        "v02b_control_metrics_reproduced",
        "v02b_control_selected_prediction_delta",
        "raw_prediction_count",
        "raw_prediction_delta_vs_v02a",
        "selected_title_threshold",
        "selected_abstract_threshold",
        "candidate_promising_for_future_freeze",
        "selected_title_at_candidate_raw_floor",
        "total_checks",
        "required_failed_count",
        "model_inference_executed_during_calibration",
        "fresh_heldout_consumed",
        "canonical_truth_mutated",
        "full_corpus_build_authorized",
        "next_slice",
    ):
        print(f"[OK] {key}={report[key]}")
    if args.strict and report["required_failed_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
