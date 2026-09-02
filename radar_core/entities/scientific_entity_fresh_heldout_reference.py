from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

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
from radar_core.contracts.scientific_entity_fresh_heldout_reference import (
    AUDIT_SCHEMA_VERSION,
    COMPLETION_MANIFEST_SCHEMA_VERSION,
    ScientificEntityFreshHeldoutReferenceCompletionManifest,
    ScientificEntityFreshHeldoutReferenceError,
    load_scientific_entity_fresh_heldout_reference_config,
)
from radar_core.contracts.scientific_entity_fresh_heldout_sample import (
    FreshHeldoutSampleManifest,
)
from radar_core.contracts.scientific_entity_manual_review import (
    ScientificEntityBlindAnnotationRow,
)
from radar_core.entities.scientific_entity_fresh_heldout_sample import (
    sha256_file,
    validate_fresh_heldout_sample,
)
from radar_core.entities.scientific_entity_manual_review import (
    annotation_counts,
    build_reference_mentions,
    validate_completed_annotations,
)


REPORT_NAME = "scientific_entity_fresh_heldout_reference_v02"
FROZEN_FILES = {
    "completed_annotations.jsonl",
    "review_manifest.json",
    "reference_mentions.jsonl",
    "completion_manifest.json",
    "annotation_audit_summary.json",
    "README.md",
    "checksums.txt",
}
CHECKSUM_FILES = FROZEN_FILES - {"checksums.txt"}


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        + b"\n"
    )


