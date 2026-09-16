from __future__ import annotations

import argparse
from pathlib import Path

from radar_core.entities.scientific_entity_semantic_typer_candidate_inference import (
    plan_or_execute_semantic_typer_candidate_inference,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "scientific_entity_semantic_typer_candidate_v0.3.yaml"


def _print_report(report: dict) -> None:
    preferred = (
        "report", "mode", "phase_complete", "prediction_id", "package_id", "candidate_id",
        "case_count", "primary_metric_eligible_count", "scored_case_count", "fallback_count",
        "typer_coverage", "model_inference_executed", "threshold_tuning_executed",
        "baseline_type_used_as_model_feature", "root_cause_used_as_model_feature", "span_mutated",
        "canonical_truth_mutated", "production_extractor_selected", "full_corpus_build_authorized",
        "output_dir", "next_slice",
    )
    for key in preferred:
        if key in report:
            print(f"[OK] {key}={report[key]}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run bounded Scientific Entity Semantic Typer v0.3 candidate inference.")
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--prediction-id")
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--allow-model-download", action="store_true")
    parser.add_argument("--model-cache-dir", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    report = plan_or_execute_semantic_typer_candidate_inference(
        project_root=ROOT,
        config_path=args.config,
        package_dir=args.package_dir,
        prediction_id=args.prediction_id,
        output_root=args.output_root,
        execute=args.execute,
        allow_model_download=args.allow_model_download,
        model_cache_dir=args.model_cache_dir,
    )
    _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
