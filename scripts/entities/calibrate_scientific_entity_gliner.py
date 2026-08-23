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
    ScientificEntityEvaluationManifest,
    ScientificEntityEvaluationMetrics,
    ScientificEntityEvaluationStatus,
    ScientificEntityReferenceMention,
    ScientificEntityReviewManifest,
    ScientificEntityReviewStatus,
    validate_reference_mention,
)
from radar_core.contracts.scientific_entity_evidence import (
    ConfidenceKind,
    EntityEvidenceBuildStatus,
    ExtractorKind,
    ScientificEntityEvidenceManifest,
    ScientificEntityMentionEvidence,
    ScientificEntitySourceField,
    validate_mention_evidence,
)
from radar_core.contracts.scientific_entity_gliner_calibration import (
    CALIBRATION_MANIFEST_SCHEMA_VERSION,
    ScientificEntityCalibrationInputs,
    ScientificEntityCalibrationStatus,
    ScientificEntityGLiNERCalibrationManifest,
)
from radar_core.entities.scientific_entity_evaluation import (
    evaluate_mentions,
    evaluation_config_sha256,
    load_evaluation_config,
)
from radar_core.entities.scientific_entity_gliner_calibration import (
    ScientificEntityGLiNERCalibrationConfig,
    ScientificEntityGLiNERCalibrationError,
    calibrate_predictions,
    gliner_calibration_config_sha256,
    load_gliner_calibration_config,
)


REPORT_NAME = "bounded_scientific_entity_gliner_dev_calibration_v01"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = (
    PROJECT_ROOT / "configs" / "scientific_entity_gliner_dev_calibration_v0.1.yaml"
)
CURRENT_CANONICAL_PATH = (
    PROJECT_ROOT / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"
)
CHECKSUM_FILES = (
    "trials.jsonl",
    "pareto_frontier.json",
    "recommended_profiles.json",
    "diagnostics.json",
    "manifest.json",
    "README.md",
)
REQUIRED_FILES = (*CHECKSUM_FILES, "checksums.txt")


class ScientificEntityGLiNERCalibrationBuildError(RuntimeError):
    """Raised when bounded calibration cannot be prepared safely."""


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
        raise ScientificEntityGLiNERCalibrationBuildError(
            f"Expected JSON object: {path}"
        )
    return payload


