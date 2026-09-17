from __future__ import annotations

from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from radar_core.contracts.scientific_entity_evidence import ScientificEntityType


CONFIG_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_frozen_policy_v0.3"
MANIFEST_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_frozen_policy_manifest_v0.3"
SUMMARY_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_frozen_policy_summary_v0.3"
POLICY_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_policy_v0.3"


class H2FrozenPolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    class Candidate(BaseModel):
        model_config = ConfigDict(extra="forbid")
        candidate_id: Literal["scientific-entity-semantic-typer-candidate-v0.3-h2"]
        status: Literal["frozen_for_independent_acceptance_preparation"]
        hypothesis: Literal["selective_model_over_method_override_over_frozen_h1_semantic_typer"]
        semantic_typer_candidate_id: Literal["scientific-entity-semantic-typer-candidate-v0.3-h1"]
        semantic_typer_config_path: Literal["configs/scientific_entity_semantic_typer_candidate_v0.3.yaml"]
        upstream_baseline_candidate_id: Literal["scientific-entity-semantic-prompt-raw-floor-extension-v0.2c"]

    class Lineage(BaseModel):
        model_config = ConfigDict(extra="forbid")
        revision_analysis_id: str = Field(min_length=1)
        parent_evaluation_id: str = Field(min_length=1)
        parent_prediction_id: str = Field(min_length=1)
        expected_parent_decision: Literal["reject_candidate"]
        expected_case_count: Literal[474]
        expected_primary_metric_eligible_count: Literal[468]

    class Policy(BaseModel):
        model_config = ConfigDict(extra="forbid")
        policy_id: Literal["scientific-entity-semantic-typer-candidate-v0.3-h2-selective-model-over-method"]
        baseline_type: Literal[ScientificEntityType.METHOD]
        semantic_typer_type: Literal[ScientificEntityType.MODEL]
        score_field: Literal["score_margin"]
        operator: Literal[">="]
        margin_threshold: Literal[0.1]
        preserve_baseline_otherwise: Literal[True]
        use_baseline_type_as_post_inference_policy_condition_only: Literal[True]
        selection_rule: Literal["lowest_interior_threshold_in_three_point_all_gate_pass_plateau"]
        selected_plateau_thresholds: list[float] = Field(min_length=3, max_length=3)

        @model_validator(mode="after")
        def validate_plateau(self) -> "H2FrozenPolicyConfig.Policy":
            if self.selected_plateau_thresholds != [0.05, 0.1, 0.15]:
                raise ValueError("selected_plateau_thresholds drifted from frozen revision analysis")
            return self

    class ExpectedDevelopmentReproduction(BaseModel):
        model_config = ConfigDict(extra="forbid")
        override_count: Literal[33]
        corrected_errors: Literal[24]
        introduced_regressions: Literal[9]
        wrong_to_wrong_changes: Literal[0]
        net_corrected_cases: Literal[15]
        regression_rate: Literal[0.026239]
        same_span_accuracy_delta: Literal[0.032051]
        macro_f1_delta: Literal[0.011061]
        model_to_method_after_count: Literal[41]
        model_to_method_reduction_fraction: Literal[0.369231]

    class Safety(BaseModel):
        model_config = ConfigDict(extra="forbid")
        consumed_development_evidence_only: Literal[True]
        new_model_inference_allowed: Literal[False]
        model_inference_threshold_tuning_allowed: Literal[False]
        policy_margin_threshold_calibration_allowed: Literal[False]
        span_mutation_allowed: Literal[False]
        taxonomy_changes_allowed: Literal[False]
        canonical_truth_mutation_allowed: Literal[False]
        production_extractor_selection_allowed: Literal[False]
        full_corpus_build_authorized: Literal[False]
        publication_allowed: Literal[False]
        independent_acceptance_executed: Literal[False]
        future_candidate_requires_new_independent_heldout: Literal[True]

    schema_version: Literal[CONFIG_SCHEMA_VERSION]
    candidate: Candidate
    lineage: Lineage
    policy: Policy
    expected_development_reproduction: ExpectedDevelopmentReproduction
    safety: Safety
    next_steps: dict[str, str]


class FrozenH2Policy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[POLICY_SCHEMA_VERSION] = POLICY_SCHEMA_VERSION
    candidate_id: Literal["scientific-entity-semantic-typer-candidate-v0.3-h2"]
    policy_id: Literal["scientific-entity-semantic-typer-candidate-v0.3-h2-selective-model-over-method"]
    semantic_typer_candidate_id: Literal["scientific-entity-semantic-typer-candidate-v0.3-h1"]
    semantic_typer_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    baseline_type: Literal[ScientificEntityType.METHOD]
    semantic_typer_type: Literal[ScientificEntityType.MODEL]
    score_field: Literal["score_margin"]
    operator: Literal[">="]
    margin_threshold: Literal[0.1]
    preserve_baseline_otherwise: Literal[True]
    use_baseline_type_as_post_inference_policy_condition_only: Literal[True]
    selection_rule: Literal["lowest_interior_threshold_in_three_point_all_gate_pass_plateau"]
    selected_plateau_thresholds: list[float] = Field(min_length=3, max_length=3)
    candidate_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    frozen_for_independent_acceptance_preparation: Literal[True] = True
    independent_acceptance_executed: Literal[False] = False
    production_extractor_selected: Literal[False] = False
    full_corpus_build_authorized: Literal[False] = False
    future_candidate_requires_new_independent_heldout: Literal[True] = True


def load_h2_frozen_policy_config(path) -> H2FrozenPolicyConfig:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected YAML object: {path}")
    return H2FrozenPolicyConfig.model_validate(payload)


__all__ = [
    "CONFIG_SCHEMA_VERSION",
    "MANIFEST_SCHEMA_VERSION",
    "SUMMARY_SCHEMA_VERSION",
    "POLICY_SCHEMA_VERSION",
    "H2FrozenPolicyConfig",
    "FrozenH2Policy",
    "load_h2_frozen_policy_config",
]
