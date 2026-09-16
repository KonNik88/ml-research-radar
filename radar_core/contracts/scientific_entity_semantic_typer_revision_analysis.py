from __future__ import annotations

from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from radar_core.contracts.scientific_entity_evidence import ScientificEntityType


CONFIG_SCHEMA_VERSION = "scientific_entity_semantic_typer_revision_analysis_v0.3"
SUMMARY_SCHEMA_VERSION = "scientific_entity_semantic_typer_revision_analysis_summary_v0.3"
SELECTED_POLICY_SCHEMA_VERSION = "scientific_entity_semantic_typer_selected_revision_policy_v0.3"


class RevisionAnalysisConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    class Analysis(BaseModel):
        model_config = ConfigDict(extra="forbid")
        analysis_id_prefix: Literal["scientific-entity-semantic-typer-revision-analysis-v0.3"]
        parent_candidate_id: Literal["scientific-entity-semantic-typer-candidate-v0.3-h1"]
        expected_parent_decision: Literal["reject_candidate"]
        expected_case_count: Literal[474]
        expected_primary_metric_eligible_count: Literal[468]
        expected_corrected_errors: Literal[51]
        expected_introduced_regressions: Literal[83]
        expected_net_corrected_cases: Literal[-32]
        expected_baseline_model_to_method_count: Literal[65]

    class PolicyFamily(BaseModel):
        model_config = ConfigDict(extra="forbid")
        policy_id: Literal["scientific-entity-semantic-typer-candidate-v0.3-h2-selective-model-over-method"]
        baseline_type: Literal[ScientificEntityType.METHOD]
        semantic_typer_type: Literal[ScientificEntityType.MODEL]
        score_field: Literal["score_margin"]
        operator: Literal[">="]
        preserve_baseline_otherwise: Literal[True]
        use_baseline_type_as_post_inference_policy_condition_only: Literal[True]
        threshold_grid: list[float] = Field(min_length=3)
        selection_rule: Literal["lowest_interior_threshold_in_three_point_all_gate_pass_plateau"]
        plateau_points: Literal[3]

        @model_validator(mode="after")
        def validate_grid(self) -> "RevisionAnalysisConfig.PolicyFamily":
            if self.threshold_grid != sorted(set(self.threshold_grid)):
                raise ValueError("threshold_grid must be sorted and unique")
            if any(value < 0.0 or value > 1.0 for value in self.threshold_grid):
                raise ValueError("threshold_grid values must lie in [0, 1]")
            return self

    class Gates(BaseModel):
        model_config = ConfigDict(extra="forbid")
        minimum_typer_coverage: float = Field(gt=0.0, le=1.0)
        minimum_same_span_accuracy_delta: float = Field(ge=0.0, le=1.0)
        minimum_net_corrected_cases: int = Field(ge=1)
        maximum_regression_rate: float = Field(ge=0.0, lt=1.0)
        minimum_model_to_method_reduction_fraction: float = Field(ge=0.0, le=1.0)
        maximum_macro_f1_drop: float = Field(ge=0.0, le=1.0)

    class Safety(BaseModel):
        model_config = ConfigDict(extra="forbid")
        consumed_development_evidence_only: Literal[True]
        new_model_inference_allowed: Literal[False]
        model_inference_threshold_tuning_allowed: Literal[False]
        policy_margin_threshold_calibration_allowed: Literal[True]
        span_mutation_allowed: Literal[False]
        taxonomy_changes_allowed: Literal[False]
        canonical_truth_mutation_allowed: Literal[False]
        production_extractor_selection_allowed: Literal[False]
        full_corpus_build_authorized: Literal[False]
        independent_acceptance_executed: Literal[False]
        future_candidate_requires_new_independent_heldout: Literal[True]

    schema_version: Literal[CONFIG_SCHEMA_VERSION]
    analysis: Analysis
    policy_family: PolicyFamily
    reuse_development_gates: Gates
    safety: Safety
    next_steps: dict[str, str]


class ThresholdSweepRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    threshold: float = Field(ge=0.0, le=1.0)
    override_count: int = Field(ge=0)
    corrected_errors: int = Field(ge=0)
    introduced_regressions: int = Field(ge=0)
    wrong_to_wrong_changes: int = Field(ge=0)
    net_corrected_cases: int
    regression_rate: float = Field(ge=0.0, le=1.0)
    same_span_accuracy_delta: float
    macro_f1_delta: float
    model_to_method_after_count: int = Field(ge=0)
    model_to_method_reduction_fraction: float = Field(ge=0.0, le=1.0)
    all_reused_gates_passed: bool
    stable_plateau_member: bool = False


class SelectedRevisionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[SELECTED_POLICY_SCHEMA_VERSION] = SELECTED_POLICY_SCHEMA_VERSION
    status: Literal["selected", "not_selected"]
    policy_id: str
    baseline_type: ScientificEntityType
    semantic_typer_type: ScientificEntityType
    score_field: Literal["score_margin"]
    operator: Literal[">="]
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    selection_rule: str
    plateau_thresholds: list[float]
    development_calibration_only: Literal[True] = True
    independent_acceptance_executed: Literal[False] = False
    future_candidate_requires_new_independent_heldout: Literal[True] = True


def load_revision_analysis_config(path) -> RevisionAnalysisConfig:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return RevisionAnalysisConfig.model_validate(payload)


__all__ = [
    "CONFIG_SCHEMA_VERSION",
    "SUMMARY_SCHEMA_VERSION",
    "SELECTED_POLICY_SCHEMA_VERSION",
    "RevisionAnalysisConfig",
    "ThresholdSweepRow",
    "SelectedRevisionPolicy",
    "load_revision_analysis_config",
]