def _read_jsonl(path: Path, *, hard_limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                raise ScientificEntityGLiNERCalibrationBuildError(
                    f"Blank JSONL line is forbidden: {path}:{line_number}"
                )
            try:
                payload = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise ScientificEntityGLiNERCalibrationBuildError(
                    f"Invalid JSON at {path}:{line_number}: {exc}"
                ) from exc
            if not isinstance(payload, dict):
                raise ScientificEntityGLiNERCalibrationBuildError(
                    f"Expected JSON object: {path}:{line_number}"
                )
            rows.append(payload)
            if len(rows) > hard_limit:
                raise ScientificEntityGLiNERCalibrationBuildError(
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
        raise ScientificEntityGLiNERCalibrationBuildError("document input is empty")
    documents: list[CanonicalDocument] = []
    by_id: dict[str, CanonicalDocument] = {}
    for row in rows:
        document = CanonicalDocument.model_validate(row)
        if document.canonical_id in by_id:
            raise ScientificEntityGLiNERCalibrationBuildError(
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
        raise ScientificEntityGLiNERCalibrationBuildError(
            f"Mention references unknown canonical_id: {canonical_id}"
        )
    value = (
        document.title
        if source_field == ScientificEntitySourceField.TITLE
        else document.abstract
    )
    if value is None or value == "":
        raise ScientificEntityGLiNERCalibrationBuildError(
            "Mention references blank source field: "
            f"{canonical_id}:{source_field.value}"
        )
    return value


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _default_calibration_id(generated_at_utc: datetime) -> str:
    timestamp = generated_at_utc.strftime("%Y%m%dT%H%M%S%fZ")
    return f"scientific-entity-gliner-dev-calibration-v0.1-{timestamp}"


def _validate_request(
    *,
    config: ScientificEntityGLiNERCalibrationConfig,
    documents_path: Path,
    review_manifest_path: Path,
    reference_mentions_path: Path,
    prediction_build_dir: Path,
    baseline_evaluation_dir: Path,
    status: ScientificEntityCalibrationStatus,
    max_documents: int,
) -> None:
    if max_documents < 1:
        raise ScientificEntityGLiNERCalibrationBuildError(
            "max_documents must be positive"
        )
    if max_documents > config.safety.hard_max_documents:
        raise ScientificEntityGLiNERCalibrationBuildError(
            f"max_documents exceeds hard limit {config.safety.hard_max_documents}"
        )
    if status.value not in config.safety.allowed_statuses:
        raise ScientificEntityGLiNERCalibrationBuildError(
            f"Calibration status is not allowed: {status.value}"
        )
    configured_canonical = _resolve_project_path(config.safety.current_canonical_path)
    if configured_canonical != CURRENT_CANONICAL_PATH.resolve():
        raise ScientificEntityGLiNERCalibrationBuildError(
            "Configured current canonical path does not match fixed safety boundary"
        )
    if documents_path.resolve() == CURRENT_CANONICAL_PATH.resolve():
        raise ScientificEntityGLiNERCalibrationBuildError(
            "Current canonical corpus is forbidden in dev calibration v0.1"
        )
    files = (
        documents_path,
        review_manifest_path,
        reference_mentions_path,
        prediction_build_dir / "manifest.json",
        prediction_build_dir / "mentions.jsonl",
        prediction_build_dir / "data_quality_summary.json",
        baseline_evaluation_dir / "manifest.json",
        baseline_evaluation_dir / "metrics.json",
    )
    for path in files:
        if not path.is_file():
            raise FileNotFoundError(path)

    if status == ScientificEntityCalibrationStatus.FIXTURE:
        expected = {
            documents_path.resolve(): _resolve_project_path(
                config.fixtures.documents_path
            ),
            review_manifest_path.resolve(): _resolve_project_path(
                config.fixtures.review_manifest_path
            ),
            reference_mentions_path.resolve(): _resolve_project_path(
                config.fixtures.reference_mentions_path
            ),
            prediction_build_dir.resolve(): _resolve_project_path(
                config.fixtures.prediction_build_dir
            ),
            baseline_evaluation_dir.resolve(): _resolve_project_path(
                config.fixtures.baseline_evaluation_dir
            ),
        }
        if any(actual != required for actual, required in expected.items()):
            raise ScientificEntityGLiNERCalibrationBuildError(
                "fixture status is reserved for the tracked calibration fixture"
            )


def _build_readme(
    *,
    calibration_id: str,
    status: ScientificEntityCalibrationStatus,
    generated_at_utc: datetime,
    document_count: int,
    reference_count: int,
    prediction_count: int,
    trial_count: int,
) -> str:
    return "\n".join(
        [
            "# Bounded Scientific Entity GLiNER Dev Calibration v0.1",
            "",
            "This immutable directory contains deterministic development-only",
            "threshold-policy evidence derived from one frozen prediction build.",
            "No model inference, model download, provider request, canonical mutation,",
            "or full-corpus processing occurs in this layer.",
            "",
            "## Calibration",
            "",
            f"- calibration_id: `{calibration_id}`",
            f"- status: `{status.value}`",
            f"- generated_at_utc: `{generated_at_utc.isoformat()}`",
            f"- document_count: `{document_count}`",
            f"- reference_mention_count: `{reference_count}`",
            f"- input_prediction_mention_count: `{prediction_count}`",
            f"- trial_count: `{trial_count}`",
            "",
            "## Semantics",
            "",
            "The retained confidence values remain uncalibrated model scores.",
            "This layer does not write a calibration_id into mention evidence and does",
            "not interpret confidence_score as a probability of correctness.",
            "F0.5/F1/F2 profiles and the Pareto frontier are descriptive dev choices,",
            "not production extractor selection or promotion evidence.",
            "",
            "The current review package has been used for tuning and cannot later be",
            "reported as held-out evidence. A candidate must be frozen before a new,",
            "disjoint, prediction-blind review is prepared.",
            "",
        ]
    )


def _write_output(
    *,
    output_dir: Path,
    trials_bytes: bytes,
    pareto_bytes: bytes,
    profiles_bytes: bytes,
    diagnostics_bytes: bytes,
    manifest_bytes: bytes,
    readme: str,
) -> list[str]:
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    if output_dir.exists():
        raise FileExistsError(
            "Immutable calibration directory already exists; overwrite is forbidden: "
            f"{output_dir}"
        )
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.tmp-", dir=output_dir.parent)
    )
    try:
        (staging / "trials.jsonl").write_bytes(trials_bytes)
        (staging / "pareto_frontier.json").write_bytes(pareto_bytes)
        (staging / "recommended_profiles.json").write_bytes(profiles_bytes)
        (staging / "diagnostics.json").write_bytes(diagnostics_bytes)
        (staging / "manifest.json").write_bytes(manifest_bytes)
        _write_text_lf(staging / "README.md", readme)
        checksums = [
            f"{_sha256_file(staging / filename)}  {filename}"
            for filename in CHECKSUM_FILES
        ]
        _write_text_lf(staging / "checksums.txt", "\n".join(checksums) + "\n")
        staging.rename(output_dir)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return list(REQUIRED_FILES)


def _assert_baseline_matches(
    *,
    baseline_manifest: ScientificEntityEvaluationManifest,
    baseline_metrics: ScientificEntityEvaluationMetrics,
    evaluation_config_path: Path,
    document_count: int,
    references: Sequence[ScientificEntityReferenceMention],
    predictions: Sequence[ScientificEntityMentionEvidence],
) -> None:
    evaluation_config = load_evaluation_config(evaluation_config_path)
    if _resolve_project_path(baseline_manifest.config_path) != (
        evaluation_config_path.resolve()
    ):
        raise ScientificEntityGLiNERCalibrationBuildError(
            "Baseline evaluation config path does not match calibration config"
        )
    if evaluation_config_sha256(evaluation_config) != baseline_manifest.config_sha256:
        raise ScientificEntityGLiNERCalibrationBuildError(
            "Baseline evaluation config SHA-256 does not match current "
            "evaluation config"
        )
    expected_policy = evaluation_config.matching.contract_policy()
    if baseline_manifest.matching_policy != expected_policy:
        raise ScientificEntityGLiNERCalibrationBuildError(
            "Baseline manifest matching policy does not match evaluation config"
        )
    if baseline_metrics.matching_policy != expected_policy:
        raise ScientificEntityGLiNERCalibrationBuildError(
            "Baseline metrics matching policy does not match evaluation config"
        )
    recomputed = evaluate_mentions(
        evaluation_id=baseline_manifest.evaluation_id,
        document_count=document_count,
        references=references,
        predictions=predictions,
        config=evaluation_config,
    )
    if recomputed.metrics.model_dump(mode="json") != baseline_metrics.model_dump(
        mode="json"
    ):
        raise ScientificEntityGLiNERCalibrationBuildError(
            "Recomputed unfiltered baseline metrics do not match pinned evaluation"
        )


def calibrate_gliner_predictions(
    *,
    config_path: Path = DEFAULT_CONFIG_PATH,
    documents_path: Path | None = None,
    review_manifest_path: Path | None = None,
    reference_mentions_path: Path | None = None,
    prediction_build_dir: Path | None = None,
    baseline_evaluation_dir: Path | None = None,
    output_root: Path | None = None,
    calibration_id: str | None = None,
    status: ScientificEntityCalibrationStatus | str = (
        ScientificEntityCalibrationStatus.FIXTURE
    ),
    max_documents: int | None = None,
    execute: bool = False,
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    resolved_config_path = config_path.resolve()
    config = load_gliner_calibration_config(resolved_config_path)
    selected_documents = _resolve_project_path(
        documents_path or config.fixtures.documents_path
    )
    selected_review_manifest = _resolve_project_path(
        review_manifest_path or config.fixtures.review_manifest_path
    )
    selected_references = _resolve_project_path(
        reference_mentions_path or config.fixtures.reference_mentions_path
    )
    selected_prediction_dir = _resolve_project_path(
        prediction_build_dir or config.fixtures.prediction_build_dir
    )
    selected_baseline_dir = _resolve_project_path(
        baseline_evaluation_dir or config.fixtures.baseline_evaluation_dir
    )
    selected_output_root = _resolve_project_path(output_root or config.outputs.root)
    selected_status = ScientificEntityCalibrationStatus(status)
    selected_max_documents = (
        config.safety.default_max_documents
        if max_documents is None
        else max_documents
    )
    _validate_request(
        config=config,
        documents_path=selected_documents,
        review_manifest_path=selected_review_manifest,
        reference_mentions_path=selected_references,
        prediction_build_dir=selected_prediction_dir,
        baseline_evaluation_dir=selected_baseline_dir,
        status=selected_status,
        max_documents=selected_max_documents,
    )

    prediction_manifest_path = selected_prediction_dir / "manifest.json"
    prediction_mentions_path = selected_prediction_dir / "mentions.jsonl"
    prediction_quality_path = selected_prediction_dir / "data_quality_summary.json"
    baseline_manifest_path = selected_baseline_dir / "manifest.json"
    baseline_metrics_path = selected_baseline_dir / "metrics.json"
    evaluation_config_path = _resolve_project_path(
        config.evaluation.evaluation_config_path
    )

    documents, documents_by_id = _load_documents(
        selected_documents,
        max_documents=selected_max_documents,
    )
    documents_sha = _sha256_file(selected_documents)
    review_manifest = ScientificEntityReviewManifest.model_validate(
        _read_json(selected_review_manifest)
    )
    prediction_manifest = ScientificEntityEvidenceManifest.model_validate(
        _read_json(prediction_manifest_path)
    )
    prediction_quality = _read_json(prediction_quality_path)
    baseline_manifest = ScientificEntityEvaluationManifest.model_validate(
        _read_json(baseline_manifest_path)
    )
    baseline_metrics = ScientificEntityEvaluationMetrics.model_validate(
        _read_json(baseline_metrics_path)
    )

    if review_manifest.canonical_input.sha256 != documents_sha:
        raise ScientificEntityGLiNERCalibrationBuildError(
            "Review canonical input SHA-256 mismatch"
        )
    if prediction_manifest.canonical_input.sha256 != documents_sha:
        raise ScientificEntityGLiNERCalibrationBuildError(
            "Prediction canonical input SHA-256 mismatch"
        )
    if baseline_manifest.canonical_input.sha256 != documents_sha:
        raise ScientificEntityGLiNERCalibrationBuildError(
            "Baseline evaluation canonical input SHA-256 mismatch"
        )
    if baseline_manifest.canonical_input.document_count != len(documents):
        raise ScientificEntityGLiNERCalibrationBuildError(
            "Baseline evaluation document count mismatch"
        )
    if review_manifest.canonical_input.document_count != len(documents):
        raise ScientificEntityGLiNERCalibrationBuildError(
            "Review document count mismatch"
        )
    if prediction_manifest.canonical_input.document_count != len(documents):
        raise ScientificEntityGLiNERCalibrationBuildError(
            "Prediction document count mismatch"
        )

    reference_rows = _read_jsonl(
        selected_references,
        hard_limit=config.safety.hard_max_reference_mentions,
    )
    prediction_rows = _read_jsonl(
        prediction_mentions_path,
        hard_limit=config.safety.hard_max_prediction_mentions,
    )
    if _sha256_file(selected_references) != review_manifest.reference_mentions_sha256:
        raise ScientificEntityGLiNERCalibrationBuildError(
            "Review reference mentions SHA-256 mismatch"
        )
    if len(reference_rows) != review_manifest.reference_mention_count:
        raise ScientificEntityGLiNERCalibrationBuildError(
            "Review reference mention count mismatch"
        )
    if _sha256_file(prediction_mentions_path) != prediction_manifest.mentions_sha256:
        raise ScientificEntityGLiNERCalibrationBuildError(
            "Prediction mentions SHA-256 mismatch"
        )
    if len(prediction_rows) != prediction_manifest.mention_count:
        raise ScientificEntityGLiNERCalibrationBuildError(
            "Prediction mention count mismatch"
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
            raise ScientificEntityGLiNERCalibrationBuildError(
                "Reference annotation_method does not match review manifest"
            )
        if parsed.annotation_pass > review_manifest.annotation_passes:
            raise ScientificEntityGLiNERCalibrationBuildError(
                "Reference annotation_pass exceeds review manifest passes"
            )
        if parsed.source_field not in review_manifest.source_fields:
            raise ScientificEntityGLiNERCalibrationBuildError(
                "Reference source_field is not declared by review manifest"
            )
        if parsed.entity_type not in review_manifest.entity_types:
            raise ScientificEntityGLiNERCalibrationBuildError(
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

    if selected_status == ScientificEntityCalibrationStatus.FIXTURE:
        if review_manifest.status != ScientificEntityReviewStatus.FIXTURE:
            raise ScientificEntityGLiNERCalibrationBuildError(
                "Fixture calibration requires fixture review"
            )
        if prediction_manifest.status != EntityEvidenceBuildStatus.FIXTURE:
            raise ScientificEntityGLiNERCalibrationBuildError(
                "Fixture calibration requires fixture predictions"
            )
        if baseline_manifest.status != ScientificEntityEvaluationStatus.FIXTURE:
            raise ScientificEntityGLiNERCalibrationBuildError(
                "Fixture calibration requires fixture baseline evaluation"
            )
    else:
        if review_manifest.status != ScientificEntityReviewStatus.REVIEWED_CANDIDATE:
            raise ScientificEntityGLiNERCalibrationBuildError(
                "Candidate calibration requires reviewed_candidate references"
            )
        if prediction_manifest.status != EntityEvidenceBuildStatus.CANDIDATE:
            raise ScientificEntityGLiNERCalibrationBuildError(
                "Candidate calibration requires candidate predictions"
            )
        if baseline_manifest.status != ScientificEntityEvaluationStatus.CANDIDATE:
            raise ScientificEntityGLiNERCalibrationBuildError(
                "Candidate calibration requires candidate baseline evaluation"
            )
        if prediction_manifest.extractor.kind != ExtractorKind.STATISTICAL_MODEL:
            raise ScientificEntityGLiNERCalibrationBuildError(
                "Candidate calibration requires a statistical-model extractor"
            )

    if any(row.confidence_kind != ConfidenceKind.MODEL_SCORE for row in predictions):
        raise ScientificEntityGLiNERCalibrationBuildError(
            "All calibration predictions must use model_score confidence"
        )
    if any(row.calibration_id is not None for row in predictions):
        raise ScientificEntityGLiNERCalibrationBuildError(
            "Input predictions must have null calibration_id"
        )
    if any(
        row.confidence_score is None
        or row.confidence_score < config.search.input_threshold
        for row in predictions
    ):
        raise ScientificEntityGLiNERCalibrationBuildError(
            "All prediction scores must be at or above input_threshold"
        )

    quality_checks = {
        "build_id": prediction_quality.get("build_id") == prediction_manifest.build_id,
        "mention_count": (
            prediction_quality.get("mention_count") == prediction_manifest.mention_count
        ),
        "confidence_kind": (
            prediction_quality.get("confidence_kind")
            == ConfidenceKind.MODEL_SCORE.value
        ),
        "threshold": (
            prediction_quality.get("threshold") == config.search.input_threshold
        ),
        "canonical_truth_mutated": (
            prediction_quality.get("canonical_truth_mutated") is False
        ),
        "full_corpus_processed": (
            prediction_quality.get("full_corpus_processed") is False
        ),
    }
    if not all(quality_checks.values()):
        failed = sorted(name for name, ok in quality_checks.items() if not ok)
        raise ScientificEntityGLiNERCalibrationBuildError(
            f"Prediction quality summary failed: {failed}"
        )

    if _sha256_file(baseline_metrics_path) != baseline_manifest.metrics_sha256:
        raise ScientificEntityGLiNERCalibrationBuildError(
            "Baseline metrics SHA-256 mismatch"
        )
    if baseline_manifest.review.manifest_sha256 != _sha256_file(
        selected_review_manifest
    ):
        raise ScientificEntityGLiNERCalibrationBuildError(
            "Baseline review manifest SHA-256 mismatch"
        )
    if baseline_manifest.review.review_id != review_manifest.review_id:
        raise ScientificEntityGLiNERCalibrationBuildError(
            "Baseline review identity mismatch"
        )
    if baseline_manifest.review.status != review_manifest.status:
        raise ScientificEntityGLiNERCalibrationBuildError(
            "Baseline review status mismatch"
        )
    if baseline_manifest.review.reference_mention_count != len(references):
        raise ScientificEntityGLiNERCalibrationBuildError(
            "Baseline review reference count mismatch"
        )
    if baseline_manifest.review.reference_mentions_sha256 != _sha256_file(
        selected_references
    ):
        raise ScientificEntityGLiNERCalibrationBuildError(
            "Baseline reference mentions SHA-256 mismatch"
        )
    if baseline_manifest.prediction.manifest_sha256 != _sha256_file(
        prediction_manifest_path
    ):
        raise ScientificEntityGLiNERCalibrationBuildError(
            "Baseline prediction manifest SHA-256 mismatch"
        )
    if baseline_manifest.prediction.build_id != prediction_manifest.build_id:
        raise ScientificEntityGLiNERCalibrationBuildError(
            "Baseline prediction build identity mismatch"
        )
    if baseline_manifest.prediction.status != prediction_manifest.status.value:
        raise ScientificEntityGLiNERCalibrationBuildError(
            "Baseline prediction status mismatch"
        )
    if baseline_manifest.prediction.mention_count != len(predictions):
        raise ScientificEntityGLiNERCalibrationBuildError(
            "Baseline prediction count mismatch"
        )
    if baseline_manifest.prediction.mentions_sha256 != _sha256_file(
        prediction_mentions_path
    ):
        raise ScientificEntityGLiNERCalibrationBuildError(
            "Baseline prediction mentions SHA-256 mismatch"
        )
    if baseline_manifest.prediction.extractor_fingerprint != (
        prediction_manifest.extractor_fingerprint
    ):
        raise ScientificEntityGLiNERCalibrationBuildError(
            "Baseline extractor fingerprint mismatch"
        )
    if baseline_metrics.evaluation_id != baseline_manifest.evaluation_id:
        raise ScientificEntityGLiNERCalibrationBuildError(
            "Baseline metrics evaluation_id mismatch"
        )

    _assert_baseline_matches(
        baseline_manifest=baseline_manifest,
        baseline_metrics=baseline_metrics,
        evaluation_config_path=evaluation_config_path,
        document_count=len(documents),
        references=references,
        predictions=predictions,
    )
    evaluation_config = load_evaluation_config(evaluation_config_path)

    generated_at = generated_at_utc or _utc_now()
    if (
        generated_at.tzinfo is None
        or generated_at.utcoffset() != timezone.utc.utcoffset(generated_at)
    ):
        raise ScientificEntityGLiNERCalibrationBuildError(
            "generated_at_utc must be timezone-aware UTC"
        )
    selected_calibration_id = calibration_id or _default_calibration_id(generated_at)
    computation = calibrate_predictions(
        calibration_id=selected_calibration_id,
        document_count=len(documents),
        references=references,
        predictions=predictions,
        config=config,
        evaluation_config=evaluation_config,
    )

    trials_bytes = _jsonl_bytes(
        [row.model_dump(mode="json") for row in computation.trials]
    )
    pareto_bytes = _json_bytes(computation.pareto.model_dump(mode="json"))
    profiles_bytes = _json_bytes(computation.profiles.model_dump(mode="json"))
    diagnostics_bytes = _json_bytes(computation.diagnostics.model_dump(mode="json"))
    inputs = ScientificEntityCalibrationInputs(
        documents_path=_project_relative_or_absolute(selected_documents),
        documents_sha256=documents_sha,
        document_count=len(documents),
        review_id=review_manifest.review_id,
        review_manifest_path=_project_relative_or_absolute(selected_review_manifest),
        review_manifest_sha256=_sha256_file(selected_review_manifest),
        reference_mentions_path=_project_relative_or_absolute(selected_references),
        reference_mentions_sha256=_sha256_file(selected_references),
        reference_mention_count=len(references),
        prediction_build_id=prediction_manifest.build_id,
        prediction_manifest_path=_project_relative_or_absolute(
            prediction_manifest_path
        ),
        prediction_manifest_sha256=_sha256_file(prediction_manifest_path),
        prediction_mentions_path=_project_relative_or_absolute(
            prediction_mentions_path
        ),
        prediction_mentions_sha256=_sha256_file(prediction_mentions_path),
        prediction_quality_path=_project_relative_or_absolute(prediction_quality_path),
        prediction_quality_sha256=_sha256_file(prediction_quality_path),
        prediction_mention_count=len(predictions),
        prediction_extractor_fingerprint=prediction_manifest.extractor_fingerprint,
        input_threshold=config.search.input_threshold,
        baseline_evaluation_id=baseline_manifest.evaluation_id,
        baseline_evaluation_manifest_path=_project_relative_or_absolute(
            baseline_manifest_path
        ),
        baseline_evaluation_manifest_sha256=_sha256_file(baseline_manifest_path),
        baseline_metrics_path=_project_relative_or_absolute(baseline_metrics_path),
        baseline_metrics_sha256=_sha256_file(baseline_metrics_path),
    )
    eligible_trial_count = sum(
        row.eligible_for_profile_selection for row in computation.trials
    )
    manifest = ScientificEntityGLiNERCalibrationManifest(
        schema_version=CALIBRATION_MANIFEST_SCHEMA_VERSION,
        calibration_id=selected_calibration_id,
        status=selected_status,
        generated_at_utc=generated_at,
        config_path=_project_relative_or_absolute(resolved_config_path),
        config_sha256=gliner_calibration_config_sha256(config),
        inputs=inputs,
        search_space_trial_count=len(computation.trials),
        eligible_trial_count=eligible_trial_count,
        trials_file="trials.jsonl",
        trials_sha256=_sha256_bytes(trials_bytes),
        pareto_file="pareto_frontier.json",
        pareto_sha256=_sha256_bytes(pareto_bytes),
        profiles_file="recommended_profiles.json",
        profiles_sha256=_sha256_bytes(profiles_bytes),
        diagnostics_file="diagnostics.json",
        diagnostics_sha256=_sha256_bytes(diagnostics_bytes),
        confidence_kind=ConfidenceKind.MODEL_SCORE,
        confidence_scores_reinterpreted_as_probabilities=False,
        calibration_id_written_to_mentions=False,
        current_dev_set_becomes_held_out=False,
        metrics_are_descriptive_only=True,
        production_extractor_selected=False,
        canonical_truth_mutated=False,
        may_be_used_as_reconcile_input=False,
        model_inference_executed=False,
        model_downloaded=False,
        provider_api_called=False,
        full_corpus_build_authorized=False,
        redistribution_allowed=False,
        publication_ready=False,
    )
    manifest_bytes = _json_bytes(manifest.model_dump(mode="json"))
    readme = _build_readme(
        calibration_id=selected_calibration_id,
        status=selected_status,
        generated_at_utc=generated_at,
        document_count=len(documents),
        reference_count=len(references),
        prediction_count=len(predictions),
        trial_count=len(computation.trials),
    )
    output_dir = selected_output_root / selected_calibration_id
    if execute and output_dir.exists():
        raise FileExistsError(
            "Immutable calibration directory already exists; overwrite is forbidden: "
            f"{output_dir}"
        )
    written_files: list[str] = []
    if execute:
        written_files = _write_output(
            output_dir=output_dir,
            trials_bytes=trials_bytes,
            pareto_bytes=pareto_bytes,
            profiles_bytes=profiles_bytes,
            diagnostics_bytes=diagnostics_bytes,
            manifest_bytes=manifest_bytes,
            readme=readme,
        )

    trials_by_id = {row.trial_id: row for row in computation.trials}
    profile_summary: dict[str, Any] = {}
    for selection in computation.profiles.selections:
        trial = trials_by_id[selection.trial_id]
        profile_summary[selection.profile_name.value] = {
            "trial_id": trial.trial_id,
            "policy": trial.policy.model_dump(mode="json"),
            "selected_prediction_count": trial.selected_prediction_count,
            "exact": trial.metrics.exact.model_dump(mode="json"),
            "relaxed": trial.metrics.relaxed.model_dump(mode="json"),
        }
    if selected_status == ScientificEntityCalibrationStatus.FIXTURE:
        next_slice = "execute_existing_24_paper_gliner_dev_calibration_v0.1"
    elif execute:
        next_slice = "review_and_freeze_one_gliner_dev_policy_v0.1"
    else:
        next_slice = "execute_planned_gliner_dev_calibration_v0.1"
    return {
        "schema_version": "scientific_entity_gliner_dev_calibration_report_v0.1",
        "report": REPORT_NAME,
        "ok": True,
        "mode": "execute" if execute else "plan",
        "phase_complete": execute,
        "calibration_id": selected_calibration_id,
        "status": selected_status.value,
        "config_path": _normalize_path(resolved_config_path),
        "documents_path": _normalize_path(selected_documents),
        "prediction_build_dir": _normalize_path(selected_prediction_dir),
        "baseline_evaluation_dir": _normalize_path(selected_baseline_dir),
        "output_dir": _normalize_path(output_dir),
        "input_document_count": len(documents),
        "reference_mention_count": len(references),
        "input_prediction_mention_count": len(predictions),
        "trial_count": len(computation.trials),
        "eligible_trial_count": eligible_trial_count,
        "pareto_trial_count": len(computation.pareto.trial_ids),
        "profile_summary": profile_summary,
        "written_files": written_files,
        "confidence_kind": ConfidenceKind.MODEL_SCORE.value,
        "confidence_scores_reinterpreted_as_probabilities": False,
        "calibration_id_written_to_mentions": False,
        "model_inference_executed": False,
        "model_downloaded": False,
        "provider_api_called": False,
        "canonical_truth_mutated": False,
        "full_corpus_build_authorized": False,
        "production_extractor_selected": False,
        "publication_ready": False,
        "next_slice": next_slice,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Plan or execute bounded Scientific Entity GLiNER Dev Calibration v0.1. "
            "Plan-only by default; no model inference is performed."
        )
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--documents", type=Path, default=None)
    parser.add_argument("--review-manifest", type=Path, default=None)
    parser.add_argument("--reference-mentions", type=Path, default=None)
    parser.add_argument("--prediction-build-dir", type=Path, default=None)
    parser.add_argument("--baseline-evaluation-dir", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--calibration-id", default=None)
    parser.add_argument("--status", choices=("fixture", "candidate"), default="fixture")
    parser.add_argument("--max-documents", type=int, default=None)
    parser.add_argument("--execute", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = calibrate_gliner_predictions(
            config_path=args.config,
            documents_path=args.documents,
            review_manifest_path=args.review_manifest,
            reference_mentions_path=args.reference_mentions,
            prediction_build_dir=args.prediction_build_dir,
            baseline_evaluation_dir=args.baseline_evaluation_dir,
            output_root=args.output_root,
            calibration_id=args.calibration_id,
            status=args.status,
            max_documents=args.max_documents,
            execute=args.execute,
        )
    except (
        FileNotFoundError,
        OSError,
        ValueError,
        ScientificEntityGLiNERCalibrationError,
        ScientificEntityGLiNERCalibrationBuildError,
    ) as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 1

    print(f"[OK] report={REPORT_NAME}")
    print(f"[OK] mode={report['mode']}")
    print(f"[OK] phase_complete={report['phase_complete']}")
    print(f"[OK] calibration_id={report['calibration_id']}")
    print(f"[OK] status={report['status']}")
    print(f"[OK] input_document_count={report['input_document_count']}")
    print(f"[OK] reference_mention_count={report['reference_mention_count']}")
    print(
        "[OK] input_prediction_mention_count="
        f"{report['input_prediction_mention_count']}"
    )
    print(f"[OK] trial_count={report['trial_count']}")
    print(f"[OK] eligible_trial_count={report['eligible_trial_count']}")
    print(f"[OK] pareto_trial_count={report['pareto_trial_count']}")
    for profile_name, profile in report["profile_summary"].items():
        policy = json.dumps(
            profile["policy"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        exact = profile["exact"]
        print(
            f"[OK] profile={profile_name} "
            f"trial_id={profile['trial_id']} "
            f"selected={profile['selected_prediction_count']} "
            f"exact_p={exact['precision']} "
            f"exact_r={exact['recall']} "
            f"exact_f1={exact['f1']} "
            f"policy={policy}"
        )
    print(f"[OK] model_inference_executed={report['model_inference_executed']}")
    print(f"[OK] output_dir={report['output_dir']}")
    print(f"[OK] next_slice={report['next_slice']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
