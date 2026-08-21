from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from radar_core.contracts.canonical_document import CanonicalDocument
from radar_core.contracts.scientific_entity_evaluation import (
    ScientificEntityReferenceMention,
    ScientificEntityReviewManifest,
    build_reference_id,
    validate_reference_mention,
)
from radar_core.contracts.scientific_entity_evidence import (
    ScientificEntitySourceField,
    ScientificEntityType,
    build_mention_id,
    sha256_text,
)
from radar_core.contracts.scientific_entity_manual_review import (
    ScientificEntityBlindAnnotationRow,
    ScientificEntityManualReviewCompletionManifest,
    ScientificEntityManualReviewPreparedManifest,
    ScientificEntityReviewSampleStatus,
    ScientificEntitySampleAssignment,
    ScientificEntitySampleStratum,
    build_selection_score,
)
from radar_core.entities.scientific_entity_manual_review import (
    ScientificEntityManualReviewConfig,
    load_manual_review_config,
)


REPORT_NAME = "scientific_entity_manual_review_evidence"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = (
    PROJECT_ROOT / "configs" / "scientific_entity_manual_review_evidence_v0.1.yaml"
)
DEFAULT_REPORT_DIR = PROJECT_ROOT / "artifacts" / "reports" / "validation"
ENVIRONMENT_LOCK_PATH = PROJECT_ROOT / "requirements" / "requirements.core.lock.txt"
CODE_REVISION_FILES = (
    "radar_core/contracts/scientific_entity_evidence.py",
    "radar_core/contracts/scientific_entity_evaluation.py",
    "radar_core/contracts/scientific_entity_manual_review.py",
    "radar_core/entities/scientific_entity_manual_review.py",
    "scripts/entities/build_scientific_entity_manual_review_evidence.py",
)
PREPARED_FILES = {
    "canonical_documents.sample.jsonl",
    "sample_assignments.jsonl",
    "annotation_template.jsonl",
    "manifest.json",
    "data_quality_summary.json",
    "README.md",
    "checksums.txt",
}
PREPARED_CHECKSUM_FILES = PREPARED_FILES - {"checksums.txt"}
COMPLETED_FILES = {
    "completed_annotations.jsonl",
    "review_manifest.json",
    "reference_mentions.jsonl",
    "completion_manifest.json",
    "annotation_audit_summary.json",
    "README.md",
    "checksums.txt",
}
COMPLETED_CHECKSUM_FILES = COMPLETED_FILES - {"checksums.txt"}
PROHIBITED_ANNOTATION_KEYS = {
    "prediction",
    "predictions",
    "prediction_evidence_id",
    "evidence_id",
    "extractor",
    "extractor_fingerprint",
    "confidence_kind",
    "confidence_score",
}


@dataclass(frozen=True)
class Check:
    name: str
    required: bool
    ok: bool
    details: str


def _add(
    checks: list[Check],
    name: str,
    ok: bool,
    details: str,
    *,
    required: bool = True,
) -> None:
    checks.append(Check(name=name, required=required, ok=bool(ok), details=details))


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


