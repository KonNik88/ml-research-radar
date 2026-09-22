from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from radar_core.contracts.scientific_entity_evaluation import (
    ScientificEntityAnnotationMethod,
    ScientificEntityReviewStatus,
)
from radar_core.contracts.scientific_entity_evidence import (
    BUILD_ID_PATTERN,
    SHA256_PATTERN,
    ScientificEntityType,
)


CONFIG_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_reference_freeze_config_v0.3"
COMPLETION_MANIFEST_SCHEMA_VERSION = (
    "scientific_entity_semantic_typer_h2_reference_freeze_manifest_v0.3"
)
AUDIT_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_reference_audit_v0.3"
CANDIDATE_ID = "scientific-entity-semantic-typer-candidate-v0.3-h2-selective-model-over-method"
CANDIDATE_FINGERPRINT = (
    "6d3782fb1f2cc7219b7083bcf381c17c546491425e817c0f5620ff145bfa6966"
)
SAMPLE_ID = "scientific-entity-fresh-heldout-sample-v0.3-20260919T093837653829Z"
REVIEW_ID = "scientific-entity-fresh-heldout-review-v0.3-20260919T093837653829Z"
SELECTED_IDS_SHA256 = (
    "bbd0f209705c8a8ff02fea7fa732741b9cf9981d24a79909c618726fed8608f8"
)
SAMPLE_MANIFEST_SHA256 = (
    "9ba9799c0d5b20b91e4059c7117fa6d6d015fb6ae1fc8f59f9058e52bd093c80"
)
ACCEPTANCE_GATE_CONFIG_SHA256 = (
    "3ed17739796807046269b88aab40ced2cc10ca1e45ff67dc8965a98070c17a89"
)


class ScientificEntityH2ReferenceError(ValueError):
    """Raised when the H2 v0.3 reference-freeze contract or evidence drifts."""


class LayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["scientific_entity_semantic_typer_h2_reference_freeze"]
    version: Literal["v0.3"]
    status: Literal["tooling_frozen"]
    layer_kind: Literal["prediction_blind_manual_reference_freeze"]


class CandidateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: Literal[CANDIDATE_ID]
    candidate_fingerprint_sha256: Literal[CANDIDATE_FINGERPRINT]


class AcceptanceGateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    config_path: Literal[
        "configs/scientific_entity_semantic_typer_h2_independent_acceptance_gate_v0.3.yaml"
    ]
    expected_canonical_config_sha256: Literal[ACCEPTANCE_GATE_CONFIG_SHA256]
    require_gate_frozen_before_annotation: Literal[True]


class SampleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sample_id: Literal[SAMPLE_ID]
    review_id: Literal[REVIEW_ID]
    expected_sample_manifest_sha256: Literal[SAMPLE_MANIFEST_SHA256]
    selected_canonical_ids_sha256: Literal[SELECTED_IDS_SHA256]
    expected_document_count: Literal[48]
    expected_annotation_row_count: Literal[96]
    expected_consumed_union_document_count: Literal[120]
    expected_consumed_union_overlap_count: Literal[0]
    require_prediction_blind_sample: Literal[True]
    require_independent_sample_validation: Literal[True]


class AnnotationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    annotation_method: Literal[ScientificEntityAnnotationMethod.MANUAL_ADJUDICATED]
    annotation_guideline_version: Literal[
        "scientific_entity_annotation_guidelines_v0.1"
    ]
    annotation_passes: Literal[1]
    source_fields: list[Literal["title", "abstract"]] = Field(
        min_length=2, max_length=2
    )
    entity_types: list[
        Literal["task", "method", "dataset", "metric", "model", "domain"]
    ] = Field(min_length=6, max_length=6)
    require_all_annotation_rows_complete: Literal[True]
    require_zero_unresolved_uncertain_mentions: Literal[True]
    minimum_reference_mentions_per_type: Literal[20]
    maximum_reference_mentions_total: Literal[5000]
    require_surface_from_exact_source_slice: Literal[True]
    duplicate_typed_spans_allowed: Literal[False]

    @model_validator(mode="after")
    def validate_order(self) -> "AnnotationConfig":
        if self.source_fields != ["title", "abstract"]:
            raise ValueError("source_fields must remain title, abstract")
        if self.entity_types != [member.value for member in ScientificEntityType]:
            raise ValueError("entity_types must cover all six frozen types in enum order")
        return self


class WorkingCopyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root: Literal[
        "data/entities/scientific_entity_semantic_typer_h2_annotation_work/v0.3"
    ]
    filename: Literal["annotations_completed.jsonl"]
    readme_filename: Literal["README.md"]
    mutable_non_evidence: Literal[True]
    overwrite_allowed: Literal[False]


class OutputsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    frozen_root: Literal[
        "data/entities/scientific_entity_semantic_typer_h2_reference/v0.3"
    ]
    immutable_directories: Literal[True]
    encoding: Literal["utf-8"]
    line_ending: Literal["lf"]


class SafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    predictions_visible_during_annotation: Literal[False]
    automatic_annotation_allowed: Literal[False]
    automatic_review_approval_allowed: Literal[False]
    h2_inference_allowed_before_reference_freeze: Literal[False]
    threshold_tuning_allowed: Literal[False]
    policy_revision_allowed: Literal[False]
    span_mutation_allowed: Literal[False]
    taxonomy_changes_allowed: Literal[False]
    evaluation_allowed_before_reference_freeze: Literal[False]
    canonical_truth_mutation_allowed: Literal[False]
    reconcile_input_allowed: Literal[False]
    production_extractor_selected: Literal[False]
    full_corpus_build_authorized: Literal[False]
    redistribution_allowed: Literal[False]
    publication_allowed: Literal[False]


class NextStepsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    after_tooling_merge: Literal["prepare_h2_prediction_blind_annotation_working_copy"]
    after_annotation_complete: Literal["freeze_and_validate_h2_v03_reference_evidence"]
    after_reference_freeze: Literal["run_frozen_h2_independent_inference"]


class ScientificEntityH2ReferenceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[CONFIG_SCHEMA_VERSION]
    layer: LayerConfig
    candidate: CandidateConfig
    acceptance_gate: AcceptanceGateConfig
    sample: SampleConfig
    annotation: AnnotationConfig
    working_copy: WorkingCopyConfig
    outputs: OutputsConfig
    safety: SafetyConfig
    next_steps: NextStepsConfig


