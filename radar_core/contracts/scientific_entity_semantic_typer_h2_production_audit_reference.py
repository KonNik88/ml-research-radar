from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from radar_core.contracts.scientific_entity_evidence import ScientificEntityType

CONFIG_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_production_audit_reference_freeze_v0.3"
MANIFEST_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_production_audit_reference_manifest_v0.3"
SUMMARY_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_production_audit_reference_summary_v0.3"
AUDIT_ID = "scientific-entity-semantic-typer-h2-production-audit-v0.3-20261003T121605823276Z"
REFERENCE_ID = "scientific-entity-semantic-typer-h2-production-audit-reference-v0.3-20261003T121605823276Z"
CANDIDATE_BUILD_ID = "scientific-entity-semantic-typer-h2-full-corpus-candidate-v0.3-20261003T121605823276Z"
CANDIDATE_ID = "scientific-entity-semantic-typer-candidate-v0.3-h2-selective-model-over-method"
CANDIDATE_FINGERPRINT = "6d3782fb1f2cc7219b7083bcf381c17c546491425e817c0f5620ff145bfa6966"
MATERIALIZATION_FINGERPRINT = "5c528cab17e2d48c812f6013fbd4f7d966d8e0ccab5eff4e86de166e92641366"
CANONICAL_SHA256 = "3cc6e3c779fee351bcab605ad1b804acf0e4f8365718db96dad398959420b6ff"
AUDIT_CONFIG_FILE_SHA256 = "0afad2d06452c22320fdc75775ad50ba02dee1a63910f2d76af0134ace1dbdfe"
AUDIT_CONFIG_CANONICAL_SHA256 = "c1f0f786c44149a3c5decbe96d96baf3ce778be3798929fe6064b05accfe9de9"
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class H2ProductionAuditReferenceError(ValueError):
    pass


