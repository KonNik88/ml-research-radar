"""Immutable preregistration of full NER coverage scoring rules (9C)."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict


class ScoringPolicyRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["scientific_entity_full_ner_coverage_scoring_policy_record_v0.1"]
    policy_id: str
    audit_id: str
    reference_id: str
    reference_annotations_sha256: str
    trusted_candidate_build_id: str
    trusted_final_mentions_sha256: str
    scoring_rules: dict[str, object]
    original_field_count: Literal[120]
    frozen_mention_count: Literal[972]
    uncertain_mention_count: Literal[68]
    overlap_pair_count: Literal[5]
    production_predictions_read: Literal[False]
    unblind_authorized: Literal[False]
    production_mutated: Literal[False]
    reference_mutated: Literal[False]


class ScoringPolicyManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["scientific_entity_full_ner_coverage_scoring_policy_manifest_v0.1"]
    policy_id: str
    audit_id: str
    reference_id: str
    config_sha256: str
    reference_manifest_sha256: str
    reference_annotations_sha256: str
    reference_summary_sha256: str
    latest_pointer_sha256: str
    policy_sha256: str
    production_predictions_read: Literal[False]
    unblind_executed: Literal[False]
    reference_mutated: Literal[False]
    production_mutated: Literal[False]
    policy_preregistered: Literal[True]
    next_slice: Literal["build_full_ner_coverage_unblind_evaluation"]
    files: dict[str, str]
