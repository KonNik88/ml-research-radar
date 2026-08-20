from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator


MENTION_SCHEMA_VERSION = "scientific_entity_mention_evidence_v0.1"
MANIFEST_SCHEMA_VERSION = "scientific_entity_evidence_manifest_v0.1"
EXTRACTOR_SCHEMA_VERSION = "scientific_entity_extractor_descriptor_v0.1"
CANONICAL_INPUT_SCHEMA_VERSION = "scientific_entity_canonical_input_v0.1"

MENTION_ID_NAMESPACE = "scientific_entity_mention_v0.1"
EVIDENCE_ID_NAMESPACE = "scientific_entity_extraction_evidence_v0.1"
MENTION_ID_PREFIX = "mention:"
EVIDENCE_ID_PREFIX = "evidence:"
IDENTITY_HASH_LENGTH = 32

SHA256_PATTERN = r"^[0-9a-f]{64}$"
MENTION_ID_PATTERN = rf"^{MENTION_ID_PREFIX}[0-9a-f]{{{IDENTITY_HASH_LENGTH}}}$"
EVIDENCE_ID_PATTERN = rf"^{EVIDENCE_ID_PREFIX}[0-9a-f]{{{IDENTITY_HASH_LENGTH}}}$"
BUILD_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"


class ScientificEntityType(str, Enum):
    TASK = "task"
    METHOD = "method"
    DATASET = "dataset"
    METRIC = "metric"
    MODEL = "model"
    DOMAIN = "domain"


class ScientificEntitySourceField(str, Enum):
    TITLE = "title"
    ABSTRACT = "abstract"


class ExtractorKind(str, Enum):
    RULE_BASED = "rule_based"
    STATISTICAL_MODEL = "statistical_model"
    LANGUAGE_MODEL = "language_model"
    HUMAN_ANNOTATION = "human_annotation"
    IMPORTED = "imported"


class ConfidenceKind(str, Enum):
    NOT_AVAILABLE = "not_available"
    RULE_SCORE = "rule_score"
    MODEL_SCORE = "model_score"
    CALIBRATED_PROBABILITY = "calibrated_probability"


class EntityEvidenceBuildStatus(str, Enum):
    FIXTURE = "fixture"
    CANDIDATE = "candidate"
    ACCEPTED = "accepted"


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _stable_identity(prefix: str, payload: Any) -> str:
    digest = sha256_text(_canonical_json(payload))[:IDENTITY_HASH_LENGTH]
    return f"{prefix}{digest}"


class ScientificEntityExtractorDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[EXTRACTOR_SCHEMA_VERSION]
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    kind: ExtractorKind
    code_revision: str = Field(min_length=1)
    config_sha256: str = Field(pattern=SHA256_PATTERN)
    environment_sha256: str = Field(pattern=SHA256_PATTERN)
    model_name: str | None = Field(default=None, min_length=1)
    model_revision: str | None = Field(default=None, min_length=1)
    model_artifact_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    model_license: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_model_provenance(self) -> "ScientificEntityExtractorDescriptor":
        for field_name in ("name", "version", "code_revision"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"{field_name} must contain non-whitespace text")

        model_kinds = {ExtractorKind.STATISTICAL_MODEL, ExtractorKind.LANGUAGE_MODEL}
        model_values = (
            self.model_name,
            self.model_revision,
            self.model_artifact_sha256,
            self.model_license,
        )
        if self.kind in model_kinds and any(
            value is None or not str(value).strip() for value in model_values
        ):
            raise ValueError(
                "model-based extractors require model_name, model_revision, "
                "model_artifact_sha256, and model_license"
            )
        if self.kind not in model_kinds and any(value is not None for value in model_values):
            raise ValueError(
                "model provenance fields are allowed only for model-based extractors"
            )
        return self


