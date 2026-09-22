from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


CONFIG_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_independent_acceptance_gate_v0.3"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
ENTITY_TYPES = ("task", "method", "dataset", "metric", "model", "domain")


class ScientificEntityH2IndependentAcceptanceGateError(ValueError):
    """Raised when the frozen H2 independent-acceptance gate contract drifts."""


class _UniqueKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueKeySafeLoader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ScientificEntityH2IndependentAcceptanceGateError(
                f"Duplicate YAML key: {key!r}"
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


class LayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["scientific_entity_semantic_typer_h2_independent_acceptance_gate"]
    version: Literal["v0.3"]
    status: Literal["design_frozen_before_independent_evaluation"]
    layer_kind: Literal["independent_comparative_acceptance_preregistration"]


class CandidateLineageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: Literal[
        "scientific-entity-semantic-typer-candidate-v0.3-h2-selective-model-over-method"
    ]
    candidate_fingerprint_sha256: Literal[
        "6d3782fb1f2cc7219b7083bcf381c17c546491425e817c0f5620ff145bfa6966"
    ]
    freeze_id: Literal[
        "scientific-entity-semantic-typer-h2-frozen-candidate-v0.3-20260919T083718533083Z"
    ]
    frozen_candidate_config_path: Literal[
        "configs/scientific_entity_semantic_typer_h2_frozen_candidate_v0.3.yaml"
    ]
    frozen_candidate_dir: Literal[
        "data/entities/scientific_entity_semantic_typer_h2_frozen_candidate/v0.3/"
        "scientific-entity-semantic-typer-h2-frozen-candidate-v0.3-20260919T083718533083Z"
    ]
    expected_freeze_manifest_sha256: Literal[
        "9f665c001c3a6b90ac4e56a8c4d26322008ab219e470453d86ee54fde68bb881"
    ]
    expected_frozen_candidate_sha256: Literal[
        "3deff1a18eb5ad680d6e3df638d03cbc36596656508ed592fdcafecf2dd04964"
    ]
    baseline_type: Literal["method"]
    semantic_typer_type: Literal["model"]
    score_field: Literal["score_margin"]
    operator: Literal[">="]
    threshold: Literal[0.1]
    preserve_baseline_otherwise: Literal[True]


class FreshHeldoutLineageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sample_id: Literal[
        "scientific-entity-fresh-heldout-sample-v0.3-20260919T093837653829Z"
    ]
    review_id: Literal[
        "scientific-entity-fresh-heldout-review-v0.3-20260919T093837653829Z"
    ]
    sample_dir: Literal[
        "data/entities/scientific_entity_fresh_heldout_sample/v0.3/"
        "scientific-entity-fresh-heldout-sample-v0.3-20260919T093837653829Z"
    ]
    sample_config_path: Literal[
        "configs/scientific_entity_semantic_typer_h2_fresh_heldout_sample_v0.3.yaml"
    ]
    expected_sample_manifest_sha256: Literal[
        "9ba9799c0d5b20b91e4059c7117fa6d6d015fb6ae1fc8f59f9058e52bd093c80"
    ]
    expected_selected_canonical_ids_sha256: Literal[
        "bbd0f209705c8a8ff02fea7fa732741b9cf9981d24a79909c618726fed8608f8"
    ]
    expected_document_count: Literal[48]
    expected_annotation_row_count: Literal[96]
    expected_consumed_union_document_count: Literal[120]
    require_zero_consumed_overlap: Literal[True]
    require_prediction_blind: Literal[True]
    require_reference_not_frozen_at_contract_freeze: Literal[True]
    require_h2_inference_not_executed_at_contract_freeze: Literal[True]
    require_evaluation_not_executed_at_contract_freeze: Literal[True]


class ReferenceAdequacyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    annotation_method: Literal["manual_adjudicated"]
    annotation_guideline_version: Literal["scientific_entity_annotation_guidelines_v0.1"]
    prediction_blind: Literal[True]
    require_all_annotation_rows_complete: Literal[True]
    require_zero_unresolved_uncertain_mentions: Literal[True]
    minimum_reference_mentions_per_type: Literal[20]
    required_entity_types: list[
        Literal["task", "method", "dataset", "metric", "model", "domain"]
    ] = Field(min_length=6, max_length=6)
    require_exact_source_slice_surface: Literal[True]
    duplicate_typed_spans_allowed: Literal[False]
    automatic_annotation_allowed: Literal[False]
    automatic_approval_allowed: Literal[False]
    candidate_inference_only_after_reference_freeze: Literal[True]

    @model_validator(mode="after")
    def validate_entity_types(self) -> "ReferenceAdequacyConfig":
        if self.required_entity_types != list(ENTITY_TYPES):
            raise ValueError("required_entity_types drifted from frozen six-type order")
        return self


class ComparativeAcceptanceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_role: Literal[
        "independent_h2_bounded_semantic_typing_intervention_acceptance_gate"
    ]
    minimum_typer_coverage: Literal[0.95]
    minimum_same_span_accuracy_delta: Literal[0.01]
    minimum_net_corrected_cases: Literal[5]
    maximum_regression_rate: Literal[0.05]
    minimum_model_to_method_reduction_fraction: Literal[0.1]
    minimum_macro_f1_delta: Literal[0.0]
    minimum_exact_f1: Literal[0.396882]
    exact_f1_floor_origin: Literal["independent_v01_heldout_exact_f1"]
    desirable_minimum_relaxed_f1: Literal[0.414868]
    relaxed_f1_floor_role: Literal["desirable_not_hard"]
    require_reference_adequacy: Literal[True]
    require_candidate_fingerprint_match: Literal[True]
    require_all_comparative_gates: Literal[True]
    require_exact_f1_hard_gate: Literal[True]
    require_relaxed_f1_as_hard_gate: Literal[False]
    required_metric_missing_denominator_policy: Literal["fail_closed_evidence_insufficient"]
    no_post_heldout_tuning: Literal[True]
    all_hard_gates_required_for_acceptance: Literal[True]


class HistoricalDiagnosticsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    compute_model_to_method_count: Literal[True]
    historical_maximum_model_to_method_count: Literal[43]
    compute_method_to_task_count: Literal[True]
    historical_maximum_method_to_task_count: Literal[25]
    compute_total_type_mismatch_count: Literal[True]
    historical_maximum_total_type_mismatch_count: Literal[150]
    compute_method_semantic_sink_count: Literal[True]
    historical_maximum_method_semantic_sink_count: Literal[74]
    compute_max_predicted_type_mismatch_sink_count: Literal[True]
    historical_maximum_any_predicted_type_mismatch_sink_count: Literal[74]
    historical_raw_count_caps_are_hard_h2_gates: Literal[False]
    require_corrected_errors: Literal[True]
    require_introduced_regressions: Literal[True]
    require_model_to_method_direct_corrections: Literal[True]
    require_model_to_method_wrong_to_wrong: Literal[True]


class DecisionSemanticsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    if_all_hard_gates_pass: Literal[
        "accept_h2_as_independently_validated_bounded_semantic_typing_intervention"
    ]
    if_any_hard_gate_fails: Literal["reject_h2_independent_acceptance"]
    pass_does_not_select_production_extractor: Literal[True]
    pass_does_not_authorize_full_corpus_build: Literal[True]
    failed_heldout_becomes_consumed_evidence: Literal[True]
    future_candidate_after_failure_requires_new_independent_heldout: Literal[True]
    heldout_may_not_be_reused_for_retuning_and_reacceptance: Literal[True]


class SafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_slice_reads_human_reference_results: Literal[False]
    contract_slice_runs_baseline_inference: Literal[False]
    contract_slice_runs_h2_inference: Literal[False]
    contract_slice_runs_evaluation: Literal[False]
    contract_slice_makes_acceptance_decision: Literal[False]
    contract_slice_consumes_fresh_heldout: Literal[False]
    model_inference_allowed_before_reference_freeze: Literal[False]
    threshold_tuning_allowed: Literal[False]
    policy_revision_allowed: Literal[False]
    span_mutation_allowed: Literal[False]
    taxonomy_changes_allowed: Literal[False]
    canonical_truth_mutation_allowed: Literal[False]
    production_extractor_selection_allowed: Literal[False]
    full_corpus_build_authorized: Literal[False]
    publication_allowed: Literal[False]


class NextStepsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    after_gate_freeze: Literal["build_h2_prediction_blind_reference_freeze_tooling"]
    after_reference_tooling: Literal["prediction_blind_manual_annotation"]
    after_reference_freeze: Literal["run_frozen_h2_independent_inference"]
    after_inference_validation: Literal["run_h2_independent_comparative_evaluation"]
    after_evaluation_validation: Literal[
        "make_immutable_h2_independent_acceptance_decision"
    ]


class ScientificEntityH2IndependentAcceptanceGateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[CONFIG_SCHEMA_VERSION]
    layer: LayerConfig
    candidate_lineage: CandidateLineageConfig
    fresh_heldout_lineage: FreshHeldoutLineageConfig
    reference_adequacy: ReferenceAdequacyConfig
    comparative_acceptance: ComparativeAcceptanceConfig
    historical_diagnostics: HistoricalDiagnosticsConfig
    decision_semantics: DecisionSemanticsConfig
    safety: SafetyConfig
    next_steps: NextStepsConfig


def load_h2_independent_acceptance_gate_config(
    path: str | Path,
) -> ScientificEntityH2IndependentAcceptanceGateConfig:
    path = Path(path)
    try:
        payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeySafeLoader)
    except (OSError, yaml.YAMLError) as exc:
        raise ScientificEntityH2IndependentAcceptanceGateError(str(exc)) from exc
    try:
        return ScientificEntityH2IndependentAcceptanceGateConfig.model_validate(payload)
    except Exception as exc:
        raise ScientificEntityH2IndependentAcceptanceGateError(str(exc)) from exc


def canonical_config_sha256(
    config: ScientificEntityH2IndependentAcceptanceGateConfig,
) -> str:
    payload = json.dumps(
        config.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


__all__ = [
    "CONFIG_SCHEMA_VERSION",
    "ENTITY_TYPES",
    "ScientificEntityH2IndependentAcceptanceGateConfig",
    "ScientificEntityH2IndependentAcceptanceGateError",
    "canonical_config_sha256",
    "load_h2_independent_acceptance_gate_config",
]
