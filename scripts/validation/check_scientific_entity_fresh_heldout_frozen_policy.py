from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.entities.scientific_entity_fresh_heldout_frozen_policy import (
    DEFAULT_CANONICAL,
    DEFAULT_CONFIG,
    PROJECT_ROOT,
    validate_frozen_policy_build,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the frozen v0.2c policy materialization on the fresh held-out."
    )
    parser.add_argument("--sample-dir", type=Path, required=True)
    parser.add_argument("--reference-dir", type=Path, required=True)
    parser.add_argument("--development-package-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--model-cache-dir", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    checks, summary = validate_frozen_policy_build(
        project_root=PROJECT_ROOT,
        config_path=args.config,
        sample_dir=args.sample_dir,
        reference_dir=args.reference_dir,
        development_package_dir=args.development_package_dir,
        canonical_path=args.canonical,
        model_cache_dir=args.model_cache_dir,
    )
    for key in (
        "report", "candidate_id", "sample_id", "review_id", "raw_build_id",
        "raw_mention_count", "build_id", "selected_prediction_count",
        "rejected_prediction_count", "title_threshold", "abstract_threshold",
        "model_inference_executed_by_policy", "policy_applied", "threshold_tuning_executed",
        "reference_labels_used_for_filtering", "evaluation_executed",
        "acceptance_decision_made", "canonical_truth_mutated",
        "production_extractor_selected", "full_corpus_build_authorized",
        "total_checks", "required_failed_count", "next_slice",
    ):
        print(f"[OK] {key}={summary.get(key)}")
    if args.strict and summary["required_failed_count"]:
        for name, ok, detail in checks:
            if not ok:
                print(f"[FAILED] {name}: {detail}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
