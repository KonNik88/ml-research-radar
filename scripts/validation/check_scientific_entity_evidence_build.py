from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from pydantic import ValidationError

from radar_core.contracts.canonical_document import CanonicalDocument
from radar_core.contracts.scientific_entity_evidence import (
    MANIFEST_SCHEMA_VERSION,
    MENTION_SCHEMA_VERSION,
    ConfidenceKind,
    EntityEvidenceBuildStatus,
    ScientificEntityEvidenceManifest,
    ScientificEntityMentionEvidence,
    ScientificEntitySourceField,
    ScientificEntityType,
    validate_mention_evidence,
)
from radar_core.entities.scientific_entity_baseline import (
    CODE_REVISION_PREFIX,
    DATA_QUALITY_SCHEMA_VERSION,
    OUTPUT_SCHEMA_VERSION,
    ScientificEntityLiteralBaselineConfig,
    baseline_config_sha256,
    load_baseline_config,
    normalized_text_sha256,
)


REPORT_BASENAME = "scientific_entity_evidence_build"
REPORT_SCHEMA_VERSION = "scientific_entity_evidence_build_validation_v0.1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = (
    PROJECT_ROOT / "configs" / "scientific_entity_extractor_baseline_v0.1.yaml"
)
CURRENT_CANONICAL_PATH = (
    PROJECT_ROOT / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"
)
REQUIRED_FILES = (
    "mentions.jsonl",
    "manifest.json",
    "schema.json",
    "data_quality_summary.json",
    "README.md",
    "checksums.txt",
)
CHECKSUM_FILES = REQUIRED_FILES[:-1]
CODE_REVISION_FILES = (
    "radar_core/contracts/scientific_entity_evidence.py",
    "radar_core/entities/scientific_entity_baseline.py",
    "scripts/entities/build_scientific_entity_evidence_baseline.py",
)
QUALITY_KEYS = {
    "schema_version",
    "build_id",
    "status",
    "bounded",
    "input_document_count",
    "max_documents",
    "hard_max_documents",
    "truncated",
    "processed_source_text_count",
    "documents_with_mentions_count",
    "documents_without_mentions_count",
    "blank_title_count",
    "null_abstract_count",
    "empty_abstract_count",
    "mention_count",
    "mention_count_by_entity_type",
    "mention_count_by_source_field",
    "overlap_pair_count",
    "same_span_multiple_type_group_count",
    "confidence_kind",
    "canonical_truth_mutated",
    "may_be_used_as_reconcile_input",
    "publication_ready",
    "model_weights_downloaded",
    "provider_api_called",
    "full_corpus_processed",
}
SCHEMA_KEYS = {
    "schema_version",
    "mentions_schema_version",
    "manifest_schema_version",
    "data_quality_schema_version",
    "serialization",
    "mentions_json_schema",
    "manifest_json_schema",
}
SOURCE_FIELD_ORDER = {
    ScientificEntitySourceField.TITLE: 0,
    ScientificEntitySourceField.ABSTRACT: 1,
}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
CODE_REVISION_PATTERN = re.compile(
    rf"^{re.escape(CODE_REVISION_PREFIX)}[0-9a-f]{{64}}$"
)


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    ok: bool
    required: bool = True
    details: str | None = None


def _normalize_path(path: Path | str) -> str:
    return str(path).replace("\\", "/")


