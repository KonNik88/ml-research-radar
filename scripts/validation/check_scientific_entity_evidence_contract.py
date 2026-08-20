from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml
from pydantic import ValidationError

from radar_core.contracts.canonical_document import CanonicalDocument
from radar_core.contracts.scientific_entity_evidence import (
    ConfidenceKind,
    ExtractorKind,
    ScientificEntityCanonicalInput,
    ScientificEntityEvidenceManifest,
    ScientificEntityExtractorDescriptor,
    ScientificEntityMentionEvidence,
    ScientificEntitySourceField,
    ScientificEntityType,
    build_extractor_fingerprint,
    validate_mention_evidence,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "configs" / "scientific_entity_evidence.yaml"
CONTRACT_PATH = (
    PROJECT_ROOT / "docs" / "scientific_entity_evidence_contract_v0.1.md"
)
GITIGNORE_PATH = PROJECT_ROOT / ".gitignore"
GITATTRIBUTES_PATH = PROJECT_ROOT / ".gitattributes"
REPORT_DIR = PROJECT_ROOT / "artifacts" / "reports" / "validation"

CONFIG_SCHEMA_VERSION = "scientific_entity_evidence_config_v1"
REPORT_SCHEMA_VERSION = "scientific_entity_evidence_contract_report_v0.1"
REPORT_BASENAME = "scientific_entity_evidence_contract"

REQUIRED_ENTITY_TYPES = {"task", "method", "dataset", "metric", "model", "domain"}
REQUIRED_SOURCE_FIELDS = {"title", "abstract"}
REQUIRED_EXTRACTOR_KINDS = {
    "rule_based",
    "statistical_model",
    "language_model",
    "human_annotation",
    "imported",
}
REQUIRED_CONFIDENCE_KINDS = {
    "not_available",
    "rule_score",
    "model_score",
    "calibrated_probability",
}
REQUIRED_MENTION_FIELDS = {
    "schema_version",
    "evidence_id",
    "mention_id",
    "build_id",
    "canonical_id",
    "entity_type",
    "source_field",
    "source_text_sha256",
    "char_start",
    "char_end",
    "surface_text",
    "extractor_fingerprint",
    "confidence_kind",
    "confidence_score",
    "calibration_id",
}
REQUIRED_MANIFEST_FIELDS = {
    "build_id",
    "status",
    "generated_at_utc",
    "canonical_input",
    "extractor",
    "extractor_fingerprint",
    "offset_unit",
    "offset_interval",
    "source_fields",
    "entity_types",
    "mentions_file",
    "mention_count",
    "mentions_sha256",
    "canonical_truth_mutated",
    "may_be_used_as_reconcile_input",
    "publication_ready",
}
REQUIRED_CANONICAL_INPUT_FIELDS = {
    "schema_version",
    "path",
    "sha256",
    "document_count",
    "canonical_contract",
}
REQUIRED_MANIFEST_CANONICAL_FIELDS = {
    "path",
    "sha256",
    "document_count",
    "canonical_contract",
}
REQUIRED_EXTRACTOR_FIELDS = {
    "schema_version",
    "name",
    "version",
    "kind",
    "code_revision",
    "config_sha256",
    "environment_sha256",
}
REQUIRED_MODEL_PROVENANCE_FIELDS = {
    "model_name",
    "model_revision",
    "model_artifact_sha256",
    "model_license",
}
REQUIRED_MENTION_ID_PARTS = {
    "canonical_id",
    "source_field",
    "source_text_sha256",
    "char_start",
    "char_end",
    "entity_type",
}
REQUIRED_EVIDENCE_ID_PARTS = {"mention_id", "extractor_fingerprint"}
REQUIRED_OUTPUT_LAYOUT = {
    "mentions.jsonl",
    "manifest.json",
    "schema.json",
    "data_quality_summary.json",
    "README.md",
    "checksums.txt",
}
REQUIRED_RECORD_SORT_KEYS = [
    "canonical_id",
    "source_field_order",
    "char_start",
    "char_end",
    "entity_type",
    "evidence_id",
]
FALSE_SAFETY_FLAGS = {
    "may_be_used_as_reconcile_input",
    "may_add_fields_to_canonical_document",
    "may_mutate_canonical_corpus",
    "may_generate_full_corpus_output",
    "may_download_model_weights",
    "may_select_production_model",
    "may_change_postgres_schema",
    "may_change_retrieval_behavior",
    "may_change_qdrant_behavior",
    "may_change_graph_behavior",
    "may_change_api_behavior",
    "may_change_streamlit_behavior",
    "may_publish_output",
}
REQUIRED_VALIDATION_FLAGS = {
    "require_executable_pydantic_contract",
    "require_contract_document",
    "require_all_entity_types",
    "require_exact_span_semantics",
    "require_identity_semantics",
    "require_extractor_provenance",
    "require_confidence_semantics",
    "require_build_compatibility",
    "require_synthetic_fixture_validation",
    "require_safety_flags",
    "require_future_layout_only_outputs",
}
REQUIRED_CONTRACT_SECTIONS = {
    "## 1. Purpose and status",
    "## 2. Architectural boundaries",
    "## 4. Identity domains",
    "## 5. Scientific entity taxonomy",
    "## 6. Source text and span semantics",
    "## 7. Extractor provenance",
    "## 8. Mention evidence record",
    "## 9. Confidence semantics",
    "## 10. Build manifest and canonical compatibility",
    "## 12. Deterministic synthetic fixture",
    "## 13. Validation requirements",
    "## 15. Explicit non-goals",
    "## 17. Acceptance decision",
}
REQUIRED_CONTRACT_MARKERS = {
    "canonical_documents.jsonl = paper truth",
    "scientific entity evidence = rebuildable derived evidence",
    "mention_id = exact typed span identity",
    "evidence_id = extractor-specific observation identity",
    "future entity_id = normalized/linked entity identity, not defined in v0.1",
    "offset_unit = Unicode code point",
    "offset_interval = [char_start, char_end)",
    "normalization_before_offsets = forbidden",
    "model_score_is_not_probability = true",
    "may_be_used_as_reconcile_input = false",
    "may_generate_full_corpus_output = false",
    "Bounded Scientific Entity Extractor Baseline v0.1",
}


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    required: bool = True
    details: str | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _normalize_path(path: Path) -> str:
    return str(path).replace("\\", "/")


def _read_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"YAML root must be an object: {path}")
    return value


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def _iter_jsonl(path: Path) -> Iterable[tuple[int, dict[str, Any]]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Expected JSON object at {path}:{line_no}")
            yield line_no, value


def _file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _uses_lf_only(path: Path) -> bool:
    payload = path.read_bytes()
    return bool(payload) and b"\r" not in payload and payload.endswith(b"\n")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_set(value: Any) -> set[str]:
    return {str(item) for item in _as_list(value)}


def _add(
    checks: list[CheckResult],
    name: str,
    ok: Any,
    details: str | None = None,
    *,
    required: bool = True,
) -> None:
    checks.append(
        CheckResult(name=name, ok=bool(ok), details=details, required=required)
    )


def _all_true(mapping: Mapping[str, Any], keys: set[str]) -> tuple[bool, str | None]:
    bad = [key for key in sorted(keys) if mapping.get(key) is not True]
    return not bad, ", ".join(bad) or None


def _all_false(mapping: Mapping[str, Any], keys: set[str]) -> tuple[bool, str | None]:
    bad = [key for key in sorted(keys) if mapping.get(key) is not False]
    return not bad, ", ".join(bad) or None


def _resolve_config_path(config_path: Path, value: Any) -> Path:
    path = Path(str(value or ""))
    if path.is_absolute():
        return path
    return config_path.parent.parent / path


def _validate_fixture(
    *,
    config_path: Path,
    fixtures: Mapping[str, Any],
    outputs: Mapping[str, Any],
) -> tuple[list[CheckResult], dict[str, Any]]:
    checks: list[CheckResult] = []
    evidence: dict[str, Any] = {
        "canonical_document_count": 0,
        "mention_record_count": 0,
        "entity_types_seen": [],
        "source_fields_seen": [],
        "duplicate_evidence_id_count": 0,
        "mention_identity_conflict_count": 0,
        "evidence_identity_conflict_count": 0,
        "record_validation_error_count": 0,
        "errors": [],
    }
    path_keys = {
        "canonical_documents_path",
        "extractor_descriptor_path",
        "manifest_path",
        "mentions_path",
    }
    paths = {
        key: _resolve_config_path(config_path, fixtures.get(key)) for key in path_keys
    }
    for key, path in sorted(paths.items()):
        _add(checks, f"fixture_path_exists:{key}", path.is_file(), _normalize_path(path))

    if not all(path.is_file() for path in paths.values()):
        return checks, evidence

    _add(
        checks,
        "fixture_canonical_jsonl_lf_only",
        _uses_lf_only(paths["canonical_documents_path"]),
    )
    _add(
        checks,
        "fixture_mentions_jsonl_lf_only",
        _uses_lf_only(paths["mentions_path"]),
    )

    try:
        canonical_items = list(_iter_jsonl(paths["canonical_documents_path"]))
        canonical_rows = [row for _, row in canonical_items]
        canonical_by_id = {
            str(row.get("canonical_id")): row
            for row in canonical_rows
            if str(row.get("canonical_id") or "").strip()
        }
        evidence["canonical_document_count"] = len(canonical_rows)
        _add(checks, "fixture_canonical_non_empty", bool(canonical_rows))
        _add(
            checks,
            "fixture_canonical_ids_unique",
            len(canonical_by_id) == len(canonical_rows),
        )
        canonical_contract_errors: list[str] = []
        for line_no, row in canonical_items:
            try:
                CanonicalDocument.model_validate(row)
            except (ValueError, ValidationError) as exc:
                canonical_contract_errors.append(f"line {line_no}: {exc}")
        _add(
            checks,
            "fixture_canonical_contract_valid",
            not canonical_contract_errors,
            "; ".join(canonical_contract_errors[:3]) or None,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        evidence["errors"].append(f"canonical fixture: {exc}")
        _add(checks, "fixture_canonical_readable", False, repr(exc))
        return checks, evidence

    try:
        extractor_payload = _read_json(paths["extractor_descriptor_path"])
        extractor = ScientificEntityExtractorDescriptor.model_validate(extractor_payload)
        extractor_fingerprint = build_extractor_fingerprint(extractor)
        evidence["extractor_fingerprint"] = extractor_fingerprint
        _add(checks, "fixture_extractor_valid", True)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, ValidationError) as exc:
        evidence["errors"].append(f"extractor fixture: {exc}")
        _add(checks, "fixture_extractor_valid", False, repr(exc))
        return checks, evidence

    try:
        manifest_payload = _read_json(paths["manifest_path"])
        manifest = ScientificEntityEvidenceManifest.model_validate(manifest_payload)
        _add(checks, "fixture_manifest_valid", True)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, ValidationError) as exc:
        evidence["errors"].append(f"manifest fixture: {exc}")
        _add(checks, "fixture_manifest_valid", False, repr(exc))
        return checks, evidence

    _add(
        checks,
        "fixture_manifest_extractor_matches_file",
        manifest.extractor.model_dump(mode="json") == extractor.model_dump(mode="json"),
    )
    _add(
        checks,
        "fixture_manifest_canonical_sha256_matches",
        manifest.canonical_input.sha256
        == _file_sha256(paths["canonical_documents_path"]),
    )
    _add(
        checks,
        "fixture_manifest_canonical_count_matches",
        manifest.canonical_input.document_count == len(canonical_rows),
    )
    _add(
        checks,
        "fixture_manifest_mentions_sha256_matches",
        manifest.mentions_sha256 == _file_sha256(paths["mentions_path"]),
    )

    mention_descriptors: dict[str, tuple[Any, ...]] = {}
    evidence_records: dict[str, str] = {}
    entity_types_seen: set[str] = set()
    source_fields_seen: set[str] = set()
    valid_records: list[ScientificEntityMentionEvidence] = []
    record_count = 0

    try:
        rows = list(_iter_jsonl(paths["mentions_path"]))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        evidence["errors"].append(f"mentions fixture: {exc}")
        _add(checks, "fixture_mentions_readable", False, repr(exc))
        return checks, evidence

    for line_no, payload in rows:
        record_count += 1
        try:
            record = ScientificEntityMentionEvidence.model_validate(payload)
            canonical = canonical_by_id.get(record.canonical_id)
            if canonical is None:
                raise ValueError("canonical_id not found in fixture input")
            source_text = canonical.get(record.source_field.value)
            if not isinstance(source_text, str):
                raise ValueError("declared source field is not a string")
            validate_mention_evidence(
                record,
                source_text=source_text,
                extractor=extractor,
                manifest=manifest,
            )
        except (ValueError, ValidationError) as exc:
            evidence["record_validation_error_count"] += 1
            if len(evidence["errors"]) < 20:
                evidence["errors"].append(f"mentions line {line_no}: {exc}")
            continue

        entity_types_seen.add(record.entity_type.value)
        source_fields_seen.add(record.source_field.value)
        valid_records.append(record)
        mention_descriptor = (
            record.canonical_id,
            record.source_field.value,
            record.source_text_sha256,
            record.char_start,
            record.char_end,
            record.entity_type.value,
        )
        previous_mention = mention_descriptors.get(record.mention_id)
        if previous_mention is None:
            mention_descriptors[record.mention_id] = mention_descriptor
        elif previous_mention != mention_descriptor:
            evidence["mention_identity_conflict_count"] += 1

        serialized_record = json.dumps(
            record.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        previous_evidence = evidence_records.get(record.evidence_id)
        if previous_evidence is None:
            evidence_records[record.evidence_id] = serialized_record
        elif previous_evidence == serialized_record:
            evidence["duplicate_evidence_id_count"] += 1
        else:
            evidence["evidence_identity_conflict_count"] += 1

    evidence["mention_record_count"] = record_count
    evidence["entity_types_seen"] = sorted(entity_types_seen)
    evidence["source_fields_seen"] = sorted(source_fields_seen)

    _add(checks, "fixture_mentions_non_empty", record_count > 0)
    _add(
        checks,
        "fixture_manifest_mention_count_matches",
        manifest.mention_count == record_count,
    )
    _add(
        checks,
        "fixture_records_valid",
        evidence["record_validation_error_count"] == 0,
        "; ".join(evidence["errors"][:5]) or None,
    )
    _add(
        checks,
        "fixture_all_entity_types_covered",
        entity_types_seen == REQUIRED_ENTITY_TYPES,
        f"seen={sorted(entity_types_seen)}",
    )
    _add(
        checks,
        "fixture_title_and_abstract_covered",
        source_fields_seen == REQUIRED_SOURCE_FIELDS,
        f"seen={sorted(source_fields_seen)}",
    )
    _add(
        checks,
        "fixture_no_duplicate_evidence_ids",
        evidence["duplicate_evidence_id_count"] == 0,
    )
    _add(
        checks,
        "fixture_no_mention_identity_conflicts",
        evidence["mention_identity_conflict_count"] == 0,
    )
    _add(
        checks,
        "fixture_no_evidence_identity_conflicts",
        evidence["evidence_identity_conflict_count"] == 0,
    )
    ordering = _as_dict(outputs.get("ordering"))
    source_field_order = [str(item) for item in _as_list(ordering.get("source_field_order"))]
    source_field_rank = {
        value: index for index, value in enumerate(source_field_order)
    }
    sorted_records = sorted(
        valid_records,
        key=lambda record: (
            record.canonical_id,
            source_field_rank.get(record.source_field.value, len(source_field_rank)),
            record.char_start,
            record.char_end,
            record.entity_type.value,
            record.evidence_id,
        ),
    )
    _add(
        checks,
        "fixture_mentions_deterministically_ordered",
        [record.evidence_id for record in valid_records]
        == [record.evidence_id for record in sorted_records],
    )
    return checks, evidence


def validate_contract(
    *,
    config_path: Path = CONFIG_PATH,
    contract_path: Path = CONTRACT_PATH,
    check_canonical_path: bool = False,
    write_reports: bool = True,
    report_dir: Path | None = None,
) -> dict[str, Any]:
    config = _read_yaml(config_path)
    contract_text = contract_path.read_text(encoding="utf-8")

    layer = _as_dict(config.get("layer"))
    canonical_input = _as_dict(config.get("canonical_input"))
    compatibility = _as_dict(canonical_input.get("compatibility_policy"))
    taxonomy = _as_dict(config.get("entity_taxonomy"))
    annotation_policy = _as_dict(taxonomy.get("annotation_policy"))
    span = _as_dict(config.get("span_contract"))
    identity = _as_dict(config.get("identity"))
    mention_identity = _as_dict(identity.get("mention"))
    evidence_identity = _as_dict(identity.get("extraction_evidence"))
    identity_policies = _as_dict(identity.get("policies"))
    extractor = _as_dict(config.get("extractor_provenance"))
    mention_record = _as_dict(config.get("mention_record"))
    confidence = _as_dict(config.get("confidence"))
    confidence_policies = _as_dict(confidence.get("policies"))
    manifest = _as_dict(config.get("manifest"))
    outputs = _as_dict(config.get("outputs"))
    fixtures = _as_dict(config.get("fixtures"))
    safety = _as_dict(config.get("safety"))
    validation = _as_dict(config.get("validation"))

    checks: list[CheckResult] = []
    _add(checks, "config_exists", config_path.is_file())
    _add(checks, "contract_document_exists", contract_path.is_file())
    _add(checks, "config_schema_version_ok", config.get("schema_version") == CONFIG_SCHEMA_VERSION)
    _add(checks, "layer_name_ok", layer.get("name") == "scientific_entity_evidence")
    _add(checks, "layer_version_v01", layer.get("version") == "v0.1")
    _add(checks, "layer_status_contract_only", layer.get("status") == "contract_only")
    _add(
        checks,
        "layer_kind_derived_evidence",
        layer.get("layer_kind") == "derived_mention_evidence",
    )

    _add(checks, "canonical_path_present", bool(canonical_input.get("path")))
    _add(checks, "canonical_contract_ok", canonical_input.get("contract") == "CanonicalDocument")
    _add(
        checks,
        "canonical_identity_field_ok",
        canonical_input.get("identity_field") == "canonical_id",
    )
    _add(
        checks,
        "source_fields_exact",
        _string_set(canonical_input.get("allowed_text_fields"))
        == REQUIRED_SOURCE_FIELDS,
    )
    compatibility_ok, compatibility_details = _all_true(
        compatibility,
        {
            "manifest_records_canonical_sha256",
            "manifest_records_canonical_document_count",
            "record_stores_source_text_sha256",
            "reject_mixed_canonical_inputs",
            "no_fixed_corpus_count_in_contract",
        },
    )
    _add(checks, "canonical_compatibility_policy_ok", compatibility_ok, compatibility_details)
    _add(
        checks,
        "contract_does_not_pin_corpus_count",
        "expected_canonical_doc_count" not in canonical_input,
    )

    _add(
        checks,
        "entity_types_exact",
        _string_set(taxonomy.get("required_types")) == REQUIRED_ENTITY_TYPES,
    )
    _add(
        checks,
        "entity_type_definitions_complete",
        set(_as_dict(taxonomy.get("definitions"))) == REQUIRED_ENTITY_TYPES,
    )
    annotation_ok, annotation_details = _all_true(
        annotation_policy,
        {
            "exact_contextual_type_required",
            "overlapping_mentions_allowed",
            "same_span_multiple_types_allowed",
            "ambiguous_mentions_may_be_omitted",
            "generic_terms_without_specific_referent_excluded",
            "entity_linking_out_of_scope",
        },
    )
    _add(checks, "annotation_policy_ok", annotation_ok, annotation_details)

    _add(checks, "span_offset_unit_ok", span.get("offset_unit") == "unicode_codepoint")
    _add(checks, "span_interval_ok", span.get("offset_interval") == "half_open")
    _add(checks, "span_base_zero", span.get("offset_base") == 0)
    _add(
        checks,
        "span_exact_source_policy",
        span.get("source_text_policy") == "exact_json_decoded_canonical_field",
    )
    _add(
        checks,
        "span_normalization_forbidden",
        span.get("normalization_before_offsets") == "forbidden",
    )
    _add(checks, "surface_slice_required", span.get("surface_must_equal_source_slice") is True)
    _add(
        checks,
        "empty_or_whitespace_span_forbidden",
        span.get("empty_or_whitespace_span_forbidden") is True,
    )
    _add(checks, "null_abstract_skipped", span.get("null_abstract_policy") == "skip")

    _add(
        checks,
        "mention_identity_namespace_ok",
        mention_identity.get("namespace") == "scientific_entity_mention_v0.1",
    )
    _add(checks, "mention_identity_prefix_ok", mention_identity.get("prefix") == "mention:")
    _add(
        checks,
        "mention_identity_hash_ok",
        mention_identity.get("hash") == "sha256"
        and mention_identity.get("hash_hex_length") == 32,
    )
    _add(
        checks,
        "mention_identity_extractor_independent",
        mention_identity.get("extractor_independent") is True,
    )
    _add(
        checks,
        "mention_identity_parts_exact",
        _string_set(mention_identity.get("parts")) == REQUIRED_MENTION_ID_PARTS,
    )
    _add(
        checks,
        "evidence_identity_namespace_ok",
        evidence_identity.get("namespace")
        == "scientific_entity_extraction_evidence_v0.1",
    )
    _add(checks, "evidence_identity_prefix_ok", evidence_identity.get("prefix") == "evidence:")
    _add(
        checks,
        "evidence_identity_hash_ok",
        evidence_identity.get("hash") == "sha256"
        and evidence_identity.get("hash_hex_length") == 32,
    )
    _add(
        checks,
        "evidence_identity_parts_exact",
        _string_set(evidence_identity.get("parts")) == REQUIRED_EVIDENCE_ID_PARTS,
    )
    identity_policy_ok, identity_policy_details = _all_true(
        identity_policies,
        {
            "canonical_id_remains_paper_identity",
            "mention_id_is_not_entity_id",
            "evidence_id_is_not_entity_id",
            "same_mention_across_extractors_keeps_mention_id",
            "extractor_or_config_change_changes_evidence_id",
            "source_text_change_changes_mention_id",
            "identity_collisions_fail_closed",
        },
    )
    _add(checks, "identity_policies_ok", identity_policy_ok, identity_policy_details)

    _add(
        checks,
        "extractor_kinds_exact",
        _string_set(extractor.get("allowed_kinds")) == REQUIRED_EXTRACTOR_KINDS,
    )
    _add(
        checks,
        "extractor_required_fields_present",
        _string_set(extractor.get("required_descriptor_fields"))
        == REQUIRED_EXTRACTOR_FIELDS,
    )
    _add(
        checks,
        "model_provenance_fields_exact",
        _string_set(extractor.get("model_descriptor_required_fields"))
        == REQUIRED_MODEL_PROVENANCE_FIELDS,
    )
    _add(
        checks,
        "extractor_fingerprint_policy_ok",
        extractor.get("fingerprint_policy")
        == "sha256_of_canonical_json_descriptor",
    )

    _add(
        checks,
        "mention_record_schema_ok",
        mention_record.get("schema_version")
        == "scientific_entity_mention_evidence_v0.1",
    )
    _add(
        checks,
        "mention_record_fields_exact",
        _string_set(mention_record.get("required_fields"))
        == REQUIRED_MENTION_FIELDS,
    )
    _add(
        checks,
        "mention_record_extra_forbid",
        mention_record.get("extra_fields_forbidden") is True,
    )

    _add(
        checks,
        "confidence_kinds_exact",
        _string_set(confidence.get("allowed_kinds"))
        == REQUIRED_CONFIDENCE_KINDS,
    )
    score_range = _as_dict(confidence.get("score_range"))
    _add(
        checks,
        "confidence_range_ok",
        score_range.get("minimum") == 0.0
        and score_range.get("maximum") == 1.0,
    )
    confidence_ok, confidence_details = _all_true(
        confidence_policies,
        {
            "model_score_is_not_probability",
            "rule_score_is_not_probability",
            "calibrated_probability_requires_calibration_id",
            "not_available_requires_null_score",
            "thresholds_belong_to_extractor_config",
        },
    )
    _add(checks, "confidence_policies_ok", confidence_ok, confidence_details)

    _add(
        checks,
        "manifest_schema_ok",
        manifest.get("schema_version")
        == "scientific_entity_evidence_manifest_v0.1",
    )
    _add(
        checks,
        "manifest_fields_present",
        _string_set(manifest.get("required_build_fields"))
        == REQUIRED_MANIFEST_FIELDS,
    )
    _add(
        checks,
        "manifest_canonical_fields_exact",
        _string_set(manifest.get("required_canonical_fields"))
        == REQUIRED_MANIFEST_CANONICAL_FIELDS,
    )
    _add(
        checks,
        "manifest_statuses_exact",
        _string_set(manifest.get("allowed_statuses"))
        == {"fixture", "candidate", "accepted"},
    )

    _add(checks, "outputs_future_layout_only", outputs.get("status") == "future_layout_only")
    _add(checks, "outputs_not_generated", outputs.get("generated_in_this_slice") is False)
    _add(
        checks,
        "output_root_exact",
        outputs.get("expected_future_output_root")
        == "data/entities/scientific_entity_evidence/v0.1",
    )
    gitignore_rule = outputs.get("generated_output_gitignore_rule")
    _add(
        checks,
        "generated_output_gitignore_rule_ok",
        gitignore_rule == "/data/entities/",
    )
    gitignore_lines = {
        line.strip()
        for line in GITIGNORE_PATH.read_text(encoding="utf-8").splitlines()
    }
    _add(
        checks,
        "generated_output_gitignore_present",
        gitignore_rule in gitignore_lines,
        str(gitignore_rule),
    )
    gitattributes_lines = (
        {
            line.strip()
            for line in GITATTRIBUTES_PATH.read_text(encoding="utf-8").splitlines()
        }
        if GITATTRIBUTES_PATH.is_file()
        else set()
    )
    _add(
        checks,
        "fixture_jsonl_eol_attribute_present",
        (
            "tests/fixtures/scientific_entity_evidence_v0_1/*.jsonl "
            "text eol=lf"
        )
        in gitattributes_lines,
    )
    _add(
        checks,
        "output_builds_immutable",
        outputs.get("build_directory_policy") == "immutable_build_id_directory",
    )
    _add(
        checks,
        "mutable_latest_not_required",
        outputs.get("mutable_latest_pointer_required") is False,
    )
    _add(
        checks,
        "future_output_layout_exact",
        _string_set(outputs.get("expected_future_output_layout"))
        == REQUIRED_OUTPUT_LAYOUT,
    )
    serialization = _as_dict(outputs.get("serialization"))
    ordering = _as_dict(outputs.get("ordering"))
    _add(
        checks,
        "output_serialization_policy_ok",
        serialization.get("encoding") == "utf-8"
        and serialization.get("line_ending") == "lf"
        and serialization.get("jsonl_record_key_order")
        == "executable_contract_field_order",
    )
    _add(
        checks,
        "output_source_field_order_exact",
        [str(item) for item in _as_list(ordering.get("source_field_order"))]
        == ["title", "abstract"],
    )
    _add(
        checks,
        "output_record_sort_keys_exact",
        [str(item) for item in _as_list(ordering.get("record_sort_keys"))]
        == REQUIRED_RECORD_SORT_KEYS,
    )

    _add(checks, "fixtures_declared_synthetic", fixtures.get("synthetic_only") is True)
    _add(checks, "fixtures_require_all_types", fixtures.get("require_all_entity_types") is True)
    _add(checks, "canonical_truth_impact_none", safety.get("canonical_truth_impact") == "none")
    safety_ok, safety_details = _all_false(safety, FALSE_SAFETY_FLAGS)
    _add(checks, "safety_false_flags_ok", safety_ok, safety_details)
    validation_ok, validation_details = _all_true(validation, REQUIRED_VALIDATION_FLAGS)
    _add(checks, "required_validation_flags_ok", validation_ok, validation_details)

    mention_model_fields = set(ScientificEntityMentionEvidence.model_fields)
    manifest_model_fields = set(ScientificEntityEvidenceManifest.model_fields)
    extractor_model_fields = set(ScientificEntityExtractorDescriptor.model_fields)
    canonical_model_fields = set(CanonicalDocument.model_fields)
    mention_schema_required = set(
        ScientificEntityMentionEvidence.model_json_schema().get("required", [])
    )
    manifest_schema_required = set(
        ScientificEntityEvidenceManifest.model_json_schema().get("required", [])
    )
    extractor_schema_required = set(
        ScientificEntityExtractorDescriptor.model_json_schema().get("required", [])
    )
    canonical_input_schema_required = set(
        ScientificEntityCanonicalInput.model_json_schema().get("required", [])
    )
    _add(checks, "pydantic_mention_fields_match", mention_model_fields == REQUIRED_MENTION_FIELDS)
    _add(
        checks,
        "pydantic_manifest_fields_cover_contract",
        manifest_model_fields == ({"schema_version"} | REQUIRED_MANIFEST_FIELDS),
    )
    _add(
        checks,
        "pydantic_extractor_fields_cover_contract",
        extractor_model_fields
        == (REQUIRED_EXTRACTOR_FIELDS | REQUIRED_MODEL_PROVENANCE_FIELDS),
    )
    _add(
        checks,
        "json_schema_mention_required_fields_exact",
        mention_schema_required == REQUIRED_MENTION_FIELDS,
    )
    _add(
        checks,
        "json_schema_manifest_required_fields_cover_contract",
        manifest_schema_required == ({"schema_version"} | REQUIRED_MANIFEST_FIELDS),
    )
    _add(
        checks,
        "json_schema_extractor_required_fields_cover_contract",
        extractor_schema_required == REQUIRED_EXTRACTOR_FIELDS,
    )
    _add(
        checks,
        "json_schema_canonical_input_required_fields_exact",
        canonical_input_schema_required == REQUIRED_CANONICAL_INPUT_FIELDS,
    )
    _add(
        checks,
        "pydantic_entity_types_match",
        {item.value for item in ScientificEntityType} == REQUIRED_ENTITY_TYPES,
    )
    _add(
        checks,
        "pydantic_source_fields_match",
        {item.value for item in ScientificEntitySourceField}
        == REQUIRED_SOURCE_FIELDS,
    )
    _add(
        checks,
        "pydantic_extractor_kinds_match",
        {item.value for item in ExtractorKind} == REQUIRED_EXTRACTOR_KINDS,
    )
    _add(
        checks,
        "pydantic_confidence_kinds_match",
        {item.value for item in ConfidenceKind} == REQUIRED_CONFIDENCE_KINDS,
    )
    _add(
        checks,
        "canonical_text_fields_available",
        {"canonical_id", "title", "abstract"} <= canonical_model_fields,
    )
    _add(
        checks,
        "canonical_contract_has_no_entity_fields",
        not ({"entities", "entity_mentions", "scientific_entities"} & canonical_model_fields),
    )

    for section in sorted(REQUIRED_CONTRACT_SECTIONS):
        _add(checks, f"contract_section:{section}", section in contract_text)
    for marker in sorted(REQUIRED_CONTRACT_MARKERS):
        _add(checks, f"contract_marker:{marker}", marker in contract_text)

    fixture_checks, fixture_evidence = _validate_fixture(
        config_path=config_path,
        fixtures=fixtures,
        outputs=outputs,
    )
    checks.extend(fixture_checks)

    if check_canonical_path:
        canonical_path = _resolve_config_path(config_path, canonical_input.get("path"))
        _add(
            checks,
            "configured_canonical_path_exists",
            canonical_path.is_file(),
            _normalize_path(canonical_path),
        )

    failed_required = [check for check in checks if check.required and not check.ok]
    warnings = [check for check in checks if not check.required and not check.ok]
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at_utc": _now_iso(),
        "status": "read_only_contract_validation",
        "config_path": _normalize_path(config_path),
        "contract_path": _normalize_path(contract_path),
        "check_canonical_path": check_canonical_path,
        "canonical_truth_mutated": False,
        "full_corpus_processed": False,
        "model_weights_downloaded": False,
        "provider_api_called": False,
        "summary": {
            "ok": not failed_required,
            "total_checks": len(checks),
            "passed_checks_count": sum(check.ok for check in checks),
            "required_failed_count": len(failed_required),
            "warning_count": len(warnings),
            "entity_type_count": len(REQUIRED_ENTITY_TYPES),
            "fixture_document_count": fixture_evidence["canonical_document_count"],
            "fixture_mention_count": fixture_evidence["mention_record_count"],
        },
        "fixture_evidence": fixture_evidence,
        "checks": [check.__dict__ for check in checks],
        "verdict": {
            "contract_valid": not failed_required,
            "contract_only": layer.get("status") == "contract_only",
            "full_corpus_output_generated": outputs.get("generated_in_this_slice") is True,
            "model_selection_allowed": safety.get("may_select_production_model") is True,
            "canonical_mutation_allowed": safety.get("may_mutate_canonical_corpus") is True,
            "reconcile_input_allowed": safety.get("may_be_used_as_reconcile_input") is True,
            "publication_allowed": safety.get("may_publish_output") is True,
            "required_failed_checks": [check.name for check in failed_required],
            "next_slice": (
                "bounded_scientific_entity_extractor_baseline_v0.1"
                if not failed_required
                else None
            ),
        },
    }
    report["ok"] = report["summary"]["ok"]
    report["required_failed_count"] = report["summary"]["required_failed_count"]

    if write_reports:
        selected_report_dir = report_dir or _resolve_config_path(
            config_path,
            validation.get("report_dir") or REPORT_DIR,
        )
        _write_reports(report, selected_report_dir)
    return report


