from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from radar_core.contracts.scientific_entity_evidence import (
    ScientificEntitySourceField,
    ScientificEntityType,
)


CONFIG_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_independent_inference_v0.3"
CASE_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_independent_inference_case_v0.3"
PREDICTION_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_independent_prediction_v0.3"
MANIFEST_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_independent_inference_manifest_v0.3"
SUMMARY_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_independent_inference_summary_v0.3"
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class ScientificEntityH2IndependentInferenceError(ValueError):
    """Raised when frozen H2 independent inference cannot be executed safely."""


class H2IndependentInferenceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    class Candidate(BaseModel):
        model_config = ConfigDict(extra="forbid")
        candidate_id: Literal[
            "scientific-entity-semantic-typer-candidate-v0.3-h2-selective-model-over-method"
        ]
        candidate_fingerprint_sha256: Literal[
            "6d3782fb1f2cc7219b7083bcf381c17c546491425e817c0f5620ff145bfa6966"
        ]
        frozen_candidate_config_path: Literal[
            "configs/scientific_entity_semantic_typer_h2_frozen_candidate_v0.3.yaml"
        ]
        parent_semantic_typer_candidate_id: Literal[
            "scientific-entity-semantic-typer-candidate-v0.3-h1"
        ]
        parent_semantic_typer_config_path: Literal[
            "configs/scientific_entity_semantic_typer_candidate_v0.3.yaml"
        ]
        parent_semantic_typer_config_sha256: Literal[
            "1d7972d965f88743fc6bc419f22e751aa94218984288974c247cdbe884712c36"
        ]
        upstream_baseline_candidate_id: Literal[
            "scientific-entity-semantic-prompt-raw-floor-extension-v0.2c"
        ]
        upstream_runtime_config_path: Literal[
            "configs/scientific_entity_gliner_semantic_prompt_raw_floor_candidate_v0.2c.yaml"
        ]
        upstream_runtime_config_sha256: Literal[
            "b9b544194183e1cdf60a4632735acb6fe24788829bd1c75941293c5cd4360da6"
        ]
        upstream_policy_config_path: Literal[
            "configs/scientific_entity_semantic_prompt_raw_floor_policy_v0.2c.yaml"
        ]
        upstream_policy_config_sha256: Literal[
            "9ad8d4f6728e49e04ed4bdc4cec6f4d2a23db82d55af71b4f71f33dabf84f62c"
        ]

    class Lineage(BaseModel):
        model_config = ConfigDict(extra="forbid")
        acceptance_gate_config_path: Literal[
            "configs/scientific_entity_semantic_typer_h2_independent_acceptance_gate_v0.3.yaml"
        ]
        acceptance_gate_config_sha256: Literal[
            "3ed17739796807046269b88aab40ced2cc10ca1e45ff67dc8965a98070c17a89"
        ]
        sample_config_path: Literal[
            "configs/scientific_entity_semantic_typer_h2_fresh_heldout_sample_v0.3.yaml"
        ]
        reference_config_path: Literal[
            "configs/scientific_entity_semantic_typer_h2_reference_freeze_v0.3.yaml"
        ]
        sample_id: Literal[
            "scientific-entity-fresh-heldout-sample-v0.3-20260919T093837653829Z"
        ]
        review_id: Literal[
            "scientific-entity-fresh-heldout-review-v0.3-20260919T093837653829Z"
        ]
        expected_document_count: Literal[48]

    class Execution(BaseModel):
        model_config = ConfigDict(extra="forbid")
        output_root: Literal[
            "data/entities/scientific_entity_semantic_typer_h2_independent_inference/v0.3"
        ]
        inference_id_prefix: Literal[
            "scientific-entity-semantic-typer-h2-independent-inference-v0.3"
        ]
        source_fields: list[Literal["title", "abstract"]] = Field(min_length=2, max_length=2)
        raw_input_threshold: Literal[0.4]
        baseline_title_threshold: Literal[0.45]
        baseline_abstract_threshold: Literal[0.625]
        h2_baseline_type: Literal[ScientificEntityType.METHOD]
        h2_semantic_typer_type: Literal[ScientificEntityType.MODEL]
        h2_score_field: Literal["score_margin"]
        h2_operator: Literal[">="]
        h2_threshold: Literal[0.1]
        preserve_baseline_otherwise: Literal[True]

        @model_validator(mode="after")
        def validate_source_fields(self) -> "H2IndependentInferenceConfig.Execution":
            if self.source_fields != ["title", "abstract"]:
                raise ValueError("source_fields drifted from frozen title/abstract order")
            return self

    class Safety(BaseModel):
        model_config = ConfigDict(extra="forbid")
        reference_must_be_frozen_before_execute: Literal[True]
        plan_runs_model_inference: Literal[False]
        reference_labels_used_for_case_construction: Literal[False]
        reference_labels_used_as_model_features: Literal[False]
        threshold_tuning_allowed: Literal[False]
        policy_revision_allowed: Literal[False]
        span_mutation_allowed: Literal[False]
        taxonomy_changes_allowed: Literal[False]
        evaluation_allowed_in_this_slice: Literal[False]
        acceptance_decision_allowed_in_this_slice: Literal[False]
        canonical_truth_mutation_allowed: Literal[False]
        production_extractor_selection_allowed: Literal[False]
        full_corpus_build_authorized: Literal[False]
        publication_allowed: Literal[False]
        overwrite_allowed: Literal[False]

    class NextSteps(BaseModel):
        model_config = ConfigDict(extra="forbid")
        after_plan: Literal["execute_frozen_h2_independent_inference_once"]
        after_execute: Literal["validate_h2_v03_independent_inference_evidence"]
        after_validation: Literal["run_h2_independent_comparative_evaluation"]

    schema_version: Literal[CONFIG_SCHEMA_VERSION]
    candidate: Candidate
    lineage: Lineage
    execution: Execution
    safety: Safety
    next_steps: NextSteps