def _resolve_project_path(path: Path | str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_bundle_revision() -> str:
    digest = hashlib.sha256()
    for relative_path in sorted(CODE_REVISION_FILES):
        path = PROJECT_ROOT / relative_path
        if not path.is_file():
            raise FileNotFoundError(path)
        normalized = path.read_text(encoding="utf-8")
        normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(normalized.encode("utf-8"))
        digest.update(b"\0")
    return f"{CODE_REVISION_PREFIX}{digest.hexdigest()}"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now_utc().isoformat()


def _now_slug() -> str:
    return _now_utc().strftime("%Y%m%dT%H%M%S%fZ")


def _add(
    checks: list[CheckResult],
    name: str,
    ok: bool,
    details: str | None = None,
    *,
    required: bool = True,
) -> None:
    checks.append(
        CheckResult(
            name=name,
            ok=bool(ok),
            required=required,
            details=details,
        )
    )


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                raise ValueError(f"Blank JSONL line: {path}:{line_number}")
            payload = json.loads(raw_line)
            if not isinstance(payload, dict):
                raise ValueError(f"Expected JSON object: {path}:{line_number}")
            rows.append(payload)
    return rows


def _text_is_utf8_lf(path: Path) -> tuple[bool, str | None]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return False, "UTF-8 BOM is forbidden"
    if b"\r" in raw:
        return False, "CR or CRLF line endings are forbidden"
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return False, f"invalid UTF-8: {exc}"
    if raw and not raw.endswith(b"\n"):
        return False, "text file must end with LF"
    return True, None


def _parse_checksums(path: Path) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if "  " not in raw_line:
            raise ValueError(f"Invalid checksum row at line {line_number}")
        digest, filename = raw_line.split("  ", 1)
        if not SHA256_PATTERN.fullmatch(digest):
            raise ValueError(f"Invalid checksum digest at line {line_number}")
        if not filename or filename in parsed:
            raise ValueError(f"Invalid or duplicate checksum path at line {line_number}")
        parsed[filename] = digest
    return parsed


def _load_canonical_documents(
    path: Path,
    *,
    max_documents: int,
) -> tuple[list[CanonicalDocument], dict[str, CanonicalDocument]]:
    documents: list[CanonicalDocument] = []
    by_id: dict[str, CanonicalDocument] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                raise ValueError(f"Blank JSONL line: {path}:{line_number}")
            row = json.loads(raw_line)
            if not isinstance(row, dict):
                raise ValueError(f"Expected JSON object: {path}:{line_number}")
            document = CanonicalDocument.model_validate(row)
            if document.canonical_id in by_id:
                raise ValueError(f"Duplicate canonical_id: {document.canonical_id}")
            documents.append(document)
            by_id[document.canonical_id] = document
            if len(documents) > max_documents:
                raise ValueError(
                    f"Canonical input exceeds hard limit {max_documents}"
                )
    return documents, by_id


def _record_sort_key(record: ScientificEntityMentionEvidence) -> tuple[Any, ...]:
    return (
        record.canonical_id,
        SOURCE_FIELD_ORDER[record.source_field],
        record.char_start,
        record.char_end,
        record.entity_type.value,
        record.evidence_id,
    )


def _expected_quality_counts(
    *,
    documents: Sequence[CanonicalDocument],
    records: Sequence[ScientificEntityMentionEvidence],
) -> dict[str, Any]:
    entity_counts = Counter(record.entity_type.value for record in records)
    source_counts = Counter(record.source_field.value for record in records)
    documents_with_mentions = {record.canonical_id for record in records}
    grouped: dict[tuple[str, str], list[ScientificEntityMentionEvidence]] = {}
    same_span_types: dict[tuple[str, str, int, int], set[str]] = {}
    for record in records:
        grouped.setdefault(
            (record.canonical_id, record.source_field.value),
            [],
        ).append(record)
        same_span_types.setdefault(
            (
                record.canonical_id,
                record.source_field.value,
                record.char_start,
                record.char_end,
            ),
            set(),
        ).add(record.entity_type.value)

    overlap_pairs = 0
    for group in grouped.values():
        for index, left in enumerate(group):
            for right in group[index + 1 :]:
                if left.char_start < right.char_end and right.char_start < left.char_end:
                    overlap_pairs += 1

    return {
        "input_document_count": len(documents),
        "processed_source_text_count": sum(
            1
            for document in documents
            for value in (document.title, document.abstract)
            if value not in (None, "")
        ),
        "documents_with_mentions_count": len(documents_with_mentions),
        "documents_without_mentions_count": len(documents) - len(documents_with_mentions),
        "blank_title_count": sum(not document.title for document in documents),
        "null_abstract_count": sum(document.abstract is None for document in documents),
        "empty_abstract_count": sum(document.abstract == "" for document in documents),
        "mention_count": len(records),
        "mention_count_by_entity_type": {
            entity_type.value: entity_counts[entity_type.value]
            for entity_type in ScientificEntityType
        },
        "mention_count_by_source_field": {
            source_field.value: source_counts[source_field.value]
            for source_field in ScientificEntitySourceField
        },
        "overlap_pair_count": overlap_pairs,
        "same_span_multiple_type_group_count": sum(
            len(entity_types) > 1 for entity_types in same_span_types.values()
        ),
    }


def _build_report(
    *,
    build_dir: Path,
    config_path: Path,
    checks: Sequence[CheckResult],
    manifest: ScientificEntityEvidenceManifest | None,
    quality: Mapping[str, Any] | None,
) -> dict[str, Any]:
    failed_required = [check for check in checks if check.required and not check.ok]
    warnings = [check for check in checks if not check.required and not check.ok]
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at_utc": _now_iso(),
        "status": "read_only_bounded_build_validation",
        "build_dir": _normalize_path(build_dir),
        "config_path": _normalize_path(config_path),
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
            "build_id": manifest.build_id if manifest else None,
            "build_status": manifest.status.value if manifest else None,
            "input_document_count": (
                manifest.canonical_input.document_count if manifest else None
            ),
            "mention_count": manifest.mention_count if manifest else None,
        },
        "quality_evidence": dict(quality or {}),
        "checks": [asdict(check) for check in checks],
        "verdict": {
            "build_valid": not failed_required,
            "bounded_candidate_evidence": (
                manifest is not None
                and manifest.status
                in {EntityEvidenceBuildStatus.FIXTURE, EntityEvidenceBuildStatus.CANDIDATE}
            ),
            "production_extractor_selected": False,
            "full_corpus_build_authorized": False,
            "canonical_mutation_allowed": False,
            "reconcile_input_allowed": False,
            "publication_allowed": False,
            "required_failed_checks": [check.name for check in failed_required],
            "authorized_follow_on": (
                "scientific_entity_review_and_evaluation_v0.1"
                if not failed_required
                else None
            ),
            "next_slice": (
                "bounded_scientific_entity_manual_review_evidence_v0.1"
                if not failed_required
                else None
            ),
        },
    }
    report["ok"] = report["summary"]["ok"]
    report["required_failed_count"] = report["summary"]["required_failed_count"]
    return report