class ScientificEntityH2ReferenceCompletionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[COMPLETION_MANIFEST_SCHEMA_VERSION]
    candidate_id: Literal[CANDIDATE_ID]
    candidate_fingerprint_sha256: Literal[CANDIDATE_FINGERPRINT]
    independent_acceptance_gate_config_sha256: Literal[
        ACCEPTANCE_GATE_CONFIG_SHA256
    ]
    sample_id: Literal[SAMPLE_ID]
    review_id: Literal[REVIEW_ID]
    generated_at_utc: datetime
    review_status: Literal[ScientificEntityReviewStatus.REVIEWED_CANDIDATE]
    annotation_method: Literal[ScientificEntityAnnotationMethod.MANUAL_ADJUDICATED]
    annotation_guideline_version: Literal[
        "scientific_entity_annotation_guidelines_v0.1"
    ]
    annotation_passes: Literal[1]
    annotator_ids: list[str] = Field(min_length=1)

    sample_manifest_file: Literal["manifest.json"]
    sample_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    blank_annotations_file: Literal["annotations_working.jsonl"]
    blank_annotations_sha256: str = Field(pattern=SHA256_PATTERN)
    completed_annotations_file: Literal["completed_annotations.jsonl"]
    completed_annotations_sha256: str = Field(pattern=SHA256_PATTERN)
    canonical_sample_file: Literal["canonical_documents.sample.jsonl"]
    canonical_sample_sha256: str = Field(pattern=SHA256_PATTERN)
    sample_assignments_file: Literal["sample_assignments.jsonl"]
    sample_assignments_sha256: str = Field(pattern=SHA256_PATTERN)
    exclusion_provenance_file: Literal["exclusion_provenance.json"]
    exclusion_provenance_sha256: str = Field(pattern=SHA256_PATTERN)
    review_manifest_file: Literal["review_manifest.json"]
    review_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    reference_mentions_file: Literal["reference_mentions.jsonl"]
    reference_mentions_sha256: str = Field(pattern=SHA256_PATTERN)
    annotation_audit_file: Literal["annotation_audit_summary.json"]
    annotation_audit_sha256: str = Field(pattern=SHA256_PATTERN)

    selected_canonical_ids_sha256: Literal[SELECTED_IDS_SHA256]
    document_count: Literal[48]
    annotation_row_count: Literal[96]
    completed_annotation_row_count: Literal[96]
    reference_mention_count: int = Field(ge=120, le=5000)
    uncertain_reference_mention_count: Literal[0]
    reference_count_by_type: dict[ScientificEntityType, int]
    minimum_reference_mentions_per_type: Literal[20]
    reference_adequacy_passed: Literal[True]

    prediction_blind: Literal[True]
    sample_independent_validation_passed: Literal[True]
    excluded_consumed_union_document_count: Literal[120]
    sample_consumed_union_overlap_count: Literal[0]
    review_complete: Literal[True]
    reference_frozen: Literal[True]
    evaluation_harness_ready: Literal[True]
    candidate_predictions_visible_during_annotation: Literal[False]
    h2_model_inference_executed: Literal[False]
    evaluation_executed: Literal[False]
    threshold_tuning_executed: Literal[False]
    policy_revision_executed: Literal[False]
    automatic_review_approval: Literal[False]
    production_extractor_selected: Literal[False]
    full_corpus_build_authorized: Literal[False]
    canonical_truth_mutated: Literal[False]
    may_be_used_as_reconcile_input: Literal[False]
    redistribution_allowed: Literal[False]
    publication_ready: Literal[False]
    next_slice: Literal["run_frozen_h2_independent_inference"]

    @model_validator(mode="after")
    def validate_manifest(self) -> "ScientificEntityH2ReferenceCompletionManifest":
        if self.generated_at_utc.tzinfo is None or self.generated_at_utc.utcoffset() != timedelta(0):
            raise ValueError("generated_at_utc must use UTC offset +00:00")
        if len(set(self.annotator_ids)) != len(self.annotator_ids):
            raise ValueError("annotator_ids must be unique")
        if any(not value.strip() for value in self.annotator_ids):
            raise ValueError("annotator_ids must contain non-whitespace text")
        if set(self.reference_count_by_type) != set(ScientificEntityType):
            raise ValueError("reference_count_by_type must cover all six entity types")
        if sum(self.reference_count_by_type.values()) != self.reference_mention_count:
            raise ValueError("reference_count_by_type must sum to reference_mention_count")
        if any(
            value < self.minimum_reference_mentions_per_type
            for value in self.reference_count_by_type.values()
        ):
            raise ValueError("every entity type must meet the frozen minimum reference count")
        return self


class _UniqueKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueKeySafeLoader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ScientificEntityH2ReferenceError(f"Duplicate YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def load_h2_reference_config(path: str | Path) -> ScientificEntityH2ReferenceConfig:
    path = Path(path)
    try:
        payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeySafeLoader)
    except (OSError, yaml.YAMLError) as exc:
        raise ScientificEntityH2ReferenceError(str(exc)) from exc
    try:
        return ScientificEntityH2ReferenceConfig.model_validate(payload)
    except Exception as exc:
        raise ScientificEntityH2ReferenceError(str(exc)) from exc


__all__ = [
    "ACCEPTANCE_GATE_CONFIG_SHA256",
    "AUDIT_SCHEMA_VERSION",
    "CANDIDATE_FINGERPRINT",
    "CANDIDATE_ID",
    "COMPLETION_MANIFEST_SCHEMA_VERSION",
    "CONFIG_SCHEMA_VERSION",
    "REVIEW_ID",
    "SAMPLE_ID",
    "ScientificEntityH2ReferenceCompletionManifest",
    "ScientificEntityH2ReferenceConfig",
    "ScientificEntityH2ReferenceError",
    "load_h2_reference_config",
]
