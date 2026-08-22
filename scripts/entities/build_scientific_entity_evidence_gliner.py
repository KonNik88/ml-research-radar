from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from radar_core.contracts.canonical_document import CanonicalDocument
from radar_core.contracts.scientific_entity_evidence import (
    CANONICAL_INPUT_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    MENTION_SCHEMA_VERSION,
    ConfidenceKind,
    EntityEvidenceBuildStatus,
    ScientificEntityCanonicalInput,
    ScientificEntityEvidenceManifest,
    ScientificEntityMentionEvidence,
    ScientificEntitySourceField,
    ScientificEntityType,
    build_evidence_id,
    build_extractor_fingerprint,
    build_mention_id,
    sha256_text,
)
from radar_core.entities.scientific_entity_gliner import (
    GLINER_QUALITY_SCHEMA_VERSION,
    OUTPUT_SCHEMA_VERSION,
    GLiNERBackend,
    ScientificEntityGLiNERAdapter,
    ScientificEntityGLiNERConfig,
    ScientificEntityGLiNERError,
    build_gliner_extractor_descriptor,
    gliner_config_sha256,
    load_gliner_config,
    load_native_gliner_backend,
    normalized_source_bundle_revision,
    normalized_text_sha256,
)


REPORT_NAME = "bounded_scientific_entity_gliner_candidate_adapter_v01"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = (
    PROJECT_ROOT / "configs" / "scientific_entity_gliner_candidate_v0.1.yaml"
)
CURRENT_CANONICAL_PATH = (
    PROJECT_ROOT / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"
)
CHECKSUM_FILES = (
    "mentions.jsonl",
    "manifest.json",
    "schema.json",
    "data_quality_summary.json",
    "README.md",
)
REQUIRED_FILES = (*CHECKSUM_FILES, "checksums.txt")
SOURCE_FIELD_ORDER = {
    ScientificEntitySourceField.TITLE: 0,
    ScientificEntitySourceField.ABSTRACT: 1,
}


class ScientificEntityGLiNERBuildError(RuntimeError):
    """Raised when a bounded GLiNER build cannot be prepared safely."""


def _normalize_path(path: Path | str) -> str:
    return str(path).replace("\\", "/")


