from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from radar_core.contracts.scientific_entity_evaluation import (
    ScientificEntityReferenceMention,
)
from radar_core.contracts.scientific_entity_evidence import (
    ConfidenceKind,
    ScientificEntityMentionEvidence,
    ScientificEntitySourceField,
    ScientificEntityType,
    sha256_text,
)
from radar_core.contracts.scientific_entity_gliner_calibration import (
    CALIBRATION_DIAGNOSTICS_SCHEMA_VERSION,
    CALIBRATION_PARETO_SCHEMA_VERSION,
    CALIBRATION_PROFILES_SCHEMA_VERSION,
    CALIBRATION_TRIAL_SCHEMA_VERSION,
    ScientificEntityCalibrationDiagnostics,
    ScientificEntityCalibrationParetoFrontier,
    ScientificEntityCalibrationProfileName,
    ScientificEntityCalibrationProfileSelection,
    ScientificEntityCalibrationProfiles,
    ScientificEntityCalibrationTrial,
    ScientificEntityCalibrationTrialStage,
    ScientificEntityThresholdPolicy,
    ScientificEntityTypeProbeDiagnostic,
    build_calibration_trial_id,
    f_beta,
)
from radar_core.entities.scientific_entity_evaluation import (
    ScientificEntityEvaluationConfig,
    evaluate_mentions,
)


CALIBRATION_CONFIG_SCHEMA_VERSION = (
    "scientific_entity_gliner_dev_calibration_config_v0.1"
)
CALIBRATION_OUTPUT_SCHEMA_VERSION = (
    "scientific_entity_gliner_dev_calibration_output_v0.1"
)


class ScientificEntityGLiNERCalibrationError(ValueError):
    """Raised when a bounded GLiNER calibration request is invalid."""


class CalibrationLayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["scientific_entity_gliner_dev_calibration"]
    version: Literal["v0.1"]
    status: Literal["dev_calibration"]
    layer_kind: Literal["derived_bounded_configuration_evidence"]
    description: str = Field(min_length=1)


class CalibrationEvaluationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluation_config_path: Literal[
        "configs/scientific_entity_evaluation_v0.1.yaml"
    ]
    reuse_existing_matching_policy: Literal[True]
    recompute_every_trial: Literal[True]
    baseline_metrics_must_match: Literal[True]
    decimal_places: Literal[6]


class CalibrationSearchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_threshold: Literal[0.5]
    threshold_is_inclusive: Literal[True]
    threshold_decimal_places: Literal[2]
    global_thresholds: list[float] = Field(min_length=1)
    title_thresholds: list[float] = Field(min_length=1)
    abstract_thresholds: list[float] = Field(min_length=1)
    type_probe_thresholds: list[float] = Field(min_length=1)
    source_pair_search_enabled: Literal[True]
    type_probe_search_enabled: Literal[True]
    type_probes_diagnostic_only: Literal[True]
    combined_type_specific_policy_selection_allowed: Literal[False]
    full_source_field_by_type_cartesian_search_allowed: Literal[False]
    hard_max_trial_count: Literal[200]

    @model_validator(mode="after")
    def validate_search_space(self) -> "CalibrationSearchConfig":
        grids = {
            "global_thresholds": self.global_thresholds,
            "title_thresholds": self.title_thresholds,
            "abstract_thresholds": self.abstract_thresholds,
            "type_probe_thresholds": self.type_probe_thresholds,
        }
        for name, values in grids.items():
            if values != sorted(values) or len(values) != len(set(values)):
                raise ValueError(f"{name} must be sorted and unique")
            if any(value < self.input_threshold or value > 0.95 for value in values):
                raise ValueError(f"{name} must stay within [input_threshold, 0.95]")
            if any(
                round(value, self.threshold_decimal_places) != value
                for value in values
            ):
                raise ValueError(f"{name} exceeds threshold precision")
        if self.input_threshold in self.global_thresholds:
            raise ValueError("global_thresholds must not duplicate the baseline trial")
        if self.input_threshold not in self.title_thresholds:
            raise ValueError("title_thresholds must include input_threshold")
        if self.input_threshold not in self.abstract_thresholds:
            raise ValueError("abstract_thresholds must include input_threshold")
        if self.input_threshold not in self.type_probe_thresholds:
            raise ValueError("type_probe_thresholds must include input_threshold")
        trial_count = (
            1
            + len(self.global_thresholds)
            + len(self.title_thresholds) * len(self.abstract_thresholds)
            + len(ScientificEntityType) * len(self.type_probe_thresholds)
        )
        if trial_count > self.hard_max_trial_count:
            raise ValueError("declared calibration search exceeds hard trial limit")
        return self

    @property
    def declared_trial_count(self) -> int:
        return (
            1
            + len(self.global_thresholds)
            + len(self.title_thresholds) * len(self.abstract_thresholds)
            + len(ScientificEntityType) * len(self.type_probe_thresholds)
        )


class CalibrationProfileSelectionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eligible_stages: list[
        Literal["baseline", "global", "source_pair"]
    ] = Field(min_length=3, max_length=3)
    require_all_entity_types_represented: Literal[True]
    primary_metric: Literal["exact_f_beta"]
    profile_betas: dict[ScientificEntityCalibrationProfileName, float]
    tie_break_order: list[
        Literal[
            "primary_metric_desc",
            "exact_precision_desc",
            "exact_recall_desc",
            "relaxed_f1_desc",
            "policy_complexity_asc",
            "trial_id_asc",
        ]
    ] = Field(min_length=6, max_length=6)
    pareto_axes: Literal["exact_precision_and_exact_recall"]
    promotion_verdict_allowed: Literal[False]

    @model_validator(mode="after")
    def validate_profiles(self) -> "CalibrationProfileSelectionConfig":
        if self.eligible_stages != ["baseline", "global", "source_pair"]:
            raise ValueError("eligible stages must preserve bounded search order")
        expected = {
            ScientificEntityCalibrationProfileName.PRECISION_ORIENTED: 0.5,
            ScientificEntityCalibrationProfileName.BALANCED: 1.0,
            ScientificEntityCalibrationProfileName.RECALL_ORIENTED: 2.0,
        }
        if self.profile_betas != expected:
            raise ValueError("profile_betas must define F0.5, F1, and F2")
        expected_ties = [
            "primary_metric_desc",
            "exact_precision_desc",
            "exact_recall_desc",
            "relaxed_f1_desc",
            "policy_complexity_asc",
            "trial_id_asc",
        ]
        if self.tie_break_order != expected_ties:
            raise ValueError("tie_break_order must remain deterministic")
        return self


class CalibrationSafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_max_documents: Literal[32]
    hard_max_documents: Literal[100]
    hard_max_reference_mentions: Literal[5000]
    hard_max_prediction_mentions: Literal[5000]
    fail_if_input_exceeds_limit: Literal[True]
    truncation_allowed: Literal[False]
    forbid_current_canonical_input: Literal[True]
    current_canonical_path: Literal[
        "data/analytics/reconciled/canonical_documents.jsonl"
    ]
    require_model_score_confidence: Literal[True]
    require_null_mention_calibration_id: Literal[True]
    require_all_scores_at_or_above_input_threshold: Literal[True]
    allowed_statuses: list[Literal["fixture", "candidate"]] = Field(
        min_length=2,
        max_length=2,
    )
    accepted_or_promoted_status_allowed: Literal[False]
    execute_required_for_writes: Literal[True]
    overwrite_allowed: Literal[False]
    model_inference_allowed: Literal[False]
    model_or_tokenizer_download_allowed: Literal[False]
    provider_api_allowed: Literal[False]
    canonical_truth_mutation_allowed: Literal[False]
    reconcile_input_allowed: Literal[False]
    full_corpus_build_authorized: Literal[False]
    redistribution_allowed: Literal[False]
    publication_allowed: Literal[False]

    @model_validator(mode="after")
    def validate_safety(self) -> "CalibrationSafetyConfig":
        if self.default_max_documents > self.hard_max_documents:
            raise ValueError("default document limit exceeds hard limit")
        if self.allowed_statuses != ["fixture", "candidate"]:
            raise ValueError("allowed statuses must be fixture and candidate")
        return self


class CalibrationOutputsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root: str = Field(min_length=1)
    immutable_calibration_directory: Literal[True]
    mutable_latest_pointer: Literal[False]
    encoding: Literal["utf-8"]
    line_ending: Literal["lf"]
    required_files: list[str] = Field(min_length=1)


class CalibrationValidationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_dir: str = Field(min_length=1)
    require_independent_validator: Literal[True]
    require_trial_recomputation: Literal[True]
    require_profile_recomputation: Literal[True]
    require_pareto_recomputation: Literal[True]
    require_checksums: Literal[True]
    require_lf_outputs: Literal[True]
    require_input_hashes: Literal[True]
    require_fail_closed_safety: Literal[True]


class CalibrationFixturesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    documents_path: Literal[
        "tests/fixtures/scientific_entity_evaluation_v0_1/canonical_documents.jsonl"
    ]
    review_manifest_path: Literal[
        "tests/fixtures/scientific_entity_evaluation_v0_1/review_manifest.json"
    ]
    reference_mentions_path: Literal[
        "tests/fixtures/scientific_entity_evaluation_v0_1/reference_mentions.jsonl"
    ]
    prediction_build_dir: Literal[
        "tests/fixtures/scientific_entity_gliner_dev_calibration_v0_1/"
        "prediction_build"
    ]
    baseline_evaluation_dir: Literal[
        "tests/fixtures/scientific_entity_gliner_dev_calibration_v0_1/"
        "baseline_evaluation"
    ]
    synthetic_only: Literal[True]


class ScientificEntityGLiNERCalibrationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[CALIBRATION_CONFIG_SCHEMA_VERSION]
    layer: CalibrationLayerConfig
    evaluation: CalibrationEvaluationConfig
    search: CalibrationSearchConfig
    profiles: CalibrationProfileSelectionConfig
    safety: CalibrationSafetyConfig
    outputs: CalibrationOutputsConfig
    validation: CalibrationValidationConfig
    fixtures: CalibrationFixturesConfig

    @model_validator(mode="after")
    def validate_output_layout(self) -> "ScientificEntityGLiNERCalibrationConfig":
        expected = {
            "manifest.json",
            "trials.jsonl",
            "pareto_frontier.json",
            "recommended_profiles.json",
            "diagnostics.json",
            "README.md",
            "checksums.txt",
        }
        if set(self.outputs.required_files) != expected:
            raise ValueError("calibration output layout does not match v0.1 contract")
        if len(set(self.outputs.required_files)) != len(self.outputs.required_files):
            raise ValueError("calibration output files must not contain duplicates")
        return self


