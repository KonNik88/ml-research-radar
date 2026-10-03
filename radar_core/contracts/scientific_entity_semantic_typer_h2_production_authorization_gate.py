"""Preregistered H2 v0.3 production-authorization boundary.

This contract is intentionally non-executing.  It records the accepted H2 lineage and
freezes the rules that a later production-authorization slice must satisfy before any
full-corpus candidate materialization may run.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

CONFIG_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_production_authorization_gate_v0.3"
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class H2ProductionAuthorizationGateError(ValueError):
    """Raised when the H2 production-authorization preregistration drifts."""


class _UniqueLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueLoader, node: Any, deep: bool = False) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise H2ProductionAuthorizationGateError(f"Duplicate YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


class LayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["scientific_entity_semantic_typer_h2_production_authorization_gate"]
    version: Literal["v0.3"]
    status: Literal["preregistered_after_independent_acceptance_before_production_authorization"]
    layer_kind: Literal["bounded_semantic_typing_production_authorization_preregistration"]


class AcceptanceLineageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: Literal["scientific-entity-semantic-typer-candidate-v0.3-h2-selective-model-over-method"]
    candidate_fingerprint_sha256: Literal["6d3782fb1f2cc7219b7083bcf381c17c546491425e817c0f5620ff145bfa6966"]
    acceptance_decision_id: Literal["scientific-entity-semantic-typer-h2-independent-acceptance-decision-v0.3-20260927T102527705827Z"]
    required_acceptance_decision: Literal["accept_h2_as_independently_validated_bounded_semantic_typing_intervention"]
    acceptance_decision_config_path: Literal["configs/scientific_entity_semantic_typer_h2_independent_acceptance_decision_v0.3.yaml"]
    acceptance_decision_config_sha256: Literal["0f36f9bf8683a0d2b2726d82d12d67fcb6fab1de22a20d5d1bd52d7a3e491dff"]
    expected_decision_validation_total_checks: Literal[24]
    expected_decision_validation_required_failed_count: Literal[0]


class BoundedInterventionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    baseline_type: Literal["method"]
    semantic_typer_type: Literal["model"]
    score_field: Literal["score_margin"]
    operator: Literal[">="]
    threshold: Literal[0.1]
    preserve_baseline_otherwise: Literal[True]
    source_surface_policy: Literal["reuse_frozen_upstream_candidate_surface_without_expansion"]
    span_mutation_allowed: Literal[False]
    span_split_merge_allowed: Literal[False]
    new_span_generation_allowed: Literal[False]
    taxonomy_changes_allowed: Literal[False]
    threshold_tuning_allowed: Literal[False]
    policy_revision_allowed: Literal[False]


class ProductionAuthorizationPrerequisitesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    require_independent_acceptance_decision: Literal[True]
    require_strict_decision_validation: Literal[True]
    require_exact_candidate_fingerprint: Literal[True]
    require_exact_frozen_h2_policy: Literal[True]
    require_exact_canonical_input_snapshot_before_authorization_execute: Literal[True]
    require_canonical_input_sha256: Literal[True]
    require_canonical_document_count: Literal[True]
    require_timestamped_candidate_output: Literal[True]
    require_immutable_build_id: Literal[True]
    require_plan_before_execute: Literal[True]
    require_no_reference_labels_in_full_corpus_build: Literal[True]
    require_no_heldout_feedback_into_policy: Literal[True]
    require_rebuildable_derived_output: Literal[True]
    require_candidate_validation_before_promotion: Literal[True]
    require_separate_promotion_decision: Literal[True]


class SafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gate_slice_runs_model_inference: Literal[False]
    gate_slice_runs_full_corpus_extraction: Literal[False]
    gate_slice_reads_human_reference_mentions: Literal[False]
    gate_slice_mutates_canonical_truth: Literal[False]
    gate_slice_selects_production_extractor: Literal[False]
    gate_slice_authorizes_full_corpus_candidate_build: Literal[False]
    gate_slice_authorizes_latest_promotion: Literal[False]
    gate_slice_authorizes_publication: Literal[False]
    overwrite_latest_allowed: Literal[False]
    canonical_truth_mutation_allowed: Literal[False]
    production_latest_promotion_requires_separate_decision: Literal[True]


class FutureAuthorizationBoundaryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    authorization_may_only_enable_timestamped_full_corpus_candidate_materialization: Literal[True]
    authorization_must_bind_exact_canonical_snapshot: Literal[True]
    authorization_must_bind_exact_candidate_fingerprint: Literal[True]
    authorization_must_preserve_frozen_h2_policy: Literal[True]
    authorization_does_not_imply_latest_promotion: Literal[True]
    authorization_does_not_imply_publication: Literal[True]


class NextStepsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    after_gate_validation: Literal["build_h2_production_authorization_record_tooling"]
    after_authorization_record_validation: Literal["run_h2_full_corpus_candidate_materialization"]
    after_candidate_materialization_validation: Literal["make_separate_h2_production_promotion_decision"]


class H2ProductionAuthorizationGateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[CONFIG_SCHEMA_VERSION]
    layer: LayerConfig
    acceptance_lineage: AcceptanceLineageConfig
    bounded_intervention: BoundedInterventionConfig
    production_authorization_prerequisites: ProductionAuthorizationPrerequisitesConfig
    safety: SafetyConfig
    future_authorization_boundary: FutureAuthorizationBoundaryConfig
    next_steps: NextStepsConfig

    @model_validator(mode="after")
    def validate_fail_closed_boundary(self) -> "H2ProductionAuthorizationGateConfig":
        safety = self.safety
        future = self.future_authorization_boundary
        prereq = self.production_authorization_prerequisites
        if any((
            safety.gate_slice_authorizes_full_corpus_candidate_build,
            safety.gate_slice_authorizes_latest_promotion,
            safety.overwrite_latest_allowed,
            safety.canonical_truth_mutation_allowed,
        )):
            raise ValueError("Gate contract must remain non-authorizing and non-mutating")
        if not all((
            prereq.require_exact_canonical_input_snapshot_before_authorization_execute,
            prereq.require_candidate_validation_before_promotion,
            prereq.require_separate_promotion_decision,
            future.authorization_does_not_imply_latest_promotion,
        )):
            raise ValueError("Production authorization boundary must fail closed")
        return self


def load_h2_production_authorization_gate_config(path: Path | str) -> H2ProductionAuthorizationGateConfig:
    path = Path(path)
    try:
        payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueLoader)
        return H2ProductionAuthorizationGateConfig.model_validate(payload)
    except (OSError, yaml.YAMLError, ValueError) as exc:
        raise H2ProductionAuthorizationGateError(f"Invalid production authorization gate {path}: {exc}") from exc


def canonical_config_sha256(config: H2ProductionAuthorizationGateConfig) -> str:
    payload = json.dumps(
        config.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
