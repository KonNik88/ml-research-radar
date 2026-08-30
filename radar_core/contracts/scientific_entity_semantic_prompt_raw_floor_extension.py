from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


CONFIG_SCHEMA_VERSION = "scientific_entity_semantic_prompt_raw_floor_extension_v0.2c"


class SemanticPromptRawFloorExtensionError(ValueError):
    """Raised when the frozen v0.2c raw-floor contract drifts."""


class _UniqueKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueKeySafeLoader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise SemanticPromptRawFloorExtensionError(f"Duplicate YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


class LayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["scientific_entity_semantic_prompt_raw_floor_extension"]
    version: Literal["v0.2c"]
    status: Literal["design_frozen"]
    layer_kind: Literal["bounded_raw_evidence_extension_experiment"]


class LineageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: Literal["scientific-entity-semantic-prompt-raw-floor-extension-v0.2c"]
    baseline_semantic_prompt_candidate_id: Literal["scientific-entity-semantic-prompt-candidate-v0.2a"]
    baseline_runtime_config_path: Literal["configs/scientific_entity_gliner_semantic_prompt_candidate_v0.2a.yaml"]
    candidate_runtime_config_path: Literal["configs/scientific_entity_gliner_semantic_prompt_raw_floor_candidate_v0.2c.yaml"]
    development_package_id: Literal["scientific-entity-semantic-prompt-development-v0.2a-20260829T140201009151Z"]
    v02a_raw_build_id: Literal["scientific-entity-gliner-small-v2.5-v0.1-20260829T141340564165Z"]
    v02a_raw_extractor_fingerprint: Literal["3e890253263ca3e5d7fa06e9a731205b020ec1251123b8aa1926a696180e48c0"]
    v02a_comparison_id: Literal["scientific-entity-semantic-prompt-comparison-v0.2a-20260829T145954260189Z"]
    v02b_calibration_id: Literal["scientific-entity-semantic-prompt-threshold-calibration-v0.2b-20260830T093225845167Z"]
    expected_document_count: Literal[72]
    expected_reference_mention_count: Literal[1316]
    development_role: Literal["consumed_development_only"]
    future_v02_acceptance_requires_new_disjoint_heldout: Literal[True]


class RawInferenceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    baseline_floor: Literal[0.5]
    candidate_floor: Literal[0.4]
    threshold_is_inclusive: Literal[True]
    expected_model_inference_document_count: Literal[72]
    source_fields: list[Literal["title", "abstract"]] = Field(min_length=2, max_length=2)
    only_intended_runtime_change: Literal["raw_inference_threshold_and_extractor_identity"]
    prompts_must_match_v02a_exactly: Literal[True]
    model_revision_artifact_must_match_v02a_exactly: Literal[True]
    adapter_windowing_must_match_v02a_exactly: Literal[True]
    canonical_entity_types_must_match_v02a_exactly: Literal[True]

    @model_validator(mode="after")
    def validate_source_fields(self) -> "RawInferenceConfig":
        if self.source_fields != ["title", "abstract"]:
            raise ValueError("source fields drifted")
        if self.candidate_floor >= self.baseline_floor:
            raise ValueError("candidate raw floor must be lower than v0.2a baseline floor")
        return self


class V02BSelectedPolicyControl(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Literal[0.5]
    abstract: Literal[0.625]


class BoundedPolicySearchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    primary_dimension: Literal["title_threshold"]
    title_thresholds: list[float] = Field(min_length=5, max_length=5)
    fixed_abstract_threshold: Literal[0.625]
    expected_trial_count: Literal[5]
    entity_type_overrides_allowed: Literal[False]
    thresholds_below_candidate_raw_floor_allowed: Literal[False]
    v02b_selected_policy_control: V02BSelectedPolicyControl
    lower_abstract_thresholds_reopened: Literal[False]

    @model_validator(mode="after")
    def validate_search(self) -> "BoundedPolicySearchConfig":
        expected = [0.40, 0.425, 0.45, 0.475, 0.50]
        if self.title_thresholds != expected:
            raise ValueError("title-only v0.2c threshold grid drifted")
        if len(self.title_thresholds) != self.expected_trial_count:
            raise ValueError("expected trial count drifted")
        if min(self.title_thresholds) < 0.40:
            raise ValueError("title thresholds cannot go below candidate raw floor")
        if 0.50 not in self.title_thresholds:
            raise ValueError("v0.2b title control must remain in v0.2c search")
        return self


class SemanticGuardrailsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision_split: Literal["consumed_v01_heldout_48"]
    maximum_model_to_method_count: Literal[43]
    maximum_method_to_task_count: Literal[25]
    maximum_total_type_mismatch_count: Literal[150]
    maximum_method_semantic_sink_count: Literal[74]
    maximum_any_predicted_type_mismatch_sink_count: Literal[74]
    require_all_guardrails_for_eligibility: Literal[True]


class SelectionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    eligible_trials_only: Literal[True]
    primary_objective: Literal["combined_dev_72_exact_f1"]
    tie_break_order: list[
        Literal[
            "combined_dev_72_relaxed_f1_desc",
            "combined_dev_72_exact_recall_desc",
            "title_threshold_desc",
            "trial_id_asc",
        ]
    ] = Field(min_length=4, max_length=4)
    automatic_production_promotion_allowed: Literal[False]

    @model_validator(mode="after")
    def validate_ties(self) -> "SelectionConfig":
        expected = [
            "combined_dev_72_relaxed_f1_desc",
            "combined_dev_72_exact_recall_desc",
            "title_threshold_desc",
            "trial_id_asc",
        ]
        if self.tie_break_order != expected:
            raise ValueError("v0.2c tie-break order drifted")
        return self


class DecisionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["development_candidate_gate_not_independent_acceptance"]
    selected_policy_minimum_consumed_heldout_exact_f1: Literal[0.396882]
    selected_policy_minimum_combined_dev_exact_f1: Literal[0.398654]
    selected_policy_minimum_consumed_heldout_relaxed_f1_desirable: Literal[0.419252]
    require_semantic_guardrails: Literal[True]
    all_hard_gates_required_for_promising: Literal[True]
    selected_trial_is_not_automatic_acceptance: Literal[True]
    selected_title_at_candidate_raw_floor_flags_possible_remaining_floor_binding: Literal[True]


class SafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_slice_runs_model_inference: Literal[False]
    contract_slice_runs_threshold_search: Literal[False]
    raw_candidate_inference_allowed_after_contract_freeze: Literal[True]
    model_or_tokenizer_download_requires_explicit_existing_builder_flag: Literal[True]
    prompt_changes_allowed: Literal[False]
    model_changes_allowed: Literal[False]
    canonical_truth_mutation_allowed: Literal[False]
    reconcile_input_allowed: Literal[False]
    provider_api_allowed: Literal[False]
    fresh_heldout_consumption_allowed: Literal[False]
    production_extractor_selected: Literal[False]
    full_corpus_build_authorized: Literal[False]
    publication_allowed: Literal[False]
    current_72_is_development_only: Literal[True]


class NextStepsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    after_contract_freeze: Literal["bounded_raw_inference_at_040_on_existing_72_development_documents"]
    after_raw_build_validation: Literal["deterministic_five_trial_title_threshold_search_at_abstract_0625"]
    if_promising_and_selected_title_above_raw_floor: Literal["materialize_v02c_policy_and_controlled_comparison"]
    if_promising_but_selected_title_equals_raw_floor: Literal["review_remaining_raw_floor_binding_before_spending_fresh_heldout"]
    if_not_promising: Literal["choose_next_bounded_extractor_hypothesis_without_reusing_future_heldout"]


class SemanticPromptRawFloorExtensionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[CONFIG_SCHEMA_VERSION]
    layer: LayerConfig
    lineage: LineageConfig
    raw_inference: RawInferenceConfig
    bounded_policy_search: BoundedPolicySearchConfig
    semantic_guardrails: SemanticGuardrailsConfig
    selection: SelectionConfig
    decision: DecisionConfig
    safety: SafetyConfig
    next_steps: NextStepsConfig


def load_semantic_prompt_raw_floor_extension_config(path: str | Path) -> SemanticPromptRawFloorExtensionConfig:
    path = Path(path)
    try:
        payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeySafeLoader)
    except (OSError, yaml.YAMLError) as exc:
        raise SemanticPromptRawFloorExtensionError(str(exc)) from exc
    try:
        return SemanticPromptRawFloorExtensionConfig.model_validate(payload)
    except Exception as exc:
        raise SemanticPromptRawFloorExtensionError(str(exc)) from exc


def canonical_config_sha256(config: SemanticPromptRawFloorExtensionConfig) -> str:
    payload = json.dumps(
        config.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