def _jsonl_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(
        json.dumps(
            dict(row),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
        for row in rows
    )


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ScientificEntityFreshHeldoutReferenceError(
            f"Expected JSON object: {path}"
        )
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                raise ScientificEntityFreshHeldoutReferenceError(
                    f"Blank JSONL line: {path}:{line_number}"
                )
            payload = json.loads(raw_line)
            if not isinstance(payload, dict):
                raise ScientificEntityFreshHeldoutReferenceError(
                    f"Expected JSON object: {path}:{line_number}"
                )
            rows.append(payload)
    return rows


def _selected_ids_sha256(ids: Sequence[str]) -> str:
    payload = ("\n".join(sorted(ids)) + "\n").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _normalize_annotator_ids(values: Sequence[str]) -> list[str]:
    normalized = [value.strip() for value in values]
    if not normalized or any(not value for value in normalized):
        raise ScientificEntityFreshHeldoutReferenceError(
            "at least one non-blank annotator_id is required"
        )
    if len(set(normalized)) != len(normalized):
        raise ScientificEntityFreshHeldoutReferenceError(
            "annotator_id values must be unique"
        )
    return normalized


def _validate_sample_identity(
    *,
    project_root: Path,
    config_path: Path,
    sample_dir: Path,
    canonical_path: Path,
    development_package_dir: Path,
):
    config = load_scientific_entity_fresh_heldout_reference_config(config_path)
    sample_dir = sample_dir.resolve()
    manifest = FreshHeldoutSampleManifest.model_validate(
        _read_json(sample_dir / "manifest.json")
    )
    if manifest.sample_id != config.sample.sample_id:
        raise ScientificEntityFreshHeldoutReferenceError(
            "sample_id does not match frozen reference-freeze config"
        )
    if manifest.review_id != config.sample.review_id:
        raise ScientificEntityFreshHeldoutReferenceError(
            "review_id does not match frozen reference-freeze config"
        )
    if manifest.selected_document_count != config.sample.expected_document_count:
        raise ScientificEntityFreshHeldoutReferenceError("sample document count drifted")
    if manifest.annotation_row_count != config.sample.expected_annotation_row_count:
        raise ScientificEntityFreshHeldoutReferenceError("sample annotation row count drifted")
    if manifest.heldout_development_overlap_count != 0:
        raise ScientificEntityFreshHeldoutReferenceError(
            "held-out/development overlap must remain zero"
        )
    selected_sha = _selected_ids_sha256(manifest.selected_canonical_ids)
    if selected_sha != config.sample.selected_canonical_ids_sha256:
        raise ScientificEntityFreshHeldoutReferenceError(
            "selected canonical ID set does not match frozen sample identity"
        )

    checks, summary = validate_fresh_heldout_sample(
        project_root=project_root,
        config_path=project_root / "configs" / "scientific_entity_fresh_heldout_gate_v0.2.yaml",
        canonical_path=canonical_path,
        development_package_dir=development_package_dir,
        sample_dir=sample_dir,
    )
    if any(not ok for _, ok, _ in checks) or summary["required_failed_count"] != 0:
        raise ScientificEntityFreshHeldoutReferenceError(
            "independent fresh held-out sample validation failed"
        )
    return config, manifest, selected_sha, summary


def prepare_annotation_working_copy(
    *,
    project_root: Path,
    config_path: Path,
    sample_dir: Path,
    canonical_path: Path,
    development_package_dir: Path,
    output_root: Path | None = None,
    execute: bool = False,
) -> dict[str, Any]:
    config, manifest, selected_sha, _ = _validate_sample_identity(
        project_root=project_root.resolve(),
        config_path=config_path.resolve(),
        sample_dir=sample_dir.resolve(),
        canonical_path=canonical_path.resolve(),
        development_package_dir=development_package_dir.resolve(),
    )
    blank_path = sample_dir.resolve() / "annotations_working.jsonl"
    blank_rows = [
        ScientificEntityBlindAnnotationRow.model_validate(row)
        for row in _read_jsonl(blank_path)
    ]
    if len(blank_rows) != config.sample.expected_annotation_row_count:
        raise ScientificEntityFreshHeldoutReferenceError("blank annotation row count drifted")
    if any(row.annotation_complete or row.mentions for row in blank_rows):
        raise ScientificEntityFreshHeldoutReferenceError(
            "sample blank annotation template is no longer blank"
        )

    root = (
        output_root.resolve()
        if output_root is not None
        else (project_root / config.working_copy.root).resolve()
    )
    output_dir = root / config.sample.review_id
    if execute and output_dir.exists():
        raise FileExistsError(
            f"annotation working copy already exists; overwrite forbidden: {output_dir}"
        )

    annotation_bytes = blank_path.read_bytes()
    readme = (
        "# Fresh v0.2 prediction-blind annotation working copy\n\n"
        f"Review ID: `{config.sample.review_id}`\n\n"
        "This directory is mutable working state, not frozen evidence.\n"
        "Edit `annotations_completed.jsonl` only. Keep every immutable source field unchanged.\n"
        "For each title/abstract row set `annotation_complete=true` after review and add manual mentions.\n"
        "Do not inspect or run v0.2c predictions before reference freeze.\n\n"
        f"Frozen selected canonical IDs SHA-256: `{selected_sha}`\n"
    ).encode("utf-8")

    if execute:
        output_dir.mkdir(parents=True, exist_ok=False)
        (output_dir / config.working_copy.filename).write_bytes(annotation_bytes)
        (output_dir / config.working_copy.readme_filename).write_bytes(readme)

    return {
        "report": REPORT_NAME,
        "mode": "execute" if execute else "plan",
        "phase_complete": execute,
        "sample_id": manifest.sample_id,
        "review_id": manifest.review_id,
        "annotation_row_count": len(blank_rows),
        "blank_annotations_sha256": sha256_file(blank_path),
        "selected_canonical_ids_sha256": selected_sha,
        "working_copy_is_mutable_non_evidence": True,
        "prediction_blind": True,
        "model_inference_executed": False,
        "evaluation_executed": False,
        "output_dir": str(output_dir).replace("\\", "/"),
        "next_slice": "complete_prediction_blind_manual_annotations",
    }


def _compute_frozen_reference(
    *,
    project_root: Path,
    config_path: Path,
    sample_dir: Path,
    canonical_path: Path,
    development_package_dir: Path,
    annotations_path: Path,
    annotator_ids: Sequence[str],
    generated_at_utc: datetime,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    config, sample_manifest, selected_sha, sample_summary = _validate_sample_identity(
        project_root=project_root.resolve(),
        config_path=config_path.resolve(),
        sample_dir=sample_dir.resolve(),
        canonical_path=canonical_path.resolve(),
        development_package_dir=development_package_dir.resolve(),
    )
    if generated_at_utc.tzinfo is None or generated_at_utc.utcoffset() != timezone.utc.utcoffset(generated_at_utc):
        raise ScientificEntityFreshHeldoutReferenceError(
            "generated_at_utc must be timezone-aware UTC"
        )

    sample_dir = sample_dir.resolve()
    annotations_path = annotations_path.resolve()
    blank_path = sample_dir / "annotations_working.jsonl"
    sample_path = sample_dir / "canonical_documents.sample.jsonl"
    assignments_path = sample_dir / "sample_assignments.jsonl"
    manifest_path = sample_dir / "manifest.json"

    if not annotations_path.is_file():
        raise FileNotFoundError(annotations_path)

    blank_rows = [
        ScientificEntityBlindAnnotationRow.model_validate(row)
        for row in _read_jsonl(blank_path)
    ]
    completed_rows = [
        ScientificEntityBlindAnnotationRow.model_validate(row)
        for row in _read_jsonl(annotations_path)
    ]
    if len(completed_rows) != config.sample.expected_annotation_row_count:
        raise ScientificEntityFreshHeldoutReferenceError(
            "completed annotation row count must remain exactly 96"
        )
    validate_completed_annotations(
        template_rows=blank_rows,
        completed_rows=completed_rows,
    )
    if any(row.review_id != config.sample.review_id for row in completed_rows):
        raise ScientificEntityFreshHeldoutReferenceError(
            "completed annotation review_id drifted"
        )

    normalized_annotators = _normalize_annotator_ids(annotator_ids)
    completed_rows = sorted(
        completed_rows,
        key=lambda row: (
            row.canonical_id,
            list(ScientificEntitySourceField).index(row.source_field),
        ),
    )
    references = build_reference_mentions(
        review_id=config.sample.review_id,
        completed_rows=completed_rows,
        annotation_method=ScientificEntityAnnotationMethod.MANUAL_ADJUDICATED,
        annotation_pass=config.annotation.annotation_passes,
    )
    by_type, by_stratum, uncertain_count = annotation_counts(
        completed_rows=completed_rows
    )
    if uncertain_count != 0:
        raise ScientificEntityFreshHeldoutReferenceError(
            f"reference freeze requires zero uncertain mentions; actual={uncertain_count}"
        )
    minimum = config.annotation.minimum_reference_mentions_per_type
    inadequate = {
        entity_type.value: by_type[entity_type]
        for entity_type in ScientificEntityType
        if by_type[entity_type] < minimum
    }
    if inadequate:
        raise ScientificEntityFreshHeldoutReferenceError(
            f"reference adequacy failed; minimum={minimum}, counts={inadequate}"
        )
    if len(references) > config.annotation.maximum_reference_mentions_total:
        raise ScientificEntityFreshHeldoutReferenceError(
            "reference mention count exceeds frozen safety maximum"
        )

    completed_bytes = _jsonl_bytes(
        [row.model_dump(mode="json") for row in completed_rows]
    )
    reference_bytes = _jsonl_bytes(
        [row.model_dump(mode="json") for row in references]
    )

    canonical_input = ScientificEntityCanonicalInput(
        schema_version=CANONICAL_INPUT_SCHEMA_VERSION,
        path=str(sample_path).replace("\\", "/"),
        sha256=sha256_file(sample_path),
        document_count=config.sample.expected_document_count,
        canonical_contract="CanonicalDocument",
    )
    review_manifest = ScientificEntityReviewManifest(
        schema_version=REVIEW_MANIFEST_SCHEMA_VERSION,
        review_id=config.sample.review_id,
        status=ScientificEntityReviewStatus.REVIEWED_CANDIDATE,
        generated_at_utc=generated_at_utc,
        canonical_input=canonical_input,
        annotation_method=ScientificEntityAnnotationMethod.MANUAL_ADJUDICATED,
        annotation_guideline_version=config.annotation.annotation_guideline_version,
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

    audit = {
        "schema_version": AUDIT_SCHEMA_VERSION,
        "sample_id": config.sample.sample_id,
        "review_id": config.sample.review_id,
        "prediction_blind": True,
        "sample_independent_validation_passed": True,
        "heldout_development_overlap_count": 0,
        "document_count": 48,
        "annotation_row_count": 96,
        "completed_annotation_row_count": sum(
            int(row.annotation_complete) for row in completed_rows
        ),
        "zero_mention_annotation_row_count": sum(
            int(not row.mentions) for row in completed_rows
        ),
        "reference_mention_count": len(references),
        "uncertain_reference_mention_count": uncertain_count,
        "minimum_reference_mentions_per_type": minimum,
        "reference_count_by_type": {
            entity_type.value: by_type[entity_type]
            for entity_type in ScientificEntityType
        },
        "reference_count_by_stratum": {
            stratum.value: count for stratum, count in by_stratum.items()
        },
        "reference_adequacy_passed": True,
        "candidate_predictions_visible_during_annotation": False,
        "model_inference_executed": False,
        "evaluation_executed": False,
        "automatic_review_approval": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "canonical_truth_mutated": False,
        "publication_ready": False,
    }
    audit_bytes = _json_bytes(audit)

    completion_manifest = ScientificEntityFreshHeldoutReferenceCompletionManifest(
        schema_version=COMPLETION_MANIFEST_SCHEMA_VERSION,
        sample_id=config.sample.sample_id,
        review_id=config.sample.review_id,
        generated_at_utc=generated_at_utc,
        review_status=ScientificEntityReviewStatus.REVIEWED_CANDIDATE,
        annotation_method=ScientificEntityAnnotationMethod.MANUAL_ADJUDICATED,
        annotation_guideline_version=config.annotation.annotation_guideline_version,
        annotation_passes=1,
        annotator_ids=normalized_annotators,
        sample_manifest_file="manifest.json",
        sample_manifest_sha256=sha256_file(manifest_path),
        blank_annotations_file="annotations_working.jsonl",
        blank_annotations_sha256=sha256_file(blank_path),
        completed_annotations_file="completed_annotations.jsonl",
        completed_annotations_sha256=_sha256_bytes(completed_bytes),
        canonical_sample_file="canonical_documents.sample.jsonl",
        canonical_sample_sha256=sha256_file(sample_path),
        sample_assignments_file="sample_assignments.jsonl",
        sample_assignments_sha256=sha256_file(assignments_path),
        review_manifest_file="review_manifest.json",
        review_manifest_sha256=_sha256_bytes(review_manifest_bytes),
        reference_mentions_file="reference_mentions.jsonl",
        reference_mentions_sha256=_sha256_bytes(reference_bytes),
        annotation_audit_file="annotation_audit_summary.json",
        annotation_audit_sha256=_sha256_bytes(audit_bytes),
        selected_canonical_ids_sha256=selected_sha,
        document_count=48,
        annotation_row_count=96,
        completed_annotation_row_count=96,
        reference_mention_count=len(references),
        uncertain_reference_mention_count=0,
        reference_count_by_type=by_type,
        minimum_reference_mentions_per_type=minimum,
        reference_adequacy_passed=True,
        prediction_blind=True,
        sample_independent_validation_passed=True,
        heldout_development_overlap_count=0,
        review_complete=True,
        evaluation_harness_ready=True,
        candidate_predictions_visible_during_annotation=False,
        model_inference_executed=False,
        evaluation_executed=False,
        automatic_review_approval=False,
        production_extractor_selected=False,
        full_corpus_build_authorized=False,
        canonical_truth_mutated=False,
        may_be_used_as_reconcile_input=False,
        redistribution_allowed=False,
        publication_ready=False,
        next_slice="run_frozen_v02c_raw_inference_once",
    )
    completion_bytes = _json_bytes(completion_manifest.model_dump(mode="json"))

    readme = (
        "# Scientific Entity Fresh v0.2 reference evidence\n\n"
        f"Sample ID: `{config.sample.sample_id}`\n\n"
        f"Review ID: `{config.sample.review_id}`\n\n"
        "This immutable package contains prediction-blind manually adjudicated "
        "reference evidence for the fresh independent v0.2 held-out sample.\n\n"
        f"- annotation rows: 96\n"
        f"- reference mentions: {len(references)}\n"
        f"- uncertain mentions: 0\n"
        f"- minimum references per type: {minimum}\n"
        "- sample independent validation: passed\n"
        "- held-out/development overlap: 0\n"
        "- model inference executed: false\n"
        "- evaluation executed: false\n"
        "- production extractor selected: false\n"
        "- full-corpus build authorized: false\n"
    ).encode("utf-8")

    files = {
        "completed_annotations.jsonl": completed_bytes,
        "review_manifest.json": review_manifest_bytes,
        "reference_mentions.jsonl": reference_bytes,
        "completion_manifest.json": completion_bytes,
        "annotation_audit_summary.json": audit_bytes,
        "README.md": readme,
    }
    checksum_bytes = "".join(
        f"{_sha256_bytes(payload)}  {name}\n"
        for name, payload in sorted(files.items())
    ).encode("utf-8")
    files["checksums.txt"] = checksum_bytes

    report = {
        "report": REPORT_NAME,
        "sample_id": sample_manifest.sample_id,
        "review_id": sample_manifest.review_id,
        "document_count": 48,
        "annotation_row_count": 96,
        "completed_annotation_row_count": 96,
        "reference_mention_count": len(references),
        "uncertain_reference_mention_count": 0,
        "minimum_reference_mentions_per_type": minimum,
        "reference_count_by_type": {
            entity_type.value: by_type[entity_type]
            for entity_type in ScientificEntityType
        },
        "reference_adequacy_passed": True,
        "selected_canonical_ids_sha256": selected_sha,
        "sample_validation_required_failed_count": sample_summary["required_failed_count"],
        "prediction_blind": True,
        "candidate_predictions_visible_during_annotation": False,
        "model_inference_executed": False,
        "evaluation_executed": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "next_slice": "run_frozen_v02c_raw_inference_once",
    }
    return files, report


def freeze_reference_evidence(
    *,
    project_root: Path,
    config_path: Path,
    sample_dir: Path,
    canonical_path: Path,
    development_package_dir: Path,
    annotations_path: Path,
    annotator_ids: Sequence[str],
    output_root: Path | None = None,
    execute: bool = False,
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at_utc or datetime.now(timezone.utc)
    files, report = _compute_frozen_reference(
        project_root=project_root,
        config_path=config_path,
        sample_dir=sample_dir,
        canonical_path=canonical_path,
        development_package_dir=development_package_dir,
        annotations_path=annotations_path,
        annotator_ids=annotator_ids,
        generated_at_utc=generated_at,
    )
    config = load_scientific_entity_fresh_heldout_reference_config(config_path)
    root = (
        output_root.resolve()
        if output_root is not None
        else (project_root / config.outputs.frozen_root).resolve()
    )
    output_dir = root / config.sample.review_id
    if execute and output_dir.exists():
        raise FileExistsError(
            f"immutable reference directory already exists; overwrite forbidden: {output_dir}"
        )
    if execute:
        root.mkdir(parents=True, exist_ok=True)
        staging = Path(
            tempfile.mkdtemp(
                prefix=f".{config.sample.review_id}.tmp-",
                dir=root,
            )
        )
        try:
            for name, payload in files.items():
                (staging / name).write_bytes(payload)
            staging.rename(output_dir)
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise
    return {
        **report,
        "mode": "execute" if execute else "plan",
        "phase_complete": execute,
        "output_dir": str(output_dir).replace("\\", "/"),
        "next_slice": (
            "validate_fresh_v02_reference_evidence"
            if execute
            else "execute_fresh_v02_reference_freeze"
        ),
    }


def parse_checksums(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        parts = line.split("  ", 1)
        if len(parts) != 2:
            raise ScientificEntityFreshHeldoutReferenceError(
                f"invalid checksum line {line_number}"
            )
        digest, filename = parts
        if filename in result:
            raise ScientificEntityFreshHeldoutReferenceError(
                f"duplicate checksum filename: {filename}"
            )
        result[filename] = digest
    return result


def lf_ok(path: Path) -> bool:
    data = path.read_bytes()
    return bool(data) and not data.startswith(b"\xef\xbb\xbf") and b"\r" not in data and data.endswith(b"\n")


def validate_frozen_reference_evidence(
    *,
    project_root: Path,
    config_path: Path,
    sample_dir: Path,
    canonical_path: Path,
    development_package_dir: Path,
    reference_dir: Path,
) -> tuple[list[tuple[str, bool, str]], dict[str, Any]]:
    reference_dir = reference_dir.resolve()
    actual_files = {path.name for path in reference_dir.iterdir() if path.is_file()}
    checks: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: Any = "") -> None:
        checks.append((name, bool(ok), str(detail)))

    add("exact_file_layout", actual_files == FROZEN_FILES, sorted(actual_files))
    checksums = parse_checksums(reference_dir / "checksums.txt")
    add("checksum_filename_set", set(checksums) == CHECKSUM_FILES, sorted(checksums))
    for filename in sorted(CHECKSUM_FILES):
        add(
            f"checksum:{filename}",
            checksums.get(filename) == sha256_file(reference_dir / filename),
            checksums.get(filename, "missing"),
        )
    for filename in sorted(FROZEN_FILES):
        add(f"lf:{filename}", lf_ok(reference_dir / filename), filename)

    config, sample_manifest, selected_sha, sample_summary = _validate_sample_identity(
        project_root=project_root.resolve(),
        config_path=config_path.resolve(),
        sample_dir=sample_dir.resolve(),
        canonical_path=canonical_path.resolve(),
        development_package_dir=development_package_dir.resolve(),
    )
    add("sample_independent_validation_passed", sample_summary["required_failed_count"] == 0, sample_summary["required_failed_count"])

    completion = ScientificEntityFreshHeldoutReferenceCompletionManifest.model_validate(
        _read_json(reference_dir / "completion_manifest.json")
    )
    review = ScientificEntityReviewManifest.model_validate(
        _read_json(reference_dir / "review_manifest.json")
    )
    audit = _read_json(reference_dir / "annotation_audit_summary.json")
    completed_rows = [
        ScientificEntityBlindAnnotationRow.model_validate(row)
        for row in _read_jsonl(reference_dir / "completed_annotations.jsonl")
    ]
    blank_rows = [
        ScientificEntityBlindAnnotationRow.model_validate(row)
        for row in _read_jsonl(sample_dir.resolve() / "annotations_working.jsonl")
    ]
    immutable_ok = True
    immutable_detail = "completed rows match frozen blank template"
    try:
        validate_completed_annotations(
            template_rows=blank_rows,
            completed_rows=completed_rows,
        )
    except Exception as exc:
        immutable_ok = False
        immutable_detail = str(exc)
    add("completed_matches_blank_template", immutable_ok, immutable_detail)

    references = build_reference_mentions(
        review_id=config.sample.review_id,
        completed_rows=sorted(
            completed_rows,
            key=lambda row: (
                row.canonical_id,
                list(ScientificEntitySourceField).index(row.source_field),
            ),
        ),
        annotation_method=ScientificEntityAnnotationMethod.MANUAL_ADJUDICATED,
        annotation_pass=1,
    )
    recomputed_reference_bytes = _jsonl_bytes(
        [row.model_dump(mode="json") for row in references]
    )
    add(
        "reference_mentions_recomputed_exactly",
        recomputed_reference_bytes == (reference_dir / "reference_mentions.jsonl").read_bytes(),
        len(references),
    )
    by_type, _, uncertain_count = annotation_counts(completed_rows=completed_rows)
    add("annotation_row_count_96", len(completed_rows) == 96, len(completed_rows))
    add("all_annotation_rows_complete", all(row.annotation_complete for row in completed_rows), sum(int(row.annotation_complete) for row in completed_rows))
    add("uncertain_reference_count_zero", uncertain_count == 0, uncertain_count)
    for entity_type in ScientificEntityType:
        add(
            f"minimum_reference_count:{entity_type.value}",
            by_type[entity_type] >= config.annotation.minimum_reference_mentions_per_type,
            by_type[entity_type],
        )

    add("sample_id_matches", completion.sample_id == sample_manifest.sample_id == config.sample.sample_id, completion.sample_id)
    add("review_id_matches", completion.review_id == review.review_id == config.sample.review_id, completion.review_id)
    add("selected_ids_sha_matches", completion.selected_canonical_ids_sha256 == selected_sha, completion.selected_canonical_ids_sha256)
    add("sample_manifest_sha_matches", completion.sample_manifest_sha256 == sha256_file(sample_dir.resolve() / "manifest.json"), completion.sample_manifest_sha256)
    add("blank_sha_matches", completion.blank_annotations_sha256 == sha256_file(sample_dir.resolve() / "annotations_working.jsonl"), completion.blank_annotations_sha256)
    add("canonical_sample_sha_matches", completion.canonical_sample_sha256 == sha256_file(sample_dir.resolve() / "canonical_documents.sample.jsonl"), completion.canonical_sample_sha256)
    add("sample_assignments_sha_matches", completion.sample_assignments_sha256 == sha256_file(sample_dir.resolve() / "sample_assignments.jsonl"), completion.sample_assignments_sha256)
    add("completed_sha_matches", completion.completed_annotations_sha256 == sha256_file(reference_dir / "completed_annotations.jsonl"), completion.completed_annotations_sha256)
    add("review_manifest_sha_matches", completion.review_manifest_sha256 == sha256_file(reference_dir / "review_manifest.json"), completion.review_manifest_sha256)
    add("reference_sha_matches", completion.reference_mentions_sha256 == sha256_file(reference_dir / "reference_mentions.jsonl") == review.reference_mentions_sha256, completion.reference_mentions_sha256)
    add("audit_sha_matches", completion.annotation_audit_sha256 == sha256_file(reference_dir / "annotation_audit_summary.json"), completion.annotation_audit_sha256)
    add("reference_count_matches", completion.reference_mention_count == review.reference_mention_count == len(references), len(references))
    add("reference_adequacy_passed", completion.reference_adequacy_passed and audit.get("reference_adequacy_passed") is True, "")
    add("prediction_blind", completion.prediction_blind and review.prediction_blind and audit.get("prediction_blind") is True, "")
    add("evaluation_harness_ready", completion.evaluation_harness_ready, "")
    safety_ok = (
        completion.candidate_predictions_visible_during_annotation is False
        and completion.model_inference_executed is False
        and completion.evaluation_executed is False
        and completion.automatic_review_approval is False
        and completion.production_extractor_selected is False
        and completion.full_corpus_build_authorized is False
        and completion.canonical_truth_mutated is False
        and completion.may_be_used_as_reconcile_input is False
        and completion.redistribution_allowed is False
        and completion.publication_ready is False
    )
    add("safety_flags_fail_closed", safety_ok, "")
    add("next_slice_run_frozen_v02c", completion.next_slice == "run_frozen_v02c_raw_inference_once", completion.next_slice)

    failed = [name for name, ok, _ in checks if not ok]
    summary = {
        "report": REPORT_NAME,
        "sample_id": completion.sample_id,
        "review_id": completion.review_id,
        "document_count": completion.document_count,
        "annotation_row_count": completion.annotation_row_count,
        "reference_mention_count": completion.reference_mention_count,
        "uncertain_reference_mention_count": completion.uncertain_reference_mention_count,
        "minimum_reference_mentions_per_type": completion.minimum_reference_mentions_per_type,
        "reference_count_by_type": {
            entity_type.value: completion.reference_count_by_type[entity_type]
            for entity_type in ScientificEntityType
        },
        "reference_adequacy_passed": completion.reference_adequacy_passed,
        "prediction_blind": completion.prediction_blind,
        "model_inference_executed": completion.model_inference_executed,
        "evaluation_executed": completion.evaluation_executed,
        "production_extractor_selected": completion.production_extractor_selected,
        "full_corpus_build_authorized": completion.full_corpus_build_authorized,
        "total_checks": len(checks),
        "required_failed_count": len(failed),
        "next_slice": completion.next_slice,
    }
    return checks, summary
