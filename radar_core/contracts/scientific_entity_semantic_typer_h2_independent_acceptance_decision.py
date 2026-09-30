"""Frozen H2 v0.3 decision record contracts. No new acceptance thresholds."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

CONFIG_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_independent_acceptance_decision_v0.3"
MANIFEST_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_independent_acceptance_decision_manifest_v0.3"
DECISION_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_independent_acceptance_decision_record_v0.3"
SHA = r"^[0-9a-f]{64}$"


class H2IndependentDecisionError(ValueError):
    """Invalid or insufficient frozen decision evidence."""


class _UniqueLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueLoader, node: Any, deep: bool = False) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise H2IndependentDecisionError(f"Duplicate YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


class H2IndependentDecisionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    class Layer(BaseModel):
        model_config = ConfigDict(extra="forbid")
        name: Literal["scientific_entity_semantic_typer_h2_independent_acceptance_decision"]
        version: Literal["v0.3"]
        status: Literal["immutable_one_shot_independent_acceptance_decision"]
        layer_kind: Literal["bounded_semantic_typing_intervention_decision"]

    class Candidate(BaseModel):
        model_config = ConfigDict(extra="forbid")
        candidate_id: Literal["scientific-entity-semantic-typer-candidate-v0.3-h2-selective-model-over-method"]
        candidate_fingerprint_sha256: Literal["6d3782fb1f2cc7219b7083bcf381c17c546491425e817c0f5620ff145bfa6966"]
        sample_id: Literal["scientific-entity-fresh-heldout-sample-v0.3-20260919T093837653829Z"]
        review_id: Literal["scientific-entity-fresh-heldout-review-v0.3-20260919T093837653829Z"]
        inference_id: Literal["scientific-entity-semantic-typer-h2-independent-inference-v0.3-20260927T102527705827Z"]
        evaluation_id: Literal["scientific-entity-semantic-typer-h2-independent-evaluation-v0.3-20260927T102527705827Z"]

    class FrozenInputs(BaseModel):
        model_config = ConfigDict(extra="forbid")
        gate_config_path: Literal["configs/scientific_entity_semantic_typer_h2_independent_acceptance_gate_v0.3.yaml"]
        gate_config_sha256: Literal["3ed17739796807046269b88aab40ced2cc10ca1e45ff67dc8965a98070c17a89"]
        evaluation_config_path: Literal["configs/scientific_entity_semantic_typer_h2_independent_evaluation_v0.3.yaml"]
        expected_evaluation_document_count: Literal[48]
        expected_reference_mention_count: Literal[929]
        expected_baseline_prediction_count: Literal[830]
        expected_h2_prediction_count: Literal[830]

    class Execution(BaseModel):
        model_config = ConfigDict(extra="forbid")
        output_root: Literal["data/entities/scientific_entity_semantic_typer_h2_independent_acceptance_decision/v0.3"]
        decision_id: Literal["scientific-entity-semantic-typer-h2-independent-acceptance-decision-v0.3-20260927T102527705827Z"]
        one_shot_execute: Literal[True]
        overwrite_allowed: Literal[False]
        plan_makes_decision: Literal[False]
        plan_exposes_quality_metrics: Literal[False]

    class Safety(BaseModel):
        model_config = ConfigDict(extra="forbid")
        require_strict_independent_evaluation_validation: Literal[True]
        require_reference_adequacy: Literal[True]
        require_candidate_fingerprint: Literal[True]
        require_frozen_gate_integrity: Literal[True]
        allow_threshold_tuning: Literal[False]
        allow_policy_revision: Literal[False]
        allow_model_inference: Literal[False]
        allow_re_evaluation_in_decision_slice: Literal[False]
        allow_canonical_truth_mutation: Literal[False]
        allow_reconcile_input: Literal[False]
        production_extractor_selected: Literal[False]
        full_corpus_build_authorized: Literal[False]
        publication_ready: Literal[False]

    class NextSteps(BaseModel):
        model_config = ConfigDict(extra="forbid")
        after_plan: Literal["commit_immutable_h2_acceptance_decision_tooling_before_execute"]
        after_execute: Literal["validate_immutable_h2_independent_acceptance_decision"]
        after_validation: Literal["record_h2_independent_acceptance_and_plan_separate_production_authorization"]

    schema_version: Literal[CONFIG_SCHEMA_VERSION]
    layer: Layer
    candidate: Candidate
    frozen_inputs: FrozenInputs
    execution: Execution
    safety: Safety
    next_steps: NextSteps


class H2GateCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    operator: Literal[">=", "<=", "=="]
    threshold: float | int | bool
    actual: float | int | bool
    passed: bool
    hard: Literal[True] = True


class H2IndependentDecisionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[DECISION_SCHEMA_VERSION] = DECISION_SCHEMA_VERSION
    decision_id: str
    evaluation_id: str
    candidate_id: str
    candidate_fingerprint_sha256: str = Field(pattern=SHA)
    gate_config_sha256: str = Field(pattern=SHA)
    reference_adequacy_passed: bool
    strictly_validated_evaluation: Literal[True] = True
    required_metric_denominators_present: Literal[True] = True
    hard_gates: list[H2GateCheck] = Field(min_length=9, max_length=9)
    all_hard_gates_passed: bool
    decision: Literal[
        "accept_h2_as_independently_validated_bounded_semantic_typing_intervention",
        "reject_h2_independent_acceptance",
    ]
    desirable_relaxed_f1_threshold: Literal[0.414868]
    desirable_relaxed_f1_actual: float | None = Field(ge=0, le=1)
    desirable_relaxed_f1_met: bool | None
    production_extractor_selected: Literal[False] = False
    full_corpus_build_authorized: Literal[False] = False
    canonical_truth_mutated: Literal[False] = False
    future_candidate_after_failure_requires_new_independent_heldout: Literal[True] = True

    @model_validator(mode="after")
    def validate_consistency(self) -> "H2IndependentDecisionRecord":
        names = [row.name for row in self.hard_gates]
        if len(set(names)) != 9:
            raise ValueError("Nine distinct hard gate names required")
        passed = all(row.passed for row in self.hard_gates)
        if self.all_hard_gates_passed != passed:
            raise ValueError("Decision hard-gate result is inconsistent")
        if (self.decision.startswith("accept_") is not passed):
            raise ValueError("Decision must reflect every hard gate")
        if self.desirable_relaxed_f1_met != (
            None if self.desirable_relaxed_f1_actual is None else
            self.desirable_relaxed_f1_actual >= self.desirable_relaxed_f1_threshold
        ):
            raise ValueError("Desirable relaxed F1 diagnostic inconsistent")
        return self


class H2IndependentDecisionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[MANIFEST_SCHEMA_VERSION] = MANIFEST_SCHEMA_VERSION
    decision_id: str
    candidate_id: str
    candidate_fingerprint_sha256: str = Field(pattern=SHA)
    evaluation_id: str
    sample_id: str
    review_id: str
    decision_config_sha256: str = Field(pattern=SHA)
    gate_config_sha256: str = Field(pattern=SHA)
    evaluation_config_sha256: str = Field(pattern=SHA)
    evaluation_manifest_sha256: str = Field(pattern=SHA)
    evaluation_summary_sha256: str = Field(pattern=SHA)
    reference_completion_manifest_sha256: str = Field(pattern=SHA)
    files: dict[str, str]
    evaluation_strict_validation_passed: Literal[True] = True
    reference_adequacy_passed: Literal[True] = True
    threshold_tuning_executed: Literal[False] = False
    policy_revision_executed: Literal[False] = False
    model_inference_executed_in_this_slice: Literal[False] = False
    evaluation_executed_in_this_slice: Literal[False] = False
    acceptance_decision_made: Literal[True] = True
    canonical_truth_mutated: Literal[False] = False
    production_extractor_selected: Literal[False] = False
    full_corpus_build_authorized: Literal[False] = False
    publication_ready: Literal[False] = False
    next_slice: Literal["validate_immutable_h2_independent_acceptance_decision"]


def load_h2_independent_decision_config(path: Path | str) -> H2IndependentDecisionConfig:
    path = Path(path)
    try:
        payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueLoader)
        return H2IndependentDecisionConfig.model_validate(payload)
    except (OSError, yaml.YAMLError, ValueError) as exc:
        raise H2IndependentDecisionError(f"Invalid decision config {path}: {exc}") from exc


def canonical_config_sha256(config: H2IndependentDecisionConfig) -> str:
    return hashlib.sha256(json.dumps(
        config.model_dump(mode="json"), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
