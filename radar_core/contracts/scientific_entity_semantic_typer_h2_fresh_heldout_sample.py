from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


CONFIG_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_fresh_heldout_sample_config_v0.3"
MANIFEST_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_fresh_heldout_sample_manifest_v0.3"
ASSIGNMENT_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_fresh_heldout_sample_assignment_v0.3"
BLIND_ANNOTATION_SCHEMA_VERSION = "scientific_entity_blind_annotation_v0.1"
ENTITY_TYPES = ("task", "method", "dataset", "metric", "model", "domain")
SHA256_PATTERN = r"^[0-9a-f]{64}$"
CANDIDATE_ID = "scientific-entity-semantic-typer-candidate-v0.3-h2-selective-model-over-method"


class H2FreshHeldoutConfigError(ValueError):
    pass


class CandidateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: Literal[CANDIDATE_ID]
    freeze_id: str = Field(min_length=1)
    candidate_fingerprint_sha256: str = Field(pattern=SHA256_PATTERN)
    expected_freeze_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    expected_frozen_candidate_sha256: str = Field(pattern=SHA256_PATTERN)


class ConsumedEvidenceExclusionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    development_package_id: str = Field(min_length=1)
    expected_development_document_count: Literal[72]
    expected_development_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    expected_development_canonical_sha256: str = Field(pattern=SHA256_PATTERN)
    previous_fresh_heldout_sample_id: str = Field(min_length=1)
    expected_previous_heldout_document_count: Literal[48]
    expected_previous_heldout_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    expected_previous_heldout_selected_ids_sha256: str = Field(pattern=SHA256_PATTERN)
    expected_union_document_count: Literal[120]
    require_zero_overlap_between_consumed_sets: Literal[True]
    exclude_all_consumed_documents: Literal[True]


class SamplingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sampling_algorithm: Literal["deterministic_hash_uniform_and_type_enriched_v0.3_h2"]
    sampling_seed: Literal["ml-research-radar-scientific-entity-h2-fresh-heldout-v0.3"]
    canonical_input_path: str = Field(min_length=1)
    require_title: Literal[True]
    require_abstract: Literal[True]
    uniform_document_count: Literal[24]
    type_enriched_documents_per_type: Literal[4]
    expected_document_count: Literal[48]
    expected_annotation_row_count: Literal[96]
    candidate_pool_per_stratum: Literal[512]
    source_fields: list[Literal["title", "abstract"]] = Field(min_length=2, max_length=2)
    enrichment_terms: dict[str, list[str]]

    @model_validator(mode="after")
    def validate_sampling(self) -> "SamplingConfig":
        if self.source_fields != ["title", "abstract"]:
            raise ValueError("source_fields must be exactly title, abstract")
        if set(self.enrichment_terms) != set(ENTITY_TYPES):
            raise ValueError("enrichment_terms must cover exactly the six frozen entity types")
        if any(not terms for terms in self.enrichment_terms.values()):
            raise ValueError("each enrichment type must have at least one term")
        return self


class BlindnessConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prediction_blind: Literal[True]
    annotations_initially_empty: Literal[True]
    candidate_predictions_may_be_read_during_sampling: Literal[False]
    h1_predictions_may_be_read_during_sampling: Literal[False]
    h2_inference_allowed_before_reference_freeze: Literal[False]
    require_frozen_candidate_identity_before_sampling: Literal[True]


class SafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_inference_allowed: Literal[False]
    evaluation_allowed: Literal[False]
    threshold_tuning_allowed: Literal[False]
    policy_revision_allowed: Literal[False]
    canonical_truth_mutation_allowed: Literal[False]
    production_extractor_selection_allowed: Literal[False]
    full_corpus_build_authorized: Literal[False]


class LayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["scientific_entity_semantic_typer_h2_fresh_heldout_sample"]
    version: Literal["v0.3"]
    status: Literal["frozen_for_materialization"]
    layer_kind: Literal["independent_prediction_blind_heldout_sample"]


class NextStepsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    after_sample_validation: Literal["prediction_blind_manual_annotation_and_reference_freeze_for_h2"]


class H2FreshHeldoutSampleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[CONFIG_SCHEMA_VERSION]
    layer: LayerConfig
    candidate: CandidateConfig
    consumed_evidence_exclusion: ConsumedEvidenceExclusionConfig
    sampling: SamplingConfig
    blindness: BlindnessConfig
    safety: SafetyConfig
    next_steps: NextStepsConfig


