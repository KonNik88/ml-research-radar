from __future__ import annotations

from pathlib import Path

import yaml

from radar_core.contracts.scientific_entity_fresh_heldout_gate import (
    ENTITY_TYPES,
    canonical_config_sha256,
    load_scientific_entity_fresh_heldout_gate_config,
)


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "scientific_entity_fresh_heldout_gate_v0.2.yaml"
RUNTIME = ROOT / "configs" / "scientific_entity_gliner_semantic_prompt_raw_floor_candidate_v0.2c.yaml"
POLICY = ROOT / "configs" / "scientific_entity_semantic_prompt_raw_floor_policy_v0.2c.yaml"
COMPARISON = ROOT / "configs" / "scientific_entity_semantic_prompt_raw_floor_comparison_v0.2c.yaml"


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_gate_freezes_exact_v02c_candidate_identity() -> None:
    config = load_scientific_entity_fresh_heldout_gate_config(CONFIG)
    runtime = _yaml(RUNTIME)
    policy = _yaml(POLICY)
    comparison = _yaml(COMPARISON)

    assert config.candidate.candidate_id == (
        "scientific-entity-semantic-prompt-raw-floor-extension-v0.2c"
    )
    assert config.candidate.development_comparison_id == (
        "scientific-entity-semantic-prompt-raw-floor-comparison-v0.2c-"
        "20260830T110628936475Z"
    )
    assert runtime["inference"]["threshold"] == 0.4
    assert policy["policy"]["source_field_thresholds"] == {
        "title": 0.45,
        "abstract": 0.625,
    }
    assert policy["policy"]["entity_type_thresholds"] == {}
    assert comparison["candidate"]["expected_selected_prediction_count"] == 1077


def test_sampling_is_new_disjoint_prediction_blind_48_paper_design() -> None:
    config = load_scientific_entity_fresh_heldout_gate_config(CONFIG)
    assert config.development_exclusion.expected_consumed_document_count == 72
    assert config.development_exclusion.canonical_id_overlap_allowed is False
    assert config.development_exclusion.exclude_all_consumed_development_documents is True
    assert config.development_exclusion.previous_v01_heldout_is_consumed_development_for_v02 is True

    s = config.sampling
    assert s.uniform_document_count == 24
    assert s.type_enriched_documents_per_type == 4
    assert s.expected_document_count == 48
    assert s.expected_annotation_row_count == 96
    assert s.source_fields == ["title", "abstract"]
    assert set(s.enrichment_terms) == set(ENTITY_TYPES)

    r = config.reference_freeze
    assert r.prediction_blind is True
    assert r.annotations_initially_empty is True
    assert r.candidate_predictions_may_be_read_during_sampling is False
    assert r.candidate_predictions_may_be_read_during_annotation is False
    assert r.candidate_inference_only_after_reference_freeze is True


def test_reference_adequacy_is_frozen_before_sample_annotation() -> None:
    config = load_scientific_entity_fresh_heldout_gate_config(CONFIG)
    r = config.reference_freeze
    assert r.require_exact_sample_identity is True
    assert r.require_original_blank_template is True
    assert r.require_all_annotation_rows_complete is True
    assert r.require_zero_unresolved_uncertain_mentions is True
    assert r.minimum_reference_mentions_per_type == 20
    assert r.required_entity_types == list(ENTITY_TYPES)


def test_acceptance_gate_reuses_historical_exact_floor_and_semantic_caps() -> None:
    config = load_scientific_entity_fresh_heldout_gate_config(CONFIG)
    a = config.acceptance
    assert a.minimum_exact_f1 == 0.396882
    assert a.exact_f1_floor_origin == "independent_v01_heldout_exact_f1"
    assert a.desirable_minimum_relaxed_f1 == 0.414868
    assert a.relaxed_f1_floor_role == "desirable_not_hard"
    assert a.require_relaxed_f1_as_hard_gate is False
    assert a.maximum_model_to_method_count == 43
    assert a.maximum_method_to_task_count == 25
    assert a.maximum_total_type_mismatch_count == 150
    assert a.maximum_method_semantic_sink_count == 74
    assert a.maximum_any_predicted_type_mismatch_sink_count == 74
    assert a.no_post_heldout_tuning is True
    assert a.all_hard_gates_required_for_acceptance is True


def test_pass_and_fail_decisions_do_not_leak_into_post_heldout_tuning() -> None:
    config = load_scientific_entity_fresh_heldout_gate_config(CONFIG)
    d = config.decision_semantics
    assert d.if_all_hard_gates_pass == (
        "accept_as_independently_validated_bounded_extractor_v0.2"
    )
    assert d.pass_does_not_select_production_extractor is True
    assert d.pass_does_not_authorize_full_corpus_build is True
    assert d.if_any_hard_gate_fails == "reject_v02c_independent_acceptance"
    assert d.failed_heldout_becomes_consumed_development_evidence is True
    assert d.future_candidate_after_failure_requires_new_independent_heldout is True
    assert d.heldout_may_not_be_reused_for_retuning_and_reacceptance is True


def test_contract_slice_does_not_select_or_consume_fresh_heldout() -> None:
    config = load_scientific_entity_fresh_heldout_gate_config(CONFIG)
    s = config.safety
    assert s.contract_slice_selects_sample is False
    assert s.contract_slice_runs_model_inference is False
    assert s.contract_slice_runs_evaluation is False
    assert s.contract_slice_consumes_fresh_heldout is False
    assert s.sample_preparation_allowed_after_contract_freeze is True
    assert s.model_inference_allowed_before_reference_freeze is False
    assert s.threshold_tuning_allowed is False
    assert s.prompt_changes_allowed is False
    assert s.model_changes_allowed is False
    assert s.entity_type_changes_allowed is False
    assert s.canonical_truth_mutation_allowed is False
    assert s.production_extractor_selected is False
    assert s.full_corpus_build_authorized is False


def test_design_hash_is_deterministic() -> None:
    first = load_scientific_entity_fresh_heldout_gate_config(CONFIG)
    second = load_scientific_entity_fresh_heldout_gate_config(CONFIG)
    assert canonical_config_sha256(first) == canonical_config_sha256(second)
    assert len(canonical_config_sha256(first)) == 64
