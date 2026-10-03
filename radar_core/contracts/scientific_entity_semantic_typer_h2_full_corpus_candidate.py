from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from radar_core.contracts.scientific_entity_evidence import (
    ScientificEntitySourceField,
    ScientificEntityType,
)

CONFIG_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_full_corpus_candidate_v0.3"
CASE_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_full_corpus_case_v0.3"
FINAL_MENTION_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_full_corpus_final_mention_v0.3"
OVERRIDE_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_full_corpus_override_v0.3"
SUMMARY_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_full_corpus_summary_v0.3"
MANIFEST_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_full_corpus_manifest_v0.3"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
EVIDENCE_ID_PATTERN = r"^evidence:[0-9a-f]{32}$"
MENTION_ID_PATTERN = r"^mention:[0-9a-f]{32}$"


class H2FullCorpusCandidateError(ValueError):
    """Raised when the authorized H2 full-corpus candidate cannot be built safely."""


class _UniqueLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueLoader, node: Any, deep: bool = False) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise H2FullCorpusCandidateError(f"Duplicate YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


class LayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["scientific_entity_semantic_typer_h2_full_corpus_candidate"]
    version: Literal["v0.3"]
    status: Literal["authorized_timestamped_candidate_materialization"]
    layer_kind: Literal["derived_scientific_entity_candidate_materialization"]


class AuthorizationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    authorization_id: Literal[
        "scientific-entity-semantic-typer-h2-production-authorization-v0.3-3cc6e3c779fee351-6d3782fb"
    ]
    authorization_config_path: Literal[
        "configs/scientific_entity_semantic_typer_h2_production_authorization_v0.3.yaml"
    ]
    authorization_config_sha256: Literal[
        "78ea64454059cffff1be2808c62b1170238db5414cfe451c52d34d5f67c81ded"
    ]
    expected_authorization_validation_total_checks: Literal[30]
    expected_authorization_validation_required_failed_count: Literal[0]
    authorized_candidate_build_count: Literal[1]


class CanonicalSnapshotConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: Literal["data/analytics/reconciled/canonical_documents.jsonl"]
    sha256: Literal[
        "3cc6e3c779fee351bcab605ad1b804acf0e4f8365718db96dad398959420b6ff"
    ]
    document_count: Literal[61075]
    canonical_contract: Literal["CanonicalDocument"]


class FrozenRuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    runtime_config_path: Literal[
        "configs/scientific_entity_gliner_semantic_prompt_raw_floor_candidate_v0.2c.yaml"
    ]
    runtime_config_sha256: Literal[
        "b9b544194183e1cdf60a4632735acb6fe24788829bd1c75941293c5cd4360da6"
    ]
    baseline_policy_config_path: Literal[
        "configs/scientific_entity_semantic_prompt_raw_floor_policy_v0.2c.yaml"
    ]
    baseline_policy_config_sha256: Literal[
        "9ad8d4f6728e49e04ed4bdc4cec6f4d2a23db82d55af71b4f71f33dabf84f62c"
    ]
    semantic_typer_config_path: Literal[
        "configs/scientific_entity_semantic_typer_candidate_v0.3.yaml"
    ]
    semantic_typer_config_sha256: Literal[
        "1d7972d965f88743fc6bc419f22e751aa94218984288974c247cdbe884712c36"
    ]
    semantic_typer_fingerprint_sha256: Literal[
        "3b495a25f1f4a80f435d983db9002e8d324427fc427ea1b27433062c64708bce"
    ]


class FrozenH2Config(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: Literal[
        "scientific-entity-semantic-typer-candidate-v0.3-h2-selective-model-over-method"
    ]
    candidate_fingerprint_sha256: Literal[
        "6d3782fb1f2cc7219b7083bcf381c17c546491425e817c0f5620ff145bfa6966"
    ]
    baseline_type: Literal[ScientificEntityType.METHOD]
    semantic_typer_type: Literal[ScientificEntityType.MODEL]
    score_field: Literal["score_margin"]
    operator: Literal[">="]
    threshold: Literal[0.1]
    preserve_baseline_otherwise: Literal[True]
    semantic_typer_scope: Literal[
        "baseline_method_mentions_only_semantics_preserving_optimization"
    ]
    span_mutation_allowed: Literal[False]
    new_span_generation_allowed: Literal[False]
    taxonomy_changes_allowed: Literal[False]


class ExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    output_root: Literal[
        "data/entities/scientific_entity_semantic_typer_h2_full_corpus_candidate/v0.3"
    ]
    build_id_prefix: Literal[
        "scientific-entity-semantic-typer-h2-full-corpus-candidate-v0.3"
    ]
    one_successful_build_per_authorization: Literal[True]
    immutable_output: Literal[True]
    overwrite_allowed: Literal[False]
    plan_writes_output: Literal[False]
    plan_runs_model_inference: Literal[False]
    stream_outputs: Literal[True]
    progress_every_documents: int = Field(ge=1)


class SafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    exact_authorized_canonical_snapshot_required: Literal[True]
    human_reference_mentions_allowed: Literal[False]
    threshold_tuning_allowed: Literal[False]
    policy_revision_allowed: Literal[False]
    canonical_truth_mutation_allowed: Literal[False]
    production_latest_promotion_authorized: Literal[False]
    latest_overwrite_allowed: Literal[False]
    publication_authorized: Literal[False]
    candidate_validation_required_before_promotion: Literal[True]
    separate_promotion_decision_required: Literal[True]


class NextStepsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    after_plan: Literal["commit_h2_full_corpus_candidate_tooling_before_execute"]
    after_execute: Literal["validate_h2_full_corpus_candidate_materialization"]
    after_validation: Literal["review_h2_full_corpus_candidate_and_build_promotion_gate"]


class H2FullCorpusCandidateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[CONFIG_SCHEMA_VERSION]
    layer: LayerConfig
    authorization: AuthorizationConfig
    canonical_snapshot: CanonicalSnapshotConfig
    frozen_runtime: FrozenRuntimeConfig
    frozen_h2: FrozenH2Config
    execution: ExecutionConfig
    safety: SafetyConfig
    next_steps: NextStepsConfig

    @model_validator(mode="after")
    def validate_boundary(self) -> "H2FullCorpusCandidateConfig":
        if self.safety.production_latest_promotion_authorized:
            raise ValueError("Candidate build must not authorize production latest promotion")
        if self.safety.latest_overwrite_allowed:
            raise ValueError("Candidate build must not allow latest overwrite")
        if self.safety.canonical_truth_mutation_allowed:
            raise ValueError("Candidate build must not mutate canonical truth")
        if self.safety.human_reference_mentions_allowed:
            raise ValueError("Candidate build must not consume held-out reference labels")
        return self


class H2FullCorpusCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[CASE_SCHEMA_VERSION] = CASE_SCHEMA_VERSION
    case_id: str = Field(min_length=1)
    canonical_id: str = Field(min_length=1)
    source_field: ScientificEntitySourceField
    source_text_sha256: str = Field(pattern=SHA256_PATTERN)
    baseline_prediction_evidence_id: str = Field(pattern=EVIDENCE_ID_PATTERN)
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    surface_text: str = Field(min_length=1)
    baseline_entity_type: Literal[ScientificEntityType.METHOD]
    baseline_confidence_score: float = Field(ge=0.0, le=1.0)
    left_context: str
    right_context: str


class H2FullCorpusOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[OVERRIDE_SCHEMA_VERSION] = OVERRIDE_SCHEMA_VERSION
    build_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    baseline_prediction_evidence_id: str = Field(pattern=EVIDENCE_ID_PATTERN)
    canonical_id: str = Field(min_length=1)
    source_field: ScientificEntitySourceField
    source_text_sha256: str = Field(pattern=SHA256_PATTERN)
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    surface_text: str = Field(min_length=1)
    baseline_entity_type: Literal[ScientificEntityType.METHOD]
    semantic_typer_entity_type: Literal[ScientificEntityType.MODEL]
    semantic_typer_score_margin: float = Field(ge=0.1, le=1.0)
    final_entity_type: Literal[ScientificEntityType.MODEL]


class H2FullCorpusFinalMention(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[FINAL_MENTION_SCHEMA_VERSION] = FINAL_MENTION_SCHEMA_VERSION
    build_id: str = Field(min_length=1)
    candidate_evidence_id: str = Field(pattern=EVIDENCE_ID_PATTERN)
    final_mention_id: str = Field(pattern=MENTION_ID_PATTERN)
    canonical_id: str = Field(min_length=1)
    source_field: ScientificEntitySourceField
    source_text_sha256: str = Field(pattern=SHA256_PATTERN)
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    surface_text: str = Field(min_length=1)
    baseline_prediction_evidence_id: str = Field(pattern=EVIDENCE_ID_PATTERN)
    baseline_entity_type: ScientificEntityType
    baseline_confidence_score: float = Field(ge=0.0, le=1.0)
    semantic_typer_case_id: str | None = None
    semantic_typer_predicted_entity_type: ScientificEntityType | None = None
    semantic_typer_used_baseline_fallback: bool | None = None
    semantic_typer_score_margin: float | None = Field(default=None, ge=0.0, le=1.0)
    h2_override_applied: bool
    final_entity_type: ScientificEntityType
    materialization_fingerprint_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_semantics(self) -> "H2FullCorpusFinalMention":
        if self.baseline_entity_type != ScientificEntityType.METHOD:
            if any(
                value is not None
                for value in (
                    self.semantic_typer_case_id,
                    self.semantic_typer_predicted_entity_type,
                    self.semantic_typer_used_baseline_fallback,
                    self.semantic_typer_score_margin,
                )
            ):
                raise ValueError("Non-method baseline rows must not carry semantic typer output")
            if self.h2_override_applied or self.final_entity_type != self.baseline_entity_type:
                raise ValueError("Non-method baseline rows must be preserved")
        elif self.semantic_typer_case_id is None:
            raise ValueError("Method baseline rows require semantic typer lineage")
        if self.h2_override_applied:
            if self.baseline_entity_type != ScientificEntityType.METHOD:
                raise ValueError("Only method baseline rows may be overridden")
            if self.semantic_typer_predicted_entity_type != ScientificEntityType.MODEL:
                raise ValueError("H2 override requires semantic typer model prediction")
            if self.semantic_typer_used_baseline_fallback:
                raise ValueError("Fallback semantic typer output cannot trigger H2")
            if self.semantic_typer_score_margin is None or self.semantic_typer_score_margin < 0.1:
                raise ValueError("H2 override requires score_margin >= 0.10")
            if self.final_entity_type != ScientificEntityType.MODEL:
                raise ValueError("H2 override final type must be model")
        elif self.final_entity_type != self.baseline_entity_type:
            raise ValueError("Non-overridden rows must preserve baseline type")
        return self


class H2FullCorpusSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[SUMMARY_SCHEMA_VERSION] = SUMMARY_SCHEMA_VERSION
    build_id: str
    input_document_count: int = Field(gt=0)
    upstream_raw_mention_count: int = Field(ge=0)
    baseline_prediction_count: int = Field(ge=0)
    baseline_method_count: int = Field(ge=0)
    semantic_typer_case_count: int = Field(ge=0)
    semantic_typer_scored_count: int = Field(ge=0)
    semantic_typer_fallback_count: int = Field(ge=0)
    typer_coverage_over_method_cases: float = Field(ge=0.0, le=1.0)
    h2_override_count: int = Field(ge=0)
    final_mention_count: int = Field(ge=0)
    baseline_count_by_type: dict[str, int]
    final_count_by_type: dict[str, int]
    source_field_counts: dict[str, int]


class H2FullCorpusManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[MANIFEST_SCHEMA_VERSION] = MANIFEST_SCHEMA_VERSION
    build_id: str
    authorization_id: str
    candidate_id: str
    candidate_fingerprint_sha256: str = Field(pattern=SHA256_PATTERN)
    materialization_config_sha256: str = Field(pattern=SHA256_PATTERN)
    materialization_fingerprint_sha256: str = Field(pattern=SHA256_PATTERN)
    canonical_path: str
    canonical_sha256: str = Field(pattern=SHA256_PATTERN)
    canonical_document_count: int = Field(gt=0)
    upstream_runtime_config_sha256: str = Field(pattern=SHA256_PATTERN)
    baseline_policy_config_sha256: str = Field(pattern=SHA256_PATTERN)
    semantic_typer_config_sha256: str = Field(pattern=SHA256_PATTERN)
    semantic_typer_fingerprint_sha256: str = Field(pattern=SHA256_PATTERN)
    h2_threshold: Literal[0.1]
    upstream_raw_mention_count: int = Field(ge=0)
    baseline_prediction_count: int = Field(ge=0)
    semantic_typer_case_count: int = Field(ge=0)
    semantic_typer_scored_count: int = Field(ge=0)
    semantic_typer_fallback_count: int = Field(ge=0)
    h2_override_count: int = Field(ge=0)
    final_mention_count: int = Field(ge=0)
    files: dict[str, str]
    exact_authorized_canonical_snapshot_verified: Literal[True]
    authorization_validated_before_model_load: Literal[True]
    reference_labels_used: Literal[False]
    threshold_tuning_executed: Literal[False]
    policy_revision_executed: Literal[False]
    span_mutated: Literal[False]
    canonical_truth_mutated: Literal[False]
    production_latest_promotion_authorized: Literal[False]
    latest_overwrite_allowed: Literal[False]
    publication_ready: Literal[False]
    candidate_validation_required_before_promotion: Literal[True]
    next_slice: Literal["validate_h2_full_corpus_candidate_materialization"]


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_h2_full_corpus_candidate_config(path: Path) -> H2FullCorpusCandidateConfig:
    try:
        payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueLoader)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise H2FullCorpusCandidateError(f"Invalid candidate config {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise H2FullCorpusCandidateError(f"Expected YAML object: {path}")
    return H2FullCorpusCandidateConfig.model_validate(payload)


def canonical_config_sha256(config: H2FullCorpusCandidateConfig) -> str:
    return hashlib.sha256(_canonical_json(config.model_dump(mode="json")).encode("utf-8")).hexdigest()


__all__ = [
    "CONFIG_SCHEMA_VERSION",
    "CASE_SCHEMA_VERSION",
    "FINAL_MENTION_SCHEMA_VERSION",
    "OVERRIDE_SCHEMA_VERSION",
    "SUMMARY_SCHEMA_VERSION",
    "MANIFEST_SCHEMA_VERSION",
    "H2FullCorpusCandidateError",
    "H2FullCorpusCandidateConfig",
    "H2FullCorpusCase",
    "H2FullCorpusOverride",
    "H2FullCorpusFinalMention",
    "H2FullCorpusSummary",
    "H2FullCorpusManifest",
    "load_h2_full_corpus_candidate_config",
    "canonical_config_sha256",
]
