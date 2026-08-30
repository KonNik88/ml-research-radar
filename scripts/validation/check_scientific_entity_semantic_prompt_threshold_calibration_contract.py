from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from radar_core.contracts.scientific_entity_semantic_prompt_threshold_calibration import (
    load_semantic_prompt_threshold_calibration_config,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = (
    PROJECT_ROOT
    / "configs"
    / "scientific_entity_semantic_prompt_threshold_calibration_v0.2b.yaml"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate the frozen v0.2b threshold-calibration design contract."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--strict", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_semantic_prompt_threshold_calibration_config(args.config.resolve())
    checks = {
        "trial_count": config.search.expected_trial_count == 35,
        "title_grid_count": len(config.search.title_thresholds) == 5,
        "abstract_grid_count": len(config.search.abstract_thresholds) == 7,
        "raw_floor": config.search.input_threshold == 0.5,
        "no_type_overrides": config.search.entity_type_overrides_allowed is False,
        "same_v02a_candidate": config.lineage.candidate_id
        == "scientific-entity-semantic-prompt-candidate-v0.2a",
        "same_raw_build": config.lineage.raw_build_id
        == "scientific-entity-gliner-small-v2.5-v0.1-20260829T141340564165Z",
        "development_72": config.lineage.expected_document_count == 72,
        "fresh_heldout_forbidden": config.safety.fresh_heldout_consumption_allowed is False,
        "model_inference_forbidden": config.safety.model_inference_allowed is False,
        "prompt_changes_forbidden": config.safety.prompt_changes_allowed is False,
        "canonical_mutation_forbidden": config.safety.canonical_truth_mutation_allowed is False,
        "full_corpus_forbidden": config.safety.full_corpus_build_authorized is False,
    }
    failed = [name for name, ok in checks.items() if not ok]
    print("[OK] report=scientific_entity_semantic_prompt_threshold_calibration_v02b_contract")
    print(f"[OK] status={config.layer.status}")
    print(f"[OK] trial_count={config.search.expected_trial_count}")
    print(f"[OK] title_threshold_count={len(config.search.title_thresholds)}")
    print(f"[OK] abstract_threshold_count={len(config.search.abstract_thresholds)}")
    print(f"[OK] input_threshold={config.search.input_threshold}")
    print(f"[OK] development_document_count={config.lineage.expected_document_count}")
    print(f"[OK] raw_prediction_count={config.lineage.expected_raw_prediction_count}")
    print(f"[OK] maximum_model_to_method_count={config.semantic_guardrails.maximum_model_to_method_count}")
    print(f"[OK] maximum_method_to_task_count={config.semantic_guardrails.maximum_method_to_task_count}")
    print(f"[OK] maximum_total_type_mismatch_count={config.semantic_guardrails.maximum_total_type_mismatch_count}")
    print(f"[OK] maximum_method_semantic_sink_count={config.semantic_guardrails.maximum_method_semantic_sink_count}")
    print(f"[OK] minimum_consumed_heldout_exact_f1={config.decision.selected_policy_minimum_consumed_heldout_exact_f1}")
    print(f"[OK] minimum_combined_dev_exact_f1={config.decision.selected_policy_minimum_combined_dev_exact_f1}")
    print("[OK] model_inference_executed=False")
    print("[OK] threshold_search_executed=False")
    print("[OK] fresh_heldout_consumed=False")
    print("[OK] canonical_truth_mutated=False")
    print("[OK] full_corpus_build_authorized=False")
    print("[OK] next_slice=execute_bounded_35_trial_threshold_search_on_existing_v02a_raw_predictions")
    if failed:
        print(f"[FAILED] required_failed_count={len(failed)}")
        for name in failed:
            print(f"[FAILED] {name}")
        return 1 if args.strict else 0
    print("[OK] required_failed_count=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
