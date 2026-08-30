from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.entities.scientific_entity_semantic_prompt_raw_floor_policy import (
    DEFAULT_CONFIG_PATH,
    build_raw_floor_selected_policy,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan or execute v0.2c selected semantic-prompt raw-floor policy materialization."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--parent-build-dir", type=Path, required=True)
    parser.add_argument("--development-package-dir", type=Path, required=True)
    parser.add_argument("--calibration-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--build-id")
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_raw_floor_selected_policy(
        config_path=args.config,
        parent_build_dir=args.parent_build_dir,
        development_package_dir=args.development_package_dir,
        calibration_dir=args.calibration_dir,
        output_root=args.output_root,
        build_id=args.build_id,
        execute=args.execute,
    )
    for key in (
        "report", "mode", "phase_complete", "build_id", "parent_build_id",
        "calibration_id", "selected_trial_id", "input_document_count",
        "input_prediction_count", "selected_prediction_count", "rejected_prediction_count",
        "extractor_fingerprint_changed", "title_threshold", "abstract_threshold",
        "calibration_hard_gates_passed", "calibration_candidate_promising",
        "selected_title_at_candidate_raw_floor", "model_inference_executed",
        "threshold_tuning_executed", "fresh_heldout_consumed", "canonical_truth_mutated",
        "full_corpus_build_authorized", "production_extractor_selected", "output_dir", "next_slice",
    ):
        print(f"[OK] {key}={report[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
