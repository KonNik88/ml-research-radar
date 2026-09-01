from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


SAMPLE_MANIFEST_SCHEMA_VERSION = "scientific_entity_fresh_heldout_sample_manifest_v0.2"
SAMPLE_ASSIGNMENT_SCHEMA_VERSION = "scientific_entity_fresh_heldout_sample_assignment_v0.2"
BLIND_ANNOTATION_SCHEMA_VERSION = "scientific_entity_blind_annotation_v0.1"
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class FreshHeldoutSampleAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[SAMPLE_ASSIGNMENT_SCHEMA_VERSION]
    sample_id: str = Field(min_length=1)
    review_id: str = Field(min_length=1)
    canonical_id: str = Field(min_length=1)
    sample_stratum: Literal["uniform", "type_enriched"]
    enrichment_entity_type: Literal[
        "task", "method", "dataset", "metric", "model", "domain"
    ] | None
    selection_score: str = Field(pattern=SHA256_PATTERN)
    stratum_rank: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_assignment(self) -> "FreshHeldoutSampleAssignment":
        if self.sample_stratum == "uniform" and self.enrichment_entity_type is not None:
            raise ValueError("uniform assignments cannot carry enrichment_entity_type")
        if self.sample_stratum == "type_enriched" and self.enrichment_entity_type is None:
            raise ValueError("type_enriched assignments require enrichment_entity_type")
        return self


class FreshHeldoutSampleManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[SAMPLE_MANIFEST_SCHEMA_VERSION]
    sample_id: str = Field(min_length=1)
    review_id: str = Field(min_length=1)
    generated_at_utc: datetime

    gate_config_path: str = Field(min_length=1)
    gate_config_sha256: str = Field(pattern=SHA256_PATTERN)
    candidate_id: Literal["scientific-entity-semantic-prompt-raw-floor-extension-v0.2c"]

    canonical_input_path: str = Field(min_length=1)
    canonical_input_sha256: str = Field(pattern=SHA256_PATTERN)
    canonical_input_row_count: int = Field(ge=1)
    eligible_non_development_document_count: int = Field(ge=1)

    development_package_id: Literal[
        "scientific-entity-semantic-prompt-development-v0.2a-20260829T140201009151Z"
    ]
    development_package_path: str = Field(min_length=1)
    development_package_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    development_package_canonical_sha256: str = Field(pattern=SHA256_PATTERN)
    excluded_development_document_count: Literal[72]
    excluded_development_ids_found_in_canonical: Literal[72]
    heldout_development_overlap_count: Literal[0]

    sampling_algorithm: Literal["deterministic_hash_uniform_and_type_enriched_v0.2"]
    sampling_seed: Literal["ml-research-radar-scientific-entity-fresh-heldout-v0.2"]
    candidate_pool_per_stratum: Literal[512]
    uniform_document_count: Literal[24]
    type_enriched_documents_per_type: Literal[4]
    type_enrichment_terms: dict[str, list[str]]
    selected_document_count: Literal[48]
    annotation_row_count: Literal[96]
    selected_canonical_ids: list[str] = Field(min_length=48, max_length=48)

    prediction_blind: Literal[True]
    annotations_initially_empty: Literal[True]
    candidate_predictions_read_during_sampling: Literal[False]
    model_inference_executed: Literal[False]
    evaluation_executed: Literal[False]
    fresh_heldout_reference_consumed: Literal[False]
    canonical_truth_mutated: Literal[False]
    production_extractor_selected: Literal[False]
    full_corpus_build_authorized: Literal[False]

    files: dict[str, str]
    next_slice: Literal["prediction_blind_manual_annotation_and_reference_freeze"]

    @model_validator(mode="after")
    def validate_manifest(self) -> "FreshHeldoutSampleManifest":
        if (
            self.generated_at_utc.tzinfo is None
            or self.generated_at_utc.utcoffset() != timedelta(0)
        ):
            raise ValueError("generated_at_utc must use UTC offset +00:00")
        if len(set(self.selected_canonical_ids)) != 48:
            raise ValueError("selected_canonical_ids must contain 48 unique IDs")
        expected_files = {
            "annotations_working.jsonl",
            "sample_assignments.jsonl",
            "canonical_documents.sample.jsonl",
            "selected_papers.tsv",
            "README.md",
        }
        if set(self.files) != expected_files:
            raise ValueError("manifest files coverage drifted")
        return self
