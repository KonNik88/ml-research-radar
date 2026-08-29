from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from radar_core.contracts.scientific_entity_evidence import ScientificEntityType
from radar_core.entities.scientific_entity_gliner import (
    ScientificEntityGLiNERConfig,
    gliner_config_sha256,
    load_gliner_config,
)


SEMANTIC_PROMPT_CANDIDATE_SCHEMA_VERSION = (
    "scientific_entity_semantic_prompt_candidate_v0.2a"
)
EXPECTED_BASELINE_PROMPTS = {
    "task": "machine learning task or research objective",
    "method": "machine learning method or algorithm",
    "dataset": "dataset corpus or benchmark",
    "metric": "evaluation metric",
    "model": "model architecture or named system",
    "domain": "research or application domain",
}
EXPECTED_CANDIDATE_PROMPTS = {
    "task": "machine learning task, prediction problem, or learning objective",
    "method": "algorithm, training procedure, optimization method, or computational technique",
    "dataset": "named dataset, benchmark dataset, corpus, or data collection",
    "metric": "quantitative metric, score, measured property, or efficiency measure",
    "model": "named machine learning or statistical model, neural network, or model architecture",
    "domain": "research field, scientific domain, application area, or data domain",
}


class SemanticPromptCandidateError(ValueError):
    """Raised when the v0.2a design contract drifts from its frozen scope."""


