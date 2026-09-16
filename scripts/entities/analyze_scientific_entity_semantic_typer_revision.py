from __future__ import annotations

import argparse
from pathlib import Path

from radar_core.entities.scientific_entity_semantic_typer_revision_analysis import (
    plan_or_execute_semantic_typer_revision_analysis,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "scientific_entity_semantic_typer_revision_analysis_v0.3.yaml"


def _print_report(report: dict) -> None:
    preferred = (
        "report", "mode", "phase_complete", "analysis_id", "parent_evaluation_id",
        "parent_candidate_id", "parent_decision", "case_count", "primary_metric_eligible_count",
        "revision_metrics_exposed_in_plan", "policy_selected", "selected_threshold",
        "selected_plateau_thresholds", "selected_net_corrected_cases", "selected_regression_rate",
        "selected_same_span_accuracy_delta", "new_model_inference_executed",
        "model_inference_threshold_tuning_executed", "policy_margin_threshold_calibration_executed",
        "canonical_truth_mutated", "production_extractor_selected", "full_corpus_build_authorized",
        "output_dir", "next_slice",
    )
    for key in preferred:
        if key in report:
            print(f"[OK] {key}={report[key]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze rejected Semantic Typer H1 and calibrate one bounded H2 selective-override policy.")
    parser.add_argument("--evaluation-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--analysis-id")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    report = plan_or_execute_semantic_typer_revision_analysis(
        project_root=ROOT,
        config_path=args.config,
        evaluation_dir=args.evaluation_dir,
        analysis_id=args.analysis_id,
        output_root=args.output_root,
        execute=args.execute,
    )
    _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
