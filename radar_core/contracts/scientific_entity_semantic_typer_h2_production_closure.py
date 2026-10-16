from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

CONFIG_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_production_closure_v0.3"
CLOSURE_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_production_closure_record_v0.3"
MANIFEST_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_production_closure_manifest_v0.3"
SHA256_PATTERN = r"^[0-9a-f]{64}$"

DECISION_ID = "scientific-entity-semantic-typer-h2-production-promotion-decision-v0.3-20261003T121605823276Z"
PROMOTION_ID = "scientific-entity-semantic-typer-h2-production-latest-promotion-v0.3-20261003T121605823276Z"
CLOSURE_ID = "scientific-entity-semantic-typer-h2-production-closure-v0.3-20261003T121605823276Z"
CANDIDATE_BUILD_ID = "scientific-entity-semantic-typer-h2-full-corpus-candidate-v0.3-20261003T121605823276Z"
CANDIDATE_ID = "scientific-entity-semantic-typer-candidate-v0.3-h2-selective-model-over-method"
CANDIDATE_FINGERPRINT = "6d3782fb1f2cc7219b7083bcf381c17c546491425e817c0f5620ff145bfa6966"
MATERIALIZATION_FINGERPRINT = "5c528cab17e2d48c812f6013fbd4f7d966d8e0ccab5eff4e86de166e92641366"
CANONICAL_SHA256 = "3cc6e3c779fee351bcab605ad1b804acf0e4f8365718db96dad398959420b6ff"


class H2ProductionClosureError(ValueError):
    pass