def _markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Scientific Entity Evidence Contract v0.1 validation",
        "",
        f"- Generated: `{report['generated_at_utc']}`",
        f"- Status: `{'OK' if report['summary']['ok'] else 'FAILED'}`",
        "- Scope: read-only contract and synthetic-fixture validation.",
        "",
        "## Summary",
        "",
    ]
    for key, value in report["summary"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Failed required checks", ""])
    failed = report["verdict"]["required_failed_checks"]
    if failed:
        lines.extend(f"- `{name}`" for name in failed)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- no canonical or reconciliation mutation",
            "- no production model selection or model download",
            "- no full-corpus extraction",
            "- no DB/API/UI/retrieval/Qdrant/graph change",
            "- no publication",
            "",
        ]
    )
    return "\n".join(lines)


def _write_reports(
    report: dict[str, Any], report_dir: Path
) -> tuple[Path, Path, Path, Path]:
    history_dir = report_dir / "history"
    report_dir.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    run_slug = _now_slug()
    latest_json = report_dir / f"{REPORT_BASENAME}_latest.json"
    latest_md = report_dir / f"{REPORT_BASENAME}_latest.md"
    history_json = history_dir / f"{REPORT_BASENAME}_{run_slug}.json"
    history_md = history_dir / f"{REPORT_BASENAME}_{run_slug}.md"
    report["report_paths"] = {
        "latest_json": _normalize_path(latest_json),
        "latest_markdown": _normalize_path(latest_md),
        "history_json": _normalize_path(history_json),
        "history_markdown": _normalize_path(history_md),
    }
    json_text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    markdown_text = _markdown(report)
    latest_json.write_text(json_text, encoding="utf-8")
    latest_md.write_text(markdown_text, encoding="utf-8")
    history_json.write_text(json_text, encoding="utf-8")
    history_md.write_text(markdown_text, encoding="utf-8")
    return latest_json, latest_md, history_json, history_md


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate Scientific Entity Evidence Contract v0.1 and its "
            "deterministic synthetic fixture. Read-only."
        )
    )
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--check-canonical-path", action="store_true")
    parser.add_argument("--no-write-reports", action="store_true")
    parser.add_argument("--report-dir", type=Path, default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = validate_contract(
            config_path=args.config,
            contract_path=args.contract,
            check_canonical_path=args.check_canonical_path,
            write_reports=not args.no_write_reports,
            report_dir=args.report_dir,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, yaml.YAMLError, ValueError) as exc:
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 1

    status = "OK" if report["summary"]["ok"] else "FAILED"
    print(f"[{status}] report={REPORT_BASENAME}")
    print(f"[{status}] total_checks={report['summary']['total_checks']}")
    print(f"[{status}] required_failed_count={report['summary']['required_failed_count']}")
    print(f"[{status}] fixture_document_count={report['summary']['fixture_document_count']}")
    print(f"[{status}] fixture_mention_count={report['summary']['fixture_mention_count']}")
    print(f"[{status}] next_slice={report['verdict']['next_slice']}")
    for label, path in report.get("report_paths", {}).items():
        print(f"[{status}] {label}={path}")
    if report["verdict"]["required_failed_checks"]:
        print("[FAILED] required_failed_checks:")
        for name in report["verdict"]["required_failed_checks"]:
            print(f"- {name}")
    return 0 if (report["summary"]["ok"] or not args.strict) else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
