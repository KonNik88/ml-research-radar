from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

ENTITY_TYPES = ("task", "method", "dataset", "metric", "model", "domain")
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class ExpectedInputs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evaluation_id: str
    decision_id: str
    decision: Literal["reject_v02c_independent_acceptance"]
    evaluation_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    evaluation_errors_sha256: str = Field(pattern=SHA256_PATTERN)
    document_count: int = Field(ge=1)
    reference_mention_count: int = Field(ge=1)
    prediction_mention_count: int = Field(ge=1)
    type_mismatch_count: int = Field(ge=1)
    model_to_method_count: int = Field(ge=0)
    method_to_task_count: int = Field(ge=0)
    method_sink_count: int = Field(ge=0)
    maximum_sink_type: Literal["method"]
    maximum_sink_count: int = Field(ge=0)


class ReviewConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    context_radius_chars: int = Field(default=120, ge=20, le=1000)
    high_confidence_thresholds: list[float] = Field(default_factory=lambda: [0.8, 0.9])
    root_cause_labels: list[str]
    recommended_action_labels: list[str]

    @model_validator(mode="after")
    def validate_thresholds(self) -> "ReviewConfig":
        if not self.high_confidence_thresholds:
            raise ValueError("high_confidence_thresholds must not be empty")
        if sorted(self.high_confidence_thresholds) != self.high_confidence_thresholds:
            raise ValueError("high_confidence_thresholds must be sorted")
        if any(not 0.0 <= value <= 1.0 for value in self.high_confidence_thresholds):
            raise ValueError("high_confidence_thresholds must be in [0, 1]")
        return self


class OutputConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root: str


class SafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analysis_only: Literal[True]
    model_inference_allowed: Literal[False]
    threshold_tuning_allowed: Literal[False]
    policy_reapply_allowed: Literal[False]
    evaluation_recompute_allowed: Literal[False]
    canonical_truth_mutation_allowed: Literal[False]
    production_extractor_selection_allowed: Literal[False]
    full_corpus_build_authorized: Literal[False]


class ScientificEntityTypingDiagnosticsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["scientific_entity_typing_diagnostics_config_v0.3"]
    analysis_name: Literal["scientific_entity_typing_diagnostics"]
    analysis_version: Literal["v0.3"]
    expected: ExpectedInputs
    review: ReviewConfig
    output: OutputConfig
    safety: SafetyConfig
    next_steps: dict[str, str]


class TypingCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["scientific_entity_typing_case_v0.3"] = "scientific_entity_typing_case_v0.3"
    diagnostic_case_id: str
    error_id: str
    evaluation_id: str
    canonical_id: str
    source_field: Literal["title", "abstract"]
    reference_id: str
    prediction_evidence_id: str
    reference_entity_type: Literal["task", "method", "dataset", "metric", "model", "domain"]
    prediction_entity_type: Literal["task", "method", "dataset", "metric", "model", "domain"]
    confusion_pair: str
    pair_count: int = Field(ge=1)
    pair_rank: int = Field(ge=1)
    reference_char_start: int = Field(ge=0)
    reference_char_end: int = Field(gt=0)
    prediction_char_start: int = Field(ge=0)
    prediction_char_end: int = Field(gt=0)
    char_iou: float = Field(ge=0.0, le=1.0)
    same_span: bool
    reference_surface: str
    prediction_surface: str
    source_excerpt: str
    prediction_confidence_score: float = Field(ge=0.0, le=1.0)
    high_confidence_at_0_8: bool
    high_confidence_at_0_9: bool


class TypingReviewRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["scientific_entity_typing_review_template_v0.3"] = "scientific_entity_typing_review_template_v0.3"
    diagnostic_case_id: str
    error_id: str
    confusion_pair: str
    reference_surface: str
    prediction_surface: str
    source_excerpt: str
    reference_entity_type: str
    prediction_entity_type: str
    prediction_confidence_score: float
    review_status: Literal["pending"] = "pending"
    root_cause: None = None
    reference_type_confirmed: None = None
    prediction_type_plausible: None = None
    ambiguity_level: None = None
    recommended_action: None = None
    review_notes: None = None
