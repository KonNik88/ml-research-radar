from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


COMPARISON_CONFIG_SCHEMA_VERSION = "scientific_entity_semantic_prompt_comparison_v0.2a"
COMPARISON_MANIFEST_SCHEMA_VERSION = "scientific_entity_semantic_prompt_comparison_manifest_v0.2a"


class SemanticPromptComparisonError(ValueError):
    """Raised when the v0.2a controlled-comparison contract drifts."""


class _UniqueKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueKeySafeLoader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise SemanticPromptComparisonError(f"Duplicate YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


class ComparisonLayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["scientific_entity_semantic_prompt_comparison"]
    version: Literal["v0.2a"]
    status: Literal["development_candidate_comparison"]
    layer_kind: Literal["derived_bounded_quality_evidence"]


class ComparisonCandidateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: Literal["scientific-entity-semantic-prompt-candidate-v0.2a"]
    design_config_path: Literal[
        "configs/scientific_entity_semantic_prompt_candidate_v0.2a.yaml"
    ]
    policy_config_path: Literal[
        "configs/scientific_entity_semantic_prompt_policy_v0.2a.yaml"
    ]
    evaluation_config_path: Literal["configs/scientific_entity_evaluation_v0.1.yaml"]
    expected_document_count: Literal[72]
    expected_selected_prediction_count: Literal[977]
    compare_splits: list[
        Literal["old_dev_24", "consumed_v01_heldout_48", "combined_dev_72"]
    ] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def validate_splits(self) -> "ComparisonCandidateConfig":
        expected = {"old_dev_24", "consumed_v01_heldout_48", "combined_dev_72"}
        if set(self.compare_splits) != expected or len(set(self.compare_splits)) != 3:
            raise ValueError("compare_splits must remain exactly 24 / 48 / 72")
        return self


class ComparisonOutputsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root: str = Field(min_length=1)
    immutable_comparison_directory: Literal[True]
    encoding: Literal["utf-8"]
    line_ending: Literal["lf"]
    required_files: list[str] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def validate_files(self) -> "ComparisonOutputsConfig":
        expected = {
            "manifest.json",
            "comparison.json",
            "diagnostics.json",
            "gate_decision.json",
            "README.md",
            "checksums.txt",
        }
        if set(self.required_files) != expected or len(set(self.required_files)) != 6:
            raise ValueError("comparison required_files drifted")
        return self


class ComparisonSafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    execute_required_for_writes: Literal[True]
    overwrite_allowed: Literal[False]
    model_inference_allowed: Literal[False]
    threshold_tuning_allowed: Literal[False]
    canonical_truth_mutation_allowed: Literal[False]
    reconcile_input_allowed: Literal[False]
    production_extractor_selected: Literal[False]
    full_corpus_build_authorized: Literal[False]
    publication_allowed: Literal[False]
    current_48_is_independent_heldout_for_v02: Literal[False]
    future_v02_acceptance_requires_new_disjoint_heldout: Literal[True]


class SemanticPromptComparisonConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[COMPARISON_CONFIG_SCHEMA_VERSION]
    layer: ComparisonLayerConfig
    candidate: ComparisonCandidateConfig
    outputs: ComparisonOutputsConfig
    safety: ComparisonSafetyConfig


def load_semantic_prompt_comparison_config(path: Path) -> SemanticPromptComparisonConfig:
    try:
        payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeySafeLoader)
    except yaml.YAMLError as exc:
        raise SemanticPromptComparisonError(f"Invalid YAML config {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SemanticPromptComparisonError("comparison config must contain a YAML mapping")
    return SemanticPromptComparisonConfig.model_validate(payload)