def build_extractor_fingerprint(
    descriptor: ScientificEntityExtractorDescriptor | Mapping[str, Any],
) -> str:
    parsed = (
        descriptor
        if isinstance(descriptor, ScientificEntityExtractorDescriptor)
        else ScientificEntityExtractorDescriptor.model_validate(descriptor)
    )
    return sha256_text(_canonical_json(parsed.model_dump(mode="json")))


def build_mention_id(
    *,
    canonical_id: str,
    source_field: ScientificEntitySourceField | str,
    source_text_sha256: str,
    char_start: int,
    char_end: int,
    entity_type: ScientificEntityType | str,
) -> str:
    source_field_value = ScientificEntitySourceField(source_field).value
    entity_type_value = ScientificEntityType(entity_type).value
    payload = [
        MENTION_ID_NAMESPACE,
        canonical_id,
        source_field_value,
        source_text_sha256,
        int(char_start),
        int(char_end),
        entity_type_value,
    ]
    return _stable_identity(MENTION_ID_PREFIX, payload)


def build_evidence_id(*, mention_id: str, extractor_fingerprint: str) -> str:
    payload = [EVIDENCE_ID_NAMESPACE, mention_id, extractor_fingerprint]
    return _stable_identity(EVIDENCE_ID_PREFIX, payload)


class ScientificEntityCanonicalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[CANONICAL_INPUT_SCHEMA_VERSION]
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=SHA256_PATTERN)
    document_count: int = Field(ge=1)
    canonical_contract: Literal["CanonicalDocument"]


class ScientificEntityMentionEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[MENTION_SCHEMA_VERSION]
    evidence_id: str = Field(pattern=EVIDENCE_ID_PATTERN)
    mention_id: str = Field(pattern=MENTION_ID_PATTERN)
    build_id: str = Field(pattern=BUILD_ID_PATTERN)
    canonical_id: str = Field(min_length=1)
    entity_type: ScientificEntityType
    source_field: ScientificEntitySourceField
    source_text_sha256: str = Field(pattern=SHA256_PATTERN)
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    surface_text: str = Field(min_length=1)
    extractor_fingerprint: str = Field(pattern=SHA256_PATTERN)
    confidence_kind: ConfidenceKind
    confidence_score: float | None = Field(ge=0.0, le=1.0)
    calibration_id: str | None

    @model_validator(mode="after")
    def validate_span_and_confidence(self) -> "ScientificEntityMentionEvidence":
        if self.char_end <= self.char_start:
            raise ValueError("char_end must be greater than char_start")
        if not self.surface_text.strip():
            raise ValueError("surface_text must contain a non-whitespace span")

        if self.confidence_kind == ConfidenceKind.NOT_AVAILABLE:
            if self.confidence_score is not None or self.calibration_id is not None:
                raise ValueError(
                    "not_available confidence requires null score and calibration_id"
                )
        else:
            if self.confidence_score is None:
                raise ValueError("scored confidence kinds require confidence_score")

        if self.confidence_kind == ConfidenceKind.CALIBRATED_PROBABILITY:
            if not self.calibration_id or not self.calibration_id.strip():
                raise ValueError(
                    "calibrated_probability requires a non-empty calibration_id"
                )
        elif self.calibration_id is not None:
            raise ValueError(
                "calibration_id is allowed only for calibrated_probability"
            )
        return self


class ScientificEntityEvidenceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[MANIFEST_SCHEMA_VERSION]
    build_id: str = Field(pattern=BUILD_ID_PATTERN)
    status: EntityEvidenceBuildStatus
    generated_at_utc: datetime
    canonical_input: ScientificEntityCanonicalInput
    extractor: ScientificEntityExtractorDescriptor
    extractor_fingerprint: str = Field(pattern=SHA256_PATTERN)
    offset_unit: Literal["unicode_codepoint"]
    offset_interval: Literal["half_open"]
    source_fields: list[ScientificEntitySourceField] = Field(min_length=1)
    entity_types: list[ScientificEntityType] = Field(min_length=1)
    mentions_file: Literal["mentions.jsonl"]
    mention_count: int = Field(ge=0)
    mentions_sha256: str = Field(pattern=SHA256_PATTERN)
    canonical_truth_mutated: Literal[False]
    may_be_used_as_reconcile_input: Literal[False]
    publication_ready: Literal[False]

    @model_validator(mode="after")
    def validate_manifest_consistency(self) -> "ScientificEntityEvidenceManifest":
        if (
            self.generated_at_utc.tzinfo is None
            or self.generated_at_utc.utcoffset() != timedelta(0)
        ):
            raise ValueError("generated_at_utc must use UTC offset +00:00")
        if len(set(self.source_fields)) != len(self.source_fields):
            raise ValueError("source_fields must not contain duplicates")
        if len(set(self.entity_types)) != len(self.entity_types):
            raise ValueError("entity_types must not contain duplicates")
        expected_fingerprint = build_extractor_fingerprint(self.extractor)
        if self.extractor_fingerprint != expected_fingerprint:
            raise ValueError("extractor_fingerprint does not match extractor descriptor")
        return self


def validate_mention_evidence(
    record: ScientificEntityMentionEvidence | Mapping[str, Any],
    *,
    source_text: str,
    extractor: ScientificEntityExtractorDescriptor | Mapping[str, Any],
    manifest: ScientificEntityEvidenceManifest | Mapping[str, Any] | None = None,
) -> ScientificEntityMentionEvidence:
    parsed_record = (
        record
        if isinstance(record, ScientificEntityMentionEvidence)
        else ScientificEntityMentionEvidence.model_validate(record)
    )
    parsed_extractor = (
        extractor
        if isinstance(extractor, ScientificEntityExtractorDescriptor)
        else ScientificEntityExtractorDescriptor.model_validate(extractor)
    )
    errors: list[str] = []

    actual_text_sha256 = sha256_text(source_text)
    if parsed_record.source_text_sha256 != actual_text_sha256:
        errors.append("source_text_sha256 mismatch")

    if parsed_record.char_end > len(source_text):
        errors.append("char_end exceeds source text length")
    else:
        expected_surface = source_text[
            parsed_record.char_start : parsed_record.char_end
        ]
        if parsed_record.surface_text != expected_surface:
            errors.append("surface_text does not match the declared half-open span")

    expected_mention_id = build_mention_id(
        canonical_id=parsed_record.canonical_id,
        source_field=parsed_record.source_field,
        source_text_sha256=parsed_record.source_text_sha256,
        char_start=parsed_record.char_start,
        char_end=parsed_record.char_end,
        entity_type=parsed_record.entity_type,
    )
    if parsed_record.mention_id != expected_mention_id:
        errors.append("mention_id does not match mention identity inputs")

    expected_extractor_fingerprint = build_extractor_fingerprint(parsed_extractor)
    if parsed_record.extractor_fingerprint != expected_extractor_fingerprint:
        errors.append("extractor_fingerprint mismatch")

    expected_evidence_id = build_evidence_id(
        mention_id=parsed_record.mention_id,
        extractor_fingerprint=parsed_record.extractor_fingerprint,
    )
    if parsed_record.evidence_id != expected_evidence_id:
        errors.append("evidence_id does not match mention/extractor identity inputs")

    if manifest is not None:
        parsed_manifest = (
            manifest
            if isinstance(manifest, ScientificEntityEvidenceManifest)
            else ScientificEntityEvidenceManifest.model_validate(manifest)
        )
        if parsed_record.build_id != parsed_manifest.build_id:
            errors.append("record build_id does not match manifest")
        if parsed_record.extractor_fingerprint != parsed_manifest.extractor_fingerprint:
            errors.append("record extractor_fingerprint does not match manifest")
        if parsed_record.source_field not in parsed_manifest.source_fields:
            errors.append("record source_field is not declared by manifest")
        if parsed_record.entity_type not in parsed_manifest.entity_types:
            errors.append("record entity_type is not declared by manifest")

    if errors:
        raise ValueError("; ".join(errors))
    return parsed_record
