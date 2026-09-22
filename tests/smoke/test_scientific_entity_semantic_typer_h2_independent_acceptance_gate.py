from __future__ import annotations

from pathlib import Path

import pytest

from radar_core.contracts.scientific_entity_semantic_typer_h2_independent_acceptance_gate import (
    ScientificEntityH2IndependentAcceptanceGateError,
    canonical_config_sha256,
    load_h2_independent_acceptance_gate_config,
)


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "scientific_entity_semantic_typer_h2_independent_acceptance_gate_v0.3.yaml"


def test_h2_independent_gate_freezes_exact_candidate_and_sample_lineage() -> None:
    config = load_h2_independent_acceptance_gate_config(CONFIG)
    assert config.candidate_lineage.candidate_id == (
        "scientific-entity-semantic-typer-candidate-v0.3-h2-selective-model-over-method"
    )
    assert config.candidate_lineage.candidate_fingerprint_sha256 == (
        "6d3782fb1f2cc7219b7083bcf381c17c546491425e817c0f5620ff145bfa6966"
    )
    assert config.candidate_lineage.threshold == 0.1
    assert config.candidate_lineage.baseline_type == "method"
    assert config.candidate_lineage.semantic_typer_type == "model"
    assert config.fresh_heldout_lineage.sample_id == (
        "scientific-entity-fresh-heldout-sample-v0.3-20260919T093837653829Z"
    )
    assert config.fresh_heldout_lineage.expected_document_count == 48
    assert config.fresh_heldout_lineage.expected_annotation_row_count == 96
    assert config.fresh_heldout_lineage.expected_consumed_union_document_count == 120


def test_reference_adequacy_is_frozen_before_h2_inference() -> None:
    config = load_h2_independent_acceptance_gate_config(CONFIG)
    reference = config.reference_adequacy
    assert reference.prediction_blind is True
    assert reference.require_all_annotation_rows_complete is True
    assert reference.require_zero_unresolved_uncertain_mentions is True
    assert reference.minimum_reference_mentions_per_type == 20
    assert reference.required_entity_types == [
        "task", "method", "dataset", "metric", "model", "domain"
    ]
    assert reference.require_exact_source_slice_surface is True
    assert reference.duplicate_typed_spans_allowed is False
    assert reference.automatic_annotation_allowed is False
    assert reference.automatic_approval_allowed is False
    assert reference.candidate_inference_only_after_reference_freeze is True


def test_h2_independent_comparative_hard_gates_are_exactly_preregistered() -> None:
    config = load_h2_independent_acceptance_gate_config(CONFIG)
    gate = config.comparative_acceptance
    assert gate.minimum_typer_coverage == 0.95
    assert gate.minimum_same_span_accuracy_delta == 0.01
    assert gate.minimum_net_corrected_cases == 5
    assert gate.maximum_regression_rate == 0.05
    assert gate.minimum_model_to_method_reduction_fraction == 0.10
    assert gate.minimum_macro_f1_delta == 0.0
    assert gate.minimum_exact_f1 == 0.396882
    assert gate.desirable_minimum_relaxed_f1 == 0.414868
    assert gate.require_relaxed_f1_as_hard_gate is False
    assert gate.required_metric_missing_denominator_policy == "fail_closed_evidence_insufficient"
    assert gate.no_post_heldout_tuning is True
    assert gate.all_hard_gates_required_for_acceptance is True


def test_historical_raw_caps_remain_diagnostics_only() -> None:
    config = load_h2_independent_acceptance_gate_config(CONFIG)
    diagnostics = config.historical_diagnostics
    assert diagnostics.historical_maximum_model_to_method_count == 43
    assert diagnostics.historical_maximum_method_to_task_count == 25
    assert diagnostics.historical_maximum_total_type_mismatch_count == 150
    assert diagnostics.historical_maximum_method_semantic_sink_count == 74
    assert diagnostics.historical_maximum_any_predicted_type_mismatch_sink_count == 74
    assert diagnostics.historical_raw_count_caps_are_hard_h2_gates is False
    assert diagnostics.require_corrected_errors is True
    assert diagnostics.require_introduced_regressions is True
    assert diagnostics.require_model_to_method_direct_corrections is True
    assert diagnostics.require_model_to_method_wrong_to_wrong is True


def test_decision_semantics_do_not_authorize_production() -> None:
    config = load_h2_independent_acceptance_gate_config(CONFIG)
    decision = config.decision_semantics
    assert decision.if_all_hard_gates_pass == (
        "accept_h2_as_independently_validated_bounded_semantic_typing_intervention"
    )
    assert decision.if_any_hard_gate_fails == "reject_h2_independent_acceptance"
    assert decision.pass_does_not_select_production_extractor is True
    assert decision.pass_does_not_authorize_full_corpus_build is True
    assert decision.failed_heldout_becomes_consumed_evidence is True
    assert decision.future_candidate_after_failure_requires_new_independent_heldout is True
    assert decision.heldout_may_not_be_reused_for_retuning_and_reacceptance is True


def test_contract_slice_spends_no_independent_evidence() -> None:
    config = load_h2_independent_acceptance_gate_config(CONFIG)
    safety = config.safety
    assert safety.contract_slice_reads_human_reference_results is False
    assert safety.contract_slice_runs_baseline_inference is False
    assert safety.contract_slice_runs_h2_inference is False
    assert safety.contract_slice_runs_evaluation is False
    assert safety.contract_slice_makes_acceptance_decision is False
    assert safety.contract_slice_consumes_fresh_heldout is False
    assert safety.model_inference_allowed_before_reference_freeze is False
    assert safety.threshold_tuning_allowed is False
    assert safety.policy_revision_allowed is False
    assert safety.canonical_truth_mutation_allowed is False
    assert safety.production_extractor_selection_allowed is False
    assert safety.full_corpus_build_authorized is False


def test_duplicate_yaml_key_fails_closed(tmp_path: Path) -> None:
    payload = CONFIG.read_text(encoding="utf-8")
    payload = payload.replace(
        "  minimum_typer_coverage: 0.95\n",
        "  minimum_typer_coverage: 0.95\n  minimum_typer_coverage: 0.90\n",
        1,
    )
    bad = tmp_path / "bad.yaml"
    bad.write_text(payload, encoding="utf-8")
    with pytest.raises(ScientificEntityH2IndependentAcceptanceGateError, match="Duplicate YAML key"):
        load_h2_independent_acceptance_gate_config(bad)


def test_gate_config_hash_is_deterministic() -> None:
    first = load_h2_independent_acceptance_gate_config(CONFIG)
    second = load_h2_independent_acceptance_gate_config(CONFIG)
    assert canonical_config_sha256(first) == canonical_config_sha256(second)
    assert len(canonical_config_sha256(first)) == 64
