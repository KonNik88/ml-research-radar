from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from radar_core.contracts.scientific_entity_evidence import (
    BUILD_ID_PATTERN,
    EVIDENCE_ID_PATTERN,
    MENTION_ID_PATTERN,
    SHA256_PATTERN,
    ScientificEntityCanonicalInput,
    ScientificEntitySourceField,
    ScientificEntityType,
    build_mention_id,
    sha256_text,
)


REFERENCE_MENTION_SCHEMA_VERSION = "scientific_entity_reference_mention_v0.1"
REVIEW_MANIFEST_SCHEMA_VERSION = "scientific_entity_review_manifest_v0.1"
EVALUATION_MANIFEST_SCHEMA_VERSION = "scientific_entity_evaluation_manifest_v0.1"
EVALUATION_MATCH_SCHEMA_VERSION = "scientific_entity_evaluation_match_v0.1"
EVALUATION_ERROR_SCHEMA_VERSION = "scientific_entity_evaluation_error_v0.1"
METRICS_SCHEMA_VERSION = "scientific_entity_evaluation_metrics_v0.1"
PER_TYPE_METRICS_SCHEMA_VERSION = "scientific_entity_per_type_metrics_v0.1"

REFERENCE_ID_NAMESPACE = "scientific_entity_reference_v0.1"
MATCH_ID_NAMESPACE = "scientific_entity_evaluation_match_v0.1"
ERROR_ID_NAMESPACE = "scientific_entity_evaluation_error_v0.1"
REFERENCE_ID_PREFIX = "reference:"
MATCH_ID_PREFIX = "evalmatch:"
ERROR_ID_PREFIX = "evalerror:"
IDENTITY_HASH_LENGTH = 32

REFERENCE_ID_PATTERN = rf"^{REFERENCE_ID_PREFIX}[0-9a-f]{{{IDENTITY_HASH_LENGTH}}}$"
MATCH_ID_PATTERN = rf"^{MATCH_ID_PREFIX}[0-9a-f]{{{IDENTITY_HASH_LENGTH}}}$"
ERROR_ID_PATTERN = rf"^{ERROR_ID_PREFIX}[0-9a-f]{{{IDENTITY_HASH_LENGTH}}}$"
EVALUATION_ID_PATTERN = BUILD_ID_PATTERN
REVIEW_ID_PATTERN = BUILD_ID_PATTERN


class ScientificEntityReviewStatus(str, Enum):
    FIXTURE = "fixture"
    REVIEWED_CANDIDATE = "reviewed_candidate"


class ScientificEntityEvaluationStatus(str, Enum):
    FIXTURE = "fixture"
    CANDIDATE = "candidate"


class ScientificEntityAnnotationMethod(str, Enum):
    SYNTHETIC_FIXTURE = "synthetic_fixture"
    MANUAL_INDEPENDENT = "manual_independent"
    MANUAL_ADJUDICATED = "manual_adjudicated"


class ScientificEntityMatchKind(str, Enum):
    EXACT = "exact"
    RELAXED = "relaxed"


class ScientificEntityEvaluationErrorKind(str, Enum):
    BOUNDARY_MISMATCH = "boundary_mismatch"
    TYPE_MISMATCH = "type_mismatch"
    FALSE_POSITIVE = "false_positive"
    FALSE_NEGATIVE = "false_negative"


class ScientificEntityManualErrorLabel(str, Enum):
    FALSE_POSITIVE_GENERIC_TERM = "false_positive_generic_term"
    FALSE_POSITIVE_LEXICAL_AMBIGUITY = "false_positive_lexical_ambiguity"
    MISSED_ENTITY = "missed_entity"
    WRONG_ENTITY_TYPE = "wrong_entity_type"
    BOUNDARY_TOO_NARROW = "boundary_too_narrow"
    BOUNDARY_TOO_WIDE = "boundary_too_wide"
    ALIAS_OR_ACRONYM_MISS = "alias_or_acronym_miss"
    DATASET_MODEL_AMBIGUITY = "dataset_model_ambiguity"
    TASK_DOMAIN_AMBIGUITY = "task_domain_ambiguity"
    ANNOTATION_UNCERTAINTY = "annotation_uncertainty"


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _stable_identity(prefix: str, payload: Any) -> str:
    digest = sha256_text(_canonical_json(payload))[:IDENTITY_HASH_LENGTH]
    return f"{prefix}{digest}"


