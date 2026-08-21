from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from radar_core.contracts.scientific_entity_evaluation import (
    ScientificEntityAnnotationMethod,
    ScientificEntityReviewStatus,
)
from radar_core.contracts.scientific_entity_evidence import (
    BUILD_ID_PATTERN,
    SHA256_PATTERN,
    ScientificEntityCanonicalInput,
    ScientificEntitySourceField,
    ScientificEntityType,
    sha256_text,
)


SAMPLE_ASSIGNMENT_SCHEMA_VERSION = "scientific_entity_sample_assignment_v0.1"
BLIND_ANNOTATION_SCHEMA_VERSION = "scientific_entity_blind_annotation_v0.1"
PREPARED_MANIFEST_SCHEMA_VERSION = (
    "scientific_entity_manual_review_prepared_manifest_v0.1"
)
COMPLETION_MANIFEST_SCHEMA_VERSION = (
    "scientific_entity_manual_review_completion_manifest_v0.1"
)
ANNOTATION_AUDIT_SCHEMA_VERSION = (
    "scientific_entity_manual_review_annotation_audit_v0.1"
)
SAMPLING_ALGORITHM = "deterministic_hash_uniform_and_type_enriched_v0.1"
NonNegativeInt = Annotated[int, Field(ge=0)]


class ScientificEntityReviewSampleStatus(str, Enum):
    FIXTURE = "fixture"
    CANDIDATE = "candidate"


class ScientificEntitySampleStratum(str, Enum):
    UNIFORM = "uniform"
    TYPE_ENRICHED = "type_enriched"


