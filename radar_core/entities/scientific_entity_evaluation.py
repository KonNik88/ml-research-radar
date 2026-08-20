from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Sequence

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from radar_core.contracts.scientific_entity_evaluation import (
    METRICS_SCHEMA_VERSION,
    PER_TYPE_METRICS_SCHEMA_VERSION,
    REFERENCE_MENTION_SCHEMA_VERSION,
    ScientificEntityDataSufficiency,
    ScientificEntityEvaluationError,
    ScientificEntityEvaluationErrorKind,
    ScientificEntityEvaluationMatch,
    ScientificEntityEvaluationMetrics,
    ScientificEntityManualErrorLabel,
    ScientificEntityMatchingMetrics,
    ScientificEntityMatchingPolicy,
    ScientificEntityMatchKind,
    ScientificEntityMetricCounts,
    ScientificEntityPerTypeMetricRow,
    ScientificEntityPerTypeMetrics,
    ScientificEntityReferenceMention,
    build_evaluation_error_id,
    build_evaluation_match_id,
)
from radar_core.contracts.scientific_entity_evidence import (
    ScientificEntityMentionEvidence,
    ScientificEntitySourceField,
    ScientificEntityType,
    sha256_text,
)


EVALUATION_CONFIG_SCHEMA_VERSION = "scientific_entity_evaluation_config_v0.1"
EVALUATION_OUTPUT_SCHEMA_VERSION = "scientific_entity_evaluation_output_v0.1"


class ScientificEntityEvaluationErrorBase(ValueError):
    """Raised when evaluation configuration or matching input is invalid."""


class EvaluationLayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["scientific_entity_evaluation_harness"]
    version: Literal["v0.1"]
    status: Literal["evaluation_harness"]
    layer_kind: Literal["derived_bounded_quality_evidence"]
    description: str = Field(min_length=1)


class EvaluationMatchingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    offset_unit: Literal["unicode_codepoint"]
    offset_interval: Literal["half_open"]
    exact_requires_same_entity_type: Literal[True]
    exact_requires_same_span: Literal[True]
    exact_requires_same_text_identity: Literal[True]
    relaxed_enabled: Literal[True]
    relaxed_min_char_iou: float = Field(gt=0.0, le=1.0)
    relaxed_requires_same_entity_type: Literal[True]
    relaxed_requires_same_text_identity: Literal[True]
    relaxed_assignment: Literal["deterministic_greedy_iou_desc_v0.1"]
    one_to_one: Literal[True]

    def contract_policy(self) -> ScientificEntityMatchingPolicy:
        return ScientificEntityMatchingPolicy(
            exact_requires_same_entity_type=self.exact_requires_same_entity_type,
            exact_requires_same_span=self.exact_requires_same_span,
            exact_requires_same_text_identity=self.exact_requires_same_text_identity,
            relaxed_enabled=self.relaxed_enabled,
            relaxed_min_char_iou=self.relaxed_min_char_iou,
            relaxed_requires_same_entity_type=self.relaxed_requires_same_entity_type,
            relaxed_requires_same_text_identity=self.relaxed_requires_same_text_identity,
            relaxed_assignment=self.relaxed_assignment,
            one_to_one=self.one_to_one,
        )


class EvaluationMetricsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_fields: list[ScientificEntitySourceField] = Field(min_length=2, max_length=2)
    entity_types: list[ScientificEntityType] = Field(min_length=6, max_length=6)
    undefined_metric_value: Literal["null"]
    decimal_places: Literal[6]
    minimum_document_count_for_promotion_evidence: int = Field(ge=1)
    minimum_reference_mentions_per_type: int = Field(ge=1)
    promotion_verdict_allowed: Literal[False]
    metrics_are_descriptive_only: Literal[True]

    @model_validator(mode="after")
    def validate_coverage(self) -> "EvaluationMetricsConfig":
        if self.source_fields != list(ScientificEntitySourceField):
            raise ValueError("source_fields must cover title and abstract in enum order")
        if self.entity_types != list(ScientificEntityType):
            raise ValueError("entity_types must cover all six types in enum order")
        return self


