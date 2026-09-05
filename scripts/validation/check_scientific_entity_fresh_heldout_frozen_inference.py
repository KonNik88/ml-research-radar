from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.contracts.scientific_entity_fresh_heldout_frozen_inference import (
    ScientificEntityFreshHeldoutFrozenInferenceError,
)
from radar_core.entities.scientific_entity_fresh_heldout_frozen_inference import (
    DEFAULT_CANONICAL,
    DEFAULT_CONFIG,
    PROJECT_ROOT,
    REPORT_NAME,
    validate_frozen_inference,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the one-shot frozen v0.2c raw inference and its fresh-heldout/reference lineage."
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
    try:
        checks, summary = validate_frozen_inference(
            project_root=PROJECT_ROOT,
            config_path=args.config,
            sample_dir=args.sample_dir,
            reference_dir=args.reference_dir,
            development_package_dir=args.development_package_dir,
            canonical_path=args.canonical,
            model_cache_dir=args.model_cache_dir,
        )
    except (FileNotFoundError, OSError, ValueError, ScientificEntityFreshHeldoutFrozenInferenceError) as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 1 if args.strict else 0

    failed = [(name, detail) for name, ok, detail in checks if not ok]
    for key in (
        "report", "candidate_id", "sample_id", "review_id", "build_id",
        "input_document_count", "raw_mention_count", "reference_mention_count",
        "reference_validation_required_failed_count", "raw_build_validation_required_failed_count",
        "model_inference_executed", "policy_applied", "evaluation_executed",
        "acceptance_decision_made", "canonical_truth_mutated", "production_extractor_selected",
        "full_corpus_build_authorized", "total_checks", "required_failed_count", "next_slice",
    ):
        print(f"[OK] {key}={summary.get(key)}")
    if failed:
        for name, detail in failed:
            print(f"[FAILED] {name}: {detail}")
        return 1 if args.strict else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
