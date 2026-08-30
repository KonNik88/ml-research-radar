from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


CONFIG_SCHEMA_VERSION = "scientific_entity_semantic_prompt_raw_floor_comparison_v0.2c"
MANIFEST_SCHEMA_VERSION = "scientific_entity_semantic_prompt_raw_floor_comparison_manifest_v0.2c"
COMPARISON_SCHEMA_VERSION = "scientific_entity_semantic_prompt_raw_floor_comparison_output_v0.2c"
DIAGNOSTICS_SCHEMA_VERSION = "scientific_entity_semantic_prompt_raw_floor_comparison_diagnostics_v0.2c"
PROGRESSION_SCHEMA_VERSION = "scientific_entity_semantic_prompt_progression_v0.2c"
GATE_SCHEMA_VERSION = "scientific_entity_semantic_prompt_raw_floor_gate_decision_v0.2c"


class RawFloorComparisonError(ValueError):
    """Raised when the frozen v0.2c comparison contract drifts."""


class _UniqueKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueKeySafeLoader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise RawFloorComparisonError(f"Duplicate YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


class LayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["scientific_entity_semantic_prompt_raw_floor_comparison"]
    version: Literal["v0.2c"]
    status: Literal["development_candidate_comparison"]
    layer_kind: Literal["derived_bounded_quality_evidence"]


class CandidateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate_id: Literal["scientific-entity-semantic-prompt-raw-floor-extension-v0.2c"]
    design_config_path: Literal["configs/scientific_entity_semantic_prompt_raw_floor_extension_v0.2c.yaml"]
    policy_config_path: Literal["configs/scientific_entity_semantic_prompt_raw_floor_policy_v0.2c.yaml"]
    evaluation_config_path: Literal["configs/scientific_entity_evaluation_v0.1.yaml"]
    development_package_id: Literal["scientific-entity-semantic-prompt-development-v0.2a-20260829T140201009151Z"]
    calibration_id: Literal["scientific-entity-semantic-prompt-raw-floor-calibration-v0.2c-20260830T104242195583Z"]
    policy_build_id: Literal["scientific-entity-semantic-prompt-raw-floor-policy-v0.2c-20260830T105318817514Z"]
    selected_trial_id: Literal["calibration-trial:adcd020d8bce5af1ff157f4303e0b171"]
    expected_document_count: Literal[72]
    expected_reference_mention_count: Literal[1316]
    expected_selected_prediction_count: Literal[1077]
    compare_splits: list[Literal["old_dev_24", "consumed_v01_heldout_48", "combined_dev_72"]]

    @model_validator(mode="after")
    def validate_splits(self) -> "CandidateConfig":
        if self.compare_splits != [
            "old_dev_24",
            "consumed_v01_heldout_48",
            "combined_dev_72",
        ]:
            raise ValueError("v0.2c comparison split order is frozen")
        return self


class HistoricalInputsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    v02a_comparison_id: Literal["scientific-entity-semantic-prompt-comparison-v0.2a-20260829T145954260189Z"]
    v02b_calibration_id: Literal["scientific-entity-semantic-prompt-threshold-calibration-v0.2b-20260830T093225845167Z"]


class SelectedCalibrationInvariants(BaseModel):
    model_config = ConfigDict(extra="forbid")
    combined_exact_f1: Literal[0.403677]
    consumed_heldout_exact_f1: Literal[0.4]
    consumed_heldout_relaxed_f1: Literal[0.422642]
    model_to_method_count: Literal[32]
    method_to_task_count: Literal[25]
    total_type_mismatch_count: Literal[140]
    method_semantic_sink_count: Literal[58]


class HardGuardrailsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    minimum_consumed_heldout_exact_f1: Literal[0.396882]
    minimum_combined_dev_exact_f1: Literal[0.398654]
    maximum_model_to_method_count: Literal[43]
    maximum_method_to_task_count: Literal[25]
    maximum_total_type_mismatch_count: Literal[150]
    maximum_method_semantic_sink_count: Literal[74]
    maximum_any_predicted_type_mismatch_sink_count: Literal[74]


class OutputsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    root: str = Field(min_length=1)
    immutable_comparison_directory: Literal[True]
    encoding: Literal["utf-8"]
    line_ending: Literal["lf"]
    required_files: list[str]


class SafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    execute_required_for_writes: Literal[True]
    overwrite_allowed: Literal[False]
    model_inference_allowed: Literal[False]
    threshold_tuning_allowed: Literal[False]
    fresh_heldout_consumption_allowed: Literal[False]
    canonical_truth_mutation_allowed: Literal[False]
    reconcile_input_allowed: Literal[False]
    production_extractor_selected: Literal[False]
    full_corpus_build_authorized: Literal[False]
    publication_allowed: Literal[False]
    current_48_is_independent_heldout_for_v02: Literal[False]
    future_v02_acceptance_requires_new_disjoint_heldout: Literal[True]


class RawFloorComparisonConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[CONFIG_SCHEMA_VERSION]
    layer: LayerConfig
    candidate: CandidateConfig
    historical_inputs: HistoricalInputsConfig
    selected_calibration_invariants: SelectedCalibrationInvariants
    hard_guardrails: HardGuardrailsConfig
    outputs: OutputsConfig
    safety: SafetyConfig


def load_raw_floor_comparison_config(path: str | Path) -> RawFloorComparisonConfig:
    path = Path(path)
    try:
        payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeySafeLoader)
    except (OSError, yaml.YAMLError) as exc:
        raise RawFloorComparisonError(str(exc)) from exc
    try:
        return RawFloorComparisonConfig.model_validate(payload)
    except Exception as exc:
        raise RawFloorComparisonError(str(exc)) from exc
