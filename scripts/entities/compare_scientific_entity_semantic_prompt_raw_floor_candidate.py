from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.entities.scientific_entity_semantic_prompt_raw_floor_comparison import (
    DEFAULT_CONFIG_PATH,
    build_raw_floor_comparison,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Plan or execute the frozen v0.2c scientific-entity raw-floor "
            "controlled development comparison."
        )
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--development-package-dir", type=Path, required=True)
    parser.add_argument("--policy-build-dir", type=Path, required=True)
    parser.add_argument("--parent-raw-build-dir", type=Path, required=True)
    parser.add_argument("--calibration-dir", type=Path, required=True)
    parser.add_argument("--v02a-comparison-dir", type=Path, required=True)
    parser.add_argument("--v02b-calibration-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--comparison-id")
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_raw_floor_comparison(
        project_root=PROJECT_ROOT,
        development_package_dir=args.development_package_dir,
        policy_build_dir=args.policy_build_dir,
        parent_raw_build_dir=args.parent_raw_build_dir,
        calibration_dir=args.calibration_dir,
        v02a_comparison_dir=args.v02a_comparison_dir,
        v02b_calibration_dir=args.v02b_calibration_dir,
        config_path=args.config,
        output_root=args.output_root,
        comparison_id=args.comparison_id,
        execute=args.execute,
    )
    for key in (
        "report",
        "mode",
        "phase_complete",
        "comparison_id",
        "development_document_count",
        "reference_mention_count",
        "candidate_prediction_count",
        "old_dev_candidate_exact_f1",
        "consumed_heldout_candidate_exact_f1",
        "consumed_heldout_candidate_relaxed_f1",
        "combined_candidate_exact_f1",
        "consumed_heldout_model_to_method_count",
        "consumed_heldout_method_to_task_count",
        "consumed_heldout_total_type_mismatch_count",
        "consumed_heldout_method_semantic_sink_count",
        "calibration_reproduction_passed",
        "all_hard_guardrails_passed",
        "candidate_ready_for_development_freeze",
        "model_inference_executed",
        "threshold_tuning_executed",
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
