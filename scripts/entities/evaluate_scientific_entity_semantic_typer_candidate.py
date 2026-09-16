from __future__ import annotations

import argparse
from pathlib import Path

from radar_core.entities.scientific_entity_semantic_typer_evaluation import (
    plan_or_execute_semantic_typer_development_evaluation,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "scientific_entity_semantic_typer_candidate_v0.3.yaml"


def _print_report(report: dict) -> None:
    preferred = (
        "report", "mode", "phase_complete", "evaluation_id", "prediction_id", "package_id",
        "case_count", "primary_metric_eligible_count", "quality_metrics_exposed_in_plan",
        "development_decision_made", "decision", "all_gates_passed", "typer_coverage",
        "same_span_accuracy_delta", "macro_f1_delta", "net_corrected_cases", "regression_rate",
        "model_to_method_reduction_fraction", "threshold_tuning_executed", "canonical_truth_mutated",
        "production_extractor_selected", "full_corpus_build_authorized", "output_dir", "next_slice",
    )
    for key in preferred:
        if key in report:
            print(f"[OK] {key}={report[key]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate Scientific Entity Semantic Typer v0.3 against frozen baseline.")
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--prediction-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--evaluation-id")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    report = plan_or_execute_semantic_typer_development_evaluation(
        project_root=ROOT,
        config_path=args.config,
        package_dir=args.package_dir,
        prediction_dir=args.prediction_dir,
        evaluation_id=args.evaluation_id,
        output_root=args.output_root,
        execute=args.execute,
    )
    _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