def build_selection_score(
    *,
    seed: str,
    stratum: ScientificEntitySampleStratum | str,
    canonical_id: str,
    enrichment_entity_type: ScientificEntityType | str | None = None,
) -> str:
    stratum_value = ScientificEntitySampleStratum(stratum).value
    type_value = (
        ScientificEntityType(enrichment_entity_type).value
        if enrichment_entity_type is not None
        else ""
    )
    payload = "\0".join(
        [
            "scientific_entity_review_sample_v0.1",
            seed,
            stratum_value,
            type_value,
            canonical_id,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ScientificEntitySampleAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[SAMPLE_ASSIGNMENT_SCHEMA_VERSION]
    review_id: str = Field(pattern=BUILD_ID_PATTERN)
    canonical_id: str = Field(min_length=1)
    sample_stratum: ScientificEntitySampleStratum
    enrichment_entity_type: ScientificEntityType | None = None
    selection_score: str = Field(pattern=SHA256_PATTERN)
    stratum_rank: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_assignment(self) -> "ScientificEntitySampleAssignment":
        if not self.canonical_id.strip():
            raise ValueError("canonical_id must contain non-whitespace text")
        if self.sample_stratum == ScientificEntitySampleStratum.UNIFORM:
            if self.enrichment_entity_type is not None:
                raise ValueError("uniform assignment cannot declare enrichment type")
        elif self.enrichment_entity_type is None:
            raise ValueError("type_enriched assignment requires enrichment type")
        return self


class ScientificEntityBlindAnnotationMention(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: ScientificEntityType
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    surface_text: str = Field(min_length=1)
    uncertain: bool = False
    reviewer_note: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_span(self) -> "ScientificEntityBlindAnnotationMention":
        if self.char_end <= self.char_start:
            raise ValueError("char_end must be greater than char_start")
        if not self.surface_text.strip():
            raise ValueError("surface_text must contain non-whitespace text")
        if self.reviewer_note is not None and not self.reviewer_note.strip():
            raise ValueError("reviewer_note must contain non-whitespace text")
        return self


class ScientificEntityBlindAnnotationRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[BLIND_ANNOTATION_SCHEMA_VERSION]
    review_id: str = Field(pattern=BUILD_ID_PATTERN)
    canonical_id: str = Field(min_length=1)
    sample_stratum: ScientificEntitySampleStratum
    enrichment_entity_type: ScientificEntityType | None = None
    source_field: ScientificEntitySourceField
    source_text_sha256: str = Field(pattern=SHA256_PATTERN)
    source_text: str = Field(min_length=1)
    annotation_complete: bool
    mentions: list[ScientificEntityBlindAnnotationMention]
    reviewer_note: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_annotation_row(self) -> "ScientificEntityBlindAnnotationRow":
        if not self.canonical_id.strip():
            raise ValueError("canonical_id must contain non-whitespace text")
        if not self.source_text.strip():
            raise ValueError("source_text must contain non-whitespace text")
        if self.source_text_sha256 != sha256_text(self.source_text):
            raise ValueError("source_text_sha256 does not match source_text")
        if self.sample_stratum == ScientificEntitySampleStratum.UNIFORM:
            if self.enrichment_entity_type is not None:
                raise ValueError("uniform annotation cannot declare enrichment type")
        elif self.enrichment_entity_type is None:
            raise ValueError("type_enriched annotation requires enrichment type")
        if self.reviewer_note is not None and not self.reviewer_note.strip():
            raise ValueError("reviewer_note must contain non-whitespace text")

        seen: set[tuple[str, int, int]] = set()
        for mention in self.mentions:
            if mention.char_end > len(self.source_text):
                raise ValueError("mention char_end exceeds source_text length")
            if self.source_text[mention.char_start : mention.char_end] != mention.surface_text:
                raise ValueError(
                    "mention surface_text does not match the declared half-open span"
                )
            key = (
                mention.entity_type.value,
                mention.char_start,
                mention.char_end,
            )
            if key in seen:
                raise ValueError("duplicate typed span in annotation row")
            seen.add(key)
        return self


class ScientificEntitySamplingPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    algorithm: Literal[SAMPLING_ALGORITHM]
    seed: str = Field(min_length=1)
    uniform_document_count: int = Field(ge=1)
    type_enriched_documents_per_type: int = Field(ge=1)
    total_document_count: int = Field(ge=1)
    candidate_pool_per_stratum: int = Field(ge=1)
    require_nonempty_title: Literal[True]
    require_nonempty_abstract: Literal[True]
    selection_term_matching: Literal["unicode_word_case_insensitive"]

    @model_validator(mode="after")
    def validate_counts(self) -> "ScientificEntitySamplingPolicy":
        if not self.seed.strip():
            raise ValueError("sampling seed must contain non-whitespace text")
        expected = self.uniform_document_count + (
            self.type_enriched_documents_per_type * len(ScientificEntityType)
        )
        if self.total_document_count != expected:
            raise ValueError("total_document_count does not match stratum targets")
        if self.candidate_pool_per_stratum < self.total_document_count:
            raise ValueError("candidate pool must cover the selected document count")
        return self


class ScientificEntityManualReviewPreparedManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[PREPARED_MANIFEST_SCHEMA_VERSION]
    review_id: str = Field(pattern=BUILD_ID_PATTERN)
    status: ScientificEntityReviewSampleStatus
    generated_at_utc: datetime
    config_path: str = Field(min_length=1)
    config_sha256: str = Field(pattern=SHA256_PATTERN)
    code_revision: str = Field(min_length=1)
    environment_sha256: str = Field(pattern=SHA256_PATTERN)
    source_canonical_input: ScientificEntityCanonicalInput
    sample_canonical_input: ScientificEntityCanonicalInput
    sampling_policy: ScientificEntitySamplingPolicy
    sample_assignments_file: Literal["sample_assignments.jsonl"]
    sample_assignments_sha256: str = Field(pattern=SHA256_PATTERN)
    annotation_template_file: Literal["annotation_template.jsonl"]
    annotation_template_sha256: str = Field(pattern=SHA256_PATTERN)
    annotation_row_count: int = Field(ge=1)
    uniform_document_count: int = Field(ge=1)
    type_enriched_document_count: int = Field(ge=1)
    type_enriched_count_by_type: dict[ScientificEntityType, NonNegativeInt]
    prediction_blind: Literal[True]
    review_complete: Literal[False]
    selection_terms_are_reference_annotations: Literal[False]
    full_corpus_entity_extraction_performed: Literal[False]
    canonical_truth_mutated: Literal[False]
    may_be_used_as_reconcile_input: Literal[False]
    production_extractor_selected: Literal[False]
    redistribution_allowed: Literal[False]
    publication_ready: Literal[False]

    @model_validator(mode="after")
    def validate_manifest(self) -> "ScientificEntityManualReviewPreparedManifest":
        if (
            self.generated_at_utc.tzinfo is None
            or self.generated_at_utc.utcoffset() != timedelta(0)
        ):
            raise ValueError("generated_at_utc must use UTC offset +00:00")
        if set(self.type_enriched_count_by_type) != set(ScientificEntityType):
            raise ValueError("type_enriched_count_by_type must cover all entity types")
        if sum(self.type_enriched_count_by_type.values()) != self.type_enriched_document_count:
            raise ValueError("type-enriched total does not match per-type counts")
        if self.uniform_document_count != self.sampling_policy.uniform_document_count:
            raise ValueError("uniform document count does not match sampling policy")
        if any(
            count != self.sampling_policy.type_enriched_documents_per_type
            for count in self.type_enriched_count_by_type.values()
        ):
            raise ValueError("per-type document counts do not match sampling policy")
        if (
            self.uniform_document_count + self.type_enriched_document_count
            != self.sample_canonical_input.document_count
        ):
            raise ValueError("sample document count does not match stratum counts")
        if self.sample_canonical_input.document_count != self.sampling_policy.total_document_count:
            raise ValueError("sample document count does not match sampling policy")
        expected_annotation_rows = self.sample_canonical_input.document_count * len(
            ScientificEntitySourceField
        )
        if self.annotation_row_count != expected_annotation_rows:
            raise ValueError("annotation row count must cover title and abstract")
        return self


class ScientificEntityPreparedReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_id: str = Field(pattern=BUILD_ID_PATTERN)
    status: ScientificEntityReviewSampleStatus
    directory_path: str = Field(min_length=1)
    manifest_path: str = Field(min_length=1)
    manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    sample_documents_path: str = Field(min_length=1)
    sample_documents_sha256: str = Field(pattern=SHA256_PATTERN)
    sample_document_count: int = Field(ge=1)
    sample_assignments_path: str = Field(min_length=1)
    sample_assignments_sha256: str = Field(pattern=SHA256_PATTERN)
    annotation_template_path: str = Field(min_length=1)
    annotation_template_sha256: str = Field(pattern=SHA256_PATTERN)


class ScientificEntityManualReviewCompletionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[COMPLETION_MANIFEST_SCHEMA_VERSION]
    review_id: str = Field(pattern=BUILD_ID_PATTERN)
    generated_at_utc: datetime
    prepared_review: ScientificEntityPreparedReviewInput
    annotations_file: Literal["completed_annotations.jsonl"]
    annotations_path: str = Field(min_length=1)
    annotations_sha256: str = Field(pattern=SHA256_PATTERN)
    annotation_row_count: int = Field(ge=1)
    annotation_method: ScientificEntityAnnotationMethod
    annotation_guideline_version: str = Field(min_length=1)
    annotation_passes: Literal[1]
    annotator_ids: list[str] = Field(min_length=1)
    review_status: Literal[ScientificEntityReviewStatus.REVIEWED_CANDIDATE]
    review_manifest_file: Literal["review_manifest.json"]
    review_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    reference_mentions_file: Literal["reference_mentions.jsonl"]
    reference_mentions_sha256: str = Field(pattern=SHA256_PATTERN)
    reference_mention_count: int = Field(ge=0)
    annotation_audit_file: Literal["annotation_audit_summary.json"]
    annotation_audit_sha256: str = Field(pattern=SHA256_PATTERN)
    completed_annotation_row_count: int = Field(ge=1)
    uncertain_reference_mention_count: int = Field(ge=0)
    reference_count_by_type: dict[ScientificEntityType, NonNegativeInt]
    reference_count_by_stratum: dict[ScientificEntitySampleStratum, NonNegativeInt]
    fixture_simulation: bool
    prediction_blind: Literal[True]
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
    def validate_completion(self) -> "ScientificEntityManualReviewCompletionManifest":
        if (
            self.generated_at_utc.tzinfo is None
            or self.generated_at_utc.utcoffset() != timedelta(0)
        ):
            raise ValueError("generated_at_utc must use UTC offset +00:00")
        if len(set(self.annotator_ids)) != len(self.annotator_ids):
            raise ValueError("annotator_ids must not contain duplicates")
        if any(not value.strip() for value in self.annotator_ids):
            raise ValueError("annotator_ids must contain non-whitespace text")
        if self.prepared_review.review_id != self.review_id:
            raise ValueError("prepared review_id does not match completion review_id")
        if self.fixture_simulation != (
            self.prepared_review.status == ScientificEntityReviewSampleStatus.FIXTURE
        ):
            raise ValueError("fixture_simulation does not match prepared status")
        expected_annotation_rows = self.prepared_review.sample_document_count * len(
            ScientificEntitySourceField
        )
        if self.annotation_row_count != expected_annotation_rows:
            raise ValueError("completion must cover title and abstract for every paper")
        if set(self.reference_count_by_type) != set(ScientificEntityType):
            raise ValueError("reference_count_by_type must cover all entity types")
        if set(self.reference_count_by_stratum) != set(ScientificEntitySampleStratum):
            raise ValueError("reference_count_by_stratum must cover both strata")
        if sum(self.reference_count_by_type.values()) != self.reference_mention_count:
            raise ValueError("per-type counts do not match reference mention count")
        if sum(self.reference_count_by_stratum.values()) != self.reference_mention_count:
            raise ValueError("per-stratum counts do not match reference mention count")
        if self.completed_annotation_row_count != self.annotation_row_count:
            raise ValueError("all annotation rows must be completed")
        return self
