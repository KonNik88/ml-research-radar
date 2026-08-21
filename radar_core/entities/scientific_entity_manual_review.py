from __future__ import annotations

import hashlib
import heapq
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from radar_core.contracts.canonical_document import CanonicalDocument
from radar_core.contracts.scientific_entity_evaluation import (
    REFERENCE_MENTION_SCHEMA_VERSION,
    ScientificEntityAnnotationMethod,
    ScientificEntityReferenceMention,
    build_reference_id,
)
from radar_core.contracts.scientific_entity_evidence import (
    ScientificEntitySourceField,
    ScientificEntityType,
    build_mention_id,
    sha256_text,
)
from radar_core.contracts.scientific_entity_manual_review import (
    BLIND_ANNOTATION_SCHEMA_VERSION,
    SAMPLE_ASSIGNMENT_SCHEMA_VERSION,
    SAMPLING_ALGORITHM,
    ScientificEntityBlindAnnotationRow,
    ScientificEntitySampleAssignment,
    ScientificEntitySampleStratum,
    ScientificEntitySamplingPolicy,
    build_selection_score,
)


MANUAL_REVIEW_CONFIG_SCHEMA_VERSION = (
    "scientific_entity_manual_review_evidence_config_v0.1"
)
MANUAL_REVIEW_CODE_REVISION_PREFIX = "sha256:"


class ScientificEntityManualReviewError(ValueError):
    """Raised when manual-review configuration or evidence is invalid."""


class ManualReviewLayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["bounded_scientific_entity_manual_review_evidence"]
    version: Literal["v0.1"]
    status: Literal["review_evidence_preparation"]
    layer_kind: Literal["derived_local_prediction_blind_review_evidence"]
    description: str = Field(min_length=1)


class ManualReviewSamplingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    algorithm: Literal[SAMPLING_ALGORITHM]
    seed: str = Field(min_length=1)
    uniform_document_count: int = Field(ge=1)
    type_enriched_documents_per_type: int = Field(ge=1)
    total_document_count: int = Field(ge=1)
    candidate_pool_per_stratum: int = Field(ge=1)
    require_nonempty_title: Literal[True]
    require_nonempty_abstract: Literal[True]
    selection_term_matching: Literal["unicode_word_case_insensitive"]
    type_enrichment_terms: dict[ScientificEntityType, list[str]]

    @model_validator(mode="after")
    def validate_sampling(self) -> "ManualReviewSamplingConfig":
        if not self.seed.strip():
            raise ValueError("sampling seed must contain non-whitespace text")
        expected_total = self.uniform_document_count + (
            self.type_enriched_documents_per_type * len(ScientificEntityType)
        )
        if self.total_document_count != expected_total:
            raise ValueError("sampling total does not match uniform + per-type targets")
        if self.candidate_pool_per_stratum < self.total_document_count:
            raise ValueError("candidate_pool_per_stratum is too small")
        if set(self.type_enrichment_terms) != set(ScientificEntityType):
            raise ValueError("type_enrichment_terms must cover all six entity types")
        for entity_type, terms in self.type_enrichment_terms.items():
            normalized_terms = [term.casefold() for term in terms]
            if not terms or len(set(normalized_terms)) != len(normalized_terms):
                raise ValueError(
                    f"selection terms must be non-empty and unique for {entity_type.value}"
                )
            if any(not term.strip() for term in terms):
                raise ValueError("selection terms must contain non-whitespace text")
        return self

    def policy(
        self,
        *,
        uniform_document_count: int | None = None,
        type_enriched_documents_per_type: int | None = None,
    ) -> ScientificEntitySamplingPolicy:
        uniform_count = (
            self.uniform_document_count
            if uniform_document_count is None
            else uniform_document_count
        )
        per_type_count = (
            self.type_enriched_documents_per_type
            if type_enriched_documents_per_type is None
            else type_enriched_documents_per_type
        )
        return ScientificEntitySamplingPolicy(
            algorithm=self.algorithm,
            seed=self.seed,
            uniform_document_count=uniform_count,
            type_enriched_documents_per_type=per_type_count,
            total_document_count=uniform_count + per_type_count * len(ScientificEntityType),
            candidate_pool_per_stratum=self.candidate_pool_per_stratum,
            require_nonempty_title=True,
            require_nonempty_abstract=True,
            selection_term_matching=self.selection_term_matching,
        )


class ManualReviewAnnotationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    guideline_version: str = Field(min_length=1)
    default_method: Literal[ScientificEntityAnnotationMethod.MANUAL_INDEPENDENT]
    prediction_blind: Literal[True]
    source_fields: list[ScientificEntitySourceField] = Field(min_length=2, max_length=2)
    entity_types: list[ScientificEntityType] = Field(min_length=6, max_length=6)
    offset_unit: Literal["unicode_codepoint"]
    offset_interval: Literal["half_open"]
    annotation_passes: Literal[1]
    require_every_source_field_completed: Literal[True]
    require_surface_from_exact_source_slice: Literal[True]
    duplicate_typed_spans_allowed: Literal[False]

    @model_validator(mode="after")
    def validate_annotation(self) -> "ManualReviewAnnotationConfig":
        if self.source_fields != list(ScientificEntitySourceField):
            raise ValueError("source_fields must cover title and abstract in enum order")
        if self.entity_types != list(ScientificEntityType):
            raise ValueError("entity_types must cover all six types in enum order")
        return self


class ManualReviewSafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_max_source_documents: int = Field(ge=1)
    hard_max_source_documents: int = Field(ge=1)
    hard_max_selected_documents: Literal[32]
    hard_max_annotation_rows: Literal[64]
    hard_max_reference_mentions: Literal[5000]
    fail_if_input_exceeds_limit: Literal[True]
    truncation_allowed: Literal[False]
    current_canonical_path: Literal[
        "data/analytics/reconciled/canonical_documents.jsonl"
    ]
    candidate_input_must_be_current_canonical: Literal[True]
    fixture_input_must_be_tracked_fixture: Literal[True]
    execute_required_for_writes: Literal[True]
    overwrite_allowed: Literal[False]
    full_corpus_entity_extraction_allowed: Literal[False]
    predictions_visible_during_annotation: Literal[False]
    automatic_annotation_allowed: Literal[False]
    automatic_review_approval_allowed: Literal[False]
    production_extractor_selection_allowed: Literal[False]
    model_or_tokenizer_download_allowed: Literal[False]
    provider_api_allowed: Literal[False]
    canonical_truth_mutation_allowed: Literal[False]
    reconcile_input_allowed: Literal[False]
    redistribution_allowed: Literal[False]
    publication_allowed: Literal[False]

    @model_validator(mode="after")
    def validate_limits(self) -> "ManualReviewSafetyConfig":
        if self.default_max_source_documents > self.hard_max_source_documents:
            raise ValueError("default source limit exceeds hard source limit")
        return self


class ManualReviewOutputsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prepared_root: str = Field(min_length=1)
    completed_root: str = Field(min_length=1)
    immutable_directories: Literal[True]
    mutable_latest_pointer: Literal[False]
    encoding: Literal["utf-8"]
    line_ending: Literal["lf"]
    prepared_required_files: list[str] = Field(min_length=1)
    completed_required_files: list[str] = Field(min_length=1)


class ManualReviewValidationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_dir: str = Field(min_length=1)
    require_independent_validator: Literal[True]
    require_sampling_recomputation: Literal[True]
    require_prediction_blind_schema: Literal[True]
    require_complete_annotation_rows: Literal[True]
    require_reference_identity_recomputation: Literal[True]
    require_checksums: Literal[True]
    require_lf_outputs: Literal[True]
    require_input_hashes: Literal[True]
    require_fail_closed_safety: Literal[True]


class ManualReviewFixturesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_path: Literal[
        "tests/fixtures/scientific_entity_manual_review_evidence_v0_1/"
        "canonical_documents.jsonl"
    ]
    completed_annotations_path: Literal[
        "tests/fixtures/scientific_entity_manual_review_evidence_v0_1/"
        "completed_annotations.jsonl"
    ]
    review_id: Literal["scientific-entity-manual-review-fixture-v0.1"]
    uniform_document_count: Literal[2]
    type_enriched_documents_per_type: Literal[1]
    expected_document_count: Literal[8]
    expected_annotation_row_count: Literal[16]
    expected_reference_mention_count: Literal[6]
    synthetic_only: Literal[True]


class ScientificEntityManualReviewConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[MANUAL_REVIEW_CONFIG_SCHEMA_VERSION]
    layer: ManualReviewLayerConfig
    sampling: ManualReviewSamplingConfig
    annotation: ManualReviewAnnotationConfig
    safety: ManualReviewSafetyConfig
    outputs: ManualReviewOutputsConfig
    validation: ManualReviewValidationConfig
    fixtures: ManualReviewFixturesConfig

    @model_validator(mode="after")
    def validate_config(self) -> "ScientificEntityManualReviewConfig":
        prepared = {
            "canonical_documents.sample.jsonl",
            "sample_assignments.jsonl",
            "annotation_template.jsonl",
            "manifest.json",
            "data_quality_summary.json",
            "README.md",
            "checksums.txt",
        }
        completed = {
            "completed_annotations.jsonl",
            "review_manifest.json",
            "reference_mentions.jsonl",
            "completion_manifest.json",
            "annotation_audit_summary.json",
            "README.md",
            "checksums.txt",
        }
        if set(self.outputs.prepared_required_files) != prepared:
            raise ValueError("prepared_required_files does not match v0.1 layout")
        if set(self.outputs.completed_required_files) != completed:
            raise ValueError("completed_required_files does not match v0.1 layout")
        if len(set(self.outputs.prepared_required_files)) != len(
            self.outputs.prepared_required_files
        ):
            raise ValueError("prepared_required_files must not contain duplicates")
        if len(set(self.outputs.completed_required_files)) != len(
            self.outputs.completed_required_files
        ):
            raise ValueError("completed_required_files must not contain duplicates")
        if self.sampling.total_document_count > self.safety.hard_max_selected_documents:
            raise ValueError("configured sample exceeds hard selected-document limit")
        fixture_count = self.fixtures.uniform_document_count + (
            self.fixtures.type_enriched_documents_per_type
            * len(ScientificEntityType)
        )
        if fixture_count != self.fixtures.expected_document_count:
            raise ValueError("fixture sample targets do not match expected count")
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


