from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

CONFIG_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_production_promotion_decision_v0.3"
DECISION_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_production_promotion_decision_record_v0.3"
MANIFEST_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_production_promotion_decision_manifest_v0.3"
SHA256_PATTERN = r"^[0-9a-f]{64}$"

AUTHORIZATION_ID = "scientific-entity-semantic-typer-h2-production-authorization-v0.3-3cc6e3c779fee351-6d3782fb"
CANDIDATE_BUILD_ID = "scientific-entity-semantic-typer-h2-full-corpus-candidate-v0.3-20261003T121605823276Z"
REFERENCE_ID = "scientific-entity-semantic-typer-h2-production-audit-reference-v0.3-20261003T121605823276Z"
EVALUATION_ID = "scientific-entity-semantic-typer-h2-production-audit-evaluation-v0.3-20261003T121605823276Z"
DECISION_ID = "scientific-entity-semantic-typer-h2-production-promotion-decision-v0.3-20261003T121605823276Z"
CANDIDATE_ID = "scientific-entity-semantic-typer-candidate-v0.3-h2-selective-model-over-method"
CANDIDATE_FINGERPRINT = "6d3782fb1f2cc7219b7083bcf381c17c546491425e817c0f5620ff145bfa6966"
MATERIALIZATION_FINGERPRINT = "5c528cab17e2d48c812f6013fbd4f7d966d8e0ccab5eff4e86de166e92641366"
CANONICAL_SHA256 = "3cc6e3c779fee351bcab605ad1b804acf0e4f8365718db96dad398959420b6ff"


class H2ProductionPromotionDecisionError(ValueError):
    pass


