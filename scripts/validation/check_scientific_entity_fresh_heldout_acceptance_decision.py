from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.contracts.scientific_entity_fresh_heldout_acceptance_decision import (
    ScientificEntityFreshHeldoutAcceptanceDecisionError,
)
from radar_core.entities.scientific_entity_fresh_heldout_acceptance_decision import (
    REPORT_NAME,
    FreshHeldoutAcceptanceDecisionBuildError,
    validate_fresh_heldout_acceptance_decision,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "scientific_entity_fresh_heldout_acceptance_decision_v0.2.yaml"
DEFAULT_CANONICAL = ROOT / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Strictly validate the immutable Scientific Entity fresh v0.2c acceptance decision."
    )
    parser.add_argument("--sample-dir", type=Path, required=True)
    parser.add_argument("--reference-dir", type=Path, required=True)
    parser.add_argument("--development-package-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--strict", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        checks, summary = validate_fresh_heldout_acceptance_decision(
            project_root=ROOT,
            config_path=args.config,
            sample_dir=args.sample_dir,
            reference_dir=args.reference_dir,
            development_package_dir=args.development_package_dir,
            canonical_path=args.canonical,
        )
    except (
        FileNotFoundError,
        OSError,
        ValueError,
        ScientificEntityFreshHeldoutAcceptanceDecisionError,
        FreshHeldoutAcceptanceDecisionBuildError,
    ) as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 1 if args.strict else 0

    failed = [(name, detail) for name, ok, detail in checks if not ok]
    print(f"[OK] report={summary['report']}")
    for key in (
        "candidate_id", "sample_id", "review_id", "evaluation_id", "decision_id",
        "decision_materialized", "decision", "failed_hard_criteria", "hard_criteria_count",
        "hard_criteria_passed_count", "desirable_criteria_count",
        "desirable_criteria_passed_count", "criterion_count", "evaluation_recomputed",
        "model_inference_executed", "policy_reapplied", "threshold_tuning_executed",
        "gate_changed", "canonical_truth_mutated", "production_extractor_selected",
        "full_corpus_build_authorized", "total_checks", "required_failed_count", "next_slice",
    ):
        print(f"[OK] {key}={summary[key]}")
    if failed:
        for name, detail in failed:
            print(f"[FAILED] {name}: {detail}")
        return 1 if args.strict else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