def _semantic_config_sha256(config: ScientificEntityManualReviewConfig) -> str:
    payload = json.dumps(
        config.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalized_file_sha256(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _source_bundle_revision() -> str:
    digest = hashlib.sha256()
    for relative_path in sorted(CODE_REVISION_FILES):
        path = PROJECT_ROOT / relative_path
        normalized = path.read_text(encoding="utf-8")
        normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(normalized.encode("utf-8"))
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _read_jsonl(path: Path, *, hard_limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                raise ValueError(f"Blank JSONL line: {path}:{line_number}")
            payload = json.loads(raw_line)
            if not isinstance(payload, dict):
                raise ValueError(f"Expected JSON object: {path}:{line_number}")
            rows.append(payload)
            if len(rows) > hard_limit:
                raise ValueError(f"JSONL input exceeds hard limit {hard_limit}: {path}")
    return rows


def _parse_checksums(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        parts = raw_line.split("  ", 1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            raise ValueError(f"Invalid checksum row: {path}:{line_number}")
        digest, filename = parts
        if filename in result:
            raise ValueError(f"Duplicate checksum filename: {filename}")
        result[filename] = digest
    return result


def _lf_ok(path: Path, *, empty_allowed: bool = False) -> bool:
    data = path.read_bytes()
    if not data:
        return empty_allowed
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return (
        not data.startswith(b"\xef\xbb\xbf")
        and b"\r" not in data
        and data.endswith(b"\n")
    )


def _validate_layout_and_checksums(
    *,
    directory: Path,
    expected_files: set[str],
    checksum_files: set[str],
    prefix: str,
    checks: list[Check],
) -> None:
    actual = {path.name for path in directory.iterdir() if path.is_file()}
    _add(
        checks,
        f"{prefix}_exact_file_layout",
        actual == expected_files,
        f"expected={sorted(expected_files)}, actual={sorted(actual)}",
    )
    missing = expected_files - actual
    if missing:
        return
    try:
        checksums = _parse_checksums(directory / "checksums.txt")
        _add(
            checks,
            f"{prefix}_checksum_filename_set",
            set(checksums) == checksum_files,
            f"expected={sorted(checksum_files)}, actual={sorted(checksums)}",
        )
        for filename in sorted(checksum_files):
            actual_sha = _sha256_file(directory / filename)
            _add(
                checks,
                f"{prefix}_checksum_{filename.replace('.', '_')}",
                checksums.get(filename) == actual_sha,
                f"declared={checksums.get(filename)}, actual={actual_sha}",
            )
    except Exception as exc:
        _add(checks, f"{prefix}_checksums_parse", False, str(exc))

    for filename in sorted(expected_files):
        path = directory / filename
        empty_allowed = filename == "reference_mentions.jsonl"
        _add(
            checks,
            f"{prefix}_lf_{filename.replace('.', '_')}",
            _lf_ok(path, empty_allowed=empty_allowed),
            "UTF-8 text must have no BOM/CR and end with LF",
        )


def _term_matches(text: str, term: str) -> bool:
    pattern = re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)
    return pattern.search(text) is not None


def _push_candidate(
    heap: list[tuple[int, str, str]],
    *,
    score: str,
    canonical_id: str,
    limit: int,
) -> None:
    heapq.heappush(heap, (-int(score, 16), canonical_id, score))
    if len(heap) > limit:
        heapq.heappop(heap)


def _independent_expected_assignments(
    *,
    source_path: Path,
    manifest: ScientificEntityManualReviewPreparedManifest,
    config: ScientificEntityManualReviewConfig,
) -> tuple[list[dict[str, Any]], int, int]:
    uniform_heap: list[tuple[int, str, str]] = []
    type_heaps: dict[ScientificEntityType, list[tuple[int, str, str]]] = {
        entity_type: [] for entity_type in ScientificEntityType
    }
    seen: set[str] = set()
    source_count = 0
    eligible_count = 0
    with source_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            if not raw_line.strip():
                raise ValueError("Blank source JSONL line")
            source_count += 1
            if source_count > config.safety.hard_max_source_documents:
                raise ValueError("Source exceeds configured hard limit")
            payload = json.loads(raw_line)
            document = CanonicalDocument.model_validate(payload)
            if document.canonical_id in seen:
                raise ValueError(f"Duplicate source canonical_id: {document.canonical_id}")
            seen.add(document.canonical_id)
            if not document.title.strip() or not (document.abstract or "").strip():
                continue
            eligible_count += 1
            score = build_selection_score(
                seed=manifest.sampling_policy.seed,
                stratum=ScientificEntitySampleStratum.UNIFORM,
                canonical_id=document.canonical_id,
            )
            _push_candidate(
                uniform_heap,
                score=score,
                canonical_id=document.canonical_id,
                limit=manifest.sampling_policy.candidate_pool_per_stratum,
            )
            text = f"{document.title}\n{document.abstract or ''}"
            for entity_type in ScientificEntityType:
                if any(
                    _term_matches(text, term)
                    for term in config.sampling.type_enrichment_terms[entity_type]
                ):
                    score = build_selection_score(
                        seed=manifest.sampling_policy.seed,
                        stratum=ScientificEntitySampleStratum.TYPE_ENRICHED,
                        enrichment_entity_type=entity_type,
                        canonical_id=document.canonical_id,
                    )
                    _push_candidate(
                        type_heaps[entity_type],
                        score=score,
                        canonical_id=document.canonical_id,
                        limit=manifest.sampling_policy.candidate_pool_per_stratum,
                    )

    selected: set[str] = set()
    rows: list[dict[str, Any]] = []
    for entity_type in ScientificEntityType:
        ordered = sorted(
            [(entry[2], entry[1]) for entry in type_heaps[entity_type]],
            key=lambda value: (value[0], value[1]),
        )
        rank = 0
        for score, canonical_id in ordered:
            if canonical_id in selected:
                continue
            rank += 1
            selected.add(canonical_id)
            rows.append(
                ScientificEntitySampleAssignment(
                    schema_version="scientific_entity_sample_assignment_v0.1",
                    review_id=manifest.review_id,
                    canonical_id=canonical_id,
                    sample_stratum=ScientificEntitySampleStratum.TYPE_ENRICHED,
                    enrichment_entity_type=entity_type,
                    selection_score=score,
                    stratum_rank=rank,
                ).model_dump(mode="json")
            )
            if rank == manifest.sampling_policy.type_enriched_documents_per_type:
                break
        if rank != manifest.sampling_policy.type_enriched_documents_per_type:
            raise ValueError(f"Insufficient type candidates for {entity_type.value}")

    ordered_uniform = sorted(
        [(entry[2], entry[1]) for entry in uniform_heap],
        key=lambda value: (value[0], value[1]),
    )
    rank = 0
    for score, canonical_id in ordered_uniform:
        if canonical_id in selected:
            continue
        rank += 1
        selected.add(canonical_id)
        rows.append(
            ScientificEntitySampleAssignment(
                schema_version="scientific_entity_sample_assignment_v0.1",
                review_id=manifest.review_id,
                canonical_id=canonical_id,
                sample_stratum=ScientificEntitySampleStratum.UNIFORM,
                enrichment_entity_type=None,
                selection_score=score,
                stratum_rank=rank,
            ).model_dump(mode="json")
        )
        if rank == manifest.sampling_policy.uniform_document_count:
            break
    if rank != manifest.sampling_policy.uniform_document_count:
        raise ValueError("Insufficient uniform candidates")
    rows = sorted(
        rows,
        key=lambda value: (
            0 if value["sample_stratum"] == "uniform" else 1,
            value["enrichment_entity_type"] or "",
            value["stratum_rank"],
            value["canonical_id"],
        ),
    )
    return rows, source_count, eligible_count


def _validate_prepared(
    *,
    prepared_dir: Path,
    config_path: Path,
    config: ScientificEntityManualReviewConfig,
    checks: list[Check],
) -> ScientificEntityManualReviewPreparedManifest | None:
    _add(checks, "prepared_directory_exists", prepared_dir.is_dir(), str(prepared_dir))
    if not prepared_dir.is_dir():
        return None
    _validate_layout_and_checksums(
        directory=prepared_dir,
        expected_files=PREPARED_FILES,
        checksum_files=PREPARED_CHECKSUM_FILES,
        prefix="prepared",
        checks=checks,
    )
    if not PREPARED_FILES.issubset(
        {path.name for path in prepared_dir.iterdir() if path.is_file()}
    ):
        return None
    try:
        manifest = ScientificEntityManualReviewPreparedManifest.model_validate(
            _read_json(prepared_dir / "manifest.json")
        )
        _add(checks, "prepared_manifest_contract", True, manifest.schema_version)
    except Exception as exc:
        _add(checks, "prepared_manifest_contract", False, str(exc))
        return None

    _add(
        checks,
        "prepared_config_path_matches",
        _resolve_project_path(manifest.config_path) == config_path.resolve(),
        manifest.config_path,
    )
    _add(
        checks,
        "prepared_config_sha256_matches",
        manifest.config_sha256 == _semantic_config_sha256(config),
        manifest.config_sha256,
    )
    _add(
        checks,
        "prepared_code_revision_matches",
        manifest.code_revision == _source_bundle_revision(),
        manifest.code_revision,
    )
    _add(
        checks,
        "prepared_environment_sha256_matches",
        manifest.environment_sha256 == _normalized_file_sha256(ENVIRONMENT_LOCK_PATH),
        manifest.environment_sha256,
    )
    if manifest.status == ScientificEntityReviewSampleStatus.FIXTURE:
        expected_policy = config.sampling.policy(
            uniform_document_count=config.fixtures.uniform_document_count,
            type_enriched_documents_per_type=(
                config.fixtures.type_enriched_documents_per_type
            ),
        )
        expected_source_path = _resolve_project_path(config.fixtures.input_path)
        _add(
            checks,
            "prepared_fixture_review_id_matches",
            manifest.review_id == config.fixtures.review_id,
            manifest.review_id,
        )
    else:
        expected_policy = config.sampling.policy()
        expected_source_path = _resolve_project_path(
            config.safety.current_canonical_path
        )
    _add(
        checks,
        "prepared_sampling_policy_matches_config",
        manifest.sampling_policy == expected_policy,
        manifest.status.value,
    )
    _add(
        checks,
        "prepared_source_path_matches_status_boundary",
        _resolve_project_path(manifest.source_canonical_input.path)
        == expected_source_path,
        manifest.source_canonical_input.path,
    )
    sample_path = prepared_dir / "canonical_documents.sample.jsonl"
    assignments_path = prepared_dir / "sample_assignments.jsonl"
    template_path = prepared_dir / "annotation_template.jsonl"
    _add(
        checks,
        "prepared_sample_manifest_path_matches",
        _resolve_project_path(manifest.sample_canonical_input.path) == sample_path.resolve(),
        manifest.sample_canonical_input.path,
    )
    _add(
        checks,
        "prepared_sample_sha256_matches",
        _sha256_file(sample_path) == manifest.sample_canonical_input.sha256,
        manifest.sample_canonical_input.sha256,
    )
    _add(
        checks,
        "prepared_assignments_sha256_matches",
        _sha256_file(assignments_path) == manifest.sample_assignments_sha256,
        manifest.sample_assignments_sha256,
    )
    _add(
        checks,
        "prepared_template_sha256_matches",
        _sha256_file(template_path) == manifest.annotation_template_sha256,
        manifest.annotation_template_sha256,
    )

    try:
        sample_payloads = _read_jsonl(
            sample_path, hard_limit=config.safety.hard_max_selected_documents
        )
        documents = [CanonicalDocument.model_validate(row) for row in sample_payloads]
        sample_ids = [document.canonical_id for document in documents]
        _add(
            checks,
            "prepared_sample_document_count",
            len(documents) == manifest.sample_canonical_input.document_count,
            f"actual={len(documents)}, declared={manifest.sample_canonical_input.document_count}",
        )
        _add(
            checks,
            "prepared_sample_ids_unique",
            len(sample_ids) == len(set(sample_ids)),
            f"count={len(sample_ids)}",
        )
        _add(
            checks,
            "prepared_sample_title_abstract_nonempty",
            all(doc.title.strip() and (doc.abstract or "").strip() for doc in documents),
            "all selected documents require both fields",
        )
    except Exception as exc:
        _add(checks, "prepared_sample_contract", False, str(exc))
        return manifest

    try:
        assignment_payloads = _read_jsonl(
            assignments_path, hard_limit=config.safety.hard_max_selected_documents
        )
        assignments = [
            ScientificEntitySampleAssignment.model_validate(row)
            for row in assignment_payloads
        ]
        assignment_ids = [row.canonical_id for row in assignments]
        _add(
            checks,
            "prepared_assignment_count",
            len(assignments) == len(documents),
            f"assignments={len(assignments)}, documents={len(documents)}",
        )
        _add(
            checks,
            "prepared_assignment_ids_exact",
            set(assignment_ids) == set(sample_ids) and len(assignment_ids) == len(set(assignment_ids)),
            "one assignment per selected document",
        )
        scores_ok = all(
            row.selection_score
            == build_selection_score(
                seed=manifest.sampling_policy.seed,
                stratum=row.sample_stratum,
                enrichment_entity_type=row.enrichment_entity_type,
                canonical_id=row.canonical_id,
            )
            for row in assignments
        )
        _add(checks, "prepared_assignment_scores_recomputed", scores_ok, "stable SHA-256 scores")
        by_stratum = Counter(row.sample_stratum for row in assignments)
        by_type = Counter(
            row.enrichment_entity_type
            for row in assignments
            if row.enrichment_entity_type is not None
        )
        _add(
            checks,
            "prepared_uniform_count_matches",
            by_stratum[ScientificEntitySampleStratum.UNIFORM] == manifest.uniform_document_count,
            str(by_stratum),
        )
        _add(
            checks,
            "prepared_type_enriched_count_matches",
            by_stratum[ScientificEntitySampleStratum.TYPE_ENRICHED]
            == manifest.type_enriched_document_count,
            str(by_stratum),
        )
        _add(
            checks,
            "prepared_per_type_counts_match",
            all(
                by_type[entity_type] == manifest.type_enriched_count_by_type[entity_type]
                for entity_type in ScientificEntityType
            ),
            str(by_type),
        )
    except Exception as exc:
        _add(checks, "prepared_assignment_contract", False, str(exc))
        return manifest

    doc_by_id = {document.canonical_id: document for document in documents}
    assignment_by_id = {row.canonical_id: row for row in assignments}
    enrichment_matches = True
    for row in assignments:
        if row.sample_stratum != ScientificEntitySampleStratum.TYPE_ENRICHED:
            continue
        document = doc_by_id[row.canonical_id]
        text = f"{document.title}\n{document.abstract or ''}"
        if not any(
            _term_matches(text, term)
            for term in config.sampling.type_enrichment_terms[row.enrichment_entity_type]
        ):
            enrichment_matches = False
    _add(
        checks,
        "prepared_type_enrichment_terms_match",
        enrichment_matches,
        "every enriched assignment matches a tracked selection cue",
    )

    try:
        template_payloads = _read_jsonl(
            template_path, hard_limit=config.safety.hard_max_annotation_rows
        )
        prohibited_present = any(
            bool(PROHIBITED_ANNOTATION_KEYS.intersection(row))
            for row in template_payloads
        )
        template_rows = [
            ScientificEntityBlindAnnotationRow.model_validate(row)
            for row in template_payloads
        ]
        template_keys = [(row.canonical_id, row.source_field) for row in template_rows]
        expected_keys = {
            (canonical_id, source_field)
            for canonical_id in sample_ids
            for source_field in ScientificEntitySourceField
        }
        _add(
            checks,
            "prepared_template_row_count",
            len(template_rows) == manifest.annotation_row_count,
            f"actual={len(template_rows)}, declared={manifest.annotation_row_count}",
        )
        _add(
            checks,
            "prepared_template_exact_source_field_coverage",
            set(template_keys) == expected_keys and len(template_keys) == len(set(template_keys)),
            "one title and abstract row per document",
        )
        _add(
            checks,
            "prepared_template_prediction_keys_absent",
            not prohibited_present,
            f"prohibited={sorted(PROHIBITED_ANNOTATION_KEYS)}",
        )
        _add(
            checks,
            "prepared_template_mentions_empty",
            all(not row.mentions for row in template_rows),
            "prepared template cannot contain labels",
        )
        _add(
            checks,
            "prepared_template_rows_pending",
            all(not row.annotation_complete for row in template_rows),
            "prepared template must not claim completed review",
        )
        template_source_ok = True
        template_assignment_ok = True
        for row in template_rows:
            document = doc_by_id[row.canonical_id]
            expected_text = (
                document.title
                if row.source_field == ScientificEntitySourceField.TITLE
                else document.abstract
            )
            template_source_ok &= (
                expected_text == row.source_text
                and row.source_text_sha256 == sha256_text(row.source_text)
            )
            assignment = assignment_by_id[row.canonical_id]
            template_assignment_ok &= (
                row.sample_stratum == assignment.sample_stratum
                and row.enrichment_entity_type == assignment.enrichment_entity_type
            )
        _add(
            checks,
            "prepared_template_source_text_exact",
            template_source_ok,
            "template source strings must equal sample title/abstract",
        )
        _add(
            checks,
            "prepared_template_assignment_exact",
            template_assignment_ok,
            "template strata must match assignments",
        )
    except Exception as exc:
        _add(checks, "prepared_template_contract", False, str(exc))

    quality: dict[str, Any] | None = None
    try:
        quality = _read_json(prepared_dir / "data_quality_summary.json")
        expected_quality_keys = {
            "schema_version",
            "review_id",
            "status",
            "scanned_source_document_count",
            "eligible_document_count",
            "selected_document_count",
            "annotation_row_count",
            "uniform_document_count",
            "type_enriched_document_count",
            "type_enriched_count_by_type",
            "prediction_fields_present",
            "review_complete",
            "selection_terms_are_reference_annotations",
        }
        _add(
            checks,
            "prepared_quality_exact_field_set",
            set(quality) == expected_quality_keys,
            f"actual={sorted(quality)}",
        )
        expected_type_counts = {
            entity_type.value: manifest.type_enriched_count_by_type[entity_type]
            for entity_type in ScientificEntityType
        }
        quality_matches = (
            quality.get("schema_version")
            == "scientific_entity_manual_review_preparation_quality_v0.1"
            and quality.get("review_id") == manifest.review_id
            and quality.get("status") == manifest.status.value
            and quality.get("scanned_source_document_count")
            == manifest.source_canonical_input.document_count
            and quality.get("selected_document_count")
            == manifest.sample_canonical_input.document_count
            and quality.get("annotation_row_count") == manifest.annotation_row_count
            and quality.get("uniform_document_count")
            == manifest.uniform_document_count
            and quality.get("type_enriched_document_count")
            == manifest.type_enriched_document_count
            and quality.get("type_enriched_count_by_type") == expected_type_counts
            and quality.get("prediction_fields_present") is False
            and quality.get("review_complete") is False
            and quality.get("selection_terms_are_reference_annotations") is False
        )
        _add(
            checks,
            "prepared_quality_semantics_match",
            quality_matches,
            "summary fields must match independently parsed evidence",
        )
    except Exception as exc:
        _add(checks, "prepared_quality_contract", False, str(exc))

    source_path = _resolve_project_path(manifest.source_canonical_input.path)
    _add(checks, "prepared_source_input_exists", source_path.is_file(), str(source_path))
    if source_path.is_file():
        _add(
            checks,
            "prepared_source_sha256_matches",
            _sha256_file(source_path) == manifest.source_canonical_input.sha256,
            manifest.source_canonical_input.sha256,
        )
        try:
            expected_rows, source_count, eligible_count = _independent_expected_assignments(
                source_path=source_path,
                manifest=manifest,
                config=config,
            )
            actual_rows = [row.model_dump(mode="json") for row in assignments]
            _add(
                checks,
                "prepared_source_document_count_matches",
                source_count == manifest.source_canonical_input.document_count,
                f"actual={source_count}, declared={manifest.source_canonical_input.document_count}",
            )
            _add(
                checks,
                "prepared_sampling_independently_recomputed",
                expected_rows == actual_rows,
                f"eligible_document_count={eligible_count}",
            )
            if quality is not None:
                _add(
                    checks,
                    "prepared_quality_eligible_count_matches",
                    quality.get("eligible_document_count") == eligible_count,
                    f"actual={eligible_count}",
                )
        except Exception as exc:
            _add(checks, "prepared_sampling_independently_recomputed", False, str(exc))

    _add(checks, "prepared_prediction_blind", manifest.prediction_blind, "must be true")
    _add(checks, "prepared_review_incomplete", not manifest.review_complete, "must be false")
    _add(
        checks,
        "prepared_no_full_corpus_extraction",
        not manifest.full_corpus_entity_extraction_performed,
        "sampling may scan metadata/text but cannot emit full-corpus mentions",
    )
    _add(checks, "prepared_no_canonical_mutation", not manifest.canonical_truth_mutated, "must be false")
    _add(checks, "prepared_not_reconcile_input", not manifest.may_be_used_as_reconcile_input, "must be false")
    _add(checks, "prepared_no_model_selection", not manifest.production_extractor_selected, "must be false")
    _add(checks, "prepared_no_redistribution", not manifest.redistribution_allowed, "must be false")
    _add(checks, "prepared_not_publication_ready", not manifest.publication_ready, "must be false")
    return manifest


def _validate_completed(
    *,
    completed_dir: Path,
    prepared_dir: Path,
    prepared_manifest: ScientificEntityManualReviewPreparedManifest,
    config: ScientificEntityManualReviewConfig,
    checks: list[Check],
) -> ScientificEntityManualReviewCompletionManifest | None:
    _add(checks, "completed_directory_exists", completed_dir.is_dir(), str(completed_dir))
    if not completed_dir.is_dir():
        return None
    _validate_layout_and_checksums(
        directory=completed_dir,
        expected_files=COMPLETED_FILES,
        checksum_files=COMPLETED_CHECKSUM_FILES,
        prefix="completed",
        checks=checks,
    )
    if not COMPLETED_FILES.issubset(
        {path.name for path in completed_dir.iterdir() if path.is_file()}
    ):
        return None
    try:
        completion = ScientificEntityManualReviewCompletionManifest.model_validate(
            _read_json(completed_dir / "completion_manifest.json")
        )
        review = ScientificEntityReviewManifest.model_validate(
            _read_json(completed_dir / "review_manifest.json")
        )
        _add(checks, "completed_manifest_contract", True, completion.schema_version)
        _add(checks, "completed_review_manifest_contract", True, review.schema_version)
    except Exception as exc:
        _add(checks, "completed_manifest_contract", False, str(exc))
        return None

    _add(
        checks,
        "completed_review_id_matches_prepared",
        completion.review_id == prepared_manifest.review_id == review.review_id,
        completion.review_id,
    )
    _add(
        checks,
        "completed_prepared_directory_matches",
        _resolve_project_path(completion.prepared_review.directory_path)
        == prepared_dir.resolve(),
        completion.prepared_review.directory_path,
    )
    _add(
        checks,
        "completed_prepared_manifest_sha256_matches",
        completion.prepared_review.manifest_sha256
        == _sha256_file(prepared_dir / "manifest.json"),
        completion.prepared_review.manifest_sha256,
    )
    prepared_descriptor_matches = (
        completion.prepared_review.review_id == prepared_manifest.review_id
        and completion.prepared_review.status == prepared_manifest.status
        and _resolve_project_path(completion.prepared_review.manifest_path)
        == (prepared_dir / "manifest.json").resolve()
        and _resolve_project_path(completion.prepared_review.sample_documents_path)
        == (prepared_dir / "canonical_documents.sample.jsonl").resolve()
        and completion.prepared_review.sample_documents_sha256
        == prepared_manifest.sample_canonical_input.sha256
        and completion.prepared_review.sample_document_count
        == prepared_manifest.sample_canonical_input.document_count
        and _resolve_project_path(completion.prepared_review.sample_assignments_path)
        == (prepared_dir / "sample_assignments.jsonl").resolve()
        and completion.prepared_review.sample_assignments_sha256
        == prepared_manifest.sample_assignments_sha256
        and _resolve_project_path(completion.prepared_review.annotation_template_path)
        == (prepared_dir / "annotation_template.jsonl").resolve()
        and completion.prepared_review.annotation_template_sha256
        == prepared_manifest.annotation_template_sha256
    )
    _add(
        checks,
        "completed_prepared_descriptor_matches",
        prepared_descriptor_matches,
        "all prepared paths, hashes, counts, status, and identity must match",
    )
    _add(
        checks,
        "completed_review_manifest_sha256_matches",
        completion.review_manifest_sha256
        == _sha256_file(completed_dir / "review_manifest.json"),
        completion.review_manifest_sha256,
    )
    _add(
        checks,
        "completed_reference_sha256_matches",
        completion.reference_mentions_sha256
        == _sha256_file(completed_dir / "reference_mentions.jsonl")
        == review.reference_mentions_sha256,
        completion.reference_mentions_sha256,
    )
    _add(
        checks,
        "completed_audit_sha256_matches",
        completion.annotation_audit_sha256
        == _sha256_file(completed_dir / "annotation_audit_summary.json"),
        completion.annotation_audit_sha256,
    )
    _add(
        checks,
        "completed_review_canonical_input_matches_sample",
        review.canonical_input == prepared_manifest.sample_canonical_input,
        review.canonical_input.path,
    )
    _add(
        checks,
        "completed_review_is_prediction_blind",
        review.prediction_blind and completion.prediction_blind,
        "both manifests must be true",
    )
    _add(
        checks,
        "completed_review_status_candidate",
        review.status.value == "reviewed_candidate",
        review.status.value,
    )
    _add(
        checks,
        "completed_review_metadata_matches_completion",
        review.generated_at_utc == completion.generated_at_utc
        and review.annotation_method == completion.annotation_method
        and review.annotation_guideline_version
        == completion.annotation_guideline_version
        and review.annotation_passes == completion.annotation_passes
        and review.annotator_ids == completion.annotator_ids
        and review.source_fields == list(ScientificEntitySourceField)
        and review.entity_types == list(ScientificEntityType),
        "review and completion annotation provenance must agree",
    )
    _add(
        checks,
        "completed_annotation_policy_matches_config",
        completion.annotation_guideline_version == config.annotation.guideline_version
        and completion.annotation_passes == config.annotation.annotation_passes,
        completion.annotation_guideline_version,
    )
    _add(
        checks,
        "completed_fixture_simulation_matches_prepared",
        completion.fixture_simulation
        == (prepared_manifest.status == ScientificEntityReviewSampleStatus.FIXTURE),
        str(completion.fixture_simulation),
    )
    _add(
        checks,
        "completed_annotation_count_matches_prepared",
        completion.annotation_row_count == prepared_manifest.annotation_row_count,
        f"completed={completion.annotation_row_count}, prepared={prepared_manifest.annotation_row_count}",
    )

    annotations_path = _resolve_project_path(completion.annotations_path)
    expected_annotations_path = completed_dir / "completed_annotations.jsonl"
    _add(
        checks,
        "completed_annotations_path_is_immutable_package_file",
        completion.annotations_file == "completed_annotations.jsonl"
        and annotations_path == expected_annotations_path.resolve(),
        completion.annotations_path,
    )
    _add(checks, "completed_annotations_input_exists", annotations_path.is_file(), str(annotations_path))
    if not annotations_path.is_file():
        return completion
    _add(
        checks,
        "completed_annotations_sha256_matches",
        _sha256_file(annotations_path) == completion.annotations_sha256,
        completion.annotations_sha256,
    )
    try:
        template_payloads = _read_jsonl(
            prepared_dir / "annotation_template.jsonl",
            hard_limit=config.safety.hard_max_annotation_rows,
        )
        annotation_payloads = _read_jsonl(
            annotations_path, hard_limit=config.safety.hard_max_annotation_rows
        )
        prohibited_present = any(
            bool(PROHIBITED_ANNOTATION_KEYS.intersection(row))
            for row in annotation_payloads
        )
        templates = [ScientificEntityBlindAnnotationRow.model_validate(row) for row in template_payloads]
        annotations = [ScientificEntityBlindAnnotationRow.model_validate(row) for row in annotation_payloads]
        template_by_key = {(row.canonical_id, row.source_field): row for row in templates}
        annotation_by_key = {(row.canonical_id, row.source_field): row for row in annotations}
        _add(
            checks,
            "completed_annotation_key_set_exact",
            set(template_by_key) == set(annotation_by_key)
            and len(templates) == len(template_by_key)
            and len(annotations) == len(annotation_by_key),
            "no missing, extra, or duplicate source-field rows",
        )
        _add(
            checks,
            "completed_annotation_rows_complete",
            all(row.annotation_complete for row in annotations),
            f"rows={len(annotations)}",
        )
        _add(
            checks,
            "completed_annotation_prediction_keys_absent",
            not prohibited_present,
            f"prohibited={sorted(PROHIBITED_ANNOTATION_KEYS)}",
        )
        immutable_ok = True
        for key, template in template_by_key.items():
            annotation = annotation_by_key.get(key)
            if annotation is None:
                immutable_ok = False
                continue
            for field_name in (
                "review_id",
                "canonical_id",
                "sample_stratum",
                "enrichment_entity_type",
                "source_field",
                "source_text_sha256",
                "source_text",
            ):
                immutable_ok &= getattr(template, field_name) == getattr(annotation, field_name)
        _add(
            checks,
            "completed_annotation_immutable_fields_preserved",
            immutable_ok,
            "source identity/text/stratum must match template",
        )
    except Exception as exc:
        _add(checks, "completed_annotation_contract", False, str(exc))
        return completion

    try:
        reference_payloads = _read_jsonl(
            completed_dir / "reference_mentions.jsonl",
            hard_limit=config.safety.hard_max_reference_mentions,
        )
        references = [ScientificEntityReferenceMention.model_validate(row) for row in reference_payloads]
        expected_payloads: list[dict[str, Any]] = []
        by_stratum: Counter[ScientificEntitySampleStratum] = Counter()
        by_type: Counter[ScientificEntityType] = Counter()
        uncertain = 0
        for annotation in annotations:
            for mention in annotation.mentions:
                mention_id = build_mention_id(
                    canonical_id=annotation.canonical_id,
                    source_field=annotation.source_field,
                    source_text_sha256=annotation.source_text_sha256,
                    char_start=mention.char_start,
                    char_end=mention.char_end,
                    entity_type=mention.entity_type,
                )
                expected = ScientificEntityReferenceMention(
                    schema_version="scientific_entity_reference_mention_v0.1",
                    reference_id=build_reference_id(
                        review_id=completion.review_id,
                        mention_id=mention_id,
                        annotation_method=completion.annotation_method,
                        annotation_pass=completion.annotation_passes,
                    ),
                    mention_id=mention_id,
                    review_id=completion.review_id,
                    canonical_id=annotation.canonical_id,
                    entity_type=mention.entity_type,
                    source_field=annotation.source_field,
                    source_text_sha256=annotation.source_text_sha256,
                    char_start=mention.char_start,
                    char_end=mention.char_end,
                    surface_text=mention.surface_text,
                    annotation_method=completion.annotation_method,
                    annotation_pass=completion.annotation_passes,
                    uncertain=mention.uncertain,
                )
                validate_reference_mention(
                    expected,
                    source_text=annotation.source_text,
                    review_id=completion.review_id,
                )
                expected_payloads.append(expected.model_dump(mode="json"))
                by_stratum[annotation.sample_stratum] += 1
                by_type[mention.entity_type] += 1
                uncertain += int(mention.uncertain)
        expected_payloads = sorted(
            expected_payloads,
            key=lambda row: (
                row["canonical_id"],
                list(ScientificEntitySourceField).index(ScientificEntitySourceField(row["source_field"])),
                row["char_start"],
                row["char_end"],
                list(ScientificEntityType).index(ScientificEntityType(row["entity_type"])),
                row["reference_id"],
            ),
        )
        actual_payloads = [row.model_dump(mode="json") for row in references]
        _add(
            checks,
            "completed_reference_mentions_independently_recomputed",
            actual_payloads == expected_payloads,
            f"actual={len(actual_payloads)}, expected={len(expected_payloads)}",
        )
        _add(
            checks,
            "completed_reference_count_matches",
            len(references)
            == completion.reference_mention_count
            == review.reference_mention_count,
            f"references={len(references)}",
        )
        _add(
            checks,
            "completed_reference_type_counts_match",
            all(completion.reference_count_by_type[t] == by_type[t] for t in ScientificEntityType),
            str(by_type),
        )
        _add(
            checks,
            "completed_reference_stratum_counts_match",
            all(completion.reference_count_by_stratum[s] == by_stratum[s] for s in ScientificEntitySampleStratum),
            str(by_stratum),
        )
        _add(
            checks,
            "completed_uncertain_count_matches",
            completion.uncertain_reference_mention_count == uncertain,
            f"actual={uncertain}",
        )
    except Exception as exc:
        _add(checks, "completed_reference_contract", False, str(exc))

    try:
        audit = _read_json(completed_dir / "annotation_audit_summary.json")
        expected_audit_keys = {
            "schema_version",
            "review_id",
            "prediction_blind",
            "review_complete",
            "annotation_row_count",
            "completed_annotation_row_count",
            "zero_mention_annotation_row_count",
            "reference_mention_count",
            "uncertain_reference_mention_count",
            "reference_count_by_type",
            "reference_count_by_stratum",
            "automatic_review_approval",
            "production_extractor_selected",
            "publication_ready",
        }
        _add(
            checks,
            "completed_audit_exact_field_set",
            set(audit) == expected_audit_keys,
            f"actual={sorted(audit)}",
        )
        _add(
            checks,
            "completed_audit_review_id_matches",
            audit.get("review_id") == completion.review_id,
            str(audit.get("review_id")),
        )
        expected_type_counts = {
            entity_type.value: by_type[entity_type]
            for entity_type in ScientificEntityType
        }
        expected_stratum_counts = {
            stratum.value: by_stratum[stratum]
            for stratum in ScientificEntitySampleStratum
        }
        _add(
            checks,
            "completed_audit_counts_match",
            audit.get("schema_version")
            == "scientific_entity_manual_review_annotation_audit_v0.1"
            and audit.get("reference_mention_count")
            == completion.reference_mention_count
            and audit.get("annotation_row_count") == completion.annotation_row_count
            and audit.get("completed_annotation_row_count")
            == completion.completed_annotation_row_count
            and audit.get("zero_mention_annotation_row_count")
            == sum(int(not row.mentions) for row in annotations)
            and audit.get("uncertain_reference_mention_count") == uncertain
            and audit.get("reference_count_by_type") == expected_type_counts
            and audit.get("reference_count_by_stratum")
            == expected_stratum_counts,
            "audit counters must match independently parsed annotations",
        )
        _add(
            checks,
            "completed_audit_safety_flags",
            audit.get("prediction_blind") is True
            and audit.get("review_complete") is True
            and audit.get("automatic_review_approval") is False
            and audit.get("production_extractor_selected") is False
            and audit.get("publication_ready") is False,
            "blind review must not imply automatic approval/model/publication",
        )
    except Exception as exc:
        _add(checks, "completed_audit_contract", False, str(exc))

    _add(checks, "completed_review_complete", completion.review_complete, "must be true")
    _add(checks, "completed_evaluation_ready", completion.evaluation_harness_ready, "must be true")
    _add(checks, "completed_no_automatic_approval", not completion.automatic_review_approval, "must be false")
    _add(checks, "completed_no_model_selection", not completion.production_extractor_selected, "must be false")
    _add(checks, "completed_no_full_corpus_authorization", not completion.full_corpus_build_authorized, "must be false")
    _add(checks, "completed_no_canonical_mutation", not completion.canonical_truth_mutated, "must be false")
    _add(checks, "completed_not_reconcile_input", not completion.may_be_used_as_reconcile_input, "must be false")
    _add(checks, "completed_no_redistribution", not completion.redistribution_allowed, "must be false")
    _add(checks, "completed_not_publication_ready", not completion.publication_ready, "must be false")
    return completion


def validate_manual_review_evidence(
    *,
    prepared_dir: Path,
    completed_dir: Path | None = None,
    config_path: Path = DEFAULT_CONFIG_PATH,
    report_dir: Path = DEFAULT_REPORT_DIR,
    write_reports: bool = True,
) -> dict[str, Any]:
    checks: list[Check] = []
    resolved_config = config_path.resolve()
    try:
        config = load_manual_review_config(resolved_config)
        _add(checks, "config_contract", True, config.schema_version)
    except Exception as exc:
        _add(checks, "config_contract", False, str(exc))
        config = None

    prepared_manifest = None
    completion_manifest = None
    if config is not None:
        prepared_manifest = _validate_prepared(
            prepared_dir=prepared_dir.resolve(),
            config_path=resolved_config,
            config=config,
            checks=checks,
        )
        if completed_dir is not None and prepared_manifest is not None:
            completion_manifest = _validate_completed(
                completed_dir=completed_dir.resolve(),
                prepared_dir=prepared_dir.resolve(),
                prepared_manifest=prepared_manifest,
                config=config,
                checks=checks,
            )

    failed_required = [check for check in checks if check.required and not check.ok]
    failed_prepared = [
        check for check in failed_required if not check.name.startswith("completed_")
    ]
    generated_at = datetime.now(timezone.utc)
    report = {
        "schema_version": "scientific_entity_manual_review_evidence_validation_v0.1",
        "report": REPORT_NAME,
        "generated_at_utc": generated_at.isoformat(),
        "prepared_dir": _normalize_path(prepared_dir.resolve()),
        "completed_dir": (
            _normalize_path(completed_dir.resolve()) if completed_dir is not None else None
        ),
        "summary": {
            "ok": not failed_required,
            "total_checks": len(checks),
            "required_failed_count": len(failed_required),
            "prepared_review_id": (
                prepared_manifest.review_id if prepared_manifest is not None else None
            ),
            "sample_document_count": (
                prepared_manifest.sample_canonical_input.document_count
                if prepared_manifest is not None
                else None
            ),
            "completed_review_present": completed_dir is not None,
            "reference_mention_count": (
                completion_manifest.reference_mention_count
                if completion_manifest is not None
                else None
            ),
        },
        "checks": [asdict(check) for check in checks],
        "verdict": {
            "prepared_evidence_valid": prepared_manifest is not None
            and not failed_prepared,
            "completed_review_valid": (
                completion_manifest is not None and not failed_required
            ),
            "prediction_blind": True if prepared_manifest is not None else None,
            "automatic_review_approval": False,
            "production_extractor_selected": False,
            "full_corpus_build_authorized": False,
            "canonical_truth_mutated": False,
            "publication_ready": False,
            "required_failed_checks": [check.name for check in failed_required],
            "next_slice": (
                "run_existing_scientific_entity_evaluation_harness_v0.1"
                if completion_manifest is not None and not failed_required
                else (
                    "complete_prediction_blind_manual_annotation_v0.1"
                    if prepared_manifest is not None and not failed_required
                    else None
                )
            ),
        },
    }
    report["ok"] = report["summary"]["ok"]
    report["required_failed_count"] = report["summary"]["required_failed_count"]
    if write_reports:
        _write_reports(report=report, report_dir=report_dir, generated_at=generated_at)
    return report


def _markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Scientific Entity Manual Review Evidence validation",
        "",
        f"- Generated: `{report['generated_at_utc']}`",
        f"- Status: `{'OK' if report['summary']['ok'] else 'FAILED'}`",
        f"- Total checks: `{report['summary']['total_checks']}`",
        f"- Required failures: `{report['summary']['required_failed_count']}`",
        f"- Review ID: `{report['summary']['prepared_review_id']}`",
        f"- Sample documents: `{report['summary']['sample_document_count']}`",
        f"- Completed review present: `{report['summary']['completed_review_present']}`",
        f"- Reference mentions: `{report['summary']['reference_mention_count']}`",
        "",
        "## Verdict",
        "",
        f"- prepared_evidence_valid: `{report['verdict']['prepared_evidence_valid']}`",
        f"- completed_review_valid: `{report['verdict']['completed_review_valid']}`",
        "- automatic_review_approval: `false`",
        "- production_extractor_selected: `false`",
        "- full_corpus_build_authorized: `false`",
        "- publication_ready: `false`",
        f"- next_slice: `{report['verdict']['next_slice']}`",
        "",
        "## Checks",
        "",
    ]
    for check in report["checks"]:
        marker = "OK" if check["ok"] else "FAILED"
        lines.append(
            f"- [{marker}] `{check['name']}` — {check['details']}"
        )
    return "\n".join(lines) + "\n"


def _write_reports(
    *,
    report: Mapping[str, Any],
    report_dir: Path,
    generated_at: datetime,
) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    history_dir = report_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    timestamp = generated_at.strftime("%Y%m%dT%H%M%S%fZ")
    json_text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    markdown = _markdown(report)
    paths = (
        report_dir / f"{REPORT_NAME}_latest.json",
        report_dir / f"{REPORT_NAME}_latest.md",
        history_dir / f"{REPORT_NAME}_{timestamp}.json",
        history_dir / f"{REPORT_NAME}_{timestamp}.md",
    )
    for path, text in zip(paths, (json_text, markdown, json_text, markdown), strict=True):
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Independently validate bounded Scientific Entity Manual Review Evidence v0.1."
    )
    parser.add_argument("--prepared-dir", type=Path, required=True)
    parser.add_argument("--completed-dir", type=Path, default=None)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--no-write-reports", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = validate_manual_review_evidence(
            prepared_dir=args.prepared_dir,
            completed_dir=args.completed_dir,
            config_path=args.config,
            report_dir=args.report_dir,
            write_reports=not args.no_write_reports,
        )
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 1

    ok = bool(report["summary"]["ok"])
    status = "OK" if ok else "FAILED"
    print(f"[{status}] report={REPORT_NAME}")
    print(f"[{status}] total_checks={report['summary']['total_checks']}")
    print(f"[{status}] required_failed_count={report['summary']['required_failed_count']}")
    print(f"[{status}] review_id={report['summary']['prepared_review_id']}")
    print(f"[{status}] sample_document_count={report['summary']['sample_document_count']}")
    print(f"[{status}] completed_review_present={report['summary']['completed_review_present']}")
    print(f"[{status}] reference_mention_count={report['summary']['reference_mention_count']}")
    print(f"[{status}] next_slice={report['verdict']['next_slice']}")
    if not ok:
        print(f"[{status}] required_failed_checks:")
        for name in report["verdict"]["required_failed_checks"]:
            print(f"- {name}")
    return 1 if args.strict and not ok else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