class _UniqueLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueLoader, node: Any, deep: bool = False) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise H2ProductionPromotionDecisionError(f"Duplicate YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


class LayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["scientific_entity_semantic_typer_h2_production_promotion_decision"]
    version: Literal["v0.3"]
    status: Literal["immutable_one_shot_controlled_promotion_authorization"]
    layer_kind: Literal["scientific_entity_production_promotion_decision"]


class LineageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    authorization_id: Literal[AUTHORIZATION_ID]
    authorization_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    authorization_record_sha256: str = Field(pattern=SHA256_PATTERN)
    candidate_build_id: Literal[CANDIDATE_BUILD_ID]
    candidate_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    candidate_summary_sha256: str = Field(pattern=SHA256_PATTERN)
    candidate_final_mentions_sha256: str = Field(pattern=SHA256_PATTERN)
    reference_id: Literal[REFERENCE_ID]
    reference_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    reference_summary_sha256: str = Field(pattern=SHA256_PATTERN)
    reference_annotations_sha256: str = Field(pattern=SHA256_PATTERN)
    evaluation_id: Literal[EVALUATION_ID]
    evaluation_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    evaluation_summary_sha256: str = Field(pattern=SHA256_PATTERN)
    evaluation_gate_results_sha256: str = Field(pattern=SHA256_PATTERN)
    evaluation_case_evaluations_sha256: str = Field(pattern=SHA256_PATTERN)
    candidate_id: Literal[CANDIDATE_ID]
    candidate_fingerprint_sha256: Literal[CANDIDATE_FINGERPRINT]
    materialization_fingerprint_sha256: Literal[MATERIALIZATION_FINGERPRINT]
    canonical_sha256: Literal[CANONICAL_SHA256]
    canonical_document_count: Literal[61075]


class DecisionPrerequisitesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    authorization_made_required: Literal[True]
    full_corpus_candidate_build_authorized_required: Literal[True]
    exact_candidate_build_required: Literal[True]
    exact_candidate_final_mentions_sha256_required: Literal[True]
    frozen_reference_required: Literal[True]
    evaluation_all_hard_gates_pass_required: Literal[True]
    evaluation_gate_verdict_required: Literal["pass_h2_production_audit_gate"]
    expected_gate_count: Literal[11]
    threshold_revision_forbidden: Literal[True]
    model_inference_in_decision_forbidden: Literal[True]
    threshold_tuning_forbidden: Literal[True]
    policy_revision_forbidden: Literal[True]
    candidate_mutation_forbidden: Literal[True]
    canonical_truth_mutation_forbidden: Literal[True]


class PromotionBoundaryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    authorization_scope: Literal["one_controlled_candidate_to_trusted_latest_promotion"]
    authorized_promotion_count: Literal[1]
    exact_candidate_build_required_at_promotion: Literal[True]
    exact_candidate_final_mentions_sha256_required_at_promotion: Literal[True]
    backup_previous_trusted_latest_required: Literal[True]
    rollback_path_required: Literal[True]
    post_promotion_validation_required: Literal[True]
    promotion_execution_allowed_in_this_slice: Literal[False]
    latest_overwrite_allowed_in_this_slice: Literal[False]
    canonical_truth_mutation_allowed: Literal[False]
    publication_authorized: Literal[False]


class ExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    output_root: Literal["data/entities/scientific_entity_semantic_typer_h2_production_promotion_decision/v0.3"]
    decision_id: Literal[DECISION_ID]
    one_shot_execute: Literal[True]
    overwrite_allowed: Literal[False]
    plan_writes_output: Literal[False]
    plan_makes_promotion_decision: Literal[False]
    plan_authorizes_production_latest_promotion: Literal[False]


class SafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_prediction_files_read_in_this_slice: Literal[False]
    model_inference_executed_in_this_slice: Literal[False]
    evaluation_recomputed_in_this_slice: Literal[False]
    threshold_tuning_executed: Literal[False]
    policy_revision_executed: Literal[False]
    candidate_mutated: Literal[False]
    canonical_truth_mutated: Literal[False]
    promotion_executed: Literal[False]
    latest_overwritten: Literal[False]
    publication_authorized: Literal[False]


class NextStepsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    after_plan: Literal["commit_h2_production_promotion_decision_tooling_before_execute"]
    after_execute: Literal["validate_immutable_h2_production_promotion_decision"]
    after_validation_pass: Literal["build_controlled_h2_production_latest_promotion_tooling"]
    after_validation_fail: Literal["fix_h2_production_promotion_decision_artifact"]


class H2ProductionPromotionDecisionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[CONFIG_SCHEMA_VERSION]
    layer: LayerConfig
    lineage: LineageConfig
    decision_prerequisites: DecisionPrerequisitesConfig
    promotion_boundary: PromotionBoundaryConfig
    execution: ExecutionConfig
    safety: SafetyConfig
    next_steps: NextStepsConfig


class H2ProductionPromotionDecisionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[DECISION_SCHEMA_VERSION] = DECISION_SCHEMA_VERSION
    decision_id: Literal[DECISION_ID]
    decision: Literal["authorize_controlled_h2_production_latest_promotion"]
    authorization_id: Literal[AUTHORIZATION_ID]
    candidate_build_id: Literal[CANDIDATE_BUILD_ID]
    reference_id: Literal[REFERENCE_ID]
    evaluation_id: Literal[EVALUATION_ID]
    candidate_id: Literal[CANDIDATE_ID]
    candidate_fingerprint_sha256: Literal[CANDIDATE_FINGERPRINT]
    materialization_fingerprint_sha256: Literal[MATERIALIZATION_FINGERPRINT]
    canonical_sha256: Literal[CANONICAL_SHA256]
    canonical_document_count: Literal[61075]
    candidate_final_mentions_sha256: str = Field(pattern=SHA256_PATTERN)
    evaluation_gate_count: Literal[11]
    evaluation_all_hard_gates_pass: Literal[True]
    evaluation_gate_verdict: Literal["pass_h2_production_audit_gate"]
    thresholds_revised_after_annotation: Literal[False]
    promotion_decision_made: Literal[True]
    production_latest_promotion_authorized: Literal[True]
    authorization_scope: Literal["one_controlled_candidate_to_trusted_latest_promotion"]
    authorized_promotion_count: Literal[1]
    exact_candidate_final_mentions_sha256_required_at_promotion: Literal[True]
    backup_previous_trusted_latest_required: Literal[True]
    rollback_path_required: Literal[True]
    post_promotion_validation_required: Literal[True]
    candidate_prediction_files_read_in_this_slice: Literal[False]
    model_inference_executed: Literal[False]
    threshold_tuning_executed: Literal[False]
    policy_revision_executed: Literal[False]
    candidate_mutated: Literal[False]
    canonical_truth_mutated: Literal[False]
    promotion_executed: Literal[False]
    latest_overwritten: Literal[False]
    publication_authorized: Literal[False]
    next_slice: Literal["build_controlled_h2_production_latest_promotion_tooling"]


class H2ProductionPromotionDecisionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[MANIFEST_SCHEMA_VERSION] = MANIFEST_SCHEMA_VERSION
    decision_id: Literal[DECISION_ID]
    decision_config_sha256: str = Field(pattern=SHA256_PATTERN)
    authorization_id: Literal[AUTHORIZATION_ID]
    authorization_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    authorization_record_sha256: str = Field(pattern=SHA256_PATTERN)
    candidate_build_id: Literal[CANDIDATE_BUILD_ID]
    candidate_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    candidate_summary_sha256: str = Field(pattern=SHA256_PATTERN)
    candidate_final_mentions_sha256: str = Field(pattern=SHA256_PATTERN)
    reference_id: Literal[REFERENCE_ID]
    reference_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    reference_summary_sha256: str = Field(pattern=SHA256_PATTERN)
    reference_annotations_sha256: str = Field(pattern=SHA256_PATTERN)
    evaluation_id: Literal[EVALUATION_ID]
    evaluation_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    evaluation_summary_sha256: str = Field(pattern=SHA256_PATTERN)
    evaluation_gate_results_sha256: str = Field(pattern=SHA256_PATTERN)
    evaluation_case_evaluations_sha256: str = Field(pattern=SHA256_PATTERN)
    candidate_id: Literal[CANDIDATE_ID]
    candidate_fingerprint_sha256: Literal[CANDIDATE_FINGERPRINT]
    materialization_fingerprint_sha256: Literal[MATERIALIZATION_FINGERPRINT]
    canonical_sha256: Literal[CANONICAL_SHA256]
    canonical_document_count: Literal[61075]
    parent_lineage_verified: Literal[True]
    evaluation_gate_count: Literal[11]
    evaluation_all_hard_gates_pass: Literal[True]
    promotion_decision_made: Literal[True]
    production_latest_promotion_authorized: Literal[True]
    candidate_prediction_files_read_in_this_slice: Literal[False]
    model_inference_executed: Literal[False]
    threshold_tuning_executed: Literal[False]
    policy_revision_executed: Literal[False]
    candidate_mutated: Literal[False]
    canonical_truth_mutated: Literal[False]
    promotion_executed: Literal[False]
    latest_overwritten: Literal[False]
    publication_authorized: Literal[False]
    files: dict[str, str]
    next_slice: Literal["validate_immutable_h2_production_promotion_decision"]

    @model_validator(mode="after")
    def validate_file_set(self) -> "H2ProductionPromotionDecisionManifest":
        if set(self.files) != {"README.md", "decision.json"}:
            raise ValueError("manifest files must be exactly README.md + decision.json")
        return self


def load_h2_production_promotion_decision_config(path: Path) -> H2ProductionPromotionDecisionConfig:
    payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueLoader)
    if not isinstance(payload, dict):
        raise H2ProductionPromotionDecisionError("Promotion-decision config must be a mapping")
    return H2ProductionPromotionDecisionConfig.model_validate(payload)


def canonical_config_sha256(config: H2ProductionPromotionDecisionConfig) -> str:
    raw = json.dumps(config.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
