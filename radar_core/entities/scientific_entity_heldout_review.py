from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml

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
from radar_core.contracts.scientific_entity_heldout_review import (
    HELDOUT_AUDIT_SCHEMA_VERSION,
    HELDOUT_COMPLETION_MANIFEST_SCHEMA_VERSION,
    ScientificEntityHeldoutReviewCompletionManifest,
)
from radar_core.contracts.scientific_entity_manual_review import (
    ScientificEntityBlindAnnotationRow,
)
from radar_core.entities.scientific_entity_manual_review import (
    annotation_counts,
    build_reference_mentions,
    validate_completed_annotations,
)


class ScientificEntityHeldoutReviewError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
        + b"\n"
    )


def _jsonl_bytes(rows: Iterable[dict[str, Any]]) -> bytes:
    return b"".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
        + b"\n"
        for row in rows
    )


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ScientificEntityHeldoutReviewError(f"Expected JSON object: {path}")
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                raise ScientificEntityHeldoutReviewError(
                    f"Blank JSONL line: {path}:{line_number}"
                )
            payload = json.loads(raw_line)
            if not isinstance(payload, dict):
                raise ScientificEntityHeldoutReviewError(
                    f"Expected JSON object: {path}:{line_number}"
                )
            rows.append(payload)
    return rows


def _count_jsonl(path: Path) -> int:
    return len(_read_jsonl(path))


def _normalize_annotator_ids(values: list[str]) -> list[str]:
    normalized = [value.strip() for value in values]
    if any(not value for value in normalized):
        raise ScientificEntityHeldoutReviewError("annotator_id must not be blank")
    if len(set(normalized)) != len(normalized):
        raise ScientificEntityHeldoutReviewError("annotator_id values must be unique")
    return normalized


