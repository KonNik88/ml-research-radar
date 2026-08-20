from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
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
from radar_core.entities.scientific_entity_baseline import (
    CODE_REVISION_PREFIX,
    DATA_QUALITY_SCHEMA_VERSION,
    OUTPUT_SCHEMA_VERSION,
    LiteralScientificEntityExtractor,
    ScientificEntityBaselineError,
    ScientificEntityLiteralBaselineConfig,
    baseline_config_sha256,
    build_rule_extractor_descriptor,
    load_baseline_config,
    normalized_text_sha256,
)


REPORT_NAME = "bounded_scientific_entity_extractor_baseline_v01"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = (
    PROJECT_ROOT / "configs" / "scientific_entity_extractor_baseline_v0.1.yaml"
)
CURRENT_CANONICAL_PATH = (
    PROJECT_ROOT / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"
)
CODE_REVISION_FILES = (
    "radar_core/contracts/scientific_entity_evidence.py",
    "radar_core/entities/scientific_entity_baseline.py",
    "scripts/entities/build_scientific_entity_evidence_baseline.py",
)
CHECKSUM_FILES = (
    "mentions.jsonl",
    "manifest.json",
    "schema.json",
    "data_quality_summary.json",
    "README.md",
)
SOURCE_FIELD_ORDER = {
    ScientificEntitySourceField.TITLE: 0,
    ScientificEntitySourceField.ABSTRACT: 1,
}


class ScientificEntityEvidenceBuildError(RuntimeError):
    """Raised when a bounded build cannot safely be prepared or written."""


def _normalize_path(path: Path | str) -> str:
    return str(path).replace("\\", "/")


