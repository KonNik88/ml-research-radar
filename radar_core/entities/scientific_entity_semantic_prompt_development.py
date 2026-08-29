from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from radar_core.contracts.canonical_document import CanonicalDocument
from radar_core.contracts.scientific_entity_evaluation import ScientificEntityEvaluationManifest
from radar_core.contracts.scientific_entity_semantic_prompt_candidate import (
    SemanticPromptCandidateConfig,
    load_semantic_prompt_candidate_config,
)


PACKAGE_SCHEMA_VERSION = "scientific_entity_semantic_prompt_development_package_v0.2a"
REPORT_NAME = "scientific_entity_semantic_prompt_development_package_v02a"
REQUIRED_FILES = (
    "canonical_documents.jsonl",
    "split_membership.jsonl",
    "manifest.json",
    "README.md",
    "checksums.txt",
)


class SemanticPromptDevelopmentError(RuntimeError):
    """Raised when the frozen 72-paper development package cannot be built safely."""


@dataclass(frozen=True)
class SourceEvaluation:
    split_name: str
    evaluation_dir: Path
    manifest_path: Path
    manifest: ScientificEntityEvaluationManifest
    canonical_path: Path
    canonical_sha256: str
    documents: tuple[CanonicalDocument, ...]
    canonical_rows: tuple[dict[str, Any], ...]
    reference_mentions_path: Path
    reference_mentions_sha256: str



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
        json.dumps(dict(row), ensure_ascii=False, separators=(",", ":")) + "\n"
        for row in rows
    ).encode("utf-8")



