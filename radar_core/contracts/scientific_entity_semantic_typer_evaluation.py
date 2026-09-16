from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from radar_core.contracts.scientific_entity_evidence import ScientificEntityType


PREDICTION_PACKAGE_SCHEMA_VERSION = "scientific_entity_semantic_typer_prediction_package_v0.3"
PREDICTION_SUMMARY_SCHEMA_VERSION = "scientific_entity_semantic_typer_prediction_summary_v0.3"
DEVELOPMENT_EVALUATION_SCHEMA_VERSION = "scientific_entity_semantic_typer_development_evaluation_v0.3"
DEVELOPMENT_EVALUATION_SUMMARY_SCHEMA_VERSION = "scientific_entity_semantic_typer_development_evaluation_summary_v0.3"


class SemanticTyperClassMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: ScientificEntityType
    support: int = Field(ge=0)
    precision: float = Field(ge=0.0, le=1.0)
    recall: float = Field(ge=0.0, le=1.0)
    f1: float = Field(ge=0.0, le=1.0)


class SemanticTyperMetricSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_count: int = Field(ge=1)
    correct_count: int = Field(ge=0)
    accuracy: float = Field(ge=0.0, le=1.0)
    macro_f1: float = Field(ge=0.0, le=1.0)
    per_type: list[SemanticTyperClassMetrics] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def validate_counts(self) -> "SemanticTyperMetricSet":
        if self.correct_count > self.case_count:
            raise ValueError("correct_count cannot exceed case_count")
        if [row.entity_type for row in self.per_type] != list(ScientificEntityType):
            raise ValueError("per_type must follow frozen canonical entity type order")
        return self


class SemanticTyperGateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate_name: str = Field(min_length=1)
    passed: bool
    actual: float | int
    operator: Literal[">=", "<="]
    threshold: float | int


class SemanticTyperDevelopmentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal[
        "reject_candidate",
        "revise_candidate",
        "freeze_for_independent_acceptance",
    ]
    all_gates_passed: bool
    positive_net_improvement: bool
    future_candidate_requires_new_independent_heldout: Literal[True] = True
    production_extractor_selected: Literal[False] = False
    full_corpus_build_authorized: Literal[False] = False


__all__ = [
    "PREDICTION_PACKAGE_SCHEMA_VERSION",
    "PREDICTION_SUMMARY_SCHEMA_VERSION",
    "DEVELOPMENT_EVALUATION_SCHEMA_VERSION",
    "DEVELOPMENT_EVALUATION_SUMMARY_SCHEMA_VERSION",
    "SemanticTyperClassMetrics",
    "SemanticTyperMetricSet",
    "SemanticTyperGateResult",
    "SemanticTyperDevelopmentDecision",
]