def _resolve_project_path(path: Path | str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


def _project_relative_or_absolute(path: Path) -> str:
    resolved = path.resolve()
    try:
        return _normalize_path(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        return _normalize_path(resolved)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_text(payload: Any, *, compact: bool = False) -> str:
    if compact:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _write_text_lf(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _default_build_id(generated_at_utc: datetime) -> str:
    timestamp = generated_at_utc.strftime("%Y%m%dT%H%M%S%fZ")
    return f"scientific-entity-gliner-small-v2.5-v0.1-{timestamp}"


def _load_documents(
    input_path: Path,
    *,
    max_documents: int,
) -> tuple[list[CanonicalDocument], str]:
    documents: list[CanonicalDocument] = []
    seen_ids: set[str] = set()
    digest = hashlib.sha256()
    with input_path.open("rb") as handle:
        for line_number, raw_bytes in enumerate(handle, start=1):
            digest.update(raw_bytes)
            try:
                line = raw_bytes.decode("utf-8")
                payload = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ScientificEntityGLiNERBuildError(
                    f"Invalid JSONL at {input_path}:{line_number}: {exc}"
                ) from exc
            if not line.strip() or not isinstance(payload, dict):
                raise ScientificEntityGLiNERBuildError(
                    f"Expected non-blank JSON object at {input_path}:{line_number}"
                )
            document = CanonicalDocument.model_validate(payload)
            if document.canonical_id in seen_ids:
                raise ScientificEntityGLiNERBuildError(
                    f"Duplicate canonical_id: {document.canonical_id}"
                )
            seen_ids.add(document.canonical_id)
            documents.append(document)
            if len(documents) > max_documents:
                raise ScientificEntityGLiNERBuildError(
                    f"Input exceeds max_documents={max_documents}; truncation is forbidden"
                )
    if not documents:
        raise ScientificEntityGLiNERBuildError("Input JSONL contains no documents")
    return documents, digest.hexdigest()


def _validate_safe_input(
    *,
    config: ScientificEntityGLiNERConfig,
    input_path: Path,
    status: EntityEvidenceBuildStatus,
    max_documents: int,
    injected_backend: bool,
) -> None:
    if max_documents < 1:
        raise ScientificEntityGLiNERBuildError("max_documents must be positive")
    if max_documents > config.safety.hard_max_documents:
        raise ScientificEntityGLiNERBuildError(
            f"Requested limit exceeds hard limit {config.safety.hard_max_documents}"
        )
    if status.value not in config.safety.allowed_build_statuses:
        raise ScientificEntityGLiNERBuildError(f"Disallowed build status: {status.value}")
    configured_current = _resolve_project_path(config.safety.current_canonical_path)
    if configured_current != CURRENT_CANONICAL_PATH.resolve():
        raise ScientificEntityGLiNERBuildError(
            "Configured current canonical path violates the fixed safety boundary"
        )
    if input_path.resolve() == CURRENT_CANONICAL_PATH.resolve():
        raise ScientificEntityGLiNERBuildError(
            "Current full canonical corpus is forbidden in bounded adapter v0.1"
        )
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    fixture_path = _resolve_project_path(config.fixtures.default_input_path)
    if status == EntityEvidenceBuildStatus.FIXTURE and input_path != fixture_path:
        raise ScientificEntityGLiNERBuildError(
            "fixture status is reserved for the tracked synthetic fixture"
        )
    if injected_backend and (
        status != EntityEvidenceBuildStatus.FIXTURE or input_path != fixture_path
    ):
        raise ScientificEntityGLiNERBuildError(
            "Injected test backends are allowed only for the tracked fixture"
        )


def _build_mentions(
    *,
    documents: Sequence[CanonicalDocument],
    adapter: ScientificEntityGLiNERAdapter,
    build_id: str,
    extractor_fingerprint: str,
) -> tuple[list[ScientificEntityMentionEvidence], dict[str, int]]:
    records: list[ScientificEntityMentionEvidence] = []
    evidence_payloads: dict[str, dict[str, Any]] = {}
    mention_payloads: dict[str, dict[str, Any]] = {}
    splitter_token_count = 0
    inference_window_count = 0
    windowed_source_text_count = 0

    for document in documents:
        values = {
            ScientificEntitySourceField.TITLE: document.title,
            ScientificEntitySourceField.ABSTRACT: document.abstract,
        }
        for source_field in adapter.config.inference.source_fields:
            source_text = values[source_field]
            if source_text in (None, ""):
                continue
            result = adapter.extract(
                canonical_id=document.canonical_id,
                source_field=source_field,
                source_text=source_text,
            )
            splitter_token_count += result.splitter_token_count
            inference_window_count += result.window_count
            windowed_source_text_count += int(result.windowed)
            source_sha = sha256_text(source_text)
            for candidate in result.candidates:
                surface = source_text[candidate.char_start : candidate.char_end]
                mention_id = build_mention_id(
                    canonical_id=document.canonical_id,
                    source_field=source_field,
                    source_text_sha256=source_sha,
                    char_start=candidate.char_start,
                    char_end=candidate.char_end,
                    entity_type=candidate.entity_type,
                )
                evidence_id = build_evidence_id(
                    mention_id=mention_id,
                    extractor_fingerprint=extractor_fingerprint,
                )
                record = ScientificEntityMentionEvidence(
                    schema_version=MENTION_SCHEMA_VERSION,
                    evidence_id=evidence_id,
                    mention_id=mention_id,
                    build_id=build_id,
                    canonical_id=document.canonical_id,
                    entity_type=candidate.entity_type,
                    source_field=source_field,
                    source_text_sha256=source_sha,
                    char_start=candidate.char_start,
                    char_end=candidate.char_end,
                    surface_text=surface,
                    extractor_fingerprint=extractor_fingerprint,
                    confidence_kind=ConfidenceKind.MODEL_SCORE,
                    confidence_score=round(candidate.score, 8),
                    calibration_id=None,
                )
                payload = record.model_dump(mode="json")
                prior_evidence = evidence_payloads.get(evidence_id)
                prior_mention = mention_payloads.get(mention_id)
                if prior_evidence is not None and prior_evidence != payload:
                    raise ScientificEntityGLiNERBuildError(
                        f"Conflicting evidence_id collision: {evidence_id}"
                    )
                if prior_mention is not None and prior_mention != payload:
                    raise ScientificEntityGLiNERBuildError(
                        f"Conflicting mention_id collision: {mention_id}"
                    )
                if prior_evidence is None:
                    evidence_payloads[evidence_id] = payload
                    mention_payloads[mention_id] = payload
                    records.append(record)

    records.sort(
        key=lambda record: (
            record.canonical_id,
            SOURCE_FIELD_ORDER[record.source_field],
            record.char_start,
            record.char_end,
            record.entity_type.value,
            record.evidence_id,
        )
    )
    return records, {
        "splitter_token_count": splitter_token_count,
        "inference_window_count": inference_window_count,
        "windowed_source_text_count": windowed_source_text_count,
    }


def _mentions_bytes(records: Sequence[ScientificEntityMentionEvidence]) -> bytes:
    rows = [_json_text(record.model_dump(mode="json"), compact=True) for record in records]
    return (("\n".join(rows) + "\n") if rows else "").encode("utf-8")


def _overlap_counts(
    records: Sequence[ScientificEntityMentionEvidence],
) -> tuple[int, int]:
    groups: dict[tuple[str, str], list[ScientificEntityMentionEvidence]] = {}
    same_spans: dict[tuple[str, str, int, int], set[str]] = {}
    for record in records:
        key = (record.canonical_id, record.source_field.value)
        groups.setdefault(key, []).append(record)
        same_spans.setdefault(
            (key[0], key[1], record.char_start, record.char_end), set()
        ).add(record.entity_type.value)
    overlap_pairs = sum(
        left.char_start < right.char_end and right.char_start < left.char_end
        for group in groups.values()
        for index, left in enumerate(group)
        for right in group[index + 1 :]
    )
    return overlap_pairs, sum(len(types) > 1 for types in same_spans.values())


def _quality_summary(
    *,
    config: ScientificEntityGLiNERConfig,
    build_id: str,
    status: EntityEvidenceBuildStatus,
    documents: Sequence[CanonicalDocument],
    records: Sequence[ScientificEntityMentionEvidence],
    diagnostics: Mapping[str, int],
    max_documents: int,
    model_artifact_verified: bool,
    backbone_config_verified: bool,
    backbone_config_downloaded: bool,
    backbone_config_injected: bool,
    model_weights_downloaded: bool,
    test_backend_injected: bool,
) -> dict[str, Any]:
    entity_counts = Counter(record.entity_type.value for record in records)
    source_counts = Counter(record.source_field.value for record in records)
    documents_with_mentions = {record.canonical_id for record in records}
    overlap_pairs, same_span_groups = _overlap_counts(records)
    return {
        "schema_version": GLINER_QUALITY_SCHEMA_VERSION,
        "build_id": build_id,
        "status": status.value,
        "bounded": True,
        "input_document_count": len(documents),
        "max_documents": max_documents,
        "hard_max_documents": config.safety.hard_max_documents,
        "truncated": False,
        "processed_source_text_count": sum(
            value not in (None, "")
            for document in documents
            for value in (document.title, document.abstract)
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
        "same_span_multiple_type_group_count": same_span_groups,
        "confidence_kind": ConfidenceKind.MODEL_SCORE.value,
        "threshold": config.inference.threshold,
        "device": config.inference.device,
        "window_size_tokens": config.inference.window_size_tokens,
        "window_overlap_tokens": config.inference.window_overlap_tokens,
        **dict(diagnostics),
        "model_repository": config.model.repository,
        "model_revision": config.model.revision,
        "model_artifact_sha256": config.model.artifact_sha256,
        "model_artifact_verified": model_artifact_verified,
        "backbone_config_repository": config.model.backbone_config.repository,
        "backbone_config_revision": config.model.backbone_config.revision,
        "backbone_config_artifact_sha256": (
            config.model.backbone_config.artifact_sha256
        ),
        "backbone_config_verified": backbone_config_verified,
        "backbone_config_downloaded": backbone_config_downloaded,
        "backbone_config_injected": backbone_config_injected,
        "test_backend_injected": test_backend_injected,
        "canonical_truth_mutated": False,
        "may_be_used_as_reconcile_input": False,
        "publication_ready": False,
        "model_weights_downloaded": model_weights_downloaded,
        "provider_api_called": False,
        "full_corpus_processed": False,
    }


def _schema_payload() -> dict[str, Any]:
    return {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "mentions_schema_version": MENTION_SCHEMA_VERSION,
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "data_quality_schema_version": GLINER_QUALITY_SCHEMA_VERSION,
        "serialization": {
            "encoding": "utf-8",
            "line_ending": "lf",
            "offset_unit": "unicode_codepoint",
            "offset_interval": "half_open",
        },
        "mentions_json_schema": ScientificEntityMentionEvidence.model_json_schema(),
        "manifest_json_schema": ScientificEntityEvidenceManifest.model_json_schema(),
    }


def _readme(
    *,
    build_id: str,
    status: EntityEvidenceBuildStatus,
    generated_at_utc: datetime,
    document_count: int,
    mention_count: int,
) -> str:
    return "\n".join(
        [
            "# Bounded GLiNER Scientific Entity Evidence v0.1",
            "",
            "This immutable directory contains experimental GLiNER candidate evidence.",
            "It is derived and rebuildable. It is not canonical paper truth, not a",
            "reconcile input, not a production-selected model, and not a full-corpus build.",
            "It is not publication ready.",
            "",
            "## Build",
            "",
            f"- build_id: `{build_id}`",
            f"- status: `{status.value}`",
            f"- generated_at_utc: `{generated_at_utc.isoformat()}`",
            f"- input_document_count: `{document_count}`",
            f"- mention_count: `{mention_count}`",
            "",
            "Scores are uncalibrated model scores. Long inputs use overlapping",
            "splitter-token windows; exact-span duplicates retain the highest score.",
            "Any promotion, full-corpus generation, runtime integration, or publication",
            "requires a separate reviewed slice.",
            "",
        ]
    )


def _write_output(
    *,
    output_dir: Path,
    mentions_bytes: bytes,
    manifest: ScientificEntityEvidenceManifest,
    schema: Mapping[str, Any],
    quality: Mapping[str, Any],
    readme: str,
) -> list[str]:
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    if output_dir.exists():
        raise FileExistsError(
            f"Immutable build directory already exists; overwrite is forbidden: {output_dir}"
        )
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.tmp-", dir=output_dir.parent))
    try:
        (staging / "mentions.jsonl").write_bytes(mentions_bytes)
        _write_text_lf(staging / "manifest.json", _json_text(manifest.model_dump(mode="json")))
        _write_text_lf(staging / "schema.json", _json_text(dict(schema)))
        _write_text_lf(staging / "data_quality_summary.json", _json_text(dict(quality)))
        _write_text_lf(staging / "README.md", readme)
        checksums = [f"{_sha256_file(staging / name)}  {name}" for name in CHECKSUM_FILES]
        _write_text_lf(staging / "checksums.txt", "\n".join(checksums) + "\n")
        staging.rename(output_dir)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return list(REQUIRED_FILES)


def build_gliner_candidate(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    input_path: Path | None = None,
    output_root: Path | None = None,
    build_id: str | None = None,
    status: EntityEvidenceBuildStatus | str = EntityEvidenceBuildStatus.FIXTURE,
    max_documents: int | None = None,
    execute: bool = False,
    allow_model_download: bool = False,
    model_cache_dir: Path | None = None,
    generated_at_utc: datetime | None = None,
    backend: GLiNERBackend | None = None,
) -> dict[str, Any]:
    config_path = config_path.resolve()
    config = load_gliner_config(config_path)
    selected_input = _resolve_project_path(input_path or config.fixtures.default_input_path)
    selected_output_root = _resolve_project_path(output_root or config.outputs.root)
    selected_status = EntityEvidenceBuildStatus(status)
    if selected_status == EntityEvidenceBuildStatus.ACCEPTED:
        raise ScientificEntityGLiNERBuildError("Adapter v0.1 cannot emit accepted status")
    selected_max = config.safety.default_max_documents if max_documents is None else max_documents
    _validate_safe_input(
        config=config,
        input_path=selected_input,
        status=selected_status,
        max_documents=selected_max,
        injected_backend=backend is not None,
    )
    documents, input_sha = _load_documents(selected_input, max_documents=selected_max)
    generated_at = generated_at_utc or _utc_now()
    if generated_at.tzinfo is None or generated_at.utcoffset() != timezone.utc.utcoffset(generated_at):
        raise ScientificEntityGLiNERBuildError("generated_at_utc must be timezone-aware UTC")
    selected_build_id = build_id or _default_build_id(generated_at)
    output_dir = selected_output_root / selected_build_id
    if execute and output_dir.exists():
        raise FileExistsError(
            f"Immutable build directory already exists; overwrite is forbidden: {output_dir}"
        )

    environment_lock = _resolve_project_path(config.extractor.environment_lock_path)
    if not environment_lock.is_file():
        raise FileNotFoundError(environment_lock)
    config_sha = gliner_config_sha256(config)
    descriptor = build_gliner_extractor_descriptor(
        config=config,
        config_sha256=config_sha,
        environment_sha256=normalized_text_sha256(environment_lock),
        code_revision=normalized_source_bundle_revision(PROJECT_ROOT),
    )
    fingerprint = build_extractor_fingerprint(descriptor)

    test_backend_injected = backend is not None
    artifact_verified = False
    backbone_config_verified = False
    backbone_config_downloaded = False
    backbone_config_injected = False
    weights_downloaded = False
    snapshot_path: str | None = None
    backbone_config_path: str | None = None
    selected_backend = backend
    if selected_backend is None:
        loaded = load_native_gliner_backend(
            config=config,
            allow_model_download=allow_model_download,
            cache_dir=model_cache_dir,
        )
        selected_backend = loaded.backend
        artifact_verified = loaded.model_artifact_verified
        backbone_config_verified = loaded.backbone_config_verified
        backbone_config_downloaded = loaded.backbone_config_downloaded
        backbone_config_injected = loaded.backbone_config_injected
        weights_downloaded = loaded.model_weights_downloaded
        snapshot_path = _normalize_path(loaded.snapshot_path)
        backbone_config_path = _normalize_path(loaded.backbone_config_path)

    adapter = ScientificEntityGLiNERAdapter(
        config=config,
        descriptor=descriptor,
        backend=selected_backend,
    )
    peak_cuda_memory_bytes: int | None = None
    runtime_device_name: str | None = None
    if not test_backend_injected:
        import torch

        if config.inference.device == "cuda":
            torch.cuda.synchronize()
            torch.cuda.reset_peak_memory_stats()
            runtime_device_name = torch.cuda.get_device_name(0)
    inference_started = time.perf_counter()
    records, diagnostics = _build_mentions(
        documents=documents,
        adapter=adapter,
        build_id=selected_build_id,
        extractor_fingerprint=fingerprint,
    )
    if not test_backend_injected and config.inference.device == "cuda":
        import torch

        torch.cuda.synchronize()
        peak_cuda_memory_bytes = int(torch.cuda.max_memory_allocated())
    inference_duration_seconds = time.perf_counter() - inference_started
    mentions_bytes = _mentions_bytes(records)
    canonical_input = ScientificEntityCanonicalInput(
        schema_version=CANONICAL_INPUT_SCHEMA_VERSION,
        path=_project_relative_or_absolute(selected_input),
        sha256=input_sha,
        document_count=len(documents),
        canonical_contract="CanonicalDocument",
    )
    manifest = ScientificEntityEvidenceManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        build_id=selected_build_id,
        status=selected_status,
        generated_at_utc=generated_at,
        canonical_input=canonical_input,
        extractor=descriptor,
        extractor_fingerprint=fingerprint,
        offset_unit="unicode_codepoint",
        offset_interval="half_open",
        source_fields=list(config.inference.source_fields),
        entity_types=list(ScientificEntityType),
        mentions_file="mentions.jsonl",
        mention_count=len(records),
        mentions_sha256=hashlib.sha256(mentions_bytes).hexdigest(),
        canonical_truth_mutated=False,
        may_be_used_as_reconcile_input=False,
        publication_ready=False,
    )
    quality = _quality_summary(
        config=config,
        build_id=selected_build_id,
        status=selected_status,
        documents=documents,
        records=records,
        diagnostics=diagnostics,
        max_documents=selected_max,
        model_artifact_verified=artifact_verified,
        backbone_config_verified=backbone_config_verified,
        backbone_config_downloaded=backbone_config_downloaded,
        backbone_config_injected=backbone_config_injected,
        model_weights_downloaded=weights_downloaded,
        test_backend_injected=test_backend_injected,
    )
    written_files: list[str] = []
    if execute:
        written_files = _write_output(
            output_dir=output_dir,
            mentions_bytes=mentions_bytes,
            manifest=manifest,
            schema=_schema_payload(),
            quality=quality,
            readme=_readme(
                build_id=selected_build_id,
                status=selected_status,
                generated_at_utc=generated_at,
                document_count=len(documents),
                mention_count=len(records),
            ),
        )
    return {
        "schema_version": "bounded_scientific_entity_gliner_candidate_report_v0.1",
        "report": REPORT_NAME,
        "ok": True,
        "mode": "execute" if execute else "plan",
        "phase_complete": execute,
        "build_id": selected_build_id,
        "status": selected_status.value,
        "config_path": _normalize_path(config_path),
        "input_path": _normalize_path(selected_input),
        "output_dir": _normalize_path(output_dir),
        "input_document_count": len(documents),
        "mention_count": len(records),
        **diagnostics,
        "config_sha256": config_sha,
        "environment_sha256": descriptor.environment_sha256,
        "code_revision": descriptor.code_revision,
        "extractor_fingerprint": fingerprint,
        "model_repository": config.model.repository,
        "model_revision": config.model.revision,
        "model_artifact_sha256": config.model.artifact_sha256,
        "model_artifact_verified": artifact_verified,
        "backbone_config_repository": config.model.backbone_config.repository,
        "backbone_config_revision": config.model.backbone_config.revision,
        "backbone_config_artifact_sha256": (
            config.model.backbone_config.artifact_sha256
        ),
        "backbone_config_verified": backbone_config_verified,
        "backbone_config_downloaded": backbone_config_downloaded,
        "backbone_config_injected": backbone_config_injected,
        "backbone_config_path": backbone_config_path,
        "model_download_allowed": allow_model_download,
        "model_weights_downloaded": weights_downloaded,
        "model_snapshot_path": snapshot_path,
        "runtime_device_name": runtime_device_name,
        "inference_duration_seconds": round(inference_duration_seconds, 6),
        "peak_cuda_memory_bytes": peak_cuda_memory_bytes,
        "test_backend_injected": test_backend_injected,
        "written_files": written_files,
        "canonical_truth_mutated": False,
        "full_corpus_processed": False,
        "provider_api_called": False,
        "publication_ready": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Plan or execute the bounded GLiNER Scientific Entity candidate adapter. "
            "Network/model download is disabled unless explicitly allowed."
        )
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--build-id", default=None)
    parser.add_argument("--status", choices=("fixture", "candidate"), default="fixture")
    parser.add_argument("--max-documents", type=int, default=None)
    parser.add_argument("--model-cache-dir", type=Path, default=None)
    parser.add_argument("--allow-model-download", action="store_true")
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_gliner_candidate(
            config_path=args.config,
            input_path=args.input,
            output_root=args.output_root,
            build_id=args.build_id,
            status=args.status,
            max_documents=args.max_documents,
            execute=args.execute,
            allow_model_download=args.allow_model_download,
            model_cache_dir=args.model_cache_dir,
        )
    except (
        FileNotFoundError,
        OSError,
        ValueError,
        ScientificEntityGLiNERError,
        ScientificEntityGLiNERBuildError,
    ) as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 1
    print(f"[OK] report={REPORT_NAME}")
    print(f"[OK] mode={report['mode']}")
    print(f"[OK] phase_complete={report['phase_complete']}")
    print(f"[OK] build_id={report['build_id']}")
    print(f"[OK] status={report['status']}")
    print(f"[OK] input_document_count={report['input_document_count']}")
    print(f"[OK] mention_count={report['mention_count']}")
    print(f"[OK] model_artifact_verified={report['model_artifact_verified']}")
    print(f"[OK] backbone_config_verified={report['backbone_config_verified']}")
    print(f"[OK] backbone_config_injected={report['backbone_config_injected']}")
    print(f"[OK] inference_duration_seconds={report['inference_duration_seconds']}")
    print(f"[OK] peak_cuda_memory_bytes={report['peak_cuda_memory_bytes']}")
    print(f"[OK] output_dir={report['output_dir']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
