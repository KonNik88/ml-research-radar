from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from radar_core.contracts.scientific_entity_evidence import (
    ScientificEntityEvidenceManifest,
    ScientificEntitySourceField,
    build_extractor_fingerprint,
    sha256_text,
)
from radar_core.contracts.scientific_entity_gliner_calibration import (
    ScientificEntityCalibrationProfileName,
    ScientificEntityThresholdPolicy,
)
from radar_core.entities.scientific_entity_gliner_frozen_policy import (
    ScientificEntityGLiNERFrozenPolicyError,
    build_policy_filtered_extractor_descriptor,
    materialize_policy_filtered_mentions,
)

CONFIG_SCHEMA_VERSION = "scientific_entity_gliner_heldout_frozen_policy_config_v0.1"
FROZEN_POLICY = ScientificEntityThresholdPolicy(
    default_threshold=0.50,
    source_field_thresholds={
        ScientificEntitySourceField.TITLE: 0.55,
        ScientificEntitySourceField.ABSTRACT: 0.65,
    },
    entity_type_thresholds={},
)


class LayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["scientific_entity_gliner_heldout_frozen_policy"]
    version: Literal["v0.1"]
    status: Literal["heldout_frozen_candidate"]
    layer_kind: Literal["derived_policy_filtered_mention_evidence"]
    description: str = Field(min_length=1)


class ExtractorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["ml_radar_gliner_small_v2_5_heldout_frozen_policy"]
    version: Literal["0.1.0"]
    environment_lock_path: str = Field(min_length=1)


class HeldoutConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_id: str = Field(min_length=1)
    expected_document_count: Literal[48]
    prepared_dir: str = Field(min_length=1)
    canonical_sample_file: Literal["canonical_documents.sample.jsonl"]
    preparation_manifest_file: Literal["preparation_manifest.json"]


class ParentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    build_id: str = Field(min_length=1)
    build_root: str = Field(min_length=1)
    expected_input_prediction_count: int = Field(ge=1)
    expected_selected_prediction_count: int = Field(ge=1)
    expected_rejected_prediction_count: int = Field(ge=0)
    expected_raw_threshold: Literal[0.5]

    @model_validator(mode="after")
    def validate_counts(self) -> "ParentConfig":
        if self.expected_input_prediction_count != self.expected_selected_prediction_count + self.expected_rejected_prediction_count:
            raise ValueError("selected + rejected must equal input")
        return self


class PolicyOriginConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    calibration_id: str = Field(min_length=1)
    calibration_root: str = Field(min_length=1)
    selected_profile: Literal[ScientificEntityCalibrationProfileName.BALANCED]
    selected_trial_id: str = Field(min_length=1)
    input_threshold: Literal[0.5]
    threshold_is_inclusive: Literal[True]
    policy: ScientificEntityThresholdPolicy

    @model_validator(mode="after")
    def validate_policy(self) -> "PolicyOriginConfig":
        if self.policy != FROZEN_POLICY:
            raise ValueError("held-out v0.1 must use frozen title>=0.55 / abstract>=0.65 policy")
        return self


class SafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed_build_statuses: list[Literal["fixture", "candidate"]]
    accepted_status_may_be_emitted: Literal[False]
    overwrite_allowed: Literal[False]
    arbitrary_threshold_override_allowed: Literal[False]
    model_inference_allowed: Literal[False]
    model_or_tokenizer_download_allowed: Literal[False]
    provider_api_allowed: Literal[False]
    canonical_truth_mutation_allowed: Literal[False]
    reconcile_input_allowed: Literal[False]
    full_corpus_build_authorized: Literal[False]
    heldout_reference_mutation_allowed: Literal[False]
    publication_allowed: Literal[False]


class OutputsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root: str = Field(min_length=1)
    encoding: Literal["utf-8"]
    line_ending: Literal["lf"]


class ScientificEntityGLiNERHeldoutPolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[CONFIG_SCHEMA_VERSION]
    layer: LayerConfig
    extractor: ExtractorConfig
    heldout: HeldoutConfig
    parent: ParentConfig
    policy_origin: PolicyOriginConfig
    safety: SafetyConfig
    outputs: OutputsConfig


class _UniqueKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ScientificEntityGLiNERFrozenPolicyError(f"duplicate YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


def canonical_semantic_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_config(path: Path) -> ScientificEntityGLiNERHeldoutPolicyConfig:
    payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeySafeLoader)
    if not isinstance(payload, dict):
        raise ScientificEntityGLiNERFrozenPolicyError("config must be a mapping")
    return ScientificEntityGLiNERHeldoutPolicyConfig.model_validate(payload)


def config_sha256(config: ScientificEntityGLiNERHeldoutPolicyConfig) -> str:
    return sha256_text(canonical_semantic_json(config.model_dump(mode="json")))


def build_descriptor(*, config: ScientificEntityGLiNERHeldoutPolicyConfig, parent_manifest: ScientificEntityEvidenceManifest, project_root: Path):
    return build_policy_filtered_extractor_descriptor(
        extractor_name=config.extractor.name,
        extractor_version=config.extractor.version,
        environment_lock_path=config.extractor.environment_lock_path,
        config_sha256=config_sha256(config),
        parent_manifest=parent_manifest,
        project_root=project_root,
    )


def materialize(*, parent_mentions, config: ScientificEntityGLiNERHeldoutPolicyConfig, build_id: str, candidate_extractor_fingerprint: str):
    return materialize_policy_filtered_mentions(
        parent_mentions=parent_mentions,
        policy=config.policy_origin.policy,
        input_threshold=config.policy_origin.input_threshold,
        expected_input_prediction_count=config.parent.expected_input_prediction_count,
        expected_selected_prediction_count=config.parent.expected_selected_prediction_count,
        expected_rejected_prediction_count=config.parent.expected_rejected_prediction_count,
        parent_build_id=config.parent.build_id,
        build_id=build_id,
        candidate_extractor_fingerprint=candidate_extractor_fingerprint,
    )
