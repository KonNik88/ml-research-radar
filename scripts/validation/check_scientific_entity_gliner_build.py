from __future__ import annotations

import argparse
import hashlib
import json
import re
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
    ExtractorKind,
    ScientificEntityEvidenceManifest,
    ScientificEntityMentionEvidence,
    ScientificEntitySourceField,
    ScientificEntityType,
    validate_mention_evidence,
)
from radar_core.entities.scientific_entity_baseline import CODE_REVISION_PREFIX
from radar_core.entities.scientific_entity_gliner import (
    GLINER_QUALITY_SCHEMA_VERSION,
    OUTPUT_SCHEMA_VERSION,
    ScientificEntityGLiNERConfig,
    gliner_config_sha256,
    load_gliner_config,
    normalized_source_bundle_revision,
    normalized_text_sha256,
)


REPORT_BASENAME = "scientific_entity_gliner_build"
REPORT_SCHEMA_VERSION = "scientific_entity_gliner_build_validation_v0.1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = (
    PROJECT_ROOT / "configs" / "scientific_entity_gliner_candidate_v0.1.yaml"
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
SOURCE_FIELD_ORDER = {
    ScientificEntitySourceField.TITLE: 0,
    ScientificEntitySourceField.ABSTRACT: 1,
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
BASE_QUALITY_KEYS = {
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
}
QUALITY_KEYS = BASE_QUALITY_KEYS | {
    "confidence_kind",
    "threshold",
    "device",
    "window_size_tokens",
    "window_overlap_tokens",
    "splitter_token_count",
    "inference_window_count",
    "windowed_source_text_count",
    "model_repository",
    "model_revision",
    "model_artifact_sha256",
    "model_artifact_verified",
    "backbone_config_repository",
    "backbone_config_revision",
    "backbone_config_artifact_sha256",
    "backbone_config_verified",
    "backbone_config_downloaded",
    "backbone_config_injected",
    "test_backend_injected",
    "canonical_truth_mutated",
    "may_be_used_as_reconcile_input",
    "publication_ready",
    "model_weights_downloaded",
    "provider_api_called",
    "full_corpus_processed",
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


def _add(
    checks: list[CheckResult],
    name: str,
    ok: bool,
    details: str | None = None,
    *,
    required: bool = True,
) -> None:
    checks.append(CheckResult(name=name, ok=bool(ok), required=required, details=details))


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            raise ValueError(f"Blank JSONL line: {path}:{line_number}")
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"Expected JSON object: {path}:{line_number}")
        rows.append(payload)
    return rows


def _text_is_utf8_lf(path: Path) -> tuple[bool, str | None]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return False, "UTF-8 BOM is forbidden"
    if b"\r" in raw:
        return False, "CR/CRLF is forbidden"
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return False, str(exc)
    if raw and not raw.endswith(b"\n"):
        return False, "text file must end with LF"
    return True, None


def _parse_checksums(path: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if "  " not in line:
            raise ValueError(f"Invalid checksum row: {line_number}")
        digest, filename = line.split("  ", 1)
        if not SHA256_PATTERN.fullmatch(digest) or not filename or filename in rows:
            raise ValueError(f"Invalid checksum row: {line_number}")
        rows[filename] = digest
    return rows


def _load_documents(
    path: Path,
    *,
    hard_limit: int,
) -> tuple[list[CanonicalDocument], dict[str, CanonicalDocument]]:
    documents: list[CanonicalDocument] = []
    by_id: dict[str, CanonicalDocument] = {}
    for payload in _read_jsonl(path):
        document = CanonicalDocument.model_validate(payload)
        if document.canonical_id in by_id:
            raise ValueError(f"Duplicate canonical_id: {document.canonical_id}")
        documents.append(document)
        by_id[document.canonical_id] = document
        if len(documents) > hard_limit:
            raise ValueError(f"Canonical input exceeds hard limit {hard_limit}")
    return documents, by_id


def _sort_key(record: ScientificEntityMentionEvidence) -> tuple[Any, ...]:
    return (
        record.canonical_id,
        SOURCE_FIELD_ORDER[record.source_field],
        record.char_start,
        record.char_end,
        record.entity_type.value,
        record.evidence_id,
    )


def _quality_counts(
    documents: Sequence[CanonicalDocument],
    records: Sequence[ScientificEntityMentionEvidence],
) -> dict[str, Any]:
    entity_counts = {item.value: 0 for item in ScientificEntityType}
    source_counts = {item.value: 0 for item in ScientificEntitySourceField}
    grouped: dict[tuple[str, str], list[ScientificEntityMentionEvidence]] = {}
    same_spans: dict[tuple[str, str, int, int], set[str]] = {}
    with_mentions: set[str] = set()
    for record in records:
        entity_counts[record.entity_type.value] += 1
        source_counts[record.source_field.value] += 1
        with_mentions.add(record.canonical_id)
        key = (record.canonical_id, record.source_field.value)
        grouped.setdefault(key, []).append(record)
        same_spans.setdefault(
            (key[0], key[1], record.char_start, record.char_end), set()
        ).add(record.entity_type.value)
    overlap_pairs = sum(
        left.char_start < right.char_end and right.char_start < left.char_end
        for group in grouped.values()
        for index, left in enumerate(group)
        for right in group[index + 1 :]
    )
    return {
        "input_document_count": len(documents),
        "processed_source_text_count": sum(
            value not in (None, "")
            for document in documents
            for value in (document.title, document.abstract)
        ),
        "documents_with_mentions_count": len(with_mentions),
        "documents_without_mentions_count": len(documents) - len(with_mentions),
        "blank_title_count": sum(not document.title for document in documents),
        "null_abstract_count": sum(document.abstract is None for document in documents),
        "empty_abstract_count": sum(document.abstract == "" for document in documents),
        "mention_count": len(records),
        "mention_count_by_entity_type": entity_counts,
        "mention_count_by_source_field": source_counts,
        "overlap_pair_count": overlap_pairs,
        "same_span_multiple_type_group_count": sum(
            len(types) > 1 for types in same_spans.values()
        ),
    }


def _cached_artifact_path(
    config: ScientificEntityGLiNERConfig,
    cache_dir: Path | None,
) -> Path | None:
    try:
        from huggingface_hub import hf_hub_download

        return Path(
            hf_hub_download(
                repo_id=config.model.repository,
                filename=config.model.artifact_filename,
                revision=config.model.revision,
                cache_dir=str(cache_dir.resolve()) if cache_dir else None,
                local_files_only=True,
            )
        ).resolve()
    except Exception:
        return None


def _cached_backbone_config_path(
    config: ScientificEntityGLiNERConfig,
    cache_dir: Path | None,
) -> Path | None:
    try:
        from huggingface_hub import hf_hub_download

        return Path(
            hf_hub_download(
                repo_id=config.model.backbone_config.repository,
                filename=config.model.backbone_config.artifact_filename,
                revision=config.model.backbone_config.revision,
                cache_dir=str(cache_dir.resolve()) if cache_dir else None,
                local_files_only=True,
            )
        ).resolve()
    except Exception:
        return None


def _build_report(
    *,
    build_dir: Path,
    config_path: Path,
    checks: Sequence[CheckResult],
    manifest: ScientificEntityEvidenceManifest | None,
    quality: Mapping[str, Any] | None,
) -> dict[str, Any]:
    failed = [check for check in checks if check.required and not check.ok]
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "read_only_bounded_gliner_build_validation",
        "build_dir": _normalize_path(build_dir),
        "config_path": _normalize_path(config_path),
        "summary": {
            "ok": not failed,
            "total_checks": len(checks),
            "passed_checks_count": sum(check.ok for check in checks),
            "required_failed_count": len(failed),
            "build_id": manifest.build_id if manifest else None,
            "build_status": manifest.status.value if manifest else None,
            "input_document_count": manifest.canonical_input.document_count if manifest else None,
            "mention_count": manifest.mention_count if manifest else None,
        },
        "quality_evidence": dict(quality or {}),
        "checks": [asdict(check) for check in checks],
        "verdict": {
            "build_valid": not failed,
            "candidate_comparison_authorized": not failed,
            "production_extractor_selected": False,
            "full_corpus_build_authorized": False,
            "canonical_mutation_allowed": False,
            "reconcile_input_allowed": False,
            "publication_allowed": False,
            "required_failed_checks": [check.name for check in failed],
            "next_slice": "compare_gliner_candidate_on_existing_pilot_dev_evidence_v0.1"
            if not failed
            else None,
        },
    }
    report["ok"] = report["summary"]["ok"]
    report["required_failed_count"] = report["summary"]["required_failed_count"]
    return report


def _write_reports(report: dict[str, Any], report_dir: Path) -> None:
    history = report_dir / "history"
    report_dir.mkdir(parents=True, exist_ok=True)
    history.mkdir(parents=True, exist_ok=True)
    slug = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    markdown = (
        "# Scientific Entity GLiNER build validation\n\n"
        f"- status: `{'OK' if report['summary']['ok'] else 'FAILED'}`\n"
        f"- required_failed_count: `{report['summary']['required_failed_count']}`\n"
        "- bounded candidate evidence only; no production/full-corpus authorization\n"
    )
    json_text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    for path, text in (
        (report_dir / f"{REPORT_BASENAME}_latest.json", json_text),
        (report_dir / f"{REPORT_BASENAME}_latest.md", markdown),
        (history / f"{REPORT_BASENAME}_{slug}.json", json_text),
        (history / f"{REPORT_BASENAME}_{slug}.md", markdown),
    ):
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)


