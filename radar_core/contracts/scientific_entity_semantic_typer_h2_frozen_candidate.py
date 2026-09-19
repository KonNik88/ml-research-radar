from __future__ import annotations

import hashlib
import json
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from radar_core.contracts.scientific_entity_evidence import ScientificEntityType


CONFIG_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_frozen_candidate_v0.3"
FROZEN_CANDIDATE_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_frozen_candidate_definition_v0.3"
MANIFEST_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_frozen_candidate_manifest_v0.3"
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class H2FrozenCandidateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    class Candidate(BaseModel):
        model_config = ConfigDict(extra="forbid")
        candidate_id: Literal["scientific-entity-semantic-typer-candidate-v0.3-h2-selective-model-over-method"]
        status: Literal["frozen_for_new_independent_acceptance"]
        hypothesis: Literal["selective_model_over_method_override_over_frozen_h1_semantic_scores"]
        parent_semantic_typer_candidate_id: Literal["scientific-entity-semantic-typer-candidate-v0.3-h1"]
        parent_semantic_typer_config_path: Literal["configs/scientific_entity_semantic_typer_candidate_v0.3.yaml"]
        parent_upstream_candidate_id: Literal["scientific-entity-semantic-prompt-raw-floor-extension-v0.2c"]

    class SelectedPolicy(BaseModel):
        model_config = ConfigDict(extra="forbid")
        baseline_type: Literal[ScientificEntityType.METHOD]
        semantic_typer_type: Literal[ScientificEntityType.MODEL]
        score_field: Literal["score_margin"]
        operator: Literal[">="]
        threshold: Literal[0.1]
        preserve_baseline_otherwise: Literal[True]
        selection_rule: Literal["lowest_interior_threshold_in_three_point_all_gate_pass_plateau"]
        expected_plateau_thresholds: list[float] = Field(min_length=3, max_length=3)
        expected_selected_net_corrected_cases: Literal[15]
        expected_selected_regression_rate: Literal[0.026239]
        expected_selected_same_span_accuracy_delta: Literal[0.032051]

        @model_validator(mode="after")
        def validate_plateau(self) -> "H2FrozenCandidateConfig.SelectedPolicy":
            if self.expected_plateau_thresholds != [0.05, 0.1, 0.15]:
                raise ValueError("expected H2 selection plateau drifted")
            return self

    class Freeze(BaseModel):
        model_config = ConfigDict(extra="forbid")
        freeze_id_prefix: Literal["scientific-entity-semantic-typer-h2-frozen-candidate-v0.3"]
        output_root: Literal["data/entities/scientific_entity_semantic_typer_h2_frozen_candidate/v0.3"]
        required_revision_parent_candidate_id: Literal["scientific-entity-semantic-typer-candidate-v0.3-h1"]
        required_revision_policy_status: Literal["selected"]
        required_revision_analysis_schema_version: Literal["scientific_entity_semantic_typer_revision_analysis_manifest_v0.3"]

    class Safety(BaseModel):
        model_config = ConfigDict(extra="forbid")
        development_evidence_consumed: Literal[True]
        new_model_inference_allowed: Literal[False]
        threshold_tuning_allowed: Literal[False]
        policy_revision_allowed_during_freeze: Literal[False]
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
    selected_policy: SelectedPolicy
    freeze: Freeze
    safety: Safety
    next_steps: dict[str, str]


class FrozenH2CandidateDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[FROZEN_CANDIDATE_SCHEMA_VERSION] = FROZEN_CANDIDATE_SCHEMA_VERSION
    candidate_id: Literal["scientific-entity-semantic-typer-candidate-v0.3-h2-selective-model-over-method"]
    candidate_status: Literal["frozen_for_new_independent_acceptance"]
    hypothesis: Literal["selective_model_over_method_override_over_frozen_h1_semantic_scores"]
    parent_semantic_typer_candidate_id: Literal["scientific-entity-semantic-typer-candidate-v0.3-h1"]
    parent_semantic_typer_config_path: str
    parent_semantic_typer_config_sha256: str = Field(pattern=SHA256_PATTERN)
    parent_upstream_candidate_id: str
    revision_analysis_id: str
    revision_analysis_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    revision_selected_policy_sha256: str = Field(pattern=SHA256_PATTERN)
    baseline_type: Literal[ScientificEntityType.METHOD]
    semantic_typer_type: Literal[ScientificEntityType.MODEL]
    score_field: Literal["score_margin"]
    operator: Literal[">="]
    threshold: Literal[0.1]
    preserve_baseline_otherwise: Literal[True]
    selection_rule: Literal["lowest_interior_threshold_in_three_point_all_gate_pass_plateau"]
    plateau_thresholds: list[float]
    development_calibration_only: Literal[True] = True
    independent_acceptance_executed: Literal[False] = False
    requires_new_disjoint_prediction_blind_heldout: Literal[True] = True
    candidate_fingerprint_sha256: str = Field(pattern=SHA256_PATTERN)


def load_h2_frozen_candidate_config(path) -> H2FrozenCandidateConfig:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return H2FrozenCandidateConfig.model_validate(payload)


def canonical_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def semantic_sha256(payload: object) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


__all__ = [
    "CONFIG_SCHEMA_VERSION",
    "FROZEN_CANDIDATE_SCHEMA_VERSION",
    "MANIFEST_SCHEMA_VERSION",
    "H2FrozenCandidateConfig",
    "FrozenH2CandidateDefinition",
    "load_h2_frozen_candidate_config",
    "canonical_json",
    "semantic_sha256",
]
