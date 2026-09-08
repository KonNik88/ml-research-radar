from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

CONFIG_SCHEMA_VERSION = "scientific_entity_fresh_heldout_evaluation_v0.2"
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class ScientificEntityFreshHeldoutEvaluationError(ValueError):
    """Raised when the frozen fresh-heldout evaluation contract drifts."""


class LayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["scientific_entity_fresh_heldout_evaluation"]
    version: Literal["v0.2"]
    status: Literal["frozen_one_shot_independent_evaluation_contract"]
    layer_kind: Literal["independent_heldout_quality_evidence"]


class CandidateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: Literal["scientific-entity-semantic-prompt-raw-floor-extension-v0.2c"]
    policy_contract_path: Literal["configs/scientific_entity_fresh_heldout_frozen_policy_v0.2.yaml"]
    policy_contract_semantic_sha256: str = Field(pattern=SHA256_PATTERN)
    policy_build_id: Literal["scientific-entity-semantic-prompt-raw-floor-policy-fresh-v0.2c-20260901T130232963026Z"]
    expected_prediction_count: Literal[773]
    expected_policy_extractor_fingerprint: str = Field(pattern=SHA256_PATTERN)
    title_threshold: Literal[0.45]
    abstract_threshold: Literal[0.625]
    entity_type_overrides: dict[str, float]

    @model_validator(mode="after")
    def validate_no_type_overrides(self) -> "CandidateConfig":
        if self.entity_type_overrides:
            raise ValueError("entity_type_overrides must remain empty")
        return self


class FreshHeldoutConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gate_config_path: Literal["configs/scientific_entity_fresh_heldout_gate_v0.2.yaml"]
    gate_config_semantic_sha256: str = Field(pattern=SHA256_PATTERN)
    sample_id: Literal["scientific-entity-fresh-heldout-sample-v0.2-20260901T130232963026Z"]
    review_id: Literal["scientific-entity-fresh-heldout-review-v0.2-20260901T130232963026Z"]
    sample_documents_file: Literal["canonical_documents.sample.jsonl"]
    reference_review_manifest_file: Literal["review_manifest.json"]
    reference_mentions_file: Literal["reference_mentions.jsonl"]
    expected_document_count: Literal[48]
    expected_reference_mention_count: Literal[944]


class BaseEvaluatorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    config_path: Literal["configs/scientific_entity_evaluation_v0.1.yaml"]
    config_semantic_sha256: str = Field(pattern=SHA256_PATTERN)
    matching_identity: Literal["exact_plus_relaxed_char_iou_v0.1"]
    relaxed_min_char_iou: Literal[0.5]
    decimal_places: Literal[6]


class AcceptanceGateSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    minimum_exact_f1: Literal[0.396882]
    desirable_minimum_relaxed_f1: Literal[0.414868]
    relaxed_f1_is_hard_gate: Literal[False]
    maximum_model_to_method_count: Literal[43]
    maximum_method_to_task_count: Literal[25]
    maximum_total_type_mismatch_count: Literal[150]
    maximum_method_semantic_sink_count: Literal[74]
    maximum_any_predicted_type_mismatch_sink_count: Literal[74]
    no_post_heldout_tuning: Literal[True]
    decision_made_in_this_slice: Literal[False]


class ExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    output_root: Literal["data/entities/scientific_entity_fresh_heldout_evaluation/v0.2"]
    evaluation_id: Literal["scientific-entity-evaluation-fresh-v0.2c-20260901T130232963026Z"]
    status: Literal["candidate"]
    max_documents: Literal[48]
    one_shot_execute: Literal[True]
    plan_runs_evaluation: Literal[False]
    overwrite_allowed: Literal[False]


class SafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy_build_must_validate_before_execute: Literal[True]
    reference_evidence_must_validate_before_execute: Literal[True]
    plan_may_expose_quality_metrics: Literal[False]
    model_inference_allowed: Literal[False]
    threshold_tuning_allowed: Literal[False]
    prompt_changes_allowed: Literal[False]
    model_changes_allowed: Literal[False]
    sampling_changes_allowed: Literal[False]
    taxonomy_changes_allowed: Literal[False]
    reference_labels_used_for_evaluation: Literal[True]
    reference_labels_used_for_filtering: Literal[False]
    acceptance_decision_in_this_slice: Literal[False]
    canonical_truth_mutation_allowed: Literal[False]
    reconcile_input_allowed: Literal[False]
    publication_allowed: Literal[False]
    production_extractor_selected: Literal[False]
    full_corpus_build_authorized: Literal[False]


class NextStepsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    after_plan: Literal["execute_frozen_v02c_fresh_heldout_evaluation_once"]
    after_execute: Literal["validate_frozen_v02c_fresh_heldout_evaluation"]
    after_validation: Literal["make_immutable_v02c_acceptance_decision_without_tuning"]


class ScientificEntityFreshHeldoutEvaluationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[CONFIG_SCHEMA_VERSION]
    layer: LayerConfig
    candidate: CandidateConfig
    fresh_heldout: FreshHeldoutConfig
    base_evaluator: BaseEvaluatorConfig
    acceptance_gate_snapshot: AcceptanceGateSnapshot
    execution: ExecutionConfig
    safety: SafetyConfig
    next_steps: NextStepsConfig


class _UniqueKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueKeySafeLoader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ScientificEntityFreshHeldoutEvaluationError(f"Duplicate YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def load_scientific_entity_fresh_heldout_evaluation_config(
    path: str | Path,
) -> ScientificEntityFreshHeldoutEvaluationConfig:
    path = Path(path)
    try:
        payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeySafeLoader)
    except (OSError, yaml.YAMLError) as exc:
        raise ScientificEntityFreshHeldoutEvaluationError(str(exc)) from exc
    if not isinstance(payload, dict):
        raise ScientificEntityFreshHeldoutEvaluationError(f"Expected YAML object: {path}")
    try:
        return ScientificEntityFreshHeldoutEvaluationConfig.model_validate(payload)
    except Exception as exc:
        raise ScientificEntityFreshHeldoutEvaluationError(str(exc)) from exc