class H2IndependentInferenceCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[CASE_SCHEMA_VERSION] = CASE_SCHEMA_VERSION
    case_id: str = Field(min_length=1)
    canonical_id: str = Field(min_length=1)
    source_field: ScientificEntitySourceField
    source_text_sha256: str = Field(pattern=SHA256_PATTERN)
    baseline_prediction_evidence_id: str = Field(min_length=1)
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    surface_text: str = Field(min_length=1)
    baseline_entity_type: ScientificEntityType
    baseline_confidence_score: float = Field(ge=0.0, le=1.0)
    left_context: str
    right_context: str

    @model_validator(mode="after")
    def validate_span(self) -> "H2IndependentInferenceCase":
        if self.char_end <= self.char_start:
            raise ValueError("H2 inference case span is invalid")
        return self


class H2IndependentPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[PREDICTION_SCHEMA_VERSION] = PREDICTION_SCHEMA_VERSION
    inference_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    canonical_id: str = Field(min_length=1)
    source_field: ScientificEntitySourceField
    source_text_sha256: str = Field(pattern=SHA256_PATTERN)
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    surface_text: str = Field(min_length=1)
    baseline_prediction_evidence_id: str = Field(min_length=1)
    baseline_entity_type: ScientificEntityType
    baseline_confidence_score: float = Field(ge=0.0, le=1.0)
    semantic_typer_candidate_id: Literal[
        "scientific-entity-semantic-typer-candidate-v0.3-h1"
    ]
    semantic_typer_predicted_entity_type: ScientificEntityType
    semantic_typer_used_baseline_fallback: bool
    semantic_typer_score_margin: float | None = Field(default=None, ge=0.0, le=1.0)
    h2_override_applied: bool
    final_entity_type: ScientificEntityType

    @model_validator(mode="after")
    def validate_span(self) -> "H2IndependentPrediction":
        if self.char_end <= self.char_start:
            raise ValueError("H2 independent prediction span is invalid")
        return self