class _UniqueKeySafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueKeySafeLoader,
    node: yaml.nodes.MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key: {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def load_gliner_calibration_config(
    path: Path,
) -> ScientificEntityGLiNERCalibrationConfig:
    try:
        payload = yaml.load(
            path.read_text(encoding="utf-8"),
            Loader=_UniqueKeySafeLoader,
        )
    except yaml.YAMLError as exc:
        raise ScientificEntityGLiNERCalibrationError(
            f"Invalid YAML config {path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ScientificEntityGLiNERCalibrationError(f"Expected YAML object: {path}")
    return ScientificEntityGLiNERCalibrationConfig.model_validate(payload)


def canonical_semantic_json(payload: object) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def gliner_calibration_config_sha256(
    config: ScientificEntityGLiNERCalibrationConfig,
) -> str:
    return sha256_text(canonical_semantic_json(config.model_dump(mode="json")))


def filter_predictions(
    predictions: Sequence[ScientificEntityMentionEvidence],
    *,
    policy: ScientificEntityThresholdPolicy,
    input_threshold: float,
) -> tuple[ScientificEntityMentionEvidence, ...]:
    selected: list[ScientificEntityMentionEvidence] = []
    for prediction in predictions:
        if prediction.confidence_kind != ConfidenceKind.MODEL_SCORE:
            raise ScientificEntityGLiNERCalibrationError(
                "calibration input requires model_score confidence"
            )
        if prediction.confidence_score is None:
            raise ScientificEntityGLiNERCalibrationError(
                "calibration input prediction is missing confidence_score"
            )
        if prediction.calibration_id is not None:
            raise ScientificEntityGLiNERCalibrationError(
                "calibration input requires null mention calibration_id"
            )
        if prediction.confidence_score < input_threshold:
            raise ScientificEntityGLiNERCalibrationError(
                "prediction score is below the declared input threshold"
            )
        threshold = policy.effective_threshold(
            source_field=prediction.source_field,
            entity_type=prediction.entity_type,
        )
        if threshold < input_threshold:
            raise ScientificEntityGLiNERCalibrationError(
                "trial threshold cannot be lower than the input threshold"
            )
        if prediction.confidence_score >= threshold:
            selected.append(prediction)
    return tuple(selected)


def _trial_evaluation_id(calibration_id: str, trial_id: str) -> str:
    digest = sha256_text(f"{calibration_id}|{trial_id}")[:32]
    return f"scientific-entity-calibration-trial-{digest}"


def _build_trial(
    *,
    calibration_id: str,
    stage: ScientificEntityCalibrationTrialStage,
    policy: ScientificEntityThresholdPolicy,
    references: Sequence[ScientificEntityReferenceMention],
    predictions: Sequence[ScientificEntityMentionEvidence],
    document_count: int,
    evaluation_config: ScientificEntityEvaluationConfig,
    input_threshold: float,
    profile_requires_all_types: bool,
) -> ScientificEntityCalibrationTrial:
    trial_id = build_calibration_trial_id(
        calibration_id=calibration_id,
        stage=stage,
        policy=policy,
    )
    selected = filter_predictions(
        predictions,
        policy=policy,
        input_threshold=input_threshold,
    )
    result = evaluate_mentions(
        evaluation_id=_trial_evaluation_id(calibration_id, trial_id),
        document_count=document_count,
        references=references,
        predictions=selected,
        config=evaluation_config,
    )
    source_counts = Counter(row.source_field for row in selected)
    type_counts = Counter(row.entity_type for row in selected)
    by_type = {
        row.entity_type: row.metrics for row in result.per_type_metrics.rows
    }
    all_types = all(
        type_counts[entity_type] > 0 for entity_type in ScientificEntityType
    )
    eligible_stage = stage in {
        ScientificEntityCalibrationTrialStage.BASELINE,
        ScientificEntityCalibrationTrialStage.GLOBAL,
        ScientificEntityCalibrationTrialStage.SOURCE_PAIR,
    }
    exact = result.metrics.micro.exact
    relaxed = result.metrics.micro.relaxed
    return ScientificEntityCalibrationTrial(
        schema_version=CALIBRATION_TRIAL_SCHEMA_VERSION,
        calibration_id=calibration_id,
        trial_id=trial_id,
        stage=stage,
        policy=policy,
        selected_prediction_count=len(selected),
        rejected_prediction_count=len(predictions) - len(selected),
        selected_prediction_count_by_source_field={
            source_field: source_counts[source_field]
            for source_field in ScientificEntitySourceField
        },
        selected_prediction_count_by_entity_type={
            entity_type: type_counts[entity_type]
            for entity_type in ScientificEntityType
        },
        all_entity_types_represented=all_types,
        eligible_for_profile_selection=(
            eligible_stage and (all_types or not profile_requires_all_types)
        ),
        metrics=result.metrics.micro,
        metrics_by_source_field=result.metrics.by_source_field,
        metrics_by_entity_type=by_type,
        exact_f0_5=f_beta(exact.precision, exact.recall, beta=0.5),
        exact_f2=f_beta(exact.precision, exact.recall, beta=2.0),
        relaxed_f0_5=f_beta(relaxed.precision, relaxed.recall, beta=0.5),
        relaxed_f2=f_beta(relaxed.precision, relaxed.recall, beta=2.0),
    )


def _policy_complexity(trial: ScientificEntityCalibrationTrial) -> int:
    return len(trial.policy.source_field_thresholds) + len(
        trial.policy.entity_type_thresholds
    )


def _primary_metric(trial: ScientificEntityCalibrationTrial, beta: float) -> float:
    if beta == 0.5:
        value = trial.exact_f0_5
    elif beta == 1.0:
        value = trial.metrics.exact.f1
    elif beta == 2.0:
        value = trial.exact_f2
    else:  # pragma: no cover - config contract prevents this branch
        raise ScientificEntityGLiNERCalibrationError(f"Unsupported beta: {beta}")
    return -1.0 if value is None else value


def select_profile_trial(
    trials: Sequence[ScientificEntityCalibrationTrial],
    *,
    beta: float,
) -> ScientificEntityCalibrationTrial:
    eligible = [row for row in trials if row.eligible_for_profile_selection]
    if not eligible:
        raise ScientificEntityGLiNERCalibrationError(
            "no trial satisfies profile-selection safety constraints"
        )

    def sort_key(row: ScientificEntityCalibrationTrial) -> tuple[Any, ...]:
        exact = row.metrics.exact
        relaxed_f1 = row.metrics.relaxed.f1
        return (
            -_primary_metric(row, beta),
            -(exact.precision if exact.precision is not None else -1.0),
            -(exact.recall if exact.recall is not None else -1.0),
            -(relaxed_f1 if relaxed_f1 is not None else -1.0),
            _policy_complexity(row),
            row.trial_id,
        )

    return sorted(eligible, key=sort_key)[0]


def _pareto_frontier(
    trials: Sequence[ScientificEntityCalibrationTrial],
) -> list[ScientificEntityCalibrationTrial]:
    eligible = [row for row in trials if row.eligible_for_profile_selection]
    frontier: list[ScientificEntityCalibrationTrial] = []
    for candidate in eligible:
        cp = candidate.metrics.exact.precision
        cr = candidate.metrics.exact.recall
        if cp is None or cr is None:
            continue
        dominated = False
        for other in eligible:
            if other.trial_id == candidate.trial_id:
                continue
            op = other.metrics.exact.precision
            ore = other.metrics.exact.recall
            if op is None or ore is None:
                continue
            if op >= cp and ore >= cr and (op > cp or ore > cr):
                dominated = True
                break
        if not dominated:
            frontier.append(candidate)
    return sorted(
        frontier,
        key=lambda row: (
            -(row.metrics.exact.recall or 0.0),
            -(row.metrics.exact.precision or 0.0),
            row.trial_id,
        ),
    )


@dataclass(frozen=True, slots=True)
class ScientificEntityCalibrationComputation:
    trials: tuple[ScientificEntityCalibrationTrial, ...]
    pareto: ScientificEntityCalibrationParetoFrontier
    profiles: ScientificEntityCalibrationProfiles
    diagnostics: ScientificEntityCalibrationDiagnostics


def calibrate_predictions(
    *,
    calibration_id: str,
    document_count: int,
    references: Sequence[ScientificEntityReferenceMention],
    predictions: Sequence[ScientificEntityMentionEvidence],
    config: ScientificEntityGLiNERCalibrationConfig,
    evaluation_config: ScientificEntityEvaluationConfig,
) -> ScientificEntityCalibrationComputation:
    if document_count < 1:
        raise ScientificEntityGLiNERCalibrationError("document_count must be positive")
    if document_count > config.safety.hard_max_documents:
        raise ScientificEntityGLiNERCalibrationError("document hard limit exceeded")
    if len(references) > config.safety.hard_max_reference_mentions:
        raise ScientificEntityGLiNERCalibrationError("reference hard limit exceeded")
    if len(predictions) > config.safety.hard_max_prediction_mentions:
        raise ScientificEntityGLiNERCalibrationError("prediction hard limit exceeded")
    if not predictions:
        raise ScientificEntityGLiNERCalibrationError(
            "prediction input must not be empty"
        )

    search = config.search
    profile_requires_all_types = (
        config.profiles.require_all_entity_types_represented
    )
    initial_specs: list[
        tuple[ScientificEntityCalibrationTrialStage, ScientificEntityThresholdPolicy]
    ] = [
        (
            ScientificEntityCalibrationTrialStage.BASELINE,
            ScientificEntityThresholdPolicy(
                default_threshold=search.input_threshold,
                source_field_thresholds={},
                entity_type_thresholds={},
            ),
        )
    ]
    initial_specs.extend(
        (
            ScientificEntityCalibrationTrialStage.GLOBAL,
            ScientificEntityThresholdPolicy(
                default_threshold=threshold,
                source_field_thresholds={},
                entity_type_thresholds={},
            ),
        )
        for threshold in search.global_thresholds
    )
    initial_specs.extend(
        (
            ScientificEntityCalibrationTrialStage.SOURCE_PAIR,
            ScientificEntityThresholdPolicy(
                default_threshold=search.input_threshold,
                source_field_thresholds={
                    ScientificEntitySourceField.TITLE: title_threshold,
                    ScientificEntitySourceField.ABSTRACT: abstract_threshold,
                },
                entity_type_thresholds={},
            ),
        )
        for title_threshold in search.title_thresholds
        for abstract_threshold in search.abstract_thresholds
    )

    trials = [
        _build_trial(
            calibration_id=calibration_id,
            stage=stage,
            policy=policy,
            references=references,
            predictions=predictions,
            document_count=document_count,
            evaluation_config=evaluation_config,
            input_threshold=search.input_threshold,
            profile_requires_all_types=profile_requires_all_types,
        )
        for stage, policy in initial_specs
    ]
    source_candidates = [
        row
        for row in trials
        if row.stage == ScientificEntityCalibrationTrialStage.SOURCE_PAIR
        and row.eligible_for_profile_selection
    ]
    source_base = select_profile_trial(source_candidates, beta=1.0)

    for entity_type in ScientificEntityType:
        for threshold in search.type_probe_thresholds:
            policy = ScientificEntityThresholdPolicy(
                default_threshold=source_base.policy.default_threshold,
                source_field_thresholds=source_base.policy.source_field_thresholds,
                entity_type_thresholds={entity_type: threshold},
            )
            trials.append(
                _build_trial(
                    calibration_id=calibration_id,
                    stage=ScientificEntityCalibrationTrialStage.TYPE_PROBE,
                    policy=policy,
                    references=references,
                    predictions=predictions,
                    document_count=document_count,
                    evaluation_config=evaluation_config,
                    input_threshold=search.input_threshold,
                    profile_requires_all_types=profile_requires_all_types,
                )
            )

    if len(trials) != search.declared_trial_count:
        raise ScientificEntityGLiNERCalibrationError(
            "computed trial count does not match declared search space"
        )
    if len({row.trial_id for row in trials}) != len(trials):
        raise ScientificEntityGLiNERCalibrationError("duplicate calibration trial_id")

    selections: list[ScientificEntityCalibrationProfileSelection] = []
    for profile_name in ScientificEntityCalibrationProfileName:
        beta = config.profiles.profile_betas[profile_name]
        selected = select_profile_trial(trials, beta=beta)
        selections.append(
            ScientificEntityCalibrationProfileSelection(
                profile_name=profile_name,
                beta=beta,
                trial_id=selected.trial_id,
                selection_metric="exact_f_beta",
                selection_score=_primary_metric(selected, beta),
                policy=selected.policy,
                selected_prediction_count=selected.selected_prediction_count,
                all_entity_types_represented=True,
                metrics=selected.metrics,
                dev_only=True,
                promotion_authorized=False,
            )
        )
    profiles = ScientificEntityCalibrationProfiles(
        schema_version=CALIBRATION_PROFILES_SCHEMA_VERSION,
        calibration_id=calibration_id,
        selections=selections,
        selected_trial_ids_may_repeat=True,
        selected_profile_is_production_extractor=False,
    )

    frontier = _pareto_frontier(trials)
    if not frontier:
        raise ScientificEntityGLiNERCalibrationError(
            "empty exact-metric Pareto frontier"
        )
    pareto = ScientificEntityCalibrationParetoFrontier(
        schema_version=CALIBRATION_PARETO_SCHEMA_VERSION,
        calibration_id=calibration_id,
        objective_axes="exact_precision_and_exact_recall",
        trial_ids=[row.trial_id for row in frontier],
        type_probe_trials_excluded=True,
    )

    type_probe_rows: list[ScientificEntityTypeProbeDiagnostic] = []
    for entity_type in ScientificEntityType:
        candidates = [
            row
            for row in trials
            if row.stage == ScientificEntityCalibrationTrialStage.TYPE_PROBE
            and set(row.policy.entity_type_thresholds) == {entity_type}
        ]
        base_f1 = source_base.metrics_by_entity_type[entity_type].exact.f1 or 0.0
        best = sorted(
            candidates,
            key=lambda row: (
                -(row.metrics_by_entity_type[entity_type].exact.f1 or 0.0),
                -(row.metrics_by_entity_type[entity_type].exact.precision or 0.0),
                -(row.metrics_by_entity_type[entity_type].exact.recall or 0.0),
                row.policy.entity_type_thresholds[entity_type],
                row.trial_id,
            ),
        )[0]
        best_f1 = best.metrics_by_entity_type[entity_type].exact.f1 or 0.0
        type_probe_rows.append(
            ScientificEntityTypeProbeDiagnostic(
                entity_type=entity_type,
                best_trial_id=best.trial_id,
                base_trial_id=source_base.trial_id,
                best_threshold=best.policy.entity_type_thresholds[entity_type],
                exact_entity_type_f1_delta_from_base=round(best_f1 - base_f1, 6),
                descriptive_only=True,
            )
        )
    diagnostics = ScientificEntityCalibrationDiagnostics(
        schema_version=CALIBRATION_DIAGNOSTICS_SCHEMA_VERSION,
        calibration_id=calibration_id,
        source_pair_base_trial_id=source_base.trial_id,
        type_probe_rows=type_probe_rows,
        combined_type_specific_policy_selected=False,
        confidence_scores_reinterpreted_as_probabilities=False,
    )
    return ScientificEntityCalibrationComputation(
        trials=tuple(trials),
        pareto=pareto,
        profiles=profiles,
        diagnostics=diagnostics,
    )