class EvaluationSafetyConfig(BaseModel):
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
    allowed_evaluation_statuses: list[Literal["fixture", "candidate"]] = Field(
        min_length=2,
        max_length=2,
    )
    accepted_or_promoted_status_allowed: Literal[False]
    execute_required_for_writes: Literal[True]
    overwrite_allowed: Literal[False]
    model_or_tokenizer_download_allowed: Literal[False]
    provider_api_allowed: Literal[False]
    canonical_truth_mutation_allowed: Literal[False]
    reconcile_input_allowed: Literal[False]
    full_corpus_build_authorized: Literal[False]
    redistribution_allowed: Literal[False]
    publication_allowed: Literal[False]

    @model_validator(mode="after")
    def validate_safety(self) -> "EvaluationSafetyConfig":
        if self.default_max_documents > self.hard_max_documents:
            raise ValueError("default_max_documents must not exceed hard_max_documents")
        if set(self.allowed_evaluation_statuses) != {"fixture", "candidate"}:
            raise ValueError("allowed evaluation statuses must be fixture and candidate")
        return self


class EvaluationOutputsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root: str = Field(min_length=1)
    immutable_evaluation_directory: Literal[True]
    mutable_latest_pointer: Literal[False]
    encoding: Literal["utf-8"]
    line_ending: Literal["lf"]
    required_files: list[str] = Field(min_length=1)


class EvaluationValidationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_dir: str = Field(min_length=1)
    require_independent_validator: Literal[True]
    require_metric_recomputation: Literal[True]
    require_one_to_one_matches: Literal[True]
    require_checksums: Literal[True]
    require_lf_outputs: Literal[True]
    require_input_hashes: Literal[True]
    require_fail_closed_safety: Literal[True]


class EvaluationFixturesConfig(BaseModel):
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
    prediction_manifest_path: Literal[
        "tests/fixtures/scientific_entity_evaluation_v0_1/"
        "prediction_build/manifest.json"
    ]
    prediction_mentions_path: Literal[
        "tests/fixtures/scientific_entity_evaluation_v0_1/"
        "prediction_build/mentions.jsonl"
    ]
    expected_metrics_path: Literal[
        "tests/fixtures/scientific_entity_evaluation_v0_1/expected_metrics.json"
    ]
    synthetic_only: Literal[True]


class ScientificEntityEvaluationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[EVALUATION_CONFIG_SCHEMA_VERSION]
    layer: EvaluationLayerConfig
    matching: EvaluationMatchingConfig
    metrics: EvaluationMetricsConfig
    safety: EvaluationSafetyConfig
    outputs: EvaluationOutputsConfig
    validation: EvaluationValidationConfig
    fixtures: EvaluationFixturesConfig
    manual_error_labels: list[ScientificEntityManualErrorLabel]

    @model_validator(mode="after")
    def validate_layout_and_labels(self) -> "ScientificEntityEvaluationConfig":
        expected_files = {
            "manifest.json",
            "metrics.json",
            "per_type_metrics.json",
            "matches.jsonl",
            "errors.jsonl",
            "README.md",
            "checksums.txt",
        }
        if set(self.outputs.required_files) != expected_files:
            raise ValueError("outputs.required_files does not match evaluation v0.1 layout")
        if len(set(self.outputs.required_files)) != len(self.outputs.required_files):
            raise ValueError("outputs.required_files must not contain duplicates")
        if self.manual_error_labels != list(ScientificEntityManualErrorLabel):
            raise ValueError("manual_error_labels must cover the accepted taxonomy in enum order")
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


