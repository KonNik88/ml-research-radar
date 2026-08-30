from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.entities.scientific_entity_semantic_prompt_raw_floor_calibration import (
    DEFAULT_CONFIG_PATH,
    build_semantic_prompt_raw_floor_calibration,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Plan or execute the frozen five-trial v0.2c title-threshold search "
            "over an already-materialized raw-floor 0.40 GLiNER build."
        )
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--development-package-dir", type=Path, required=True)
    parser.add_argument("--baseline-raw-build-dir", type=Path, required=True)
    parser.add_argument("--raw-build-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--calibration-id")
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_semantic_prompt_raw_floor_calibration(
        project_root=PROJECT_ROOT,
        config_path=args.config,
        development_package_dir=args.development_package_dir,
        baseline_raw_build_dir=args.baseline_raw_build_dir,
        raw_build_dir=args.raw_build_dir,
        output_root=args.output_root,
        calibration_id=args.calibration_id,
        execute=args.execute,
    )
    for key in (
        "report",
        "mode",
        "phase_complete",
        "calibration_id",
        "raw_build_id",
        "document_count",
        "reference_mention_count",
        "raw_prediction_count",
        "raw_prediction_delta_vs_v02a",
        "trial_count",
        "eligible_trial_count",
        "baseline_raw_evidence_preserved",
        "baseline_raw_missing_count",
        "baseline_raw_score_changed_count",
        "new_at_or_above_baseline_floor_count",
        "new_selected_by_v02b_control_count",
        "new_at_or_above_baseline_floor_mention_ids",
        "v02b_control_metrics_reproduced",
        "v02b_control_selected_prediction_delta",
        "selected_trial_id",
        "selected_title_threshold",
        "selected_abstract_threshold",
        "selected_combined_exact_f1",
        "selected_consumed_heldout_exact_f1",
        "selected_consumed_heldout_relaxed_f1",
        "selected_model_to_method_count",
        "selected_method_to_task_count",
        "selected_total_type_mismatch_count",
        "selected_method_semantic_sink_count",
        "all_hard_gates_passed",
        "candidate_promising_for_future_freeze",
        "selected_title_at_candidate_raw_floor",
        "raw_input_floor_may_still_be_binding",
        "model_inference_executed_during_calibration",
        "prompt_changes_executed",
        "threshold_search_executed",
        "fresh_heldout_consumed",
        "canonical_truth_mutated",
        "full_corpus_build_authorized",
        "output_dir",
        "next_slice",
    ):
        print(f"[OK] {key}={report[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
