from __future__ import annotations

import hashlib
import json
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from radar_core.contracts.scientific_entity_evidence import ScientificEntityType


CONFIG_SCHEMA_VERSION = "scientific_entity_semantic_typer_candidate_v0.3"
DEV_CASE_SCHEMA_VERSION = "scientific_entity_semantic_typer_development_case_v0.3"
PREDICTION_SCHEMA_VERSION = "scientific_entity_semantic_typer_prediction_v0.3"
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class CandidateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: Literal["scientific-entity-semantic-typer-candidate-v0.3-h1"]
    status: Literal["development_candidate_design_frozen"]
    hypothesis: Literal[
        "target_focused_second_stage_semantic_typing_over_frozen_spans"
    ]
    upstream_runtime_config_path: Literal[
        "configs/scientific_entity_gliner_semantic_prompt_raw_floor_candidate_v0.2c.yaml"
    ]
    upstream_candidate_id: Literal[
        "scientific-entity-semantic-prompt-raw-floor-extension-v0.2c"
    ]
    canonical_entity_types: list[ScientificEntityType] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def validate_entity_types(self) -> "CandidateConfig":
        if self.canonical_entity_types != list(ScientificEntityType):
            raise ValueError("canonical_entity_types must match the frozen six-type order")
        return self


class ParentEvidenceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluation_id: str
    evaluation_root: str
    root_cause_review_id: str
    root_cause_review_root: str
    typing_diagnostics_id: str
    typing_diagnostics_root: str
    expected_document_count: int = Field(ge=1)
    expected_reference_mention_count: int = Field(ge=1)
    expected_prediction_mention_count: int = Field(ge=1)
    expected_type_mismatch_count: int = Field(ge=1)
    expected_same_span_type_mismatch_count: int = Field(ge=1)
    expected_same_span_reference_issue_count: int = Field(ge=0)


class SemanticTyperLabelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: ScientificEntityType
    prompt: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_prompt(self) -> "SemanticTyperLabelConfig":
        if self.prompt != self.prompt.strip():
            raise ValueError("semantic typer prompt must be trimmed")
        if not self.prompt:
            raise ValueError("semantic typer prompt must not be blank")
        return self


class SemanticTypingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: Literal["target_focused_gliner_multi_label_rescoring"]
    synthetic_target_prefix: Literal["Target entity: "]
    synthetic_context_prefix: Literal["Context: "]
    target_marker: Literal["[TARGET]"]
    context_left_chars: int = Field(ge=0, le=2000)
    context_right_chars: int = Field(ge=0, le=2000)
    inference_threshold: Literal[0.0]
    flat_ner: Literal[False]
    multi_label: Literal[True]
    selection: Literal["highest_exact_target_score"]
    tie_breaker: Literal["canonical_entity_type_order"]
    unscorable_policy: Literal["preserve_baseline_type"]
    labels: list[SemanticTyperLabelConfig] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def validate_labels(self) -> "SemanticTypingConfig":
        entity_types = [item.entity_type for item in self.labels]
        prompts = [item.prompt.casefold() for item in self.labels]
        if entity_types != list(ScientificEntityType):
            raise ValueError("semantic typer labels must follow canonical entity type order")
        if len(set(prompts)) != len(prompts):
            raise ValueError("semantic typer prompts must be unique")
        return self


class DevelopmentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["consumed_fresh_v02c_development_evidence_only"]
    include_exact_baseline_matches: Literal[True]
    include_same_span_type_mismatches: Literal[True]
    include_different_span_cases: Literal[False]
    include_false_positive_cases: Literal[False]
    include_false_negative_cases: Literal[False]
    primary_metric_excludes_reference_issue: Literal[True]
    preserve_source_order: Literal[True]
    development_root: str
    required_files: list[str] = Field(min_length=5, max_length=5)

    @model_validator(mode="after")
    def validate_required_files(self) -> "DevelopmentConfig":
        expected = {
            "manifest.json",
            "development_cases.jsonl",
            "summary.json",
            "README.md",
            "checksums.txt",
        }
        if set(self.required_files) != expected:
            raise ValueError("development required_files drifted")
        return self


class DevelopmentGateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    minimum_typer_coverage: float = Field(gt=0.0, le=1.0)
    minimum_same_span_accuracy_delta: float = Field(ge=0.0, le=1.0)
    minimum_net_corrected_cases: int = Field(ge=1)
    maximum_regression_rate: float = Field(ge=0.0, lt=1.0)
    minimum_model_to_method_reduction_fraction: float = Field(ge=0.0, le=1.0)
    maximum_macro_f1_drop: float = Field(ge=0.0, le=1.0)
    decision_role: Literal[
        "development_candidate_gate_not_independent_acceptance"
    ]


class SafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_inference_allowed_in_prepare: Literal[False]
    threshold_tuning_allowed: Literal[False]
    span_mutation_allowed: Literal[False]
    taxonomy_changes_allowed: Literal[False]
    canonical_truth_mutation_allowed: Literal[False]
    production_extractor_selection_allowed: Literal[False]
    full_corpus_build_authorized: Literal[False]
    publication_allowed: Literal[False]
    root_cause_labels_as_model_features_allowed: Literal[False]
    baseline_type_as_model_feature_allowed: Literal[False]
    future_candidate_requires_new_independent_heldout: Literal[True]


class ScientificEntitySemanticTyperConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[CONFIG_SCHEMA_VERSION]
    candidate: CandidateConfig
    parent_evidence: ParentEvidenceConfig
    semantic_typing: SemanticTypingConfig
    development: DevelopmentConfig
    development_gate: DevelopmentGateConfig
    safety: SafetyConfig
    next_steps: dict[str, str]


class SemanticTyperDevelopmentCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[DEV_CASE_SCHEMA_VERSION] = DEV_CASE_SCHEMA_VERSION
    case_id: str
    evaluation_id: str
    canonical_id: str
    source_field: Literal["title", "abstract"]
    source_text_sha256: str = Field(pattern=SHA256_PATTERN)
    reference_id: str
    baseline_prediction_evidence_id: str
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    surface_text: str = Field(min_length=1)
    reference_entity_type: ScientificEntityType
    baseline_entity_type: ScientificEntityType
    baseline_correct: bool
    baseline_confidence_score: float | None = Field(default=None, ge=0.0, le=1.0)
    left_context: str
    right_context: str
    root_cause: str | None = None
    ambiguity_level: str | None = None
    reference_type_confirmed: bool | None = None
    primary_metric_eligible: bool

    @model_validator(mode="after")
    def validate_case(self) -> "SemanticTyperDevelopmentCase":
        if self.char_end <= self.char_start:
            raise ValueError("development case span is invalid")
        if self.baseline_correct != (self.reference_entity_type == self.baseline_entity_type):
            raise ValueError("baseline_correct does not match type equality")
        if not self.surface_text.strip():
            raise ValueError("surface_text must not be blank")
        if self.root_cause == "annotation_reference_issue" and self.primary_metric_eligible:
            raise ValueError("annotation reference issues must be excluded from primary metrics")
        return self


class SemanticTyperPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[PREDICTION_SCHEMA_VERSION] = PREDICTION_SCHEMA_VERSION
    case_id: str
    candidate_id: Literal["scientific-entity-semantic-typer-candidate-v0.3-h1"]
    predicted_entity_type: ScientificEntityType
    used_baseline_fallback: bool
    selected_score: float | None = Field(default=None, ge=0.0, le=1.0)
    second_best_entity_type: ScientificEntityType | None = None
    second_best_score: float | None = Field(default=None, ge=0.0, le=1.0)
    score_margin: float | None = Field(default=None, ge=0.0, le=1.0)
    scored_type_count: int = Field(ge=0, le=6)
    per_type_scores: dict[ScientificEntityType, float]
    synthetic_text_sha256: str = Field(pattern=SHA256_PATTERN)
    context_trimmed: bool

    @model_validator(mode="after")
    def validate_prediction(self) -> "SemanticTyperPrediction":
        if len(self.per_type_scores) != self.scored_type_count:
            raise ValueError("scored_type_count does not match per_type_scores")
        if self.used_baseline_fallback:
            if self.selected_score is not None or self.scored_type_count != 0:
                raise ValueError("baseline fallback is allowed only for an unscorable target")
            if self.second_best_entity_type is not None or self.second_best_score is not None:
                raise ValueError("baseline fallback cannot carry runner-up scores")
            if self.score_margin is not None:
                raise ValueError("baseline fallback cannot carry a score margin")
        elif self.selected_score is None or self.scored_type_count < 1:
            raise ValueError("retyped predictions require at least one exact-target score")
        return self


class _UniqueKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueKeySafeLoader,
    node: yaml.nodes.MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key: {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def load_semantic_typer_config(path) -> ScientificEntitySemanticTyperConfig:
    try:
        payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeySafeLoader)
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid semantic typer YAML config {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Expected YAML object: {path}")
    return ScientificEntitySemanticTyperConfig.model_validate(payload)


def canonical_semantic_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def semantic_typer_config_sha256(config: ScientificEntitySemanticTyperConfig) -> str:
    encoded = canonical_semantic_json(config.model_dump(mode="json")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