def load_evaluation_config(path: Path) -> ScientificEntityEvaluationConfig:
    try:
        payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeySafeLoader)
    except yaml.YAMLError as exc:
        raise ScientificEntityEvaluationErrorBase(
            f"Invalid YAML config {path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ScientificEntityEvaluationErrorBase(f"Expected YAML object: {path}")
    return ScientificEntityEvaluationConfig.model_validate(payload)


def canonical_semantic_json(payload: object) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def evaluation_config_sha256(config: ScientificEntityEvaluationConfig) -> str:
    return sha256_text(canonical_semantic_json(config.model_dump(mode="json")))


def _reference_sort_key(record: ScientificEntityReferenceMention) -> tuple[Any, ...]:
    return (
        record.canonical_id,
        list(ScientificEntitySourceField).index(record.source_field),
        record.char_start,
        record.char_end,
        record.entity_type.value,
        record.reference_id,
    )


def _prediction_sort_key(record: ScientificEntityMentionEvidence) -> tuple[Any, ...]:
    return (
        record.canonical_id,
        list(ScientificEntitySourceField).index(record.source_field),
        record.char_start,
        record.char_end,
        record.entity_type.value,
        record.evidence_id,
    )


def _same_text(left: Any, right: Any) -> bool:
    return (
        left.canonical_id == right.canonical_id
        and left.source_field == right.source_field
        and left.source_text_sha256 == right.source_text_sha256
    )


def _intersection_and_iou(
    reference: ScientificEntityReferenceMention,
    prediction: ScientificEntityMentionEvidence,
) -> tuple[int, int, float, int]:
    intersection = max(
        0,
        min(reference.char_end, prediction.char_end)
        - max(reference.char_start, prediction.char_start),
    )
    union = max(reference.char_end, prediction.char_end) - min(
        reference.char_start,
        prediction.char_start,
    )
    iou = intersection / union if union else 0.0
    boundary_distance = abs(reference.char_start - prediction.char_start) + abs(
        reference.char_end - prediction.char_end
    )
    return intersection, union, iou, boundary_distance


def _metric_counts(
    *,
    true_positive: int,
    reference_support: int,
    prediction_support: int,
    decimal_places: int,
) -> ScientificEntityMetricCounts:
    false_positive = prediction_support - true_positive
    false_negative = reference_support - true_positive
    precision = (
        round(true_positive / prediction_support, decimal_places)
        if prediction_support
        else None
    )
    recall = (
        round(true_positive / reference_support, decimal_places)
        if reference_support
        else None
    )
    if precision is None or recall is None:
        f1 = None
    elif precision + recall == 0:
        f1 = 0.0
    else:
        f1 = round(2 * precision * recall / (precision + recall), decimal_places)
    return ScientificEntityMetricCounts(
        true_positive=true_positive,
        false_positive=false_positive,
        false_negative=false_negative,
        reference_support=reference_support,
        prediction_support=prediction_support,
        precision_denominator=prediction_support,
        recall_denominator=reference_support,
        precision=precision,
        recall=recall,
        f1=f1,
    )


def _match_record(
    *,
    evaluation_id: str,
    kind: ScientificEntityMatchKind,
    reference: ScientificEntityReferenceMention,
    prediction: ScientificEntityMentionEvidence,
) -> ScientificEntityEvaluationMatch:
    intersection, union, iou, boundary_distance = _intersection_and_iou(
        reference,
        prediction,
    )
    return ScientificEntityEvaluationMatch(
        schema_version="scientific_entity_evaluation_match_v0.1",
        match_id=build_evaluation_match_id(
            evaluation_id=evaluation_id,
            match_kind=kind,
            reference_id=reference.reference_id,
            evidence_id=prediction.evidence_id,
        ),
        evaluation_id=evaluation_id,
        match_kind=kind,
        reference_id=reference.reference_id,
        reference_mention_id=reference.mention_id,
        prediction_evidence_id=prediction.evidence_id,
        prediction_mention_id=prediction.mention_id,
        canonical_id=reference.canonical_id,
        source_field=reference.source_field,
        source_text_sha256=reference.source_text_sha256,
        entity_type=reference.entity_type,
        reference_char_start=reference.char_start,
        reference_char_end=reference.char_end,
        prediction_char_start=prediction.char_start,
        prediction_char_end=prediction.char_end,
        intersection_length=intersection,
        union_length=union,
        char_iou=round(iou, 12),
        boundary_distance=boundary_distance,
    )


def _error_record(
    *,
    evaluation_id: str,
    kind: ScientificEntityEvaluationErrorKind,
    reference: ScientificEntityReferenceMention | None,
    prediction: ScientificEntityMentionEvidence | None,
) -> ScientificEntityEvaluationError:
    anchor = reference or prediction
    if anchor is None:
        raise ScientificEntityEvaluationErrorBase("evaluation error requires an anchor")
    iou: float | None = None
    if reference is not None and prediction is not None:
        _, _, raw_iou, _ = _intersection_and_iou(reference, prediction)
        iou = round(raw_iou, 12)
    return ScientificEntityEvaluationError(
        schema_version="scientific_entity_evaluation_error_v0.1",
        error_id=build_evaluation_error_id(
            evaluation_id=evaluation_id,
            error_kind=kind,
            reference_id=reference.reference_id if reference else None,
            evidence_id=prediction.evidence_id if prediction else None,
        ),
        evaluation_id=evaluation_id,
        error_kind=kind,
        canonical_id=anchor.canonical_id,
        source_field=anchor.source_field,
        source_text_sha256=anchor.source_text_sha256,
        reference_id=reference.reference_id if reference else None,
        prediction_evidence_id=prediction.evidence_id if prediction else None,
        reference_entity_type=reference.entity_type if reference else None,
        prediction_entity_type=prediction.entity_type if prediction else None,
        reference_char_start=reference.char_start if reference else None,
        reference_char_end=reference.char_end if reference else None,
        prediction_char_start=prediction.char_start if prediction else None,
        prediction_char_end=prediction.char_end if prediction else None,
        char_iou=iou,
        manual_label=None,
    )


def _greedy_pairs(
    candidates: Sequence[
        tuple[
            tuple[Any, ...],
            ScientificEntityReferenceMention,
            ScientificEntityMentionEvidence,
        ]
    ],
) -> list[tuple[ScientificEntityReferenceMention, ScientificEntityMentionEvidence]]:
    used_reference: set[str] = set()
    used_prediction: set[str] = set()
    selected: list[
        tuple[ScientificEntityReferenceMention, ScientificEntityMentionEvidence]
    ] = []
    for _, reference, prediction in sorted(candidates, key=lambda item: item[0]):
        if reference.reference_id in used_reference:
            continue
        if prediction.evidence_id in used_prediction:
            continue
        used_reference.add(reference.reference_id)
        used_prediction.add(prediction.evidence_id)
        selected.append((reference, prediction))
    return selected


@dataclass(frozen=True, slots=True)
class ScientificEntityEvaluationResult:
    matches: tuple[ScientificEntityEvaluationMatch, ...]
    errors: tuple[ScientificEntityEvaluationError, ...]
    metrics: ScientificEntityEvaluationMetrics
    per_type_metrics: ScientificEntityPerTypeMetrics


def evaluate_mentions(
    *,
    evaluation_id: str,
    document_count: int,
    references: Sequence[ScientificEntityReferenceMention],
    predictions: Sequence[ScientificEntityMentionEvidence],
    config: ScientificEntityEvaluationConfig,
) -> ScientificEntityEvaluationResult:
    if document_count < 1:
        raise ScientificEntityEvaluationErrorBase("document_count must be positive")
    if len(references) > config.safety.hard_max_reference_mentions:
        raise ScientificEntityEvaluationErrorBase("reference mention hard limit exceeded")
    if len(predictions) > config.safety.hard_max_prediction_mentions:
        raise ScientificEntityEvaluationErrorBase("prediction mention hard limit exceeded")

    sorted_references = sorted(references, key=_reference_sort_key)
    sorted_predictions = sorted(predictions, key=_prediction_sort_key)
    if len({row.reference_id for row in sorted_references}) != len(sorted_references):
        raise ScientificEntityEvaluationErrorBase("duplicate reference_id")
    if len({row.mention_id for row in sorted_references}) != len(sorted_references):
        raise ScientificEntityEvaluationErrorBase("duplicate reference mention_id")
    if len({row.evidence_id for row in sorted_predictions}) != len(sorted_predictions):
        raise ScientificEntityEvaluationErrorBase("duplicate prediction evidence_id")
    if len({row.mention_id for row in sorted_predictions}) != len(sorted_predictions):
        raise ScientificEntityEvaluationErrorBase("duplicate prediction mention_id")

    exact_candidates: list[
        tuple[
            tuple[Any, ...],
            ScientificEntityReferenceMention,
            ScientificEntityMentionEvidence,
        ]
    ] = []
    for reference in sorted_references:
        for prediction in sorted_predictions:
            if not _same_text(reference, prediction):
                continue
            if reference.entity_type != prediction.entity_type:
                continue
            if (
                reference.char_start == prediction.char_start
                and reference.char_end == prediction.char_end
            ):
                exact_candidates.append(
                    ((reference.reference_id, prediction.evidence_id), reference, prediction)
                )
    exact_pairs = _greedy_pairs(exact_candidates)
    used_reference = {reference.reference_id for reference, _ in exact_pairs}
    used_prediction = {prediction.evidence_id for _, prediction in exact_pairs}

    relaxed_candidates: list[
        tuple[
            tuple[Any, ...],
            ScientificEntityReferenceMention,
            ScientificEntityMentionEvidence,
        ]
    ] = []
    for reference in sorted_references:
        if reference.reference_id in used_reference:
            continue
        for prediction in sorted_predictions:
            if prediction.evidence_id in used_prediction:
                continue
            if not _same_text(reference, prediction):
                continue
            if reference.entity_type != prediction.entity_type:
                continue
            intersection, _, iou, boundary_distance = _intersection_and_iou(
                reference,
                prediction,
            )
            if intersection <= 0 or iou < config.matching.relaxed_min_char_iou:
                continue
            relaxed_candidates.append(
                (
                    (
                        -iou,
                        boundary_distance,
                        reference.reference_id,
                        prediction.evidence_id,
                    ),
                    reference,
                    prediction,
                )
            )
    relaxed_pairs = _greedy_pairs(relaxed_candidates)
    used_reference.update(reference.reference_id for reference, _ in relaxed_pairs)
    used_prediction.update(prediction.evidence_id for _, prediction in relaxed_pairs)

    matches = [
        _match_record(
            evaluation_id=evaluation_id,
            kind=ScientificEntityMatchKind.EXACT,
            reference=reference,
            prediction=prediction,
        )
        for reference, prediction in exact_pairs
    ]
    matches.extend(
        _match_record(
            evaluation_id=evaluation_id,
            kind=ScientificEntityMatchKind.RELAXED,
            reference=reference,
            prediction=prediction,
        )
        for reference, prediction in relaxed_pairs
    )

    errors = [
        _error_record(
            evaluation_id=evaluation_id,
            kind=ScientificEntityEvaluationErrorKind.BOUNDARY_MISMATCH,
            reference=reference,
            prediction=prediction,
        )
        for reference, prediction in relaxed_pairs
    ]

    remaining_references = [
        row for row in sorted_references if row.reference_id not in used_reference
    ]
    remaining_predictions = [
        row for row in sorted_predictions if row.evidence_id not in used_prediction
    ]

    type_candidates: list[
        tuple[
            tuple[Any, ...],
            ScientificEntityReferenceMention,
            ScientificEntityMentionEvidence,
        ]
    ] = []
    for reference in remaining_references:
        for prediction in remaining_predictions:
            if not _same_text(reference, prediction):
                continue
            if reference.entity_type == prediction.entity_type:
                continue
            intersection, _, iou, boundary_distance = _intersection_and_iou(
                reference,
                prediction,
            )
            if intersection <= 0:
                continue
            exact_span_rank = int(
                not (
                    reference.char_start == prediction.char_start
                    and reference.char_end == prediction.char_end
                )
            )
            type_candidates.append(
                (
                    (
                        exact_span_rank,
                        -iou,
                        boundary_distance,
                        reference.reference_id,
                        prediction.evidence_id,
                    ),
                    reference,
                    prediction,
                )
            )
    type_pairs = _greedy_pairs(type_candidates)
    used_reference.update(reference.reference_id for reference, _ in type_pairs)
    used_prediction.update(prediction.evidence_id for _, prediction in type_pairs)
    errors.extend(
        _error_record(
            evaluation_id=evaluation_id,
            kind=ScientificEntityEvaluationErrorKind.TYPE_MISMATCH,
            reference=reference,
            prediction=prediction,
        )
        for reference, prediction in type_pairs
    )

    remaining_references = [
        row for row in sorted_references if row.reference_id not in used_reference
    ]
    remaining_predictions = [
        row for row in sorted_predictions if row.evidence_id not in used_prediction
    ]
    boundary_candidates: list[
        tuple[
            tuple[Any, ...],
            ScientificEntityReferenceMention,
            ScientificEntityMentionEvidence,
        ]
    ] = []
    for reference in remaining_references:
        for prediction in remaining_predictions:
            if not _same_text(reference, prediction):
                continue
            if reference.entity_type != prediction.entity_type:
                continue
            intersection, _, iou, boundary_distance = _intersection_and_iou(
                reference,
                prediction,
            )
            if intersection <= 0:
                continue
            boundary_candidates.append(
                (
                    (
                        -iou,
                        boundary_distance,
                        reference.reference_id,
                        prediction.evidence_id,
                    ),
                    reference,
                    prediction,
                )
            )
    boundary_pairs = _greedy_pairs(boundary_candidates)
    used_reference.update(reference.reference_id for reference, _ in boundary_pairs)
    used_prediction.update(prediction.evidence_id for _, prediction in boundary_pairs)
    errors.extend(
        _error_record(
            evaluation_id=evaluation_id,
            kind=ScientificEntityEvaluationErrorKind.BOUNDARY_MISMATCH,
            reference=reference,
            prediction=prediction,
        )
        for reference, prediction in boundary_pairs
    )

    errors.extend(
        _error_record(
            evaluation_id=evaluation_id,
            kind=ScientificEntityEvaluationErrorKind.FALSE_POSITIVE,
            reference=None,
            prediction=prediction,
        )
        for prediction in sorted_predictions
        if prediction.evidence_id not in used_prediction
    )
    errors.extend(
        _error_record(
            evaluation_id=evaluation_id,
            kind=ScientificEntityEvaluationErrorKind.FALSE_NEGATIVE,
            reference=reference,
            prediction=None,
        )
        for reference in sorted_references
        if reference.reference_id not in used_reference
    )

    matches.sort(key=lambda row: (row.match_kind.value, row.match_id))
    errors.sort(key=lambda row: (row.error_kind.value, row.error_id))

    exact_reference_ids = {
        row.reference_id for row in matches if row.match_kind == ScientificEntityMatchKind.EXACT
    }
    relaxed_reference_ids = {row.reference_id for row in matches}

    def metrics_for(
        *,
        entity_type: ScientificEntityType | None = None,
        source_field: ScientificEntitySourceField | None = None,
    ) -> ScientificEntityMatchingMetrics:
        selected_references = [
            row
            for row in sorted_references
            if (entity_type is None or row.entity_type == entity_type)
            and (source_field is None or row.source_field == source_field)
        ]
        selected_predictions = [
            row
            for row in sorted_predictions
            if (entity_type is None or row.entity_type == entity_type)
            and (source_field is None or row.source_field == source_field)
        ]
        selected_reference_ids = {row.reference_id for row in selected_references}
        exact_tp = len(selected_reference_ids & exact_reference_ids)
        relaxed_tp = len(selected_reference_ids & relaxed_reference_ids)
        return ScientificEntityMatchingMetrics(
            exact=_metric_counts(
                true_positive=exact_tp,
                reference_support=len(selected_references),
                prediction_support=len(selected_predictions),
                decimal_places=config.metrics.decimal_places,
            ),
            relaxed=_metric_counts(
                true_positive=relaxed_tp,
                reference_support=len(selected_references),
                prediction_support=len(selected_predictions),
                decimal_places=config.metrics.decimal_places,
            ),
        )

    per_type_rows = [
        ScientificEntityPerTypeMetricRow(
            entity_type=entity_type,
            metrics=metrics_for(entity_type=entity_type),
            support_sufficient=(
                sum(row.entity_type == entity_type for row in sorted_references)
                >= config.metrics.minimum_reference_mentions_per_type
            ),
        )
        for entity_type in ScientificEntityType
    ]
    per_type = ScientificEntityPerTypeMetrics(
        schema_version=PER_TYPE_METRICS_SCHEMA_VERSION,
        evaluation_id=evaluation_id,
        minimum_reference_mentions_per_type=(
            config.metrics.minimum_reference_mentions_per_type
        ),
        rows=per_type_rows,
    )
    error_counts = Counter(row.error_kind for row in errors)
    data_sufficiency = ScientificEntityDataSufficiency(
        minimum_document_count=(
            config.metrics.minimum_document_count_for_promotion_evidence
        ),
        minimum_reference_mentions_per_type=(
            config.metrics.minimum_reference_mentions_per_type
        ),
        document_count_sufficient=(
            document_count
            >= config.metrics.minimum_document_count_for_promotion_evidence
        ),
        per_type_support_sufficient={
            row.entity_type: row.support_sufficient for row in per_type_rows
        },
        promotion_sample_sufficient=False,
        metrics_are_descriptive_only=True,
    )
    metrics = ScientificEntityEvaluationMetrics(
        schema_version=METRICS_SCHEMA_VERSION,
        evaluation_id=evaluation_id,
        document_count=document_count,
        reference_mention_count=len(sorted_references),
        prediction_mention_count=len(sorted_predictions),
        matching_policy=config.matching.contract_policy(),
        micro=metrics_for(),
        by_source_field={
            source_field: metrics_for(source_field=source_field)
            for source_field in ScientificEntitySourceField
        },
        exact_match_count=len(exact_pairs),
        relaxed_only_match_count=len(relaxed_pairs),
        error_count_by_kind={
            kind: error_counts[kind] for kind in ScientificEntityEvaluationErrorKind
        },
        data_sufficiency=data_sufficiency,
        production_extractor_selected=False,
        full_corpus_build_authorized=False,
        canonical_truth_mutated=False,
        publication_ready=False,
    )
    return ScientificEntityEvaluationResult(
        matches=tuple(matches),
        errors=tuple(errors),
        metrics=metrics,
        per_type_metrics=per_type,
    )
