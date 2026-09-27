from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from radar_core.contracts.scientific_entity_evidence import ScientificEntityType

CONFIG_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_independent_evaluation_v0.3"
MANIFEST_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_independent_evaluation_manifest_v0.3"
SUMMARY_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_independent_evaluation_summary_v0.3"
CASE_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_comparative_case_v0.3"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
ENTITY_TYPES = ("task", "method", "dataset", "metric", "model", "domain")


class ScientificEntityH2IndependentEvaluationError(ValueError):
    """Raised when H2 independent comparative evaluation cannot be executed safely."""


class H2IndependentEvaluationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    class Layer(BaseModel):
        model_config = ConfigDict(extra="forbid")
        name: Literal["scientific_entity_semantic_typer_h2_independent_evaluation"]
        version: Literal["v0.3"]
        status: Literal["frozen_one_shot_independent_comparative_evaluation"]
        layer_kind: Literal["independent_comparative_quality_evidence"]

    class Candidate(BaseModel):
        model_config = ConfigDict(extra="forbid")
        candidate_id: Literal[
            "scientific-entity-semantic-typer-candidate-v0.3-h2-selective-model-over-method"
        ]
        candidate_fingerprint_sha256: Literal[
            "6d3782fb1f2cc7219b7083bcf381c17c546491425e817c0f5620ff145bfa6966"
        ]

    class AcceptanceGate(BaseModel):
        model_config = ConfigDict(extra="forbid")
        config_path: Literal[
            "configs/scientific_entity_semantic_typer_h2_independent_acceptance_gate_v0.3.yaml"
        ]
        config_sha256: Literal[
            "3ed17739796807046269b88aab40ced2cc10ca1e45ff67dc8965a98070c17a89"
        ]
        minimum_typer_coverage: Literal[0.95]
        minimum_same_span_accuracy_delta: Literal[0.01]
        minimum_net_corrected_cases: Literal[5]
        maximum_regression_rate: Literal[0.05]
        minimum_model_to_method_reduction_fraction: Literal[0.1]
        minimum_macro_f1_delta: Literal[0.0]
        minimum_exact_f1: Literal[0.396882]
        desirable_minimum_relaxed_f1: Literal[0.414868]
        relaxed_f1_is_hard_gate: Literal[False]
        missing_required_denominator_policy: Literal["fail_closed_evidence_insufficient"]

    class Inference(BaseModel):
        model_config = ConfigDict(extra="forbid")
        config_path: Literal[
            "configs/scientific_entity_semantic_typer_h2_independent_inference_v0.3.yaml"
        ]
        inference_id: Literal[
            "scientific-entity-semantic-typer-h2-independent-inference-v0.3-20260927T102527705827Z"
        ]
        expected_document_count: Literal[48]
        expected_baseline_prediction_count: Literal[830]
        expected_h2_prediction_count: Literal[830]
        expected_typer_coverage: Literal[0.983133]
        expected_h2_override_count: Literal[39]

    class FreshHeldout(BaseModel):
        model_config = ConfigDict(extra="forbid")
        sample_id: Literal[
            "scientific-entity-fresh-heldout-sample-v0.3-20260919T093837653829Z"
        ]
        review_id: Literal[
            "scientific-entity-fresh-heldout-review-v0.3-20260919T093837653829Z"
        ]
        sample_documents_file: Literal["canonical_documents.sample.jsonl"]
        reference_review_manifest_file: Literal["review_manifest.json"]
        reference_mentions_file: Literal["reference_mentions.jsonl"]
        expected_document_count: Literal[48]
        expected_reference_mention_count: Literal[929]

    class BaseEvaluator(BaseModel):
        model_config = ConfigDict(extra="forbid")
        config_path: Literal["configs/scientific_entity_evaluation_v0.1.yaml"]
        matching_identity: Literal["exact_plus_relaxed_char_iou_v0.1"]
        relaxed_min_char_iou: Literal[0.5]
        decimal_places: Literal[6]

    class Comparative(BaseModel):
        model_config = ConfigDict(extra="forbid")
        same_span_pairing: Literal["exact_span_type_agnostic_deterministic_v0.3"]
        regression_rate_denominator: Literal["baseline_correct_same_span_cases"]
        model_to_method_reduction_denominator: Literal[
            "baseline_model_to_method_same_span_cases"
        ]
        macro_f1_scope: Literal["same_span_six_type_classification"]
        require_nonzero_same_span_pair_count: Literal[True]
        require_nonzero_baseline_correct_count: Literal[True]
        require_nonzero_baseline_model_to_method_count: Literal[True]
        require_nonzero_reference_support_for_all_six_types: Literal[True]
        materialize_corrected_errors: Literal[True]
        materialize_introduced_regressions: Literal[True]
        materialize_model_to_method_direct_corrections: Literal[True]
        materialize_model_to_method_wrong_to_wrong: Literal[True]

    class Execution(BaseModel):
        model_config = ConfigDict(extra="forbid")
        output_root: Literal[
            "data/entities/scientific_entity_semantic_typer_h2_independent_evaluation/v0.3"
        ]
        evaluation_id: Literal[
            "scientific-entity-semantic-typer-h2-independent-evaluation-v0.3-20260927T102527705827Z"
        ]
        one_shot_execute: Literal[True]
        plan_runs_evaluation: Literal[False]
        overwrite_allowed: Literal[False]

    class Safety(BaseModel):
        model_config = ConfigDict(extra="forbid")
        inference_must_validate_before_execute: Literal[True]
        reference_must_be_frozen_before_execute: Literal[True]
        plan_may_expose_quality_metrics: Literal[False]
        model_inference_allowed: Literal[False]
        threshold_tuning_allowed: Literal[False]
        policy_revision_allowed: Literal[False]
        span_mutation_allowed: Literal[False]
        taxonomy_changes_allowed: Literal[False]
        reference_labels_used_for_evaluation: Literal[True]
        reference_labels_used_for_filtering: Literal[False]
        acceptance_decision_allowed_in_this_slice: Literal[False]
        canonical_truth_mutation_allowed: Literal[False]
        production_extractor_selection_allowed: Literal[False]
        full_corpus_build_authorized: Literal[False]
        publication_allowed: Literal[False]

    class NextSteps(BaseModel):
        model_config = ConfigDict(extra="forbid")
        after_plan: Literal["execute_h2_v03_independent_comparative_evaluation_once"]
        after_execute: Literal["validate_h2_v03_independent_comparative_evaluation"]
        after_validation: Literal["make_immutable_h2_independent_acceptance_decision"]

    schema_version: Literal[CONFIG_SCHEMA_VERSION]
    layer: Layer
    candidate: Candidate
    acceptance_gate: AcceptanceGate
    inference: Inference
    fresh_heldout: FreshHeldout
    base_evaluator: BaseEvaluator
    comparative: Comparative
    execution: Execution
    safety: Safety
    next_steps: NextSteps