def build_reference_id(
    *,
    review_id: str,
    mention_id: str,
    annotation_method: ScientificEntityAnnotationMethod | str,
    annotation_pass: int,
) -> str:
    payload = [
        REFERENCE_ID_NAMESPACE,
        review_id,
        mention_id,
        ScientificEntityAnnotationMethod(annotation_method).value,
        int(annotation_pass),
    ]
    return _stable_identity(REFERENCE_ID_PREFIX, payload)


def build_evaluation_match_id(
    *,
    evaluation_id: str,
    match_kind: ScientificEntityMatchKind | str,
    reference_id: str,
    evidence_id: str,
) -> str:
    payload = [
        MATCH_ID_NAMESPACE,
        evaluation_id,
        ScientificEntityMatchKind(match_kind).value,
        reference_id,
        evidence_id,
    ]
    return _stable_identity(MATCH_ID_PREFIX, payload)


def build_evaluation_error_id(
    *,
    evaluation_id: str,
    error_kind: ScientificEntityEvaluationErrorKind | str,
    reference_id: str | None,
    evidence_id: str | None,
) -> str:
    payload = [
        ERROR_ID_NAMESPACE,
        evaluation_id,
        ScientificEntityEvaluationErrorKind(error_kind).value,
        reference_id,
        evidence_id,
    ]
    return _stable_identity(ERROR_ID_PREFIX, payload)