class H2IndependentInferenceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[MANIFEST_SCHEMA_VERSION] = MANIFEST_SCHEMA_VERSION
    inference_id: str = Field(min_length=1)
    candidate_id: str
    candidate_fingerprint_sha256: str = Field(pattern=SHA256_PATTERN)
    sample_id: str
    review_id: str
    inference_config_sha256: str = Field(pattern=SHA256_PATTERN)
    acceptance_gate_config_sha256: str = Field(pattern=SHA256_PATTERN)
    sample_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    frozen_candidate_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    frozen_candidate_sha256: str = Field(pattern=SHA256_PATTERN)
    reference_completion_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    reference_mentions_sha256: str = Field(pattern=SHA256_PATTERN)
    parent_semantic_typer_config_sha256: str = Field(pattern=SHA256_PATTERN)
    upstream_runtime_config_sha256: str = Field(pattern=SHA256_PATTERN)
    upstream_policy_config_sha256: str = Field(pattern=SHA256_PATTERN)
    input_document_count: Literal[48]
    upstream_raw_mention_count: int = Field(ge=0)
    baseline_prediction_count: int = Field(ge=0)
    semantic_typer_case_count: int = Field(ge=0)
    semantic_typer_scored_count: int = Field(ge=0)
    semantic_typer_fallback_count: int = Field(ge=0)
    h2_override_count: int = Field(ge=0)
    files: dict[str, str]
    reference_frozen_before_inference: Literal[True] = True
    reference_labels_used_for_case_construction: Literal[False] = False
    reference_labels_used_as_model_features: Literal[False] = False
    upstream_model_inference_executed: Literal[True] = True
    semantic_typer_model_inference_executed: Literal[True] = True
    frozen_h2_policy_applied: Literal[True] = True
    threshold_tuning_executed: Literal[False] = False
    policy_revision_executed: Literal[False] = False
    span_mutated: Literal[False] = False
    evaluation_executed: Literal[False] = False
    acceptance_decision_made: Literal[False] = False
    canonical_truth_mutated: Literal[False] = False
    production_extractor_selected: Literal[False] = False
    full_corpus_build_authorized: Literal[False] = False
    publication_ready: Literal[False] = False
    next_slice: Literal["validate_h2_v03_independent_inference_evidence"]


class H2IndependentInferenceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[SUMMARY_SCHEMA_VERSION] = SUMMARY_SCHEMA_VERSION
    inference_id: str
    input_document_count: Literal[48]
    upstream_raw_mention_count: int = Field(ge=0)
    baseline_prediction_count: int = Field(ge=0)
    semantic_typer_case_count: int = Field(ge=0)
    semantic_typer_scored_count: int = Field(ge=0)
    semantic_typer_fallback_count: int = Field(ge=0)
    typer_coverage: float = Field(ge=0.0, le=1.0)
    h2_override_count: int = Field(ge=0)
    baseline_count_by_type: dict[str, int]
    final_count_by_type: dict[str, int]
    source_field_counts: dict[str, int]
    evaluation_executed: Literal[False] = False
    acceptance_decision_made: Literal[False] = False


def load_h2_independent_inference_config(path: str | Path) -> H2IndependentInferenceConfig:
    path = Path(path)
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ScientificEntityH2IndependentInferenceError(str(exc)) from exc
    try:
        return H2IndependentInferenceConfig.model_validate(payload)
    except Exception as exc:
        raise ScientificEntityH2IndependentInferenceError(str(exc)) from exc


def canonical_config_sha256(config: H2IndependentInferenceConfig) -> str:
    payload = json.dumps(
        config.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


__all__ = [
    "CONFIG_SCHEMA_VERSION",
    "CASE_SCHEMA_VERSION",
    "PREDICTION_SCHEMA_VERSION",
    "MANIFEST_SCHEMA_VERSION",
    "SUMMARY_SCHEMA_VERSION",
    "H2IndependentInferenceConfig",
    "H2IndependentInferenceCase",
    "H2IndependentPrediction",
    "H2IndependentInferenceManifest",
    "H2IndependentInferenceSummary",
    "ScientificEntityH2IndependentInferenceError",
    "canonical_config_sha256",
    "load_h2_independent_inference_config",
]