class _UniqueLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueLoader, node: Any, deep: bool = False) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise H2ProductionClosureError(f"Duplicate YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


class LayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["scientific_entity_semantic_typer_h2_production_closure"]
    version: Literal["v0.3"]
    status: Literal["immutable_production_milestone_closure"]
    layer_kind: Literal["scientific_entity_production_lifecycle_closure"]


class LineageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision_id: Literal[DECISION_ID]
    decision_sha256: str = Field(pattern=SHA256_PATTERN)
    decision_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    decision_checksums_sha256: str = Field(pattern=SHA256_PATTERN)
    promotion_id: Literal[PROMOTION_ID]
    promotion_record_sha256: str = Field(pattern=SHA256_PATTERN)
    promotion_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    promotion_post_validation_sha256: str = Field(pattern=SHA256_PATTERN)
    promotion_checksums_sha256: str = Field(pattern=SHA256_PATTERN)
    trusted_latest_pointer_sha256: str = Field(pattern=SHA256_PATTERN)
    candidate_build_id: Literal[CANDIDATE_BUILD_ID]
    candidate_id: Literal[CANDIDATE_ID]
    candidate_fingerprint_sha256: Literal[CANDIDATE_FINGERPRINT]
    materialization_fingerprint_sha256: Literal[MATERIALIZATION_FINGERPRINT]
    candidate_final_mentions_sha256: str = Field(pattern=SHA256_PATTERN)
    final_mention_count: Literal[846264]
    h2_override_count: Literal[33469]
    canonical_sha256: Literal[CANONICAL_SHA256]
    canonical_document_count: Literal[61075]


class InputsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision_root: str
    promotion_root: str
    trusted_latest_path: str


class ExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    output_root: str
    closure_id: Literal[CLOSURE_ID]
    one_shot_execute: Literal[True]
    overwrite_closure_record_allowed: Literal[False]
    plan_writes_output: Literal[False]


class ClosurePolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trusted_production_baseline_established: Literal[True]
    h2_v03_lifecycle_closed: Literal[True]
    future_h2_v03_tuning_allowed: Literal[False]
    historical_production_audit_reference_reuse_for_tuning_allowed: Literal[False]
    future_quality_work_requires_new_version: Literal[True]
    future_full_ner_coverage_audit_requires_fresh_prediction_blind_sample: Literal[True]
    production_latest_remains_active: Literal[True]
    rollback_remains_available: Literal[True]
    publication_authorized: Literal[False]


class SafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    exact_trusted_target_sha_recheck_required: Literal[True]
    exact_trusted_target_line_count_recheck_required: Literal[True]
    trusted_latest_mutation_allowed: Literal[False]
    candidate_mutation_allowed: Literal[False]
    canonical_truth_mutation_allowed: Literal[False]
    model_inference_allowed: Literal[False]
    threshold_tuning_allowed: Literal[False]
    policy_revision_allowed: Literal[False]


class NextStepsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    after_plan: Literal["commit_h2_v03_production_closure_tooling_before_execute"]
    after_execute: Literal["validate_immutable_h2_v03_production_closure"]
    after_validation_pass: Literal["plan_prediction_blind_full_ner_coverage_audit"]


class H2ProductionClosureConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[CONFIG_SCHEMA_VERSION]
    layer: LayerConfig
    lineage: LineageConfig
    inputs: InputsConfig
    execution: ExecutionConfig
    closure_policy: ClosurePolicyConfig
    safety: SafetyConfig
    next_steps: NextStepsConfig


class H2ProductionClosureRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[CLOSURE_SCHEMA_VERSION] = CLOSURE_SCHEMA_VERSION
    closure_id: Literal[CLOSURE_ID]
    lifecycle_status: Literal["closed_as_trusted_production_baseline"]
    decision_id: Literal[DECISION_ID]
    promotion_id: Literal[PROMOTION_ID]
    candidate_build_id: Literal[CANDIDATE_BUILD_ID]
    candidate_id: Literal[CANDIDATE_ID]
    candidate_fingerprint_sha256: Literal[CANDIDATE_FINGERPRINT]
    materialization_fingerprint_sha256: Literal[MATERIALIZATION_FINGERPRINT]
    candidate_final_mentions_sha256: str = Field(pattern=SHA256_PATTERN)
    final_mention_count: Literal[846264]
    h2_override_count: Literal[33469]
    canonical_sha256: Literal[CANONICAL_SHA256]
    canonical_document_count: Literal[61075]
    promotion_decision_validated: Literal[True]
    promotion_executed: Literal[True]
    promotion_validated: Literal[True]
    production_latest_active: Literal[True]
    trusted_target_revalidated_at_closure: Literal[True]
    rollback_path_ready: Literal[True]
    trusted_production_baseline_established: Literal[True]
    h2_v03_lifecycle_closed: Literal[True]
    future_h2_v03_tuning_allowed: Literal[False]
    historical_production_audit_reference_reuse_for_tuning_allowed: Literal[False]
    future_quality_work_requires_new_version: Literal[True]
    future_full_ner_coverage_audit_requires_fresh_prediction_blind_sample: Literal[True]
    full_ner_coverage_audit_started: Literal[False]
    trusted_latest_mutated_in_this_slice: Literal[False]
    candidate_mutated: Literal[False]
    canonical_truth_mutated: Literal[False]
    model_inference_executed: Literal[False]
    threshold_tuning_executed: Literal[False]
    policy_revision_executed: Literal[False]
    publication_authorized: Literal[False]
    next_slice: Literal["plan_prediction_blind_full_ner_coverage_audit"]


class H2ProductionClosureManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[MANIFEST_SCHEMA_VERSION] = MANIFEST_SCHEMA_VERSION
    closure_id: Literal[CLOSURE_ID]
    closure_config_sha256: str = Field(pattern=SHA256_PATTERN)
    decision_id: Literal[DECISION_ID]
    decision_sha256: str = Field(pattern=SHA256_PATTERN)
    decision_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    decision_checksums_sha256: str = Field(pattern=SHA256_PATTERN)
    promotion_id: Literal[PROMOTION_ID]
    promotion_record_sha256: str = Field(pattern=SHA256_PATTERN)
    promotion_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    promotion_post_validation_sha256: str = Field(pattern=SHA256_PATTERN)
    promotion_checksums_sha256: str = Field(pattern=SHA256_PATTERN)
    trusted_latest_pointer_sha256: str = Field(pattern=SHA256_PATTERN)
    trusted_target_sha256: str = Field(pattern=SHA256_PATTERN)
    trusted_target_line_count: Literal[846264]
    parent_lineage_verified: Literal[True]
    trusted_target_revalidated_at_closure: Literal[True]
    production_latest_active: Literal[True]
    rollback_path_ready: Literal[True]
    h2_v03_lifecycle_closed: Literal[True]
    trusted_latest_mutated_in_this_slice: Literal[False]
    candidate_mutated: Literal[False]
    canonical_truth_mutated: Literal[False]
    publication_authorized: Literal[False]
    files: dict[str, str]
    next_slice: Literal["validate_immutable_h2_v03_production_closure"]

    @model_validator(mode="after")
    def validate_file_set(self) -> "H2ProductionClosureManifest":
        if set(self.files) != {"README.md", "closure.json"}:
            raise ValueError("closure manifest files must be exactly README.md + closure.json")
        return self


def load_h2_production_closure_config(path: Path) -> H2ProductionClosureConfig:
    raw = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueLoader)
    if not isinstance(raw, dict):
        raise H2ProductionClosureError("Closure config root must be a mapping")
    return H2ProductionClosureConfig.model_validate(raw)


def canonical_config_sha256(config: H2ProductionClosureConfig) -> str:
    payload = json.dumps(config.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
