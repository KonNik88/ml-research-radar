from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from radar_core.contracts.scientific_entity_evaluation import (
    ScientificEntityMatchingMetrics,
)
from radar_core.contracts.scientific_entity_evidence import (
    BUILD_ID_PATTERN,
    SHA256_PATTERN,
    ConfidenceKind,
    ScientificEntitySourceField,
    ScientificEntityType,
    sha256_text,
)


CALIBRATION_MANIFEST_SCHEMA_VERSION = (
    "scientific_entity_gliner_calibration_manifest_v0.1"
)
CALIBRATION_TRIAL_SCHEMA_VERSION = "scientific_entity_gliner_calibration_trial_v0.1"
CALIBRATION_PROFILES_SCHEMA_VERSION = (
    "scientific_entity_gliner_calibration_profiles_v0.1"
)
CALIBRATION_PARETO_SCHEMA_VERSION = "scientific_entity_gliner_calibration_pareto_v0.1"
CALIBRATION_DIAGNOSTICS_SCHEMA_VERSION = (
    "scientific_entity_gliner_calibration_diagnostics_v0.1"
)

TRIAL_ID_PREFIX = "calibration-trial:"
TRIAL_ID_PATTERN = rf"^{TRIAL_ID_PREFIX}[0-9a-f]{{32}}$"


class ScientificEntityCalibrationStatus(str, Enum):
    FIXTURE = "fixture"
    CANDIDATE = "candidate"


class ScientificEntityCalibrationTrialStage(str, Enum):
    BASELINE = "baseline"
    GLOBAL = "global"
    SOURCE_PAIR = "source_pair"
    TYPE_PROBE = "type_probe"


class ScientificEntityCalibrationProfileName(str, Enum):
    PRECISION_ORIENTED = "precision_oriented_f0_5"
    BALANCED = "balanced_f1"
    RECALL_ORIENTED = "recall_oriented_f2"


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def build_calibration_trial_id(
    *,
    calibration_id: str,
    stage: ScientificEntityCalibrationTrialStage | str,
    policy: "ScientificEntityThresholdPolicy | Mapping[str, Any]",
) -> str:
    parsed_policy = (
        policy
        if isinstance(policy, ScientificEntityThresholdPolicy)
        else ScientificEntityThresholdPolicy.model_validate(policy)
    )
    payload = [
        "scientific_entity_gliner_calibration_trial_v0.1",
        calibration_id,
        ScientificEntityCalibrationTrialStage(stage).value,
        parsed_policy.model_dump(mode="json"),
    ]
    return f"{TRIAL_ID_PREFIX}{sha256_text(_canonical_json(payload))[:32]}"


def f_beta(
    precision: float | None,
    recall: float | None,
    *,
    beta: float,
    decimal_places: int = 6,
) -> float | None:
    if precision is None or recall is None:
        return None
    beta_squared = beta * beta
    denominator = beta_squared * precision + recall
    if denominator == 0:
        return 0.0
    return round(
        (1 + beta_squared) * precision * recall / denominator,
        decimal_places,
    )


class ScientificEntityThresholdPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_threshold: float = Field(ge=0.0, le=1.0)
    source_field_thresholds: dict[ScientificEntitySourceField, float]
    entity_type_thresholds: dict[ScientificEntityType, float]

    @model_validator(mode="after")
    def validate_policy(self) -> "ScientificEntityThresholdPolicy":
        if len(self.source_field_thresholds) > len(ScientificEntitySourceField):
            raise ValueError("too many source-field thresholds")
        if len(self.entity_type_thresholds) > len(ScientificEntityType):
            raise ValueError("too many entity-type thresholds")
        return self

    def effective_threshold(
        self,
        *,
        source_field: ScientificEntitySourceField,
        entity_type: ScientificEntityType,
    ) -> float:
        source_threshold = self.source_field_thresholds.get(
            source_field,
            self.default_threshold,
        )
        return self.entity_type_thresholds.get(entity_type, source_threshold)