class H2ComparativeCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[CASE_SCHEMA_VERSION] = CASE_SCHEMA_VERSION
    case_id: str = Field(min_length=1)
    reference_id: str = Field(min_length=1)
    baseline_prediction_evidence_id: str = Field(min_length=1)
    canonical_id: str = Field(min_length=1)
    source_field: Literal["title", "abstract"]
    source_text_sha256: str = Field(pattern=SHA256_PATTERN)
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    surface_text: str = Field(min_length=1)
    reference_entity_type: ScientificEntityType
    baseline_entity_type: ScientificEntityType
    h2_entity_type: ScientificEntityType
    h2_override_applied: bool
    baseline_correct: bool
    h2_correct: bool

    @model_validator(mode="after")
    def validate_case(self) -> "H2ComparativeCase":
        if self.char_end <= self.char_start:
            raise ValueError("comparative case span is invalid")
        if self.baseline_correct != (self.baseline_entity_type == self.reference_entity_type):
            raise ValueError("baseline_correct drifted from types")
        if self.h2_correct != (self.h2_entity_type == self.reference_entity_type):
            raise ValueError("h2_correct drifted from types")
        return self


class ClassificationPerTypeRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_type: ScientificEntityType
    reference_support: int = Field(ge=0)
    prediction_support: int = Field(ge=0)
    true_positive: int = Field(ge=0)
    precision: float | None = Field(default=None, ge=0.0, le=1.0)
    recall: float | None = Field(default=None, ge=0.0, le=1.0)
    f1: float | None = Field(default=None, ge=0.0, le=1.0)


class ClassificationSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_count: int = Field(ge=0)
    correct_count: int = Field(ge=0)
    accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    macro_f1: float | None = Field(default=None, ge=0.0, le=1.0)
    per_type: list[ClassificationPerTypeRow]


class ExtractionSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prediction_mention_count: int = Field(ge=0)
    exact_precision: float | None = Field(default=None, ge=0.0, le=1.0)
    exact_recall: float | None = Field(default=None, ge=0.0, le=1.0)
    exact_f1: float | None = Field(default=None, ge=0.0, le=1.0)
    relaxed_precision: float | None = Field(default=None, ge=0.0, le=1.0)
    relaxed_recall: float | None = Field(default=None, ge=0.0, le=1.0)
    relaxed_f1: float | None = Field(default=None, ge=0.0, le=1.0)
    exact_match_count: int = Field(ge=0)
    relaxed_only_match_count: int = Field(ge=0)
    model_to_method_count: int = Field(ge=0)
    method_to_task_count: int = Field(ge=0)
    total_type_mismatch_count: int = Field(ge=0)
    method_semantic_sink_count: int = Field(ge=0)
    maximum_predicted_type_mismatch_sink_type: str | None = None
    maximum_any_predicted_type_mismatch_sink_count: int = Field(ge=0)


