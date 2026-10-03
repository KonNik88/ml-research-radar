"""Contracts for one immutable H2 v0.3 full-corpus candidate-build authorization.

The authorization is deliberately narrower than production promotion: it may authorize
one timestamped derived candidate build against one exact canonical snapshot.  It never
authorizes canonical mutation, overwrite of a trusted latest entity build, publication,
or promotion to production latest.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

CONFIG_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_production_authorization_v0.3"
AUTHORIZATION_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_production_authorization_record_v0.3"
MANIFEST_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_production_authorization_manifest_v0.3"
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class H2ProductionAuthorizationError(ValueError):
    """Raised when H2 production authorization cannot be established safely."""


class _UniqueLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueLoader, node: Any, deep: bool = False) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise H2ProductionAuthorizationError(f"Duplicate YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


class LayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["scientific_entity_semantic_typer_h2_production_authorization"]
    version: Literal["v0.3"]
    status: Literal["immutable_one_shot_candidate_materialization_authorization"]
    layer_kind: Literal["bounded_semantic_typing_candidate_materialization_authorization"]


class LineageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    production_authorization_gate_config_path: Literal[
        "configs/scientific_entity_semantic_typer_h2_production_authorization_gate_v0.3.yaml"
    ]
    production_authorization_gate_config_sha256: Literal[
        "6e2101150cc3f06b07901ca58ecc31f72b7ed6c2c8bd884d08c7e173d92645a1"
    ]
    expected_gate_validation_total_checks: Literal[17]
    expected_gate_validation_required_failed_count: Literal[0]
    candidate_id: Literal[
        "scientific-entity-semantic-typer-candidate-v0.3-h2-selective-model-over-method"
    ]
    candidate_fingerprint_sha256: Literal[
        "6d3782fb1f2cc7219b7083bcf381c17c546491425e817c0f5620ff145bfa6966"
    ]
    acceptance_decision_id: Literal[
        "scientific-entity-semantic-typer-h2-independent-acceptance-decision-v0.3-20260927T102527705827Z"
    ]
    required_acceptance_decision: Literal[
        "accept_h2_as_independently_validated_bounded_semantic_typing_intervention"
    ]


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


class AuthorizationBoundaryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    authorization_scope: Literal["one_timestamped_full_corpus_candidate_materialization"]
    authorized_candidate_build_count: Literal[1]
    exact_canonical_snapshot_required: Literal[True]
    same_canonical_snapshot_required_at_build: Literal[True]
    same_candidate_fingerprint_required_at_build: Literal[True]
    same_frozen_h2_policy_required_at_build: Literal[True]
    timestamped_candidate_output_required: Literal[True]
    immutable_build_id_required: Literal[True]
    reference_labels_allowed_in_build: Literal[False]
    heldout_feedback_into_policy_allowed: Literal[False]
    candidate_validation_required_before_promotion: Literal[True]
    separate_promotion_decision_required: Literal[True]
    production_latest_promotion_authorized: Literal[False]
    latest_overwrite_allowed: Literal[False]
    canonical_truth_mutation_allowed: Literal[False]
    publication_authorized: Literal[False]


class ExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    output_root: Literal["data/entities/scientific_entity_semantic_typer_h2_production_authorization/v0.3"]
    authorization_id_prefix: Literal["scientific-entity-semantic-typer-h2-production-authorization-v0.3"]
    canonical_sha256_prefix_length: Literal[16]
    candidate_fingerprint_prefix_length: Literal[8]
    one_shot_execute: Literal[True]
    overwrite_allowed: Literal[False]
    plan_writes_output: Literal[False]
    plan_authorizes_candidate_build: Literal[False]
    plan_exposes_quality_metrics: Literal[False]


class SafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_inference_executed_in_this_slice: Literal[False]
    full_corpus_extraction_executed_in_this_slice: Literal[False]
    human_reference_mentions_read_in_this_slice: Literal[False]
    threshold_tuning_executed: Literal[False]
    policy_revision_executed: Literal[False]
    canonical_truth_mutated: Literal[False]
    production_latest_extractor_selected: Literal[False]
    production_latest_promotion_authorized: Literal[False]
    publication_authorized: Literal[False]


class NextStepsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    after_plan: Literal["commit_h2_production_authorization_record_tooling_before_execute"]
    after_execute: Literal["validate_immutable_h2_production_authorization_record"]
    after_validation: Literal["build_h2_full_corpus_candidate_materialization_tooling"]


class H2ProductionAuthorizationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[CONFIG_SCHEMA_VERSION]
    layer: LayerConfig
    lineage: LineageConfig
    bounded_intervention: BoundedInterventionConfig
    authorization_boundary: AuthorizationBoundaryConfig
    execution: ExecutionConfig
    safety: SafetyConfig
    next_steps: NextStepsConfig

    @model_validator(mode="after")
    def validate_safety_boundary(self) -> "H2ProductionAuthorizationConfig":
        if self.authorization_boundary.production_latest_promotion_authorized:
            raise ValueError("Authorization must not promote production latest")
        if self.authorization_boundary.latest_overwrite_allowed:
            raise ValueError("Authorization must not allow latest overwrite")
        if self.authorization_boundary.canonical_truth_mutation_allowed:
            raise ValueError("Authorization must not mutate canonical truth")
        if self.authorization_boundary.publication_authorized:
            raise ValueError("Authorization must not authorize publication")
        if self.authorization_boundary.reference_labels_allowed_in_build:
            raise ValueError("Full-corpus candidate build must not consume held-out labels")
        return self


class H2ProductionAuthorizationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[AUTHORIZATION_SCHEMA_VERSION] = AUTHORIZATION_SCHEMA_VERSION
    authorization_id: str = Field(min_length=1)
    authorization_scope: Literal["one_timestamped_full_corpus_candidate_materialization"]
    gate_config_sha256: str = Field(pattern=SHA256_PATTERN)
    acceptance_decision_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    candidate_fingerprint_sha256: str = Field(pattern=SHA256_PATTERN)
    canonical_path: str = Field(min_length=1)
    canonical_sha256: str = Field(pattern=SHA256_PATTERN)
    canonical_document_count: int = Field(gt=0)
    authorized_candidate_build_count: Literal[1] = 1
    full_corpus_candidate_build_authorized: Literal[True] = True
    timestamped_candidate_output_required: Literal[True] = True
    immutable_build_id_required: Literal[True] = True
    same_canonical_snapshot_required_at_build: Literal[True] = True
    same_candidate_fingerprint_required_at_build: Literal[True] = True
    same_frozen_h2_policy_required_at_build: Literal[True] = True
    reference_labels_allowed_in_build: Literal[False] = False
    heldout_feedback_into_policy_allowed: Literal[False] = False
    candidate_validation_required_before_promotion: Literal[True] = True
    separate_promotion_decision_required: Literal[True] = True
    production_latest_promotion_authorized: Literal[False] = False
    latest_overwrite_allowed: Literal[False] = False
    canonical_truth_mutated: Literal[False] = False
    publication_authorized: Literal[False] = False


class H2ProductionAuthorizationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[MANIFEST_SCHEMA_VERSION] = MANIFEST_SCHEMA_VERSION
    authorization_id: str = Field(min_length=1)
    authorization_config_sha256: str = Field(pattern=SHA256_PATTERN)
    gate_config_sha256: str = Field(pattern=SHA256_PATTERN)
    acceptance_decision_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    candidate_fingerprint_sha256: str = Field(pattern=SHA256_PATTERN)
    canonical_path: str = Field(min_length=1)
    canonical_sha256: str = Field(pattern=SHA256_PATTERN)
    canonical_document_count: int = Field(gt=0)
    gate_strict_validation_passed: Literal[True] = True
    gate_validation_total_checks: Literal[17] = 17
    gate_validation_required_failed_count: Literal[0] = 0
    authorization_made: Literal[True] = True
    full_corpus_candidate_build_authorized: Literal[True] = True
    production_latest_promotion_authorized: Literal[False] = False
    canonical_truth_mutated: Literal[False] = False
    files: dict[str, str]
    next_slice: Literal["validate_immutable_h2_production_authorization_record"]


def load_h2_production_authorization_config(path: Path | str) -> H2ProductionAuthorizationConfig:
    path = Path(path)
    try:
        payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueLoader)
        return H2ProductionAuthorizationConfig.model_validate(payload)
    except (OSError, yaml.YAMLError, ValueError) as exc:
        raise H2ProductionAuthorizationError(f"Invalid production authorization config {path}: {exc}") from exc


def canonical_config_sha256(config: H2ProductionAuthorizationConfig) -> str:
    payload = json.dumps(
        config.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
