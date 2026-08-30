from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.entities.scientific_entity_semantic_prompt_raw_floor_comparison import (
    DEFAULT_CONFIG_PATH,
    validate_raw_floor_comparison,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate one immutable v0.2c raw-floor controlled development comparison."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--comparison-dir", type=Path, required=True)
    parser.add_argument("--development-package-dir", type=Path, required=True)
    parser.add_argument("--policy-build-dir", type=Path, required=True)
    parser.add_argument("--parent-raw-build-dir", type=Path, required=True)
    parser.add_argument("--calibration-dir", type=Path, required=True)
    parser.add_argument("--v02a-comparison-dir", type=Path, required=True)
    parser.add_argument("--v02b-calibration-dir", type=Path, required=True)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--no-write-reports", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = validate_raw_floor_comparison(
        project_root=PROJECT_ROOT,
        comparison_dir=args.comparison_dir,
        development_package_dir=args.development_package_dir,
        policy_build_dir=args.policy_build_dir,
        parent_raw_build_dir=args.parent_raw_build_dir,
        calibration_dir=args.calibration_dir,
        v02a_comparison_dir=args.v02a_comparison_dir,
        v02b_calibration_dir=args.v02b_calibration_dir,
        config_path=args.config,
    )
    for key in (
        "report",
        "comparison_id",
        "development_document_count",
        "reference_mention_count",
        "candidate_prediction_count",
        "calibration_reproduction_passed",
        "all_hard_guardrails_passed",
        "candidate_ready_for_development_freeze",
        "total_checks",
        "required_failed_count",
        "model_inference_executed",
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