def load_heldout_config(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ScientificEntityHeldoutReviewError("Held-out config must be a mapping")
    for required in ("review", "expected", "safety", "outputs"):
        if not isinstance(payload.get(required), dict):
            raise ScientificEntityHeldoutReviewError(
                f"Held-out config missing mapping: {required}"
            )
    return payload


def finalize_heldout_review(
    *,
    prepared_dir: Path,
    annotations_path: Path,
    config_path: Path,
    annotator_ids: list[str],
    output_root: Path | None = None,
    execute: bool = False,
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    prepared_dir = prepared_dir.resolve()
    annotations_path = annotations_path.resolve()
    config_path = config_path.resolve()
    config = load_heldout_config(config_path)
    review_cfg = config["review"]
    expected = config["expected"]
    safety = config["safety"]

    required_prepared_files = {
        "annotations_working.jsonl",
        "canonical_documents.sample.jsonl",
        "sample_assignments.jsonl",
        "selected_papers.tsv",
        "preparation_manifest.json",
    }
    missing = sorted(
        name for name in required_prepared_files if not (prepared_dir / name).is_file()
    )
    if missing:
        raise ScientificEntityHeldoutReviewError(
            f"Prepared held-out package missing required files: {missing}"
        )
    if not annotations_path.is_file():
        raise ScientificEntityHeldoutReviewError(
            f"Completed annotations file not found: {annotations_path}"
        )

    preparation_manifest_path = prepared_dir / "preparation_manifest.json"
    preparation_manifest = _read_json(preparation_manifest_path)
    review_id = str(review_cfg["review_id"])
    if preparation_manifest.get("review_id") != review_id:
        raise ScientificEntityHeldoutReviewError(
            "Prepared review_id does not match frozen held-out config"
        )
    if preparation_manifest.get("prediction_blind") is not True:
        raise ScientificEntityHeldoutReviewError("Prepared package is not prediction-blind")
    if int(preparation_manifest.get("heldout_dev_overlap_count", -1)) != int(
        safety["heldout_dev_overlap_count"]
    ):
        raise ScientificEntityHeldoutReviewError("Held-out/dev overlap is not zero")
    if int(preparation_manifest.get("selected_document_count", -1)) != int(
        expected["document_count"]
    ):
        raise ScientificEntityHeldoutReviewError("Prepared document count mismatch")
    if int(preparation_manifest.get("annotation_row_count", -1)) != int(
        expected["annotation_row_count"]
    ):
        raise ScientificEntityHeldoutReviewError("Prepared annotation row count mismatch")

    files = preparation_manifest.get("files")
    if not isinstance(files, dict):
        raise ScientificEntityHeldoutReviewError("Preparation manifest files map missing")

    blank_path = prepared_dir / "annotations_working.jsonl"
    blank_sha = sha256_file(blank_path)
    expected_blank_sha = str(expected["blank_annotations_sha256"])
    if blank_sha != expected_blank_sha:
        raise ScientificEntityHeldoutReviewError(
            f"Blank annotation SHA mismatch: expected={expected_blank_sha}, actual={blank_sha}"
        )
    if files.get("annotations_working.jsonl") != blank_sha:
        raise ScientificEntityHeldoutReviewError(
            "Blank annotation SHA does not match preparation manifest"
        )

    sample_path = prepared_dir / "canonical_documents.sample.jsonl"
    assignments_path = prepared_dir / "sample_assignments.jsonl"
    sample_sha = sha256_file(sample_path)
    assignments_sha = sha256_file(assignments_path)
    if files.get("canonical_documents.sample.jsonl") != sample_sha:
        raise ScientificEntityHeldoutReviewError(
            "Canonical sample SHA does not match preparation manifest"
        )
    if files.get("sample_assignments.jsonl") != assignments_sha:
        raise ScientificEntityHeldoutReviewError(
            "Sample assignments SHA does not match preparation manifest"
        )

    sample_rows = _read_jsonl(sample_path)
    sample_ids = [str(row.get("canonical_id") or "") for row in sample_rows]
    if len(sample_rows) != int(expected["document_count"]):
        raise ScientificEntityHeldoutReviewError("Canonical sample document count mismatch")
    if len(set(sample_ids)) != len(sample_ids) or any(not value for value in sample_ids):
        raise ScientificEntityHeldoutReviewError("Canonical sample IDs must be unique/non-empty")
    selected_ids = preparation_manifest.get("selected_canonical_ids")
    if not isinstance(selected_ids, list) or sorted(sample_ids) != sorted(selected_ids):
        raise ScientificEntityHeldoutReviewError(
            "Canonical sample IDs differ from preparation manifest"
        )
    excluded_ids = set(preparation_manifest.get("excluded_dev_canonical_ids") or [])
    if set(sample_ids) & excluded_ids:
        raise ScientificEntityHeldoutReviewError("Held-out sample overlaps excluded dev IDs")

    blank_payloads = _read_jsonl(blank_path)
    completed_payloads = _read_jsonl(annotations_path)
    if len(blank_payloads) != int(expected["annotation_row_count"]):
        raise ScientificEntityHeldoutReviewError("Blank annotation row count mismatch")
    if len(completed_payloads) != int(expected["annotation_row_count"]):
        raise ScientificEntityHeldoutReviewError("Completed annotation row count mismatch")

    blank_rows = [ScientificEntityBlindAnnotationRow.model_validate(row) for row in blank_payloads]
    completed_rows = [
        ScientificEntityBlindAnnotationRow.model_validate(row) for row in completed_payloads
    ]
    validate_completed_annotations(template_rows=blank_rows, completed_rows=completed_rows)
    if any(row.review_id != review_id for row in completed_rows):
        raise ScientificEntityHeldoutReviewError(
            "Completed annotation review_id does not match frozen held-out review"
        )
    if any(row.annotation_complete for row in blank_rows):
        raise ScientificEntityHeldoutReviewError(
            "Recovered blank annotations must remain annotation_complete=false"
        )
    if any(row.mentions for row in blank_rows):
        raise ScientificEntityHeldoutReviewError(
            "Recovered blank annotations must contain zero mentions"
        )

    normalized_annotators = _normalize_annotator_ids(annotator_ids)
    annotation_method = ScientificEntityAnnotationMethod(review_cfg["annotation_method"])
    if annotation_method != ScientificEntityAnnotationMethod.MANUAL_ADJUDICATED:
        raise ScientificEntityHeldoutReviewError(
            "Held-out v0.1 is frozen to manual_adjudicated annotation method"
        )
    annotation_passes = int(review_cfg["annotation_passes"])

    completed_rows = sorted(
        completed_rows,
        key=lambda row: (
            row.canonical_id,
            list(ScientificEntitySourceField).index(row.source_field),
        ),
    )
    references = build_reference_mentions(
        review_id=review_id,
        completed_rows=completed_rows,
        annotation_method=annotation_method,
        annotation_pass=annotation_passes,
    )
    if len(references) != int(expected["reference_mention_count"]):
        raise ScientificEntityHeldoutReviewError(
            f"Reference mention count mismatch: expected={expected['reference_mention_count']}, "
            f"actual={len(references)}"
        )

    by_type, by_stratum, uncertain_count = annotation_counts(completed_rows=completed_rows)
    expected_by_type = {
        ScientificEntityType(key): int(value)
        for key, value in expected["reference_count_by_type"].items()
    }
    if by_type != expected_by_type:
        raise ScientificEntityHeldoutReviewError(
            f"Reference count by type mismatch: expected={expected_by_type}, actual={by_type}"
        )
    if uncertain_count != int(expected["uncertain_reference_mention_count"]):
        raise ScientificEntityHeldoutReviewError("Uncertain mention count mismatch")

    completed_bytes = _jsonl_bytes([row.model_dump(mode="json") for row in completed_rows])
    reference_bytes = _jsonl_bytes([row.model_dump(mode="json") for row in references])
    generated_at = generated_at_utc or datetime.now(timezone.utc)
    if generated_at.tzinfo is None or generated_at.utcoffset() != timezone.utc.utcoffset(
        generated_at
    ):
        raise ScientificEntityHeldoutReviewError("generated_at_utc must be UTC-aware")

    canonical_input = ScientificEntityCanonicalInput(
        schema_version=CANONICAL_INPUT_SCHEMA_VERSION,
        path=str(sample_path).replace("\\", "/"),
        sha256=sample_sha,
        document_count=len(sample_rows),
        canonical_contract="CanonicalDocument",
    )
    review_manifest = ScientificEntityReviewManifest(
        schema_version=REVIEW_MANIFEST_SCHEMA_VERSION,
        review_id=review_id,
        status=ScientificEntityReviewStatus.REVIEWED_CANDIDATE,
        generated_at_utc=generated_at,
        canonical_input=canonical_input,
        annotation_method=annotation_method,
        annotation_guideline_version=str(review_cfg["annotation_guideline_version"]),
        annotation_passes=annotation_passes,
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
        "schema_version": HELDOUT_AUDIT_SCHEMA_VERSION,
        "review_id": review_id,
        "prediction_blind": True,
        "heldout_dev_overlap_count": 0,
        "review_complete": True,
        "document_count": len(sample_rows),
        "annotation_row_count": len(completed_rows),
        "completed_annotation_row_count": sum(
            int(row.annotation_complete) for row in completed_rows
        ),
        "zero_mention_annotation_row_count": sum(int(not row.mentions) for row in completed_rows),
        "reference_mention_count": len(references),
        "uncertain_reference_mention_count": uncertain_count,
        "reference_count_by_type": {
            entity_type.value: by_type[entity_type] for entity_type in ScientificEntityType
        },
        "reference_count_by_stratum": {
            stratum.value: count for stratum, count in by_stratum.items()
        },
        "automatic_review_approval": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "publication_ready": False,
    }
    audit_bytes = _json_bytes(audit)

    completion_manifest = ScientificEntityHeldoutReviewCompletionManifest(
        schema_version=HELDOUT_COMPLETION_MANIFEST_SCHEMA_VERSION,
        review_id=review_id,
        generated_at_utc=generated_at,
        review_status=ScientificEntityReviewStatus.REVIEWED_CANDIDATE,
        annotation_method=annotation_method,
        annotation_guideline_version=str(review_cfg["annotation_guideline_version"]),
        annotation_passes=annotation_passes,
        annotator_ids=normalized_annotators,
        preparation_manifest_file="preparation_manifest.json",
        preparation_manifest_sha256=sha256_file(preparation_manifest_path),
        blank_annotations_file="annotations_working.jsonl",
        blank_annotations_sha256=blank_sha,
        completed_annotations_file="completed_annotations.jsonl",
        completed_annotations_sha256=_sha256_bytes(completed_bytes),
        canonical_sample_file="canonical_documents.sample.jsonl",
        canonical_sample_sha256=sample_sha,
        sample_assignments_file="sample_assignments.jsonl",
        sample_assignments_sha256=assignments_sha,
        review_manifest_file="review_manifest.json",
        review_manifest_sha256=_sha256_bytes(review_manifest_bytes),
        reference_mentions_file="reference_mentions.jsonl",
        reference_mentions_sha256=_sha256_bytes(reference_bytes),
        annotation_audit_file="annotation_audit_summary.json",
        annotation_audit_sha256=_sha256_bytes(audit_bytes),
        document_count=len(sample_rows),
        annotation_row_count=len(completed_rows),
        completed_annotation_row_count=len(completed_rows),
        reference_mention_count=len(references),
        uncertain_reference_mention_count=uncertain_count,
        reference_count_by_type=by_type,
        prediction_blind=True,
        heldout_dev_overlap_count=0,
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

    readme = (
        f"# Scientific Entity held-out review evidence v0.1\n\n"
        f"Review ID: `{review_id}`\n\n"
        f"This immutable package contains prediction-blind, manually adjudicated "
        f"held-out reference evidence for 48 papers.\n\n"
        f"- annotation rows: {len(completed_rows)}\n"
        f"- reference mentions: {len(references)}\n"
        f"- uncertain mentions: {uncertain_count}\n"
        f"- held-out/dev overlap: 0\n"
        f"- production extractor selected: false\n"
        f"- full-corpus build authorized: false\n"
    ).encode("utf-8")

    output_root = (
        output_root.resolve()
        if output_root is not None
        else (Path.cwd() / config["outputs"]["completed_root"]).resolve()
    )
    output_dir = output_root / review_id
    if output_dir.exists() and execute:
        raise FileExistsError(
            f"Immutable held-out completion directory already exists: {output_dir}"
        )

    output_files = {
        "completed_annotations.jsonl": completed_bytes,
        "review_manifest.json": review_manifest_bytes,
        "reference_mentions.jsonl": reference_bytes,
        "completion_manifest.json": completion_bytes,
        "annotation_audit_summary.json": audit_bytes,
        "README.md": readme,
    }
    checksums = "".join(
        f"{_sha256_bytes(payload)}  {name}\n" for name, payload in sorted(output_files.items())
    ).encode("utf-8")
    output_files["checksums.txt"] = checksums

    if execute:
        output_dir.mkdir(parents=True, exist_ok=False)
        for name, payload in output_files.items():
            (output_dir / name).write_bytes(payload)

    return {
        "report": "scientific_entity_heldout_review_finalize_v01",
        "mode": "execute" if execute else "plan",
        "phase_complete": execute,
        "review_id": review_id,
        "document_count": len(sample_rows),
        "annotation_row_count": len(completed_rows),
        "reference_mention_count": len(references),
        "uncertain_reference_mention_count": uncertain_count,
        "reference_count_by_type": {
            entity_type.value: by_type[entity_type] for entity_type in ScientificEntityType
        },
        "blank_annotations_sha256": blank_sha,
        "completed_annotations_sha256": _sha256_bytes(completed_bytes),
        "prediction_blind": True,
        "heldout_dev_overlap_count": 0,
        "evaluation_harness_ready": True,
        "output_dir": str(output_dir).replace("\\", "/"),
        "next_slice": (
            "validate_heldout_reference_evidence_v0.1"
            if execute
            else "execute_heldout_reference_finalization_v0.1"
        ),
    }
