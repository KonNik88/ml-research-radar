"""Schema of immutable 9D full-field NER evaluation outputs."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class FullNerUnblindPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["scientific_entity_full_ner_coverage_unblind_prediction_v0.1"]
    audit_case_id: str
    canonical_id: str
    source_field: Literal["title", "abstract"]
    final_mention_id: str
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    surface_text: str
    entity_type: Literal["task", "method", "dataset", "metric", "model", "domain"]
    source_text_sha256: str


class FullNerUnblindSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["scientific_entity_full_ner_coverage_unblind_summary_v0.1"]
    evaluation_id: str
    audit_id: str
    reference_id: str
    policy_id: str
    field_count: Literal[120]
    title_field_count: Literal[60]
    abstract_field_count: Literal[60]
    frozen_mention_count: Literal[972]
    certain_reference_count: Literal[904]
    uncertain_mention_count: Literal[68]
    production_prediction_count_scanned: Literal[846264]
    selected_prediction_count: int = Field(ge=0)
    ignored_prediction_count: int = Field(ge=0)
    primary_panel: Literal["typed_exact"]
    primary_micro: dict[str, Any]
    metrics: dict[str, Any]
    sensitivity_include_uncertain_as_gold: dict[str, Any]
    diagnostic_counts: dict[str, int]
    balanced_sample_not_corpus_population_weighted: Literal[True]
    numerical_quality_pass_fail_decision_made: Literal[False]
    model_inference_executed: Literal[False]
    production_mutated: Literal[False]
    reference_mutated: Literal[False]
    policy_mutated: Literal[False]
    threshold_tuning_executed: Literal[False]
    publication_authorized: Literal[False]


class FullNerUnblindManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["scientific_entity_full_ner_coverage_unblind_manifest_v0.1"]
    evaluation_id: str
    audit_id: str
    reference_id: str
    policy_id: str
    evaluation_config_sha256: str
    reference_manifest_sha256: str
    reference_annotations_sha256: str
    policy_manifest_sha256: str
    policy_record_sha256: str
    latest_pointer_sha256: str
    production_candidate_build_id: str
    production_final_mentions_sha256: str
    production_final_mention_count: Literal[846264]
    selected_prediction_count: int = Field(ge=0)
    primary_panel: Literal["typed_exact"]
    metrics_are_balanced_sample_only: Literal[True]
    evaluation_executed: Literal[True]
    model_inference_executed: Literal[False]
    production_mutated: Literal[False]
    reference_mutated: Literal[False]
    policy_mutated: Literal[False]
    publication_authorized: Literal[False]
    next_slice: Literal["review_full_ner_coverage_results_and_plan_v04_diagnostics"]
    files: dict[str, str]
