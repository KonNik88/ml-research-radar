from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from radar_core.contracts.scientific_entity_evidence import ScientificEntitySourceField


POLICY_CONFIG_SCHEMA_VERSION = "scientific_entity_semantic_prompt_raw_floor_policy_v0.2c"
POLICY_DERIVATION_SCHEMA_VERSION = "scientific_entity_semantic_prompt_raw_floor_policy_derivation_v0.2c"
POLICY_LINEAGE_SCHEMA_VERSION = "scientific_entity_semantic_prompt_raw_floor_policy_lineage_v0.2c"


class RawFloorPolicyError(ValueError):
    """Raised when the v0.2c selected-policy contract drifts."""


class _UniqueKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueKeySafeLoader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise RawFloorPolicyError(f"Duplicate YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


class LayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["scientific_entity_semantic_prompt_raw_floor_policy"]
    version: Literal["v0.2c"]
    status: Literal["development_candidate"]
    layer_kind: Literal["derived_policy_filtered_mention_evidence"]


class CandidateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: Literal["scientific-entity-semantic-prompt-raw-floor-extension-v0.2c"]
    design_config_path: Literal["configs/scientific_entity_semantic_prompt_raw_floor_extension_v0.2c.yaml"]
    runtime_config_path: Literal["configs/scientific_entity_gliner_semantic_prompt_raw_floor_candidate_v0.2c.yaml"]
    development_package_id: Literal["scientific-entity-semantic-prompt-development-v0.2a-20260829T140201009151Z"]
    raw_build_id: Literal["scientific-entity-gliner-small-v2.5-v0.1-20260830T100756992945Z"]
    calibration_id: Literal["scientific-entity-semantic-prompt-raw-floor-calibration-v0.2c-20260830T104242195583Z"]
    selected_trial_id: Literal["calibration-trial:adcd020d8bce5af1ff157f4303e0b171"]
    expected_document_count: Literal[72]
    expected_raw_prediction_count: Literal[1762]


class ThresholdPolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_threshold: Literal[0.4]
    threshold_is_inclusive: Literal[True]
    default_threshold: Literal[0.4]
    source_field_thresholds: dict[ScientificEntitySourceField, float]
    entity_type_thresholds: dict[str, float]

    @model_validator(mode="after")
    def validate_policy(self) -> "ThresholdPolicyConfig":
        expected = {
            ScientificEntitySourceField.TITLE: 0.45,
            ScientificEntitySourceField.ABSTRACT: 0.625,
        }
        if self.source_field_thresholds != expected:
            raise ValueError("v0.2c selected policy must remain title>=0.45 / abstract>=0.625")
        if self.entity_type_thresholds:
            raise ValueError("v0.2c selected policy forbids entity-type threshold overrides")
        return self


class ExtractorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["ml_radar_gliner_small_v2_5_semantic_prompt_raw_floor_policy_candidate"]
    version: Literal["0.2c.0"]
    policy_identity: Literal[
        "raw_floor_design_plus_runtime_plus_calibration_selected_trial_plus_threshold_policy"
    ]


class SafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    execute_required_for_writes: Literal[True]
    overwrite_allowed: Literal[False]
    accepted_status_allowed: Literal[False]
    model_inference_allowed: Literal[False]
    threshold_tuning_allowed: Literal[False]
    fresh_heldout_consumption_allowed: Literal[False]
    canonical_truth_mutation_allowed: Literal[False]
    reconcile_input_allowed: Literal[False]
    production_extractor_selected: Literal[False]
    full_corpus_build_authorized: Literal[False]
    publication_allowed: Literal[False]
    future_v02_acceptance_requires_new_disjoint_heldout: Literal[True]


class OutputsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root: str = Field(min_length=1)
    immutable_build_directory: Literal[True]
    encoding: Literal["utf-8"]
    line_ending: Literal["lf"]


class RawFloorPolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[POLICY_CONFIG_SCHEMA_VERSION]
    layer: LayerConfig
    candidate: CandidateConfig
    policy: ThresholdPolicyConfig
    extractor: ExtractorConfig
    safety: SafetyConfig
    outputs: OutputsConfig


class RawFloorPolicyDerivationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[POLICY_DERIVATION_SCHEMA_VERSION] = POLICY_DERIVATION_SCHEMA_VERSION
    build_id: str = Field(min_length=1)
    parent_build_id: str = Field(min_length=1)
    development_package_id: str = Field(min_length=1)
    candidate_id: Literal["scientific-entity-semantic-prompt-raw-floor-extension-v0.2c"]
    calibration_id: str = Field(min_length=1)
    selected_trial_id: str = Field(min_length=1)
    design_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    runtime_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    calibration_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    calibration_selected_policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    parent_extractor_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_extractor_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_threshold: Literal[0.4]
    title_threshold: Literal[0.45]
    abstract_threshold: Literal[0.625]
    entity_type_overrides: dict[str, float]
    input_prediction_count: Literal[1762]
    selected_prediction_count: int = Field(ge=0)
    rejected_prediction_count: int = Field(ge=0)
    calibration_trial_selected_prediction_count: int = Field(ge=0)
    calibration_hard_gates_passed: Literal[True]
    calibration_candidate_promising: Literal[True]
    selected_title_at_candidate_raw_floor: Literal[False]
    mention_id_preserved: Literal[True]
    evidence_id_recomputed: Literal[True]
    confidence_preserved: Literal[True]
    model_inference_executed: Literal[False]
    threshold_tuning_executed: Literal[False]
    fresh_heldout_consumed: Literal[False]
    canonical_truth_mutated: Literal[False]
    may_be_used_as_reconcile_input: Literal[False]
    production_extractor_selected: Literal[False]
    full_corpus_build_authorized: Literal[False]
    publication_ready: Literal[False]
    future_v02_acceptance_requires_new_disjoint_heldout: Literal[True]

    @model_validator(mode="after")
    def validate_counts(self) -> "RawFloorPolicyDerivationManifest":
        if self.selected_prediction_count + self.rejected_prediction_count != self.input_prediction_count:
            raise ValueError("selected + rejected must equal input prediction count")
        if self.selected_prediction_count != self.calibration_trial_selected_prediction_count:
            raise ValueError("materialized selected count must reproduce selected calibration trial")
        if self.entity_type_overrides:
            raise ValueError("entity_type_overrides must remain empty")
        return self


class RawFloorPolicyLineage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[POLICY_LINEAGE_SCHEMA_VERSION] = POLICY_LINEAGE_SCHEMA_VERSION
    build_id: str = Field(min_length=1)
    parent_build_id: str = Field(min_length=1)
    calibration_id: str = Field(min_length=1)
    selected_trial_id: str = Field(min_length=1)
    mention_id: str = Field(min_length=1)
    parent_evidence_id: str = Field(min_length=1)
    candidate_evidence_id: str = Field(min_length=1)


def load_raw_floor_policy_config(path: str | Path) -> RawFloorPolicyConfig:
    path = Path(path)
    try:
        payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeySafeLoader)
    except (OSError, yaml.YAMLError) as exc:
        raise RawFloorPolicyError(str(exc)) from exc
    try:
        return RawFloorPolicyConfig.model_validate(payload)
    except Exception as exc:
        raise RawFloorPolicyError(str(exc)) from exc
