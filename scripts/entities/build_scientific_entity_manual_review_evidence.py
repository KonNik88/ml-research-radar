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
from radar_core.contracts.scientific_entity_evaluation import (
    REVIEW_MANIFEST_SCHEMA_VERSION,
    ScientificEntityAnnotationMethod,
    ScientificEntityReviewManifest,
    ScientificEntityReviewStatus,
)
from radar_core.contracts.scientific_entity_evidence import (
    CANONICAL_INPUT_SCHEMA_VERSION,
    ScientificEntityCanonicalInput,
    ScientificEntitySourceField,
    ScientificEntityType,
)
from radar_core.contracts.scientific_entity_manual_review import (
    ANNOTATION_AUDIT_SCHEMA_VERSION,
    COMPLETION_MANIFEST_SCHEMA_VERSION,
    PREPARED_MANIFEST_SCHEMA_VERSION,
    ScientificEntityBlindAnnotationRow,
    ScientificEntityManualReviewCompletionManifest,
    ScientificEntityManualReviewPreparedManifest,
    ScientificEntityPreparedReviewInput,
    ScientificEntityReviewSampleStatus,
    ScientificEntitySampleStratum,
)
from radar_core.entities.scientific_entity_manual_review import (
    MANUAL_REVIEW_CODE_REVISION_PREFIX,
    DeterministicScientificEntitySampler,
    ScientificEntityManualReviewConfig,
    ScientificEntityManualReviewError,
    annotation_counts,
    build_annotation_template,
    build_reference_mentions,
    load_manual_review_config,
    manual_review_config_sha256,
    normalized_file_sha256,
    validate_completed_annotations,
)


REPORT_NAME = "bounded_scientific_entity_manual_review_evidence_v01"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = (
    PROJECT_ROOT / "configs" / "scientific_entity_manual_review_evidence_v0.1.yaml"
)
CURRENT_CANONICAL_PATH = (
    PROJECT_ROOT / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"
)
ENVIRONMENT_LOCK_PATH = PROJECT_ROOT / "requirements" / "requirements.core.lock.txt"
CODE_REVISION_FILES = (
    "radar_core/contracts/scientific_entity_evidence.py",
    "radar_core/contracts/scientific_entity_evaluation.py",
    "radar_core/contracts/scientific_entity_manual_review.py",
    "radar_core/entities/scientific_entity_manual_review.py",
    "scripts/entities/build_scientific_entity_manual_review_evidence.py",
)
PREPARED_CHECKSUM_FILES = (
    "canonical_documents.sample.jsonl",
    "sample_assignments.jsonl",
    "annotation_template.jsonl",
    "manifest.json",
    "data_quality_summary.json",
    "README.md",
)
COMPLETED_CHECKSUM_FILES = (
    "completed_annotations.jsonl",
    "review_manifest.json",
    "reference_mentions.jsonl",
    "completion_manifest.json",
    "annotation_audit_summary.json",
    "README.md",
)


class ScientificEntityManualReviewBuildError(RuntimeError):
    """Raised when bounded review evidence cannot be safely built."""


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


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    if not rows:
        return b""
    return "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
        for row in rows
    ).encode("utf-8")


