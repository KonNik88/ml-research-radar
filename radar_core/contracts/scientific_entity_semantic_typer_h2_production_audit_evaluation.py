from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from radar_core.contracts.scientific_entity_evidence import ScientificEntityType

CONFIG_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_production_audit_evaluation_v0.3"
CASE_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_production_audit_evaluation_case_v0.3"
STRATUM_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_production_audit_stratum_metrics_v0.3"
GATES_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_production_audit_gate_results_v0.3"
SUMMARY_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_production_audit_evaluation_summary_v0.3"
MANIFEST_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_production_audit_evaluation_manifest_v0.3"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
EVIDENCE_ID_PATTERN = r"^evidence:[0-9a-f]{32}$"

AUDIT_ID = "scientific-entity-semantic-typer-h2-production-audit-v0.3-20261003T121605823276Z"
REFERENCE_ID = "scientific-entity-semantic-typer-h2-production-audit-reference-v0.3-20261003T121605823276Z"
EVALUATION_ID = "scientific-entity-semantic-typer-h2-production-audit-evaluation-v0.3-20261003T121605823276Z"
CANDIDATE_BUILD_ID = "scientific-entity-semantic-typer-h2-full-corpus-candidate-v0.3-20261003T121605823276Z"
CANDIDATE_ID = "scientific-entity-semantic-typer-candidate-v0.3-h2-selective-model-over-method"
CANDIDATE_FINGERPRINT = "6d3782fb1f2cc7219b7083bcf381c17c546491425e817c0f5620ff145bfa6966"
MATERIALIZATION_FINGERPRINT = "5c528cab17e2d48c812f6013fbd4f7d966d8e0ccab5eff4e86de166e92641366"
CANONICAL_SHA256 = "3cc6e3c779fee351bcab605ad1b804acf0e4f8365718db96dad398959420b6ff"
AUDIT_CONFIG_CANONICAL_SHA256 = "c1f0f786c44149a3c5decbe96d96baf3ce778be3798929fe6064b05accfe9de9"
REFERENCE_CONFIG_CANONICAL_SHA256 = "82f058248696f6cd9828b81e33e20f9538d0521ac76e6c8bf84335aefaed626e"

Stratum = Literal["override", "preserved_method", "fallback_method"]
SpanStatus = Literal["valid_entity_span", "boundary_issue", "not_an_entity", "uncertain"]
Confidence = Literal["high", "medium", "low"]
Comparator = Literal["<=", ">="]


class H2ProductionAuditEvaluationError(ValueError):
    pass


