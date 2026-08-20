from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, Sequence

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from radar_core.contracts.scientific_entity_evidence import (
    EXTRACTOR_SCHEMA_VERSION,
    ExtractorKind,
    ScientificEntityExtractorDescriptor,
    ScientificEntitySourceField,
    ScientificEntityType,
    sha256_text,
)


BASELINE_CONFIG_SCHEMA_VERSION = "scientific_entity_literal_baseline_config_v0.1"
DATA_QUALITY_SCHEMA_VERSION = "scientific_entity_evidence_quality_v0.1"
OUTPUT_SCHEMA_VERSION = "scientific_entity_evidence_output_schema_v0.1"
CODE_REVISION_PREFIX = "normalized-source-sha256:"


class ScientificEntityBaselineError(ValueError):
    """Raised when the bounded baseline configuration or output is unsafe."""


class LiteralRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: ScientificEntityType
    term: str = Field(min_length=1)
    case_sensitive: bool | None = None
    boundary: Literal["unicode_word", "none"] | None = None

    @model_validator(mode="after")
    def validate_term(self) -> "LiteralRule":
        if not self.term.strip():
            raise ValueError("rule term must contain non-whitespace text")
        if self.term != self.term.strip():
            raise ValueError("rule term must not contain leading or trailing whitespace")
        return self


class BaselineLayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Literal["bounded_scientific_entity_extractor_baseline"]
    version: Literal["v0.1"]
    status: Literal["reference_baseline"]
    layer_kind: Literal["derived_candidate_mention_evidence"]
    description: str = Field(min_length=1)


class BaselineExtractorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    kind: Literal["rule_based"]
    environment_lock_path: Literal["requirements/requirements.core.lock.txt"]
    code_revision_policy: Literal["normalized_source_bundle_sha256"]
    config_fingerprint_policy: Literal["sha256_of_canonical_semantic_json"]
    confidence_kind: Literal["not_available"]


class BaselineMatchingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_fields: list[ScientificEntitySourceField] = Field(min_length=1)
    default_case_sensitive: bool
    default_boundary: Literal["unicode_word", "none"]
    overlapping_mentions_allowed: Literal[True]
    same_span_multiple_types_allowed: Literal[True]
    normalization_before_offsets: Literal["forbidden"]
    surface_from_exact_source_slice: Literal[True]

    @model_validator(mode="after")
    def validate_source_fields(self) -> "BaselineMatchingConfig":
        if len(set(self.source_fields)) != len(self.source_fields):
            raise ValueError("matching source_fields must not contain duplicates")
        required = {
            ScientificEntitySourceField.TITLE,
            ScientificEntitySourceField.ABSTRACT,
        }
        if set(self.source_fields) != required:
            raise ValueError("baseline must declare exact title and abstract source fields")
        return self


class BaselineSafetyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_max_documents: Literal[32]
    hard_max_documents: Literal[100]
    fail_if_input_exceeds_limit: Literal[True]
    truncation_allowed: Literal[False]
    forbid_current_canonical_input: Literal[True]
    current_canonical_path: Literal[
        "data/analytics/reconciled/canonical_documents.jsonl"
    ]
    allowed_build_statuses: list[Literal["fixture", "candidate"]] = Field(
        min_length=2,
        max_length=2,
    )
    accepted_status_may_be_emitted: Literal[False]
    execute_required_for_writes: Literal[True]
    overwrite_allowed: Literal[False]
    model_or_tokenizer_download_allowed: Literal[False]
    provider_api_allowed: Literal[False]
    canonical_truth_mutation_allowed: Literal[False]
    reconcile_input_allowed: Literal[False]
    publication_allowed: Literal[False]

    @model_validator(mode="after")
    def validate_limits_and_statuses(self) -> "BaselineSafetyConfig":
        if self.default_max_documents > self.hard_max_documents:
            raise ValueError("default_max_documents must not exceed hard_max_documents")
        if set(self.allowed_build_statuses) != {"fixture", "candidate"}:
            raise ValueError("allowed build statuses must be fixture and candidate")
        return self


class BaselineOutputsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root: str = Field(min_length=1)
    immutable_build_directory: Literal[True]
    mutable_latest_pointer: Literal[False]
    encoding: Literal["utf-8"]
    line_ending: Literal["lf"]
    required_files: list[str] = Field(min_length=1)


class BaselineValidationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_dir: str = Field(min_length=1)
    require_independent_output_validator: Literal[True]
    require_exact_spans: Literal[True]
    require_deterministic_order: Literal[True]
    require_identity_recomputation: Literal[True]
    require_checksums: Literal[True]
    require_lf_outputs: Literal[True]
    require_bounded_input: Literal[True]


class BaselineFixturesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_input_path: Literal[
        "tests/fixtures/scientific_entity_extractor_baseline_v0_1/"
        "canonical_documents.jsonl"
    ]
    expected_spans_path: Literal[
        "tests/fixtures/scientific_entity_extractor_baseline_v0_1/"
        "expected_spans.jsonl"
    ]
    synthetic_only: Literal[True]


class ScientificEntityLiteralBaselineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[BASELINE_CONFIG_SCHEMA_VERSION]
    layer: BaselineLayerConfig
    extractor: BaselineExtractorConfig
    matching: BaselineMatchingConfig
    rules: list[LiteralRule] = Field(min_length=1)
    safety: BaselineSafetyConfig
    outputs: BaselineOutputsConfig
    validation: BaselineValidationConfig
    fixtures: BaselineFixturesConfig

    @model_validator(mode="after")
    def validate_rules_and_layout(self) -> "ScientificEntityLiteralBaselineConfig":
        covered_types = {rule.entity_type for rule in self.rules}
        if covered_types != set(ScientificEntityType):
            raise ValueError("baseline rules must cover all six scientific entity types")

        seen: set[tuple[str, str, bool, str]] = set()
        for rule in self.rules:
            case_sensitive = (
                self.matching.default_case_sensitive
                if rule.case_sensitive is None
                else rule.case_sensitive
            )
            boundary = rule.boundary or self.matching.default_boundary
            term_key = rule.term if case_sensitive else rule.term.casefold()
            key = (rule.entity_type.value, term_key, case_sensitive, boundary)
            if key in seen:
                raise ValueError(f"duplicate literal rule: {rule.entity_type.value}:{rule.term}")
            seen.add(key)

        expected_files = {
            "mentions.jsonl",
            "manifest.json",
            "schema.json",
            "data_quality_summary.json",
            "README.md",
            "checksums.txt",
        }
        if set(self.outputs.required_files) != expected_files:
            raise ValueError("outputs.required_files does not match the v0.1 layout")
        if len(set(self.outputs.required_files)) != len(self.outputs.required_files):
            raise ValueError("outputs.required_files must not contain duplicates")
        return self


@dataclass(frozen=True, slots=True)
class MentionCandidate:
    entity_type: ScientificEntityType
    char_start: int
    char_end: int


class ScientificEntityExtractorAdapter(Protocol):
    descriptor: ScientificEntityExtractorDescriptor

    def extract(
        self,
        *,
        canonical_id: str,
        source_field: ScientificEntitySourceField,
        source_text: str,
    ) -> Sequence[MentionCandidate]: ...


def canonical_semantic_json(payload: object) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def baseline_config_sha256(config: ScientificEntityLiteralBaselineConfig) -> str:
    payload = config.model_dump(mode="json")
    return sha256_text(canonical_semantic_json(payload))


def normalized_text_sha256(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return sha256_text(normalized)


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


def load_baseline_config(path: Path) -> ScientificEntityLiteralBaselineConfig:
    try:
        payload = yaml.load(
            path.read_text(encoding="utf-8"),
            Loader=_UniqueKeySafeLoader,
        )
    except yaml.YAMLError as exc:
        raise ScientificEntityBaselineError(f"Invalid YAML config {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ScientificEntityBaselineError(f"Expected YAML object: {path}")
    return ScientificEntityLiteralBaselineConfig.model_validate(payload)


def build_rule_extractor_descriptor(
    *,
    config: ScientificEntityLiteralBaselineConfig,
    config_sha256: str,
    environment_sha256: str,
    code_revision: str,
) -> ScientificEntityExtractorDescriptor:
    return ScientificEntityExtractorDescriptor(
        schema_version=EXTRACTOR_SCHEMA_VERSION,
        name=config.extractor.name,
        version=config.extractor.version,
        kind=ExtractorKind.RULE_BASED,
        code_revision=code_revision,
        config_sha256=config_sha256,
        environment_sha256=environment_sha256,
        model_name=None,
        model_revision=None,
        model_artifact_sha256=None,
        model_license=None,
    )


def _is_word_character(value: str) -> bool:
    return value == "_" or value.isalnum()


def _has_unicode_word_boundaries(text: str, start: int, end: int) -> bool:
    surface = text[start:end]
    if not surface:
        return False
    if _is_word_character(surface[0]) and start > 0:
        if _is_word_character(text[start - 1]):
            return False
    if _is_word_character(surface[-1]) and end < len(text):
        if _is_word_character(text[end]):
            return False
    return True


class LiteralScientificEntityExtractor:
    """Deterministic, overlapping literal matcher used only as a reference baseline."""

    def __init__(
        self,
        *,
        config: ScientificEntityLiteralBaselineConfig,
        descriptor: ScientificEntityExtractorDescriptor,
    ) -> None:
        if descriptor.kind != ExtractorKind.RULE_BASED:
            raise ScientificEntityBaselineError("literal baseline requires rule_based kind")
        self.config = config
        self.descriptor = descriptor

    def extract(
        self,
        *,
        canonical_id: str,
        source_field: ScientificEntitySourceField,
        source_text: str,
    ) -> Sequence[MentionCandidate]:
        del canonical_id
        if source_field not in self.config.matching.source_fields:
            raise ScientificEntityBaselineError(
                f"Unsupported source field: {source_field.value}"
            )

        candidates: dict[tuple[str, int, int], MentionCandidate] = {}
        for rule in self.config.rules:
            case_sensitive = (
                self.config.matching.default_case_sensitive
                if rule.case_sensitive is None
                else rule.case_sensitive
            )
            boundary = rule.boundary or self.config.matching.default_boundary
            flags = 0 if case_sensitive else re.IGNORECASE
            pattern = re.compile(re.escape(rule.term), flags=flags)
            search_start = 0
            while search_start <= len(source_text):
                match = pattern.search(source_text, search_start)
                if match is None:
                    break
                start, end = match.span()
                boundary_ok = boundary == "none" or _has_unicode_word_boundaries(
                    source_text,
                    start,
                    end,
                )
                if boundary_ok:
                    candidate = MentionCandidate(
                        entity_type=rule.entity_type,
                        char_start=start,
                        char_end=end,
                    )
                    candidates[(rule.entity_type.value, start, end)] = candidate
                search_start = start + 1

        return tuple(
            sorted(
                candidates.values(),
                key=lambda item: (
                    item.char_start,
                    item.char_end,
                    item.entity_type.value,
                ),
            )
        )
