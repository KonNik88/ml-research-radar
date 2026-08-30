from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


MANIFEST_SCHEMA_VERSION = "scientific_entity_semantic_prompt_raw_floor_calibration_manifest_v0.2c"
TRIAL_SCHEMA_VERSION = "scientific_entity_semantic_prompt_raw_floor_calibration_trial_v0.2c"
SELECTED_POLICY_SCHEMA_VERSION = "scientific_entity_semantic_prompt_raw_floor_selected_policy_v0.2c"
DIAGNOSTICS_SCHEMA_VERSION = "scientific_entity_semantic_prompt_raw_floor_calibration_diagnostics_v0.2c"


class RawFloorCalibrationTrial(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[TRIAL_SCHEMA_VERSION] = TRIAL_SCHEMA_VERSION
    calibration_id: str = Field(min_length=1)
    trial_id: str = Field(min_length=1)
    title_threshold: float = Field(ge=0.4, le=0.5)
    abstract_threshold: Literal[0.625]
    is_v02b_control_policy: bool
    selected_prediction_count: int = Field(ge=0)
    old_dev_prediction_count: int = Field(ge=0)
    consumed_heldout_prediction_count: int = Field(ge=0)
    old_dev_exact_f1: float | None
    consumed_heldout_exact_f1: float | None
    consumed_heldout_relaxed_f1: float | None
    combined_exact_precision: float | None
    combined_exact_recall: float | None
    combined_exact_f1: float | None
    combined_relaxed_f1: float | None
    model_to_method_count: int = Field(ge=0)
    method_to_task_count: int = Field(ge=0)
    total_type_mismatch_count: int = Field(ge=0)
    method_semantic_sink_count: int = Field(ge=0)
    max_predicted_type_mismatch_sink_count: int = Field(ge=0)
    semantic_guardrails_passed: bool
    eligible_for_selection: bool


class RawFloorSelectedPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[SELECTED_POLICY_SCHEMA_VERSION] = SELECTED_POLICY_SCHEMA_VERSION
    calibration_id: str = Field(min_length=1)
    selected_trial_id: str = Field(min_length=1)
    title_threshold: float = Field(ge=0.4, le=0.5)
    abstract_threshold: Literal[0.625]
    selection_objective: Literal["combined_dev_72_exact_f1"]
    hard_gates: dict[str, dict[str, object]]
    desirable_signals: dict[str, dict[str, object]]
    all_hard_gates_passed: bool
    candidate_promising_for_future_freeze: bool
    production_acceptance: Literal[False] = False
    independent_v02_acceptance: Literal[False] = False
    full_corpus_build_authorized: Literal[False] = False
    future_v02_acceptance_requires_new_disjoint_heldout: Literal[True] = True


class RawFloorCalibrationDiagnostics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[DIAGNOSTICS_SCHEMA_VERSION] = DIAGNOSTICS_SCHEMA_VERSION
    calibration_id: str = Field(min_length=1)
    trial_count: Literal[5]
    eligible_trial_count: int = Field(ge=0, le=5)
    v02b_control_trial_id: str = Field(min_length=1)
    v02b_control_trial_eligible: bool
    v02b_control_metrics_reproduced: bool
    v02b_control_selected_prediction_delta: int
    baseline_raw_evidence_preserved: bool
    baseline_raw_missing_count: int = Field(ge=0)
    baseline_raw_score_changed_count: int = Field(ge=0)
    new_at_or_above_baseline_floor_count: int = Field(ge=0)
    new_selected_by_v02b_control_count: int = Field(ge=0)
    new_at_or_above_baseline_floor_mention_ids: list[str]
    selected_trial_id: str = Field(min_length=1)
    selected_title_at_candidate_raw_floor: bool
    raw_input_floor_may_still_be_binding: bool
    raw_prediction_count: int = Field(ge=1)
    v02a_raw_prediction_count: Literal[1430] = 1430
    raw_prediction_delta_vs_v02a: int
    model_inference_executed_during_calibration: Literal[False] = False
    prompt_changes_executed: Literal[False] = False
    fresh_heldout_consumed: Literal[False] = False
    canonical_truth_mutated: Literal[False] = False
