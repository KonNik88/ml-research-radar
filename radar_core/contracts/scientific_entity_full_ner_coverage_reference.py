"""Immutable full-field NER reference freeze v0.1 contracts."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class ReferenceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["scientific_entity_full_ner_coverage_reference_summary_v0.1"]
    audit_id: str
    reference_id: str
    field_count: int = Field(ge=1)
    title_count: int = Field(ge=0)
    abstract_count: int = Field(ge=0)
    mention_count: int = Field(ge=0)
    uncertain_mention_count: int = Field(ge=0)
    fields_with_uncertain_mentions: int = Field(ge=0)
    overlap_pair_count: int = Field(ge=0)
    entity_type_counts: dict[str, int]
    uncertain_entity_type_counts: dict[str, int]
    annotation_complete: bool
    uncertain_flags_preserved: bool
    prediction_blind: bool
    production_predictions_read: bool
    future_unblind_not_executed: bool


class ReferenceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["scientific_entity_full_ner_coverage_reference_manifest_v0.1"]
    audit_id: str
    reference_id: str
    sample_manifest_sha256: str
    audit_fields_sha256: str
    annotations_sha256: str
    reference_summary_sha256: str
    trusted_candidate_build_id: str
    trusted_final_mentions_sha256: str
    canonical_sha256: str
    source_working_path: str
    source_working_sha256: str
    complete_annotation_count: int
    uncertainty_policy: Literal["preserve_as_unresolved_for_preregistered_scoring"]
    unblinding_executed: Literal[False]
    production_prediction_files_read: Literal[False]
    canonical_mutated: Literal[False]
    production_latest_mutated: Literal[False]
    reference_frozen: Literal[True]
    next_slice: str
    files: dict[str, str]
