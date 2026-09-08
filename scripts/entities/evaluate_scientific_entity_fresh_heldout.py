from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.contracts.scientific_entity_fresh_heldout_evaluation import (
    ScientificEntityFreshHeldoutEvaluationError,
)
from radar_core.entities.scientific_entity_fresh_heldout_evaluation import (
    REPORT_NAME,
    FreshHeldoutEvaluationBuildError,
    plan_or_execute_fresh_heldout_evaluation,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "scientific_entity_fresh_heldout_evaluation_v0.2.yaml"
DEFAULT_CANONICAL = ROOT / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plan or execute the one-shot Scientific Entity fresh v0.2 independent evaluation."
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
        report = plan_or_execute_fresh_heldout_evaluation(
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
        ScientificEntityFreshHeldoutEvaluationError,
        FreshHeldoutEvaluationBuildError,
    ) as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 1

    print(f"[OK] report={report['report']}")
    for key in (
        "mode", "phase_complete", "candidate_id", "sample_id", "review_id",
        "document_count", "reference_mention_count", "policy_build_id",
        "prediction_mention_count", "policy_extractor_fingerprint",
        "reference_validation_required_failed_count", "policy_validation_required_failed_count",
        "gate_config_sha256", "evaluation_config_sha256", "evaluation_id",
        "one_shot_already_executed", "plan_runs_evaluation",
        "model_inference_executed", "threshold_tuning_executed",
        "reference_labels_used_for_evaluation", "reference_labels_used_for_filtering",
        "evaluation_executed", "acceptance_decision_made",
        "canonical_truth_mutated", "production_extractor_selected",
        "full_corpus_build_authorized",
    ):
        print(f"[OK] {key}={report[key]}")
    for key in (
        "exact_precision", "exact_recall", "exact_f1",
        "relaxed_precision", "relaxed_recall", "relaxed_f1",
        "model_to_method_count", "method_to_task_count", "total_type_mismatch_count",
        "method_semantic_sink_count", "maximum_predicted_type_mismatch_sink_type",
        "maximum_any_predicted_type_mismatch_sink_count",
        "base_evaluation_validation_total_checks",
        "base_evaluation_validation_required_failed_count",
    ):
        if key in report:
            print(f"[OK] {key}={report[key]}")
    print(f"[OK] output_dir={report['output_dir']}")
    print(f"[OK] next_slice={report['next_slice']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
