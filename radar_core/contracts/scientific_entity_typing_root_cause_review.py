from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


ENTITY_TYPES = ("task", "method", "dataset", "metric", "model", "domain")
ROOT_CAUSE_LABELS = (
    "clear_semantic_mistyping",
    "taxonomy_boundary_ambiguity",
    "annotation_reference_issue",
    "compound_or_nested_entity",
    "insufficient_context",
    "other",
)
RECOMMENDED_ACTION_LABELS = (
    "prompt_or_label_definition",
    "second_stage_typer",
    "ambiguity_rejection",
    "annotation_guideline",
    "span_handling",
    "no_change",
    "other",
)
AMBIGUITY_LEVELS = ("none", "low", "medium", "high")
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class ParentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_id: str
    evaluation_id: str
    decision_id: str
    diagnostic_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    diagnostic_summary_sha256: str = Field(pattern=SHA256_PATTERN)
    typing_cases_sha256: str = Field(pattern=SHA256_PATTERN)
    review_template_sha256: str = Field(pattern=SHA256_PATTERN)
    type_mismatch_count: int = Field(ge=1)
    same_span_type_mismatch_count: int = Field(ge=0)
    model_to_method_count: int = Field(ge=0)
    method_to_task_count: int = Field(ge=0)
    method_sink_count: int = Field(ge=0)


class ReviewConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ambiguity_levels: list[Literal["none", "low", "medium", "high"]]
    root_cause_labels: list[
        Literal[
            "clear_semantic_mistyping",
            "taxonomy_boundary_ambiguity",
            "annotation_reference_issue",
            "compound_or_nested_entity",
            "insufficient_context",
            "other",
        ]
    ]
    recommended_action_labels: list[
        Literal[
            "prompt_or_label_definition",
            "second_stage_typer",
            "ambiguity_rejection",
            "annotation_guideline",
            "span_handling",
            "no_change",
            "other",
        ]
    ]
    note_required_for_other: Literal[True]
    working_copy_may_be_partial: Literal[True]
    finalization_requires_all_complete: Literal[True]

    @model_validator(mode="after")
    def validate_vocabularies(self) -> "ReviewConfig":
        if tuple(self.ambiguity_levels) != AMBIGUITY_LEVELS:
            raise ValueError("ambiguity_levels must match the frozen v0.3 vocabulary and order")
        if tuple(self.root_cause_labels) != ROOT_CAUSE_LABELS:
            raise ValueError("root_cause_labels must match the frozen v0.3 vocabulary and order")
        if tuple(self.recommended_action_labels) != RECOMMENDED_ACTION_LABELS:
            raise ValueError("recommended_action_labels must match the frozen v0.3 vocabulary and order")
        return self


class OutputConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    working_root: str
    final_root: str


class SafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    human_review_only: Literal[True]
    model_inference_allowed: Literal[False]
    threshold_tuning_allowed: Literal[False]
    policy_reapply_allowed: Literal[False]
    evaluation_recompute_allowed: Literal[False]
    canonical_truth_mutation_allowed: Literal[False]
    production_extractor_selection_allowed: Literal[False]
    full_corpus_build_authorized: Literal[False]
    automatic_root_cause_assignment_allowed: Literal[False]
    automatic_candidate_selection_allowed: Literal[False]


class ScientificEntityTypingRootCauseReviewConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["scientific_entity_typing_root_cause_review_config_v0.3"]
    review_name: Literal["scientific_entity_typing_root_cause_review"]
    review_version: Literal["v0.3"]
    parent: ParentConfig
    review: ReviewConfig
    output: OutputConfig
    safety: SafetyConfig
    next_steps: dict[str, str]


class WorkingReviewRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[
        "scientific_entity_typing_root_cause_review_working_row_v0.3"
    ] = "scientific_entity_typing_root_cause_review_working_row_v0.3"

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

    review_status: Literal["pending", "complete"] = "pending"
    root_cause: Literal[
        "clear_semantic_mistyping",
        "taxonomy_boundary_ambiguity",
        "annotation_reference_issue",
        "compound_or_nested_entity",
        "insufficient_context",
        "other",
    ] | None = None
    reference_type_confirmed: bool | None = None
    prediction_type_plausible: bool | None = None
    ambiguity_level: Literal["none", "low", "medium", "high"] | None = None
    recommended_action: Literal[
        "prompt_or_label_definition",
        "second_stage_typer",
        "ambiguity_rejection",
        "annotation_guideline",
        "span_handling",
        "no_change",
        "other",
    ] | None = None
    review_notes: str | None = None

    @model_validator(mode="after")
    def validate_review_state(self) -> "WorkingReviewRow":
        review_values = (
            self.root_cause,
            self.reference_type_confirmed,
            self.prediction_type_plausible,
            self.ambiguity_level,
            self.recommended_action,
        )
        if self.review_status == "pending":
            if any(value is not None for value in review_values):
                raise ValueError("pending rows must keep all structured review fields null")
            if self.review_notes not in (None, ""):
                raise ValueError("pending rows must not carry review_notes")
            return self

        if any(value is None for value in review_values):
            raise ValueError("complete rows require all structured review fields")

        notes = (self.review_notes or "").strip()
        if self.root_cause == "other" or self.recommended_action == "other":
            if not notes:
                raise ValueError("review_notes are required when root_cause/action is other")
        return self