def _write_text_lf(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _verify_checksum_file(
    *,
    directory: Path,
    expected_files: Sequence[str],
) -> None:
    checksum_path = directory / "checksums.txt"
    declared: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        checksum_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        parts = raw_line.split("  ", 1)
        if (
            len(parts) != 2
            or len(parts[0]) != 64
            or any(character not in "0123456789abcdef" for character in parts[0])
        ):
            raise ScientificEntityManualReviewBuildError(
                f"Invalid checksum row: {checksum_path}:{line_number}"
            )
        digest, filename = parts
        if filename in declared:
            raise ScientificEntityManualReviewBuildError(
                f"Duplicate checksum filename: {filename}"
            )
        declared[filename] = digest
    expected = set(expected_files)
    if set(declared) != expected:
        raise ScientificEntityManualReviewBuildError(
            "Prepared checksum filename set does not match the immutable layout"
        )
    for filename in expected_files:
        path = directory / filename
        if _sha256_file(path) != declared[filename]:
            raise ScientificEntityManualReviewBuildError(
                f"Prepared checksum mismatch: {filename}"
            )


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ScientificEntityManualReviewBuildError(f"Expected JSON object: {path}")
    return payload


def _read_jsonl(path: Path, *, hard_limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                raise ScientificEntityManualReviewBuildError(
                    f"Blank JSONL line is forbidden: {path}:{line_number}"
                )
            try:
                payload = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise ScientificEntityManualReviewBuildError(
                    f"Invalid JSON at {path}:{line_number}: {exc}"
                ) from exc
            if not isinstance(payload, dict):
                raise ScientificEntityManualReviewBuildError(
                    f"Expected JSON object: {path}:{line_number}"
                )
            rows.append(payload)
            if len(rows) > hard_limit:
                raise ScientificEntityManualReviewBuildError(
                    f"Input exceeds hard limit {hard_limit}; truncation is forbidden"
                )
    return rows


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _review_id(generated_at_utc: datetime) -> str:
    timestamp = generated_at_utc.strftime("%Y%m%dT%H%M%S%fZ")
    return f"scientific-entity-manual-review-v0.1-{timestamp}"


def _source_bundle_revision() -> str:
    digest = hashlib.sha256()
    for relative_path in sorted(CODE_REVISION_FILES):
        path = PROJECT_ROOT / relative_path
        if not path.is_file():
            raise ScientificEntityManualReviewBuildError(
                f"Code revision source file is missing: {path}"
            )
        normalized = path.read_text(encoding="utf-8")
        normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(normalized.encode("utf-8"))
        digest.update(b"\0")
    return f"{MANUAL_REVIEW_CODE_REVISION_PREFIX}{digest.hexdigest()}"


def _validate_prepare_paths(
    *,
    config: ScientificEntityManualReviewConfig,
    input_path: Path,
    status: ScientificEntityReviewSampleStatus,
    max_source_documents: int,
) -> None:
    if max_source_documents < 1:
        raise ScientificEntityManualReviewBuildError(
            "max_source_documents must be positive"
        )
    if max_source_documents > config.safety.hard_max_source_documents:
        raise ScientificEntityManualReviewBuildError(
            "max_source_documents exceeds configured hard limit"
        )
    configured_canonical = _resolve_project_path(config.safety.current_canonical_path)
    if configured_canonical != CURRENT_CANONICAL_PATH.resolve():
        raise ScientificEntityManualReviewBuildError(
            "Configured current canonical path does not match fixed safety boundary"
        )
    fixture_path = _resolve_project_path(config.fixtures.input_path)
    if status == ScientificEntityReviewSampleStatus.FIXTURE:
        if input_path.resolve() != fixture_path:
            raise ScientificEntityManualReviewBuildError(
                "fixture status is reserved for the tracked synthetic review fixture"
            )
    elif input_path.resolve() != CURRENT_CANONICAL_PATH.resolve():
        raise ScientificEntityManualReviewBuildError(
            "candidate sampling must read the fixed current canonical path"
        )
    if not input_path.is_file():
        raise FileNotFoundError(input_path)


def _scan_source(
    *,
    input_path: Path,
    sampler: DeterministicScientificEntitySampler,
    max_source_documents: int,
) -> tuple[int, str]:
    seen_ids: set[str] = set()
    digest = hashlib.sha256()
    document_count = 0
    with input_path.open("rb") as handle:
        for line_number, raw_bytes in enumerate(handle, start=1):
            digest.update(raw_bytes)
            document_count += 1
            if document_count > max_source_documents:
                raise ScientificEntityManualReviewBuildError(
                    "Source input exceeds max_source_documents; truncation is forbidden"
                )
            try:
                raw_line = raw_bytes.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ScientificEntityManualReviewBuildError(
                    f"Invalid UTF-8 at {input_path}:{line_number}: {exc}"
                ) from exc
            if not raw_line.strip():
                raise ScientificEntityManualReviewBuildError(
                    f"Blank JSONL line is forbidden: {input_path}:{line_number}"
                )
            try:
                payload = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise ScientificEntityManualReviewBuildError(
                    f"Invalid JSON at {input_path}:{line_number}: {exc}"
                ) from exc
            if not isinstance(payload, dict):
                raise ScientificEntityManualReviewBuildError(
                    f"Expected JSON object: {input_path}:{line_number}"
                )
            document = CanonicalDocument.model_validate(payload)
            if not document.canonical_id.strip():
                raise ScientificEntityManualReviewBuildError(
                    "canonical_id must contain non-whitespace text"
                )
            if document.canonical_id in seen_ids:
                raise ScientificEntityManualReviewBuildError(
                    f"Duplicate canonical_id: {document.canonical_id}"
                )
            seen_ids.add(document.canonical_id)
            sampler.consider(document=document, payload=payload)
    if document_count == 0:
        raise ScientificEntityManualReviewBuildError("Source JSONL is empty")
    return document_count, digest.hexdigest()


def _prepared_readme(
    *,
    review_id: str,
    status: ScientificEntityReviewSampleStatus,
    source_count: int,
    selected_count: int,
    uniform_count: int,
    type_enriched_count: int,
) -> str:
    return "\n".join(
        [
            "# Bounded Scientific Entity Manual Review — prepared evidence",
            "",
            "This immutable local package contains a deterministic bounded sample and",
            "a prediction-blind annotation template. It is derived review support.",
            "",
            "It is not canonical truth, not a reconcile input, not completed review,",
            "not extractor approval, and not publication-ready data.",
            "",
            "## Preparation",
            "",
            f"- review_id: `{review_id}`",
            f"- status: `{status.value}`",
            f"- scanned_source_document_count: `{source_count}`",
            f"- selected_document_count: `{selected_count}`",
            f"- uniform_document_count: `{uniform_count}`",
            f"- type_enriched_document_count: `{type_enriched_count}`",
            "- prediction_blind: `true`",
            "- review_complete: `false`",
            "",
            "## Human workflow",
            "",
            "Copy `annotation_template.jsonl` to a separate local working file.",
            "Annotate every title and abstract without opening extractor predictions.",
            "Set `annotation_complete=true` for every row, including zero-mention rows.",
            "Then run the explicit finalize command with an annotator identifier.",
            "",
            "Selection terms enrich sampling only. They are not reference annotations.",
            "Real-paper text and completed annotations must remain outside Git.",
            "",
        ]
    )


def _completed_readme(
    *,
    review_id: str,
    annotation_method: ScientificEntityAnnotationMethod,
    annotation_row_count: int,
    reference_count: int,
) -> str:
    return "\n".join(
        [
            "# Bounded Scientific Entity Manual Review — completed evidence",
            "",
            "This immutable local package contains completed prediction-blind reference",
            "annotations compatible with Scientific Entity Evaluation Harness v0.1.",
            "",
            f"- review_id: `{review_id}`",
            f"- annotation_method: `{annotation_method.value}`",
            f"- completed_annotation_row_count: `{annotation_row_count}`",
            f"- reference_mention_count: `{reference_count}`",
            "- prediction_blind: `true`",
            "- review_complete: `true`",
            "- evaluation_harness_ready: `true`",
            "",
            "This package does not select a production extractor, authorize full-corpus",
            "generation, mutate canonical truth, or authorize redistribution/publication.",
            "",
        ]
    )


def _write_immutable_directory(
    *,
    output_dir: Path,
    files: Mapping[str, bytes],
    checksum_files: Sequence[str],
) -> list[str]:
    output_root = output_dir.parent
    output_root.mkdir(parents=True, exist_ok=True)
    if output_dir.exists():
        raise FileExistsError(
            f"Immutable review directory already exists; overwrite is forbidden: {output_dir}"
        )
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.tmp-", dir=output_root)
    )
    try:
        for filename, value in files.items():
            (staging / filename).write_bytes(value)
        checksum_lines = [
            f"{_sha256_file(staging / filename)}  {filename}"
            for filename in checksum_files
        ]
        _write_text_lf(staging / "checksums.txt", "\n".join(checksum_lines) + "\n")
        staging.rename(output_dir)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return [*checksum_files, "checksums.txt"]


def prepare_manual_review_evidence(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    input_path: Path | None = None,
    output_root: Path | None = None,
    review_id: str | None = None,
    status: ScientificEntityReviewSampleStatus | str = ScientificEntityReviewSampleStatus.FIXTURE,
    max_source_documents: int | None = None,
    execute: bool = False,
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    resolved_config_path = config_path.resolve()
    config = load_manual_review_config(resolved_config_path)
    selected_status = ScientificEntityReviewSampleStatus(status)
    selected_input = _resolve_project_path(input_path or config.fixtures.input_path)
    selected_output_root = _resolve_project_path(
        output_root or config.outputs.prepared_root
    )
    selected_max_source_documents = (
        config.safety.default_max_source_documents
        if max_source_documents is None
        else max_source_documents
    )
    _validate_prepare_paths(
        config=config,
        input_path=selected_input,
        status=selected_status,
        max_source_documents=selected_max_source_documents,
    )

    generated_at = generated_at_utc or _utc_now()
    if generated_at.tzinfo is None or generated_at.utcoffset() != timezone.utc.utcoffset(
        generated_at
    ):
        raise ScientificEntityManualReviewBuildError(
            "generated_at_utc must be timezone-aware UTC"
        )
    selected_review_id = review_id or (
        config.fixtures.review_id
        if selected_status == ScientificEntityReviewSampleStatus.FIXTURE
        else _review_id(generated_at)
    )
    if selected_status == ScientificEntityReviewSampleStatus.FIXTURE:
        if selected_review_id != config.fixtures.review_id:
            raise ScientificEntityManualReviewBuildError(
                "fixture status requires the tracked fixture review_id"
            )
        policy = config.sampling.policy(
            uniform_document_count=config.fixtures.uniform_document_count,
            type_enriched_documents_per_type=(
                config.fixtures.type_enriched_documents_per_type
            ),
        )
    else:
        policy = config.sampling.policy()
    if policy.total_document_count > config.safety.hard_max_selected_documents:
        raise ScientificEntityManualReviewBuildError(
            "Requested sample exceeds hard selected-document limit"
        )

    sampler = DeterministicScientificEntitySampler(config=config, policy=policy)
    source_count, source_sha256 = _scan_source(
        input_path=selected_input,
        sampler=sampler,
        max_source_documents=selected_max_source_documents,
    )
    candidates, assignments = sampler.finalize(review_id=selected_review_id)
    annotation_rows = build_annotation_template(
        review_id=selected_review_id,
        candidates=candidates,
        assignments=assignments,
    )
    if len(annotation_rows) > config.safety.hard_max_annotation_rows:
        raise ScientificEntityManualReviewBuildError(
            "Annotation row count exceeds hard limit"
        )

    sample_bytes = _jsonl_bytes([candidate.payload for candidate in candidates])
    assignments_bytes = _jsonl_bytes(
        [row.model_dump(mode="json") for row in assignments]
    )
    template_bytes = _jsonl_bytes(
        [row.model_dump(mode="json") for row in annotation_rows]
    )
    output_dir = selected_output_root / selected_review_id
    sample_path = output_dir / "canonical_documents.sample.jsonl"
    assignment_counts = Counter(row.sample_stratum for row in assignments)
    type_counts = Counter(
        row.enrichment_entity_type
        for row in assignments
        if row.enrichment_entity_type is not None
    )

    manifest = ScientificEntityManualReviewPreparedManifest(
        schema_version=PREPARED_MANIFEST_SCHEMA_VERSION,
        review_id=selected_review_id,
        status=selected_status,
        generated_at_utc=generated_at,
        config_path=_project_relative_or_absolute(resolved_config_path),
        config_sha256=manual_review_config_sha256(config),
        code_revision=_source_bundle_revision(),
        environment_sha256=normalized_file_sha256(ENVIRONMENT_LOCK_PATH),
        source_canonical_input=ScientificEntityCanonicalInput(
            schema_version=CANONICAL_INPUT_SCHEMA_VERSION,
            path=_project_relative_or_absolute(selected_input),
            sha256=source_sha256,
            document_count=source_count,
            canonical_contract="CanonicalDocument",
        ),
        sample_canonical_input=ScientificEntityCanonicalInput(
            schema_version=CANONICAL_INPUT_SCHEMA_VERSION,
            path=_project_relative_or_absolute(sample_path),
            sha256=_sha256_bytes(sample_bytes),
            document_count=len(candidates),
            canonical_contract="CanonicalDocument",
        ),
        sampling_policy=policy,
        sample_assignments_file="sample_assignments.jsonl",
        sample_assignments_sha256=_sha256_bytes(assignments_bytes),
        annotation_template_file="annotation_template.jsonl",
        annotation_template_sha256=_sha256_bytes(template_bytes),
        annotation_row_count=len(annotation_rows),
        uniform_document_count=assignment_counts[
            ScientificEntitySampleStratum.UNIFORM
        ],
        type_enriched_document_count=assignment_counts[
            ScientificEntitySampleStratum.TYPE_ENRICHED
        ],
        type_enriched_count_by_type={
            entity_type: type_counts[entity_type]
            for entity_type in ScientificEntityType
        },
        prediction_blind=True,
        review_complete=False,
        selection_terms_are_reference_annotations=False,
        full_corpus_entity_extraction_performed=False,
        canonical_truth_mutated=False,
        may_be_used_as_reconcile_input=False,
        production_extractor_selected=False,
        redistribution_allowed=False,
        publication_ready=False,
    )
    manifest_bytes = _json_bytes(manifest.model_dump(mode="json"))
    quality = {
        "schema_version": "scientific_entity_manual_review_preparation_quality_v0.1",
        "review_id": selected_review_id,
        "status": selected_status.value,
        "scanned_source_document_count": source_count,
        "eligible_document_count": sampler.eligible_document_count,
        "selected_document_count": len(candidates),
        "annotation_row_count": len(annotation_rows),
        "uniform_document_count": manifest.uniform_document_count,
        "type_enriched_document_count": manifest.type_enriched_document_count,
        "type_enriched_count_by_type": {
            key.value: value for key, value in manifest.type_enriched_count_by_type.items()
        },
        "prediction_fields_present": False,
        "review_complete": False,
        "selection_terms_are_reference_annotations": False,
    }
    quality_bytes = _json_bytes(quality)
    readme = _prepared_readme(
        review_id=selected_review_id,
        status=selected_status,
        source_count=source_count,
        selected_count=len(candidates),
        uniform_count=manifest.uniform_document_count,
        type_enriched_count=manifest.type_enriched_document_count,
    )
    files = {
        "canonical_documents.sample.jsonl": sample_bytes,
        "sample_assignments.jsonl": assignments_bytes,
        "annotation_template.jsonl": template_bytes,
        "manifest.json": manifest_bytes,
        "data_quality_summary.json": quality_bytes,
        "README.md": readme.encode("utf-8"),
    }
    if execute and output_dir.exists():
        raise FileExistsError(
            f"Immutable review directory already exists; overwrite is forbidden: {output_dir}"
        )
    written_files: list[str] = []
    if execute:
        written_files = _write_immutable_directory(
            output_dir=output_dir,
            files=files,
            checksum_files=PREPARED_CHECKSUM_FILES,
        )

    return {
        "schema_version": "scientific_entity_manual_review_prepare_report_v0.1",
        "report": REPORT_NAME,
        "phase": "prepare",
        "ok": True,
        "mode": "execute" if execute else "plan",
        "phase_complete": execute,
        "review_id": selected_review_id,
        "status": selected_status.value,
        "source_document_count": source_count,
        "eligible_document_count": sampler.eligible_document_count,
        "sample_document_count": len(candidates),
        "uniform_document_count": manifest.uniform_document_count,
        "type_enriched_document_count": manifest.type_enriched_document_count,
        "annotation_row_count": len(annotation_rows),
        "output_dir": _normalize_path(output_dir),
        "written_files": written_files,
        "prediction_blind": True,
        "review_complete": False,
        "canonical_truth_mutated": False,
        "full_corpus_entity_extraction_performed": False,
        "publication_ready": False,
        "next_action": "complete_prediction_blind_annotation",
    }


def _load_prepared_manifest(
    prepared_dir: Path,
) -> ScientificEntityManualReviewPreparedManifest:
    path = prepared_dir / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(path)
    manifest = ScientificEntityManualReviewPreparedManifest.model_validate(
        _read_json(path)
    )
    expected = {
        "canonical_documents.sample.jsonl",
        "sample_assignments.jsonl",
        "annotation_template.jsonl",
        "manifest.json",
        "data_quality_summary.json",
        "README.md",
        "checksums.txt",
    }
    actual = {path.name for path in prepared_dir.iterdir() if path.is_file()}
    if actual != expected:
        raise ScientificEntityManualReviewBuildError(
            f"Prepared directory layout mismatch; expected={sorted(expected)}, actual={sorted(actual)}"
        )
    _verify_checksum_file(
        directory=prepared_dir,
        expected_files=PREPARED_CHECKSUM_FILES,
    )
    for filename in sorted(expected):
        data = (prepared_dir / filename).read_bytes()
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ScientificEntityManualReviewBuildError(
                f"Prepared text file is not UTF-8: {filename}"
            ) from exc
        if (
            not data
            or data.startswith(b"\xef\xbb\xbf")
            or b"\r" in data
            or not data.endswith(b"\n")
        ):
            raise ScientificEntityManualReviewBuildError(
                f"Prepared text file is not canonical LF UTF-8: {filename}"
            )
    if _sha256_file(prepared_dir / "canonical_documents.sample.jsonl") != (
        manifest.sample_canonical_input.sha256
    ):
        raise ScientificEntityManualReviewBuildError(
            "Prepared sample SHA-256 does not match manifest"
        )
    if _sha256_file(prepared_dir / "sample_assignments.jsonl") != (
        manifest.sample_assignments_sha256
    ):
        raise ScientificEntityManualReviewBuildError(
            "Prepared assignment SHA-256 does not match manifest"
        )
    if _sha256_file(prepared_dir / "annotation_template.jsonl") != (
        manifest.annotation_template_sha256
    ):
        raise ScientificEntityManualReviewBuildError(
            "Prepared annotation template SHA-256 does not match manifest"
        )
    return manifest


def finalize_manual_review_evidence(
    *,
    prepared_dir: Path,
    annotations_path: Path,
    annotator_ids: Sequence[str],
    config_path: Path = DEFAULT_CONFIG_PATH,
    output_root: Path | None = None,
    annotation_method: ScientificEntityAnnotationMethod | str = (
        ScientificEntityAnnotationMethod.MANUAL_INDEPENDENT
    ),
    execute: bool = False,
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    resolved_config_path = config_path.resolve()
    config = load_manual_review_config(resolved_config_path)
    selected_prepared_dir = _resolve_project_path(prepared_dir)
    selected_annotations = _resolve_project_path(annotations_path)
    selected_output_root = _resolve_project_path(
        output_root or config.outputs.completed_root
    )
    if not selected_prepared_dir.is_dir():
        raise FileNotFoundError(selected_prepared_dir)
    if not selected_annotations.is_file():
        raise FileNotFoundError(selected_annotations)
    normalized_annotators = [value.strip() for value in annotator_ids]
    if not normalized_annotators or any(not value for value in normalized_annotators):
        raise ScientificEntityManualReviewBuildError(
            "At least one non-empty annotator_id is required"
        )
    if len(set(normalized_annotators)) != len(normalized_annotators):
        raise ScientificEntityManualReviewBuildError(
            "annotator_ids must not contain duplicates"
        )
    selected_method = ScientificEntityAnnotationMethod(annotation_method)
    if selected_method not in {
        ScientificEntityAnnotationMethod.MANUAL_INDEPENDENT,
        ScientificEntityAnnotationMethod.MANUAL_ADJUDICATED,
    }:
        raise ScientificEntityManualReviewBuildError(
            "Finalized review requires a manual annotation method"
        )

    prepared_manifest = _load_prepared_manifest(selected_prepared_dir)
    if _resolve_project_path(prepared_manifest.config_path) != resolved_config_path:
        raise ScientificEntityManualReviewBuildError(
            "Prepared review config path does not match finalize config"
        )
    if prepared_manifest.config_sha256 != manual_review_config_sha256(config):
        raise ScientificEntityManualReviewBuildError(
            "Prepared review semantic config does not match finalize config"
        )
    if prepared_manifest.code_revision != _source_bundle_revision():
        raise ScientificEntityManualReviewBuildError(
            "Prepared review code revision does not match current finalize code"
        )
    if prepared_manifest.environment_sha256 != normalized_file_sha256(
        ENVIRONMENT_LOCK_PATH
    ):
        raise ScientificEntityManualReviewBuildError(
            "Prepared review dependency environment does not match current lock"
        )
    template_payloads = _read_jsonl(
        selected_prepared_dir / "annotation_template.jsonl",
        hard_limit=config.safety.hard_max_annotation_rows,
    )
    completed_payloads = _read_jsonl(
        selected_annotations,
        hard_limit=config.safety.hard_max_annotation_rows,
    )
    template_rows = [
        ScientificEntityBlindAnnotationRow.model_validate(row)
        for row in template_payloads
    ]
    completed_rows = [
        ScientificEntityBlindAnnotationRow.model_validate(row)
        for row in completed_payloads
    ]
    validate_completed_annotations(
        template_rows=template_rows,
        completed_rows=completed_rows,
    )
    if any(row.review_id != prepared_manifest.review_id for row in completed_rows):
        raise ScientificEntityManualReviewBuildError(
            "Completed annotation review_id does not match prepared manifest"
        )
    completed_rows = sorted(
        completed_rows,
        key=lambda row: (
            row.canonical_id,
            list(ScientificEntitySourceField).index(row.source_field),
        ),
    )
    completed_annotations_bytes = _jsonl_bytes(
        [row.model_dump(mode="json") for row in completed_rows]
    )

    references = build_reference_mentions(
        review_id=prepared_manifest.review_id,
        completed_rows=completed_rows,
        annotation_method=selected_method,
        annotation_pass=config.annotation.annotation_passes,
    )
    if len(references) > config.safety.hard_max_reference_mentions:
        raise ScientificEntityManualReviewBuildError(
            "Reference mention count exceeds hard limit"
        )
    reference_bytes = _jsonl_bytes(
        [row.model_dump(mode="json") for row in references]
    )
    generated_at = generated_at_utc or _utc_now()
    if generated_at.tzinfo is None or generated_at.utcoffset() != timezone.utc.utcoffset(
        generated_at
    ):
        raise ScientificEntityManualReviewBuildError(
            "generated_at_utc must be timezone-aware UTC"
        )
    review_manifest = ScientificEntityReviewManifest(
        schema_version=REVIEW_MANIFEST_SCHEMA_VERSION,
        review_id=prepared_manifest.review_id,
        status=ScientificEntityReviewStatus.REVIEWED_CANDIDATE,
        generated_at_utc=generated_at,
        canonical_input=prepared_manifest.sample_canonical_input,
        annotation_method=selected_method,
        annotation_guideline_version=config.annotation.guideline_version,
        annotation_passes=config.annotation.annotation_passes,
        annotator_ids=normalized_annotators,
        prediction_blind=True,
        review_complete=True,
        source_fields=list(ScientificEntitySourceField),
        entity_types=list(ScientificEntityType),
        reference_mentions_file="reference_mentions.jsonl",
        reference_mention_count=len(references),
        reference_mentions_sha256=_sha256_bytes(reference_bytes),
        canonical_truth_mutated=False,
        may_be_used_as_reconcile_input=False,
        redistribution_allowed=False,
        publication_ready=False,
    )
    review_manifest_bytes = _json_bytes(review_manifest.model_dump(mode="json"))
    by_type, by_stratum, uncertain_count = annotation_counts(
        completed_rows=completed_rows
    )
    audit = {
        "schema_version": ANNOTATION_AUDIT_SCHEMA_VERSION,
        "review_id": prepared_manifest.review_id,
        "prediction_blind": True,
        "review_complete": True,
        "annotation_row_count": len(completed_rows),
        "completed_annotation_row_count": sum(
            int(row.annotation_complete) for row in completed_rows
        ),
        "zero_mention_annotation_row_count": sum(
            int(not row.mentions) for row in completed_rows
        ),
        "reference_mention_count": len(references),
        "uncertain_reference_mention_count": uncertain_count,
        "reference_count_by_type": {
            entity_type.value: by_type[entity_type]
            for entity_type in ScientificEntityType
        },
        "reference_count_by_stratum": {
            stratum.value: by_stratum[stratum]
            for stratum in ScientificEntitySampleStratum
        },
        "automatic_review_approval": False,
        "production_extractor_selected": False,
        "publication_ready": False,
    }
    audit_bytes = _json_bytes(audit)
    output_dir = selected_output_root / prepared_manifest.review_id
    immutable_annotations_path = output_dir / "completed_annotations.jsonl"
    completion_manifest = ScientificEntityManualReviewCompletionManifest(
        schema_version=COMPLETION_MANIFEST_SCHEMA_VERSION,
        review_id=prepared_manifest.review_id,
        generated_at_utc=generated_at,
        prepared_review=ScientificEntityPreparedReviewInput(
            review_id=prepared_manifest.review_id,
            status=prepared_manifest.status,
            directory_path=_project_relative_or_absolute(selected_prepared_dir),
            manifest_path=_project_relative_or_absolute(
                selected_prepared_dir / "manifest.json"
            ),
            manifest_sha256=_sha256_file(selected_prepared_dir / "manifest.json"),
            sample_documents_path=_project_relative_or_absolute(
                selected_prepared_dir / "canonical_documents.sample.jsonl"
            ),
            sample_documents_sha256=prepared_manifest.sample_canonical_input.sha256,
            sample_document_count=prepared_manifest.sample_canonical_input.document_count,
            sample_assignments_path=_project_relative_or_absolute(
                selected_prepared_dir / "sample_assignments.jsonl"
            ),
            sample_assignments_sha256=prepared_manifest.sample_assignments_sha256,
            annotation_template_path=_project_relative_or_absolute(
                selected_prepared_dir / "annotation_template.jsonl"
            ),
            annotation_template_sha256=prepared_manifest.annotation_template_sha256,
        ),
        annotations_file="completed_annotations.jsonl",
        annotations_path=_project_relative_or_absolute(immutable_annotations_path),
        annotations_sha256=_sha256_bytes(completed_annotations_bytes),
        annotation_row_count=len(completed_rows),
        annotation_method=selected_method,
        annotation_guideline_version=config.annotation.guideline_version,
        annotation_passes=1,
        annotator_ids=normalized_annotators,
        review_status=ScientificEntityReviewStatus.REVIEWED_CANDIDATE,
        review_manifest_file="review_manifest.json",
        review_manifest_sha256=_sha256_bytes(review_manifest_bytes),
        reference_mentions_file="reference_mentions.jsonl",
        reference_mentions_sha256=_sha256_bytes(reference_bytes),
        reference_mention_count=len(references),
        annotation_audit_file="annotation_audit_summary.json",
        annotation_audit_sha256=_sha256_bytes(audit_bytes),
        completed_annotation_row_count=len(completed_rows),
        uncertain_reference_mention_count=uncertain_count,
        reference_count_by_type=by_type,
        reference_count_by_stratum=by_stratum,
        fixture_simulation=(
            prepared_manifest.status == ScientificEntityReviewSampleStatus.FIXTURE
        ),
        prediction_blind=True,
        review_complete=True,
        evaluation_harness_ready=True,
        automatic_review_approval=False,
        production_extractor_selected=False,
        full_corpus_build_authorized=False,
        canonical_truth_mutated=False,
        may_be_used_as_reconcile_input=False,
        redistribution_allowed=False,
        publication_ready=False,
    )
    completion_bytes = _json_bytes(completion_manifest.model_dump(mode="json"))
    readme = _completed_readme(
        review_id=prepared_manifest.review_id,
        annotation_method=selected_method,
        annotation_row_count=len(completed_rows),
        reference_count=len(references),
    )
    files = {
        "completed_annotations.jsonl": completed_annotations_bytes,
        "review_manifest.json": review_manifest_bytes,
        "reference_mentions.jsonl": reference_bytes,
        "completion_manifest.json": completion_bytes,
        "annotation_audit_summary.json": audit_bytes,
        "README.md": readme.encode("utf-8"),
    }
    if execute and output_dir.exists():
        raise FileExistsError(
            f"Immutable review directory already exists; overwrite is forbidden: {output_dir}"
        )
    written_files: list[str] = []
    if execute:
        written_files = _write_immutable_directory(
            output_dir=output_dir,
            files=files,
            checksum_files=COMPLETED_CHECKSUM_FILES,
        )

    return {
        "schema_version": "scientific_entity_manual_review_finalize_report_v0.1",
        "report": REPORT_NAME,
        "phase": "finalize",
        "ok": True,
        "mode": "execute" if execute else "plan",
        "phase_complete": execute,
        "review_id": prepared_manifest.review_id,
        "prepared_status": prepared_manifest.status.value,
        "review_status": ScientificEntityReviewStatus.REVIEWED_CANDIDATE.value,
        "annotation_method": selected_method.value,
        "annotation_row_count": len(completed_rows),
        "reference_mention_count": len(references),
        "uncertain_reference_mention_count": uncertain_count,
        "output_dir": _normalize_path(output_dir),
        "written_files": written_files,
        "prediction_blind": True,
        "review_complete": True,
        "evaluation_harness_ready": True,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "canonical_truth_mutated": False,
        "publication_ready": False,
        "next_action": "build_candidate_predictions_then_run_evaluation_harness",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare or finalize bounded prediction-blind Scientific Entity "
            "Manual Review Evidence v0.1. Plan-only by default."
        )
    )
    subparsers = parser.add_subparsers(dest="phase", required=True)

    prepare = subparsers.add_parser("prepare", help="Prepare bounded blind review package")
    prepare.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    prepare.add_argument("--input", type=Path, default=None)
    prepare.add_argument("--output-root", type=Path, default=None)
    prepare.add_argument("--review-id", default=None)
    prepare.add_argument("--status", choices=("fixture", "candidate"), default="fixture")
    prepare.add_argument("--max-source-documents", type=int, default=None)
    prepare.add_argument("--execute", action="store_true")

    finalize = subparsers.add_parser(
        "finalize", help="Finalize completed blind annotations for evaluation"
    )
    finalize.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    finalize.add_argument("--prepared-dir", type=Path, required=True)
    finalize.add_argument("--annotations", type=Path, required=True)
    finalize.add_argument("--annotator-id", action="append", required=True)
    finalize.add_argument(
        "--annotation-method",
        choices=("manual_independent", "manual_adjudicated"),
        default="manual_independent",
    )
    finalize.add_argument("--output-root", type=Path, default=None)
    finalize.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.phase == "prepare":
            report = prepare_manual_review_evidence(
                config_path=args.config,
                input_path=args.input,
                output_root=args.output_root,
                review_id=args.review_id,
                status=args.status,
                max_source_documents=args.max_source_documents,
                execute=args.execute,
            )
        else:
            report = finalize_manual_review_evidence(
                config_path=args.config,
                prepared_dir=args.prepared_dir,
                annotations_path=args.annotations,
                annotator_ids=args.annotator_id,
                output_root=args.output_root,
                annotation_method=args.annotation_method,
                execute=args.execute,
            )
    except (
        FileNotFoundError,
        OSError,
        ValueError,
        ScientificEntityManualReviewError,
        ScientificEntityManualReviewBuildError,
    ) as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] phase={args.phase}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 1

    print(f"[OK] report={REPORT_NAME}")
    print(f"[OK] phase={report['phase']}")
    print(f"[OK] mode={report['mode']}")
    print(f"[OK] phase_complete={report['phase_complete']}")
    print(f"[OK] review_id={report['review_id']}")
    if report["phase"] == "prepare":
        print(f"[OK] sample_document_count={report['sample_document_count']}")
        print(f"[OK] uniform_document_count={report['uniform_document_count']}")
        print(
            "[OK] type_enriched_document_count="
            f"{report['type_enriched_document_count']}"
        )
    else:
        print(f"[OK] annotation_row_count={report['annotation_row_count']}")
        print(f"[OK] reference_mention_count={report['reference_mention_count']}")
        print(f"[OK] evaluation_harness_ready={report['evaluation_harness_ready']}")
    print(f"[OK] output_dir={report['output_dir']}")
    print(f"[OK] next_action={report['next_action']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
