from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from radar_core.contracts.scientific_entity_evidence import ScientificEntitySourceField


POLICY_CONFIG_SCHEMA_VERSION = "scientific_entity_semantic_prompt_policy_v0.2a"
POLICY_DERIVATION_SCHEMA_VERSION = "scientific_entity_semantic_prompt_policy_derivation_v0.2a"
POLICY_LINEAGE_SCHEMA_VERSION = "scientific_entity_semantic_prompt_policy_lineage_v0.2a"


class SemanticPromptPolicyLayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["scientific_entity_semantic_prompt_policy"]
    version: Literal["v0.2a"]
    status: Literal["development_candidate"]
    layer_kind: Literal["derived_policy_filtered_mention_evidence"]


class SemanticPromptPolicyCandidateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: Literal["scientific-entity-semantic-prompt-candidate-v0.2a"]
    design_config_path: str = Field(min_length=1)
    runtime_config_path: str = Field(min_length=1)
    expected_document_count: Literal[72]


class SemanticPromptThresholdPolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_threshold: Literal[0.5]
    threshold_is_inclusive: Literal[True]
    default_threshold: Literal[0.5]
    source_field_thresholds: dict[ScientificEntitySourceField, float]
    entity_type_thresholds: dict[str, float]

    @model_validator(mode="after")
    def validate_policy(self) -> "SemanticPromptThresholdPolicyConfig":
        expected = {
            ScientificEntitySourceField.TITLE: 0.55,
            ScientificEntitySourceField.ABSTRACT: 0.65,
        }
        if self.source_field_thresholds != expected:
            raise ValueError("v0.2a comparison policy must remain title>=0.55 / abstract>=0.65")
        if self.entity_type_thresholds:
            raise ValueError("v0.2a comparison policy forbids entity-type threshold overrides")
        return self


class SemanticPromptPolicyExtractorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["ml_radar_gliner_small_v2_5_semantic_prompt_policy_candidate"]
    version: Literal["0.2a.0"]
    policy_identity: Literal[
        "design_config_plus_runtime_config_plus_frozen_threshold_policy"
    ]


class SemanticPromptPolicySafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execute_required_for_writes: Literal[True]
    overwrite_allowed: Literal[False]
    accepted_status_allowed: Literal[False]
    model_inference_allowed: Literal[False]
    threshold_tuning_allowed: Literal[False]
    canonical_truth_mutation_allowed: Literal[False]
    reconcile_input_allowed: Literal[False]
    production_extractor_selected: Literal[False]
    full_corpus_build_authorized: Literal[False]
    publication_allowed: Literal[False]


class SemanticPromptPolicyOutputsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root: str = Field(min_length=1)
    immutable_build_directory: Literal[True]
    encoding: Literal["utf-8"]
    line_ending: Literal["lf"]


class SemanticPromptPolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[POLICY_CONFIG_SCHEMA_VERSION]
    layer: SemanticPromptPolicyLayerConfig
    candidate: SemanticPromptPolicyCandidateConfig
    policy: SemanticPromptThresholdPolicyConfig
    extractor: SemanticPromptPolicyExtractorConfig
    safety: SemanticPromptPolicySafetyConfig
    outputs: SemanticPromptPolicyOutputsConfig


class SemanticPromptPolicyDerivationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[POLICY_DERIVATION_SCHEMA_VERSION]
    build_id: str = Field(min_length=1)
    parent_build_id: str = Field(min_length=1)
    development_package_id: str = Field(min_length=1)
    candidate_id: Literal["scientific-entity-semantic-prompt-candidate-v0.2a"]
    design_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    runtime_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    parent_extractor_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_extractor_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_threshold: Literal[0.5]
    title_threshold: Literal[0.55]
    abstract_threshold: Literal[0.65]
    entity_type_overrides: dict[str, float]
    input_prediction_count: int = Field(ge=0)
    selected_prediction_count: int = Field(ge=0)
    rejected_prediction_count: int = Field(ge=0)
    mention_id_preserved: Literal[True]
    evidence_id_recomputed: Literal[True]
    confidence_preserved: Literal[True]
    model_inference_executed: Literal[False]
    threshold_tuning_executed: Literal[False]
    canonical_truth_mutated: Literal[False]
    may_be_used_as_reconcile_input: Literal[False]
    production_extractor_selected: Literal[False]
    full_corpus_build_authorized: Literal[False]
    publication_ready: Literal[False]

    @model_validator(mode="after")
    def validate_counts(self) -> "SemanticPromptPolicyDerivationManifest":
        if self.selected_prediction_count + self.rejected_prediction_count != self.input_prediction_count:
            raise ValueError("selected + rejected must equal input prediction count")
        if self.entity_type_overrides:
            raise ValueError("entity_type_overrides must remain empty")
        return self


class SemanticPromptPolicyLineage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[POLICY_LINEAGE_SCHEMA_VERSION]
    build_id: str = Field(min_length=1)
    parent_build_id: str = Field(min_length=1)
    mention_id: str = Field(min_length=1)
    parent_evidence_id: str = Field(min_length=1)
    candidate_evidence_id: str = Field(min_length=1)