class H2IndependentEvaluationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[SUMMARY_SCHEMA_VERSION] = SUMMARY_SCHEMA_VERSION
    evaluation_id: str
    inference_id: str
    document_count: Literal[48]
    reference_mention_count: Literal[929]
    typer_coverage: float = Field(ge=0.0, le=1.0)
    same_span_pair_count: int = Field(ge=0)
    baseline_typing: ClassificationSnapshot
    h2_typing: ClassificationSnapshot
    same_span_accuracy_delta: float
    macro_f1_delta: float
    corrected_errors: int = Field(ge=0)
    introduced_regressions: int = Field(ge=0)
    net_corrected_cases: int
    regression_rate: float = Field(ge=0.0)
    baseline_model_to_method_count: int = Field(ge=0)
    h2_model_to_method_count: int = Field(ge=0)
    model_to_method_reduction_fraction: float
    model_to_method_direct_corrections: int = Field(ge=0)
    model_to_method_wrong_to_wrong: int = Field(ge=0)
    baseline_extraction: ExtractionSnapshot
    h2_extraction: ExtractionSnapshot
    required_metric_denominators_present: Literal[True] = True
    evaluation_executed: Literal[True] = True
    acceptance_decision_made: Literal[False] = False
    threshold_tuning_executed: Literal[False] = False
    policy_revision_executed: Literal[False] = False
    canonical_truth_mutated: Literal[False] = False
    production_extractor_selected: Literal[False] = False
    full_corpus_build_authorized: Literal[False] = False


class H2IndependentEvaluationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[MANIFEST_SCHEMA_VERSION] = MANIFEST_SCHEMA_VERSION
    evaluation_id: str
    inference_id: str
    candidate_id: str
    candidate_fingerprint_sha256: str = Field(pattern=SHA256_PATTERN)
    sample_id: str
    review_id: str
    evaluation_config_sha256: str = Field(pattern=SHA256_PATTERN)
    acceptance_gate_config_sha256: str = Field(pattern=SHA256_PATTERN)
    base_evaluator_config_sha256: str = Field(pattern=SHA256_PATTERN)
    inference_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    reference_mentions_sha256: str = Field(pattern=SHA256_PATTERN)
    document_count: Literal[48]
    reference_mention_count: Literal[929]
    baseline_prediction_count: Literal[830]
    h2_prediction_count: Literal[830]
    files: dict[str, str]
    inference_validated_before_evaluation: Literal[True] = True
    reference_labels_used_for_evaluation: Literal[True] = True
    reference_labels_used_for_filtering: Literal[False] = False
    model_inference_executed_in_this_slice: Literal[False] = False
    threshold_tuning_executed: Literal[False] = False
    policy_revision_executed: Literal[False] = False
    span_mutated: Literal[False] = False
    evaluation_executed: Literal[True] = True
    acceptance_decision_made: Literal[False] = False
    canonical_truth_mutated: Literal[False] = False
    production_extractor_selected: Literal[False] = False
    full_corpus_build_authorized: Literal[False] = False
    publication_ready: Literal[False] = False
    next_slice: Literal["validate_h2_v03_independent_comparative_evaluation"]


class _UniqueKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueKeySafeLoader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ScientificEntityH2IndependentEvaluationError(f"Duplicate YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def load_h2_independent_evaluation_config(
    path: str | Path,
) -> H2IndependentEvaluationConfig:
    path = Path(path)
    try:
        payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeySafeLoader)
    except (OSError, yaml.YAMLError) as exc:
        raise ScientificEntityH2IndependentEvaluationError(str(exc)) from exc
    if not isinstance(payload, dict):
        raise ScientificEntityH2IndependentEvaluationError(f"Expected YAML object: {path}")
    try:
        return H2IndependentEvaluationConfig.model_validate(payload)
    except Exception as exc:
        raise ScientificEntityH2IndependentEvaluationError(str(exc)) from exc


def canonical_config_sha256(config: H2IndependentEvaluationConfig) -> str:
    payload = json.dumps(
        config.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


__all__ = [
    "CONFIG_SCHEMA_VERSION",
    "MANIFEST_SCHEMA_VERSION",
    "SUMMARY_SCHEMA_VERSION",
    "CASE_SCHEMA_VERSION",
    "ENTITY_TYPES",
    "H2IndependentEvaluationConfig",
    "H2ComparativeCase",
    "ClassificationPerTypeRow",
    "ClassificationSnapshot",
    "ExtractionSnapshot",
    "H2IndependentEvaluationSummary",
    "H2IndependentEvaluationManifest",
    "ScientificEntityH2IndependentEvaluationError",
    "canonical_config_sha256",
    "load_h2_independent_evaluation_config",
]
