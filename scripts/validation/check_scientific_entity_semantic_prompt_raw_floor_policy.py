from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.entities.scientific_entity_semantic_prompt_raw_floor_policy import (
    DEFAULT_CONFIG_PATH,
    validate_raw_floor_selected_policy_build,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate immutable v0.2c selected semantic-prompt raw-floor policy evidence.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--parent-build-dir", type=Path, required=True)
    parser.add_argument("--development-package-dir", type=Path, required=True)
    parser.add_argument("--calibration-dir", type=Path, required=True)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--no-write-reports", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = validate_raw_floor_selected_policy_build(
        build_dir=args.build_dir,
        parent_build_dir=args.parent_build_dir,
        development_package_dir=args.development_package_dir,
        calibration_dir=args.calibration_dir,
        config_path=args.config,
    )
    for key in (
        "report", "build_id", "parent_build_id", "calibration_id", "input_document_count",
        "input_prediction_count", "selected_prediction_count", "rejected_prediction_count",
        "extractor_fingerprint_changed", "calibration_hard_gates_passed",
        "calibration_candidate_promising", "model_inference_executed", "threshold_tuning_executed",
        "fresh_heldout_consumed", "canonical_truth_mutated", "full_corpus_build_authorized",
        "total_checks", "required_failed_count", "next_slice",
    ):
        print(f"[OK] {key}={report[key]}")
    if args.strict and report["required_failed_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
