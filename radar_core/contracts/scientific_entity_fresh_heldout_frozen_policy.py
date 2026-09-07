from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

CONFIG_SCHEMA_VERSION = "scientific_entity_fresh_heldout_frozen_policy_v0.2"
DERIVATION_SCHEMA_VERSION = "scientific_entity_fresh_heldout_frozen_policy_derivation_v0.2"
LINEAGE_SCHEMA_VERSION = "scientific_entity_fresh_heldout_frozen_policy_lineage_v0.2"
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class ScientificEntityFreshHeldoutFrozenPolicyError(ValueError):
    """Raised when the frozen fresh-heldout policy contract drifts."""


class LayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["scientific_entity_fresh_heldout_frozen_policy"]
    version: Literal["v0.2"]
    status: Literal["frozen_one_shot_policy_contract"]
    layer_kind: Literal["independent_heldout_policy_filtered_candidate_evidence"]


class CandidateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: Literal["scientific-entity-semantic-prompt-raw-floor-extension-v0.2c"]
    raw_inference_contract_path: Literal["configs/scientific_entity_fresh_heldout_frozen_inference_v0.2.yaml"]
    raw_inference_contract_sha256: str = Field(pattern=SHA256_PATTERN)
    raw_build_id: Literal["scientific-entity-gliner-small-v2.5-fresh-v0.2c-20260901T130232963026Z"]
    expected_raw_prediction_count: Literal[1257]
    expected_raw_extractor_fingerprint: str = Field(pattern=SHA256_PATTERN)
    runtime_config_sha256: str = Field(pattern=SHA256_PATTERN)
    frozen_policy_config_path: Literal["configs/scientific_entity_semantic_prompt_raw_floor_policy_v0.2c.yaml"]
    frozen_policy_config_sha256: str = Field(pattern=SHA256_PATTERN)
    calibration_id: Literal["scientific-entity-semantic-prompt-raw-floor-calibration-v0.2c-20260830T104242195583Z"]
    selected_trial_id: Literal["calibration-trial:adcd020d8bce5af1ff157f4303e0b171"]
    development_policy_build_id: Literal["scientific-entity-semantic-prompt-raw-floor-policy-v0.2c-20260830T105318817514Z"]


class FreshHeldoutConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sample_id: Literal["scientific-entity-fresh-heldout-sample-v0.2-20260901T130232963026Z"]
    review_id: Literal["scientific-entity-fresh-heldout-review-v0.2-20260901T130232963026Z"]
    expected_document_count: Literal[48]
    expected_reference_mention_count: Literal[944]


class PolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_threshold: Literal[0.4]
    threshold_is_inclusive: Literal[True]
    default_threshold: Literal[0.4]
    title_threshold: Literal[0.45]
    abstract_threshold: Literal[0.625]
    entity_type_overrides: dict[str, float]

    @model_validator(mode="after")
    def validate_no_type_overrides(self) -> "PolicyConfig":
        if self.entity_type_overrides:
            raise ValueError("entity_type_overrides must remain empty")
        return self


class ExtractorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["ml_radar_gliner_small_v2_5_semantic_prompt_raw_floor_policy_fresh_candidate"]
    version: Literal["0.2c.0-fresh"]
    policy_identity: Literal["frozen_v02c_policy_plus_fresh_raw_parent"]


class ExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    output_root: Literal["data/entities/scientific_entity_fresh_heldout_frozen_policy/v0.2"]
    build_id: Literal["scientific-entity-semantic-prompt-raw-floor-policy-fresh-v0.2c-20260901T130232963026Z"]
    build_status: Literal["candidate"]
    one_shot_execute: Literal[True]
    plan_runs_policy_filtering: Literal[False]
    overwrite_allowed: Literal[False]
    model_inference_allowed: Literal[False]


class SafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    raw_inference_must_validate_before_execute: Literal[True]
    raw_prediction_count_must_match: Literal[True]
    raw_extractor_fingerprint_must_match: Literal[True]
    fresh_heldout_policy_application_in_this_slice: Literal[True]
    prompt_changes_allowed: Literal[False]
    threshold_changes_allowed: Literal[False]
    model_changes_allowed: Literal[False]
    sampling_changes_allowed: Literal[False]
    threshold_tuning_allowed: Literal[False]
    evaluation_in_this_slice: Literal[False]
    acceptance_decision_in_this_slice: Literal[False]
    reference_labels_used_for_filtering: Literal[False]
    canonical_truth_mutation_allowed: Literal[False]
    reconcile_input_allowed: Literal[False]
    publication_allowed: Literal[False]
    production_extractor_selected: Literal[False]
    full_corpus_build_authorized: Literal[False]


class NextStepsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    after_plan: Literal["execute_frozen_v02c_policy_once"]
    after_execute: Literal["validate_frozen_v02c_policy_application"]
    after_validation: Literal["evaluate_frozen_v02c_on_fresh_heldout_once"]


class ScientificEntityFreshHeldoutFrozenPolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[CONFIG_SCHEMA_VERSION]
    layer: LayerConfig
    candidate: CandidateConfig
    fresh_heldout: FreshHeldoutConfig
    policy: PolicyConfig
    extractor: ExtractorConfig
    execution: ExecutionConfig
    safety: SafetyConfig
    next_steps: NextStepsConfig


class FrozenPolicyDerivationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[DERIVATION_SCHEMA_VERSION] = DERIVATION_SCHEMA_VERSION
    build_id: str = Field(min_length=1)
    parent_build_id: str = Field(min_length=1)
    candidate_id: Literal["scientific-entity-semantic-prompt-raw-floor-extension-v0.2c"]
    sample_id: str = Field(min_length=1)
    review_id: str = Field(min_length=1)
    runtime_config_sha256: str = Field(pattern=SHA256_PATTERN)
    frozen_policy_config_sha256: str = Field(pattern=SHA256_PATTERN)
    calibration_id: str = Field(min_length=1)
    selected_trial_id: str = Field(min_length=1)
    development_policy_build_id: str = Field(min_length=1)
    parent_extractor_fingerprint: str = Field(pattern=SHA256_PATTERN)
    candidate_extractor_fingerprint: str = Field(pattern=SHA256_PATTERN)
    input_threshold: Literal[0.4]
    title_threshold: Literal[0.45]
    abstract_threshold: Literal[0.625]
    entity_type_overrides: dict[str, float]
    input_prediction_count: Literal[1257]
    selected_prediction_count: int = Field(ge=0)
    rejected_prediction_count: int = Field(ge=0)
    mention_id_preserved: Literal[True]
    evidence_id_recomputed: Literal[True]
    confidence_preserved: Literal[True]
    model_inference_executed: Literal[False]
    threshold_tuning_executed: Literal[False]
    reference_labels_used_for_filtering: Literal[False]
    evaluation_executed: Literal[False]
    acceptance_decision_made: Literal[False]
    canonical_truth_mutated: Literal[False]
    may_be_used_as_reconcile_input: Literal[False]
    production_extractor_selected: Literal[False]
    full_corpus_build_authorized: Literal[False]
    publication_ready: Literal[False]

    @model_validator(mode="after")
    def validate_counts(self) -> "FrozenPolicyDerivationManifest":
        if self.selected_prediction_count + self.rejected_prediction_count != self.input_prediction_count:
            raise ValueError("selected + rejected must equal input prediction count")
        if self.entity_type_overrides:
            raise ValueError("entity_type_overrides must remain empty")
        return self


class FrozenPolicyLineage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[LINEAGE_SCHEMA_VERSION] = LINEAGE_SCHEMA_VERSION
    build_id: str = Field(min_length=1)
    parent_build_id: str = Field(min_length=1)
    calibration_id: str = Field(min_length=1)
    selected_trial_id: str = Field(min_length=1)
    mention_id: str = Field(min_length=1)
    parent_evidence_id: str = Field(min_length=1)
    candidate_evidence_id: str = Field(min_length=1)


class _UniqueKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueKeySafeLoader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ScientificEntityFreshHeldoutFrozenPolicyError(f"Duplicate YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def load_scientific_entity_fresh_heldout_frozen_policy_config(path: str | Path) -> ScientificEntityFreshHeldoutFrozenPolicyConfig:
    path = Path(path)
    try:
        payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeySafeLoader)
    except (OSError, yaml.YAMLError) as exc:
        raise ScientificEntityFreshHeldoutFrozenPolicyError(str(exc)) from exc
    if not isinstance(payload, dict):
        raise ScientificEntityFreshHeldoutFrozenPolicyError(f"Expected YAML object: {path}")
    return ScientificEntityFreshHeldoutFrozenPolicyConfig.model_validate(payload)