class H2FreshHeldoutSampleAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[ASSIGNMENT_SCHEMA_VERSION]
    sample_id: str = Field(min_length=1)
    review_id: str = Field(min_length=1)
    canonical_id: str = Field(min_length=1)
    sample_stratum: Literal["uniform", "type_enriched"]
    enrichment_entity_type: Literal["task", "method", "dataset", "metric", "model", "domain"] | None
    selection_score: str = Field(pattern=SHA256_PATTERN)
    stratum_rank: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_assignment(self) -> "H2FreshHeldoutSampleAssignment":
        if self.sample_stratum == "uniform" and self.enrichment_entity_type is not None:
            raise ValueError("uniform assignments cannot carry enrichment_entity_type")
        if self.sample_stratum == "type_enriched" and self.enrichment_entity_type is None:
            raise ValueError("type_enriched assignments require enrichment_entity_type")
        return self


class H2FreshHeldoutSampleManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[MANIFEST_SCHEMA_VERSION]
    sample_id: str = Field(min_length=1)
    review_id: str = Field(min_length=1)
    generated_at_utc: datetime
    config_path: str = Field(min_length=1)
    config_sha256: str = Field(pattern=SHA256_PATTERN)

    candidate_id: Literal[CANDIDATE_ID]
    freeze_id: str = Field(min_length=1)
    candidate_fingerprint_sha256: str = Field(pattern=SHA256_PATTERN)
    freeze_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    frozen_candidate_sha256: str = Field(pattern=SHA256_PATTERN)

    canonical_input_path: str = Field(min_length=1)
    canonical_input_sha256: str = Field(pattern=SHA256_PATTERN)
    canonical_input_row_count: int = Field(ge=1)
    eligible_document_count_after_all_exclusions: int = Field(ge=1)

    development_package_id: str = Field(min_length=1)
    development_package_path: str = Field(min_length=1)
    development_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    development_canonical_sha256: str = Field(pattern=SHA256_PATTERN)
    excluded_development_document_count: Literal[72]

    previous_heldout_sample_id: str = Field(min_length=1)
    previous_heldout_sample_path: str = Field(min_length=1)
    previous_heldout_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    previous_heldout_selected_ids_sha256: str = Field(pattern=SHA256_PATTERN)
    excluded_previous_heldout_document_count: Literal[48]

    consumed_set_overlap_count: Literal[0]
    excluded_consumed_union_document_count: Literal[120]
    excluded_consumed_ids_found_in_canonical: Literal[120]
    sample_development_overlap_count: Literal[0]
    sample_previous_heldout_overlap_count: Literal[0]
    sample_consumed_union_overlap_count: Literal[0]

    sampling_algorithm: Literal["deterministic_hash_uniform_and_type_enriched_v0.3_h2"]
    sampling_seed: Literal["ml-research-radar-scientific-entity-h2-fresh-heldout-v0.3"]
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
    h1_predictions_read_during_sampling: Literal[False]
    h2_model_inference_executed: Literal[False]
    evaluation_executed: Literal[False]
    reference_frozen: Literal[False]
    threshold_tuning_executed: Literal[False]
    policy_revision_executed: Literal[False]
    canonical_truth_mutated: Literal[False]
    production_extractor_selected: Literal[False]
    full_corpus_build_authorized: Literal[False]

    files: dict[str, str]
    next_slice: Literal["prediction_blind_manual_annotation_and_reference_freeze_for_h2"]

    @model_validator(mode="after")
    def validate_manifest(self) -> "H2FreshHeldoutSampleManifest":
        if self.generated_at_utc.tzinfo is None or self.generated_at_utc.utcoffset() != timedelta(0):
            raise ValueError("generated_at_utc must use UTC offset +00:00")
        if len(set(self.selected_canonical_ids)) != 48:
            raise ValueError("selected_canonical_ids must contain 48 unique IDs")
        expected_files = {
            "annotations_working.jsonl",
            "sample_assignments.jsonl",
            "canonical_documents.sample.jsonl",
            "selected_papers.tsv",
            "exclusion_provenance.json",
            "README.md",
        }
        if set(self.files) != expected_files:
            raise ValueError("manifest files coverage drifted")
        return self


def load_h2_fresh_heldout_sample_config(path: Path) -> H2FreshHeldoutSampleConfig:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise H2FreshHeldoutConfigError(f"Expected YAML object: {path}")
    return H2FreshHeldoutSampleConfig.model_validate(payload)


def canonical_config_sha256(config: H2FreshHeldoutSampleConfig) -> str:
    payload = config.model_dump(mode="json")
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
