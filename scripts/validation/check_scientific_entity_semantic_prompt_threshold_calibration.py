from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.entities.scientific_entity_semantic_prompt_threshold_calibration import (
    DEFAULT_CONFIG_PATH,
    validate_semantic_prompt_threshold_calibration,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate one immutable v0.2b semantic-prompt threshold calibration artifact."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--calibration-dir", type=Path, required=True)
    parser.add_argument("--development-package-dir", type=Path, required=True)
    parser.add_argument("--raw-build-dir", type=Path, required=True)
    parser.add_argument("--v02a-comparison-dir", type=Path, required=True)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--no-write-reports", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = validate_semantic_prompt_threshold_calibration(
        project_root=PROJECT_ROOT,
        config_path=args.config,
        calibration_dir=args.calibration_dir,
        development_package_dir=args.development_package_dir,
        raw_build_dir=args.raw_build_dir,
        v02a_comparison_dir=args.v02a_comparison_dir,
    )
    print(f"[OK] report={report['report']}")
    print(f"[OK] calibration_id={report['calibration_id']}")
    print(f"[OK] trial_count={report['trial_count']}")
    print(f"[OK] eligible_trial_count={report['eligible_trial_count']}")
    print(f"[OK] selected_title_threshold={report['selected_title_threshold']}")
    print(f"[OK] selected_abstract_threshold={report['selected_abstract_threshold']}")
    print(f"[OK] candidate_promising_for_future_freeze={report['candidate_promising_for_future_freeze']}")
    print(f"[OK] total_checks={report['total_checks']}")
    print(f"[OK] required_failed_count={report['required_failed_count']}")
    print(f"[OK] model_inference_executed={report['model_inference_executed']}")
    print(f"[OK] fresh_heldout_consumed={report['fresh_heldout_consumed']}")
    print(f"[OK] canonical_truth_mutated={report['canonical_truth_mutated']}")
    print(f"[OK] full_corpus_build_authorized={report['full_corpus_build_authorized']}")
    print(f"[OK] next_slice={report['next_slice']}")
    if args.strict and report["required_failed_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
