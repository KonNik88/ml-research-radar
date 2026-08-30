from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


CONFIG_SCHEMA_VERSION = "scientific_entity_semantic_prompt_threshold_calibration_v0.2b"
MANIFEST_SCHEMA_VERSION = "scientific_entity_semantic_prompt_threshold_calibration_manifest_v0.2b"
TRIAL_SCHEMA_VERSION = "scientific_entity_semantic_prompt_threshold_calibration_trial_v0.2b"
SELECTED_POLICY_SCHEMA_VERSION = "scientific_entity_semantic_prompt_threshold_selected_policy_v0.2b"
DIAGNOSTICS_SCHEMA_VERSION = "scientific_entity_semantic_prompt_threshold_calibration_diagnostics_v0.2b"


class SemanticPromptThresholdCalibrationError(ValueError):
    """Raised when the frozen v0.2b threshold-calibration contract drifts."""


class _UniqueKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(loader: _UniqueKeySafeLoader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise SemanticPromptThresholdCalibrationError(
                f"Duplicate YAML key: {key!r}"
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


class CalibrationLayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["scientific_entity_semantic_prompt_threshold_calibration"]
    version: Literal["v0.2b"]
    status: Literal["design_frozen"]
    layer_kind: Literal["derived_bounded_threshold_policy_evidence"]


class CalibrationLineageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: Literal["scientific-entity-semantic-prompt-candidate-v0.2a"]
    candidate_design_config_path: Literal[
        "configs/scientific_entity_semantic_prompt_candidate_v0.2a.yaml"
    ]
    evaluation_config_path: Literal["configs/scientific_entity_evaluation_v0.1.yaml"]
    development_package_id: Literal[
        "scientific-entity-semantic-prompt-development-v0.2a-20260829T140201009151Z"
    ]
    raw_build_id: Literal[
        "scientific-entity-gliner-small-v2.5-v0.1-20260829T141340564165Z"
    ]
    raw_extractor_fingerprint: Literal[
        "3e890253263ca3e5d7fa06e9a731205b020ec1251123b8aa1926a696180e48c0"
    ]
    v02a_comparison_id: Literal[
        "scientific-entity-semantic-prompt-comparison-v0.2a-20260829T145954260189Z"
    ]
    expected_document_count: Literal[72]
    expected_reference_mention_count: Literal[1316]
    expected_raw_prediction_count: Literal[1430]
    development_splits: list[
        Literal["old_dev_24", "consumed_v01_heldout_48", "combined_dev_72"]
    ] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def validate_splits(self) -> "CalibrationLineageConfig":
        expected = {"old_dev_24", "consumed_v01_heldout_48", "combined_dev_72"}
        if set(self.development_splits) != expected or len(set(self.development_splits)) != 3:
            raise ValueError("development_splits must remain exactly 24 / 48 / 72")
        return self


class InheritedPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Literal[0.55]
    abstract: Literal[0.65]


class CalibrationSearchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_threshold: Literal[0.5]
    threshold_is_inclusive: Literal[True]
    title_thresholds: list[float] = Field(min_length=5, max_length=5)
    abstract_thresholds: list[float] = Field(min_length=7, max_length=7)
    expected_trial_count: Literal[35]
    source_field_pair_search_only: Literal[True]
    entity_type_overrides_allowed: Literal[False]
    thresholds_below_raw_input_floor_allowed: Literal[False]
    inherited_v02a_policy: InheritedPolicy

    @model_validator(mode="after")
    def validate_search(self) -> "CalibrationSearchConfig":
        expected_title = [0.50, 0.525, 0.55, 0.575, 0.60]
        expected_abstract = [0.50, 0.525, 0.55, 0.575, 0.60, 0.625, 0.65]
        if self.title_thresholds != expected_title:
            raise ValueError("title threshold grid drifted")
        if self.abstract_thresholds != expected_abstract:
            raise ValueError("abstract threshold grid drifted")
        if len(self.title_thresholds) * len(self.abstract_thresholds) != self.expected_trial_count:
            raise ValueError("declared trial count does not match source-field grid")
        if min(self.title_thresholds + self.abstract_thresholds) < self.input_threshold:
            raise ValueError("threshold grid cannot go below raw input floor")
        if self.inherited_v02a_policy.title not in self.title_thresholds:
            raise ValueError("v0.2a title threshold must be included in search")
        if self.inherited_v02a_policy.abstract not in self.abstract_thresholds:
            raise ValueError("v0.2a abstract threshold must be included in search")
        return self


class SemanticGuardrailsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_split: Literal["consumed_v01_heldout_48"]
    maximum_model_to_method_count: Literal[43]
    maximum_method_to_task_count: Literal[25]
    maximum_total_type_mismatch_count: Literal[150]
    maximum_method_semantic_sink_count: Literal[74]
    maximum_any_predicted_type_mismatch_sink_count: Literal[74]
    require_all_guardrails_for_eligibility: Literal[True]


class SelectionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eligible_trials_only: Literal[True]
    primary_objective: Literal["combined_dev_72_exact_f1"]
    tie_break_order: list[
        Literal[
            "combined_dev_72_relaxed_f1_desc",
            "combined_dev_72_exact_recall_desc",
            "threshold_sum_desc",
            "title_threshold_desc",
            "abstract_threshold_desc",
            "trial_id_asc",
        ]
    ] = Field(min_length=6, max_length=6)
    automatic_production_promotion_allowed: Literal[False]

    @model_validator(mode="after")
    def validate_ties(self) -> "SelectionConfig":
        expected = [
            "combined_dev_72_relaxed_f1_desc",
            "combined_dev_72_exact_recall_desc",
            "threshold_sum_desc",
            "title_threshold_desc",
            "abstract_threshold_desc",
            "trial_id_asc",
        ]
        if self.tie_break_order != expected:
            raise ValueError("tie-break order drifted")
        return self


class DecisionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["development_candidate_gate_not_independent_acceptance"]
    selected_policy_minimum_consumed_heldout_exact_f1: Literal[0.396882]
    selected_policy_minimum_combined_dev_exact_f1: Literal[0.386393]
    selected_policy_minimum_consumed_heldout_relaxed_f1_desirable: Literal[0.414868]
    require_semantic_guardrails: Literal[True]
    all_hard_gates_required_for_promising: Literal[True]
    selected_trial_is_not_automatic_acceptance: Literal[True]


class CalibrationSafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_inference_allowed: Literal[False]
    model_or_tokenizer_download_allowed: Literal[False]
    prompt_changes_allowed: Literal[False]
    model_changes_allowed: Literal[False]
    threshold_search_allowed_after_contract_freeze: Literal[True]
    canonical_truth_mutation_allowed: Literal[False]
    reconcile_input_allowed: Literal[False]
    provider_api_allowed: Literal[False]
    fresh_heldout_consumption_allowed: Literal[False]
    production_extractor_selected: Literal[False]
    full_corpus_build_authorized: Literal[False]
    publication_allowed: Literal[False]
    overwrite_allowed: Literal[False]
    execute_required_for_writes: Literal[True]
    current_72_is_development_only: Literal[True]
    future_v02_acceptance_requires_new_disjoint_heldout: Literal[True]


class CalibrationOutputsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root: str = Field(min_length=1)
    immutable_calibration_directory: Literal[True]
    encoding: Literal["utf-8"]
    line_ending: Literal["lf"]
    required_files: list[str] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def validate_files(self) -> "CalibrationOutputsConfig":
        expected = {
            "manifest.json",
            "trials.jsonl",
            "selected_policy.json",
            "diagnostics.json",
            "README.md",
            "checksums.txt",
        }
        if set(self.required_files) != expected or len(set(self.required_files)) != 6:
            raise ValueError("calibration required_files drifted")
        return self


class CalibrationValidationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_dir: str = Field(min_length=1)
    require_independent_validator: Literal[True]
    require_deterministic_recomputation: Literal[True]
    require_input_hashes: Literal[True]
    require_checksums: Literal[True]
    require_lf_outputs: Literal[True]
    require_fail_closed_safety: Literal[True]


class SemanticPromptThresholdCalibrationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[CONFIG_SCHEMA_VERSION]
    layer: CalibrationLayerConfig
    lineage: CalibrationLineageConfig
    search: CalibrationSearchConfig
    semantic_guardrails: SemanticGuardrailsConfig
    selection: SelectionConfig
    decision: DecisionConfig
    safety: CalibrationSafetyConfig
    outputs: CalibrationOutputsConfig
    validation: CalibrationValidationConfig


class CalibrationTrial(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[TRIAL_SCHEMA_VERSION] = TRIAL_SCHEMA_VERSION
    calibration_id: str = Field(min_length=1)
    trial_id: str = Field(min_length=1)
    title_threshold: float = Field(ge=0.5, le=1.0)
    abstract_threshold: float = Field(ge=0.5, le=1.0)
    is_inherited_v02a_policy: bool
    selected_prediction_count: int = Field(ge=0)
    old_dev_prediction_count: int = Field(ge=0)
    consumed_heldout_prediction_count: int = Field(ge=0)
    old_dev_exact_f1: float | None
    consumed_heldout_exact_f1: float | None
    consumed_heldout_relaxed_f1: float | None
    combined_exact_precision: float | None
    combined_exact_recall: float | None
    combined_exact_f1: float | None
    combined_relaxed_f1: float | None
    model_to_method_count: int = Field(ge=0)
    method_to_task_count: int = Field(ge=0)
    total_type_mismatch_count: int = Field(ge=0)
    method_semantic_sink_count: int = Field(ge=0)
    max_predicted_type_mismatch_sink_count: int = Field(ge=0)
    semantic_guardrails_passed: bool
    eligible_for_selection: bool


class SelectedPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[SELECTED_POLICY_SCHEMA_VERSION] = SELECTED_POLICY_SCHEMA_VERSION
    calibration_id: str = Field(min_length=1)
    selected_trial_id: str = Field(min_length=1)
    title_threshold: float
    abstract_threshold: float
    selection_objective: Literal["combined_dev_72_exact_f1"]
    hard_gates: dict[str, dict[str, object]]
    desirable_signals: dict[str, dict[str, object]]
    all_hard_gates_passed: bool
    candidate_promising_for_future_freeze: bool
    production_acceptance: Literal[False] = False
    independent_v02_acceptance: Literal[False] = False
    full_corpus_build_authorized: Literal[False] = False
    future_v02_acceptance_requires_new_disjoint_heldout: Literal[True] = True


class CalibrationDiagnostics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[DIAGNOSTICS_SCHEMA_VERSION] = DIAGNOSTICS_SCHEMA_VERSION
    calibration_id: str = Field(min_length=1)
    trial_count: Literal[35]
    eligible_trial_count: int = Field(ge=0, le=35)
    inherited_v02a_trial_id: str = Field(min_length=1)
    inherited_v02a_trial_eligible: bool
    selected_trial_id: str = Field(min_length=1)
    selected_trial_is_boundary_title_floor: bool
    selected_trial_is_boundary_abstract_floor: bool
    raw_input_floor_may_be_binding: bool
    model_inference_executed: Literal[False] = False
    prompt_changes_executed: Literal[False] = False
    fresh_heldout_consumed: Literal[False] = False
    canonical_truth_mutated: Literal[False] = False


def load_semantic_prompt_threshold_calibration_config(
    path: Path,
) -> SemanticPromptThresholdCalibrationConfig:
    try:
        payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeySafeLoader)
    except yaml.YAMLError as exc:
        raise SemanticPromptThresholdCalibrationError(
            f"Invalid YAML config {path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise SemanticPromptThresholdCalibrationError(
            "threshold calibration config must contain a YAML mapping"
        )
    return SemanticPromptThresholdCalibrationConfig.model_validate(payload)
