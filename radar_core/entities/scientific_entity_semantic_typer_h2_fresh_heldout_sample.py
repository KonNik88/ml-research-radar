from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from radar_core.contracts.scientific_entity_semantic_typer_h2_fresh_heldout_sample import (
    ASSIGNMENT_SCHEMA_VERSION,
    BLIND_ANNOTATION_SCHEMA_VERSION,
    ENTITY_TYPES,
    H2FreshHeldoutSampleAssignment,
    H2FreshHeldoutSampleConfig,
    H2FreshHeldoutSampleManifest,
    MANIFEST_SCHEMA_VERSION,
    canonical_config_sha256,
    load_h2_fresh_heldout_sample_config,
)


REPORT_NAME = "scientific_entity_semantic_typer_h2_fresh_heldout_sample_v03"
REQUIRED_FILES = (
    "annotations_working.jsonl",
    "sample_assignments.jsonl",
    "canonical_documents.sample.jsonl",
    "selected_papers.tsv",
    "exclusion_provenance.json",
    "manifest.json",
    "README.md",
    "checksums.txt",
)
DEVELOPMENT_PACKAGE_SCHEMA_VERSION = "scientific_entity_semantic_prompt_development_package_v0.2a"
PREVIOUS_HELDOUT_MANIFEST_SCHEMA_VERSION = "scientific_entity_fresh_heldout_sample_manifest_v0.2"
H2_FREEZE_MANIFEST_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_frozen_candidate_manifest_v0.3"
H2_FROZEN_DEFINITION_SCHEMA_VERSION = "scientific_entity_semantic_typer_h2_frozen_candidate_definition_v0.3"


class ScientificEntityH2FreshHeldoutSampleError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8") + b"\n"


