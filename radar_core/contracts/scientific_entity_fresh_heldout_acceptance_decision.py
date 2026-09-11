from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

CONFIG_SCHEMA_VERSION = "scientific_entity_fresh_heldout_acceptance_decision_v0.2"
DECISION_MANIFEST_SCHEMA_VERSION = "scientific_entity_fresh_heldout_acceptance_decision_manifest_v0.2"
DECISION_RESULT_SCHEMA_VERSION = "scientific_entity_fresh_heldout_acceptance_decision_result_v0.2"
DECISION_CRITERION_SCHEMA_VERSION = "scientific_entity_fresh_heldout_acceptance_decision_criterion_v0.2"
SHA256_PATTERN = r"^[0-9a-f]{64}$"

DecisionValue = Literal[
    "accept_as_independently_validated_bounded_extractor_v0.2",
    "reject_v02c_independent_acceptance",
]
CriterionName = Literal[
    "minimum_exact_f1",
    "desirable_minimum_relaxed_f1",
    "maximum_model_to_method_count",
    "maximum_method_to_task_count",
    "maximum_total_type_mismatch_count",
    "maximum_method_semantic_sink_count",
    "maximum_any_predicted_type_mismatch_sink_count",
]


class ScientificEntityFreshHeldoutAcceptanceDecisionError(ValueError):
    """Raised when the immutable fresh-heldout acceptance-decision contract drifts."""


class LayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["scientific_entity_fresh_heldout_acceptance_decision"]
    version: Literal["v0.2"]
    status: Literal["immutable_one_shot_acceptance_decision_contract"]
    layer_kind: Literal["independent_heldout_acceptance_decision"]


class CandidateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: Literal["scientific-entity-semantic-prompt-raw-floor-extension-v0.2c"]
    sample_id: Literal["scientific-entity-fresh-heldout-sample-v0.2-20260901T130232963026Z"]
    review_id: Literal["scientific-entity-fresh-heldout-review-v0.2-20260901T130232963026Z"]
    policy_build_id: Literal["scientific-entity-semantic-prompt-raw-floor-policy-fresh-v0.2c-20260901T130232963026Z"]
    policy_extractor_fingerprint: str = Field(pattern=SHA256_PATTERN)
    expected_document_count: Literal[48]
    expected_reference_mention_count: Literal[944]
    expected_prediction_count: Literal[773]


class EvaluationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    config_path: Literal["configs/scientific_entity_fresh_heldout_evaluation_v0.2.yaml"]
    config_semantic_sha256: str = Field(pattern=SHA256_PATTERN)
    evaluation_id: Literal["scientific-entity-evaluation-fresh-v0.2c-20260901T130232963026Z"]
    manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    metrics_sha256: str = Field(pattern=SHA256_PATTERN)
    errors_sha256: str = Field(pattern=SHA256_PATTERN)
    checksums_sha256: str = Field(pattern=SHA256_PATTERN)
    required_validation_failed_count: Literal[0]


class GateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    config_path: Literal["configs/scientific_entity_fresh_heldout_gate_v0.2.yaml"]
    config_semantic_sha256: str = Field(pattern=SHA256_PATTERN)
    decision_role: Literal["independent_v02_candidate_acceptance_gate"]
    all_hard_gates_required_for_acceptance: Literal[True]
    relaxed_f1_is_desirable_not_hard: Literal[True]
    no_post_heldout_tuning: Literal[True]


class ExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    output_root: Literal["data/entities/scientific_entity_fresh_heldout_acceptance_decision/v0.2"]
    decision_id: Literal["scientific-entity-fresh-heldout-acceptance-decision-v0.2c-20260901T130232963026Z"]
    one_shot_execute: Literal[True]
    plan_runs_decision: Literal[False]
    overwrite_allowed: Literal[False]


class SafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evaluation_recomputation_allowed: Literal[False]
    model_inference_allowed: Literal[False]
    policy_reapplication_allowed: Literal[False]
    threshold_tuning_allowed: Literal[False]
    prompt_changes_allowed: Literal[False]
    model_changes_allowed: Literal[False]
    sampling_changes_allowed: Literal[False]
    taxonomy_changes_allowed: Literal[False]
    gate_changes_allowed: Literal[False]
    canonical_truth_mutation_allowed: Literal[False]
    reconcile_input_allowed: Literal[False]
    provider_api_allowed: Literal[False]
    production_extractor_selected: Literal[False]
    full_corpus_build_authorized: Literal[False]
    publication_allowed: Literal[False]


class NextStepsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    after_plan: Literal["execute_immutable_v02c_acceptance_decision_once"]
    after_execute: Literal["validate_immutable_v02c_acceptance_decision"]
    after_validation: Literal["close_v02c_and_begin_typing_focused_diagnostics"]