def validate_gliner_build(
    *,
    build_dir: Path,
    config_path: Path = DEFAULT_CONFIG_PATH,
    model_cache_dir: Path | None = None,
    write_reports: bool = True,
    report_dir: Path | None = None,
) -> dict[str, Any]:
    build_dir = build_dir.resolve()
    config_path = config_path.resolve()
    config = load_gliner_config(config_path)
    checks: list[CheckResult] = []
    manifest: ScientificEntityEvidenceManifest | None = None
    quality: dict[str, Any] = {}
    selected_report_dir = report_dir or _resolve_project_path(config.validation.report_dir)

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
    files = {path.name for path in build_dir.iterdir() if path.is_file()}
    dirs = {path.name for path in build_dir.iterdir() if path.is_dir()}
    _add(checks, "exact_output_files_present", files == set(REQUIRED_FILES))
    _add(checks, "nested_directories_absent", not dirs)
    if files != set(REQUIRED_FILES):
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
        ok, detail = _text_is_utf8_lf(build_dir / filename)
        _add(checks, f"output_utf8_lf:{filename}", ok, detail)
    try:
        manifest = ScientificEntityEvidenceManifest.model_validate(
            _read_json(build_dir / "manifest.json")
        )
        _add(checks, "manifest_schema_valid", True)
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        _add(checks, "manifest_schema_valid", False, str(exc))
    try:
        schema = _read_json(build_dir / "schema.json")
        _add(checks, "schema_json_valid", True)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        schema = {}
        _add(checks, "schema_json_valid", False, str(exc))
    try:
        quality = _read_json(build_dir / "data_quality_summary.json")
        _add(checks, "quality_json_valid", True)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        _add(checks, "quality_json_valid", False, str(exc))
    try:
        records = [
            ScientificEntityMentionEvidence.model_validate(row)
            for row in _read_jsonl(build_dir / "mentions.jsonl")
        ]
        _add(checks, "mention_records_schema_valid", True)
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        records = []
        _add(checks, "mention_records_schema_valid", False, str(exc))
    try:
        checksums = _parse_checksums(build_dir / "checksums.txt")
        _add(checks, "checksums_file_valid", True)
    except (OSError, UnicodeError, ValueError) as exc:
        checksums = {}
        _add(checks, "checksums_file_valid", False, str(exc))
    _add(checks, "checksums_cover_exact_files", set(checksums) == set(CHECKSUM_FILES))
    for filename in CHECKSUM_FILES:
        _add(
            checks,
            f"checksum_matches:{filename}",
            checksums.get(filename) == _sha256_file(build_dir / filename),
        )

    _add(checks, "schema_version_matches", schema.get("schema_version") == OUTPUT_SCHEMA_VERSION)
    _add(checks, "mention_schema_matches", schema.get("mentions_schema_version") == MENTION_SCHEMA_VERSION)
    _add(checks, "manifest_schema_matches", schema.get("manifest_schema_version") == MANIFEST_SCHEMA_VERSION)
    _add(checks, "quality_schema_matches", schema.get("data_quality_schema_version") == GLINER_QUALITY_SCHEMA_VERSION)
    _add(checks, "schema_keys_exact", set(schema) == SCHEMA_KEYS)
    _add(checks, "quality_keys_exact", set(quality) == QUALITY_KEYS)
    serialization = schema.get("serialization") or {}
    _add(checks, "serialization_utf8_lf", serialization.get("encoding") == "utf-8" and serialization.get("line_ending") == "lf")
    _add(checks, "serialization_offsets", serialization.get("offset_unit") == "unicode_codepoint" and serialization.get("offset_interval") == "half_open")
    readme = (build_dir / "README.md").read_text(encoding="utf-8")
    for marker in (
        "derived and rebuildable",
        "not canonical paper truth",
        "not a full-corpus build",
        "not publication ready",
    ):
        _add(checks, f"readme_marker:{marker}", marker in readme)

    if manifest is not None:
        _add(checks, "build_directory_matches_build_id", build_dir.name == manifest.build_id)
        _add(checks, "bounded_status", manifest.status in {EntityEvidenceBuildStatus.FIXTURE, EntityEvidenceBuildStatus.CANDIDATE})
        _add(checks, "accepted_status_absent", manifest.status != EntityEvidenceBuildStatus.ACCEPTED)
        _add(checks, "extractor_kind_statistical", manifest.extractor.kind == ExtractorKind.STATISTICAL_MODEL)
        _add(checks, "model_repository_pinned", manifest.extractor.model_name == config.model.repository)
        _add(checks, "model_revision_pinned", manifest.extractor.model_revision == config.model.revision)
        _add(checks, "model_artifact_sha_pinned", manifest.extractor.model_artifact_sha256 == config.model.artifact_sha256)
        _add(checks, "model_license_pinned", manifest.extractor.model_license == config.model.license)
        _add(checks, "config_sha_matches", manifest.extractor.config_sha256 == gliner_config_sha256(config))
        env_path = _resolve_project_path(config.extractor.environment_lock_path)
        _add(checks, "environment_lock_exists", env_path.is_file())
        _add(checks, "environment_sha_matches", env_path.is_file() and manifest.extractor.environment_sha256 == normalized_text_sha256(env_path))
        _add(checks, "code_revision_shape", bool(CODE_REVISION_PATTERN.fullmatch(manifest.extractor.code_revision)))
        _add(checks, "code_revision_matches_current_source", manifest.extractor.code_revision == normalized_source_bundle_revision(PROJECT_ROOT))
        _add(checks, "source_fields_match", manifest.source_fields == config.inference.source_fields)
        _add(checks, "entity_types_complete", manifest.entity_types == list(ScientificEntityType))
        _add(checks, "manifest_mention_count_matches", manifest.mention_count == len(records))
        _add(checks, "manifest_mentions_sha_matches", manifest.mentions_sha256 == _sha256_file(build_dir / "mentions.jsonl"))
        _add(checks, "manifest_safety_flags", not manifest.canonical_truth_mutated and not manifest.may_be_used_as_reconcile_input and not manifest.publication_ready)

        canonical_path = _resolve_project_path(manifest.canonical_input.path)
        fixture_path = _resolve_project_path(config.fixtures.default_input_path)
        _add(checks, "current_canonical_path_fixed", _resolve_project_path(config.safety.current_canonical_path) == CURRENT_CANONICAL_PATH.resolve())
        _add(checks, "canonical_input_exists", canonical_path.is_file())
        _add(checks, "current_full_canonical_forbidden", canonical_path != CURRENT_CANONICAL_PATH.resolve())
        _add(checks, "fixture_input_matches", manifest.status != EntityEvidenceBuildStatus.FIXTURE or canonical_path == fixture_path)
        if canonical_path.is_file():
            _add(checks, "canonical_input_sha_matches", manifest.canonical_input.sha256 == _sha256_file(canonical_path))
            try:
                documents, by_id = _load_documents(canonical_path, hard_limit=config.safety.hard_max_documents)
                _add(checks, "canonical_input_schema_valid", True)
            except (OSError, UnicodeError, json.JSONDecodeError, ValidationError, ValueError) as exc:
                documents, by_id = [], {}
                _add(checks, "canonical_input_schema_valid", False, str(exc))
        else:
            documents, by_id = [], {}
        _add(checks, "canonical_document_count_matches", manifest.canonical_input.document_count == len(documents))

        errors: list[str] = []
        for index, record in enumerate(records):
            document = by_id.get(record.canonical_id)
            if document is None:
                errors.append(f"{index}: missing canonical_id")
                continue
            source = document.title if record.source_field == ScientificEntitySourceField.TITLE else document.abstract
            if source is None:
                errors.append(f"{index}: source is null")
                continue
            try:
                validate_mention_evidence(record, source_text=source, extractor=manifest.extractor, manifest=manifest)
            except ValueError as exc:
                errors.append(f"{index}: {exc}")
        _add(checks, "mention_evidence_recomputed", not errors, "; ".join(errors[:5]) or None)
        _add(checks, "mention_records_sorted", records == sorted(records, key=_sort_key))
        _add(checks, "evidence_ids_unique", len({row.evidence_id for row in records}) == len(records))
        _add(checks, "mention_ids_unique", len({row.mention_id for row in records}) == len(records))
        _add(checks, "confidence_is_model_score", all(row.confidence_kind == ConfidenceKind.MODEL_SCORE and row.confidence_score is not None and row.calibration_id is None for row in records))

        for key, expected in _quality_counts(documents, records).items():
            _add(checks, f"quality_counter_matches:{key}", quality.get(key) == expected)
        _add(checks, "quality_build_identity", quality.get("build_id") == manifest.build_id and quality.get("status") == manifest.status.value)
        _add(checks, "quality_bounds", quality.get("bounded") is True and quality.get("truncated") is False and quality.get("hard_max_documents") == config.safety.hard_max_documents)
        _add(checks, "quality_inference_config", quality.get("confidence_kind") == "model_score" and quality.get("threshold") == config.inference.threshold and quality.get("device") == config.inference.device and quality.get("window_size_tokens") == config.inference.window_size_tokens and quality.get("window_overlap_tokens") == config.inference.window_overlap_tokens)
        _add(checks, "quality_model_provenance", quality.get("model_repository") == config.model.repository and quality.get("model_revision") == config.model.revision and quality.get("model_artifact_sha256") == config.model.artifact_sha256)
        _add(
            checks,
            "quality_backbone_config_provenance",
            quality.get("backbone_config_repository")
            == config.model.backbone_config.repository
            and quality.get("backbone_config_revision")
            == config.model.backbone_config.revision
            and quality.get("backbone_config_artifact_sha256")
            == config.model.backbone_config.artifact_sha256,
        )
        _add(checks, "quality_nonnegative_diagnostics", all(isinstance(quality.get(key), int) and quality[key] >= 0 for key in ("splitter_token_count", "inference_window_count", "windowed_source_text_count")))
        _add(checks, "quality_safety_flags", all(quality.get(key) is False for key in ("canonical_truth_mutated", "may_be_used_as_reconcile_input", "publication_ready", "provider_api_called", "full_corpus_processed")))
        if manifest.status == EntityEvidenceBuildStatus.CANDIDATE:
            _add(checks, "candidate_not_test_backend", quality.get("test_backend_injected") is False)
            _add(checks, "candidate_artifact_verified_at_build", quality.get("model_artifact_verified") is True)
            _add(
                checks,
                "candidate_backbone_config_verified_at_build",
                quality.get("backbone_config_verified") is True,
            )
            _add(
                checks,
                "candidate_backbone_config_injected_at_build",
                quality.get("backbone_config_injected") is True,
            )
            cached_artifact = _cached_artifact_path(config, model_cache_dir)
            _add(checks, "candidate_cached_artifact_present", cached_artifact is not None)
            _add(checks, "candidate_cached_artifact_size_matches", cached_artifact is not None and cached_artifact.stat().st_size == config.model.artifact_size_bytes)
            _add(checks, "candidate_cached_artifact_sha_matches", cached_artifact is not None and _sha256_file(cached_artifact) == config.model.artifact_sha256)
            cached_backbone_config = _cached_backbone_config_path(
                config,
                model_cache_dir,
            )
            _add(
                checks,
                "candidate_cached_backbone_config_present",
                cached_backbone_config is not None,
            )
            _add(
                checks,
                "candidate_cached_backbone_config_size_matches",
                cached_backbone_config is not None
                and cached_backbone_config.stat().st_size
                == config.model.backbone_config.artifact_size_bytes,
            )
            _add(
                checks,
                "candidate_cached_backbone_config_sha_matches",
                cached_backbone_config is not None
                and _sha256_file(cached_backbone_config)
                == config.model.backbone_config.artifact_sha256,
            )
        else:
            _add(checks, "fixture_backend_boundary", quality.get("test_backend_injected") is True or quality.get("model_artifact_verified") is True)

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
    parser = argparse.ArgumentParser(description="Validate one immutable bounded GLiNER candidate build.")
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--model-cache-dir", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--no-write-reports", action="store_true")
    parser.add_argument("--report-dir", type=Path, default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = validate_gliner_build(
            build_dir=args.build_dir,
            config_path=args.config,
            model_cache_dir=args.model_cache_dir,
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
    return 0 if report["summary"]["ok"] or not args.strict else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