def _resolve_manifest_path(project_root: Path, value: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    return candidate.resolve()



def _project_relative_or_absolute(project_root: Path, path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(project_root.resolve())).replace("\\", "/")
    except ValueError:
        return str(resolved).replace("\\", "/")



def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SemanticPromptDevelopmentError(f"Invalid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SemanticPromptDevelopmentError(f"Expected JSON object: {path}")
    return payload



def _load_documents(path: Path) -> tuple[tuple[CanonicalDocument, ...], tuple[dict[str, Any], ...]]:
    documents: list[CanonicalDocument] = []
    raw_rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                raise SemanticPromptDevelopmentError(
                    f"Blank JSONL line is forbidden: {path}:{line_number}"
                )
            try:
                payload = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise SemanticPromptDevelopmentError(
                    f"Invalid canonical JSONL: {path}:{line_number}: {exc}"
                ) from exc
            if not isinstance(payload, dict):
                raise SemanticPromptDevelopmentError(
                    f"Expected canonical JSON object: {path}:{line_number}"
                )
            document = CanonicalDocument.model_validate(payload)
            if document.canonical_id in seen:
                raise SemanticPromptDevelopmentError(
                    f"Duplicate canonical_id within source package: {document.canonical_id}"
                )
            seen.add(document.canonical_id)
            documents.append(document)
            raw_rows.append(payload)
    if not documents:
        raise SemanticPromptDevelopmentError(f"Canonical input is empty: {path}")
    return tuple(documents), tuple(raw_rows)



def _count_jsonl(path: Path) -> int:
    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                raise SemanticPromptDevelopmentError(
                    f"Blank JSONL line is forbidden: {path}:{line_number}"
                )
            count += 1
    return count



def _load_source_evaluation(
    *,
    project_root: Path,
    split_name: str,
    evaluation_dir: Path,
) -> SourceEvaluation:
    resolved_dir = evaluation_dir.resolve()
    manifest_path = resolved_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    manifest = ScientificEntityEvaluationManifest.model_validate(_read_json(manifest_path))

    canonical_path = _resolve_manifest_path(project_root, manifest.canonical_input.path)
    if not canonical_path.is_file():
        raise FileNotFoundError(canonical_path)
    canonical_sha = _sha256_file(canonical_path)
    if canonical_sha != manifest.canonical_input.sha256:
        raise SemanticPromptDevelopmentError(
            f"{split_name} canonical SHA-256 does not match evaluation manifest"
        )
    documents, canonical_rows = _load_documents(canonical_path)
    if len(documents) != manifest.canonical_input.document_count:
        raise SemanticPromptDevelopmentError(
            f"{split_name} canonical document count does not match evaluation manifest"
        )

    reference_path = _resolve_manifest_path(project_root, manifest.review.reference_mentions_path)
    if not reference_path.is_file():
        raise FileNotFoundError(reference_path)
    reference_sha = _sha256_file(reference_path)
    if reference_sha != manifest.review.reference_mentions_sha256:
        raise SemanticPromptDevelopmentError(
            f"{split_name} reference mention SHA-256 does not match evaluation manifest"
        )
    if _count_jsonl(reference_path) != manifest.review.reference_mention_count:
        raise SemanticPromptDevelopmentError(
            f"{split_name} reference mention count does not match evaluation manifest"
        )

    return SourceEvaluation(
        split_name=split_name,
        evaluation_dir=resolved_dir,
        manifest_path=manifest_path,
        manifest=manifest,
        canonical_path=canonical_path,
        canonical_sha256=canonical_sha,
        documents=documents,
        canonical_rows=canonical_rows,
        reference_mentions_path=reference_path,
        reference_mentions_sha256=reference_sha,
    )



def _validate_lineage(
    *,
    design: SemanticPromptCandidateConfig,
    old_dev: SourceEvaluation,
    consumed_heldout: SourceEvaluation,
) -> None:
    expected_old = design.development_evidence.old_dev
    expected_heldout = design.development_evidence.consumed_v01_heldout

    if len(old_dev.documents) != expected_old.document_count:
        raise SemanticPromptDevelopmentError(
            f"old_dev document count must remain {expected_old.document_count}"
        )
    if old_dev.manifest.review.review_id != expected_old.review_id:
        raise SemanticPromptDevelopmentError("old_dev review_id does not match frozen design")
    if expected_old.evaluation_id and old_dev.manifest.evaluation_id != expected_old.evaluation_id:
        raise SemanticPromptDevelopmentError("old_dev evaluation_id does not match frozen design")

    if len(consumed_heldout.documents) != expected_heldout.document_count:
        raise SemanticPromptDevelopmentError(
            f"consumed held-out document count must remain {expected_heldout.document_count}"
        )
    if consumed_heldout.manifest.review.review_id != expected_heldout.review_id:
        raise SemanticPromptDevelopmentError(
            "consumed held-out review_id does not match frozen design"
        )
    if (
        expected_heldout.evaluation_id
        and consumed_heldout.manifest.evaluation_id != expected_heldout.evaluation_id
    ):
        raise SemanticPromptDevelopmentError(
            "consumed held-out evaluation_id does not match frozen design"
        )

    old_ids = {row.canonical_id for row in old_dev.documents}
    heldout_ids = {row.canonical_id for row in consumed_heldout.documents}
    overlap = old_ids & heldout_ids
    if overlap:
        sample = sorted(overlap)[:5]
        raise SemanticPromptDevelopmentError(
            f"Development splits must remain disjoint; overlap={sample}"
        )
    if len(old_ids | heldout_ids) != design.development_evidence.combined_document_count:
        raise SemanticPromptDevelopmentError("Combined development document count drifted")



def _canonical_rows(sources: Sequence[SourceEvaluation]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in sources:
        rows.extend(dict(row) for row in source.canonical_rows)
    return rows



def _membership_rows(sources: Sequence[SourceEvaluation]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in sources:
        for ordinal, document in enumerate(source.documents):
            rows.append(
                {
                    "canonical_id": document.canonical_id,
                    "split": source.split_name,
                    "split_ordinal": ordinal,
                    "source_evaluation_id": source.manifest.evaluation_id,
                    "source_review_id": source.manifest.review.review_id,
                }
            )
    return rows



def _source_descriptor(project_root: Path, source: SourceEvaluation) -> dict[str, Any]:
    return {
        "split": source.split_name,
        "evaluation_id": source.manifest.evaluation_id,
        "evaluation_dir": _project_relative_or_absolute(project_root, source.evaluation_dir),
        "evaluation_manifest_path": _project_relative_or_absolute(
            project_root, source.manifest_path
        ),
        "evaluation_manifest_sha256": _sha256_file(source.manifest_path),
        "review_id": source.manifest.review.review_id,
        "review_manifest_path": source.manifest.review.manifest_path,
        "reference_mentions_path": _project_relative_or_absolute(
            project_root, source.reference_mentions_path
        ),
        "reference_mentions_sha256": source.reference_mentions_sha256,
        "reference_mention_count": source.manifest.review.reference_mention_count,
        "canonical_input_path": _project_relative_or_absolute(project_root, source.canonical_path),
        "canonical_input_sha256": source.canonical_sha256,
        "document_count": len(source.documents),
    }



def _default_package_id(generated_at_utc: datetime) -> str:
    timestamp = generated_at_utc.strftime("%Y%m%dT%H%M%S%fZ")
    return f"scientific-entity-semantic-prompt-development-v0.2a-{timestamp}"



def _readme(package_id: str, canonical_sha: str) -> str:
    return "\n".join(
        [
            "# Scientific Entity Semantic Prompt Development Package v0.2a",
            "",
            f"package_id = `{package_id}`",
            "",
            "This immutable local package combines only the already-consumed v0.2",
            "development evidence: the 24-paper original DEV review and the 48-paper",
            "v0.1 held-out package whose errors have now been inspected.",
            "",
            "It contains canonical-shaped source text plus deterministic split membership.",
            "It does not merge annotation identities, run GLiNER, retune thresholds, mutate",
            "canonical truth, or create independent held-out evidence.",
            "",
            f"combined_canonical_sha256 = `{canonical_sha}`",
            "document_count = `72`",
            "future_v0.2_acceptance_requires_new_disjoint_heldout = `true`",
            "",
        ]
    )



def prepare_semantic_prompt_development_package(
    *,
    project_root: Path,
    design_config_path: Path,
    old_dev_evaluation_dir: Path,
    consumed_heldout_evaluation_dir: Path,
    output_root: Path,
    package_id: str | None = None,
    execute: bool = False,
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    root = project_root.resolve()
    design = load_semantic_prompt_candidate_config(design_config_path.resolve())
    generated_at = generated_at_utc or datetime.now(timezone.utc)
    if generated_at.tzinfo is None or generated_at.utcoffset() != timezone.utc.utcoffset(generated_at):
        raise SemanticPromptDevelopmentError("generated_at_utc must be timezone-aware UTC")

    old_dev = _load_source_evaluation(
        project_root=root,
        split_name="old_dev_24",
        evaluation_dir=old_dev_evaluation_dir,
    )
    consumed = _load_source_evaluation(
        project_root=root,
        split_name="consumed_v01_heldout_48",
        evaluation_dir=consumed_heldout_evaluation_dir,
    )
    _validate_lineage(design=design, old_dev=old_dev, consumed_heldout=consumed)

    sources = (old_dev, consumed)
    canonical_rows = _canonical_rows(sources)
    membership_rows = _membership_rows(sources)
    canonical_bytes = _jsonl_bytes(canonical_rows)
    membership_bytes = _jsonl_bytes(membership_rows)
    canonical_sha = _sha256_bytes(canonical_bytes)
    membership_sha = _sha256_bytes(membership_bytes)

    selected_package_id = package_id or _default_package_id(generated_at)
    output_dir = output_root.resolve() / selected_package_id
    if execute and output_dir.exists():
        raise FileExistsError(
            f"Immutable development package already exists; overwrite is forbidden: {output_dir}"
        )

    manifest = {
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "package_id": selected_package_id,
        "candidate_id": design.candidate.candidate_id,
        "generated_at_utc": generated_at.isoformat().replace("+00:00", "Z"),
        "development_role": "v0.2_development_only_not_independent_acceptance",
        "sources": [_source_descriptor(root, source) for source in sources],
        "combined_document_count": len(canonical_rows),
        "split_counts": {
            "old_dev_24": len(old_dev.documents),
            "consumed_v01_heldout_48": len(consumed.documents),
        },
        "source_split_overlap_count": 0,
        "canonical_documents_file": "canonical_documents.jsonl",
        "canonical_documents_sha256": canonical_sha,
        "split_membership_file": "split_membership.jsonl",
        "split_membership_sha256": membership_sha,
        "future_v02_acceptance_requires_new_disjoint_heldout": True,
        "model_inference_executed": False,
        "threshold_tuning_executed": False,
        "canonical_truth_mutated": False,
        "may_be_used_as_reconcile_input": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "publication_ready": False,
        "next_slice": "bounded_raw_candidate_inference_on_72_development_documents",
    }
    manifest_bytes = _json_bytes(manifest)
    readme_bytes = _readme(selected_package_id, canonical_sha).encode("utf-8")

    written_files: list[str] = []
    if execute:
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(
            tempfile.mkdtemp(prefix=f".{selected_package_id}.tmp-", dir=output_dir.parent)
        )
        try:
            (staging / "canonical_documents.jsonl").write_bytes(canonical_bytes)
            (staging / "split_membership.jsonl").write_bytes(membership_bytes)
            (staging / "manifest.json").write_bytes(manifest_bytes)
            (staging / "README.md").write_bytes(readme_bytes)
            checksum_lines = []
            for filename in REQUIRED_FILES[:-1]:
                checksum_lines.append(f"{_sha256_file(staging / filename)}  {filename}")
            (staging / "checksums.txt").write_text(
                "\n".join(checksum_lines) + "\n", encoding="utf-8", newline="\n"
            )
            staging.rename(output_dir)
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise
        written_files = list(REQUIRED_FILES)

    return {
        "report": REPORT_NAME,
        "ok": True,
        "mode": "execute" if execute else "plan",
        "phase_complete": execute,
        "package_id": selected_package_id,
        "output_dir": str(output_dir).replace("\\", "/"),
        "old_dev_evaluation_id": old_dev.manifest.evaluation_id,
        "consumed_heldout_evaluation_id": consumed.manifest.evaluation_id,
        "old_dev_document_count": len(old_dev.documents),
        "consumed_heldout_document_count": len(consumed.documents),
        "combined_document_count": len(canonical_rows),
        "source_split_overlap_count": 0,
        "canonical_documents_sha256": canonical_sha,
        "split_membership_sha256": membership_sha,
        "written_files": written_files,
        "model_inference_executed": False,
        "threshold_tuning_executed": False,
        "canonical_truth_mutated": False,
        "full_corpus_build_authorized": False,
        "next_slice": "bounded_raw_candidate_inference_on_72_development_documents",
    }



def validate_semantic_prompt_development_package(
    *,
    project_root: Path,
    design_config_path: Path,
    package_dir: Path,
) -> dict[str, Any]:
    root = project_root.resolve()
    resolved = package_dir.resolve()
    for filename in REQUIRED_FILES:
        if not (resolved / filename).is_file():
            raise FileNotFoundError(resolved / filename)

    manifest = _read_json(resolved / "manifest.json")
    if manifest.get("schema_version") != PACKAGE_SCHEMA_VERSION:
        raise SemanticPromptDevelopmentError("Unexpected package schema_version")

    checksums: dict[str, str] = {}
    for line in (resolved / "checksums.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        sha, filename = line.split("  ", 1)
        checksums[filename] = sha
    if set(checksums) != set(REQUIRED_FILES[:-1]):
        raise SemanticPromptDevelopmentError("checksums.txt coverage mismatch")
    for filename, expected_sha in checksums.items():
        if _sha256_file(resolved / filename) != expected_sha:
            raise SemanticPromptDevelopmentError(f"Checksum mismatch: {filename}")

    if _sha256_file(resolved / "canonical_documents.jsonl") != manifest.get(
        "canonical_documents_sha256"
    ):
        raise SemanticPromptDevelopmentError("Combined canonical SHA mismatch")
    if _sha256_file(resolved / "split_membership.jsonl") != manifest.get(
        "split_membership_sha256"
    ):
        raise SemanticPromptDevelopmentError("Split membership SHA mismatch")

    source_rows = manifest.get("sources")
    if not isinstance(source_rows, list) or len(source_rows) != 2:
        raise SemanticPromptDevelopmentError("Package must record exactly two source evaluations")

    source_by_split = {row["split"]: row for row in source_rows}
    if set(source_by_split) != {"old_dev_24", "consumed_v01_heldout_48"}:
        raise SemanticPromptDevelopmentError("Package source split names drifted")

    design = load_semantic_prompt_candidate_config(design_config_path.resolve())
    if manifest.get("candidate_id") != design.candidate.candidate_id:
        raise SemanticPromptDevelopmentError("Package candidate_id drifted")
    if manifest.get("combined_document_count") != design.development_evidence.combined_document_count:
        raise SemanticPromptDevelopmentError("Package combined_document_count drifted")
    expected_split_counts = {
        "old_dev_24": design.development_evidence.old_dev.document_count,
        "consumed_v01_heldout_48": design.development_evidence.consumed_v01_heldout.document_count,
    }
    if manifest.get("split_counts") != expected_split_counts:
        raise SemanticPromptDevelopmentError("Package split_counts drifted")
    if manifest.get("source_split_overlap_count") != 0:
        raise SemanticPromptDevelopmentError("Package must record zero source split overlap")
    required_false = (
        "model_inference_executed",
        "threshold_tuning_executed",
        "canonical_truth_mutated",
        "may_be_used_as_reconcile_input",
        "production_extractor_selected",
        "full_corpus_build_authorized",
        "publication_ready",
    )
    for key in required_false:
        if manifest.get(key) is not False:
            raise SemanticPromptDevelopmentError(f"Package safety flag must remain false: {key}")
    if manifest.get("future_v02_acceptance_requires_new_disjoint_heldout") is not True:
        raise SemanticPromptDevelopmentError(
            "Package must preserve the fresh v0.2 held-out requirement"
        )
    if manifest.get("next_slice") != "bounded_raw_candidate_inference_on_72_development_documents":
        raise SemanticPromptDevelopmentError("Package next_slice drifted")

    source_objects: list[SourceEvaluation] = []
    for split in ("old_dev_24", "consumed_v01_heldout_48"):
        row = source_by_split[split]
        source = _load_source_evaluation(
            project_root=root,
            split_name=split,
            evaluation_dir=_resolve_manifest_path(root, row["evaluation_dir"]),
        )
        if _sha256_file(source.manifest_path) != row["evaluation_manifest_sha256"]:
            raise SemanticPromptDevelopmentError(f"{split} evaluation manifest drifted")
        expected_source = _source_descriptor(root, source)
        if row != expected_source:
            raise SemanticPromptDevelopmentError(f"{split} source descriptor does not reproduce")
        source_objects.append(source)
    _validate_lineage(
        design=design,
        old_dev=source_objects[0],
        consumed_heldout=source_objects[1],
    )

    expected_canonical = _jsonl_bytes(_canonical_rows(source_objects))
    expected_membership = _jsonl_bytes(_membership_rows(source_objects))
    if (resolved / "canonical_documents.jsonl").read_bytes() != expected_canonical:
        raise SemanticPromptDevelopmentError("Combined canonical bytes do not reproduce")
    if (resolved / "split_membership.jsonl").read_bytes() != expected_membership:
        raise SemanticPromptDevelopmentError("Split membership bytes do not reproduce")

    combined_documents, _ = _load_documents(resolved / "canonical_documents.jsonl")
    if len(combined_documents) != design.development_evidence.combined_document_count:
        raise SemanticPromptDevelopmentError("Combined package document count drifted")

    return {
        "report": REPORT_NAME,
        "ok": True,
        "package_id": manifest["package_id"],
        "combined_document_count": len(combined_documents),
        "old_dev_document_count": len(source_objects[0].documents),
        "consumed_heldout_document_count": len(source_objects[1].documents),
        "source_split_overlap_count": manifest["source_split_overlap_count"],
        "canonical_documents_sha256": manifest["canonical_documents_sha256"],
        "split_membership_sha256": manifest["split_membership_sha256"],
        "model_inference_executed": manifest["model_inference_executed"],
        "threshold_tuning_executed": manifest["threshold_tuning_executed"],
        "canonical_truth_mutated": manifest["canonical_truth_mutated"],
        "full_corpus_build_authorized": manifest["full_corpus_build_authorized"],
        "next_slice": manifest["next_slice"],
    }