class ScientificEntityReferenceMention(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[REFERENCE_MENTION_SCHEMA_VERSION]
    reference_id: str = Field(pattern=REFERENCE_ID_PATTERN)
    mention_id: str = Field(pattern=MENTION_ID_PATTERN)
    review_id: str = Field(pattern=REVIEW_ID_PATTERN)
    canonical_id: str = Field(min_length=1)
    entity_type: ScientificEntityType
    source_field: ScientificEntitySourceField
    source_text_sha256: str = Field(pattern=SHA256_PATTERN)
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    surface_text: str = Field(min_length=1)
    annotation_method: ScientificEntityAnnotationMethod
    annotation_pass: int = Field(ge=1)
    uncertain: bool

    @model_validator(mode="after")
    def validate_reference_identity(self) -> "ScientificEntityReferenceMention":
        if self.char_end <= self.char_start:
            raise ValueError("char_end must be greater than char_start")
        if not self.canonical_id.strip():
            raise ValueError("canonical_id must contain non-whitespace text")
        if not self.surface_text.strip():
            raise ValueError("surface_text must contain a non-whitespace span")
        expected_mention_id = build_mention_id(
            canonical_id=self.canonical_id,
            source_field=self.source_field,
            source_text_sha256=self.source_text_sha256,
            char_start=self.char_start,
            char_end=self.char_end,
            entity_type=self.entity_type,
        )
        if self.mention_id != expected_mention_id:
            raise ValueError("mention_id does not match reference mention identity")
        expected_reference_id = build_reference_id(
            review_id=self.review_id,
            mention_id=self.mention_id,
            annotation_method=self.annotation_method,
            annotation_pass=self.annotation_pass,
        )
        if self.reference_id != expected_reference_id:
            raise ValueError("reference_id does not match reference identity inputs")
        return self


def validate_reference_mention(
    record: ScientificEntityReferenceMention | Mapping[str, Any],
    *,
    source_text: str,
    review_id: str | None = None,
) -> ScientificEntityReferenceMention:
    parsed = (
        record
        if isinstance(record, ScientificEntityReferenceMention)
        else ScientificEntityReferenceMention.model_validate(record)
    )
    errors: list[str] = []
    if parsed.source_text_sha256 != sha256_text(source_text):
        errors.append("source_text_sha256 mismatch")
    if parsed.char_end > len(source_text):
        errors.append("char_end exceeds source text length")
    elif source_text[parsed.char_start : parsed.char_end] != parsed.surface_text:
        errors.append("surface_text does not match the declared half-open span")
    if review_id is not None and parsed.review_id != review_id:
        errors.append("reference review_id does not match review manifest")
    if errors:
        raise ValueError("; ".join(errors))
    return parsed


class ScientificEntityReviewManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[REVIEW_MANIFEST_SCHEMA_VERSION]
    review_id: str = Field(pattern=REVIEW_ID_PATTERN)
    status: ScientificEntityReviewStatus
    generated_at_utc: datetime
    canonical_input: ScientificEntityCanonicalInput
    annotation_method: ScientificEntityAnnotationMethod
    annotation_guideline_version: str = Field(min_length=1)
    annotation_passes: int = Field(ge=1)
    annotator_ids: list[str]
    prediction_blind: bool
    review_complete: Literal[True]
    source_fields: list[ScientificEntitySourceField] = Field(min_length=1)
    entity_types: list[ScientificEntityType] = Field(min_length=1)
    reference_mentions_file: Literal["reference_mentions.jsonl"]
    reference_mention_count: int = Field(ge=0)
    reference_mentions_sha256: str = Field(pattern=SHA256_PATTERN)
    canonical_truth_mutated: Literal[False]
    may_be_used_as_reconcile_input: Literal[False]
    redistribution_allowed: Literal[False]
    publication_ready: Literal[False]

    @model_validator(mode="after")
    def validate_review_manifest(self) -> "ScientificEntityReviewManifest":
        if (
            self.generated_at_utc.tzinfo is None
            or self.generated_at_utc.utcoffset() != timedelta(0)
        ):
            raise ValueError("generated_at_utc must use UTC offset +00:00")
        if len(set(self.source_fields)) != len(self.source_fields):
            raise ValueError("source_fields must not contain duplicates")
        if len(set(self.entity_types)) != len(self.entity_types):
            raise ValueError("entity_types must not contain duplicates")
        if len(set(self.annotator_ids)) != len(self.annotator_ids):
            raise ValueError("annotator_ids must not contain duplicates")
        if any(not value.strip() for value in self.annotator_ids):
            raise ValueError("annotator_ids must contain non-whitespace text")
        if self.annotation_method == ScientificEntityAnnotationMethod.SYNTHETIC_FIXTURE:
            if self.status != ScientificEntityReviewStatus.FIXTURE:
                raise ValueError("synthetic_fixture annotation requires fixture status")
            if self.annotator_ids:
                raise ValueError("synthetic fixture must not claim human annotators")
        else:
            if self.status != ScientificEntityReviewStatus.REVIEWED_CANDIDATE:
                raise ValueError("manual annotation requires reviewed_candidate status")
            if not self.annotator_ids:
                raise ValueError("manual annotation requires at least one annotator_id")
            if not self.prediction_blind:
                raise ValueError("v0.1 manual reference annotation must be prediction blind")
        return self


class ScientificEntityReviewInputDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_id: str = Field(pattern=REVIEW_ID_PATTERN)
    status: ScientificEntityReviewStatus
    manifest_path: str = Field(min_length=1)
    manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    reference_mentions_path: str = Field(min_length=1)
    reference_mentions_sha256: str = Field(pattern=SHA256_PATTERN)
    reference_mention_count: int = Field(ge=0)
    review_complete: Literal[True]
    prediction_blind: bool


class ScientificEntityPredictionInputDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    build_id: str = Field(pattern=BUILD_ID_PATTERN)
    status: Literal["fixture", "candidate"]
    manifest_path: str = Field(min_length=1)
    manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    mentions_path: str = Field(min_length=1)
    mentions_sha256: str = Field(pattern=SHA256_PATTERN)
    mention_count: int = Field(ge=0)
    extractor_fingerprint: str = Field(pattern=SHA256_PATTERN)


class ScientificEntityMatchingPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exact_requires_same_entity_type: Literal[True]
    exact_requires_same_span: Literal[True]
    exact_requires_same_text_identity: Literal[True]
    relaxed_enabled: Literal[True]
    relaxed_min_char_iou: float = Field(gt=0.0, le=1.0)
    relaxed_requires_same_entity_type: Literal[True]
    relaxed_requires_same_text_identity: Literal[True]
    relaxed_assignment: Literal["deterministic_greedy_iou_desc_v0.1"]
    one_to_one: Literal[True]


class ScientificEntityMetricCounts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    true_positive: int = Field(ge=0)
    false_positive: int = Field(ge=0)
    false_negative: int = Field(ge=0)
    reference_support: int = Field(ge=0)
    prediction_support: int = Field(ge=0)
    precision_denominator: int = Field(ge=0)
    recall_denominator: int = Field(ge=0)
    precision: float | None = Field(default=None, ge=0.0, le=1.0)
    recall: float | None = Field(default=None, ge=0.0, le=1.0)
    f1: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_counts(self) -> "ScientificEntityMetricCounts":
        if self.precision_denominator != self.true_positive + self.false_positive:
            raise ValueError("precision_denominator does not match TP + FP")
        if self.recall_denominator != self.true_positive + self.false_negative:
            raise ValueError("recall_denominator does not match TP + FN")
        if self.prediction_support != self.precision_denominator:
            raise ValueError("prediction_support does not match precision denominator")
        if self.reference_support != self.recall_denominator:
            raise ValueError("reference_support does not match recall denominator")
        if (self.precision_denominator == 0) != (self.precision is None):
            raise ValueError("precision nullability does not match denominator")
        if (self.recall_denominator == 0) != (self.recall is None):
            raise ValueError("recall nullability does not match denominator")
        if self.precision is None or self.recall is None:
            if self.f1 is not None:
                raise ValueError("f1 must be null when precision or recall is null")
        return self


class ScientificEntityMatchingMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exact: ScientificEntityMetricCounts
    relaxed: ScientificEntityMetricCounts


class ScientificEntityDataSufficiency(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minimum_document_count: int = Field(ge=1)
    minimum_reference_mentions_per_type: int = Field(ge=1)
    document_count_sufficient: bool
    per_type_support_sufficient: dict[ScientificEntityType, bool]
    promotion_sample_sufficient: Literal[False]
    metrics_are_descriptive_only: Literal[True]

    @model_validator(mode="after")
    def validate_type_coverage(self) -> "ScientificEntityDataSufficiency":
        if set(self.per_type_support_sufficient) != set(ScientificEntityType):
            raise ValueError("per_type_support_sufficient must cover all entity types")
        return self


class ScientificEntityEvaluationMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[METRICS_SCHEMA_VERSION]
    evaluation_id: str = Field(pattern=EVALUATION_ID_PATTERN)
    document_count: int = Field(ge=1)
    reference_mention_count: int = Field(ge=0)
    prediction_mention_count: int = Field(ge=0)
    matching_policy: ScientificEntityMatchingPolicy
    micro: ScientificEntityMatchingMetrics
    by_source_field: dict[ScientificEntitySourceField, ScientificEntityMatchingMetrics]
    exact_match_count: int = Field(ge=0)
    relaxed_only_match_count: int = Field(ge=0)
    error_count_by_kind: dict[ScientificEntityEvaluationErrorKind, int]
    data_sufficiency: ScientificEntityDataSufficiency
    production_extractor_selected: Literal[False]
    full_corpus_build_authorized: Literal[False]
    canonical_truth_mutated: Literal[False]
    publication_ready: Literal[False]

    @model_validator(mode="after")
    def validate_metric_coverage(self) -> "ScientificEntityEvaluationMetrics":
        if set(self.by_source_field) != set(ScientificEntitySourceField):
            raise ValueError("by_source_field must cover title and abstract")
        if set(self.error_count_by_kind) != set(ScientificEntityEvaluationErrorKind):
            raise ValueError("error_count_by_kind must cover all automatic error kinds")
        return self


class ScientificEntityPerTypeMetricRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: ScientificEntityType
    metrics: ScientificEntityMatchingMetrics
    support_sufficient: bool


class ScientificEntityPerTypeMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[PER_TYPE_METRICS_SCHEMA_VERSION]
    evaluation_id: str = Field(pattern=EVALUATION_ID_PATTERN)
    minimum_reference_mentions_per_type: int = Field(ge=1)
    rows: list[ScientificEntityPerTypeMetricRow]

    @model_validator(mode="after")
    def validate_rows(self) -> "ScientificEntityPerTypeMetrics":
        entity_types = [row.entity_type for row in self.rows]
        if entity_types != list(ScientificEntityType):
            raise ValueError("per-type rows must cover all entity types in enum order")
        return self


class ScientificEntityEvaluationMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[EVALUATION_MATCH_SCHEMA_VERSION]
    match_id: str = Field(pattern=MATCH_ID_PATTERN)
    evaluation_id: str = Field(pattern=EVALUATION_ID_PATTERN)
    match_kind: ScientificEntityMatchKind
    reference_id: str = Field(pattern=REFERENCE_ID_PATTERN)
    reference_mention_id: str = Field(pattern=MENTION_ID_PATTERN)
    prediction_evidence_id: str = Field(pattern=EVIDENCE_ID_PATTERN)
    prediction_mention_id: str = Field(pattern=MENTION_ID_PATTERN)
    canonical_id: str = Field(min_length=1)
    source_field: ScientificEntitySourceField
    source_text_sha256: str = Field(pattern=SHA256_PATTERN)
    entity_type: ScientificEntityType
    reference_char_start: int = Field(ge=0)
    reference_char_end: int = Field(gt=0)
    prediction_char_start: int = Field(ge=0)
    prediction_char_end: int = Field(gt=0)
    intersection_length: int = Field(gt=0)
    union_length: int = Field(gt=0)
    char_iou: float = Field(gt=0.0, le=1.0)
    boundary_distance: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_match(self) -> "ScientificEntityEvaluationMatch":
        if self.reference_char_end <= self.reference_char_start:
            raise ValueError("invalid reference span")
        if self.prediction_char_end <= self.prediction_char_start:
            raise ValueError("invalid prediction span")
        expected_match_id = build_evaluation_match_id(
            evaluation_id=self.evaluation_id,
            match_kind=self.match_kind,
            reference_id=self.reference_id,
            evidence_id=self.prediction_evidence_id,
        )
        if self.match_id != expected_match_id:
            raise ValueError("match_id does not match match identity inputs")
        if self.match_kind == ScientificEntityMatchKind.EXACT:
            if (
                self.reference_char_start != self.prediction_char_start
                or self.reference_char_end != self.prediction_char_end
                or self.char_iou != 1.0
                or self.boundary_distance != 0
            ):
                raise ValueError("exact match requires identical spans and IoU 1")
        return self


class ScientificEntityEvaluationError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[EVALUATION_ERROR_SCHEMA_VERSION]
    error_id: str = Field(pattern=ERROR_ID_PATTERN)
    evaluation_id: str = Field(pattern=EVALUATION_ID_PATTERN)
    error_kind: ScientificEntityEvaluationErrorKind
    canonical_id: str = Field(min_length=1)
    source_field: ScientificEntitySourceField
    source_text_sha256: str = Field(pattern=SHA256_PATTERN)
    reference_id: str | None = Field(default=None, pattern=REFERENCE_ID_PATTERN)
    prediction_evidence_id: str | None = Field(default=None, pattern=EVIDENCE_ID_PATTERN)
    reference_entity_type: ScientificEntityType | None = None
    prediction_entity_type: ScientificEntityType | None = None
    reference_char_start: int | None = Field(default=None, ge=0)
    reference_char_end: int | None = Field(default=None, gt=0)
    prediction_char_start: int | None = Field(default=None, ge=0)
    prediction_char_end: int | None = Field(default=None, gt=0)
    char_iou: float | None = Field(default=None, ge=0.0, le=1.0)
    manual_label: ScientificEntityManualErrorLabel | None = None

    @model_validator(mode="after")
    def validate_error(self) -> "ScientificEntityEvaluationError":
        expected_error_id = build_evaluation_error_id(
            evaluation_id=self.evaluation_id,
            error_kind=self.error_kind,
            reference_id=self.reference_id,
            evidence_id=self.prediction_evidence_id,
        )
        if self.error_id != expected_error_id:
            raise ValueError("error_id does not match error identity inputs")

        has_reference = self.reference_id is not None
        has_prediction = self.prediction_evidence_id is not None
        if self.error_kind == ScientificEntityEvaluationErrorKind.FALSE_POSITIVE:
            if has_reference or not has_prediction:
                raise ValueError("false_positive requires prediction only")
        elif self.error_kind == ScientificEntityEvaluationErrorKind.FALSE_NEGATIVE:
            if not has_reference or has_prediction:
                raise ValueError("false_negative requires reference only")
        elif not (has_reference and has_prediction):
            raise ValueError("paired errors require reference and prediction")

        reference_span = (self.reference_char_start, self.reference_char_end)
        prediction_span = (self.prediction_char_start, self.prediction_char_end)
        if has_reference and any(value is None for value in reference_span):
            raise ValueError("reference identity requires a complete reference span")
        if not has_reference and any(value is not None for value in reference_span):
            raise ValueError("reference span is forbidden without reference identity")
        if has_prediction and any(value is None for value in prediction_span):
            raise ValueError("prediction identity requires a complete prediction span")
        if not has_prediction and any(value is not None for value in prediction_span):
            raise ValueError("prediction span is forbidden without prediction identity")
        return self


class ScientificEntityEvaluationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[EVALUATION_MANIFEST_SCHEMA_VERSION]
    evaluation_id: str = Field(pattern=EVALUATION_ID_PATTERN)
    status: ScientificEntityEvaluationStatus
    generated_at_utc: datetime
    config_path: str = Field(min_length=1)
    config_sha256: str = Field(pattern=SHA256_PATTERN)
    canonical_input: ScientificEntityCanonicalInput
    review: ScientificEntityReviewInputDescriptor
    prediction: ScientificEntityPredictionInputDescriptor
    matching_policy: ScientificEntityMatchingPolicy
    metrics_file: Literal["metrics.json"]
    metrics_sha256: str = Field(pattern=SHA256_PATTERN)
    per_type_metrics_file: Literal["per_type_metrics.json"]
    per_type_metrics_sha256: str = Field(pattern=SHA256_PATTERN)
    matches_file: Literal["matches.jsonl"]
    matches_sha256: str = Field(pattern=SHA256_PATTERN)
    match_count: int = Field(ge=0)
    errors_file: Literal["errors.jsonl"]
    errors_sha256: str = Field(pattern=SHA256_PATTERN)
    error_count: int = Field(ge=0)
    canonical_truth_mutated: Literal[False]
    may_be_used_as_reconcile_input: Literal[False]
    production_extractor_selected: Literal[False]
    full_corpus_build_authorized: Literal[False]
    model_downloaded: Literal[False]
    provider_api_called: Literal[False]
    redistribution_allowed: Literal[False]
    publication_ready: Literal[False]

    @model_validator(mode="after")
    def validate_manifest(self) -> "ScientificEntityEvaluationManifest":
        if (
            self.generated_at_utc.tzinfo is None
            or self.generated_at_utc.utcoffset() != timedelta(0)
        ):
            raise ValueError("generated_at_utc must use UTC offset +00:00")
        if self.status == ScientificEntityEvaluationStatus.FIXTURE:
            if self.review.status != ScientificEntityReviewStatus.FIXTURE:
                raise ValueError("fixture evaluation requires fixture review")
            if self.prediction.status != "fixture":
                raise ValueError("fixture evaluation requires fixture predictions")
        return self


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
