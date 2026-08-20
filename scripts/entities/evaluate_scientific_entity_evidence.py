from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from radar_core.contracts.canonical_document import CanonicalDocument
from radar_core.contracts.scientific_entity_evaluation import (
    EVALUATION_MANIFEST_SCHEMA_VERSION,
    ScientificEntityEvaluationManifest,
    ScientificEntityEvaluationStatus,
    ScientificEntityPredictionInputDescriptor,
    ScientificEntityReferenceMention,
    ScientificEntityReviewInputDescriptor,
    ScientificEntityReviewManifest,
    ScientificEntityReviewStatus,
    validate_reference_mention,
)
from radar_core.contracts.scientific_entity_evidence import (
    EntityEvidenceBuildStatus,
    ScientificEntityEvidenceManifest,
    ScientificEntityMentionEvidence,
    ScientificEntitySourceField,
    validate_mention_evidence,
)
from radar_core.entities.scientific_entity_evaluation import (
    ScientificEntityEvaluationConfig,
    ScientificEntityEvaluationErrorBase,
    evaluate_mentions,
    evaluation_config_sha256,
    load_evaluation_config,
)


REPORT_NAME = "scientific_entity_evaluation_harness_v01"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = (
    PROJECT_ROOT / "configs" / "scientific_entity_evaluation_v0.1.yaml"
)
CURRENT_CANONICAL_PATH = (
    PROJECT_ROOT / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"
)
CHECKSUM_FILES = (
    "manifest.json",
    "metrics.json",
    "per_type_metrics.json",
    "matches.jsonl",
    "errors.jsonl",
    "README.md",
)
REQUIRED_FILES = (*CHECKSUM_FILES, "checksums.txt")


class ScientificEntityEvaluationBuildError(RuntimeError):
    """Raised when a bounded evaluation cannot be safely prepared or written."""


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
    return (
        "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in rows
        )
    ).encode("utf-8")


