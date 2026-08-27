from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Literal

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


HELDOUT_COMPLETION_MANIFEST_SCHEMA_VERSION = (
    "scientific_entity_heldout_review_completion_manifest_v0.1"
)
HELDOUT_AUDIT_SCHEMA_VERSION = "scientific_entity_heldout_review_annotation_audit_v0.1"
NonNegativeInt = Annotated[int, Field(ge=0)]


class ScientificEntityHeldoutReviewCompletionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[HELDOUT_COMPLETION_MANIFEST_SCHEMA_VERSION]
    review_id: str = Field(pattern=BUILD_ID_PATTERN)
    generated_at_utc: datetime
    review_status: ScientificEntityReviewStatus
    annotation_method: ScientificEntityAnnotationMethod
    annotation_guideline_version: str = Field(min_length=1)
    annotation_passes: int = Field(ge=1)
    annotator_ids: list[str] = Field(min_length=1)

    preparation_manifest_file: Literal["preparation_manifest.json"]
    preparation_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    blank_annotations_file: Literal["annotations_working.jsonl"]
    blank_annotations_sha256: str = Field(pattern=SHA256_PATTERN)
    completed_annotations_file: Literal["completed_annotations.jsonl"]
    completed_annotations_sha256: str = Field(pattern=SHA256_PATTERN)
    canonical_sample_file: Literal["canonical_documents.sample.jsonl"]
    canonical_sample_sha256: str = Field(pattern=SHA256_PATTERN)
    sample_assignments_file: Literal["sample_assignments.jsonl"]
    sample_assignments_sha256: str = Field(pattern=SHA256_PATTERN)

    review_manifest_file: Literal["review_manifest.json"]
    review_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    reference_mentions_file: Literal["reference_mentions.jsonl"]
    reference_mentions_sha256: str = Field(pattern=SHA256_PATTERN)
    annotation_audit_file: Literal["annotation_audit_summary.json"]
    annotation_audit_sha256: str = Field(pattern=SHA256_PATTERN)

    document_count: int = Field(ge=1)
    annotation_row_count: int = Field(ge=1)
    completed_annotation_row_count: int = Field(ge=1)
    reference_mention_count: NonNegativeInt
    uncertain_reference_mention_count: NonNegativeInt
    reference_count_by_type: dict[ScientificEntityType, NonNegativeInt]

    prediction_blind: Literal[True]
    heldout_dev_overlap_count: Literal[0]
    review_complete: Literal[True]
    evaluation_harness_ready: Literal[True]
    automatic_review_approval: Literal[False]
    production_extractor_selected: Literal[False]
    full_corpus_build_authorized: Literal[False]
    canonical_truth_mutated: Literal[False]
    may_be_used_as_reconcile_input: Literal[False]
    redistribution_allowed: Literal[False]
    publication_ready: Literal[False]

    @model_validator(mode="after")
    def validate_manifest(self) -> "ScientificEntityHeldoutReviewCompletionManifest":
        if (
            self.generated_at_utc.tzinfo is None
            or self.generated_at_utc.utcoffset() != timedelta(0)
        ):
            raise ValueError("generated_at_utc must use UTC offset +00:00")
        if self.review_status != ScientificEntityReviewStatus.REVIEWED_CANDIDATE:
            raise ValueError("held-out manual review must use reviewed_candidate status")
        if self.annotation_method == ScientificEntityAnnotationMethod.SYNTHETIC_FIXTURE:
            raise ValueError("held-out review cannot use synthetic_fixture annotation method")
        if len(set(self.annotator_ids)) != len(self.annotator_ids):
            raise ValueError("annotator_ids must not contain duplicates")
        if any(not value.strip() for value in self.annotator_ids):
            raise ValueError("annotator_ids must contain non-whitespace text")
        if set(self.reference_count_by_type) != set(ScientificEntityType):
            raise ValueError("reference_count_by_type must cover all entity types")
        if sum(self.reference_count_by_type.values()) != self.reference_mention_count:
            raise ValueError("reference_count_by_type must sum to reference_mention_count")
        if self.completed_annotation_row_count != self.annotation_row_count:
            raise ValueError("all annotation rows must be complete")
        return self