class _UniqueLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueLoader, node: Any, deep: bool = False) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise H2ProductionAuditReferenceError(f"Duplicate YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


class LayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["scientific_entity_semantic_typer_h2_production_audit_reference_freeze"]
    version: Literal["v0.3"]
    status: Literal["prediction_blind_reference_freeze_tooling"]
    layer_kind: Literal["derived_scientific_entity_promotion_safety_reference"]


class LineageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    audit_id: Literal[AUDIT_ID]
    candidate_build_id: Literal[CANDIDATE_BUILD_ID]
    candidate_id: Literal[CANDIDATE_ID]
    candidate_fingerprint_sha256: Literal[CANDIDATE_FINGERPRINT]
    materialization_fingerprint_sha256: Literal[MATERIALIZATION_FINGERPRINT]
    canonical_sha256: Literal[CANONICAL_SHA256]
    canonical_document_count: Literal[61075]
    audit_config_path: Literal["configs/scientific_entity_semantic_typer_h2_production_audit_v0.3.yaml"]
    audit_config_file_sha256: Literal[AUDIT_CONFIG_FILE_SHA256]
    audit_config_canonical_sha256: Literal[AUDIT_CONFIG_CANONICAL_SHA256]
    expected_audit_case_count: Literal[240]
    expected_audit_sample_validation_total_checks: Literal[27]
    expected_audit_sample_validation_required_failed_count: Literal[0]


class AnnotationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    working_root: Literal["data/entities/scientific_entity_semantic_typer_h2_production_audit_annotation_work/v0.3"]
    completed_filename: Literal["annotations_completed.jsonl"]
    allowed_entity_types: list[ScientificEntityType]
    allowed_span_statuses: list[Literal["valid_entity_span", "boundary_issue", "not_an_entity", "uncertain"]]
    confidence_levels: list[Literal["high", "medium", "low"]]
    require_all_rows_complete: Literal[True]
    require_exact_alignment_to_blank_annotations: Literal[True]
    require_immutable_source_fields_unchanged: Literal[True]
    preserve_row_order: Literal[True]
    uncertain_allowed: Literal[True]
    boundary_issue_allowed: Literal[True]
    automatic_annotation_allowed: Literal[False]
    automatic_review_approval_allowed: Literal[False]

    @model_validator(mode="after")
    def validate_taxonomy(self) -> "AnnotationConfig":
        if self.allowed_entity_types != list(ScientificEntityType):
            raise ValueError("allowed_entity_types must match frozen Scientific Entity enum order")
        if self.allowed_span_statuses != ["valid_entity_span", "boundary_issue", "not_an_entity", "uncertain"]:
            raise ValueError("allowed_span_statuses order drifted")
        if self.confidence_levels != ["high", "medium", "low"]:
            raise ValueError("confidence_levels order drifted")
        return self


class OutputsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    frozen_root: Literal["data/entities/scientific_entity_semantic_typer_h2_production_audit_reference/v0.3"]
    reference_id: Literal[REFERENCE_ID]
    immutable_directories: Literal[True]
    overwrite_allowed: Literal[False]
    encoding: Literal["utf-8"]
    line_ending: Literal["lf"]


class SafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_prediction_files_may_be_read: Literal[False]
    sampled_strata_may_be_reconstructed: Literal[False]
    unblinding_allowed: Literal[False]
    promotion_gate_evaluation_allowed: Literal[False]
    model_inference_allowed: Literal[False]
    threshold_tuning_allowed: Literal[False]
    h2_policy_revision_allowed: Literal[False]
    candidate_mutation_allowed: Literal[False]
    canonical_truth_mutation_allowed: Literal[False]
    production_latest_promotion_authorized: Literal[False]
    latest_overwrite_allowed: Literal[False]
    publication_authorized: Literal[False]


class NextStepsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    after_plan: Literal["commit_h2_production_audit_reference_freeze_tooling_before_execute"]
    after_execute: Literal["validate_frozen_h2_production_audit_reference"]
    after_validation: Literal["unblind_and_evaluate_h2_production_audit_promotion_gate"]


class H2ProductionAuditReferenceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[CONFIG_SCHEMA_VERSION]
    layer: LayerConfig
    lineage: LineageConfig
    annotation: AnnotationConfig
    outputs: OutputsConfig
    safety: SafetyConfig
    next_steps: NextStepsConfig


class H2ProductionAuditReferenceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[SUMMARY_SCHEMA_VERSION] = SUMMARY_SCHEMA_VERSION
    reference_id: Literal[REFERENCE_ID]
    audit_id: Literal[AUDIT_ID]
    annotation_row_count: Literal[240]
    completed_annotation_row_count: Literal[240]
    span_status_count: dict[str, int]
    reference_type_count: dict[str, int]
    confidence_count: dict[str, int]
    reviewer_note_nonempty_count: int = Field(ge=0, le=240)
    uncertain_count: int = Field(ge=0, le=240)
    not_an_entity_count: int = Field(ge=0, le=240)
    boundary_issue_count: int = Field(ge=0, le=240)
    valid_entity_span_count: int = Field(ge=0, le=240)
    uncertain_rate: float = Field(ge=0.0, le=1.0)
    not_an_entity_rate: float = Field(ge=0.0, le=1.0)
    boundary_issue_rate: float = Field(ge=0.0, le=1.0)
    promotion_gates_evaluated: Literal[False]
    sampled_strata_reconstructed: Literal[False]
    candidate_prediction_files_read: Literal[False]


class H2ProductionAuditReferenceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[MANIFEST_SCHEMA_VERSION] = MANIFEST_SCHEMA_VERSION
    reference_id: Literal[REFERENCE_ID]
    audit_id: Literal[AUDIT_ID]
    candidate_build_id: Literal[CANDIDATE_BUILD_ID]
    candidate_id: Literal[CANDIDATE_ID]
    candidate_fingerprint_sha256: Literal[CANDIDATE_FINGERPRINT]
    materialization_fingerprint_sha256: Literal[MATERIALIZATION_FINGERPRINT]
    canonical_sha256: Literal[CANONICAL_SHA256]
    canonical_document_count: Literal[61075]
    audit_config_file_sha256: Literal[AUDIT_CONFIG_FILE_SHA256]
    audit_config_canonical_sha256: Literal[AUDIT_CONFIG_CANONICAL_SHA256]
    audit_sample_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    audit_cases_sha256: str = Field(pattern=SHA256_PATTERN)
    blank_annotations_sha256: str = Field(pattern=SHA256_PATTERN)
    completed_annotations_source_sha256: str = Field(pattern=SHA256_PATTERN)
    reference_annotations_sha256: str = Field(pattern=SHA256_PATTERN)
    annotation_summary_sha256: str = Field(pattern=SHA256_PATTERN)
    annotator_ids: list[str] = Field(min_length=1)
    annotation_row_count: Literal[240]
    completed_annotation_row_count: Literal[240]
    prediction_blind: Literal[True]
    reference_frozen: Literal[True]
    candidate_prediction_files_read: Literal[False]
    sampled_strata_reconstructed: Literal[False]
    unblinding_executed: Literal[False]
    promotion_gates_evaluated: Literal[False]
    model_inference_executed: Literal[False]
    threshold_tuning_executed: Literal[False]
    policy_revision_executed: Literal[False]
    candidate_mutated: Literal[False]
    canonical_truth_mutated: Literal[False]
    production_latest_promotion_authorized: Literal[False]
    latest_overwritten: Literal[False]
    publication_ready: Literal[False]
    next_slice: Literal["unblind_and_evaluate_h2_production_audit_promotion_gate"]

    @model_validator(mode="after")
    def validate_annotators(self) -> "H2ProductionAuditReferenceManifest":
        normalized = [value.strip() for value in self.annotator_ids]
        if any(not value for value in normalized) or len(set(normalized)) != len(normalized):
            raise ValueError("annotator_ids must be unique non-empty identifiers")
        return self


def load_h2_production_audit_reference_config(path: Path) -> H2ProductionAuditReferenceConfig:
    payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueLoader)
    if not isinstance(payload, dict):
        raise H2ProductionAuditReferenceError("Reference-freeze config must be a mapping")
    return H2ProductionAuditReferenceConfig.model_validate(payload)


def canonical_config_sha256(config: H2ProductionAuditReferenceConfig) -> str:
    raw = json.dumps(config.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