class ScientificEntityCalibrationTrial(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[CALIBRATION_TRIAL_SCHEMA_VERSION]
    calibration_id: str = Field(pattern=BUILD_ID_PATTERN)
    trial_id: str = Field(pattern=TRIAL_ID_PATTERN)
    stage: ScientificEntityCalibrationTrialStage
    policy: ScientificEntityThresholdPolicy
    selected_prediction_count: int = Field(ge=0)
    rejected_prediction_count: int = Field(ge=0)
    selected_prediction_count_by_source_field: dict[
        ScientificEntitySourceField,
        int,
    ]
    selected_prediction_count_by_entity_type: dict[ScientificEntityType, int]
    all_entity_types_represented: bool
    eligible_for_profile_selection: bool
    metrics: ScientificEntityMatchingMetrics
    metrics_by_source_field: dict[
        ScientificEntitySourceField,
        ScientificEntityMatchingMetrics,
    ]
    metrics_by_entity_type: dict[
        ScientificEntityType,
        ScientificEntityMatchingMetrics,
    ]
    exact_f0_5: float | None = Field(default=None, ge=0.0, le=1.0)
    exact_f2: float | None = Field(default=None, ge=0.0, le=1.0)
    relaxed_f0_5: float | None = Field(default=None, ge=0.0, le=1.0)
    relaxed_f2: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_trial(self) -> "ScientificEntityCalibrationTrial":
        expected_id = build_calibration_trial_id(
            calibration_id=self.calibration_id,
            stage=self.stage,
            policy=self.policy,
        )
        if self.trial_id != expected_id:
            raise ValueError("trial_id does not match calibration trial identity")

        expected_source_keys = set(ScientificEntitySourceField)
        expected_type_keys = set(ScientificEntityType)
        if set(self.selected_prediction_count_by_source_field) != expected_source_keys:
            raise ValueError("selected source-field counts must cover both fields")
        if set(self.selected_prediction_count_by_entity_type) != expected_type_keys:
            raise ValueError("selected entity-type counts must cover all six types")
        if sum(self.selected_prediction_count_by_source_field.values()) != (
            self.selected_prediction_count
        ):
            raise ValueError("source-field counts do not sum to selected count")
        if sum(self.selected_prediction_count_by_entity_type.values()) != (
            self.selected_prediction_count
        ):
            raise ValueError("entity-type counts do not sum to selected count")
        represented = all(
            count > 0
            for count in self.selected_prediction_count_by_entity_type.values()
        )
        if self.all_entity_types_represented != represented:
            raise ValueError("all_entity_types_represented does not match counts")
        if self.metrics.exact.prediction_support != self.selected_prediction_count:
            raise ValueError("exact prediction support does not match selected count")
        if self.metrics.relaxed.prediction_support != self.selected_prediction_count:
            raise ValueError("relaxed prediction support does not match selected count")
        if set(self.metrics_by_source_field) != expected_source_keys:
            raise ValueError("source-field metrics must cover title and abstract")
        if set(self.metrics_by_entity_type) != expected_type_keys:
            raise ValueError("entity-type metrics must cover all six types")

        source_keys = set(self.policy.source_field_thresholds)
        type_keys = set(self.policy.entity_type_thresholds)
        if self.stage in {
            ScientificEntityCalibrationTrialStage.BASELINE,
            ScientificEntityCalibrationTrialStage.GLOBAL,
        }:
            if source_keys or type_keys:
                raise ValueError("baseline/global trials cannot contain overrides")
        elif self.stage == ScientificEntityCalibrationTrialStage.SOURCE_PAIR:
            if source_keys != expected_source_keys or type_keys:
                raise ValueError(
                    "source-pair trials require both source overrides and no "
                    "type override"
                )
        else:
            if source_keys != expected_source_keys or len(type_keys) != 1:
                raise ValueError(
                    "type-probe trials require both source overrides and one "
                    "type override"
                )
            if self.eligible_for_profile_selection:
                raise ValueError("type-probe trials are diagnostic only")

        exact = self.metrics.exact
        relaxed = self.metrics.relaxed
        expected_values = {
            "exact_f0_5": f_beta(exact.precision, exact.recall, beta=0.5),
            "exact_f2": f_beta(exact.precision, exact.recall, beta=2.0),
            "relaxed_f0_5": f_beta(relaxed.precision, relaxed.recall, beta=0.5),
            "relaxed_f2": f_beta(relaxed.precision, relaxed.recall, beta=2.0),
        }
        for name, expected in expected_values.items():
            if getattr(self, name) != expected:
                raise ValueError(f"{name} does not match trial metrics")
        return self


class ScientificEntityCalibrationProfileSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_name: ScientificEntityCalibrationProfileName
    beta: Literal[0.5, 1.0, 2.0]
    trial_id: str = Field(pattern=TRIAL_ID_PATTERN)
    selection_metric: Literal["exact_f_beta"]
    selection_score: float = Field(ge=0.0, le=1.0)
    policy: ScientificEntityThresholdPolicy
    selected_prediction_count: int = Field(ge=1)
    all_entity_types_represented: Literal[True]
    metrics: ScientificEntityMatchingMetrics
    dev_only: Literal[True]
    promotion_authorized: Literal[False]

    @model_validator(mode="after")
    def validate_selection_score(
        self,
    ) -> "ScientificEntityCalibrationProfileSelection":
        exact = self.metrics.exact
        expected = f_beta(exact.precision, exact.recall, beta=self.beta)
        if expected is None or self.selection_score != expected:
            raise ValueError("selection_score does not match exact F-beta")
        return self


class ScientificEntityCalibrationProfiles(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[CALIBRATION_PROFILES_SCHEMA_VERSION]
    calibration_id: str = Field(pattern=BUILD_ID_PATTERN)
    selections: list[ScientificEntityCalibrationProfileSelection] = Field(
        min_length=3,
        max_length=3,
    )
    selected_trial_ids_may_repeat: Literal[True]
    selected_profile_is_production_extractor: Literal[False]

    @model_validator(mode="after")
    def validate_profiles(self) -> "ScientificEntityCalibrationProfiles":
        if {row.profile_name for row in self.selections} != set(
            ScientificEntityCalibrationProfileName
        ):
            raise ValueError("profiles must cover F0.5, F1, and F2 selections")
        expected_beta = {
            ScientificEntityCalibrationProfileName.PRECISION_ORIENTED: 0.5,
            ScientificEntityCalibrationProfileName.BALANCED: 1.0,
            ScientificEntityCalibrationProfileName.RECALL_ORIENTED: 2.0,
        }
        if any(row.beta != expected_beta[row.profile_name] for row in self.selections):
            raise ValueError("profile beta does not match profile name")
        return self


class ScientificEntityCalibrationParetoFrontier(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[CALIBRATION_PARETO_SCHEMA_VERSION]
    calibration_id: str = Field(pattern=BUILD_ID_PATTERN)
    objective_axes: Literal["exact_precision_and_exact_recall"]
    trial_ids: list[str] = Field(min_length=1)
    type_probe_trials_excluded: Literal[True]

    @model_validator(mode="after")
    def validate_trial_ids(self) -> "ScientificEntityCalibrationParetoFrontier":
        if len(set(self.trial_ids)) != len(self.trial_ids):
            raise ValueError("Pareto trial_ids must not contain duplicates")
        if any(not re.fullmatch(TRIAL_ID_PATTERN, value) for value in self.trial_ids):
            raise ValueError("invalid Pareto trial_id")
        return self


class ScientificEntityTypeProbeDiagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: ScientificEntityType
    best_trial_id: str = Field(pattern=TRIAL_ID_PATTERN)
    base_trial_id: str = Field(pattern=TRIAL_ID_PATTERN)
    best_threshold: float = Field(ge=0.0, le=1.0)
    exact_entity_type_f1_delta_from_base: float = Field(ge=-1.0, le=1.0)
    descriptive_only: Literal[True]


class ScientificEntityCalibrationDiagnostics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[CALIBRATION_DIAGNOSTICS_SCHEMA_VERSION]
    calibration_id: str = Field(pattern=BUILD_ID_PATTERN)
    source_pair_base_trial_id: str = Field(pattern=TRIAL_ID_PATTERN)
    type_probe_rows: list[ScientificEntityTypeProbeDiagnostic] = Field(
        min_length=6,
        max_length=6,
    )
    combined_type_specific_policy_selected: Literal[False]
    confidence_scores_reinterpreted_as_probabilities: Literal[False]

    @model_validator(mode="after")
    def validate_types(self) -> "ScientificEntityCalibrationDiagnostics":
        if {row.entity_type for row in self.type_probe_rows} != set(
            ScientificEntityType
        ):
            raise ValueError("type-probe diagnostics must cover all six entity types")
        return self


class ScientificEntityCalibrationInputs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    documents_path: str = Field(min_length=1)
    documents_sha256: str = Field(pattern=SHA256_PATTERN)
    document_count: int = Field(ge=1)
    review_id: str = Field(pattern=BUILD_ID_PATTERN)
    review_manifest_path: str = Field(min_length=1)
    review_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    reference_mentions_path: str = Field(min_length=1)
    reference_mentions_sha256: str = Field(pattern=SHA256_PATTERN)
    reference_mention_count: int = Field(ge=1)
    prediction_build_id: str = Field(pattern=BUILD_ID_PATTERN)
    prediction_manifest_path: str = Field(min_length=1)
    prediction_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    prediction_mentions_path: str = Field(min_length=1)
    prediction_mentions_sha256: str = Field(pattern=SHA256_PATTERN)
    prediction_quality_path: str = Field(min_length=1)
    prediction_quality_sha256: str = Field(pattern=SHA256_PATTERN)
    prediction_mention_count: int = Field(ge=1)
    prediction_extractor_fingerprint: str = Field(pattern=SHA256_PATTERN)
    input_threshold: float = Field(ge=0.0, le=1.0)
    baseline_evaluation_id: str = Field(pattern=BUILD_ID_PATTERN)
    baseline_evaluation_manifest_path: str = Field(min_length=1)
    baseline_evaluation_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    baseline_metrics_path: str = Field(min_length=1)
    baseline_metrics_sha256: str = Field(pattern=SHA256_PATTERN)


class ScientificEntityGLiNERCalibrationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[CALIBRATION_MANIFEST_SCHEMA_VERSION]
    calibration_id: str = Field(pattern=BUILD_ID_PATTERN)
    status: ScientificEntityCalibrationStatus
    generated_at_utc: datetime
    config_path: str = Field(min_length=1)
    config_sha256: str = Field(pattern=SHA256_PATTERN)
    inputs: ScientificEntityCalibrationInputs
    search_space_trial_count: int = Field(ge=1)
    eligible_trial_count: int = Field(ge=1)
    trials_file: Literal["trials.jsonl"]
    trials_sha256: str = Field(pattern=SHA256_PATTERN)
    pareto_file: Literal["pareto_frontier.json"]
    pareto_sha256: str = Field(pattern=SHA256_PATTERN)
    profiles_file: Literal["recommended_profiles.json"]
    profiles_sha256: str = Field(pattern=SHA256_PATTERN)
    diagnostics_file: Literal["diagnostics.json"]
    diagnostics_sha256: str = Field(pattern=SHA256_PATTERN)
    confidence_kind: Literal[ConfidenceKind.MODEL_SCORE]
    confidence_scores_reinterpreted_as_probabilities: Literal[False]
    calibration_id_written_to_mentions: Literal[False]
    current_dev_set_becomes_held_out: Literal[False]
    metrics_are_descriptive_only: Literal[True]
    production_extractor_selected: Literal[False]
    canonical_truth_mutated: Literal[False]
    may_be_used_as_reconcile_input: Literal[False]
    model_inference_executed: Literal[False]
    model_downloaded: Literal[False]
    provider_api_called: Literal[False]
    full_corpus_build_authorized: Literal[False]
    redistribution_allowed: Literal[False]
    publication_ready: Literal[False]

    @model_validator(mode="after")
    def validate_manifest(self) -> "ScientificEntityGLiNERCalibrationManifest":
        if (
            self.generated_at_utc.tzinfo is None
            or self.generated_at_utc.utcoffset() != timedelta(0)
        ):
            raise ValueError("generated_at_utc must use UTC offset +00:00")
        if self.eligible_trial_count > self.search_space_trial_count:
            raise ValueError("eligible trial count exceeds total trial count")
        return self
