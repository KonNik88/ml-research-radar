from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

CONFIG_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_production_latest_promotion_v0.3"
POINTER_SCHEMA_VERSION = "scientific_entity_production_latest_pointer_v0.3"
PROMOTION_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_production_latest_promotion_record_v0.3"
PREVIOUS_STATE_SCHEMA_VERSION = "scientific_entity_production_previous_latest_state_v0.3"
POSTVALIDATION_SCHEMA_VERSION = "scientific_entity_production_latest_postvalidation_v0.3"
MANIFEST_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_production_latest_promotion_manifest_v0.3"
ROLLBACK_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_production_latest_rollback_record_v0.3"
SHA256_PATTERN = r"^[0-9a-f]{64}$"

DECISION_ID = "scientific-entity-semantic-typer-h2-production-promotion-decision-v0.3-20261003T121605823276Z"
CANDIDATE_BUILD_ID = "scientific-entity-semantic-typer-h2-full-corpus-candidate-v0.3-20261003T121605823276Z"
CANDIDATE_ID = "scientific-entity-semantic-typer-candidate-v0.3-h2-selective-model-over-method"
CANDIDATE_FINGERPRINT = "6d3782fb1f2cc7219b7083bcf381c17c546491425e817c0f5620ff145bfa6966"
MATERIALIZATION_FINGERPRINT = "5c528cab17e2d48c812f6013fbd4f7d966d8e0ccab5eff4e86de166e92641366"
CANONICAL_SHA256 = "3cc6e3c779fee351bcab605ad1b804acf0e4f8365718db96dad398959420b6ff"
PROMOTION_ID = "scientific-entity-semantic-typer-h2-production-latest-promotion-v0.3-20261003T121605823276Z"
ROLLBACK_ID = "scientific-entity-semantic-typer-h2-production-latest-rollback-v0.3-20261003T121605823276Z"


class H2ProductionLatestPromotionError(ValueError):
    pass