def _write_text_lf(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ScientificEntityEvaluationBuildError(f"Expected JSON object: {path}")
    return payload


def _read_jsonl(path: Path, *, hard_limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                raise ScientificEntityEvaluationBuildError(
                    f"Blank JSONL line is forbidden: {path}:{line_number}"
                )
            try:
                payload = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise ScientificEntityEvaluationBuildError(
                    f"Invalid JSON at {path}:{line_number}: {exc}"
                ) from exc
            if not isinstance(payload, dict):
                raise ScientificEntityEvaluationBuildError(
                    f"Expected JSON object: {path}:{line_number}"
                )
            rows.append(payload)
            if len(rows) > hard_limit:
                raise ScientificEntityEvaluationBuildError(
                    f"Input exceeds hard limit {hard_limit}; truncation is forbidden"
                )
    return rows


def _load_documents(
    path: Path,
    *,
    max_documents: int,
) -> tuple[list[CanonicalDocument], dict[str, CanonicalDocument]]:
    rows = _read_jsonl(path, hard_limit=max_documents)
    if not rows:
        raise ScientificEntityEvaluationBuildError("Canonical-shaped input is empty")
    documents: list[CanonicalDocument] = []
    by_id: dict[str, CanonicalDocument] = {}
    for row in rows:
        document = CanonicalDocument.model_validate(row)
        if document.canonical_id in by_id:
            raise ScientificEntityEvaluationBuildError(
                f"Duplicate canonical_id: {document.canonical_id}"
            )
        documents.append(document)
        by_id[document.canonical_id] = document
    return documents, by_id


def _source_text(
    documents_by_id: Mapping[str, CanonicalDocument],
    *,
    canonical_id: str,
    source_field: ScientificEntitySourceField,
) -> str:
    document = documents_by_id.get(canonical_id)
    if document is None:
        raise ScientificEntityEvaluationBuildError(
            f"Mention references unknown canonical_id: {canonical_id}"
        )
    value = (
        document.title
        if source_field == ScientificEntitySourceField.TITLE
        else document.abstract
    )
    if value is None or value == "":
        raise ScientificEntityEvaluationBuildError(
            f"Mention references blank source field: {canonical_id}:{source_field.value}"
        )
    return value


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _evaluation_id(generated_at_utc: datetime) -> str:
    timestamp = generated_at_utc.strftime("%Y%m%dT%H%M%S%fZ")
    return f"scientific-entity-evaluation-v0.1-{timestamp}"


def _validate_paths_and_status(
    *,
    config: ScientificEntityEvaluationConfig,
    documents_path: Path,
    review_manifest_path: Path,
    reference_mentions_path: Path,
    prediction_manifest_path: Path,
    prediction_mentions_path: Path,
    status: ScientificEntityEvaluationStatus,
    max_documents: int,
) -> None:
    if max_documents < 1:
        raise ScientificEntityEvaluationBuildError("max_documents must be positive")
    if max_documents > config.safety.hard_max_documents:
        raise ScientificEntityEvaluationBuildError(
            f"max_documents exceeds hard limit {config.safety.hard_max_documents}"
        )
    if status.value not in config.safety.allowed_evaluation_statuses:
        raise ScientificEntityEvaluationBuildError(
            f"Evaluation status is not allowed: {status.value}"
        )
    configured_canonical = _resolve_project_path(config.safety.current_canonical_path)
    if configured_canonical != CURRENT_CANONICAL_PATH.resolve():
        raise ScientificEntityEvaluationBuildError(
            "Configured current canonical path does not match fixed safety boundary"
        )
    if documents_path.resolve() == CURRENT_CANONICAL_PATH.resolve():
        raise ScientificEntityEvaluationBuildError(
            "Current canonical corpus input is forbidden in evaluation harness v0.1"
        )
    for path in (
        documents_path,
        review_manifest_path,
        reference_mentions_path,
        prediction_manifest_path,
        prediction_mentions_path,
    ):
        if not path.is_file():
            raise FileNotFoundError(path)

    if status == ScientificEntityEvaluationStatus.FIXTURE:
        expected = {
            documents_path.resolve(): _resolve_project_path(config.fixtures.documents_path),
            review_manifest_path.resolve(): _resolve_project_path(
                config.fixtures.review_manifest_path
            ),
            reference_mentions_path.resolve(): _resolve_project_path(
                config.fixtures.reference_mentions_path
            ),
            prediction_manifest_path.resolve(): _resolve_project_path(
                config.fixtures.prediction_manifest_path
            ),
            prediction_mentions_path.resolve(): _resolve_project_path(
                config.fixtures.prediction_mentions_path
            ),
        }
        if any(actual != required for actual, required in expected.items()):
            raise ScientificEntityEvaluationBuildError(
                "fixture status is reserved for the tracked synthetic evaluation fixture"
            )


def _build_readme(
    *,
    evaluation_id: str,
    status: ScientificEntityEvaluationStatus,
    generated_at_utc: datetime,
    document_count: int,
    reference_count: int,
    prediction_count: int,
    exact_match_count: int,
    relaxed_only_match_count: int,
    error_count: int,
) -> str:
    return "\n".join(
        [
            "# Scientific Entity Evaluation v0.1",
            "",
            "This directory contains bounded, deterministic quality evidence for",
            "scientific-entity mention extraction. It is derived and rebuildable.",
            "",
            "It is not canonical paper truth, not a reconcile input, not a production",
            "extractor selection, not a full-corpus authorization, and not publication ready.",
            "",
            "## Evaluation",
            "",
            f"- evaluation_id: `{evaluation_id}`",
            f"- status: `{status.value}`",
            f"- generated_at_utc: `{generated_at_utc.isoformat()}`",
            f"- document_count: `{document_count}`",
            f"- reference_mention_count: `{reference_count}`",
            f"- prediction_mention_count: `{prediction_count}`",
            f"- exact_match_count: `{exact_match_count}`",
            f"- relaxed_only_match_count: `{relaxed_only_match_count}`",
            f"- error_count: `{error_count}`",
            "",
            "## Files",
            "",
            "- `manifest.json` — immutable input/output provenance and safety state",
            "- `metrics.json` — micro and source-field exact/relaxed metrics",
            "- `per_type_metrics.json` — exact/relaxed metrics for all six types",
            "- `matches.jsonl` — deterministic one-to-one exact/relaxed matches",
            "- `errors.jsonl` — automatic structural error evidence",
            "- `checksums.txt` — raw-byte SHA-256 checksums",
            "",
            "Metrics are descriptive only. Manual review evidence and a separate",
            "acceptance decision are required before model selection or scale-up.",
            "",
        ]
    )


def _write_evaluation_directory(
    *,
    output_dir: Path,
    manifest_bytes: bytes,
    metrics_bytes: bytes,
    per_type_metrics_bytes: bytes,
    matches_bytes: bytes,
    errors_bytes: bytes,
    readme: str,
) -> list[str]:
    output_root = output_dir.parent
    output_root.mkdir(parents=True, exist_ok=True)
    if output_dir.exists():
        raise FileExistsError(
            f"Immutable evaluation directory exists; overwrite is forbidden: {output_dir}"
        )
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.tmp-", dir=output_root)
    )
    try:
        (staging / "manifest.json").write_bytes(manifest_bytes)
        (staging / "metrics.json").write_bytes(metrics_bytes)
        (staging / "per_type_metrics.json").write_bytes(per_type_metrics_bytes)
        (staging / "matches.jsonl").write_bytes(matches_bytes)
        (staging / "errors.jsonl").write_bytes(errors_bytes)
        _write_text_lf(staging / "README.md", readme)
        checksum_lines = [
            f"{_sha256_file(staging / filename)}  {filename}"
            for filename in CHECKSUM_FILES
        ]
        _write_text_lf(staging / "checksums.txt", "\n".join(checksum_lines) + "\n")
        staging.rename(output_dir)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return list(REQUIRED_FILES)


def evaluate_evidence(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    documents_path: Path | None = None,
    review_manifest_path: Path | None = None,
    reference_mentions_path: Path | None = None,
    prediction_manifest_path: Path | None = None,
    prediction_mentions_path: Path | None = None,
    output_root: Path | None = None,
    evaluation_id: str | None = None,
    status: ScientificEntityEvaluationStatus | str = ScientificEntityEvaluationStatus.FIXTURE,
    max_documents: int | None = None,
    execute: bool = False,
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    resolved_config_path = config_path.resolve()
    config = load_evaluation_config(resolved_config_path)
    selected_documents = _resolve_project_path(
        documents_path or config.fixtures.documents_path
    )
    selected_review_manifest = _resolve_project_path(
        review_manifest_path or config.fixtures.review_manifest_path
    )
    selected_references = _resolve_project_path(
        reference_mentions_path or config.fixtures.reference_mentions_path
    )
    selected_prediction_manifest = _resolve_project_path(
        prediction_manifest_path or config.fixtures.prediction_manifest_path
    )
    selected_predictions = _resolve_project_path(
        prediction_mentions_path or config.fixtures.prediction_mentions_path
    )
    selected_output_root = _resolve_project_path(output_root or config.outputs.root)
    selected_status = ScientificEntityEvaluationStatus(status)
    selected_max_documents = (
        config.safety.default_max_documents
        if max_documents is None
        else max_documents
    )
    _validate_paths_and_status(
        config=config,
        documents_path=selected_documents,
        review_manifest_path=selected_review_manifest,
        reference_mentions_path=selected_references,
        prediction_manifest_path=selected_prediction_manifest,
        prediction_mentions_path=selected_predictions,
        status=selected_status,
        max_documents=selected_max_documents,
    )

    documents, documents_by_id = _load_documents(
        selected_documents,
        max_documents=selected_max_documents,
    )
    canonical_sha256 = _sha256_file(selected_documents)
    review_manifest = ScientificEntityReviewManifest.model_validate(
        _read_json(selected_review_manifest)
    )
    prediction_manifest = ScientificEntityEvidenceManifest.model_validate(
        _read_json(selected_prediction_manifest)
    )
    if review_manifest.canonical_input.sha256 != canonical_sha256:
        raise ScientificEntityEvaluationBuildError(
            "Review manifest canonical input SHA-256 mismatch"
        )
    if prediction_manifest.canonical_input.sha256 != canonical_sha256:
        raise ScientificEntityEvaluationBuildError(
            "Prediction manifest canonical input SHA-256 mismatch"
        )
    if review_manifest.canonical_input.document_count != len(documents):
        raise ScientificEntityEvaluationBuildError(
            "Review manifest canonical document count mismatch"
        )
    if prediction_manifest.canonical_input.document_count != len(documents):
        raise ScientificEntityEvaluationBuildError(
            "Prediction manifest canonical document count mismatch"
        )
    if prediction_manifest.status not in {
        EntityEvidenceBuildStatus.FIXTURE,
        EntityEvidenceBuildStatus.CANDIDATE,
    }:
        raise ScientificEntityEvaluationBuildError(
            "Only fixture/candidate prediction builds may be evaluated in v0.1"
        )

    reference_rows = _read_jsonl(
        selected_references,
        hard_limit=config.safety.hard_max_reference_mentions,
    )
    prediction_rows = _read_jsonl(
        selected_predictions,
        hard_limit=config.safety.hard_max_prediction_mentions,
    )
    if _sha256_file(selected_references) != review_manifest.reference_mentions_sha256:
        raise ScientificEntityEvaluationBuildError(
            "Review manifest reference mentions SHA-256 mismatch"
        )
    if len(reference_rows) != review_manifest.reference_mention_count:
        raise ScientificEntityEvaluationBuildError(
            "Review manifest reference mention count mismatch"
        )
    if _sha256_file(selected_predictions) != prediction_manifest.mentions_sha256:
        raise ScientificEntityEvaluationBuildError(
            "Prediction manifest mentions SHA-256 mismatch"
        )
    if len(prediction_rows) != prediction_manifest.mention_count:
        raise ScientificEntityEvaluationBuildError(
            "Prediction manifest mention count mismatch"
        )

    references: list[ScientificEntityReferenceMention] = []
    for row in reference_rows:
        parsed = ScientificEntityReferenceMention.model_validate(row)
        source_text = _source_text(
            documents_by_id,
            canonical_id=parsed.canonical_id,
            source_field=parsed.source_field,
        )
        references.append(
            validate_reference_mention(
                parsed,
                source_text=source_text,
                review_id=review_manifest.review_id,
            )
        )
        if parsed.annotation_method != review_manifest.annotation_method:
            raise ScientificEntityEvaluationBuildError(
                "Reference annotation_method does not match review manifest"
            )
        if parsed.annotation_pass > review_manifest.annotation_passes:
            raise ScientificEntityEvaluationBuildError(
                "Reference annotation_pass exceeds review manifest passes"
            )
        if parsed.source_field not in review_manifest.source_fields:
            raise ScientificEntityEvaluationBuildError(
                "Reference source_field is not declared by review manifest"
            )
        if parsed.entity_type not in review_manifest.entity_types:
            raise ScientificEntityEvaluationBuildError(
                "Reference entity_type is not declared by review manifest"
            )
    predictions: list[ScientificEntityMentionEvidence] = []
    for row in prediction_rows:
        parsed = ScientificEntityMentionEvidence.model_validate(row)
        source_text = _source_text(
            documents_by_id,
            canonical_id=parsed.canonical_id,
            source_field=parsed.source_field,
        )
        predictions.append(
            validate_mention_evidence(
                parsed,
                source_text=source_text,
                extractor=prediction_manifest.extractor,
                manifest=prediction_manifest,
            )
        )

    if selected_status == ScientificEntityEvaluationStatus.FIXTURE:
        if review_manifest.status != ScientificEntityReviewStatus.FIXTURE:
            raise ScientificEntityEvaluationBuildError(
                "Fixture evaluation requires fixture review manifest"
            )
        if prediction_manifest.status != EntityEvidenceBuildStatus.FIXTURE:
            raise ScientificEntityEvaluationBuildError(
                "Fixture evaluation requires fixture prediction manifest"
            )
    else:
        if review_manifest.status != ScientificEntityReviewStatus.REVIEWED_CANDIDATE:
            raise ScientificEntityEvaluationBuildError(
                "Candidate evaluation requires reviewed_candidate review manifest"
            )
        if prediction_manifest.status != EntityEvidenceBuildStatus.CANDIDATE:
            raise ScientificEntityEvaluationBuildError(
                "Candidate evaluation requires candidate prediction manifest"
            )

    generated_at = generated_at_utc or _utc_now()
    if generated_at.tzinfo is None or generated_at.utcoffset() != timezone.utc.utcoffset(
        generated_at
    ):
        raise ScientificEntityEvaluationBuildError(
            "generated_at_utc must be timezone-aware UTC"
        )
    selected_evaluation_id = evaluation_id or _evaluation_id(generated_at)
    result = evaluate_mentions(
        evaluation_id=selected_evaluation_id,
        document_count=len(documents),
        references=references,
        predictions=predictions,
        config=config,
    )

    metrics_bytes = _json_bytes(result.metrics.model_dump(mode="json"))
    per_type_metrics_bytes = _json_bytes(
        result.per_type_metrics.model_dump(mode="json")
    )
    matches_bytes = _jsonl_bytes(
        [row.model_dump(mode="json") for row in result.matches]
    )
    errors_bytes = _jsonl_bytes(
        [row.model_dump(mode="json") for row in result.errors]
    )
    review_descriptor = ScientificEntityReviewInputDescriptor(
        review_id=review_manifest.review_id,
        status=review_manifest.status,
        manifest_path=_project_relative_or_absolute(selected_review_manifest),
        manifest_sha256=_sha256_file(selected_review_manifest),
        reference_mentions_path=_project_relative_or_absolute(selected_references),
        reference_mentions_sha256=_sha256_file(selected_references),
        reference_mention_count=len(references),
        review_complete=True,
        prediction_blind=review_manifest.prediction_blind,
    )
    prediction_descriptor = ScientificEntityPredictionInputDescriptor(
        build_id=prediction_manifest.build_id,
        status=prediction_manifest.status.value,
        manifest_path=_project_relative_or_absolute(selected_prediction_manifest),
        manifest_sha256=_sha256_file(selected_prediction_manifest),
        mentions_path=_project_relative_or_absolute(selected_predictions),
        mentions_sha256=_sha256_file(selected_predictions),
        mention_count=len(predictions),
        extractor_fingerprint=prediction_manifest.extractor_fingerprint,
    )
    manifest = ScientificEntityEvaluationManifest(
        schema_version=EVALUATION_MANIFEST_SCHEMA_VERSION,
        evaluation_id=selected_evaluation_id,
        status=selected_status,
        generated_at_utc=generated_at,
        config_path=_project_relative_or_absolute(resolved_config_path),
        config_sha256=evaluation_config_sha256(config),
        canonical_input=review_manifest.canonical_input,
        review=review_descriptor,
        prediction=prediction_descriptor,
        matching_policy=config.matching.contract_policy(),
        metrics_file="metrics.json",
        metrics_sha256=_sha256_bytes(metrics_bytes),
        per_type_metrics_file="per_type_metrics.json",
        per_type_metrics_sha256=_sha256_bytes(per_type_metrics_bytes),
        matches_file="matches.jsonl",
        matches_sha256=_sha256_bytes(matches_bytes),
        match_count=len(result.matches),
        errors_file="errors.jsonl",
        errors_sha256=_sha256_bytes(errors_bytes),
        error_count=len(result.errors),
        canonical_truth_mutated=False,
        may_be_used_as_reconcile_input=False,
        production_extractor_selected=False,
        full_corpus_build_authorized=False,
        model_downloaded=False,
        provider_api_called=False,
        redistribution_allowed=False,
        publication_ready=False,
    )
    manifest_bytes = _json_bytes(manifest.model_dump(mode="json"))
    readme = _build_readme(
        evaluation_id=selected_evaluation_id,
        status=selected_status,
        generated_at_utc=generated_at,
        document_count=len(documents),
        reference_count=len(references),
        prediction_count=len(predictions),
        exact_match_count=result.metrics.exact_match_count,
        relaxed_only_match_count=result.metrics.relaxed_only_match_count,
        error_count=len(result.errors),
    )
    output_dir = selected_output_root / selected_evaluation_id
    if execute and output_dir.exists():
        raise FileExistsError(
            f"Immutable evaluation directory exists; overwrite is forbidden: {output_dir}"
        )
    written_files: list[str] = []
    if execute:
        written_files = _write_evaluation_directory(
            output_dir=output_dir,
            manifest_bytes=manifest_bytes,
            metrics_bytes=metrics_bytes,
            per_type_metrics_bytes=per_type_metrics_bytes,
            matches_bytes=matches_bytes,
            errors_bytes=errors_bytes,
            readme=readme,
        )

    return {
        "schema_version": "scientific_entity_evaluation_harness_report_v0.1",
        "report": REPORT_NAME,
        "ok": True,
        "mode": "execute" if execute else "plan",
        "phase_complete": execute,
        "evaluation_id": selected_evaluation_id,
        "status": selected_status.value,
        "config_path": _normalize_path(resolved_config_path),
        "documents_path": _normalize_path(selected_documents),
        "review_manifest_path": _normalize_path(selected_review_manifest),
        "reference_mentions_path": _normalize_path(selected_references),
        "prediction_manifest_path": _normalize_path(selected_prediction_manifest),
        "prediction_mentions_path": _normalize_path(selected_predictions),
        "output_dir": _normalize_path(output_dir),
        "input_document_count": len(documents),
        "reference_mention_count": len(references),
        "prediction_mention_count": len(predictions),
        "exact_match_count": result.metrics.exact_match_count,
        "relaxed_only_match_count": result.metrics.relaxed_only_match_count,
        "error_count": len(result.errors),
        "exact_micro": result.metrics.micro.exact.model_dump(mode="json"),
        "relaxed_micro": result.metrics.micro.relaxed.model_dump(mode="json"),
        "written_files": written_files,
        "canonical_truth_mutated": False,
        "full_corpus_build_authorized": False,
        "production_extractor_selected": False,
        "model_downloaded": False,
        "provider_api_called": False,
        "publication_ready": False,
        "next_slice": "bounded_scientific_entity_manual_review_evidence_v0.1",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Plan or execute bounded Scientific Entity Evaluation Harness v0.1. "
            "Plan-only by default."
        )
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--documents", type=Path, default=None)
    parser.add_argument("--review-manifest", type=Path, default=None)
    parser.add_argument("--reference-mentions", type=Path, default=None)
    parser.add_argument("--prediction-manifest", type=Path, default=None)
    parser.add_argument("--prediction-mentions", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--evaluation-id", default=None)
    parser.add_argument("--status", choices=("fixture", "candidate"), default="fixture")
    parser.add_argument("--max-documents", type=int, default=None)
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = evaluate_evidence(
            config_path=args.config,
            documents_path=args.documents,
            review_manifest_path=args.review_manifest,
            reference_mentions_path=args.reference_mentions,
            prediction_manifest_path=args.prediction_manifest,
            prediction_mentions_path=args.prediction_mentions,
            output_root=args.output_root,
            evaluation_id=args.evaluation_id,
            status=args.status,
            max_documents=args.max_documents,
            execute=args.execute,
        )
    except (
        FileNotFoundError,
        OSError,
        ValueError,
        ScientificEntityEvaluationErrorBase,
        ScientificEntityEvaluationBuildError,
    ) as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 1

    print(f"[OK] report={REPORT_NAME}")
    print(f"[OK] mode={report['mode']}")
    print(f"[OK] phase_complete={report['phase_complete']}")
    print(f"[OK] evaluation_id={report['evaluation_id']}")
    print(f"[OK] status={report['status']}")
    print(f"[OK] input_document_count={report['input_document_count']}")
    print(f"[OK] reference_mention_count={report['reference_mention_count']}")
    print(f"[OK] prediction_mention_count={report['prediction_mention_count']}")
    print(f"[OK] exact_match_count={report['exact_match_count']}")
    print(f"[OK] relaxed_only_match_count={report['relaxed_only_match_count']}")
    print(f"[OK] error_count={report['error_count']}")
    print(f"[OK] output_dir={report['output_dir']}")
    print(f"[OK] next_slice={report['next_slice']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
