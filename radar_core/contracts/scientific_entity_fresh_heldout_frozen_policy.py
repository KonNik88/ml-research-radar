from __future__ import annotations

from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from radar_core.contracts.scientific_entity_evidence import ScientificEntitySourceField
from radar_core.contracts.scientific_entity_gliner_calibration import ScientificEntityThresholdPolicy

CONFIG_SCHEMA_VERSION = "scientific_entity_fresh_heldout_frozen_policy_v0.2"
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class ScientificEntityFreshHeldoutFrozenPolicyError(ValueError):
    """Raised when the frozen fresh-heldout policy contract drifts."""


class LayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["scientific_entity_fresh_heldout_frozen_policy"]
    version: Literal["v0.2"]
    status: Literal["frozen_policy_application_contract"]
    layer_kind: Literal["independent_heldout_policy_filtered_candidate_evidence"]


class CandidateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: Literal["scientific-entity-semantic-prompt-raw-floor-extension-v0.2c"]
    raw_build_id: Literal["scientific-entity-gliner-small-v2.5-fresh-v0.2c-20260901T130232963026Z"]
    raw_build_root: Literal["data/entities/scientific_entity_evidence/v0.1"]
    expected_document_count: Literal[48]
    expected_raw_mention_count: Literal[1257]
    expected_raw_extractor_fingerprint: str = Field(pattern=SHA256_PATTERN)


class FreshHeldoutConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sample_id: Literal["scientific-entity-fresh-heldout-sample-v0.2-20260901T130232963026Z"]
    review_id: Literal["scientific-entity-fresh-heldout-review-v0.2-20260901T130232963026Z"]
    selected_canonical_ids_sha256: str = Field(pattern=SHA256_PATTERN)
    expected_reference_mention_count: Literal[944]


class PolicyOriginConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    development_policy_config_path: Literal[
        "configs/scientific_entity_semantic_prompt_raw_floor_policy_v0.2c.yaml"
    ]
    development_policy_config_sha256: str = Field(pattern=SHA256_PATTERN)
    calibration_id: Literal[
        "scientific-entity-semantic-prompt-raw-floor-calibration-v0.2c-20260830T104242195583Z"
    ]
    selected_trial_id: Literal["calibration-trial:adcd020d8bce5af1ff157f4303e0b171"]
    input_threshold: Literal[0.4]
    threshold_is_inclusive: Literal[True]
    default_threshold: Literal[0.4]
    source_field_thresholds: dict[ScientificEntitySourceField, float]
    entity_type_thresholds: dict[str, float]

    @model_validator(mode="after")
    def validate_policy(self) -> "PolicyOriginConfig":
        expected = {
            ScientificEntitySourceField.TITLE: 0.45,
            ScientificEntitySourceField.ABSTRACT: 0.625,
        }
        if self.source_field_thresholds != expected:
            raise ValueError("frozen v0.2c policy must remain title>=0.45 / abstract>=0.625")
        if self.entity_type_thresholds:
            raise ValueError("fresh v0.2 frozen policy forbids entity-type threshold overrides")
        return self

    def threshold_policy(self) -> ScientificEntityThresholdPolicy:
        return ScientificEntityThresholdPolicy(
            default_threshold=self.default_threshold,
            source_field_thresholds=self.source_field_thresholds,
            entity_type_thresholds={},
        )


class ExtractorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["ml_radar_gliner_small_v2_5_fresh_v02c_frozen_policy"]
    version: Literal["0.2c.0"]
    environment_lock_path: Literal["requirements/requirements.entities_gliner.lock.txt"]


class ExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    output_root: Literal["data/entities/scientific_entity_fresh_heldout_policy/v0.2"]
    build_id: Literal["scientific-entity-gliner-small-v2.5-fresh-v0.2c-policy-20260901T130232963026Z"]
    build_status: Literal["candidate"]
    one_shot_execute: Literal[True]
    overwrite_allowed: Literal[False]
    plan_runs_model_inference: Literal[False]
    plan_runs_evaluation: Literal[False]


class SafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    raw_inference_must_validate_first: Literal[True]
    new_model_inference_allowed: Literal[False]
    threshold_tuning_allowed: Literal[False]
    prompt_changes_allowed: Literal[False]
    model_changes_allowed: Literal[False]
    sampling_changes_allowed: Literal[False]
    reference_comparison_allowed: Literal[False]
    evaluation_in_this_slice: Literal[False]
    acceptance_decision_in_this_slice: Literal[False]
    canonical_truth_mutation_allowed: Literal[False]
    reconcile_input_allowed: Literal[False]
    publication_allowed: Literal[False]
    production_extractor_selected: Literal[False]
    full_corpus_build_authorized: Literal[False]


class NextStepsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    after_plan: Literal["execute_frozen_v02c_policy_once"]
    after_execute: Literal["validate_frozen_v02c_policy_application"]
    after_validation: Literal["evaluate_frozen_v02c_policy_once"]


class ScientificEntityFreshHeldoutFrozenPolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[CONFIG_SCHEMA_VERSION]
    layer: LayerConfig
    candidate: CandidateConfig
    fresh_heldout: FreshHeldoutConfig
    policy_origin: PolicyOriginConfig
    extractor: ExtractorConfig
    execution: ExecutionConfig
    safety: SafetyConfig
    next_steps: NextStepsConfig


class _UniqueKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueKeySafeLoader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ScientificEntityFreshHeldoutFrozenPolicyError(
                f"Duplicate YAML key: {key!r}"
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def load_scientific_entity_fresh_heldout_frozen_policy_config(path):
    try:
        payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeySafeLoader)
    except yaml.YAMLError as exc:
        raise ScientificEntityFreshHeldoutFrozenPolicyError(
            f"Invalid YAML config {path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ScientificEntityFreshHeldoutFrozenPolicyError(
            f"Expected YAML object: {path}"
        )
    return ScientificEntityFreshHeldoutFrozenPolicyConfig.model_validate(payload)
