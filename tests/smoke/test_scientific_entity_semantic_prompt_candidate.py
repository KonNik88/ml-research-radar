from __future__ import annotations

from pathlib import Path

import pytest

from radar_core.contracts.scientific_entity_semantic_prompt_candidate import (
    EXPECTED_BASELINE_PROMPTS,
    EXPECTED_CANDIDATE_PROMPTS,
    SemanticPromptCandidateConfig,
    load_semantic_prompt_candidate_config,
    validate_candidate_contract,
)
from radar_core.entities.scientific_entity_gliner import (
    ScientificEntityGLiNERConfig,
    load_gliner_config,
)


ROOT = Path(__file__).resolve().parents[2]
DESIGN_CONFIG = ROOT / "configs" / "scientific_entity_semantic_prompt_candidate_v0.2a.yaml"
BASELINE_CONFIG = ROOT / "configs" / "scientific_entity_gliner_candidate_v0.1.yaml"
CANDIDATE_CONFIG = ROOT / "configs" / "scientific_entity_gliner_semantic_prompt_candidate_v0.2a.yaml"


def _prompt_map(config: ScientificEntityGLiNERConfig) -> dict[str, str]:
    return {row.entity_type.value: row.prompt for row in config.inference.labels}


def test_design_contract_freezes_exact_six_prompt_deltas() -> None:
    design = load_semantic_prompt_candidate_config(DESIGN_CONFIG)
    assert isinstance(design, SemanticPromptCandidateConfig)
    assert {row.entity_type.value: row.baseline_prompt for row in design.prompts} == EXPECTED_BASELINE_PROMPTS
    assert {row.entity_type.value: row.candidate_prompt for row in design.prompts} == EXPECTED_CANDIDATE_PROMPTS
    assert all(EXPECTED_BASELINE_PROMPTS[k] != EXPECTED_CANDIDATE_PROMPTS[k] for k in EXPECTED_BASELINE_PROMPTS)


def test_runtime_candidate_changes_only_allowed_prompt_extractor_delta() -> None:
    report = validate_candidate_contract(project_root=ROOT, design_config_path=DESIGN_CONFIG)
    assert report["ok"] is True
    assert report["changed_prompt_count"] == 6
    assert report["runtime_config_sha_changed"] is True
    assert report["model_inference_executed"] is False
    assert report["threshold_tuning_executed"] is False
    assert report["canonical_truth_mutated"] is False


def test_runtime_candidate_keeps_model_windowing_and_raw_threshold() -> None:
    baseline = load_gliner_config(BASELINE_CONFIG)
    candidate = load_gliner_config(CANDIDATE_CONFIG)
    assert candidate.model == baseline.model
    assert candidate.inference.threshold == baseline.inference.threshold == 0.5
    assert candidate.inference.window_size_tokens == baseline.inference.window_size_tokens == 320
    assert candidate.inference.window_overlap_tokens == baseline.inference.window_overlap_tokens == 64
    assert candidate.inference.flat_ner is baseline.inference.flat_ner is False
    assert candidate.inference.multi_label is baseline.inference.multi_label is False
    assert _prompt_map(candidate) == EXPECTED_CANDIDATE_PROMPTS


def test_development_evidence_boundary_is_24_plus_48_not_v02_heldout() -> None:
    design = load_semantic_prompt_candidate_config(DESIGN_CONFIG)
    assert design.development_evidence.old_dev.document_count == 24
    assert design.development_evidence.consumed_v01_heldout.document_count == 48
    assert design.development_evidence.combined_document_count == 72
    assert design.development_evidence.current_48_may_be_called_independent_heldout_for_v02 is False
    assert design.development_evidence.future_v02_acceptance_requires_new_disjoint_heldout is True


def test_first_controlled_comparison_keeps_frozen_055_065_policy() -> None:
    design = load_semantic_prompt_candidate_config(DESIGN_CONFIG)
    policy = design.controlled_comparison.frozen_source_field_policy
    assert policy.title_threshold == 0.55
    assert policy.abstract_threshold == 0.65
    assert policy.entity_type_overrides == {}
    assert design.controlled_comparison.raw_candidate_inference_threshold == 0.5


def test_decision_gates_are_prefrozen_and_bounded() -> None:
    design = load_semantic_prompt_candidate_config(DESIGN_CONFIG)
    gates = design.controlled_comparison.decision_gates.hard_guardrails
    assert gates.minimum_overall_exact_f1 == 0.386882
    assert gates.maximum_model_to_method_count == 44
    assert gates.maximum_method_to_task_count == 28
    assert gates.maximum_total_type_mismatch_count == 176
    assert gates.maximum_method_semantic_sink_count == 84
    assert gates.maximum_any_predicted_type_mismatch_sink_count == 94
    assert design.controlled_comparison.decision_gates.all_hard_guardrails_required_for_promising is True


def test_safety_boundary_does_not_promote_or_expand_scope() -> None:
    design = load_semantic_prompt_candidate_config(DESIGN_CONFIG)
    safety = design.safety
    assert safety.contract_slice_runs_model_inference is False
    assert safety.contract_slice_runs_threshold_tuning is False
    assert safety.changes_canonical_truth is False
    assert safety.may_be_used_as_reconcile_input is False
    assert safety.production_extractor_selected is False
    assert safety.full_corpus_build_authorized is False
    assert safety.publication_ready is False
    assert safety.medium_model_comparison_in_scope is False
    assert safety.fine_tuning_in_scope is False
    assert safety.markup_cleanup_in_scope is False


def test_prompt_drift_fails_closed() -> None:
    design = load_semantic_prompt_candidate_config(DESIGN_CONFIG)
    payload = design.model_dump(mode="json")
    payload["prompts"][0]["candidate_prompt"] = "different prompt"
    with pytest.raises(ValueError, match="candidate prompt drift"):
        SemanticPromptCandidateConfig.model_validate(payload)