def load_manual_review_config(path: Path) -> ScientificEntityManualReviewConfig:
    try:
        payload = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeySafeLoader)
    except yaml.YAMLError as exc:
        raise ScientificEntityManualReviewError(
            f"Invalid manual-review YAML: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ScientificEntityManualReviewError("Manual-review config must be a mapping")
    return ScientificEntityManualReviewConfig.model_validate(payload)


def manual_review_config_sha256(config: ScientificEntityManualReviewConfig) -> str:
    payload = json.dumps(
        config.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalized_file_sha256(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ScientificEntitySampleCandidate:
    document: CanonicalDocument
    payload: Mapping[str, Any]


def _term_pattern(term: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", flags=re.IGNORECASE)


def document_matches_enrichment_type(
    document: CanonicalDocument,
    *,
    entity_type: ScientificEntityType,
    config: ScientificEntityManualReviewConfig,
) -> bool:
    text = f"{document.title}\n{document.abstract or ''}"
    return any(
        _term_pattern(term).search(text) is not None
        for term in config.sampling.type_enrichment_terms[entity_type]
    )


class DeterministicScientificEntitySampler:
    def __init__(
        self,
        *,
        config: ScientificEntityManualReviewConfig,
        policy: ScientificEntitySamplingPolicy,
    ) -> None:
        self.config = config
        self.policy = policy
        self.eligible_document_count = 0
        self._uniform_heap: list[tuple[int, str, str, ScientificEntitySampleCandidate]] = []
        self._type_heaps: dict[
            ScientificEntityType,
            list[tuple[int, str, str, ScientificEntitySampleCandidate]],
        ] = {entity_type: [] for entity_type in ScientificEntityType}

    def _push(
        self,
        heap: list[tuple[int, str, str, ScientificEntitySampleCandidate]],
        *,
        score: str,
        candidate: ScientificEntitySampleCandidate,
    ) -> None:
        entry = (-int(score, 16), candidate.document.canonical_id, score, candidate)
        heapq.heappush(heap, entry)
        if len(heap) > self.policy.candidate_pool_per_stratum:
            heapq.heappop(heap)

    def consider(
        self,
        *,
        document: CanonicalDocument,
        payload: Mapping[str, Any],
    ) -> None:
        if not document.title.strip() or not (document.abstract or "").strip():
            return
        self.eligible_document_count += 1
        candidate = ScientificEntitySampleCandidate(document=document, payload=payload)
        uniform_score = build_selection_score(
            seed=self.policy.seed,
            stratum=ScientificEntitySampleStratum.UNIFORM,
            canonical_id=document.canonical_id,
        )
        self._push(self._uniform_heap, score=uniform_score, candidate=candidate)

        for entity_type in ScientificEntityType:
            if not document_matches_enrichment_type(
                document,
                entity_type=entity_type,
                config=self.config,
            ):
                continue
            score = build_selection_score(
                seed=self.policy.seed,
                stratum=ScientificEntitySampleStratum.TYPE_ENRICHED,
                enrichment_entity_type=entity_type,
                canonical_id=document.canonical_id,
            )
            self._push(self._type_heaps[entity_type], score=score, candidate=candidate)

    @staticmethod
    def _ordered(
        heap: Sequence[tuple[int, str, str, ScientificEntitySampleCandidate]],
    ) -> list[tuple[str, ScientificEntitySampleCandidate]]:
        rows = [(entry[2], entry[3]) for entry in heap]
        return sorted(rows, key=lambda row: (row[0], row[1].document.canonical_id))

    def finalize(
        self,
        *,
        review_id: str,
    ) -> tuple[list[ScientificEntitySampleCandidate], list[ScientificEntitySampleAssignment]]:
        selected: dict[str, ScientificEntitySampleCandidate] = {}
        assignments: list[ScientificEntitySampleAssignment] = []

        for entity_type in ScientificEntityType:
            selected_for_type = 0
            for score, candidate in self._ordered(self._type_heaps[entity_type]):
                canonical_id = candidate.document.canonical_id
                if canonical_id in selected:
                    continue
                selected_for_type += 1
                selected[canonical_id] = candidate
                assignments.append(
                    ScientificEntitySampleAssignment(
                        schema_version=SAMPLE_ASSIGNMENT_SCHEMA_VERSION,
                        review_id=review_id,
                        canonical_id=canonical_id,
                        sample_stratum=ScientificEntitySampleStratum.TYPE_ENRICHED,
                        enrichment_entity_type=entity_type,
                        selection_score=score,
                        stratum_rank=selected_for_type,
                    )
                )
                if selected_for_type == self.policy.type_enriched_documents_per_type:
                    break
            if selected_for_type != self.policy.type_enriched_documents_per_type:
                raise ScientificEntityManualReviewError(
                    "Insufficient distinct type-enriched candidates for "
                    f"{entity_type.value}: required "
                    f"{self.policy.type_enriched_documents_per_type}, selected "
                    f"{selected_for_type}"
                )

        uniform_rank = 0
        for score, candidate in self._ordered(self._uniform_heap):
            canonical_id = candidate.document.canonical_id
            if canonical_id in selected:
                continue
            uniform_rank += 1
            selected[canonical_id] = candidate
            assignments.append(
                ScientificEntitySampleAssignment(
                    schema_version=SAMPLE_ASSIGNMENT_SCHEMA_VERSION,
                    review_id=review_id,
                    canonical_id=canonical_id,
                    sample_stratum=ScientificEntitySampleStratum.UNIFORM,
                    enrichment_entity_type=None,
                    selection_score=score,
                    stratum_rank=uniform_rank,
                )
            )
            if uniform_rank == self.policy.uniform_document_count:
                break
        if uniform_rank != self.policy.uniform_document_count:
            raise ScientificEntityManualReviewError(
                "Insufficient distinct uniform candidates after stratum deduplication: "
                f"required {self.policy.uniform_document_count}, selected {uniform_rank}"
            )

        if len(selected) != self.policy.total_document_count:
            raise ScientificEntityManualReviewError(
                "Selected document count does not match sampling policy"
            )
        candidates = sorted(
            selected.values(), key=lambda value: value.document.canonical_id
        )
        assignments = sorted(
            assignments,
            key=lambda value: (
                0
                if value.sample_stratum == ScientificEntitySampleStratum.UNIFORM
                else 1,
                value.enrichment_entity_type.value
                if value.enrichment_entity_type is not None
                else "",
                value.stratum_rank,
                value.canonical_id,
            ),
        )
        return candidates, assignments


def build_annotation_template(
    *,
    review_id: str,
    candidates: Sequence[ScientificEntitySampleCandidate],
    assignments: Sequence[ScientificEntitySampleAssignment],
) -> list[ScientificEntityBlindAnnotationRow]:
    assignment_by_id = {row.canonical_id: row for row in assignments}
    rows: list[ScientificEntityBlindAnnotationRow] = []
    for candidate in candidates:
        document = candidate.document
        assignment = assignment_by_id[document.canonical_id]
        values = {
            ScientificEntitySourceField.TITLE: document.title,
            ScientificEntitySourceField.ABSTRACT: document.abstract,
        }
        for source_field in ScientificEntitySourceField:
            source_text = values[source_field]
            if source_text is None or source_text == "":
                raise ScientificEntityManualReviewError(
                    "Selected review documents must contain title and abstract"
                )
            rows.append(
                ScientificEntityBlindAnnotationRow(
                    schema_version=BLIND_ANNOTATION_SCHEMA_VERSION,
                    review_id=review_id,
                    canonical_id=document.canonical_id,
                    sample_stratum=assignment.sample_stratum,
                    enrichment_entity_type=assignment.enrichment_entity_type,
                    source_field=source_field,
                    source_text_sha256=sha256_text(source_text),
                    source_text=source_text,
                    annotation_complete=False,
                    mentions=[],
                    reviewer_note=None,
                )
            )
    return sorted(
        rows,
        key=lambda row: (
            row.canonical_id,
            list(ScientificEntitySourceField).index(row.source_field),
        ),
    )


def validate_completed_annotations(
    *,
    template_rows: Sequence[ScientificEntityBlindAnnotationRow],
    completed_rows: Sequence[ScientificEntityBlindAnnotationRow],
) -> None:
    def keyed(
        rows: Sequence[ScientificEntityBlindAnnotationRow],
    ) -> dict[tuple[str, ScientificEntitySourceField], ScientificEntityBlindAnnotationRow]:
        result: dict[
            tuple[str, ScientificEntitySourceField], ScientificEntityBlindAnnotationRow
        ] = {}
        for row in rows:
            key = (row.canonical_id, row.source_field)
            if key in result:
                raise ScientificEntityManualReviewError(
                    f"Duplicate annotation row: {row.canonical_id}:{row.source_field.value}"
                )
            result[key] = row
        return result

    template = keyed(template_rows)
    completed = keyed(completed_rows)
    if set(template) != set(completed):
        missing = sorted(f"{key[0]}:{key[1].value}" for key in set(template) - set(completed))
        extra = sorted(f"{key[0]}:{key[1].value}" for key in set(completed) - set(template))
        raise ScientificEntityManualReviewError(
            f"Completed annotation row set mismatch; missing={missing}, extra={extra}"
        )
    for key, expected in template.items():
        actual = completed[key]
        immutable_fields = (
            "review_id",
            "canonical_id",
            "sample_stratum",
            "enrichment_entity_type",
            "source_field",
            "source_text_sha256",
            "source_text",
        )
        for field_name in immutable_fields:
            if getattr(actual, field_name) != getattr(expected, field_name):
                raise ScientificEntityManualReviewError(
                    f"Annotation changed immutable field {field_name}: "
                    f"{actual.canonical_id}:{actual.source_field.value}"
                )
        if not actual.annotation_complete:
            raise ScientificEntityManualReviewError(
                "Every title/abstract annotation row must be explicitly complete"
            )


def build_reference_mentions(
    *,
    review_id: str,
    completed_rows: Sequence[ScientificEntityBlindAnnotationRow],
    annotation_method: ScientificEntityAnnotationMethod,
    annotation_pass: int,
) -> list[ScientificEntityReferenceMention]:
    references: list[ScientificEntityReferenceMention] = []
    for row in completed_rows:
        for mention in row.mentions:
            mention_id = build_mention_id(
                canonical_id=row.canonical_id,
                source_field=row.source_field,
                source_text_sha256=row.source_text_sha256,
                char_start=mention.char_start,
                char_end=mention.char_end,
                entity_type=mention.entity_type,
            )
            references.append(
                ScientificEntityReferenceMention(
                    schema_version=REFERENCE_MENTION_SCHEMA_VERSION,
                    reference_id=build_reference_id(
                        review_id=review_id,
                        mention_id=mention_id,
                        annotation_method=annotation_method,
                        annotation_pass=annotation_pass,
                    ),
                    mention_id=mention_id,
                    review_id=review_id,
                    canonical_id=row.canonical_id,
                    entity_type=mention.entity_type,
                    source_field=row.source_field,
                    source_text_sha256=row.source_text_sha256,
                    char_start=mention.char_start,
                    char_end=mention.char_end,
                    surface_text=mention.surface_text,
                    annotation_method=annotation_method,
                    annotation_pass=annotation_pass,
                    uncertain=mention.uncertain,
                )
            )
    return sorted(
        references,
        key=lambda row: (
            row.canonical_id,
            list(ScientificEntitySourceField).index(row.source_field),
            row.char_start,
            row.char_end,
            list(ScientificEntityType).index(row.entity_type),
            row.reference_id,
        ),
    )


def annotation_counts(
    *,
    completed_rows: Sequence[ScientificEntityBlindAnnotationRow],
) -> tuple[
    dict[ScientificEntityType, int],
    dict[ScientificEntitySampleStratum, int],
    int,
]:
    by_type: Counter[ScientificEntityType] = Counter()
    by_stratum: Counter[ScientificEntitySampleStratum] = Counter()
    uncertain = 0
    for row in completed_rows:
        for mention in row.mentions:
            by_type[mention.entity_type] += 1
            by_stratum[row.sample_stratum] += 1
            uncertain += int(mention.uncertain)
    return (
        {entity_type: by_type[entity_type] for entity_type in ScientificEntityType},
        {stratum: by_stratum[stratum] for stratum in ScientificEntitySampleStratum},
        uncertain,
    )
