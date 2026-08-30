from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

from radar_core.contracts.scientific_entity_semantic_prompt_raw_floor_extension import (
    canonical_config_sha256,
    load_semantic_prompt_raw_floor_extension_config,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs" / "scientific_entity_semantic_prompt_raw_floor_extension_v0.2c.yaml"


def _sha256_yaml(path: Path) -> str:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _runtime_semantic_snapshot(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    inf = data["inference"]
    return {
        "model": data["model"],
        "source_fields": inf["source_fields"],
        "flat_ner": inf["flat_ner"],
        "multi_label": inf["multi_label"],
        "window_size_tokens": inf["window_size_tokens"],
        "window_overlap_tokens": inf["window_overlap_tokens"],
        "batch_size": inf["batch_size"],
        "device": inf["device"],
        "seed": inf["seed"],
        "normalization_before_offsets": inf["normalization_before_offsets"],
        "surface_from_exact_source_slice": inf["surface_from_exact_source_slice"],
        "overlap_reconciliation": inf["overlap_reconciliation"],
        "labels": inf["labels"],
        "safety": data["safety"],
        "outputs": data["outputs"],
        "validation": data["validation"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    config_path = Path(args.config)
    config = load_semantic_prompt_raw_floor_extension_config(config_path)
    baseline_path = ROOT / config.lineage.baseline_runtime_config_path
    candidate_path = ROOT / config.lineage.candidate_runtime_config_path

    baseline = yaml.safe_load(baseline_path.read_text(encoding="utf-8"))
    candidate = yaml.safe_load(candidate_path.read_text(encoding="utf-8"))

    checks = {
        "design_config_exists": config_path.exists(),
        "baseline_runtime_exists": baseline_path.exists(),
        "candidate_runtime_exists": candidate_path.exists(),
        "baseline_floor_is_050": baseline["inference"]["threshold"] == 0.5,
        "candidate_floor_is_040": candidate["inference"]["threshold"] == 0.4,
        "runtime_semantics_unchanged": _runtime_semantic_snapshot(baseline_path) == _runtime_semantic_snapshot(candidate_path),
        "runtime_config_sha_changed": _sha256_yaml(baseline_path) != _sha256_yaml(candidate_path),
        "extractor_name_changed": baseline["extractor"]["name"] != candidate["extractor"]["name"],
        "extractor_version_changed": baseline["extractor"]["version"] != candidate["extractor"]["version"],
        "five_trial_title_grid": config.bounded_policy_search.title_thresholds == [0.4, 0.425, 0.45, 0.475, 0.5],
        "abstract_fixed_0625": config.bounded_policy_search.fixed_abstract_threshold == 0.625,
        "semantic_guardrails_preserved": (
            config.semantic_guardrails.maximum_model_to_method_count == 43
            and config.semantic_guardrails.maximum_method_to_task_count == 25
            and config.semantic_guardrails.maximum_total_type_mismatch_count == 150
            and config.semantic_guardrails.maximum_method_semantic_sink_count == 74
            and config.semantic_guardrails.maximum_any_predicted_type_mismatch_sink_count == 74
        ),
        "decision_gate_preserved_and_hardened": (
            config.decision.selected_policy_minimum_consumed_heldout_exact_f1 == 0.396882
            and config.decision.selected_policy_minimum_combined_dev_exact_f1 == 0.398654
        ),
        "fresh_heldout_forbidden": config.safety.fresh_heldout_consumption_allowed is False,
        "full_corpus_forbidden": config.safety.full_corpus_build_authorized is False,
        "contract_does_not_run_inference": config.safety.contract_slice_runs_model_inference is False,
        "contract_does_not_run_search": config.safety.contract_slice_runs_threshold_search is False,
    }

    failed = [name for name, passed in checks.items() if not passed]
    print("[OK] report=scientific_entity_semantic_prompt_raw_floor_extension_v02c_contract")
    print(f"[OK] status={config.layer.status}")
    print(f"[OK] candidate_id={config.lineage.candidate_id}")
    print(f"[OK] baseline_raw_floor={config.raw_inference.baseline_floor}")
    print(f"[OK] candidate_raw_floor={config.raw_inference.candidate_floor}")
    print(f"[OK] title_threshold_count={len(config.bounded_policy_search.title_thresholds)}")
    print(f"[OK] fixed_abstract_threshold={config.bounded_policy_search.fixed_abstract_threshold}")
    print(f"[OK] expected_trial_count={config.bounded_policy_search.expected_trial_count}")
    print(f"[OK] development_document_count={config.lineage.expected_document_count}")
    print(f"[OK] reference_mention_count={config.lineage.expected_reference_mention_count}")
    print(f"[OK] maximum_model_to_method_count={config.semantic_guardrails.maximum_model_to_method_count}")
    print(f"[OK] maximum_method_to_task_count={config.semantic_guardrails.maximum_method_to_task_count}")
    print(f"[OK] minimum_consumed_heldout_exact_f1={config.decision.selected_policy_minimum_consumed_heldout_exact_f1}")
    print(f"[OK] minimum_combined_dev_exact_f1={config.decision.selected_policy_minimum_combined_dev_exact_f1}")
    print(f"[OK] design_config_sha256={canonical_config_sha256(config)}")
    print(f"[OK] runtime_config_sha_changed={checks['runtime_config_sha_changed']}")
    print("[OK] model_inference_executed=False")
    print("[OK] threshold_search_executed=False")
    print("[OK] fresh_heldout_consumed=False")
    print("[OK] canonical_truth_mutated=False")
    print("[OK] full_corpus_build_authorized=False")
    print(f"[OK] next_slice={config.next_steps.after_contract_freeze}")
    if failed:
        print(f"[FAILED] required_failed_count={len(failed)}")
        for name in failed:
            print(f"[FAILED] {name}")
        return 1 if args.strict else 0
    print("[OK] required_failed_count=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
