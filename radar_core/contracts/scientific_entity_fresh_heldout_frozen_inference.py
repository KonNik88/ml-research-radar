from __future__ import annotations

from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

CONFIG_SCHEMA_VERSION = "scientific_entity_fresh_heldout_frozen_inference_v0.2"
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class ScientificEntityFreshHeldoutFrozenInferenceError(ValueError):
    """Raised when the frozen fresh-heldout inference contract drifts."""


class LayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["scientific_entity_fresh_heldout_frozen_inference"]
    version: Literal["v0.2"]
    status: Literal["frozen_one_shot_inference_contract"]
    layer_kind: Literal["independent_heldout_raw_candidate_inference"]


class CandidateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: Literal["scientific-entity-semantic-prompt-raw-floor-extension-v0.2c"]
    runtime_config_path: Literal[
        "configs/scientific_entity_gliner_semantic_prompt_raw_floor_candidate_v0.2c.yaml"
    ]
    runtime_config_sha256: str = Field(pattern=SHA256_PATTERN)
    extractor_name: Literal["ml_radar_gliner_small_v2_5_semantic_prompt_raw_floor_candidate"]
    extractor_version: Literal["0.2.0c1"]
    model_repository: Literal["gliner-community/gliner_small-v2.5"]
    model_revision: Literal["f227d3cd637bd4e6757ae143935316d062393341"]
    model_artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    raw_inference_floor: Literal[0.4]
    window_size_tokens: Literal[320]
    window_overlap_tokens: Literal[64]
    source_fields: list[Literal["title", "abstract"]] = Field(min_length=2, max_length=2)
    entity_types: list[Literal["task", "method", "dataset", "metric", "model", "domain"]] = Field(min_length=6, max_length=6)
    title_policy_threshold_after_raw_validation: Literal[0.45]
    abstract_policy_threshold_after_raw_validation: Literal[0.625]
    entity_type_overrides_allowed: Literal[False]

    @model_validator(mode="after")
    def validate_order(self) -> "CandidateConfig":
        if self.source_fields != ["title", "abstract"]:
            raise ValueError("source_fields must remain title, abstract")
        if self.entity_types != ["task", "method", "dataset", "metric", "model", "domain"]:
            raise ValueError("entity_types must remain the frozen six-type taxonomy")
        return self


class FreshHeldoutConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sample_id: Literal["scientific-entity-fresh-heldout-sample-v0.2-20260901T130232963026Z"]
    review_id: Literal["scientific-entity-fresh-heldout-review-v0.2-20260901T130232963026Z"]
    selected_canonical_ids_sha256: str = Field(pattern=SHA256_PATTERN)
    expected_document_count: Literal[48]
    expected_annotation_row_count: Literal[96]
    expected_reference_mention_count: Literal[944]
    expected_uncertain_reference_mention_count: Literal[0]
    expected_reference_count_by_type: dict[
        Literal["task", "method", "dataset", "metric", "model", "domain"], int
    ]
    require_reference_adequacy_passed: Literal[True]
    require_strict_reference_validation: Literal[True]

    @model_validator(mode="after")
    def validate_reference_counts(self) -> "FreshHeldoutConfig":
        expected = {
            "task": 150, "method": 279, "dataset": 66,
            "metric": 86, "model": 280, "domain": 83,
        }
        if self.expected_reference_count_by_type != expected:
            raise ValueError("reference counts must match the frozen reference evidence")
        if sum(self.expected_reference_count_by_type.values()) != self.expected_reference_mention_count:
            raise ValueError("reference counts must sum to expected_reference_mention_count")
        return self


class ExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_filename: Literal["canonical_documents.sample.jsonl"]
    raw_output_root: Literal["data/entities/scientific_entity_evidence/v0.1"]
    build_id: Literal["scientific-entity-gliner-small-v2.5-fresh-v0.2c-20260901T130232963026Z"]
    build_status: Literal["candidate"]
    max_documents: Literal[48]
    one_shot_execute: Literal[True]
    plan_runs_model_inference: Literal[False]
    overwrite_allowed: Literal[False]
    existing_gliner_builder_required: Literal[True]
    existing_gliner_validator_required: Literal[True]


class SafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference_must_be_frozen_before_execute: Literal[True]
    raw_candidate_must_be_frozen: Literal[True]
    prompt_changes_allowed: Literal[False]
    threshold_changes_allowed: Literal[False]
    model_changes_allowed: Literal[False]
    sampling_changes_allowed: Literal[False]
    policy_application_in_this_slice: Literal[False]
    evaluation_in_this_slice: Literal[False]
    acceptance_decision_in_this_slice: Literal[False]
    canonical_truth_mutation_allowed: Literal[False]
    provider_api_allowed: Literal[False]
    reconcile_input_allowed: Literal[False]
    publication_allowed: Literal[False]
    production_extractor_selected: Literal[False]
    full_corpus_build_authorized: Literal[False]


class NextStepsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    after_plan: Literal["execute_frozen_v02c_raw_inference_once"]
    after_execute: Literal["validate_frozen_v02c_raw_inference"]
    after_validation: Literal["apply_frozen_v02c_policy_once"]


class ScientificEntityFreshHeldoutFrozenInferenceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[CONFIG_SCHEMA_VERSION]
    layer: LayerConfig
    candidate: CandidateConfig
    fresh_heldout: FreshHeldoutConfig
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
            raise ScientificEntityFreshHeldoutFrozenInferenceError(
                f"Duplicate YAML key: {key!r}"
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def load_scientific_entity_fresh_heldout_frozen_inference_config(path):
    try:
        payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeySafeLoader)
    except yaml.YAMLError as exc:
        raise ScientificEntityFreshHeldoutFrozenInferenceError(
            f"Invalid YAML config {path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ScientificEntityFreshHeldoutFrozenInferenceError(
            f"Expected YAML object: {path}"
        )
    return ScientificEntityFreshHeldoutFrozenInferenceConfig.model_validate(payload)