def _markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Scientific Entity Evidence Build validation",
        "",
        f"- Generated: `{report['generated_at_utc']}`",
        f"- Status: `{'OK' if report['summary']['ok'] else 'FAILED'}`",
        "- Scope: read-only bounded build-directory validation.",
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
            "- bounded candidate evidence only",
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
    report: dict[str, Any],
    report_dir: Path,
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
    json_text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    markdown_text = _markdown(report)
    for path, text in (
        (latest_json, json_text),
        (latest_md, markdown_text),
        (history_json, json_text),
        (history_md, markdown_text),
    ):
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    return latest_json, latest_md, history_json, history_md


def validate_build(
    *,
    build_dir: Path,
    config_path: Path = DEFAULT_CONFIG_PATH,
    write_reports: bool = True,
    report_dir: Path | None = None,
) -> dict[str, Any]:
    build_dir = build_dir.resolve()
    config_path = config_path.resolve()
    config = load_baseline_config(config_path)
    selected_report_dir = report_dir or _resolve_project_path(
        config.validation.report_dir
    )
    checks: list[CheckResult] = []
    manifest: ScientificEntityEvidenceManifest | None = None
    quality: dict[str, Any] | None = None

    _add(checks, "build_directory_exists", build_dir.is_dir(), _normalize_path(build_dir))
    if not build_dir.is_dir():
        report = _build_report(
            build_dir=build_dir,
            config_path=config_path,
            checks=checks,
            manifest=None,
            quality=None,
        )
        if write_reports:
            _write_reports(report, selected_report_dir)
        return report

    actual_files = {path.name for path in build_dir.iterdir() if path.is_file()}
    actual_directories = {path.name for path in build_dir.iterdir() if path.is_dir()}
    _add(checks, "required_output_files_present", set(REQUIRED_FILES) <= actual_files)
    _add(checks, "unexpected_output_files_absent", actual_files == set(REQUIRED_FILES))
    _add(checks, "nested_output_directories_absent", not actual_directories)
    if not set(REQUIRED_FILES) <= actual_files:
        report = _build_report(
            build_dir=build_dir,
            config_path=config_path,
            checks=checks,
            manifest=None,
            quality=None,
        )
        if write_reports:
            _write_reports(report, selected_report_dir)
        return report

    for filename in REQUIRED_FILES:
        ok, details = _text_is_utf8_lf(build_dir / filename)
        _add(checks, f"output_utf8_lf:{filename}", ok, details)

    try:
        manifest_payload = _read_json(build_dir / "manifest.json")
        manifest = ScientificEntityEvidenceManifest.model_validate(manifest_payload)
        _add(checks, "manifest_schema_valid", True)
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        _add(checks, "manifest_schema_valid", False, str(exc))
        manifest_payload = {}

    try:
        schema_payload = _read_json(build_dir / "schema.json")
        _add(checks, "schema_json_valid", True)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        _add(checks, "schema_json_valid", False, str(exc))
        schema_payload = {}

    try:
        quality = _read_json(build_dir / "data_quality_summary.json")
        _add(checks, "data_quality_json_valid", True)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        _add(checks, "data_quality_json_valid", False, str(exc))
        quality = {}

    try:
        mention_payloads = _read_jsonl(build_dir / "mentions.jsonl")
        records = [
            ScientificEntityMentionEvidence.model_validate(payload)
            for payload in mention_payloads
        ]
        _add(checks, "mention_records_schema_valid", True)
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        _add(checks, "mention_records_schema_valid", False, str(exc))
        mention_payloads = []
        records = []

    try:
        checksums = _parse_checksums(build_dir / "checksums.txt")
        _add(checks, "checksums_file_valid", True)
    except (OSError, UnicodeError, ValueError) as exc:
        _add(checks, "checksums_file_valid", False, str(exc))
        checksums = {}
    _add(checks, "checksums_cover_exact_files", set(checksums) == set(CHECKSUM_FILES))
    for filename in CHECKSUM_FILES:
        expected = checksums.get(filename)
        _add(
            checks,
            f"checksum_matches:{filename}",
            expected is not None and expected == _sha256_file(build_dir / filename),
        )

    _add(
        checks,
        "output_schema_version_matches",
        schema_payload.get("schema_version") == OUTPUT_SCHEMA_VERSION,
    )
    _add(
        checks,
        "mention_schema_version_matches",
        schema_payload.get("mentions_schema_version") == MENTION_SCHEMA_VERSION,
    )
    _add(
        checks,
        "manifest_schema_version_matches",
        schema_payload.get("manifest_schema_version") == MANIFEST_SCHEMA_VERSION,
    )
    _add(
        checks,
        "quality_schema_version_matches",
        quality.get("schema_version") == DATA_QUALITY_SCHEMA_VERSION,
    )
    _add(checks, "schema_has_exact_top_level_keys", set(schema_payload) == SCHEMA_KEYS)
    _add(checks, "quality_has_exact_top_level_keys", set(quality) == QUALITY_KEYS)
    serialization = schema_payload.get("serialization") or {}
    _add(checks, "schema_declares_utf8", serialization.get("encoding") == "utf-8")
    _add(checks, "schema_declares_lf", serialization.get("line_ending") == "lf")
    _add(
        checks,
        "schema_declares_unicode_codepoint_offsets",
        serialization.get("offset_unit") == "unicode_codepoint",
    )
    _add(
        checks,
        "schema_declares_half_open_offsets",
        serialization.get("offset_interval") == "half_open",
    )

    readme = (build_dir / "README.md").read_text(encoding="utf-8")
    _add(checks, "readme_marks_derived", "derived and rebuildable" in readme)
    _add(checks, "readme_rejects_canonical_truth", "not canonical paper truth" in readme)
    _add(checks, "readme_rejects_full_corpus", "not a full-corpus build" in readme)
    _add(checks, "readme_rejects_publication", "not publication ready" in readme)

    if manifest is not None:
        _add(checks, "build_directory_matches_build_id", build_dir.name == manifest.build_id)
        _add(checks, "readme_build_id_matches", manifest.build_id in readme)
        _add(
            checks,
            "baseline_status_is_bounded",
            manifest.status
            in {EntityEvidenceBuildStatus.FIXTURE, EntityEvidenceBuildStatus.CANDIDATE},
        )
        _add(
            checks,
            "accepted_status_absent",
            manifest.status != EntityEvidenceBuildStatus.ACCEPTED,
        )
        _add(
            checks,
            "manifest_config_sha_matches",
            manifest.extractor.config_sha256 == baseline_config_sha256(config),
        )
        environment_path = _resolve_project_path(config.extractor.environment_lock_path)
        _add(checks, "environment_lock_exists", environment_path.is_file())
        _add(
            checks,
            "manifest_environment_sha_matches",
            environment_path.is_file()
            and manifest.extractor.environment_sha256
            == normalized_text_sha256(environment_path),
        )
        _add(
            checks,
            "manifest_code_revision_is_immutable_source_hash",
            bool(CODE_REVISION_PATTERN.fullmatch(manifest.extractor.code_revision)),
        )
        _add(
            checks,
            "manifest_code_revision_matches_current_source",
            manifest.extractor.code_revision == _source_bundle_revision(),
        )
        _add(
            checks,
            "manifest_source_fields_match_config",
            manifest.source_fields == config.matching.source_fields,
        )
        _add(
            checks,
            "manifest_entity_types_complete",
            manifest.entity_types == list(ScientificEntityType),
        )
        _add(checks, "manifest_mentions_file_matches", manifest.mentions_file == "mentions.jsonl")
        _add(checks, "manifest_mention_count_matches", manifest.mention_count == len(records))
        _add(
            checks,
            "manifest_mentions_sha_matches",
            manifest.mentions_sha256 == _sha256_file(build_dir / "mentions.jsonl"),
        )
        _add(checks, "manifest_canonical_truth_not_mutated", not manifest.canonical_truth_mutated)
        _add(checks, "manifest_not_reconcile_input", not manifest.may_be_used_as_reconcile_input)
        _add(checks, "manifest_not_publication_ready", not manifest.publication_ready)

        canonical_path = _resolve_project_path(manifest.canonical_input.path)
        current_canonical_path = _resolve_project_path(config.safety.current_canonical_path)
        fixture_path = _resolve_project_path(config.fixtures.default_input_path)
        _add(
            checks,
            "configured_current_canonical_path_is_fixed",
            current_canonical_path == CURRENT_CANONICAL_PATH.resolve(),
        )
        _add(checks, "canonical_input_exists", canonical_path.is_file())
        _add(
            checks,
            "current_full_canonical_input_forbidden",
            canonical_path != current_canonical_path,
        )
        _add(
            checks,
            "fixture_status_input_matches",
            manifest.status != EntityEvidenceBuildStatus.FIXTURE
            or canonical_path == fixture_path,
        )
        if canonical_path.is_file():
            _add(
                checks,
                "canonical_input_sha_matches",
                manifest.canonical_input.sha256 == _sha256_file(canonical_path),
            )
            try:
                documents, documents_by_id = _load_canonical_documents(
                    canonical_path,
                    max_documents=config.safety.hard_max_documents,
                )
                _add(checks, "canonical_input_schema_valid", True)
            except (
                OSError,
                UnicodeError,
                json.JSONDecodeError,
                ValidationError,
                ValueError,
            ) as exc:
                _add(checks, "canonical_input_schema_valid", False, str(exc))
                documents = []
                documents_by_id = {}
        else:
            documents = []
            documents_by_id = {}
        _add(
            checks,
            "canonical_document_count_matches",
            manifest.canonical_input.document_count == len(documents),
        )
        _add(
            checks,
            "canonical_input_within_hard_limit",
            len(documents) <= config.safety.hard_max_documents,
        )

        record_errors: list[str] = []
        for index, record in enumerate(records):
            document = documents_by_id.get(record.canonical_id)
            if document is None:
                record_errors.append(f"record {index}: canonical_id missing from input")
                continue
            source_text = (
                document.title
                if record.source_field == ScientificEntitySourceField.TITLE
                else document.abstract
            )
            if source_text is None:
                record_errors.append(f"record {index}: source field is null")
                continue
            try:
                validate_mention_evidence(
                    record,
                    source_text=source_text,
                    extractor=manifest.extractor,
                    manifest=manifest,
                )
            except ValueError as exc:
                record_errors.append(f"record {index}: {exc}")
        _add(
            checks,
            "mention_evidence_recomputed",
            not record_errors,
            "; ".join(record_errors[:5]) or None,
        )
        _add(
            checks,
            "mention_records_sorted",
            records == sorted(records, key=_record_sort_key),
        )
        _add(
            checks,
            "evidence_ids_unique",
            len({record.evidence_id for record in records}) == len(records),
        )
        _add(
            checks,
            "mention_ids_unique",
            len({record.mention_id for record in records}) == len(records),
        )
        _add(
            checks,
            "confidence_is_not_available",
            all(
                record.confidence_kind == ConfidenceKind.NOT_AVAILABLE
                and record.confidence_score is None
                and record.calibration_id is None
                for record in records
            ),
        )

        expected_quality = _expected_quality_counts(
            documents=documents,
            records=records,
        )
        for key, expected_value in expected_quality.items():
            _add(
                checks,
                f"quality_counter_matches:{key}",
                quality.get(key) == expected_value,
            )
        _add(checks, "quality_build_id_matches", quality.get("build_id") == manifest.build_id)
        _add(checks, "quality_status_matches", quality.get("status") == manifest.status.value)
        _add(checks, "quality_bounded_true", quality.get("bounded") is True)
        _add(checks, "quality_truncated_false", quality.get("truncated") is False)
        _add(
            checks,
            "quality_max_documents_valid",
            isinstance(quality.get("max_documents"), int)
            and len(documents) <= quality["max_documents"] <= config.safety.hard_max_documents,
        )
        _add(
            checks,
            "quality_hard_limit_matches",
            quality.get("hard_max_documents") == config.safety.hard_max_documents,
        )
        for flag in (
            "canonical_truth_mutated",
            "may_be_used_as_reconcile_input",
            "publication_ready",
            "model_weights_downloaded",
            "provider_api_called",
            "full_corpus_processed",
        ):
            _add(checks, f"quality_safety_false:{flag}", quality.get(flag) is False)

    report = _build_report(
        build_dir=build_dir,
        config_path=config_path,
        checks=checks,
        manifest=manifest,
        quality=quality,
    )
    if write_reports:
        _write_reports(report, selected_report_dir)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate one immutable bounded Scientific Entity Evidence v0.1 "
            "build directory. Read-only."
        )
    )
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--no-write-reports", action="store_true")
    parser.add_argument("--report-dir", type=Path, default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = validate_build(
            build_dir=args.build_dir,
            config_path=args.config,
            write_reports=not args.no_write_reports,
            report_dir=args.report_dir,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        print(f"[FAILED] report={REPORT_BASENAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 1

    status = "OK" if report["summary"]["ok"] else "FAILED"
    print(f"[{status}] report={REPORT_BASENAME}")
    print(f"[{status}] total_checks={report['summary']['total_checks']}")
    print(f"[{status}] required_failed_count={report['summary']['required_failed_count']}")
    print(f"[{status}] build_id={report['summary']['build_id']}")
    print(f"[{status}] input_document_count={report['summary']['input_document_count']}")
    print(f"[{status}] mention_count={report['summary']['mention_count']}")
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