class ScientificEntityFreshHeldoutAcceptanceDecisionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[CONFIG_SCHEMA_VERSION]
    layer: LayerConfig
    candidate: CandidateConfig
    evaluation: EvaluationConfig
    gate: GateConfig
    execution: ExecutionConfig
    safety: SafetyConfig
    next_steps: NextStepsConfig


class AcceptanceCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[DECISION_CRITERION_SCHEMA_VERSION] = DECISION_CRITERION_SCHEMA_VERSION
    name: CriterionName
    observed: float | int
    operator: Literal[">=", "<="]
    threshold: float | int
    hard: bool
    passed: bool


class AcceptanceDecisionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[DECISION_RESULT_SCHEMA_VERSION] = DECISION_RESULT_SCHEMA_VERSION
    decision_id: str
    decision: DecisionValue
    hard_criteria_count: int = Field(ge=1)
    hard_criteria_passed_count: int = Field(ge=0)
    failed_hard_criteria: list[CriterionName]
    desirable_criteria_count: int = Field(ge=0)
    desirable_criteria_passed_count: int = Field(ge=0)
    failed_desirable_criteria: list[CriterionName]
    heldout_becomes_consumed_development_evidence: bool
    future_candidate_requires_new_independent_heldout: bool
    production_extractor_selected: Literal[False]
    full_corpus_build_authorized: Literal[False]

    @model_validator(mode="after")
    def validate_counts_and_decision(self) -> "AcceptanceDecisionResult":
        if self.hard_criteria_passed_count + len(self.failed_hard_criteria) != self.hard_criteria_count:
            raise ValueError("hard criterion counts are inconsistent")
        if self.desirable_criteria_passed_count + len(self.failed_desirable_criteria) != self.desirable_criteria_count:
            raise ValueError("desirable criterion counts are inconsistent")
        rejected = bool(self.failed_hard_criteria)
        if rejected != (self.decision == "reject_v02c_independent_acceptance"):
            raise ValueError("decision does not match failed hard criteria")
        return self


class AcceptanceDecisionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[DECISION_MANIFEST_SCHEMA_VERSION] = DECISION_MANIFEST_SCHEMA_VERSION
    decision_id: str
    generated_at_utc: str
    candidate_id: str
    sample_id: str
    review_id: str
    policy_build_id: str
    policy_extractor_fingerprint: str = Field(pattern=SHA256_PATTERN)
    document_count: int
    reference_mention_count: int
    prediction_mention_count: int
    decision_config_path: str
    decision_config_semantic_sha256: str = Field(pattern=SHA256_PATTERN)
    evaluation_config_path: str
    evaluation_config_semantic_sha256: str = Field(pattern=SHA256_PATTERN)
    evaluation_id: str
    evaluation_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    evaluation_metrics_sha256: str = Field(pattern=SHA256_PATTERN)
    evaluation_errors_sha256: str = Field(pattern=SHA256_PATTERN)
    evaluation_checksums_sha256: str = Field(pattern=SHA256_PATTERN)
    evaluation_validation_required_failed_count: Literal[0]
    gate_config_path: str
    gate_config_semantic_sha256: str = Field(pattern=SHA256_PATTERN)
    evaluation_recomputed: Literal[False]
    model_inference_executed: Literal[False]
    policy_reapplied: Literal[False]
    threshold_tuning_executed: Literal[False]
    gate_changed: Literal[False]
    canonical_truth_mutated: Literal[False]
    production_extractor_selected: Literal[False]
    full_corpus_build_authorized: Literal[False]


class _UniqueKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueKeySafeLoader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ScientificEntityFreshHeldoutAcceptanceDecisionError(
                f"Duplicate YAML key: {key!r}"
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def load_scientific_entity_fresh_heldout_acceptance_decision_config(
    path: str | Path,
) -> ScientificEntityFreshHeldoutAcceptanceDecisionConfig:
    path = Path(path)
    try:
        payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeySafeLoader)
    except (OSError, yaml.YAMLError) as exc:
        raise ScientificEntityFreshHeldoutAcceptanceDecisionError(str(exc)) from exc
    if not isinstance(payload, dict):
        raise ScientificEntityFreshHeldoutAcceptanceDecisionError(f"Expected YAML object: {path}")
    try:
        return ScientificEntityFreshHeldoutAcceptanceDecisionConfig.model_validate(payload)
    except Exception as exc:
        raise ScientificEntityFreshHeldoutAcceptanceDecisionError(str(exc)) from exc


def canonical_config_sha256(
    config: ScientificEntityFreshHeldoutAcceptanceDecisionConfig,
) -> str:
    payload = json.dumps(
        config.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
