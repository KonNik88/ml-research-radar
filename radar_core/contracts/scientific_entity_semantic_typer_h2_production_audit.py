from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from radar_core.contracts.scientific_entity_evidence import ScientificEntitySourceField, ScientificEntityType

CONFIG_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_production_audit_v0.3"
CASE_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_production_audit_case_v0.3"
ANNOTATION_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_production_audit_annotation_v0.3"
MANIFEST_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_production_audit_manifest_v0.3"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
EVIDENCE_ID_PATTERN = r"^evidence:[0-9a-f]{32}$"


class H2ProductionAuditError(ValueError):
    pass


class _UniqueLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueLoader, node: Any, deep: bool = False) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise H2ProductionAuditError(f"Duplicate YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


class LayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["scientific_entity_semantic_typer_h2_production_audit"]
    version: Literal["v0.3"]
    status: Literal["preregistered_prediction_blind_production_audit"]
    layer_kind: Literal["derived_scientific_entity_promotion_safety_audit"]


class CandidateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    build_id: Literal["scientific-entity-semantic-typer-h2-full-corpus-candidate-v0.3-20261003T121605823276Z"]
    candidate_dir: Literal["data/entities/scientific_entity_semantic_typer_h2_full_corpus_candidate/v0.3/scientific-entity-semantic-typer-h2-full-corpus-candidate-v0.3-20261003T121605823276Z"]
    candidate_id: Literal["scientific-entity-semantic-typer-candidate-v0.3-h2-selective-model-over-method"]
    candidate_fingerprint_sha256: Literal["6d3782fb1f2cc7219b7083bcf381c17c546491425e817c0f5620ff145bfa6966"]
    materialization_fingerprint_sha256: Literal["5c528cab17e2d48c812f6013fbd4f7d966d8e0ccab5eff4e86de166e92641366"]
    expected_full_corpus_validation_total_checks: Literal[42]
    expected_full_corpus_validation_required_failed_count: Literal[0]
    baseline_prediction_count: Literal[846264]
    baseline_method_count: Literal[260200]
    h2_override_count: Literal[33469]
    final_mention_count: Literal[846264]


class CanonicalSnapshotConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: Literal["data/analytics/reconciled/canonical_documents.jsonl"]
    sha256: Literal["3cc6e3c779fee351bcab605ad1b804acf0e4f8365718db96dad398959420b6ff"]
    document_count: Literal[61075]


class SamplingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    audit_id: Literal["scientific-entity-semantic-typer-h2-production-audit-v0.3-20261003T121605823276Z"]
    selection_seed_sha256: str = Field(pattern=SHA256_PATTERN)
    blind_order_seed_sha256: str = Field(pattern=SHA256_PATTERN)
    override_count: Literal[100]
    preserved_method_count: Literal[100]
    fallback_method_count: Literal[40]
    total_count: Literal[240]
    sample_unit: Literal["baseline_method_mention"]
    deterministic_hash_rank_sampling: Literal[True]
    annotation_order_hides_stratum: Literal[True]


class AnnotationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed_entity_types: list[ScientificEntityType]
    allowed_span_statuses: list[Literal["valid_entity_span", "boundary_issue", "not_an_entity", "uncertain"]]
    confidence_levels: list[Literal["high", "medium", "low"]]
    prediction_blind: Literal[True]
    stratum_hidden: Literal[True]
    candidate_prediction_hidden: Literal[True]
    semantic_scores_hidden: Literal[True]
    reference_freeze_required_before_unblinding: Literal[True]


class PromotionGatesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_overall_uncertain_rate: Literal[0.10]
    max_overall_not_entity_rate: Literal[0.15]
    min_override_usable_count: Literal[80]
    min_override_reference_model_rate: Literal[0.45]
    max_override_reference_method_rate: Literal[0.30]
    min_override_net_model_minus_method_rate: Literal[0.15]
    min_preserved_usable_count: Literal[80]
    min_preserved_reference_method_rate: Literal[0.50]
    max_preserved_reference_model_rate: Literal[0.30]
    min_fallback_usable_count: Literal[30]
    max_fallback_unresolved_or_not_entity_rate: Literal[0.25]
    boundary_issue_rate_is_diagnostic_only: Literal[True]
    thresholds_may_not_be_revised_after_annotation_starts: Literal[True]


class ExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    output_root: Literal["data/entities/scientific_entity_semantic_typer_h2_production_audit/v0.3"]
    annotation_work_root: Literal["data/entities/scientific_entity_semantic_typer_h2_production_audit_annotation_work/v0.3"]
    immutable_sample_output: Literal[True]
    overwrite_allowed: Literal[False]
    plan_writes_output: Literal[False]
    plan_reads_candidate_predictions: Literal[False]
    plan_exposes_sampled_strata: Literal[False]


class SafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    new_model_inference_allowed: Literal[False]
    threshold_tuning_allowed: Literal[False]
    h2_policy_revision_allowed: Literal[False]
    candidate_mutation_allowed: Literal[False]
    canonical_truth_mutation_allowed: Literal[False]
    production_latest_promotion_authorized: Literal[False]
    latest_overwrite_allowed: Literal[False]
    publication_authorized: Literal[False]
    blind_annotation_required: Literal[True]
    separate_reference_freeze_required: Literal[True]
    separate_promotion_decision_required: Literal[True]


class NextStepsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    after_plan: Literal["commit_h2_production_audit_sample_tooling_before_execute"]
    after_execute: Literal["complete_prediction_blind_h2_production_audit_annotation"]
    after_annotation: Literal["freeze_h2_production_audit_reference_then_evaluate_promotion_gate"]


class H2ProductionAuditConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[CONFIG_SCHEMA_VERSION]
    layer: LayerConfig
    candidate: CandidateConfig
    canonical_snapshot: CanonicalSnapshotConfig
    sampling: SamplingConfig
    annotation: AnnotationConfig
    promotion_gates: PromotionGatesConfig
    execution: ExecutionConfig
    safety: SafetyConfig
    next_steps: NextStepsConfig

    @model_validator(mode="after")
    def validate_boundary(self) -> "H2ProductionAuditConfig":
        expected_types = {ScientificEntityType.TASK, ScientificEntityType.METHOD, ScientificEntityType.DATASET, ScientificEntityType.METRIC, ScientificEntityType.MODEL, ScientificEntityType.DOMAIN}
        if set(self.annotation.allowed_entity_types) != expected_types:
            raise ValueError("Audit taxonomy must exactly match frozen Scientific Entity taxonomy")
        if self.sampling.override_count + self.sampling.preserved_method_count + self.sampling.fallback_method_count != self.sampling.total_count:
            raise ValueError("Audit stratum counts must sum to total_count")
        if self.safety.production_latest_promotion_authorized or self.safety.latest_overwrite_allowed:
            raise ValueError("Audit slice must not authorize promotion")
        return self


class H2ProductionAuditCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[CASE_SCHEMA_VERSION] = CASE_SCHEMA_VERSION
    audit_id: str = Field(min_length=1)
    audit_case_id: str = Field(min_length=1)
    canonical_id: str = Field(min_length=1)
    source_field: ScientificEntitySourceField
    source_text_sha256: str = Field(pattern=SHA256_PATTERN)
    source_text: str = Field(min_length=1)
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    surface_text: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_span(self) -> "H2ProductionAuditCase":
        if self.char_end <= self.char_start:
            raise ValueError("Invalid audit span")
        if self.source_text[self.char_start:self.char_end] != self.surface_text:
            raise ValueError("Audit surface_text does not match source_text slice")
        return self


class H2ProductionAuditAnnotation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[ANNOTATION_SCHEMA_VERSION] = ANNOTATION_SCHEMA_VERSION
    audit_id: str = Field(min_length=1)
    audit_case_id: str = Field(min_length=1)
    canonical_id: str = Field(min_length=1)
    source_field: ScientificEntitySourceField
    source_text_sha256: str = Field(pattern=SHA256_PATTERN)
    source_text: str = Field(min_length=1)
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    surface_text: str = Field(min_length=1)
    reference_entity_type: ScientificEntityType | None = None
    span_status: Literal["valid_entity_span", "boundary_issue", "not_an_entity", "uncertain"] | None = None
    annotation_confidence: Literal["high", "medium", "low"] | None = None
    reviewer_note: str | None = None
    annotation_complete: bool = False

    @model_validator(mode="after")
    def validate_annotation(self) -> "H2ProductionAuditAnnotation":
        if self.source_text[self.char_start:self.char_end] != self.surface_text:
            raise ValueError("Annotation surface_text does not match source_text slice")
        if self.span_status in {"valid_entity_span", "boundary_issue"} and self.reference_entity_type is None:
            raise ValueError("Usable entity spans require reference_entity_type")
        if self.span_status in {"not_an_entity", "uncertain"} and self.reference_entity_type is not None:
            raise ValueError("not_an_entity/uncertain must not carry reference_entity_type")
        if self.annotation_complete and (self.span_status is None or self.annotation_confidence is None):
            raise ValueError("Complete annotation requires span_status and annotation_confidence")
        return self


class H2ProductionAuditManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[MANIFEST_SCHEMA_VERSION] = MANIFEST_SCHEMA_VERSION
    audit_id: str
    candidate_build_id: str
    candidate_id: str
    candidate_fingerprint_sha256: str = Field(pattern=SHA256_PATTERN)
    materialization_fingerprint_sha256: str = Field(pattern=SHA256_PATTERN)
    canonical_sha256: str = Field(pattern=SHA256_PATTERN)
    canonical_document_count: int = Field(gt=0)
    audit_config_sha256: str = Field(pattern=SHA256_PATTERN)
    selection_seed_sha256: str = Field(pattern=SHA256_PATTERN)
    blind_order_seed_sha256: str = Field(pattern=SHA256_PATTERN)
    audit_case_count: int = Field(gt=0)
    override_count: int = Field(ge=0)
    preserved_method_count: int = Field(ge=0)
    fallback_method_count: int = Field(ge=0)
    prediction_blind: Literal[True]
    sampled_stratum_exposed_in_cases: Literal[False]
    candidate_prediction_exposed_in_cases: Literal[False]
    semantic_scores_exposed_in_cases: Literal[False]
    model_inference_executed: Literal[False]
    threshold_tuning_executed: Literal[False]
    policy_revision_executed: Literal[False]
    canonical_truth_mutated: Literal[False]
    production_latest_promotion_authorized: Literal[False]


def load_h2_production_audit_config(path: Path) -> H2ProductionAuditConfig:
    raw = path.read_text(encoding="utf-8")
    payload = yaml.load(raw, Loader=_UniqueLoader)
    if not isinstance(payload, dict):
        raise H2ProductionAuditError("Audit config must be a mapping")
    return H2ProductionAuditConfig.model_validate(payload)


def canonical_config_sha256(config: H2ProductionAuditConfig) -> str:
    payload = json.dumps(config.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
