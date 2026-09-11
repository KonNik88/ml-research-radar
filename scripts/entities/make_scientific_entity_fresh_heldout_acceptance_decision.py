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
    plan_or_execute_fresh_heldout_acceptance_decision,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "scientific_entity_fresh_heldout_acceptance_decision_v0.2.yaml"
DEFAULT_CANONICAL = ROOT / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan or execute the immutable Scientific Entity fresh v0.2c acceptance decision."
    )
    parser.add_argument("--sample-dir", type=Path, required=True)
    parser.add_argument("--reference-dir", type=Path, required=True)
    parser.add_argument("--development-package-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = plan_or_execute_fresh_heldout_acceptance_decision(
            project_root=ROOT,
            config_path=args.config,
            sample_dir=args.sample_dir,
            reference_dir=args.reference_dir,
            development_package_dir=args.development_package_dir,
            canonical_path=args.canonical,
            execute=args.execute,
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
        return 1

    print(f"[OK] report={report['report']}")
    for key in (
        "mode", "phase_complete", "candidate_id", "sample_id", "review_id",
        "policy_build_id", "policy_extractor_fingerprint", "document_count",
        "reference_mention_count", "prediction_mention_count", "evaluation_id",
        "evaluation_validation_required_failed_count", "evaluation_manifest_sha256",
        "evaluation_metrics_sha256", "evaluation_errors_sha256", "gate_config_sha256",
        "decision_id", "one_shot_already_executed", "plan_runs_decision",
        "decision_materialized", "evaluation_recomputed", "model_inference_executed",
        "policy_reapplied", "threshold_tuning_executed", "gate_changed",
        "canonical_truth_mutated", "production_extractor_selected",
        "full_corpus_build_authorized",
    ):
        print(f"[OK] {key}={report[key]}")
    for key in (
        "decision", "failed_hard_criteria", "hard_criteria_passed_count",
        "hard_criteria_count", "desirable_criteria_passed_count", "desirable_criteria_count",
    ):
        if key in report:
            print(f"[OK] {key}={report[key]}")
    print(f"[OK] output_dir={report['output_dir']}")
    print(f"[OK] next_slice={report['next_slice']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