class _UniqueLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueLoader, node: Any, deep: bool = False) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise H2ProductionAuditEvaluationError(f"Duplicate YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


class LayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["scientific_entity_semantic_typer_h2_production_audit_evaluation"]
    version: Literal["v0.3"]
    status: Literal["frozen_one_shot_unblinded_production_audit_evaluation"]
    layer_kind: Literal["derived_scientific_entity_promotion_safety_evidence"]


class LineageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    audit_id: Literal[AUDIT_ID]
    reference_id: Literal[REFERENCE_ID]
    candidate_build_id: Literal[CANDIDATE_BUILD_ID]
    candidate_id: Literal[CANDIDATE_ID]
    candidate_fingerprint_sha256: Literal[CANDIDATE_FINGERPRINT]
    materialization_fingerprint_sha256: Literal[MATERIALIZATION_FINGERPRINT]
    canonical_sha256: Literal[CANONICAL_SHA256]
    canonical_document_count: Literal[61075]
    audit_config_path: Literal["configs/scientific_entity_semantic_typer_h2_production_audit_v0.3.yaml"]
    audit_config_canonical_sha256: Literal[AUDIT_CONFIG_CANONICAL_SHA256]
    reference_freeze_config_path: Literal["configs/scientific_entity_semantic_typer_h2_production_audit_reference_freeze_v0.3.yaml"]
    reference_freeze_config_canonical_sha256: Literal[REFERENCE_CONFIG_CANONICAL_SHA256]
    expected_audit_case_count: Literal[240]
    expected_reference_row_count: Literal[240]
    expected_override_count: Literal[100]
    expected_preserved_method_count: Literal[100]
    expected_fallback_method_count: Literal[40]
    expected_candidate_validation_total_checks: Literal[42]
    expected_candidate_validation_required_failed_count: Literal[0]
    expected_audit_sample_validation_total_checks: Literal[27]
    expected_audit_sample_validation_required_failed_count: Literal[0]
    expected_reference_validation_total_checks: Literal[23]
    expected_reference_validation_required_failed_count: Literal[0]


class EvaluationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    usable_span_statuses: list[Literal["valid_entity_span", "boundary_issue"]]
    reference_type_rate_denominator: Literal["usable_cases_only"]
    overall_rate_denominator: Literal["all_240_audit_cases"]
    fallback_unresolved_or_not_entity_rate_denominator: Literal["all_fallback_cases"]
    boundary_issue_rate_is_diagnostic_only: Literal[True]
    materialize_case_level_unblinded_evidence: Literal[True]
    materialize_baseline_vs_final_correctness: Literal[True]

    @model_validator(mode="after")
    def validate_usable_statuses(self) -> "EvaluationConfig":
        if self.usable_span_statuses != ["valid_entity_span", "boundary_issue"]:
            raise ValueError("usable_span_statuses must remain valid_entity_span + boundary_issue")
        return self


class PromotionGatesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_overall_uncertain_rate: Literal[0.10]
    max_overall_not_entity_rate: Literal[0.15]
    min_override_usable_count: Literal[80]
    min_override_reference_model_rate: Literal[0.45]
    max_override_reference_method_rate: Literal[0.30]
    min_override_net_model_minus_method_rate: Literal[0.15]
    min_preserved_usable_count: Literal[80]
    min_preserved_reference_method_rate: Literal[0.50]
    max_preserved_reference_model_rate: Literal[0.30]
    min_fallback_usable_count: Literal[30]
    max_fallback_unresolved_or_not_entity_rate: Literal[0.25]
    thresholds_may_not_be_revised: Literal[True]


class ExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    output_root: Literal["data/entities/scientific_entity_semantic_typer_h2_production_audit_evaluation/v0.3"]
    evaluation_id: Literal[EVALUATION_ID]
    one_shot_execute: Literal[True]
    overwrite_allowed: Literal[False]
    plan_writes_output: Literal[False]
    plan_reads_candidate_predictions: Literal[False]
    plan_reconstructs_sampled_strata: Literal[False]
    plan_exposes_quality_metrics: Literal[False]


class SafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    frozen_reference_required_before_execute: Literal[True]
    unblinding_allowed_on_execute: Literal[True]
    candidate_prediction_files_may_be_read_on_execute: Literal[True]
    sampled_strata_may_be_reconstructed_on_execute: Literal[True]
    promotion_gate_evaluation_allowed_on_execute: Literal[True]
    model_inference_allowed: Literal[False]
    threshold_tuning_allowed: Literal[False]
    h2_policy_revision_allowed: Literal[False]
    candidate_mutation_allowed: Literal[False]
    canonical_truth_mutation_allowed: Literal[False]
    promotion_decision_allowed_in_this_slice: Literal[False]
    production_latest_promotion_authorized: Literal[False]
    latest_overwrite_allowed: Literal[False]
    publication_authorized: Literal[False]


class NextStepsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    after_plan: Literal["commit_h2_production_audit_evaluation_tooling_before_execute"]
    after_execute: Literal["validate_h2_production_audit_evaluation"]
    after_validation_pass: Literal["make_immutable_h2_production_promotion_decision"]
    after_validation_fail: Literal["fix_h2_production_audit_evaluation_artifact"]


class H2ProductionAuditEvaluationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[CONFIG_SCHEMA_VERSION]
    layer: LayerConfig
    lineage: LineageConfig
    evaluation: EvaluationConfig
    promotion_gates: PromotionGatesConfig
    execution: ExecutionConfig
    safety: SafetyConfig
    next_steps: NextStepsConfig


class H2ProductionAuditEvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[CASE_SCHEMA_VERSION] = CASE_SCHEMA_VERSION
    evaluation_id: Literal[EVALUATION_ID]
    audit_id: Literal[AUDIT_ID]
    reference_id: Literal[REFERENCE_ID]
    audit_case_id: str = Field(min_length=1)
    stratum: Stratum
    candidate_evidence_id: str = Field(pattern=EVIDENCE_ID_PATTERN)
    baseline_prediction_evidence_id: str = Field(pattern=EVIDENCE_ID_PATTERN)
    canonical_id: str = Field(min_length=1)
    source_field: Literal["title", "abstract"]
    source_text_sha256: str = Field(pattern=SHA256_PATTERN)
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    surface_text: str = Field(min_length=1)
    baseline_entity_type: Literal[ScientificEntityType.METHOD]
    final_entity_type: ScientificEntityType
    semantic_typer_predicted_entity_type: ScientificEntityType | None = None
    semantic_typer_used_baseline_fallback: bool
    semantic_typer_score_margin: float | None = Field(default=None, ge=0.0, le=1.0)
    h2_override_applied: bool
    reference_entity_type: ScientificEntityType | None
    span_status: SpanStatus
    annotation_confidence: Confidence
    reviewer_note: str | None = None
    usable_for_reference_type_rates: bool
    baseline_matches_reference: bool | None
    final_matches_reference: bool | None

    @model_validator(mode="after")
    def validate_semantics(self) -> "H2ProductionAuditEvaluationCase":
        usable = self.span_status in {"valid_entity_span", "boundary_issue"}
        if self.usable_for_reference_type_rates != usable:
            raise ValueError("usable_for_reference_type_rates drifted from span_status")
        if usable:
            if self.reference_entity_type is None:
                raise ValueError("usable case requires reference_entity_type")
            if self.baseline_matches_reference != (self.baseline_entity_type == self.reference_entity_type):
                raise ValueError("baseline_matches_reference drifted")
            if self.final_matches_reference != (self.final_entity_type == self.reference_entity_type):
                raise ValueError("final_matches_reference drifted")
        else:
            if self.reference_entity_type is not None:
                raise ValueError("unusable case must not carry reference_entity_type")
            if self.baseline_matches_reference is not None or self.final_matches_reference is not None:
                raise ValueError("unusable case correctness must be null")
        if self.stratum == "override":
            if not self.h2_override_applied or self.final_entity_type != ScientificEntityType.MODEL:
                raise ValueError("override stratum semantics drifted")
            if self.semantic_typer_used_baseline_fallback:
                raise ValueError("override cannot be fallback")
        elif self.stratum == "preserved_method":
            if self.h2_override_applied or self.final_entity_type != ScientificEntityType.METHOD:
                raise ValueError("preserved_method semantics drifted")
            if self.semantic_typer_used_baseline_fallback:
                raise ValueError("preserved_method cannot be fallback")
        else:
            if self.h2_override_applied or self.final_entity_type != ScientificEntityType.METHOD:
                raise ValueError("fallback_method semantics drifted")
            if not self.semantic_typer_used_baseline_fallback:
                raise ValueError("fallback_method requires fallback")
        return self


class H2ProductionAuditStratumMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[STRATUM_SCHEMA_VERSION] = STRATUM_SCHEMA_VERSION
    stratum: Stratum
    total_count: int = Field(gt=0)
    usable_count: int = Field(ge=0)
    valid_entity_span_count: int = Field(ge=0)
    boundary_issue_count: int = Field(ge=0)
    not_an_entity_count: int = Field(ge=0)
    uncertain_count: int = Field(ge=0)
    reference_type_count: dict[str, int]
    reference_model_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    reference_method_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    model_minus_method_rate: float | None = Field(default=None, ge=-1.0, le=1.0)
    unresolved_or_not_entity_rate: float = Field(ge=0.0, le=1.0)
    baseline_correct_count: int = Field(ge=0)
    final_correct_count: int = Field(ge=0)
    corrected_by_h2_count: int = Field(ge=0)
    regressed_by_h2_count: int = Field(ge=0)


class H2ProductionAuditGateResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gate_name: str = Field(min_length=1)
    comparator: Comparator
    threshold: float
    observed_value: float
    passed: bool

    @model_validator(mode="after")
    def validate_result(self) -> "H2ProductionAuditGateResult":
        expected = self.observed_value <= self.threshold if self.comparator == "<=" else self.observed_value >= self.threshold
        if self.passed != expected:
            raise ValueError("gate result does not match comparator")
        return self


class H2ProductionAuditGateResults(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[GATES_SCHEMA_VERSION] = GATES_SCHEMA_VERSION
    evaluation_id: Literal[EVALUATION_ID]
    gate_count: Literal[11]
    gates: list[H2ProductionAuditGateResult]
    all_hard_gates_pass: bool
    gate_verdict: Literal["pass_h2_production_audit_gate", "fail_h2_production_audit_gate"]
    thresholds_revised_after_annotation: Literal[False]
    promotion_decision_made: Literal[False]
    production_latest_promotion_authorized: Literal[False]

    @model_validator(mode="after")
    def validate_gates(self) -> "H2ProductionAuditGateResults":
        if len(self.gates) != 11 or len({x.gate_name for x in self.gates}) != 11:
            raise ValueError("exactly 11 unique hard gates are required")
        all_pass = all(x.passed for x in self.gates)
        if self.all_hard_gates_pass != all_pass:
            raise ValueError("all_hard_gates_pass drifted")
        expected = "pass_h2_production_audit_gate" if all_pass else "fail_h2_production_audit_gate"
        if self.gate_verdict != expected:
            raise ValueError("gate_verdict drifted")
        return self


class H2ProductionAuditEvaluationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[SUMMARY_SCHEMA_VERSION] = SUMMARY_SCHEMA_VERSION
    evaluation_id: Literal[EVALUATION_ID]
    audit_id: Literal[AUDIT_ID]
    reference_id: Literal[REFERENCE_ID]
    audit_case_count: Literal[240]
    usable_count: int = Field(ge=0, le=240)
    uncertain_count: int = Field(ge=0, le=240)
    not_an_entity_count: int = Field(ge=0, le=240)
    boundary_issue_count: int = Field(ge=0, le=240)
    uncertain_rate: float = Field(ge=0.0, le=1.0)
    not_an_entity_rate: float = Field(ge=0.0, le=1.0)
    boundary_issue_rate: float = Field(ge=0.0, le=1.0)
    strata: list[H2ProductionAuditStratumMetrics]
    all_hard_gates_pass: bool
    gate_verdict: Literal["pass_h2_production_audit_gate", "fail_h2_production_audit_gate"]
    candidate_prediction_files_read: Literal[True]
    sampled_strata_reconstructed: Literal[True]
    unblinding_executed: Literal[True]
    promotion_gates_evaluated: Literal[True]
    model_inference_executed: Literal[False]
    threshold_tuning_executed: Literal[False]
    policy_revision_executed: Literal[False]
    candidate_mutated: Literal[False]
    canonical_truth_mutated: Literal[False]
    promotion_decision_made: Literal[False]
    production_latest_promotion_authorized: Literal[False]


class H2ProductionAuditEvaluationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[MANIFEST_SCHEMA_VERSION] = MANIFEST_SCHEMA_VERSION
    evaluation_id: Literal[EVALUATION_ID]
    audit_id: Literal[AUDIT_ID]
    reference_id: Literal[REFERENCE_ID]
    candidate_build_id: Literal[CANDIDATE_BUILD_ID]
    candidate_id: Literal[CANDIDATE_ID]
    candidate_fingerprint_sha256: Literal[CANDIDATE_FINGERPRINT]
    materialization_fingerprint_sha256: Literal[MATERIALIZATION_FINGERPRINT]
    canonical_sha256: Literal[CANONICAL_SHA256]
    canonical_document_count: Literal[61075]
    evaluation_config_sha256: str = Field(pattern=SHA256_PATTERN)
    audit_config_canonical_sha256: Literal[AUDIT_CONFIG_CANONICAL_SHA256]
    reference_freeze_config_canonical_sha256: Literal[REFERENCE_CONFIG_CANONICAL_SHA256]
    audit_sample_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    reference_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    candidate_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    candidate_final_mentions_sha256: str = Field(pattern=SHA256_PATTERN)
    files: dict[str, str]
    audit_case_count: Literal[240]
    override_count: Literal[100]
    preserved_method_count: Literal[100]
    fallback_method_count: Literal[40]
    frozen_reference_verified_before_unblinding: Literal[True]
    deterministic_sample_reconstructed_exactly: Literal[True]
    candidate_prediction_files_read: Literal[True]
    sampled_strata_reconstructed: Literal[True]
    unblinding_executed: Literal[True]
    promotion_gates_evaluated: Literal[True]
    model_inference_executed: Literal[False]
    threshold_tuning_executed: Literal[False]
    policy_revision_executed: Literal[False]
    candidate_mutated: Literal[False]
    canonical_truth_mutated: Literal[False]
    promotion_decision_made: Literal[False]
    production_latest_promotion_authorized: Literal[False]
    latest_overwritten: Literal[False]
    publication_ready: Literal[False]
    next_slice: Literal["validate_h2_production_audit_evaluation"]


def load_h2_production_audit_evaluation_config(path: Path) -> H2ProductionAuditEvaluationConfig:
    payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueLoader)
    if not isinstance(payload, dict):
        raise H2ProductionAuditEvaluationError("Evaluation config must be a mapping")
    return H2ProductionAuditEvaluationConfig.model_validate(payload)


def canonical_config_sha256(config: H2ProductionAuditEvaluationConfig) -> str:
    payload = json.dumps(config.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
