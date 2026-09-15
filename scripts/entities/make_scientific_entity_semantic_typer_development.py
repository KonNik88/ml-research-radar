from __future__ import annotations

import argparse
from pathlib import Path

from radar_core.entities.scientific_entity_semantic_typer_development import (
    prepare_semantic_typer_development,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "scientific_entity_semantic_typer_candidate_v0.3.yaml"


def _print_report(report: dict) -> None:
    preferred = (
        "report",
        "mode",
        "phase_complete",
        "package_id",
        "evaluation_id",
        "root_cause_review_id",
        "case_count",
        "baseline_correct_same_span_count",
        "baseline_wrong_same_span_count",
        "primary_metric_eligible_count",
        "primary_metric_excluded_count",
        "model_to_method_count",
        "method_to_task_count",
        "model_inference_executed",
        "threshold_tuning_executed",
        "span_matching_recomputed",
        "canonical_truth_mutated",
        "production_extractor_selected",
        "full_corpus_build_authorized",
        "output_dir",
        "next_slice",
    )
    for key in preferred:
        if key in report:
            print(f"[OK] {key}={report[key]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare Scientific Entity Semantic Typer v0.3 development evidence."
    )
    parser.add_argument("--evaluation-dir", type=Path, required=True)
    parser.add_argument("--review-dir", type=Path, required=True)
    parser.add_argument("--diagnostics-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--package-id")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)

    report = prepare_semantic_typer_development(
        project_root=ROOT,
        config_path=args.config,
        evaluation_dir=args.evaluation_dir,
        review_dir=args.review_dir,
        diagnostics_dir=args.diagnostics_dir,
        package_id=args.package_id,
        output_root=args.output_root,
        execute=args.execute,
    )
    _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