def _jsonl_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(
        json.dumps(dict(row), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
        for row in rows
    )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ScientificEntityH2FreshHeldoutSampleError(f"Invalid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ScientificEntityH2FreshHeldoutSampleError(f"Expected JSON object: {path}")
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                raise ScientificEntityH2FreshHeldoutSampleError(f"Blank JSONL line: {path}:{line_number}")
            try:
                payload = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise ScientificEntityH2FreshHeldoutSampleError(f"Invalid JSONL: {path}:{line_number}: {exc}") from exc
            if not isinstance(payload, dict):
                raise ScientificEntityH2FreshHeldoutSampleError(f"Expected JSON object: {path}:{line_number}")
            rows.append(payload)
    return rows


def _project_relative_or_absolute(project_root: Path, path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(project_root.resolve())).replace("\\", "/")
    except ValueError:
        return str(resolved).replace("\\", "/")


def _ids_sha256(ids: set[str] | Sequence[str]) -> str:
    return _sha256_bytes(("\n".join(sorted(ids)) + "\n").encode("utf-8"))


def _load_development_exclusion(
    *, development_package_dir: Path, config: H2FreshHeldoutSampleConfig
) -> tuple[set[str], str, str]:
    directory = development_package_dir.resolve()
    manifest_path = directory / "manifest.json"
    canonical_path = directory / "canonical_documents.jsonl"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    if not canonical_path.is_file():
        raise FileNotFoundError(canonical_path)
    manifest = _read_json(manifest_path)
    expected = config.consumed_evidence_exclusion
    if manifest.get("schema_version") != DEVELOPMENT_PACKAGE_SCHEMA_VERSION:
        raise ScientificEntityH2FreshHeldoutSampleError("Development package schema_version drifted")
    if manifest.get("package_id") != expected.development_package_id:
        raise ScientificEntityH2FreshHeldoutSampleError("Development package ID mismatch")
    if manifest.get("combined_document_count") != expected.expected_development_document_count:
        raise ScientificEntityH2FreshHeldoutSampleError("Development package document count mismatch")
    manifest_sha = sha256_file(manifest_path)
    canonical_sha = sha256_file(canonical_path)
    if manifest_sha != expected.expected_development_manifest_sha256:
        raise ScientificEntityH2FreshHeldoutSampleError("Development package manifest SHA-256 mismatch")
    if canonical_sha != expected.expected_development_canonical_sha256:
        raise ScientificEntityH2FreshHeldoutSampleError("Development package canonical SHA-256 mismatch")
    if manifest.get("canonical_documents_sha256") != canonical_sha:
        raise ScientificEntityH2FreshHeldoutSampleError("Development manifest canonical SHA-256 mismatch")
    ids = {str(row.get("canonical_id") or "").strip() for row in _read_jsonl(canonical_path)}
    if "" in ids or len(ids) != expected.expected_development_document_count:
        raise ScientificEntityH2FreshHeldoutSampleError("Development package canonical IDs are invalid or duplicated")
    return ids, manifest_sha, canonical_sha


def _load_previous_heldout_exclusion(
    *, previous_heldout_sample_dir: Path, config: H2FreshHeldoutSampleConfig
) -> tuple[set[str], str, str]:
    directory = previous_heldout_sample_dir.resolve()
    manifest_path = directory / "manifest.json"
    sample_path = directory / "canonical_documents.sample.jsonl"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    if not sample_path.is_file():
        raise FileNotFoundError(sample_path)
    manifest = _read_json(manifest_path)
    expected = config.consumed_evidence_exclusion
    if manifest.get("schema_version") != PREVIOUS_HELDOUT_MANIFEST_SCHEMA_VERSION:
        raise ScientificEntityH2FreshHeldoutSampleError("Previous held-out manifest schema_version drifted")
    if manifest.get("sample_id") != expected.previous_fresh_heldout_sample_id:
        raise ScientificEntityH2FreshHeldoutSampleError("Previous held-out sample ID mismatch")
    if manifest.get("selected_document_count") != expected.expected_previous_heldout_document_count:
        raise ScientificEntityH2FreshHeldoutSampleError("Previous held-out document count mismatch")
    manifest_sha = sha256_file(manifest_path)
    if manifest_sha != expected.expected_previous_heldout_manifest_sha256:
        raise ScientificEntityH2FreshHeldoutSampleError("Previous held-out manifest SHA-256 mismatch")
    ids_from_manifest = [str(value) for value in manifest.get("selected_canonical_ids", [])]
    rows = _read_jsonl(sample_path)
    ids_from_rows = [str(row.get("canonical_id") or "").strip() for row in rows]
    if len(ids_from_rows) != 48 or len(set(ids_from_rows)) != 48 or "" in ids_from_rows:
        raise ScientificEntityH2FreshHeldoutSampleError("Previous held-out sample IDs are invalid or duplicated")
    if sorted(ids_from_rows) != sorted(ids_from_manifest):
        raise ScientificEntityH2FreshHeldoutSampleError("Previous held-out manifest/sample ID mismatch")
    ids_sha = _ids_sha256(set(ids_from_rows))
    if ids_sha != expected.expected_previous_heldout_selected_ids_sha256:
        raise ScientificEntityH2FreshHeldoutSampleError("Previous held-out selected IDs SHA-256 mismatch")
    return set(ids_from_rows), manifest_sha, ids_sha


def _load_frozen_candidate(
    *, frozen_candidate_dir: Path, config: H2FreshHeldoutSampleConfig
) -> tuple[dict[str, Any], str, str]:
    directory = frozen_candidate_dir.resolve()
    manifest_path = directory / "manifest.json"
    definition_path = directory / "frozen_candidate.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    if not definition_path.is_file():
        raise FileNotFoundError(definition_path)
    manifest = _read_json(manifest_path)
    definition = _read_json(definition_path)
    candidate = config.candidate
    manifest_sha = sha256_file(manifest_path)
    definition_sha = sha256_file(definition_path)
    if manifest.get("schema_version") != H2_FREEZE_MANIFEST_SCHEMA_VERSION:
        raise ScientificEntityH2FreshHeldoutSampleError("H2 freeze manifest schema_version drifted")
    if definition.get("schema_version") != H2_FROZEN_DEFINITION_SCHEMA_VERSION:
        raise ScientificEntityH2FreshHeldoutSampleError("H2 frozen definition schema_version drifted")
    if manifest.get("freeze_id") != candidate.freeze_id or directory.name != candidate.freeze_id:
        raise ScientificEntityH2FreshHeldoutSampleError("H2 freeze ID mismatch")
    if manifest.get("candidate_id") != candidate.candidate_id or definition.get("candidate_id") != candidate.candidate_id:
        raise ScientificEntityH2FreshHeldoutSampleError("H2 candidate ID mismatch")
    if manifest.get("candidate_fingerprint_sha256") != candidate.candidate_fingerprint_sha256:
        raise ScientificEntityH2FreshHeldoutSampleError("H2 candidate fingerprint mismatch")
    if definition.get("candidate_fingerprint_sha256") != candidate.candidate_fingerprint_sha256:
        raise ScientificEntityH2FreshHeldoutSampleError("H2 frozen definition fingerprint mismatch")
    if definition.get("candidate_status") != "frozen_for_new_independent_acceptance":
        raise ScientificEntityH2FreshHeldoutSampleError("H2 candidate is not frozen for new independent acceptance")
    if not definition.get("requires_new_disjoint_prediction_blind_heldout"):
        raise ScientificEntityH2FreshHeldoutSampleError("H2 frozen definition does not require a new disjoint held-out")
    if manifest_sha != candidate.expected_freeze_manifest_sha256:
        raise ScientificEntityH2FreshHeldoutSampleError("H2 freeze manifest SHA-256 mismatch")
    if definition_sha != candidate.expected_frozen_candidate_sha256:
        raise ScientificEntityH2FreshHeldoutSampleError("H2 frozen candidate SHA-256 mismatch")
    return definition, manifest_sha, definition_sha


def _load_eligible_canonical_documents(
    *, canonical_path: Path, excluded_ids: set[str]
) -> tuple[list[dict[str, Any]], int, int]:
    documents: list[dict[str, Any]] = []
    seen: set[str] = set()
    total_rows = 0
    excluded_found = 0
    with canonical_path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                raise ScientificEntityH2FreshHeldoutSampleError(f"Blank canonical JSONL line: {canonical_path}:{line_number}")
            total_rows += 1
            try:
                payload = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise ScientificEntityH2FreshHeldoutSampleError(f"Invalid canonical JSONL: {canonical_path}:{line_number}: {exc}") from exc
            if not isinstance(payload, dict):
                raise ScientificEntityH2FreshHeldoutSampleError(f"Expected canonical JSON object: {canonical_path}:{line_number}")
            canonical_id = str(payload.get("canonical_id") or "").strip()
            if not canonical_id:
                raise ScientificEntityH2FreshHeldoutSampleError(f"Missing canonical_id: {canonical_path}:{line_number}")
            if canonical_id in seen:
                raise ScientificEntityH2FreshHeldoutSampleError(f"Duplicate canonical_id: {canonical_id}")
            seen.add(canonical_id)
            if canonical_id in excluded_ids:
                excluded_found += 1
                continue
            title = payload.get("title")
            abstract = payload.get("abstract")
            if not isinstance(title, str) or not title.strip():
                continue
            if not isinstance(abstract, str) or not abstract.strip():
                continue
            documents.append(payload)
    return documents, total_rows, excluded_found


def _term_pattern(term: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", flags=re.IGNORECASE)


def _selection_score(
    *, config: H2FreshHeldoutSampleConfig, stratum: str, canonical_id: str, enrichment_entity_type: str | None = None
) -> str:
    payload = "\0".join([
        "scientific_entity_h2_fresh_heldout_sample_v0.3",
        config.sampling.sampling_seed,
        stratum,
        enrichment_entity_type or "",
        canonical_id,
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _choose_sample(
    *, documents: Sequence[dict[str, Any]], config: H2FreshHeldoutSampleConfig
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: dict[str, dict[str, Any]] = {}
    assignments: list[dict[str, Any]] = []
    patterns = {
        entity_type: tuple(_term_pattern(term) for term in terms)
        for entity_type, terms in config.sampling.enrichment_terms.items()
    }
    pool_limit = config.sampling.candidate_pool_per_stratum
    per_type = config.sampling.type_enriched_documents_per_type

    for entity_type in ENTITY_TYPES:
        candidates: list[tuple[str, dict[str, Any]]] = []
        for document in documents:
            text = f"{document['title']}\n{document['abstract']}"
            if any(pattern.search(text) is not None for pattern in patterns[entity_type]):
                candidates.append((
                    _selection_score(config=config, stratum="type_enriched", canonical_id=str(document["canonical_id"]), enrichment_entity_type=entity_type),
                    document,
                ))
        candidates.sort(key=lambda item: (item[0], str(item[1]["canonical_id"])))
        candidates = candidates[:pool_limit]
        rank = 0
        for score, document in candidates:
            canonical_id = str(document["canonical_id"])
            if canonical_id in selected:
                continue
            rank += 1
            selected[canonical_id] = document
            assignments.append({
                "canonical_id": canonical_id,
                "sample_stratum": "type_enriched",
                "enrichment_entity_type": entity_type,
                "selection_score": score,
                "stratum_rank": rank,
            })
            if rank == per_type:
                break
        if rank != per_type:
            raise ScientificEntityH2FreshHeldoutSampleError(
                f"Insufficient distinct type-enriched candidates for {entity_type}: required={per_type}, selected={rank}"
            )

    uniform_candidates = [
        (_selection_score(config=config, stratum="uniform", canonical_id=str(document["canonical_id"])), document)
        for document in documents
    ]
    uniform_candidates.sort(key=lambda item: (item[0], str(item[1]["canonical_id"])))
    uniform_candidates = uniform_candidates[:pool_limit]
    rank = 0
    for score, document in uniform_candidates:
        canonical_id = str(document["canonical_id"])
        if canonical_id in selected:
            continue
        rank += 1
        selected[canonical_id] = document
        assignments.append({
            "canonical_id": canonical_id,
            "sample_stratum": "uniform",
            "enrichment_entity_type": None,
            "selection_score": score,
            "stratum_rank": rank,
        })
        if rank == config.sampling.uniform_document_count:
            break
    if rank != config.sampling.uniform_document_count:
        raise ScientificEntityH2FreshHeldoutSampleError("Insufficient distinct uniform candidates after enriched-stratum deduplication")
    if len(selected) != config.sampling.expected_document_count:
        raise ScientificEntityH2FreshHeldoutSampleError("Selected document count mismatch")
    documents_out = sorted(selected.values(), key=lambda row: str(row["canonical_id"]))
    assignments.sort(key=lambda row: (
        0 if row["sample_stratum"] == "uniform" else 1,
        row["enrichment_entity_type"] or "",
        row["stratum_rank"],
        row["canonical_id"],
    ))
    return documents_out, assignments


def _default_ids(generated_at_utc: datetime) -> tuple[str, str]:
    stamp = generated_at_utc.strftime("%Y%m%dT%H%M%S%fZ")
    return (
        f"scientific-entity-fresh-heldout-sample-v0.3-{stamp}",
        f"scientific-entity-fresh-heldout-review-v0.3-{stamp}",
    )


def _derive_review_id(sample_id: str) -> str:
    prefix = "scientific-entity-fresh-heldout-sample-v0.3-"
    if not sample_id.startswith(prefix):
        raise ScientificEntityH2FreshHeldoutSampleError("Explicit sample_id must use frozen v0.3 prefix")
    suffix = sample_id[len(prefix):]
    if not suffix:
        raise ScientificEntityH2FreshHeldoutSampleError("sample_id suffix cannot be empty")
    return f"scientific-entity-fresh-heldout-review-v0.3-{suffix}"


def _build_assignments(*, sample_id: str, review_id: str, assignments: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in assignments:
        payload = {"schema_version": ASSIGNMENT_SCHEMA_VERSION, "sample_id": sample_id, "review_id": review_id, **dict(row)}
        result.append(H2FreshHeldoutSampleAssignment.model_validate(payload).model_dump(mode="json"))
    return result


def _build_blank_annotations(
    *, review_id: str, documents: Sequence[Mapping[str, Any]], assignments: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    assignment_by_id = {str(row["canonical_id"]): row for row in assignments}
    rows: list[dict[str, Any]] = []
    for document in documents:
        canonical_id = str(document["canonical_id"])
        assignment = assignment_by_id[canonical_id]
        for source_field in ("title", "abstract"):
            source_text = str(document[source_field])
            rows.append({
                "schema_version": BLIND_ANNOTATION_SCHEMA_VERSION,
                "review_id": review_id,
                "canonical_id": canonical_id,
                "sample_stratum": assignment["sample_stratum"],
                "enrichment_entity_type": assignment["enrichment_entity_type"],
                "source_field": source_field,
                "source_text_sha256": sha256_text(source_text),
                "source_text": source_text,
                "annotation_complete": False,
                "mentions": [],
                "reviewer_note": None,
            })
    rows.sort(key=lambda row: (row["canonical_id"], 0 if row["source_field"] == "title" else 1))
    return rows


def _source_families(document: Mapping[str, Any]) -> list[str]:
    result: set[str] = set()
    sources = document.get("sources")
    if isinstance(sources, list):
        for source in sources:
            if isinstance(source, dict):
                name = source.get("source") or source.get("source_name") or source.get("name")
                if isinstance(name, str) and name.strip():
                    result.add(name.strip())
    source_ids = document.get("source_ids")
    if isinstance(source_ids, dict):
        result.update(str(key).strip() for key in source_ids if str(key).strip())
    return sorted(result)


def _selection_overview_bytes(
    *, documents: Sequence[Mapping[str, Any]], assignments: Sequence[Mapping[str, Any]]
) -> bytes:
    assignment_by_id = {str(row["canonical_id"]): row for row in assignments}
    lines = ["canonical_id\tsample_stratum\tenrichment_entity_type\tyear\tsource_families\ttitle"]
    for document in documents:
        canonical_id = str(document["canonical_id"])
        assignment = assignment_by_id[canonical_id]
        title = str(document.get("title") or "").replace("\t", " ").replace("\n", " ")
        lines.append("\t".join([
            canonical_id,
            str(assignment["sample_stratum"]),
            str(assignment["enrichment_entity_type"] or ""),
            str(document.get("year") or ""),
            ",".join(_source_families(document)),
            title,
        ]))
    return ("\n".join(lines) + "\n").encode("utf-8")


def _readme_bytes(*, sample_id: str, review_id: str, candidate_fingerprint: str, selected_ids_sha256: str) -> bytes:
    text = f"""# Scientific Entity H2 Fresh v0.3 Held-Out Sample

sample_id = `{sample_id}`
review_id = `{review_id}`

This immutable local package contains the new prediction-blind 48-paper held-out
sample for independent acceptance of the already-frozen H2 semantic typer candidate.

The selection excludes all 72 earlier development papers and all 48 papers from
the consumed v0.2c fresh held-out, for a 120-document consumed-evidence boundary.
No H1 or H2 predictions are read or generated during sampling.

frozen_candidate_fingerprint = `{candidate_fingerprint}`
selected_canonical_ids_sha256 = `{selected_ids_sha256}`

`annotations_working.jsonl` is intentionally blank. Human reference annotation
must be completed and frozen before any H2 inference is run on this sample.

This package does not mutate canonical truth, select a production extractor, or
authorize a full-corpus entity build.
"""
    return text.encode("utf-8")


def _compute_materialization(
    *,
    project_root: Path,
    config_path: Path,
    canonical_path: Path,
    development_package_dir: Path,
    previous_heldout_sample_dir: Path,
    frozen_candidate_dir: Path,
    sample_id: str,
    review_id: str,
    generated_at_utc: datetime,
) -> dict[str, Any]:
    config = load_h2_fresh_heldout_sample_config(config_path.resolve())
    dev_ids, dev_manifest_sha, dev_canonical_sha = _load_development_exclusion(
        development_package_dir=development_package_dir, config=config
    )
    old_ids, old_manifest_sha, old_ids_sha = _load_previous_heldout_exclusion(
        previous_heldout_sample_dir=previous_heldout_sample_dir, config=config
    )
    frozen_definition, freeze_manifest_sha, frozen_definition_sha = _load_frozen_candidate(
        frozen_candidate_dir=frozen_candidate_dir, config=config
    )
    consumed_overlap = dev_ids & old_ids
    if consumed_overlap:
        raise ScientificEntityH2FreshHeldoutSampleError(
            f"Consumed development and previous held-out sets overlap: {sorted(consumed_overlap)[:5]}"
        )
    consumed_union = dev_ids | old_ids
    expected_union = config.consumed_evidence_exclusion.expected_union_document_count
    if len(consumed_union) != expected_union:
        raise ScientificEntityH2FreshHeldoutSampleError(
            f"Consumed exclusion union mismatch: expected={expected_union}, actual={len(consumed_union)}"
        )

    eligible, canonical_rows, excluded_found = _load_eligible_canonical_documents(
        canonical_path=canonical_path.resolve(), excluded_ids=consumed_union
    )
    if excluded_found != expected_union:
        raise ScientificEntityH2FreshHeldoutSampleError(
            "Current canonical input does not contain all consumed evidence documents; "
            f"found={excluded_found}, expected={expected_union}"
        )
    selected_documents, raw_assignments = _choose_sample(documents=eligible, config=config)
    selected_ids = {str(row["canonical_id"]) for row in selected_documents}
    dev_overlap = selected_ids & dev_ids
    old_overlap = selected_ids & old_ids
    union_overlap = selected_ids & consumed_union
    if union_overlap:
        raise ScientificEntityH2FreshHeldoutSampleError(
            f"Fresh H2 held-out overlaps consumed evidence: {sorted(union_overlap)[:5]}"
        )

    assignments = _build_assignments(sample_id=sample_id, review_id=review_id, assignments=raw_assignments)
    annotation_rows = _build_blank_annotations(review_id=review_id, documents=selected_documents, assignments=assignments)
    selected_ids_sha = _ids_sha256(selected_ids)

    exclusion_payload = {
        "schema_version": "scientific_entity_semantic_typer_h2_fresh_heldout_exclusion_provenance_v0.3",
        "development_package_id": config.consumed_evidence_exclusion.development_package_id,
        "development_document_count": len(dev_ids),
        "previous_heldout_sample_id": config.consumed_evidence_exclusion.previous_fresh_heldout_sample_id,
        "previous_heldout_document_count": len(old_ids),
        "consumed_set_overlap_count": 0,
        "consumed_union_document_count": len(consumed_union),
        "candidate_id": config.candidate.candidate_id,
        "freeze_id": config.candidate.freeze_id,
        "candidate_fingerprint_sha256": config.candidate.candidate_fingerprint_sha256,
        "h2_model_inference_executed": False,
    }

    file_bytes = {
        "annotations_working.jsonl": _jsonl_bytes(annotation_rows),
        "sample_assignments.jsonl": _jsonl_bytes(assignments),
        "canonical_documents.sample.jsonl": _jsonl_bytes(selected_documents),
        "selected_papers.tsv": _selection_overview_bytes(documents=selected_documents, assignments=assignments),
        "exclusion_provenance.json": _json_bytes(exclusion_payload),
        "README.md": _readme_bytes(
            sample_id=sample_id,
            review_id=review_id,
            candidate_fingerprint=config.candidate.candidate_fingerprint_sha256,
            selected_ids_sha256=selected_ids_sha,
        ),
    }
    file_shas = {filename: _sha256_bytes(payload) for filename, payload in file_bytes.items()}

    manifest_payload = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "sample_id": sample_id,
        "review_id": review_id,
        "generated_at_utc": generated_at_utc.isoformat(),
        "config_path": _project_relative_or_absolute(project_root, config_path),
        "config_sha256": canonical_config_sha256(config),
        "candidate_id": config.candidate.candidate_id,
        "freeze_id": config.candidate.freeze_id,
        "candidate_fingerprint_sha256": config.candidate.candidate_fingerprint_sha256,
        "freeze_manifest_sha256": freeze_manifest_sha,
        "frozen_candidate_sha256": frozen_definition_sha,
        "canonical_input_path": _project_relative_or_absolute(project_root, canonical_path),
        "canonical_input_sha256": sha256_file(canonical_path),
        "canonical_input_row_count": canonical_rows,
        "eligible_document_count_after_all_exclusions": len(eligible),
        "development_package_id": config.consumed_evidence_exclusion.development_package_id,
        "development_package_path": _project_relative_or_absolute(project_root, development_package_dir),
        "development_manifest_sha256": dev_manifest_sha,
        "development_canonical_sha256": dev_canonical_sha,
        "excluded_development_document_count": len(dev_ids),
        "previous_heldout_sample_id": config.consumed_evidence_exclusion.previous_fresh_heldout_sample_id,
        "previous_heldout_sample_path": _project_relative_or_absolute(project_root, previous_heldout_sample_dir),
        "previous_heldout_manifest_sha256": old_manifest_sha,
        "previous_heldout_selected_ids_sha256": old_ids_sha,
        "excluded_previous_heldout_document_count": len(old_ids),
        "consumed_set_overlap_count": len(consumed_overlap),
        "excluded_consumed_union_document_count": len(consumed_union),
        "excluded_consumed_ids_found_in_canonical": excluded_found,
        "sample_development_overlap_count": len(dev_overlap),
        "sample_previous_heldout_overlap_count": len(old_overlap),
        "sample_consumed_union_overlap_count": len(union_overlap),
        "sampling_algorithm": config.sampling.sampling_algorithm,
        "sampling_seed": config.sampling.sampling_seed,
        "candidate_pool_per_stratum": config.sampling.candidate_pool_per_stratum,
        "uniform_document_count": config.sampling.uniform_document_count,
        "type_enriched_documents_per_type": config.sampling.type_enriched_documents_per_type,
        "type_enrichment_terms": config.sampling.enrichment_terms,
        "selected_document_count": len(selected_documents),
        "annotation_row_count": len(annotation_rows),
        "selected_canonical_ids": sorted(selected_ids),
        "prediction_blind": True,
        "annotations_initially_empty": True,
        "candidate_predictions_read_during_sampling": False,
        "h1_predictions_read_during_sampling": False,
        "h2_model_inference_executed": False,
        "evaluation_executed": False,
        "reference_frozen": False,
        "threshold_tuning_executed": False,
        "policy_revision_executed": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "files": file_shas,
        "next_slice": "prediction_blind_manual_annotation_and_reference_freeze_for_h2",
    }
    manifest = H2FreshHeldoutSampleManifest.model_validate(manifest_payload)
    return {
        "config": config,
        "manifest": manifest,
        "manifest_bytes": _json_bytes(manifest.model_dump(mode="json")),
        "file_bytes": file_bytes,
        "selected_documents": selected_documents,
        "assignments": assignments,
        "annotation_rows": annotation_rows,
        "selected_ids_sha256": selected_ids_sha,
        "development_ids": dev_ids,
        "previous_heldout_ids": old_ids,
        "consumed_union_ids": consumed_union,
        "frozen_definition": frozen_definition,
    }


def prepare_h2_fresh_heldout_sample(
    *,
    project_root: Path,
    config_path: Path,
    canonical_path: Path,
    development_package_dir: Path,
    previous_heldout_sample_dir: Path,
    frozen_candidate_dir: Path,
    output_root: Path,
    sample_id: str | None = None,
    execute: bool = False,
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at_utc or datetime.now(timezone.utc)
    if generated_at.tzinfo is None or generated_at.utcoffset() != timezone.utc.utcoffset(generated_at):
        raise ScientificEntityH2FreshHeldoutSampleError("generated_at_utc must be timezone-aware UTC")
    if sample_id is None:
        selected_sample_id, review_id = _default_ids(generated_at)
    else:
        selected_sample_id = sample_id
        review_id = _derive_review_id(sample_id)
    computed = _compute_materialization(
        project_root=project_root.resolve(),
        config_path=config_path.resolve(),
        canonical_path=canonical_path.resolve(),
        development_package_dir=development_package_dir.resolve(),
        previous_heldout_sample_dir=previous_heldout_sample_dir.resolve(),
        frozen_candidate_dir=frozen_candidate_dir.resolve(),
        sample_id=selected_sample_id,
        review_id=review_id,
        generated_at_utc=generated_at,
    )
    manifest: H2FreshHeldoutSampleManifest = computed["manifest"]
    output_dir = output_root.resolve() / selected_sample_id
    if execute and output_dir.exists():
        raise FileExistsError(f"Immutable H2 fresh held-out sample already exists; overwrite forbidden: {output_dir}")
    if execute:
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{selected_sample_id}.tmp-", dir=output_dir.parent))
        try:
            for filename, payload in computed["file_bytes"].items():
                (staging / filename).write_bytes(payload)
            (staging / "manifest.json").write_bytes(computed["manifest_bytes"])
            checksum_lines = [
                f"{sha256_file(staging / filename)}  {filename}" for filename in REQUIRED_FILES[:-1]
            ]
            (staging / "checksums.txt").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8", newline="\n")
            staging.rename(output_dir)
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise
    type_counts = Counter(
        row["enrichment_entity_type"] for row in computed["assignments"] if row["sample_stratum"] == "type_enriched"
    )
    return {
        "report": REPORT_NAME,
        "mode": "execute" if execute else "plan",
        "phase_complete": execute,
        "sample_id": selected_sample_id,
        "review_id": review_id,
        "candidate_id": manifest.candidate_id,
        "candidate_fingerprint_sha256": manifest.candidate_fingerprint_sha256,
        "output_dir": str(output_dir).replace("\\", "/"),
        "canonical_input_row_count": manifest.canonical_input_row_count,
        "excluded_development_document_count": manifest.excluded_development_document_count,
        "excluded_previous_heldout_document_count": manifest.excluded_previous_heldout_document_count,
        "excluded_consumed_union_document_count": manifest.excluded_consumed_union_document_count,
        "excluded_consumed_ids_found_in_canonical": manifest.excluded_consumed_ids_found_in_canonical,
        "sample_consumed_union_overlap_count": manifest.sample_consumed_union_overlap_count,
        "uniform_document_count": manifest.uniform_document_count,
        "type_enriched_document_count": manifest.type_enriched_documents_per_type * len(ENTITY_TYPES),
        "type_enriched_count_by_type": {entity_type: type_counts[entity_type] for entity_type in ENTITY_TYPES},
        "selected_document_count": manifest.selected_document_count,
        "annotation_row_count": manifest.annotation_row_count,
        "selected_canonical_ids_sha256": computed["selected_ids_sha256"],
        "prediction_blind": manifest.prediction_blind,
        "annotations_initially_empty": manifest.annotations_initially_empty,
        "candidate_predictions_read_during_sampling": manifest.candidate_predictions_read_during_sampling,
        "h1_predictions_read_during_sampling": manifest.h1_predictions_read_during_sampling,
        "h2_model_inference_executed": manifest.h2_model_inference_executed,
        "evaluation_executed": manifest.evaluation_executed,
        "reference_frozen": manifest.reference_frozen,
        "threshold_tuning_executed": manifest.threshold_tuning_executed,
        "policy_revision_executed": manifest.policy_revision_executed,
        "canonical_truth_mutated": manifest.canonical_truth_mutated,
        "production_extractor_selected": manifest.production_extractor_selected,
        "full_corpus_build_authorized": manifest.full_corpus_build_authorized,
        "next_slice": manifest.next_slice,
    }


def _parse_checksums(path: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        sha, filename = line.split("  ", 1)
        if filename in checksums:
            raise ScientificEntityH2FreshHeldoutSampleError(f"Duplicate checksums filename: {filename}")
        checksums[filename] = sha
    return checksums


def validate_h2_fresh_heldout_sample(
    *,
    project_root: Path,
    config_path: Path,
    canonical_path: Path,
    development_package_dir: Path,
    previous_heldout_sample_dir: Path,
    frozen_candidate_dir: Path,
    sample_dir: Path,
) -> tuple[list[tuple[str, bool, str]], dict[str, Any]]:
    directory = sample_dir.resolve()
    for filename in REQUIRED_FILES:
        if not (directory / filename).is_file():
            raise FileNotFoundError(directory / filename)
    manifest = H2FreshHeldoutSampleManifest.model_validate(_read_json(directory / "manifest.json"))
    config = load_h2_fresh_heldout_sample_config(config_path.resolve())
    checks: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: Any = "") -> None:
        checks.append((name, bool(ok), str(detail)))

    add("manifest_sample_id_matches_directory", directory.name == manifest.sample_id, directory.name)
    add("candidate_id_matches_config", manifest.candidate_id == config.candidate.candidate_id, manifest.candidate_id)
    add("candidate_fingerprint_matches_config", manifest.candidate_fingerprint_sha256 == config.candidate.candidate_fingerprint_sha256, manifest.candidate_fingerprint_sha256)
    add("config_sha_matches", manifest.config_sha256 == canonical_config_sha256(config), manifest.config_sha256)
    add("canonical_sha_matches", manifest.canonical_input_sha256 == sha256_file(canonical_path.resolve()), manifest.canonical_input_sha256)

    dev_ids, dev_manifest_sha, dev_canonical_sha = _load_development_exclusion(development_package_dir=development_package_dir, config=config)
    old_ids, old_manifest_sha, old_ids_sha = _load_previous_heldout_exclusion(previous_heldout_sample_dir=previous_heldout_sample_dir, config=config)
    _, freeze_manifest_sha, frozen_definition_sha = _load_frozen_candidate(frozen_candidate_dir=frozen_candidate_dir, config=config)
    add("development_manifest_sha_matches", manifest.development_manifest_sha256 == dev_manifest_sha, dev_manifest_sha)
    add("development_canonical_sha_matches", manifest.development_canonical_sha256 == dev_canonical_sha, dev_canonical_sha)
    add("previous_heldout_manifest_sha_matches", manifest.previous_heldout_manifest_sha256 == old_manifest_sha, old_manifest_sha)
    add("previous_heldout_ids_sha_matches", manifest.previous_heldout_selected_ids_sha256 == old_ids_sha, old_ids_sha)
    add("freeze_manifest_sha_matches", manifest.freeze_manifest_sha256 == freeze_manifest_sha, freeze_manifest_sha)
    add("frozen_candidate_sha_matches", manifest.frozen_candidate_sha256 == frozen_definition_sha, frozen_definition_sha)

    consumed_union = dev_ids | old_ids
    add("consumed_sets_disjoint", len(dev_ids & old_ids) == 0, len(dev_ids & old_ids))
    add("consumed_union_count_120", len(consumed_union) == 120, len(consumed_union))

    checksum_map = _parse_checksums(directory / "checksums.txt")
    expected_checksum_files = set(REQUIRED_FILES[:-1])
    add("checksums_coverage_exact", set(checksum_map) == expected_checksum_files, sorted(checksum_map))
    for filename in sorted(expected_checksum_files):
        add(f"checksum:{filename}", checksum_map.get(filename) == sha256_file(directory / filename), checksum_map.get(filename, "missing"))
    file_sha_checks = {filename: sha256_file(directory / filename) for filename in manifest.files}
    add("manifest_file_shas_match", file_sha_checks == manifest.files, json.dumps(file_sha_checks, sort_keys=True))

    recomputed = _compute_materialization(
        project_root=project_root.resolve(),
        config_path=config_path.resolve(),
        canonical_path=canonical_path.resolve(),
        development_package_dir=development_package_dir.resolve(),
        previous_heldout_sample_dir=previous_heldout_sample_dir.resolve(),
        frozen_candidate_dir=frozen_candidate_dir.resolve(),
        sample_id=manifest.sample_id,
        review_id=manifest.review_id,
        generated_at_utc=manifest.generated_at_utc,
    )
    expected_manifest: H2FreshHeldoutSampleManifest = recomputed["manifest"]
    add("manifest_reproduces_from_parents", manifest.model_dump(mode="json") == expected_manifest.model_dump(mode="json"), manifest.sample_id)
    for filename, payload in recomputed["file_bytes"].items():
        add(f"reproduced_bytes:{filename}", (directory / filename).read_bytes() == payload, filename)
    add("reproduced_manifest_bytes", (directory / "manifest.json").read_bytes() == recomputed["manifest_bytes"], "manifest.json")

    sample_rows = _read_jsonl(directory / "canonical_documents.sample.jsonl")
    selected_ids = [str(row.get("canonical_id") or "") for row in sample_rows]
    add("selected_document_count_48", len(sample_rows) == 48, len(sample_rows))
    add("selected_ids_unique", len(set(selected_ids)) == 48, len(set(selected_ids)))
    add("development_overlap_zero", len(set(selected_ids) & dev_ids) == 0, len(set(selected_ids) & dev_ids))
    add("previous_heldout_overlap_zero", len(set(selected_ids) & old_ids) == 0, len(set(selected_ids) & old_ids))
    add("consumed_union_overlap_zero", len(set(selected_ids) & consumed_union) == 0, len(set(selected_ids) & consumed_union))

    assignment_rows = [H2FreshHeldoutSampleAssignment.model_validate(row) for row in _read_jsonl(directory / "sample_assignments.jsonl")]
    uniform = [row for row in assignment_rows if row.sample_stratum == "uniform"]
    enriched = [row for row in assignment_rows if row.sample_stratum == "type_enriched"]
    add("assignment_count_48", len(assignment_rows) == 48, len(assignment_rows))
    add("uniform_count_24", len(uniform) == 24, len(uniform))
    add("type_enriched_count_24", len(enriched) == 24, len(enriched))
    enriched_counts = Counter(row.enrichment_entity_type for row in enriched)
    for entity_type in ENTITY_TYPES:
        add(f"type_enriched_count:{entity_type}", enriched_counts[entity_type] == 4, enriched_counts[entity_type])

    annotation_rows = _read_jsonl(directory / "annotations_working.jsonl")
    add("annotation_row_count_96", len(annotation_rows) == 96, len(annotation_rows))
    annotation_ids = Counter(str(row.get("canonical_id") or "") for row in annotation_rows)
    add("two_annotation_rows_per_document", set(annotation_ids) == set(selected_ids) and all(value == 2 for value in annotation_ids.values()), len(annotation_ids))
    blank_ok = all(
        row.get("schema_version") == BLIND_ANNOTATION_SCHEMA_VERSION
        and row.get("review_id") == manifest.review_id
        and row.get("annotation_complete") is False
        and row.get("mentions") == []
        and row.get("reviewer_note") is None
        for row in annotation_rows
    )
    add("annotations_are_blank_prediction_blind_template", blank_ok, len(annotation_rows))
    forbidden_prediction_keys = {
        "prediction", "predicted_type", "candidate_type", "selected_score", "score_margin", "per_type_scores"
    }
    no_prediction_fields = all(not (forbidden_prediction_keys & set(row)) for row in annotation_rows)
    add("annotation_rows_contain_no_prediction_fields", no_prediction_fields, "")

    by_id = {str(row["canonical_id"]): row for row in sample_rows}
    source_ok = True
    for row in annotation_rows:
        canonical_id = str(row.get("canonical_id") or "")
        source_field = row.get("source_field")
        if source_field not in {"title", "abstract"} or canonical_id not in by_id:
            source_ok = False
            continue
        source_text = str(by_id[canonical_id][source_field])
        if row.get("source_text") != source_text or row.get("source_text_sha256") != sha256_text(source_text):
            source_ok = False
    add("annotation_source_text_and_hashes_match_sample", source_ok, "")

    safety_false = all(
        getattr(manifest, key) is False
        for key in (
            "candidate_predictions_read_during_sampling",
            "h1_predictions_read_during_sampling",
            "h2_model_inference_executed",
            "evaluation_executed",
            "reference_frozen",
            "threshold_tuning_executed",
            "policy_revision_executed",
            "canonical_truth_mutated",
            "production_extractor_selected",
            "full_corpus_build_authorized",
        )
    )
    add("safety_flags_remain_false", safety_false, "")
    add("prediction_blind_true", manifest.prediction_blind is True, "")
    add("annotations_initially_empty_true", manifest.annotations_initially_empty is True, "")
    add("next_slice_is_h2_manual_annotation_reference_freeze", manifest.next_slice == "prediction_blind_manual_annotation_and_reference_freeze_for_h2", manifest.next_slice)

    failed = [name for name, ok, _ in checks if not ok]
    summary = {
        "report": REPORT_NAME,
        "sample_id": manifest.sample_id,
        "review_id": manifest.review_id,
        "candidate_id": manifest.candidate_id,
        "candidate_fingerprint_sha256": manifest.candidate_fingerprint_sha256,
        "selected_document_count": len(sample_rows),
        "annotation_row_count": len(annotation_rows),
        "uniform_document_count": len(uniform),
        "type_enriched_document_count": len(enriched),
        "excluded_development_document_count": len(dev_ids),
        "excluded_previous_heldout_document_count": len(old_ids),
        "excluded_consumed_union_document_count": len(consumed_union),
        "sample_consumed_union_overlap_count": len(set(selected_ids) & consumed_union),
        "selected_canonical_ids_sha256": recomputed["selected_ids_sha256"],
        "prediction_blind": manifest.prediction_blind,
        "annotations_initially_empty": manifest.annotations_initially_empty,
        "candidate_predictions_read_during_sampling": manifest.candidate_predictions_read_during_sampling,
        "h1_predictions_read_during_sampling": manifest.h1_predictions_read_during_sampling,
        "h2_model_inference_executed": manifest.h2_model_inference_executed,
        "evaluation_executed": manifest.evaluation_executed,
        "reference_frozen": manifest.reference_frozen,
        "threshold_tuning_executed": manifest.threshold_tuning_executed,
        "policy_revision_executed": manifest.policy_revision_executed,
        "canonical_truth_mutated": manifest.canonical_truth_mutated,
        "production_extractor_selected": manifest.production_extractor_selected,
        "full_corpus_build_authorized": manifest.full_corpus_build_authorized,
        "total_checks": len(checks),
        "required_failed_count": len(failed),
        "next_slice": manifest.next_slice,
    }
    return checks, summary