class _UniqueLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueLoader, node: Any, deep: bool = False) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise H2ProductionLatestPromotionError(f"Duplicate YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


class LayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["scientific_entity_semantic_typer_h2_production_latest_promotion"]
    version: Literal["v0.3"]
    status: Literal["controlled_one_shot_trusted_latest_promotion"]
    layer_kind: Literal["scientific_entity_production_trusted_state"]


class LineageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision_id: Literal[DECISION_ID]
    decision_config_canonical_sha256: str = Field(pattern=SHA256_PATTERN)
    candidate_build_id: Literal[CANDIDATE_BUILD_ID]
    candidate_id: Literal[CANDIDATE_ID]
    candidate_fingerprint_sha256: Literal[CANDIDATE_FINGERPRINT]
    materialization_fingerprint_sha256: Literal[MATERIALIZATION_FINGERPRINT]
    candidate_final_mentions_sha256: str = Field(pattern=SHA256_PATTERN)
    final_mention_count: int = Field(gt=0)
    h2_override_count: int = Field(ge=0)
    canonical_sha256: Literal[CANONICAL_SHA256]
    canonical_document_count: Literal[61075]


class InputsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision_config_path: str
    decision_root: str
    candidate_dir: str


class TrustedLatestConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root: str
    pointer_name: Literal["latest.json"]
    pointer_targets_immutable_candidate_artifact: Literal[True]
    promoted_candidate_artifact_retention_required: Literal[True]
    atomic_pointer_replace_required: Literal[True]
    first_promotion_may_have_no_previous_latest: Literal[True]
    previous_latest_state_snapshot_required: Literal[True]


class ExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    output_root: str
    promotion_id: Literal[PROMOTION_ID]
    rollback_output_root: str
    rollback_id: Literal[ROLLBACK_ID]
    one_shot_execute: Literal[True]
    overwrite_promotion_record_allowed: Literal[False]
    plan_writes_output: Literal[False]


class SafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    exact_candidate_sha_recheck_required_in_plan: Literal[True]
    exact_candidate_sha_recheck_required_immediately_before_mutation: Literal[True]
    previous_latest_backup_required_if_present: Literal[True]
    absent_previous_latest_bootstrap_snapshot_required: Literal[True]
    rollback_tooling_required_before_promotion: Literal[True]
    post_promotion_validation_required: Literal[True]
    candidate_mutation_allowed: Literal[False]
    canonical_truth_mutation_allowed: Literal[False]
    model_inference_allowed: Literal[False]
    threshold_tuning_allowed: Literal[False]
    policy_revision_allowed: Literal[False]
    publication_authorized: Literal[False]


class NextStepsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    after_plan: Literal["commit_h2_production_latest_promotion_tooling_before_execute"]
    after_execute: Literal["validate_h2_production_latest_promotion"]
    after_validation_pass: Literal["close_h2_v03_production_promotion_and_plan_full_ner_coverage_audit"]
    after_validation_fail: Literal["rollback_or_fix_h2_production_latest_promotion"]


class H2ProductionLatestPromotionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[CONFIG_SCHEMA_VERSION]
    layer: LayerConfig
    lineage: LineageConfig
    inputs: InputsConfig
    trusted_latest: TrustedLatestConfig
    execution: ExecutionConfig
    safety: SafetyConfig
    next_steps: NextStepsConfig


class ScientificEntityProductionLatestPointer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[POINTER_SCHEMA_VERSION] = POINTER_SCHEMA_VERSION
    state: Literal["trusted_latest"] = "trusted_latest"
    promotion_id: Literal[PROMOTION_ID]
    decision_id: Literal[DECISION_ID]
    candidate_build_id: Literal[CANDIDATE_BUILD_ID]
    candidate_id: Literal[CANDIDATE_ID]
    candidate_fingerprint_sha256: Literal[CANDIDATE_FINGERPRINT]
    materialization_fingerprint_sha256: Literal[MATERIALIZATION_FINGERPRINT]
    candidate_final_mentions_sha256: str = Field(pattern=SHA256_PATTERN)
    final_mention_count: int = Field(gt=0)
    h2_override_count: int = Field(ge=0)
    canonical_sha256: Literal[CANONICAL_SHA256]
    canonical_document_count: Literal[61075]
    artifact_path: str = Field(min_length=1)
    promotion_record_path: str = Field(min_length=1)
    artifact_is_immutable_candidate: Literal[True]
    artifact_retention_required: Literal[True]
    post_promotion_validation_required: Literal[True]
    publication_authorized: Literal[False]


class PreviousLatestState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[PREVIOUS_STATE_SCHEMA_VERSION] = PREVIOUS_STATE_SCHEMA_VERSION
    previous_latest_exists: bool
    previous_latest_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    previous_latest_bytes_base64: str | None = None
    rollback_action: Literal["remove_latest_pointer", "restore_previous_latest_pointer"]

    @model_validator(mode="after")
    def validate_state(self) -> "PreviousLatestState":
        if self.previous_latest_exists:
            if self.previous_latest_sha256 is None or self.previous_latest_bytes_base64 is None:
                raise ValueError("existing previous latest requires SHA and byte backup")
            raw = base64.b64decode(self.previous_latest_bytes_base64.encode("ascii"), validate=True)
            if hashlib.sha256(raw).hexdigest() != self.previous_latest_sha256:
                raise ValueError("previous latest byte backup SHA mismatch")
            if self.rollback_action != "restore_previous_latest_pointer":
                raise ValueError("existing previous latest requires restore rollback")
        else:
            if self.previous_latest_sha256 is not None or self.previous_latest_bytes_base64 is not None:
                raise ValueError("absent previous latest cannot contain byte backup")
            if self.rollback_action != "remove_latest_pointer":
                raise ValueError("first promotion rollback must remove latest pointer")
        return self


class H2ProductionLatestPromotionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[PROMOTION_SCHEMA_VERSION] = PROMOTION_SCHEMA_VERSION
    promotion_id: Literal[PROMOTION_ID]
    decision_id: Literal[DECISION_ID]
    candidate_build_id: Literal[CANDIDATE_BUILD_ID]
    candidate_final_mentions_sha256: str = Field(pattern=SHA256_PATTERN)
    final_mention_count: int = Field(gt=0)
    h2_override_count: int = Field(ge=0)
    canonical_sha256: Literal[CANONICAL_SHA256]
    canonical_document_count: Literal[61075]
    promotion_decision_validated: Literal[True]
    production_latest_promotion_authorized: Literal[True]
    previous_latest_exists: bool
    previous_latest_state_snapshotted: Literal[True]
    promotion_executed: Literal[True]
    trusted_latest_pointer_updated: Literal[True]
    post_promotion_validation_passed: Literal[True]
    exact_candidate_sha_verified_immediately_before_mutation: Literal[True]
    rollback_path_ready: Literal[True]
    rollback_command: str = Field(min_length=1)
    candidate_mutated: Literal[False]
    canonical_truth_mutated: Literal[False]
    model_inference_executed: Literal[False]
    threshold_tuning_executed: Literal[False]
    policy_revision_executed: Literal[False]
    publication_authorized: Literal[False]
    next_slice: Literal["validate_h2_production_latest_promotion"]


class H2ProductionLatestPostValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[POSTVALIDATION_SCHEMA_VERSION] = POSTVALIDATION_SCHEMA_VERSION
    promotion_id: Literal[PROMOTION_ID]
    latest_pointer_exists: Literal[True]
    latest_pointer_matches_expected: Literal[True]
    target_artifact_exists: Literal[True]
    target_sha256_matches_authorized: Literal[True]
    target_line_count_matches_expected: Literal[True]
    target_sha256: str = Field(pattern=SHA256_PATTERN)
    target_line_count: int = Field(gt=0)
    post_promotion_validation_passed: Literal[True]


class H2ProductionLatestPromotionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[MANIFEST_SCHEMA_VERSION] = MANIFEST_SCHEMA_VERSION
    promotion_id: Literal[PROMOTION_ID]
    promotion_config_sha256: str = Field(pattern=SHA256_PATTERN)
    decision_id: Literal[DECISION_ID]
    candidate_build_id: Literal[CANDIDATE_BUILD_ID]
    candidate_final_mentions_sha256: str = Field(pattern=SHA256_PATTERN)
    final_mention_count: int = Field(gt=0)
    canonical_sha256: Literal[CANONICAL_SHA256]
    canonical_document_count: Literal[61075]
    latest_pointer_path: str
    latest_pointer_sha256: str = Field(pattern=SHA256_PATTERN)
    previous_latest_exists: bool
    previous_latest_state_sha256: str = Field(pattern=SHA256_PATTERN)
    promotion_executed: Literal[True]
    trusted_latest_pointer_updated: Literal[True]
    post_promotion_validation_passed: Literal[True]
    rollback_path_ready: Literal[True]
    candidate_mutated: Literal[False]
    canonical_truth_mutated: Literal[False]
    publication_authorized: Literal[False]
    files: dict[str, str]
    next_slice: Literal["validate_h2_production_latest_promotion"]

    @model_validator(mode="after")
    def validate_file_set(self) -> "H2ProductionLatestPromotionManifest":
        expected = {"README.md", "installed_latest.json", "post_validation.json", "previous_latest_state.json", "promotion.json"}
        if set(self.files) != expected:
            raise ValueError("promotion manifest file set drifted")
        return self


class H2ProductionLatestRollbackRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[ROLLBACK_SCHEMA_VERSION] = ROLLBACK_SCHEMA_VERSION
    rollback_id: Literal[ROLLBACK_ID]
    promotion_id: Literal[PROMOTION_ID]
    previous_latest_exists: bool
    rollback_action: Literal["remove_latest_pointer", "restore_previous_latest_pointer"]
    current_promoted_pointer_verified_before_rollback: Literal[True]
    rollback_executed: Literal[True]
    rollback_postcheck_passed: Literal[True]
    trusted_latest_exists_after_rollback: bool
    canonical_truth_mutated: Literal[False]
    candidate_mutated: Literal[False]


def load_h2_production_latest_promotion_config(path: Path) -> H2ProductionLatestPromotionConfig:
    payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueLoader)
    if not isinstance(payload, dict):
        raise H2ProductionLatestPromotionError("Production-latest promotion config must be a mapping")
    return H2ProductionLatestPromotionConfig.model_validate(payload)


def canonical_config_sha256(config: H2ProductionLatestPromotionConfig) -> str:
    raw = json.dumps(config.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
