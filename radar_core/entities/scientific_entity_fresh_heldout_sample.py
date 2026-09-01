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

from radar_core.contracts.scientific_entity_fresh_heldout_gate import (
    ENTITY_TYPES,
    ScientificEntityFreshHeldoutGateConfig,
    canonical_config_sha256,
    load_scientific_entity_fresh_heldout_gate_config,
)
from radar_core.contracts.scientific_entity_fresh_heldout_sample import (
    BLIND_ANNOTATION_SCHEMA_VERSION,
    SAMPLE_ASSIGNMENT_SCHEMA_VERSION,
    SAMPLE_MANIFEST_SCHEMA_VERSION,
    FreshHeldoutSampleAssignment,
    FreshHeldoutSampleManifest,
)


REPORT_NAME = "scientific_entity_fresh_heldout_sample_v02"
REQUIRED_FILES = (
    "annotations_working.jsonl",
    "sample_assignments.jsonl",
    "canonical_documents.sample.jsonl",
    "selected_papers.tsv",
    "manifest.json",
    "README.md",
    "checksums.txt",
)
DEVELOPMENT_PACKAGE_MANIFEST_SCHEMA_VERSION = (
    "scientific_entity_semantic_prompt_development_package_v0.2a"
)


class ScientificEntityFreshHeldoutSampleError(RuntimeError):
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
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ScientificEntityFreshHeldoutSampleError(
            f"Invalid JSON: {path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ScientificEntityFreshHeldoutSampleError(f"Expected JSON object: {path}")
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                raise ScientificEntityFreshHeldoutSampleError(
                    f"Blank JSONL line is forbidden: {path}:{line_number}"
                )
            try:
                payload = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise ScientificEntityFreshHeldoutSampleError(
                    f"Invalid JSONL: {path}:{line_number}: {exc}"
                ) from exc
            if not isinstance(payload, dict):
                raise ScientificEntityFreshHeldoutSampleError(
                    f"Expected JSON object: {path}:{line_number}"
                )
            rows.append(payload)
    return rows


def _project_relative_or_absolute(project_root: Path, path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(project_root.resolve())).replace("\\", "/")
    except ValueError:
        return str(resolved).replace("\\", "/")


def _term_pattern(term: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", flags=re.IGNORECASE)


def _term_patterns(
    config: ScientificEntityFreshHeldoutGateConfig,
) -> dict[str, tuple[re.Pattern[str], ...]]:
    return {
        entity_type: tuple(_term_pattern(term) for term in terms)
        for entity_type, terms in config.sampling.enrichment_terms.items()
    }


def _matches_type(
    document: Mapping[str, Any],
    entity_type: str,
    patterns: Mapping[str, Sequence[re.Pattern[str]]],
) -> bool:
    text = f"{document['title']}\n{document['abstract']}"
    return any(pattern.search(text) is not None for pattern in patterns[entity_type])


def _selection_score(
    *,
    config: ScientificEntityFreshHeldoutGateConfig,
    stratum: str,
    canonical_id: str,
    enrichment_entity_type: str | None = None,
) -> str:
    payload = "\0".join(
        [
            "scientific_entity_review_sample_v0.2",
            config.sampling.sampling_seed,
            stratum,
            enrichment_entity_type or "",
            canonical_id,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_development_exclusion(
    *,
    development_package_dir: Path,
    config: ScientificEntityFreshHeldoutGateConfig,
) -> tuple[set[str], dict[str, Any], str, str]:
    package_dir = development_package_dir.resolve()
    manifest_path = package_dir / "manifest.json"
    canonical_path = package_dir / "canonical_documents.jsonl"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    if not canonical_path.is_file():
        raise FileNotFoundError(canonical_path)

    manifest = _read_json(manifest_path)
    if manifest.get("schema_version") != DEVELOPMENT_PACKAGE_MANIFEST_SCHEMA_VERSION:
        raise ScientificEntityFreshHeldoutSampleError(
            "Development package schema_version drifted"
        )
    if manifest.get("package_id") != config.development_exclusion.development_package_id:
        raise ScientificEntityFreshHeldoutSampleError(
            "Development package ID does not match frozen held-out gate"
        )
    if (
        manifest.get("combined_document_count")
        != config.development_exclusion.expected_consumed_document_count
    ):
        raise ScientificEntityFreshHeldoutSampleError(
            "Development package document count does not match frozen held-out gate"
        )
    canonical_sha = sha256_file(canonical_path)
    if canonical_sha != manifest.get("canonical_documents_sha256"):
        raise ScientificEntityFreshHeldoutSampleError(
            "Development package canonical SHA-256 mismatch"
        )

    ids: set[str] = set()
    for row in _read_jsonl(canonical_path):
        canonical_id = str(row.get("canonical_id") or "").strip()
        if not canonical_id:
            raise ScientificEntityFreshHeldoutSampleError(
                "Development package contains missing canonical_id"
            )
        if canonical_id in ids:
            raise ScientificEntityFreshHeldoutSampleError(
                f"Duplicate development canonical_id: {canonical_id}"
            )
        ids.add(canonical_id)

    expected = config.development_exclusion.expected_consumed_document_count
    if len(ids) != expected:
        raise ScientificEntityFreshHeldoutSampleError(
            f"Development exclusion must contain exactly {expected} IDs; actual={len(ids)}"
        )
    return ids, manifest, sha256_file(manifest_path), canonical_sha


def _load_eligible_canonical_documents(
    *,
    canonical_path: Path,
    excluded_ids: set[str],
) -> tuple[list[dict[str, Any]], int, int]:
    documents: list[dict[str, Any]] = []
    seen: set[str] = set()
    total_rows = 0
    excluded_found = 0

    with canonical_path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                raise ScientificEntityFreshHeldoutSampleError(
                    f"Blank canonical JSONL line: {canonical_path}:{line_number}"
                )
            total_rows += 1
            try:
                payload = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise ScientificEntityFreshHeldoutSampleError(
                    f"Invalid canonical JSONL: {canonical_path}:{line_number}: {exc}"
                ) from exc
            if not isinstance(payload, dict):
                raise ScientificEntityFreshHeldoutSampleError(
                    f"Expected canonical JSON object: {canonical_path}:{line_number}"
                )

            canonical_id = str(payload.get("canonical_id") or "").strip()
            if not canonical_id:
                raise ScientificEntityFreshHeldoutSampleError(
                    f"Missing canonical_id: {canonical_path}:{line_number}"
                )
            if canonical_id in seen:
                raise ScientificEntityFreshHeldoutSampleError(
                    f"Duplicate canonical_id in canonical input: {canonical_id}"
                )
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


def _choose_sample(
    *,
    documents: Sequence[dict[str, Any]],
    config: ScientificEntityFreshHeldoutGateConfig,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected: dict[str, dict[str, Any]] = {}
    assignments: list[dict[str, Any]] = []
    patterns = _term_patterns(config)
    per_type = config.sampling.type_enriched_documents_per_type
    pool_limit = config.sampling.candidate_pool_per_stratum

    for entity_type in ENTITY_TYPES:
        candidates = [
            (
                _selection_score(
                    config=config,
                    stratum="type_enriched",
                    enrichment_entity_type=entity_type,
                    canonical_id=str(document["canonical_id"]),
                ),
                document,
            )
            for document in documents
            if _matches_type(document, entity_type, patterns)
        ]
        candidates.sort(key=lambda item: (item[0], str(item[1]["canonical_id"])))
        candidates = candidates[:pool_limit]

        rank = 0
        for score, document in candidates:
            canonical_id = str(document["canonical_id"])
            if canonical_id in selected:
                continue
            rank += 1
            selected[canonical_id] = document
            assignments.append(
                {
                    "canonical_id": canonical_id,
                    "sample_stratum": "type_enriched",
                    "enrichment_entity_type": entity_type,
                    "selection_score": score,
                    "stratum_rank": rank,
                }
            )
            if rank == per_type:
                break

        if rank != per_type:
            raise ScientificEntityFreshHeldoutSampleError(
                f"Insufficient distinct type-enriched candidates for {entity_type}: "
                f"required={per_type}, selected={rank}"
            )

    uniform_candidates = [
        (
            _selection_score(
                config=config,
                stratum="uniform",
                canonical_id=str(document["canonical_id"]),
            ),
            document,
        )
        for document in documents
    ]
    uniform_candidates.sort(key=lambda item: (item[0], str(item[1]["canonical_id"])))
    uniform_candidates = uniform_candidates[:pool_limit]

    uniform_rank = 0
    for score, document in uniform_candidates:
        canonical_id = str(document["canonical_id"])
        if canonical_id in selected:
            continue
        uniform_rank += 1
        selected[canonical_id] = document
        assignments.append(
            {
                "canonical_id": canonical_id,
                "sample_stratum": "uniform",
                "enrichment_entity_type": None,
                "selection_score": score,
                "stratum_rank": uniform_rank,
            }
        )
        if uniform_rank == config.sampling.uniform_document_count:
            break

    if uniform_rank != config.sampling.uniform_document_count:
        raise ScientificEntityFreshHeldoutSampleError(
            "Insufficient distinct uniform candidates after enriched-stratum deduplication"
        )

    if len(selected) != config.sampling.expected_document_count:
        raise ScientificEntityFreshHeldoutSampleError(
            f"Selected document count mismatch: expected={config.sampling.expected_document_count}, "
            f"actual={len(selected)}"
        )

    selected_documents = sorted(
        selected.values(), key=lambda row: str(row["canonical_id"])
    )
    assignments.sort(
        key=lambda row: (
            0 if row["sample_stratum"] == "uniform" else 1,
            row["enrichment_entity_type"] or "",
            row["stratum_rank"],
            row["canonical_id"],
        )
    )
    return selected_documents, assignments


def _default_ids(generated_at_utc: datetime) -> tuple[str, str]:
    stamp = generated_at_utc.strftime("%Y%m%dT%H%M%S%fZ")
    return (
        f"scientific-entity-fresh-heldout-sample-v0.2-{stamp}",
        f"scientific-entity-fresh-heldout-review-v0.2-{stamp}",
    )


def _derive_review_id(sample_id: str) -> str:
    prefix = "scientific-entity-fresh-heldout-sample-v0.2-"
    if not sample_id.startswith(prefix):
        raise ScientificEntityFreshHeldoutSampleError(
            "Explicit sample_id must use frozen v0.2 prefix"
        )
    suffix = sample_id[len(prefix):]
    if not suffix:
        raise ScientificEntityFreshHeldoutSampleError("sample_id suffix cannot be empty")
    return f"scientific-entity-fresh-heldout-review-v0.2-{suffix}"


def _build_assignments(
    *,
    sample_id: str,
    review_id: str,
    assignments: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in assignments:
        payload = {
            "schema_version": SAMPLE_ASSIGNMENT_SCHEMA_VERSION,
            "sample_id": sample_id,
            "review_id": review_id,
            **dict(row),
        }
        validated = FreshHeldoutSampleAssignment.model_validate(payload)
        result.append(validated.model_dump(mode="json"))
    return result


def _build_blank_annotations(
    *,
    review_id: str,
    documents: Sequence[Mapping[str, Any]],
    assignments: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    assignment_by_id = {str(row["canonical_id"]): row for row in assignments}
    rows: list[dict[str, Any]] = []

    for document in documents:
        canonical_id = str(document["canonical_id"])
        assignment = assignment_by_id[canonical_id]
        for source_field in ("title", "abstract"):
            source_text = document[source_field]
            rows.append(
                {
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
                }
            )

    rows.sort(
        key=lambda row: (
            row["canonical_id"],
            0 if row["source_field"] == "title" else 1,
        )
    )
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
        for key in source_ids:
            if isinstance(key, str) and key.strip():
                result.add(key.strip())
    return sorted(result)


def _selection_overview_bytes(
    *,
    documents: Sequence[Mapping[str, Any]],
    assignments: Sequence[Mapping[str, Any]],
) -> bytes:
    assignment_by_id = {str(row["canonical_id"]): row for row in assignments}
    lines = [
        "canonical_id\tsample_stratum\tenrichment_entity_type\tyear\tsource_families\ttitle"
    ]
    for document in documents:
        canonical_id = str(document["canonical_id"])
        assignment = assignment_by_id[canonical_id]
        title = str(document.get("title") or "").replace("\t", " ").replace("\n", " ")
        lines.append(
            "\t".join(
                [
                    canonical_id,
                    str(assignment["sample_stratum"]),
                    str(assignment["enrichment_entity_type"] or ""),
                    str(document.get("year") or ""),
                    ",".join(_source_families(document)),
                    title,
                ]
            )
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def _readme_bytes(
    *,
    sample_id: str,
    review_id: str,
    selected_ids_sha256: str,
) -> bytes:
    text = f"""# Scientific Entity Fresh v0.2 Held-Out Sample

sample_id = `{sample_id}`
review_id = `{review_id}`

This immutable local package contains the new prediction-blind 48-paper
independent v0.2 held-out sample.

It was selected deterministically after excluding all 72 consumed v0.2
development papers. Candidate predictions were not read or generated.

`annotations_working.jsonl` is intentionally blank and must be completed
prediction-blind before the frozen v0.2c candidate may be run.

selected_canonical_ids_sha256 = `{selected_ids_sha256}`

This package does not select a production extractor and does not authorize
a full-corpus entity build.
"""
    return text.encode("utf-8")


def _compute_materialization(
    *,
    project_root: Path,
    config_path: Path,
    canonical_path: Path,
    development_package_dir: Path,
    sample_id: str,
    review_id: str,
    generated_at_utc: datetime,
) -> dict[str, Any]:
    config = load_scientific_entity_fresh_heldout_gate_config(config_path.resolve())
    excluded_ids, dev_manifest, dev_manifest_sha, dev_canonical_sha = (
        _load_development_exclusion(
            development_package_dir=development_package_dir,
            config=config,
        )
    )

    eligible, canonical_rows, excluded_found = _load_eligible_canonical_documents(
        canonical_path=canonical_path.resolve(),
        excluded_ids=excluded_ids,
    )
    expected_excluded = config.development_exclusion.expected_consumed_document_count
    if excluded_found != expected_excluded:
        raise ScientificEntityFreshHeldoutSampleError(
            "Current canonical input does not contain all consumed development papers; "
            f"found={excluded_found}, expected={expected_excluded}"
        )

    selected_documents, raw_assignments = _choose_sample(
        documents=eligible,
        config=config,
    )
    selected_ids = {str(row["canonical_id"]) for row in selected_documents}
    overlap = selected_ids & excluded_ids
    if overlap:
        raise ScientificEntityFreshHeldoutSampleError(
            f"Fresh held-out/development overlap detected: {sorted(overlap)[:5]}"
        )

    assignments = _build_assignments(
        sample_id=sample_id,
        review_id=review_id,
        assignments=raw_assignments,
    )
    annotation_rows = _build_blank_annotations(
        review_id=review_id,
        documents=selected_documents,
        assignments=assignments,
    )

    selected_id_lines = "\n".join(sorted(selected_ids)) + "\n"
    selected_ids_sha = _sha256_bytes(selected_id_lines.encode("utf-8"))

    annotation_bytes = _jsonl_bytes(annotation_rows)
    assignment_bytes = _jsonl_bytes(assignments)
    sample_bytes = _jsonl_bytes(selected_documents)
    overview_bytes = _selection_overview_bytes(
        documents=selected_documents,
        assignments=assignments,
    )
    readme_bytes = _readme_bytes(
        sample_id=sample_id,
        review_id=review_id,
        selected_ids_sha256=selected_ids_sha,
    )

    file_bytes = {
        "annotations_working.jsonl": annotation_bytes,
        "sample_assignments.jsonl": assignment_bytes,
        "canonical_documents.sample.jsonl": sample_bytes,
        "selected_papers.tsv": overview_bytes,
        "README.md": readme_bytes,
    }
    file_shas = {
        filename: _sha256_bytes(payload)
        for filename, payload in file_bytes.items()
    }

    manifest_payload = {
        "schema_version": SAMPLE_MANIFEST_SCHEMA_VERSION,
        "sample_id": sample_id,
        "review_id": review_id,
        "generated_at_utc": generated_at_utc.isoformat(),
        "gate_config_path": _project_relative_or_absolute(project_root, config_path),
        "gate_config_sha256": canonical_config_sha256(config),
        "candidate_id": config.candidate.candidate_id,
        "canonical_input_path": _project_relative_or_absolute(project_root, canonical_path),
        "canonical_input_sha256": sha256_file(canonical_path),
        "canonical_input_row_count": canonical_rows,
        "eligible_non_development_document_count": len(eligible),
        "development_package_id": dev_manifest["package_id"],
        "development_package_path": _project_relative_or_absolute(
            project_root, development_package_dir
        ),
        "development_package_manifest_sha256": dev_manifest_sha,
        "development_package_canonical_sha256": dev_canonical_sha,
        "excluded_development_document_count": len(excluded_ids),
        "excluded_development_ids_found_in_canonical": excluded_found,
        "heldout_development_overlap_count": 0,
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
        "model_inference_executed": False,
        "evaluation_executed": False,
        "fresh_heldout_reference_consumed": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "files": file_shas,
        "next_slice": "prediction_blind_manual_annotation_and_reference_freeze",
    }
    manifest = FreshHeldoutSampleManifest.model_validate(manifest_payload)
    manifest_bytes = _json_bytes(manifest.model_dump(mode="json"))

    return {
        "config": config,
        "manifest": manifest,
        "manifest_bytes": manifest_bytes,
        "file_bytes": file_bytes,
        "selected_documents": selected_documents,
        "assignments": assignments,
        "annotation_rows": annotation_rows,
        "selected_ids_sha256": selected_ids_sha,
        "development_ids": excluded_ids,
    }


def prepare_fresh_heldout_sample(
    *,
    project_root: Path,
    config_path: Path,
    canonical_path: Path,
    development_package_dir: Path,
    output_root: Path,
    sample_id: str | None = None,
    execute: bool = False,
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_at_utc or datetime.now(timezone.utc)
    if generated_at.tzinfo is None or generated_at.utcoffset() != timezone.utc.utcoffset(generated_at):
        raise ScientificEntityFreshHeldoutSampleError(
            "generated_at_utc must be timezone-aware UTC"
        )

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
        sample_id=selected_sample_id,
        review_id=review_id,
        generated_at_utc=generated_at,
    )
    manifest: FreshHeldoutSampleManifest = computed["manifest"]
    output_dir = output_root.resolve() / selected_sample_id

    if execute and output_dir.exists():
        raise FileExistsError(
            f"Immutable fresh held-out sample already exists; overwrite forbidden: {output_dir}"
        )

    if execute:
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(
            tempfile.mkdtemp(prefix=f".{selected_sample_id}.tmp-", dir=output_dir.parent)
        )
        try:
            for filename, payload in computed["file_bytes"].items():
                (staging / filename).write_bytes(payload)
            (staging / "manifest.json").write_bytes(computed["manifest_bytes"])
            checksum_lines = [
                f"{sha256_file(staging / filename)}  {filename}"
                for filename in REQUIRED_FILES[:-1]
            ]
            (staging / "checksums.txt").write_text(
                "\n".join(checksum_lines) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            staging.rename(output_dir)
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise

    type_counts = Counter(
        row["enrichment_entity_type"]
        for row in computed["assignments"]
        if row["sample_stratum"] == "type_enriched"
    )
    return {
        "report": REPORT_NAME,
        "mode": "execute" if execute else "plan",
        "phase_complete": execute,
        "sample_id": selected_sample_id,
        "review_id": review_id,
        "output_dir": str(output_dir).replace("\\", "/"),
        "canonical_input_row_count": manifest.canonical_input_row_count,
        "eligible_non_development_document_count": manifest.eligible_non_development_document_count,
        "excluded_development_document_count": manifest.excluded_development_document_count,
        "excluded_development_ids_found_in_canonical": manifest.excluded_development_ids_found_in_canonical,
        "heldout_development_overlap_count": manifest.heldout_development_overlap_count,
        "uniform_document_count": manifest.uniform_document_count,
        "type_enriched_document_count": manifest.type_enriched_documents_per_type * len(ENTITY_TYPES),
        "type_enriched_count_by_type": {
            entity_type: type_counts[entity_type] for entity_type in ENTITY_TYPES
        },
        "selected_document_count": manifest.selected_document_count,
        "annotation_row_count": manifest.annotation_row_count,
        "selected_canonical_ids_sha256": computed["selected_ids_sha256"],
        "annotations_initially_empty": manifest.annotations_initially_empty,
        "prediction_blind": manifest.prediction_blind,
        "candidate_predictions_read_during_sampling": manifest.candidate_predictions_read_during_sampling,
        "model_inference_executed": manifest.model_inference_executed,
        "evaluation_executed": manifest.evaluation_executed,
        "fresh_heldout_reference_consumed": manifest.fresh_heldout_reference_consumed,
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
            raise ScientificEntityFreshHeldoutSampleError(
                f"Duplicate checksums filename: {filename}"
            )
        checksums[filename] = sha
    return checksums


def validate_fresh_heldout_sample(
    *,
    project_root: Path,
    config_path: Path,
    canonical_path: Path,
    development_package_dir: Path,
    sample_dir: Path,
) -> tuple[list[tuple[str, bool, str]], dict[str, Any]]:
    directory = sample_dir.resolve()
    for filename in REQUIRED_FILES:
        if not (directory / filename).is_file():
            raise FileNotFoundError(directory / filename)

    manifest = FreshHeldoutSampleManifest.model_validate(
        _read_json(directory / "manifest.json")
    )
    config = load_scientific_entity_fresh_heldout_gate_config(config_path.resolve())

    checks: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: Any = "") -> None:
        checks.append((name, bool(ok), str(detail)))

    add("manifest_sample_id_matches_directory", directory.name == manifest.sample_id, directory.name)
    add("manifest_candidate_matches_gate", manifest.candidate_id == config.candidate.candidate_id, manifest.candidate_id)
    add("manifest_gate_config_sha_matches", manifest.gate_config_sha256 == canonical_config_sha256(config), manifest.gate_config_sha256)
    add("canonical_sha_matches_manifest", sha256_file(canonical_path.resolve()) == manifest.canonical_input_sha256, manifest.canonical_input_sha256)

    dev_ids, dev_manifest, dev_manifest_sha, dev_canonical_sha = _load_development_exclusion(
        development_package_dir=development_package_dir.resolve(),
        config=config,
    )
    add("development_package_id_matches", manifest.development_package_id == dev_manifest["package_id"], manifest.development_package_id)
    add("development_manifest_sha_matches", manifest.development_package_manifest_sha256 == dev_manifest_sha, dev_manifest_sha)
    add("development_canonical_sha_matches", manifest.development_package_canonical_sha256 == dev_canonical_sha, dev_canonical_sha)

    checksum_map = _parse_checksums(directory / "checksums.txt")
    expected_checksum_files = set(REQUIRED_FILES[:-1])
    add("checksums_coverage_exact", set(checksum_map) == expected_checksum_files, sorted(checksum_map))
    for filename in sorted(expected_checksum_files):
        add(f"checksum:{filename}", checksum_map.get(filename) == sha256_file(directory / filename), checksum_map.get(filename, "missing"))

    file_sha_checks = {
        filename: sha256_file(directory / filename)
        for filename in manifest.files
    }
    add("manifest_file_shas_match", file_sha_checks == manifest.files, json.dumps(file_sha_checks, sort_keys=True))

    recomputed = _compute_materialization(
        project_root=project_root.resolve(),
        config_path=config_path.resolve(),
        canonical_path=canonical_path.resolve(),
        development_package_dir=development_package_dir.resolve(),
        sample_id=manifest.sample_id,
        review_id=manifest.review_id,
        generated_at_utc=manifest.generated_at_utc,
    )
    expected_manifest: FreshHeldoutSampleManifest = recomputed["manifest"]

    add("manifest_reproduces_from_parents", manifest.model_dump(mode="json") == expected_manifest.model_dump(mode="json"), manifest.sample_id)
    for filename, payload in recomputed["file_bytes"].items():
        add(f"reproduced_bytes:{filename}", (directory / filename).read_bytes() == payload, filename)
    add("reproduced_manifest_bytes", (directory / "manifest.json").read_bytes() == recomputed["manifest_bytes"], "manifest.json")

    sample_rows = _read_jsonl(directory / "canonical_documents.sample.jsonl")
    selected_ids = [str(row.get("canonical_id") or "") for row in sample_rows]
    add("selected_document_count_48", len(sample_rows) == 48, len(sample_rows))
    add("selected_ids_unique", len(set(selected_ids)) == 48, len(set(selected_ids)))
    overlap = set(selected_ids) & dev_ids
    add("development_overlap_zero", len(overlap) == 0, sorted(overlap)[:5])

    assignment_rows_raw = _read_jsonl(directory / "sample_assignments.jsonl")
    assignments = [FreshHeldoutSampleAssignment.model_validate(row) for row in assignment_rows_raw]
    add("assignment_count_48", len(assignments) == 48, len(assignments))
    uniform = [row for row in assignments if row.sample_stratum == "uniform"]
    enriched = [row for row in assignments if row.sample_stratum == "type_enriched"]
    add("uniform_count_24", len(uniform) == 24, len(uniform))
    add("type_enriched_count_24", len(enriched) == 24, len(enriched))
    enriched_counts = Counter(row.enrichment_entity_type for row in enriched)
    for entity_type in ENTITY_TYPES:
        add(f"type_enriched_count:{entity_type}", enriched_counts[entity_type] == 4, enriched_counts[entity_type])

    annotation_rows = _read_jsonl(directory / "annotations_working.jsonl")
    add("annotation_row_count_96", len(annotation_rows) == 96, len(annotation_rows))
    annotation_ids = Counter(str(row.get("canonical_id") or "") for row in annotation_rows)
    add(
        "two_annotation_rows_per_document",
        set(annotation_ids) == set(selected_ids)
        and all(value == 2 for value in annotation_ids.values()),
        len(annotation_ids),
    )
    blank_ok = all(
        row.get("schema_version") == BLIND_ANNOTATION_SCHEMA_VERSION
        and row.get("review_id") == manifest.review_id
        and row.get("annotation_complete") is False
        and row.get("mentions") == []
        and row.get("reviewer_note") is None
        for row in annotation_rows
    )
    add("annotations_are_blank_prediction_blind_template", blank_ok, len(annotation_rows))

    by_id = {str(row["canonical_id"]): row for row in sample_rows}
    source_hashes_ok = True
    source_fields_ok = True
    for row in annotation_rows:
        canonical_id = str(row.get("canonical_id") or "")
        source_field = row.get("source_field")
        if source_field not in {"title", "abstract"}:
            source_fields_ok = False
            continue
        source_text = by_id[canonical_id][source_field]
        if row.get("source_text") != source_text:
            source_hashes_ok = False
        if row.get("source_text_sha256") != sha256_text(source_text):
            source_hashes_ok = False
    add("annotation_source_fields_title_abstract_only", source_fields_ok, "")
    add("annotation_source_text_and_hashes_match_sample", source_hashes_ok, "")

    safety_false = all(
        getattr(manifest, key) is False
        for key in (
            "candidate_predictions_read_during_sampling",
            "model_inference_executed",
            "evaluation_executed",
            "fresh_heldout_reference_consumed",
            "canonical_truth_mutated",
            "production_extractor_selected",
            "full_corpus_build_authorized",
        )
    )
    add("safety_flags_remain_false", safety_false, "")
    add("prediction_blind_true", manifest.prediction_blind is True, "")
    add("annotations_initially_empty_true", manifest.annotations_initially_empty is True, "")
    add("next_slice_is_manual_annotation_reference_freeze", manifest.next_slice == "prediction_blind_manual_annotation_and_reference_freeze", manifest.next_slice)

    failed = [name for name, ok, _ in checks if not ok]
    summary = {
        "report": REPORT_NAME,
        "sample_id": manifest.sample_id,
        "review_id": manifest.review_id,
        "selected_document_count": len(sample_rows),
        "annotation_row_count": len(annotation_rows),
        "uniform_document_count": len(uniform),
        "type_enriched_document_count": len(enriched),
        "heldout_development_overlap_count": len(overlap),
        "selected_canonical_ids_sha256": recomputed["selected_ids_sha256"],
        "prediction_blind": manifest.prediction_blind,
        "annotations_initially_empty": manifest.annotations_initially_empty,
        "candidate_predictions_read_during_sampling": manifest.candidate_predictions_read_during_sampling,
        "model_inference_executed": manifest.model_inference_executed,
        "evaluation_executed": manifest.evaluation_executed,
        "fresh_heldout_reference_consumed": manifest.fresh_heldout_reference_consumed,
        "canonical_truth_mutated": manifest.canonical_truth_mutated,
        "production_extractor_selected": manifest.production_extractor_selected,
        "full_corpus_build_authorized": manifest.full_corpus_build_authorized,
        "total_checks": len(checks),
        "required_failed_count": len(failed),
        "next_slice": manifest.next_slice,
    }
    return checks, summary