class _UniqueKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueKeySafeLoader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise SemanticPromptCandidateError(f"Duplicate YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


class CandidateHeader(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: Literal["scientific-entity-semantic-prompt-candidate-v0.2a"]
    status: Literal["design_frozen"]
    hypothesis: Literal["more_discriminative_gliner_facing_semantic_prompts"]
    change_scope: Literal["semantic_prompts_only"]
    baseline_runtime_config_path: Literal[
        "configs/scientific_entity_gliner_candidate_v0.1.yaml"
    ]
    candidate_runtime_config_path: Literal[
        "configs/scientific_entity_gliner_semantic_prompt_candidate_v0.2a.yaml"
    ]
    canonical_entity_types: list[ScientificEntityType] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def validate_types(self) -> "CandidateHeader":
        if set(self.canonical_entity_types) != set(ScientificEntityType):
            raise ValueError("canonical_entity_types must be exactly the six v0.1 types")
        if len(set(self.canonical_entity_types)) != 6:
            raise ValueError("canonical_entity_types must not contain duplicates")
        return self


class PromptDelta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_type: ScientificEntityType
    baseline_prompt: str = Field(min_length=1)
    candidate_prompt: str = Field(min_length=1)
    design_target: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_strings(self) -> "PromptDelta":
        for value in (self.baseline_prompt, self.candidate_prompt, self.design_target):
            if value != value.strip():
                raise ValueError("prompt delta strings must be trimmed")
        if self.baseline_prompt.casefold() == self.candidate_prompt.casefold():
            raise ValueError("candidate prompt must differ from baseline prompt")
        return self


class DevelopmentSet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_count: int = Field(gt=0)
    role: str = Field(min_length=1)
    review_id: str = Field(min_length=1)
    evaluation_id: str | None = None
    error_analysis_id: str | None = None


class DevelopmentEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    old_dev: DevelopmentSet
    consumed_v01_heldout: DevelopmentSet
    combined_document_count: Literal[72]
    current_48_may_be_called_independent_heldout_for_v02: Literal[False]
    future_v02_acceptance_requires_new_disjoint_heldout: Literal[True]

    @model_validator(mode="after")
    def validate_counts(self) -> "DevelopmentEvidence":
        if self.old_dev.document_count != 24:
            raise ValueError("old_dev must remain 24 papers")
        if self.consumed_v01_heldout.document_count != 48:
            raise ValueError("consumed v0.1 held-out must remain 48 papers")
        if self.old_dev.document_count + self.consumed_v01_heldout.document_count != 72:
            raise ValueError("combined development evidence must equal 72 papers")
        return self


class FrozenSourceFieldPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title_threshold: Literal[0.55]
    abstract_threshold: Literal[0.65]
    entity_type_overrides: dict[str, float]

    @model_validator(mode="after")
    def validate_no_overrides(self) -> "FrozenSourceFieldPolicy":
        if self.entity_type_overrides:
            raise ValueError("v0.2a first comparison forbids entity-type threshold overrides")
        return self


class ConsumedHeldoutBaseline(BaseModel):
    model_config = ConfigDict(extra="forbid")
    exact_f1: Literal[0.396882]
    relaxed_f1: Literal[0.414868]
    total_type_mismatch_count: Literal[176]
    model_to_method_count: Literal[55]
    method_to_task_count: Literal[28]
    method_semantic_sink_count: Literal[94]
    metric_exact_f1: Literal[0.209877]
    domain_exact_f1: Literal[0.293707]
    task_exact_recall: Literal[0.308571]
    model_exact_f1: Literal[0.513369]


class HardGuardrails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    minimum_overall_exact_f1: Literal[0.386882]
    maximum_model_to_method_count: Literal[44]
    maximum_method_to_task_count: Literal[28]
    maximum_total_type_mismatch_count: Literal[176]
    maximum_method_semantic_sink_count: Literal[84]
    maximum_any_predicted_type_mismatch_sink_count: Literal[94]


class DecisionGates(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evaluation_role: Literal["development_candidate_gate_not_independent_acceptance"]
    all_hard_guardrails_required_for_promising: Literal[True]
    hard_guardrails: HardGuardrails
    desirable_directional_signals: dict[str, Literal["increase", "nondecrease"]]


class ControlledComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")
    raw_candidate_inference_threshold: Literal[0.5]
    frozen_source_field_policy: FrozenSourceFieldPolicy
    compare_splits: list[Literal["old_dev_24", "consumed_v01_heldout_48", "combined_dev_72"]]
    metrics: list[str] = Field(min_length=1)
    consumed_v01_heldout_baseline: ConsumedHeldoutBaseline
    decision_gates: DecisionGates

    @model_validator(mode="after")
    def validate_splits(self) -> "ControlledComparison":
        expected = {"old_dev_24", "consumed_v01_heldout_48", "combined_dev_72"}
        if set(self.compare_splits) != expected or len(set(self.compare_splits)) != 3:
            raise ValueError("compare_splits must contain exactly the three frozen dev views")
        return self


class IdentityLineage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_must_use_new_extractor_identity: Literal[True]
    candidate_runtime_config_sha_must_differ_from_baseline: Literal[True]
    extractor_fingerprint_must_differ_from_v01: Literal[True]
    same_span_type_text_keeps_mention_id: Literal[True]
    changed_extractor_fingerprint_changes_evidence_id: Literal[True]
    new_build_id_required: Literal[True]
    immutable_outputs_required: Literal[True]
    overwrite_forbidden: Literal[True]


class SafetyBoundary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_slice_runs_model_inference: Literal[False]
    contract_slice_runs_threshold_tuning: Literal[False]
    changes_canonical_truth: Literal[False]
    may_be_used_as_reconcile_input: Literal[False]
    production_extractor_selected: Literal[False]
    full_corpus_build_authorized: Literal[False]
    publication_ready: Literal[False]
    medium_model_comparison_in_scope: Literal[False]
    fine_tuning_in_scope: Literal[False]
    markup_cleanup_in_scope: Literal[False]


class NextSteps(BaseModel):
    model_config = ConfigDict(extra="forbid")
    after_contract_freeze: Literal[
        "bounded_raw_candidate_inference_on_72_development_documents"
    ]
    after_raw_candidate_inference: Literal[
        "apply_unchanged_055_065_policy_and_run_controlled_comparison"
    ]
    if_promising: Literal[
        "consider_separate_v02_recalibration_then_fresh_disjoint_heldout"
    ]
    if_not_promising: Literal[
        "evaluate_next_bounded_hypothesis_without_reusing_future_heldout"
    ]


class SemanticPromptCandidateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[SEMANTIC_PROMPT_CANDIDATE_SCHEMA_VERSION]
    candidate: CandidateHeader
    prompts: list[PromptDelta] = Field(min_length=6, max_length=6)
    development_evidence: DevelopmentEvidence
    controlled_comparison: ControlledComparison
    identity_and_lineage: IdentityLineage
    safety: SafetyBoundary
    next_steps: NextSteps

    @model_validator(mode="after")
    def validate_prompts(self) -> "SemanticPromptCandidateConfig":
        by_type = {row.entity_type.value: row for row in self.prompts}
        if set(by_type) != set(EXPECTED_BASELINE_PROMPTS) or len(by_type) != 6:
            raise ValueError("prompts must cover each canonical entity type exactly once")
        for entity_type, expected in EXPECTED_BASELINE_PROMPTS.items():
            if by_type[entity_type].baseline_prompt != expected:
                raise ValueError(f"baseline prompt drift for {entity_type}")
        for entity_type, expected in EXPECTED_CANDIDATE_PROMPTS.items():
            if by_type[entity_type].candidate_prompt != expected:
                raise ValueError(f"candidate prompt drift for {entity_type}")
        return self


def load_semantic_prompt_candidate_config(path: Path) -> SemanticPromptCandidateConfig:
    try:
        payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeySafeLoader)
    except yaml.YAMLError as exc:
        raise SemanticPromptCandidateError(f"Invalid YAML config {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SemanticPromptCandidateError("candidate config must contain a YAML mapping")
    return SemanticPromptCandidateConfig.model_validate(payload)


def _prompt_map(config: ScientificEntityGLiNERConfig) -> dict[str, str]:
    return {row.entity_type.value: row.prompt for row in config.inference.labels}


def _without_prompt_delta(config: ScientificEntityGLiNERConfig) -> dict:
    payload = config.model_dump(mode="json")
    payload["extractor"]["name"] = "<allowed-delta>"
    payload["extractor"]["version"] = "<allowed-delta>"
    for row in payload["inference"]["labels"]:
        row["prompt"] = "<allowed-delta>"
    payload["layer"]["description"] = "<allowed-delta>"
    return payload


def validate_candidate_contract(
    *, project_root: Path, design_config_path: Path
) -> dict[str, object]:
    root = project_root.resolve()
    design = load_semantic_prompt_candidate_config(design_config_path.resolve())
    baseline_path = root / design.candidate.baseline_runtime_config_path
    candidate_path = root / design.candidate.candidate_runtime_config_path
    baseline = load_gliner_config(baseline_path)
    candidate = load_gliner_config(candidate_path)

    baseline_prompts = _prompt_map(baseline)
    candidate_prompts = _prompt_map(candidate)
    if baseline_prompts != EXPECTED_BASELINE_PROMPTS:
        raise SemanticPromptCandidateError("baseline runtime prompts drifted")
    if candidate_prompts != EXPECTED_CANDIDATE_PROMPTS:
        raise SemanticPromptCandidateError("candidate runtime prompts drifted")
    if _without_prompt_delta(baseline) != _without_prompt_delta(candidate):
        raise SemanticPromptCandidateError(
            "candidate runtime config changes fields outside the frozen prompt/extractor delta"
        )
    if baseline.extractor.name == candidate.extractor.name:
        raise SemanticPromptCandidateError("candidate extractor name must differ from v0.1")
    if baseline.extractor.version == candidate.extractor.version:
        raise SemanticPromptCandidateError("candidate extractor version must differ from v0.1")

    baseline_sha = gliner_config_sha256(baseline)
    candidate_sha = gliner_config_sha256(candidate)
    if baseline_sha == candidate_sha:
        raise SemanticPromptCandidateError("candidate runtime config SHA must differ")

    return {
        "report": "scientific_entity_semantic_prompt_candidate_v02a_contract",
        "ok": True,
        "candidate_id": design.candidate.candidate_id,
        "status": design.candidate.status,
        "development_document_count": design.development_evidence.combined_document_count,
        "baseline_runtime_config_sha256": baseline_sha,
        "candidate_runtime_config_sha256": candidate_sha,
        "runtime_config_sha_changed": True,
        "baseline_prompt_count": len(baseline_prompts),
        "candidate_prompt_count": len(candidate_prompts),
        "changed_prompt_count": sum(
            baseline_prompts[key] != candidate_prompts[key] for key in baseline_prompts
        ),
        "raw_candidate_inference_threshold": candidate.inference.threshold,
        "title_policy_threshold": design.controlled_comparison.frozen_source_field_policy.title_threshold,
        "abstract_policy_threshold": design.controlled_comparison.frozen_source_field_policy.abstract_threshold,
        "model_repository": candidate.model.repository,
        "model_revision": candidate.model.revision,
        "window_size_tokens": candidate.inference.window_size_tokens,
        "window_overlap_tokens": candidate.inference.window_overlap_tokens,
        "minimum_overall_exact_f1": design.controlled_comparison.decision_gates.hard_guardrails.minimum_overall_exact_f1,
        "maximum_model_to_method_count": design.controlled_comparison.decision_gates.hard_guardrails.maximum_model_to_method_count,
        "maximum_method_to_task_count": design.controlled_comparison.decision_gates.hard_guardrails.maximum_method_to_task_count,
        "maximum_total_type_mismatch_count": design.controlled_comparison.decision_gates.hard_guardrails.maximum_total_type_mismatch_count,
        "maximum_method_semantic_sink_count": design.controlled_comparison.decision_gates.hard_guardrails.maximum_method_semantic_sink_count,
        "model_inference_executed": False,
        "threshold_tuning_executed": False,
        "canonical_truth_mutated": False,
        "full_corpus_build_authorized": False,
        "production_extractor_selected": False,
        "next_slice": design.next_steps.after_contract_freeze,
    }
