from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

EntityType = Literal["task", "method", "dataset", "metric", "model", "domain"]
SourceField = Literal["title", "abstract"]


class FullNerCoverageAuditField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["scientific_entity_full_ner_coverage_audit_field_v0.1"]
    audit_id: str
    audit_case_id: str
    canonical_id: str
    source_field: SourceField
    source_text: str
    source_text_sha256: str


class FullNerCoverageMention(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: EntityType
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    surface_text: str
    uncertain: bool = False
    reviewer_note: str | None = None

    @model_validator(mode="after")
    def _check_bounds(self) -> "FullNerCoverageMention":
        if self.char_end <= self.char_start:
            raise ValueError("char_end must be greater than char_start")
        return self


class FullNerCoverageAnnotationRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["scientific_entity_full_ner_coverage_annotation_working_v0.1"]
    audit_id: str
    audit_case_id: str
    canonical_id: str
    source_field: SourceField
    source_text: str
    source_text_sha256: str
    mentions: list[FullNerCoverageMention]
    annotation_complete: bool
    reviewer_note: str | None = None

    @model_validator(mode="after")
    def _check_mentions(self) -> "FullNerCoverageAnnotationRow":
        for mention in self.mentions:
            if mention.char_end > len(self.source_text):
                raise ValueError("mention char_end exceeds source_text length")
            if self.source_text[mention.char_start : mention.char_end] != mention.surface_text:
                raise ValueError("surface_text does not match source_text offsets")
        return self
