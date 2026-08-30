from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from radar_core.contracts.scientific_entity_semantic_prompt_raw_floor_extension import (
    canonical_config_sha256,
    load_semantic_prompt_raw_floor_extension_config,
)


ROOT = Path(__file__).resolve().parents[2]
DESIGN_CONFIG = ROOT / "configs" / "scientific_entity_semantic_prompt_raw_floor_extension_v0.2c.yaml"
BASELINE_RUNTIME = ROOT / "configs" / "scientific_entity_gliner_semantic_prompt_candidate_v0.2a.yaml"
CANDIDATE_RUNTIME = ROOT / "configs" / "scientific_entity_gliner_semantic_prompt_raw_floor_candidate_v0.2c.yaml"


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _snapshot(payload: dict) -> dict:
    inf = payload["inference"]
    return {
        "model": payload["model"],
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
        "safety": payload["safety"],
        "outputs": payload["outputs"],
        "validation": payload["validation"],
    }


def test_contract_freezes_existing_72_development_lineage() -> None:
    config = load_semantic_prompt_raw_floor_extension_config(DESIGN_CONFIG)
    assert config.lineage.expected_document_count == 72
    assert config.lineage.expected_reference_mention_count == 1316
    assert config.lineage.development_package_id == (
        "scientific-entity-semantic-prompt-development-v0.2a-20260829T140201009151Z"
    )
    assert config.lineage.v02b_calibration_id == (
        "scientific-entity-semantic-prompt-threshold-calibration-v0.2b-20260830T093225845167Z"
    )
    assert config.lineage.future_v02_acceptance_requires_new_disjoint_heldout is True


def test_runtime_changes_only_raw_floor_and_extractor_identity() -> None:
    baseline = _load_yaml(BASELINE_RUNTIME)
    candidate = _load_yaml(CANDIDATE_RUNTIME)
    assert baseline["inference"]["threshold"] == 0.5
    assert candidate["inference"]["threshold"] == 0.4
    assert baseline["extractor"]["name"] != candidate["extractor"]["name"]
    assert baseline["extractor"]["version"] != candidate["extractor"]["version"]
    assert _snapshot(baseline) == _snapshot(candidate)


def test_runtime_prompts_are_exactly_v02a_prompts() -> None:
    baseline = _load_yaml(BASELINE_RUNTIME)
    candidate = _load_yaml(CANDIDATE_RUNTIME)
    assert candidate["inference"]["labels"] == baseline["inference"]["labels"]
    assert [x["entity_type"] for x in candidate["inference"]["labels"]] == [
        "task", "method", "dataset", "metric", "model", "domain"
    ]


def test_title_only_search_is_frozen_to_five_trials() -> None:
    config = load_semantic_prompt_raw_floor_extension_config(DESIGN_CONFIG)
    assert config.bounded_policy_search.title_thresholds == [0.4, 0.425, 0.45, 0.475, 0.5]
    assert config.bounded_policy_search.fixed_abstract_threshold == 0.625
    assert config.bounded_policy_search.expected_trial_count == 5
    assert config.bounded_policy_search.lower_abstract_thresholds_reopened is False
    assert config.bounded_policy_search.v02b_selected_policy_control.title == 0.5
    assert config.bounded_policy_search.v02b_selected_policy_control.abstract == 0.625


def test_semantic_guardrails_are_not_relaxed_after_v02b() -> None:
    config = load_semantic_prompt_raw_floor_extension_config(DESIGN_CONFIG)
    g = config.semantic_guardrails
    assert g.maximum_model_to_method_count == 43
    assert g.maximum_method_to_task_count == 25
    assert g.maximum_total_type_mismatch_count == 150
    assert g.maximum_method_semantic_sink_count == 74
    assert g.maximum_any_predicted_type_mismatch_sink_count == 74


def test_v02c_decision_requires_recovery_beyond_v02b_selected_combined_f1() -> None:
    config = load_semantic_prompt_raw_floor_extension_config(DESIGN_CONFIG)
    assert config.decision.selected_policy_minimum_consumed_heldout_exact_f1 == 0.396882
    assert config.decision.selected_policy_minimum_combined_dev_exact_f1 == 0.398654
    assert config.decision.selected_policy_minimum_consumed_heldout_relaxed_f1_desirable == 0.419252
    assert config.decision.all_hard_gates_required_for_promising is True


def test_contract_slice_is_non_inference_and_does_not_spend_fresh_heldout() -> None:
    config = load_semantic_prompt_raw_floor_extension_config(DESIGN_CONFIG)
    assert config.safety.contract_slice_runs_model_inference is False
    assert config.safety.contract_slice_runs_threshold_search is False
    assert config.safety.raw_candidate_inference_allowed_after_contract_freeze is True
    assert config.safety.prompt_changes_allowed is False
    assert config.safety.model_changes_allowed is False
    assert config.safety.fresh_heldout_consumption_allowed is False
    assert config.safety.canonical_truth_mutation_allowed is False
    assert config.safety.full_corpus_build_authorized is False


def test_design_config_hash_is_stable() -> None:
    first = load_semantic_prompt_raw_floor_extension_config(DESIGN_CONFIG)
    second = load_semantic_prompt_raw_floor_extension_config(DESIGN_CONFIG)
    assert canonical_config_sha256(first) == canonical_config_sha256(second)
    assert len(canonical_config_sha256(first)) == 64
