from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from radar_core.entities.scientific_entity_semantic_typer_h2_frozen_policy import (  # noqa: E402
    plan_or_execute_h2_frozen_policy,
)


DEFAULT_CONFIG = ROOT / "configs" / "scientific_entity_semantic_typer_h2_frozen_policy_v0.3.yaml"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Freeze Scientific Entity Semantic Typer v0.3 H2 selective override policy.")
    parser.add_argument("--revision-analysis-dir", type=Path, required=True)
    parser.add_argument("--evaluation-dir", type=Path, required=True)
    parser.add_argument("--prediction-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--freeze-id", type=str)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)

    report = plan_or_execute_h2_frozen_policy(
        project_root=ROOT,
        config_path=args.config,
        revision_analysis_dir=args.revision_analysis_dir,
        evaluation_dir=args.evaluation_dir,
        prediction_dir=args.prediction_dir,
        freeze_id=args.freeze_id,
        output_root=args.output_root,
        execute=args.execute,
    )
    ordered = (
        "report",
        "mode",
        "phase_complete",
        "freeze_id",
        "candidate_id",
        "revision_analysis_id",
        "parent_evaluation_id",
        "parent_prediction_id",
        "semantic_typer_candidate_id",
        "h2_candidate_fingerprint",
        "margin_threshold",
        "policy_frozen",
        "development_reproduction_executed",
        "development_override_count",
        "development_net_corrected_cases",
        "development_regression_rate",
        "development_same_span_accuracy_delta",
        "new_model_inference_executed",
        "model_inference_threshold_tuning_executed",
        "policy_margin_threshold_calibration_executed",
        "independent_acceptance_executed",
        "canonical_truth_mutated",
        "production_extractor_selected",
        "full_corpus_build_authorized",
        "output_dir",
        "next_slice",
    )
    for key in ordered:
        if key in report:
            print(f"[OK] {key}={report[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