def _project_relative_or_absolute(path: Path) -> str:
    resolved = path.resolve()
    try:
        return _normalize_path(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        return _normalize_path(resolved)


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


def _json_text(payload: Any, *, compact: bool = False) -> str:
    if compact:
        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _write_text_lf(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _source_bundle_revision() -> str:
    digest = hashlib.sha256()
    for relative_path in sorted(CODE_REVISION_FILES):
        path = PROJECT_ROOT / relative_path
        if not path.is_file():
            raise ScientificEntityEvidenceBuildError(
                f"Code revision source file is missing: {path}"
            )
        normalized = path.read_text(encoding="utf-8")
        normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(normalized.encode("utf-8"))
        digest.update(b"\0")
    return f"{CODE_REVISION_PREFIX}{digest.hexdigest()}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _build_id(generated_at_utc: datetime) -> str:
    timestamp = generated_at_utc.strftime("%Y%m%dT%H%M%S%fZ")
    return f"scientific-entity-literal-v0.1-{timestamp}"


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
                raw_line = raw_bytes.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ScientificEntityEvidenceBuildError(
                    f"Invalid UTF-8 at {input_path}:{line_number}: {exc}"
                ) from exc
            if not raw_line.strip():
                raise ScientificEntityEvidenceBuildError(
                    f"Blank JSONL line is forbidden: {input_path}:{line_number}"
                )
            try:
                payload = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise ScientificEntityEvidenceBuildError(
                    f"Invalid JSON at {input_path}:{line_number}: {exc}"
                ) from exc
            if not isinstance(payload, dict):
                raise ScientificEntityEvidenceBuildError(
                    f"Expected JSON object at {input_path}:{line_number}"
                )
            document = CanonicalDocument.model_validate(payload)
            if not document.canonical_id.strip():
                raise ScientificEntityEvidenceBuildError("canonical_id must not be blank")
            if document.canonical_id in seen_ids:
                raise ScientificEntityEvidenceBuildError(
                    f"Duplicate canonical_id: {document.canonical_id}"
                )
            seen_ids.add(document.canonical_id)
            documents.append(document)
            if len(documents) > max_documents:
                raise ScientificEntityEvidenceBuildError(
                    f"Input exceeds bounded max_documents={max_documents}; truncation is forbidden"
                )
    if not documents:
        raise ScientificEntityEvidenceBuildError("Input JSONL contains no documents")
    return documents, digest.hexdigest()


def _validate_safe_input(
    *,
    config: ScientificEntityLiteralBaselineConfig,
    input_path: Path,
    status: EntityEvidenceBuildStatus,
    max_documents: int,
) -> None:
    if max_documents < 1:
        raise ScientificEntityEvidenceBuildError("max_documents must be positive")
    if max_documents > config.safety.hard_max_documents:
        raise ScientificEntityEvidenceBuildError(
            "Requested max_documents exceeds the configured hard limit "
            f"of {config.safety.hard_max_documents}"
        )
    if status.value not in config.safety.allowed_build_statuses:
        raise ScientificEntityEvidenceBuildError(
            f"Build status is not allowed by the bounded baseline: {status.value}"
        )
    configured_canonical = _resolve_project_path(config.safety.current_canonical_path)
    if configured_canonical != CURRENT_CANONICAL_PATH.resolve():
        raise ScientificEntityEvidenceBuildError(
            "Configured current canonical path does not match the fixed safety boundary"
        )
    if input_path.resolve() == CURRENT_CANONICAL_PATH.resolve():
        raise ScientificEntityEvidenceBuildError(
            "Current canonical corpus input is forbidden in bounded baseline v0.1"
        )
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    fixture_path = _resolve_project_path(config.fixtures.default_input_path)
    if status == EntityEvidenceBuildStatus.FIXTURE and input_path.resolve() != fixture_path:
        raise ScientificEntityEvidenceBuildError(
            "fixture status is reserved for the tracked synthetic baseline fixture"
        )


def _build_mentions(
    *,
    documents: Sequence[CanonicalDocument],
    extractor: LiteralScientificEntityExtractor,
    build_id: str,
    extractor_fingerprint: str,
) -> list[ScientificEntityMentionEvidence]:
    records: list[ScientificEntityMentionEvidence] = []
    evidence_payloads: dict[str, dict[str, Any]] = {}
    mention_payloads: dict[str, dict[str, Any]] = {}

    for document in documents:
        values = {
            ScientificEntitySourceField.TITLE: document.title,
            ScientificEntitySourceField.ABSTRACT: document.abstract,
        }
        for source_field in extractor.config.matching.source_fields:
            source_text = values[source_field]
            if source_text is None or source_text == "":
                continue
            source_text_sha256 = sha256_text(source_text)
            candidates = extractor.extract(
                canonical_id=document.canonical_id,
                source_field=source_field,
                source_text=source_text,
            )
            for candidate in candidates:
                surface_text = source_text[candidate.char_start : candidate.char_end]
                mention_id = build_mention_id(
                    canonical_id=document.canonical_id,
                    source_field=source_field,
                    source_text_sha256=source_text_sha256,
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
                    source_text_sha256=source_text_sha256,
                    char_start=candidate.char_start,
                    char_end=candidate.char_end,
                    surface_text=surface_text,
                    extractor_fingerprint=extractor_fingerprint,
                    confidence_kind=ConfidenceKind.NOT_AVAILABLE,
                    confidence_score=None,
                    calibration_id=None,
                )
                payload = record.model_dump(mode="json")
                previous_evidence = evidence_payloads.get(record.evidence_id)
                if previous_evidence is not None and previous_evidence != payload:
                    raise ScientificEntityEvidenceBuildError(
                        f"Conflicting evidence_id collision: {record.evidence_id}"
                    )
                previous_mention = mention_payloads.get(record.mention_id)
                if previous_mention is not None and previous_mention != payload:
                    raise ScientificEntityEvidenceBuildError(
                        f"Conflicting mention_id collision: {record.mention_id}"
                    )
                if previous_evidence is None:
                    evidence_payloads[record.evidence_id] = payload
                    mention_payloads[record.mention_id] = payload
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
    return records


def _mentions_bytes(records: Sequence[ScientificEntityMentionEvidence]) -> bytes:
    rows = [
        _json_text(record.model_dump(mode="json"), compact=True)
        for record in records
    ]
    return (("\n".join(rows) + "\n") if rows else "").encode("utf-8")


def _overlap_counters(
    records: Sequence[ScientificEntityMentionEvidence],
) -> tuple[int, int]:
    grouped: dict[tuple[str, str], list[ScientificEntityMentionEvidence]] = {}
    for record in records:
        key = (record.canonical_id, record.source_field.value)
        grouped.setdefault(key, []).append(record)

    overlap_pairs = 0
    same_span_types: dict[tuple[str, str, int, int], set[str]] = {}
    for key, group in grouped.items():
        for index, left in enumerate(group):
            span_key = (key[0], key[1], left.char_start, left.char_end)
            same_span_types.setdefault(span_key, set()).add(left.entity_type.value)
            for right in group[index + 1 :]:
                if left.char_start < right.char_end and right.char_start < left.char_end:
                    overlap_pairs += 1
    same_span_multi_type_groups = sum(
        len(entity_types) > 1 for entity_types in same_span_types.values()
    )
    return overlap_pairs, same_span_multi_type_groups


def _build_quality_summary(
    *,
    build_id: str,
    status: EntityEvidenceBuildStatus,
    documents: Sequence[CanonicalDocument],
    records: Sequence[ScientificEntityMentionEvidence],
    max_documents: int,
    hard_max_documents: int,
) -> dict[str, Any]:
    entity_counts = Counter(record.entity_type.value for record in records)
    source_counts = Counter(record.source_field.value for record in records)
    documents_with_mentions = {record.canonical_id for record in records}
    overlap_pairs, same_span_groups = _overlap_counters(records)
    processed_source_text_count = sum(
        1
        for document in documents
        for value in (document.title, document.abstract)
        if value not in (None, "")
    )
    return {
        "schema_version": DATA_QUALITY_SCHEMA_VERSION,
        "build_id": build_id,
        "status": status.value,
        "bounded": True,
        "input_document_count": len(documents),
        "max_documents": max_documents,
        "hard_max_documents": hard_max_documents,
        "truncated": False,
        "processed_source_text_count": processed_source_text_count,
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
        "confidence_kind": ConfidenceKind.NOT_AVAILABLE.value,
        "canonical_truth_mutated": False,
        "may_be_used_as_reconcile_input": False,
        "publication_ready": False,
        "model_weights_downloaded": False,
        "provider_api_called": False,
        "full_corpus_processed": False,
    }


def _build_schema_payload() -> dict[str, Any]:
    return {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "mentions_schema_version": MENTION_SCHEMA_VERSION,
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "data_quality_schema_version": DATA_QUALITY_SCHEMA_VERSION,
        "serialization": {
            "encoding": "utf-8",
            "line_ending": "lf",
            "offset_unit": "unicode_codepoint",
            "offset_interval": "half_open",
        },
        "mentions_json_schema": ScientificEntityMentionEvidence.model_json_schema(),
        "manifest_json_schema": ScientificEntityEvidenceManifest.model_json_schema(),
    }


def _build_readme(
    *,
    build_id: str,
    status: EntityEvidenceBuildStatus,
    generated_at_utc: datetime,
    document_count: int,
    mention_count: int,
) -> str:
    lines = [
        "# Bounded Scientific Entity Evidence v0.1",
        "",
        "This directory contains deterministic candidate mention evidence emitted by",
        "the ML Research Radar literal/rule reference baseline.",
        "",
        "It is derived and rebuildable. It is not canonical paper truth, not a",
        "reconcile input, not a production NER model, and not a full-corpus build.",
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
        "## Files",
        "",
        "- `mentions.jsonl` — exact typed span evidence",
        "- `manifest.json` — canonical input and extractor provenance",
        "- `schema.json` — executable output schemas and serialization rules",
        "- `data_quality_summary.json` — bounded build counters and safety flags",
        "- `checksums.txt` — SHA-256 checksums for the files above and this README",
        "",
        "Any acceptance, model comparison, normalization, linking, runtime",
        "integration, or full-corpus generation requires a separate reviewed slice.",
    ]
    return "\n".join(lines) + "\n"


def _write_build_directory(
    *,
    output_dir: Path,
    mentions_bytes: bytes,
    manifest: ScientificEntityEvidenceManifest,
    schema_payload: Mapping[str, Any],
    quality_summary: Mapping[str, Any],
    readme: str,
) -> list[str]:
    output_root = output_dir.parent
    output_root.mkdir(parents=True, exist_ok=True)
    if output_dir.exists():
        raise FileExistsError(
            f"Immutable build directory already exists; overwrite is forbidden: {output_dir}"
        )

    staging = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.tmp-", dir=output_root)
    )
    try:
        (staging / "mentions.jsonl").write_bytes(mentions_bytes)
        _write_text_lf(
            staging / "manifest.json",
            _json_text(manifest.model_dump(mode="json")),
        )
        _write_text_lf(staging / "schema.json", _json_text(dict(schema_payload)))
        _write_text_lf(
            staging / "data_quality_summary.json",
            _json_text(dict(quality_summary)),
        )
        _write_text_lf(staging / "README.md", readme)
        checksum_lines = [
            f"{_sha256_file(staging / name)}  {name}" for name in CHECKSUM_FILES
        ]
        _write_text_lf(staging / "checksums.txt", "\n".join(checksum_lines) + "\n")
        staging.rename(output_dir)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return [*CHECKSUM_FILES, "checksums.txt"]


def build_baseline(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    input_path: Path | None = None,
    output_root: Path | None = None,
    build_id: str | None = None,
    status: EntityEvidenceBuildStatus | str = EntityEvidenceBuildStatus.FIXTURE,
    max_documents: int | None = None,
    execute: bool = False,
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    config_path = config_path.resolve()
    config = load_baseline_config(config_path)
    selected_input = _resolve_project_path(
        input_path or config.fixtures.default_input_path
    )
    selected_output_root = _resolve_project_path(output_root or config.outputs.root)
    selected_status = EntityEvidenceBuildStatus(status)
    if selected_status == EntityEvidenceBuildStatus.ACCEPTED:
        raise ScientificEntityEvidenceBuildError(
            "Bounded baseline v0.1 cannot emit accepted status"
        )
    selected_max_documents = (
        config.safety.default_max_documents
        if max_documents is None
        else max_documents
    )
    _validate_safe_input(
        config=config,
        input_path=selected_input,
        status=selected_status,
        max_documents=selected_max_documents,
    )

    documents, canonical_input_sha256 = _load_documents(
        selected_input,
        max_documents=selected_max_documents,
    )
    generated_at = generated_at_utc or _utc_now()
    if generated_at.tzinfo is None or generated_at.utcoffset() != timezone.utc.utcoffset(
        generated_at
    ):
        raise ScientificEntityEvidenceBuildError(
            "generated_at_utc must be timezone-aware UTC"
        )
    selected_build_id = build_id or _build_id(generated_at)

    config_sha256 = baseline_config_sha256(config)
    environment_lock = _resolve_project_path(config.extractor.environment_lock_path)
    if not environment_lock.is_file():
        raise FileNotFoundError(environment_lock)
    environment_sha256 = normalized_text_sha256(environment_lock)
    descriptor = build_rule_extractor_descriptor(
        config=config,
        config_sha256=config_sha256,
        environment_sha256=environment_sha256,
        code_revision=_source_bundle_revision(),
    )
    extractor_fingerprint = build_extractor_fingerprint(descriptor)
    extractor = LiteralScientificEntityExtractor(
        config=config,
        descriptor=descriptor,
    )
    records = _build_mentions(
        documents=documents,
        extractor=extractor,
        build_id=selected_build_id,
        extractor_fingerprint=extractor_fingerprint,
    )
    mentions_bytes = _mentions_bytes(records)
    mentions_sha256 = hashlib.sha256(mentions_bytes).hexdigest()
    canonical_input = ScientificEntityCanonicalInput(
        schema_version=CANONICAL_INPUT_SCHEMA_VERSION,
        path=_project_relative_or_absolute(selected_input),
        sha256=canonical_input_sha256,
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
        extractor_fingerprint=extractor_fingerprint,
        offset_unit="unicode_codepoint",
        offset_interval="half_open",
        source_fields=list(config.matching.source_fields),
        entity_types=list(ScientificEntityType),
        mentions_file="mentions.jsonl",
        mention_count=len(records),
        mentions_sha256=mentions_sha256,
        canonical_truth_mutated=False,
        may_be_used_as_reconcile_input=False,
        publication_ready=False,
    )
    quality_summary = _build_quality_summary(
        build_id=selected_build_id,
        status=selected_status,
        documents=documents,
        records=records,
        max_documents=selected_max_documents,
        hard_max_documents=config.safety.hard_max_documents,
    )
    schema_payload = _build_schema_payload()
    readme = _build_readme(
        build_id=selected_build_id,
        status=selected_status,
        generated_at_utc=generated_at,
        document_count=len(documents),
        mention_count=len(records),
    )
    output_dir = selected_output_root / selected_build_id
    if execute and output_dir.exists():
        raise FileExistsError(
            f"Immutable build directory already exists; overwrite is forbidden: {output_dir}"
        )

    written_files: list[str] = []
    if execute:
        written_files = _write_build_directory(
            output_dir=output_dir,
            mentions_bytes=mentions_bytes,
            manifest=manifest,
            schema_payload=schema_payload,
            quality_summary=quality_summary,
            readme=readme,
        )

    return {
        "schema_version": "bounded_scientific_entity_extractor_baseline_report_v0.1",
        "report": REPORT_NAME,
        "ok": True,
        "mode": "execute" if execute else "plan",
        "phase_complete": execute,
        "build_id": selected_build_id,
        "status": selected_status.value,
        "config_path": _normalize_path(config_path),
        "input_path": _normalize_path(selected_input),
        "output_dir": _normalize_path(output_dir),
        "max_documents": selected_max_documents,
        "hard_max_documents": config.safety.hard_max_documents,
        "input_document_count": len(documents),
        "mention_count": len(records),
        "canonical_input_sha256": canonical_input.sha256,
        "config_sha256": config_sha256,
        "environment_sha256": environment_sha256,
        "code_revision": descriptor.code_revision,
        "extractor_fingerprint": extractor_fingerprint,
        "mentions_sha256": mentions_sha256,
        "written_files": written_files,
        "canonical_truth_mutated": False,
        "full_corpus_processed": False,
        "model_weights_downloaded": False,
        "provider_api_called": False,
        "publication_ready": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Plan or execute the bounded deterministic Scientific Entity "
            "Extractor Baseline v0.1. Plan-only by default."
        )
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--build-id", default=None)
    parser.add_argument(
        "--status",
        choices=("fixture", "candidate"),
        default="fixture",
    )
    parser.add_argument("--max-documents", type=int, default=None)
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_baseline(
            config_path=args.config,
            input_path=args.input,
            output_root=args.output_root,
            build_id=args.build_id,
            status=args.status,
            max_documents=args.max_documents,
            execute=args.execute,
        )
    except (
        FileNotFoundError,
        OSError,
        ValueError,
        ScientificEntityBaselineError,
        ScientificEntityEvidenceBuildError,
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
    print(f"[OK] output_dir={report['output_dir']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
