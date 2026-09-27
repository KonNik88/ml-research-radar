from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from radar_core.contracts.canonical_document import CanonicalDocument
from radar_core.contracts.scientific_entity_evaluation import (
    ScientificEntityEvaluationErrorKind,
    ScientificEntityReferenceMention,
    ScientificEntityReviewManifest,
    validate_reference_mention,
)
from radar_core.contracts.scientific_entity_evidence import (
    ScientificEntityMentionEvidence,
    ScientificEntitySourceField,
    ScientificEntityType,
    build_mention_id,
    sha256_text,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_independent_acceptance_gate import (
    canonical_config_sha256 as acceptance_gate_sha256,
    load_h2_independent_acceptance_gate_config,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_independent_evaluation import (
    ClassificationPerTypeRow,
    ClassificationSnapshot,
    ExtractionSnapshot,
    H2ComparativeCase,
    H2IndependentEvaluationManifest,
    H2IndependentEvaluationSummary,
    ScientificEntityH2IndependentEvaluationError,
    canonical_config_sha256 as evaluation_contract_sha256,
    load_h2_independent_evaluation_config,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_independent_inference import (
    H2IndependentInferenceManifest,
    H2IndependentInferenceSummary,
    H2IndependentPrediction,
)
from radar_core.entities.scientific_entity_evaluation import (
    evaluate_mentions,
    evaluation_config_sha256,
    load_evaluation_config,
)
from radar_core.entities.scientific_entity_semantic_typer_h2_independent_inference import (
    validate_h2_independent_inference,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = (
    PROJECT_ROOT
    / "configs"
    / "scientific_entity_semantic_typer_h2_independent_evaluation_v0.3.yaml"
)
DEFAULT_CANONICAL = (
    PROJECT_ROOT / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"
)
REPORT_NAME = "scientific_entity_semantic_typer_h2_independent_evaluation_v03"

REQUIRED_FILES = {
    "manifest.json",
    "comparative_summary.json",
    "baseline_evaluation.json",
    "h2_evaluation.json",
    "same_span_cases.jsonl",
    "corrected_errors.jsonl",
    "introduced_regressions.jsonl",
    "model_to_method_direct_corrections.jsonl",
    "model_to_method_wrong_to_wrong.jsonl",
    "README.md",
    "checksums.txt",
}
CHECKSUM_FILES = REQUIRED_FILES - {"checksums.txt"}


@dataclass(frozen=True, slots=True)
class _ComparablePrediction:
    evidence_id: str
    mention_id: str
    canonical_id: str
    source_field: ScientificEntitySourceField
    source_text_sha256: str
    char_start: int
    char_end: int
    surface_text: str
    entity_type: ScientificEntityType


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(payload: Any) -> bytes:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _jsonl_bytes(rows: Sequence[Any]) -> bytes:
    chunks: list[str] = []
    for row in rows:
        payload = row.model_dump(mode="json") if hasattr(row, "model_dump") else row
        chunks.append(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    return (("\n".join(chunks) + "\n") if chunks else "").encode("utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ScientificEntityH2IndependentEvaluationError(
            f"Expected JSON object: {path}"
        )
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip():
                raise ScientificEntityH2IndependentEvaluationError(
                    f"Blank JSONL line: {path}:{line_number}"
                )
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ScientificEntityH2IndependentEvaluationError(
                    f"Expected JSON object: {path}:{line_number}"
                )
            rows.append(payload)
    return rows


def _write_atomic(output_dir: Path, payloads: Mapping[str, bytes]) -> None:
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    if output_dir.exists():
        raise FileExistsError(
            f"Immutable H2 independent evaluation already exists: {output_dir}"
        )
    staging = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.tmp-", dir=output_dir.parent)
    )
    try:
        for name, data in payloads.items():
            (staging / name).write_bytes(data)
        staging.rename(output_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _checksums(payloads: Mapping[str, bytes]) -> bytes:
    names = sorted(name for name in payloads if name != "checksums.txt")
    return "".join(
        f"{hashlib.sha256(payloads[name]).hexdigest()}  {name}\n"
        for name in names
    ).encode("utf-8")


def _stable_id(prefix: str, parts: Sequence[str]) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"{prefix}:{digest}"


def _load_documents(
    path: Path,
    *,
    expected_count: int,
) -> tuple[tuple[CanonicalDocument, ...], dict[str, CanonicalDocument]]:
    docs = tuple(CanonicalDocument.model_validate(row) for row in _read_jsonl(path))
    if len(docs) != expected_count:
        raise ScientificEntityH2IndependentEvaluationError(
            f"Expected {expected_count} held-out documents, found {len(docs)}"
        )
    by_id = {row.canonical_id: row for row in docs}
    if len(by_id) != len(docs):
        raise ScientificEntityH2IndependentEvaluationError(
            "Duplicate canonical_id in held-out sample"
        )
    return docs, by_id


def _source_text(
    documents_by_id: Mapping[str, CanonicalDocument],
    *,
    canonical_id: str,
    source_field: ScientificEntitySourceField,
) -> str:
    document = documents_by_id.get(canonical_id)
    if document is None:
        raise ScientificEntityH2IndependentEvaluationError(
            f"Unknown canonical_id: {canonical_id}"
        )
    value = (
        document.title
        if source_field == ScientificEntitySourceField.TITLE
        else document.abstract
    )
    if value in (None, ""):
        raise ScientificEntityH2IndependentEvaluationError(
            f"Blank source field: {canonical_id}:{source_field.value}"
        )
    return value


def _validate_parent_state(
    *,
    root: Path,
    config_path: Path,
    sample_dir: Path,
    reference_dir: Path,
    development_package_dir: Path,
    previous_heldout_sample_dir: Path,
    frozen_candidate_dir: Path,
    canonical_path: Path,
    inference_dir: Path,
) -> dict[str, Any]:
    config = load_h2_independent_evaluation_config(config_path)

    gate_path = _resolve(root, config.acceptance_gate.config_path)
    gate = load_h2_independent_acceptance_gate_config(gate_path)
    gate_sha = acceptance_gate_sha256(gate)
    if gate_sha != config.acceptance_gate.config_sha256:
        raise ScientificEntityH2IndependentEvaluationError(
            "Independent acceptance gate SHA-256 drifted"
        )
    if gate.candidate_lineage.candidate_id != config.candidate.candidate_id:
        raise ScientificEntityH2IndependentEvaluationError(
            "Acceptance gate candidate_id drifted"
        )
    if (
        gate.candidate_lineage.candidate_fingerprint_sha256
        != config.candidate.candidate_fingerprint_sha256
    ):
        raise ScientificEntityH2IndependentEvaluationError(
            "Acceptance gate candidate fingerprint drifted"
        )

    comparative = gate.comparative_acceptance
    expected_gate = {
        "minimum_typer_coverage": config.acceptance_gate.minimum_typer_coverage,
        "minimum_same_span_accuracy_delta": (
            config.acceptance_gate.minimum_same_span_accuracy_delta
        ),
        "minimum_net_corrected_cases": (
            config.acceptance_gate.minimum_net_corrected_cases
        ),
        "maximum_regression_rate": config.acceptance_gate.maximum_regression_rate,
        "minimum_model_to_method_reduction_fraction": (
            config.acceptance_gate.minimum_model_to_method_reduction_fraction
        ),
        "minimum_macro_f1_delta": config.acceptance_gate.minimum_macro_f1_delta,
        "minimum_exact_f1": config.acceptance_gate.minimum_exact_f1,
        "desirable_minimum_relaxed_f1": (
            config.acceptance_gate.desirable_minimum_relaxed_f1
        ),
        "require_relaxed_f1_as_hard_gate": (
            config.acceptance_gate.relaxed_f1_is_hard_gate
        ),
        "required_metric_missing_denominator_policy": (
            config.acceptance_gate.missing_required_denominator_policy
        ),
    }
    actual_gate = {
        "minimum_typer_coverage": comparative.minimum_typer_coverage,
        "minimum_same_span_accuracy_delta": comparative.minimum_same_span_accuracy_delta,
        "minimum_net_corrected_cases": comparative.minimum_net_corrected_cases,
        "maximum_regression_rate": comparative.maximum_regression_rate,
        "minimum_model_to_method_reduction_fraction": comparative.minimum_model_to_method_reduction_fraction,
        "minimum_macro_f1_delta": comparative.minimum_macro_f1_delta,
        "minimum_exact_f1": comparative.minimum_exact_f1,
        "desirable_minimum_relaxed_f1": comparative.desirable_minimum_relaxed_f1,
        "require_relaxed_f1_as_hard_gate": comparative.require_relaxed_f1_as_hard_gate,
        "required_metric_missing_denominator_policy": comparative.required_metric_missing_denominator_policy,
    }
    if actual_gate != expected_gate:
        raise ScientificEntityH2IndependentEvaluationError(
            "Comparative acceptance snapshot drifted"
        )

    base_config_path = _resolve(root, config.base_evaluator.config_path)
    base_config = load_evaluation_config(base_config_path)
    if (
        base_config.matching.relaxed_min_char_iou
        != config.base_evaluator.relaxed_min_char_iou
    ):
        raise ScientificEntityH2IndependentEvaluationError(
            "Base evaluator relaxed IoU drifted"
        )
    if base_config.metrics.decimal_places != config.base_evaluator.decimal_places:
        raise ScientificEntityH2IndependentEvaluationError(
            "Base evaluator decimal_places drifted"
        )

    inference_config_path = _resolve(root, config.inference.config_path)
    checks, inference_summary = validate_h2_independent_inference(
        project_root=root,
        config_path=inference_config_path,
        sample_dir=sample_dir,
        reference_dir=reference_dir,
        development_package_dir=development_package_dir,
        previous_heldout_sample_dir=previous_heldout_sample_dir,
        frozen_candidate_dir=frozen_candidate_dir,
        canonical_path=canonical_path,
        inference_dir=inference_dir,
    )
    if any(not ok for _, ok, _ in checks) or inference_summary.get(
        "required_failed_count"
    ) != 0:
        raise ScientificEntityH2IndependentEvaluationError(
            "Frozen H2 inference evidence failed strict pre-evaluation validation"
        )
    required_inference = {
        "inference_id": config.inference.inference_id,
        "candidate_id": config.candidate.candidate_id,
        "candidate_fingerprint_sha256": (
            config.candidate.candidate_fingerprint_sha256
        ),
        "sample_id": config.fresh_heldout.sample_id,
        "review_id": config.fresh_heldout.review_id,
        "input_document_count": config.inference.expected_document_count,
        "baseline_prediction_count": (
            config.inference.expected_baseline_prediction_count
        ),
        "typer_coverage": config.inference.expected_typer_coverage,
        "h2_override_count": config.inference.expected_h2_override_count,
        "evaluation_executed": False,
        "acceptance_decision_made": False,
    }
    for key, expected in required_inference.items():
        if inference_summary.get(key) != expected:
            raise ScientificEntityH2IndependentEvaluationError(
                f"Inference lineage mismatch for {key}: "
                f"{inference_summary.get(key)!r} != {expected!r}"
            )

    inference_manifest_path = inference_dir / "manifest.json"
    inference_manifest = H2IndependentInferenceManifest.model_validate(
        _read_json(inference_manifest_path)
    )
    inference_runtime_summary = H2IndependentInferenceSummary.model_validate(
        _read_json(inference_dir / "summary.json")
    )
    if inference_manifest.inference_id != config.inference.inference_id:
        raise ScientificEntityH2IndependentEvaluationError(
            "Inference manifest ID drifted"
        )
    if (
        inference_manifest.baseline_prediction_count
        != config.inference.expected_baseline_prediction_count
    ):
        raise ScientificEntityH2IndependentEvaluationError(
            "Inference baseline count drifted"
        )
    if (
        inference_runtime_summary.typer_coverage
        != config.inference.expected_typer_coverage
    ):
        raise ScientificEntityH2IndependentEvaluationError(
            "Inference typer coverage drifted"
        )

    return {
        "config": config,
        "gate": gate,
        "gate_sha": gate_sha,
        "base_config": base_config,
        "base_config_path": base_config_path,
        "base_config_sha": evaluation_config_sha256(base_config),
        "inference_summary": inference_summary,
        "inference_manifest": inference_manifest,
        "inference_manifest_sha": _sha256_file(inference_manifest_path),
        "evaluation_config_sha": evaluation_contract_sha256(config),
    }


def _load_reference_and_predictions(
    *,
    parent: Mapping[str, Any],
    sample_dir: Path,
    reference_dir: Path,
    inference_dir: Path,
) -> tuple[
    tuple[ScientificEntityReferenceMention, ...],
    tuple[ScientificEntityMentionEvidence, ...],
    tuple[H2IndependentPrediction, ...],
]:
    config = parent["config"]
    sample_documents_path = (
        sample_dir / config.fresh_heldout.sample_documents_file
    )
    _, documents_by_id = _load_documents(
        sample_documents_path,
        expected_count=config.fresh_heldout.expected_document_count,
    )

    review_manifest_path = (
        reference_dir / config.fresh_heldout.reference_review_manifest_file
    )
    review_manifest = ScientificEntityReviewManifest.model_validate(
        _read_json(review_manifest_path)
    )
    if review_manifest.review_id != config.fresh_heldout.review_id:
        raise ScientificEntityH2IndependentEvaluationError(
            "Reference review_id drifted"
        )
    if not review_manifest.prediction_blind or not review_manifest.review_complete:
        raise ScientificEntityH2IndependentEvaluationError(
            "Reference is not complete prediction-blind evidence"
        )

    reference_path = reference_dir / config.fresh_heldout.reference_mentions_file
    reference_rows = tuple(
        ScientificEntityReferenceMention.model_validate(row)
        for row in _read_jsonl(reference_path)
    )
    if len(reference_rows) != config.fresh_heldout.expected_reference_mention_count:
        raise ScientificEntityH2IndependentEvaluationError(
            "Reference mention count drifted"
        )
    if _sha256_file(reference_path) != review_manifest.reference_mentions_sha256:
        raise ScientificEntityH2IndependentEvaluationError(
            "Reference mentions SHA-256 drifted"
        )
    for row in reference_rows:
        validate_reference_mention(
            row,
            source_text=_source_text(
                documents_by_id,
                canonical_id=row.canonical_id,
                source_field=row.source_field,
            ),
            review_id=review_manifest.review_id,
        )

    baseline_rows = tuple(
        ScientificEntityMentionEvidence.model_validate(row)
        for row in _read_jsonl(inference_dir / "baseline_mentions.jsonl")
    )
    if len(baseline_rows) != config.inference.expected_baseline_prediction_count:
        raise ScientificEntityH2IndependentEvaluationError(
            "Baseline prediction count drifted"
        )

    h2_rows = tuple(
        H2IndependentPrediction.model_validate(row)
        for row in _read_jsonl(inference_dir / "h2_predictions.jsonl")
    )
    if len(h2_rows) != config.inference.expected_h2_prediction_count:
        raise ScientificEntityH2IndependentEvaluationError(
            "H2 prediction count drifted"
        )

    baseline_by_evidence = {row.evidence_id: row for row in baseline_rows}
    if len(baseline_by_evidence) != len(baseline_rows):
        raise ScientificEntityH2IndependentEvaluationError(
            "Duplicate baseline evidence_id"
        )
    h2_by_evidence = {
        row.baseline_prediction_evidence_id: row for row in h2_rows
    }
    if len(h2_by_evidence) != len(h2_rows):
        raise ScientificEntityH2IndependentEvaluationError(
            "Duplicate H2 baseline_prediction_evidence_id"
        )
    if set(baseline_by_evidence) != set(h2_by_evidence):
        raise ScientificEntityH2IndependentEvaluationError(
            "H2 predictions are not a one-to-one typing view over baseline spans"
        )

    for evidence_id, baseline in baseline_by_evidence.items():
        h2 = h2_by_evidence[evidence_id]
        immutable = (
            baseline.canonical_id == h2.canonical_id
            and baseline.source_field == h2.source_field
            and baseline.source_text_sha256 == h2.source_text_sha256
            and baseline.char_start == h2.char_start
            and baseline.char_end == h2.char_end
            and baseline.surface_text == h2.surface_text
            and baseline.entity_type == h2.baseline_entity_type
        )
        if not immutable:
            raise ScientificEntityH2IndependentEvaluationError(
                "H2 prediction mutated a frozen baseline span"
            )
        source_text = _source_text(
            documents_by_id,
            canonical_id=h2.canonical_id,
            source_field=h2.source_field,
        )
        if source_text[h2.char_start : h2.char_end] != h2.surface_text:
            raise ScientificEntityH2IndependentEvaluationError(
                "H2 surface is not the exact source slice"
            )

    return reference_rows, baseline_rows, h2_rows


def _adapt_h2_predictions(
    h2_rows: Sequence[H2IndependentPrediction],
) -> tuple[_ComparablePrediction, ...]:
    output: list[_ComparablePrediction] = []
    for row in h2_rows:
        mention_id = build_mention_id(
            canonical_id=row.canonical_id,
            source_field=row.source_field,
            source_text_sha256=row.source_text_sha256,
            char_start=row.char_start,
            char_end=row.char_end,
            entity_type=row.final_entity_type,
        )
        output.append(
            _ComparablePrediction(
                evidence_id=row.baseline_prediction_evidence_id,
                mention_id=mention_id,
                canonical_id=row.canonical_id,
                source_field=row.source_field,
                source_text_sha256=row.source_text_sha256,
                char_start=row.char_start,
                char_end=row.char_end,
                surface_text=row.surface_text,
                entity_type=row.final_entity_type,
            )
        )
    return tuple(output)


def _guardrails(errors: Sequence[Any]) -> dict[str, Any]:
    pair_counts: Counter[tuple[str, str]] = Counter()
    predicted_sinks: Counter[str] = Counter()
    for row in errors:
        if row.error_kind != ScientificEntityEvaluationErrorKind.TYPE_MISMATCH:
            continue
        ref = row.reference_entity_type.value
        pred = row.prediction_entity_type.value
        pair_counts[(ref, pred)] += 1
        predicted_sinks[pred] += 1
    max_type = None
    max_count = 0
    if predicted_sinks:
        max_type, max_count = sorted(
            predicted_sinks.items(), key=lambda item: (-item[1], item[0])
        )[0]
    return {
        "model_to_method_count": pair_counts.get(("model", "method"), 0),
        "method_to_task_count": pair_counts.get(("method", "task"), 0),
        "total_type_mismatch_count": sum(pair_counts.values()),
        "method_semantic_sink_count": predicted_sinks.get("method", 0),
        "maximum_predicted_type_mismatch_sink_type": max_type,
        "maximum_any_predicted_type_mismatch_sink_count": max_count,
    }


def _extraction_snapshot(result) -> ExtractionSnapshot:
    return ExtractionSnapshot(
        prediction_mention_count=result.metrics.prediction_mention_count,
        exact_precision=result.metrics.micro.exact.precision,
        exact_recall=result.metrics.micro.exact.recall,
        exact_f1=result.metrics.micro.exact.f1,
        relaxed_precision=result.metrics.micro.relaxed.precision,
        relaxed_recall=result.metrics.micro.relaxed.recall,
        relaxed_f1=result.metrics.micro.relaxed.f1,
        exact_match_count=result.metrics.exact_match_count,
        relaxed_only_match_count=result.metrics.relaxed_only_match_count,
        **_guardrails(result.errors),
    )


def _span_key(row: Any) -> tuple[Any, ...]:
    return (
        row.canonical_id,
        row.source_field,
        row.source_text_sha256,
        row.char_start,
        row.char_end,
    )


def _same_span_cases(
    *,
    evaluation_id: str,
    references: Sequence[ScientificEntityReferenceMention],
    baseline_rows: Sequence[ScientificEntityMentionEvidence],
    h2_rows: Sequence[H2IndependentPrediction],
) -> tuple[H2ComparativeCase, ...]:
    refs_by_span: dict[tuple[Any, ...], list[ScientificEntityReferenceMention]] = (
        defaultdict(list)
    )
    baseline_by_span: dict[
        tuple[Any, ...], list[ScientificEntityMentionEvidence]
    ] = defaultdict(list)
    h2_by_evidence = {
        row.baseline_prediction_evidence_id: row for row in h2_rows
    }

    for row in references:
        refs_by_span[_span_key(row)].append(row)
    for row in baseline_rows:
        baseline_by_span[_span_key(row)].append(row)

    cases: list[H2ComparativeCase] = []
    for key in sorted(set(refs_by_span) & set(baseline_by_span), key=str):
        refs = sorted(refs_by_span[key], key=lambda row: row.reference_id)
        preds = sorted(
            baseline_by_span[key], key=lambda row: row.evidence_id
        )
        for reference, baseline in zip(refs, preds):
            h2 = h2_by_evidence[baseline.evidence_id]
            case_id = _stable_id(
                "h2-comparative-case",
                [evaluation_id, reference.reference_id, baseline.evidence_id],
            )
            cases.append(
                H2ComparativeCase(
                    case_id=case_id,
                    reference_id=reference.reference_id,
                    baseline_prediction_evidence_id=baseline.evidence_id,
                    canonical_id=reference.canonical_id,
                    source_field=reference.source_field.value,
                    source_text_sha256=reference.source_text_sha256,
                    char_start=reference.char_start,
                    char_end=reference.char_end,
                    surface_text=reference.surface_text,
                    reference_entity_type=reference.entity_type,
                    baseline_entity_type=baseline.entity_type,
                    h2_entity_type=h2.final_entity_type,
                    h2_override_applied=h2.h2_override_applied,
                    baseline_correct=(baseline.entity_type == reference.entity_type),
                    h2_correct=(h2.final_entity_type == reference.entity_type),
                )
            )
    cases.sort(key=lambda row: row.case_id)
    return tuple(cases)


def _classification_snapshot(
    cases: Sequence[H2ComparativeCase],
    *,
    prediction_field: str,
    decimal_places: int,
) -> ClassificationSnapshot:
    correct = 0
    rows: list[ClassificationPerTypeRow] = []
    f1_values: list[float] = []
    for entity_type in ScientificEntityType:
        reference_support = sum(
            row.reference_entity_type == entity_type for row in cases
        )
        prediction_support = sum(
            getattr(row, prediction_field) == entity_type for row in cases
        )
        tp = sum(
            row.reference_entity_type == entity_type
            and getattr(row, prediction_field) == entity_type
            for row in cases
        )
        precision = (
            round(tp / prediction_support, decimal_places)
            if prediction_support
            else 0.0
        )
        recall = (
            round(tp / reference_support, decimal_places)
            if reference_support
            else None
        )
        if recall is None:
            f1 = None
        elif precision + recall == 0:
            f1 = 0.0
        else:
            f1 = round(
                2 * precision * recall / (precision + recall),
                decimal_places,
            )
        if f1 is not None:
            f1_values.append(f1)
        rows.append(
            ClassificationPerTypeRow(
                entity_type=entity_type,
                reference_support=reference_support,
                prediction_support=prediction_support,
                true_positive=tp,
                precision=precision,
                recall=recall,
                f1=f1,
            )
        )
    correct = sum(
        getattr(row, prediction_field) == row.reference_entity_type
        for row in cases
    )
    accuracy = (
        round(correct / len(cases), decimal_places) if cases else None
    )
    macro_f1 = (
        round(sum(f1_values) / len(ScientificEntityType), decimal_places)
        if len(f1_values) == len(ScientificEntityType)
        else None
    )
    return ClassificationSnapshot(
        case_count=len(cases),
        correct_count=correct,
        accuracy=accuracy,
        macro_f1=macro_f1,
        per_type=rows,
    )


def compute_h2_independent_evaluation(
    *,
    parent: Mapping[str, Any],
    sample_dir: Path,
    reference_dir: Path,
    inference_dir: Path,
) -> dict[str, Any]:
    config = parent["config"]
    references, baseline_rows, h2_rows = _load_reference_and_predictions(
        parent=parent,
        sample_dir=sample_dir,
        reference_dir=reference_dir,
        inference_dir=inference_dir,
    )
    h2_predictions = _adapt_h2_predictions(h2_rows)

    baseline_result = evaluate_mentions(
        evaluation_id=config.execution.evaluation_id + "-baseline",
        document_count=config.fresh_heldout.expected_document_count,
        references=references,
        predictions=baseline_rows,
        config=parent["base_config"],
    )
    h2_result = evaluate_mentions(
        evaluation_id=config.execution.evaluation_id + "-h2",
        document_count=config.fresh_heldout.expected_document_count,
        references=references,
        predictions=h2_predictions,
        config=parent["base_config"],
    )
    cases = _same_span_cases(
        evaluation_id=config.execution.evaluation_id,
        references=references,
        baseline_rows=baseline_rows,
        h2_rows=h2_rows,
    )

    if config.comparative.require_nonzero_same_span_pair_count and not cases:
        raise ScientificEntityH2IndependentEvaluationError(
            "Required same-span comparative denominator is zero"
        )
    per_type_support = Counter(
        row.reference_entity_type for row in cases
    )
    if (
        config.comparative.require_nonzero_reference_support_for_all_six_types
        and any(per_type_support[kind] == 0 for kind in ScientificEntityType)
    ):
        raise ScientificEntityH2IndependentEvaluationError(
            "Same-span comparative population has zero reference support for at least one entity type"
        )

    baseline_typing = _classification_snapshot(
        cases,
        prediction_field="baseline_entity_type",
        decimal_places=config.base_evaluator.decimal_places,
    )
    h2_typing = _classification_snapshot(
        cases,
        prediction_field="h2_entity_type",
        decimal_places=config.base_evaluator.decimal_places,
    )
    if baseline_typing.accuracy is None or h2_typing.accuracy is None:
        raise ScientificEntityH2IndependentEvaluationError(
            "Same-span accuracy denominator is missing"
        )
    if baseline_typing.macro_f1 is None or h2_typing.macro_f1 is None:
        raise ScientificEntityH2IndependentEvaluationError(
            "Same-span macro-F1 denominator is missing"
        )

    corrected = tuple(
        row for row in cases if not row.baseline_correct and row.h2_correct
    )
    regressions = tuple(
        row for row in cases if row.baseline_correct and not row.h2_correct
    )
    baseline_correct_count = baseline_typing.correct_count
    if (
        config.comparative.require_nonzero_baseline_correct_count
        and baseline_correct_count == 0
    ):
        raise ScientificEntityH2IndependentEvaluationError(
            "Regression-rate denominator is zero"
        )
    regression_rate = round(
        len(regressions) / baseline_correct_count,
        config.base_evaluator.decimal_places,
    )

    baseline_m2m = tuple(
        row
        for row in cases
        if row.reference_entity_type == ScientificEntityType.MODEL
        and row.baseline_entity_type == ScientificEntityType.METHOD
    )
    h2_m2m = tuple(
        row
        for row in cases
        if row.reference_entity_type == ScientificEntityType.MODEL
        and row.h2_entity_type == ScientificEntityType.METHOD
    )
    if (
        config.comparative.require_nonzero_baseline_model_to_method_count
        and not baseline_m2m
    ):
        raise ScientificEntityH2IndependentEvaluationError(
            "model->method reduction denominator is zero"
        )
    reduction = round(
        (len(baseline_m2m) - len(h2_m2m)) / len(baseline_m2m),
        config.base_evaluator.decimal_places,
    )

    direct = tuple(
        row
        for row in baseline_m2m
        if row.h2_entity_type == ScientificEntityType.MODEL
        and row.h2_correct
    )
    wrong_to_wrong = tuple(
        row
        for row in baseline_m2m
        if row.h2_entity_type != row.baseline_entity_type
        and not row.h2_correct
    )

    summary = H2IndependentEvaluationSummary(
        evaluation_id=config.execution.evaluation_id,
        inference_id=config.inference.inference_id,
        document_count=48,
        reference_mention_count=929,
        typer_coverage=parent["inference_summary"]["typer_coverage"],
        same_span_pair_count=len(cases),
        baseline_typing=baseline_typing,
        h2_typing=h2_typing,
        same_span_accuracy_delta=round(
            h2_typing.accuracy - baseline_typing.accuracy,
            config.base_evaluator.decimal_places,
        ),
        macro_f1_delta=round(
            h2_typing.macro_f1 - baseline_typing.macro_f1,
            config.base_evaluator.decimal_places,
        ),
        corrected_errors=len(corrected),
        introduced_regressions=len(regressions),
        net_corrected_cases=len(corrected) - len(regressions),
        regression_rate=regression_rate,
        baseline_model_to_method_count=len(baseline_m2m),
        h2_model_to_method_count=len(h2_m2m),
        model_to_method_reduction_fraction=reduction,
        model_to_method_direct_corrections=len(direct),
        model_to_method_wrong_to_wrong=len(wrong_to_wrong),
        baseline_extraction=_extraction_snapshot(baseline_result),
        h2_extraction=_extraction_snapshot(h2_result),
    )
    return {
        "summary": summary,
        "cases": cases,
        "corrected": corrected,
        "regressions": regressions,
        "direct": direct,
        "wrong_to_wrong": wrong_to_wrong,
    }


def _readme(config) -> bytes:
    text = (
        "# H2 v0.3 independent comparative evaluation\n\n"
        f"Evaluation ID: `{config.execution.evaluation_id}`\n\n"
        f"Inference ID: `{config.inference.inference_id}`\n\n"
        "This immutable package compares the frozen v0.2c baseline typing view and "
        "the frozen H2 selective method-to-model intervention against the same frozen "
        "prediction-blind human reference.\n\n"
        "The existing Scientific Entity Evaluation v0.1 matching semantics are reused "
        "for extraction exact/relaxed metrics. Comparative typing metrics are computed "
        "only on deterministic exact-span type-agnostic pairs.\n\n"
        "This slice does not make an acceptance decision, does not tune thresholds, "
        "does not revise policy, does not run model inference, does not select a "
        "production extractor, and does not authorize a full-corpus build.\n"
    )
    return text.encode("utf-8")


def plan_or_execute_h2_independent_evaluation(
    *,
    project_root: Path,
    config_path: Path,
    sample_dir: Path,
    reference_dir: Path,
    development_package_dir: Path,
    previous_heldout_sample_dir: Path,
    frozen_candidate_dir: Path,
    canonical_path: Path,
    inference_dir: Path,
    execute: bool = False,
) -> dict[str, Any]:
    root = project_root.resolve()
    parent = _validate_parent_state(
        root=root,
        config_path=config_path.resolve(),
        sample_dir=sample_dir.resolve(),
        reference_dir=reference_dir.resolve(),
        development_package_dir=development_package_dir.resolve(),
        previous_heldout_sample_dir=previous_heldout_sample_dir.resolve(),
        frozen_candidate_dir=frozen_candidate_dir.resolve(),
        canonical_path=canonical_path.resolve(),
        inference_dir=inference_dir.resolve(),
    )
    config = parent["config"]
    output_dir = _resolve(root, config.execution.output_root) / config.execution.evaluation_id
    already_executed = output_dir.exists()
    if execute and already_executed:
        raise FileExistsError(
            f"Immutable H2 independent evaluation already exists: {output_dir}"
        )

    report: dict[str, Any] = {
        "report": REPORT_NAME,
        "mode": "execute" if execute else "plan",
        "phase_complete": False,
        "candidate_id": config.candidate.candidate_id,
        "candidate_fingerprint_sha256": config.candidate.candidate_fingerprint_sha256,
        "sample_id": config.fresh_heldout.sample_id,
        "review_id": config.fresh_heldout.review_id,
        "inference_id": config.inference.inference_id,
        "document_count": config.fresh_heldout.expected_document_count,
        "reference_mention_count": config.fresh_heldout.expected_reference_mention_count,
        "baseline_prediction_count": config.inference.expected_baseline_prediction_count,
        "h2_prediction_count": config.inference.expected_h2_prediction_count,
        "inference_validation_required_failed_count": parent["inference_summary"]["required_failed_count"],
        "gate_config_sha256": parent["gate_sha"],
        "base_evaluator_config_sha256": parent["base_config_sha"],
        "evaluation_id": config.execution.evaluation_id,
        "output_dir": str(output_dir).replace("\\", "/"),
        "one_shot_already_executed": already_executed,
        "plan_runs_evaluation": False,
        "plan_exposes_quality_metrics": False,
        "model_inference_executed_in_this_slice": False,
        "threshold_tuning_executed": False,
        "policy_revision_executed": False,
        "reference_labels_used_for_evaluation": True,
        "reference_labels_used_for_filtering": False,
        "evaluation_executed": False,
        "acceptance_decision_made": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "next_slice": config.next_steps.after_plan,
    }
    if not execute:
        return report

    computed = compute_h2_independent_evaluation(
        parent=parent,
        sample_dir=sample_dir.resolve(),
        reference_dir=reference_dir.resolve(),
        inference_dir=inference_dir.resolve(),
    )
    summary = computed["summary"]

    payloads: dict[str, bytes] = {
        "comparative_summary.json": _json_bytes(summary),
        "baseline_evaluation.json": _json_bytes(summary.baseline_extraction),
        "h2_evaluation.json": _json_bytes(summary.h2_extraction),
        "same_span_cases.jsonl": _jsonl_bytes(computed["cases"]),
        "corrected_errors.jsonl": _jsonl_bytes(computed["corrected"]),
        "introduced_regressions.jsonl": _jsonl_bytes(computed["regressions"]),
        "model_to_method_direct_corrections.jsonl": _jsonl_bytes(computed["direct"]),
        "model_to_method_wrong_to_wrong.jsonl": _jsonl_bytes(computed["wrong_to_wrong"]),
        "README.md": _readme(config),
    }
    file_hashes = {
        name: hashlib.sha256(data).hexdigest()
        for name, data in payloads.items()
    }
    manifest = H2IndependentEvaluationManifest(
        evaluation_id=config.execution.evaluation_id,
        inference_id=config.inference.inference_id,
        candidate_id=config.candidate.candidate_id,
        candidate_fingerprint_sha256=config.candidate.candidate_fingerprint_sha256,
        sample_id=config.fresh_heldout.sample_id,
        review_id=config.fresh_heldout.review_id,
        evaluation_config_sha256=parent["evaluation_config_sha"],
        acceptance_gate_config_sha256=parent["gate_sha"],
        base_evaluator_config_sha256=parent["base_config_sha"],
        inference_manifest_sha256=parent["inference_manifest_sha"],
        reference_mentions_sha256=parent["inference_manifest"].reference_mentions_sha256,
        document_count=48,
        reference_mention_count=929,
        baseline_prediction_count=830,
        h2_prediction_count=830,
        files=file_hashes,
        next_slice=config.next_steps.after_execute,
    )
    payloads["manifest.json"] = _json_bytes(manifest)
    payloads["checksums.txt"] = _checksums(payloads)
    _write_atomic(output_dir, payloads)

    report.update(
        {
            "phase_complete": True,
            "one_shot_already_executed": True,
            "evaluation_executed": True,
            "same_span_pair_count": summary.same_span_pair_count,
            "typer_coverage": summary.typer_coverage,
            "baseline_same_span_accuracy": summary.baseline_typing.accuracy,
            "h2_same_span_accuracy": summary.h2_typing.accuracy,
            "same_span_accuracy_delta": summary.same_span_accuracy_delta,
            "baseline_macro_f1": summary.baseline_typing.macro_f1,
            "h2_macro_f1": summary.h2_typing.macro_f1,
            "macro_f1_delta": summary.macro_f1_delta,
            "corrected_errors": summary.corrected_errors,
            "introduced_regressions": summary.introduced_regressions,
            "net_corrected_cases": summary.net_corrected_cases,
            "regression_rate": summary.regression_rate,
            "baseline_model_to_method_count": summary.baseline_model_to_method_count,
            "h2_model_to_method_count": summary.h2_model_to_method_count,
            "model_to_method_reduction_fraction": summary.model_to_method_reduction_fraction,
            "h2_exact_f1": summary.h2_extraction.exact_f1,
            "h2_relaxed_f1": summary.h2_extraction.relaxed_f1,
            "acceptance_decision_made": False,
            "next_slice": config.next_steps.after_execute,
        }
    )
    return report



def _parse_checksums(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line_number, raw in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if "  " not in raw:
            raise ScientificEntityH2IndependentEvaluationError(
                f"Invalid checksum row: {line_number}"
            )
        digest, name = raw.split("  ", 1)
        if name in result:
            raise ScientificEntityH2IndependentEvaluationError(
                f"Duplicate checksum filename: {name}"
            )
        result[name] = digest
    return result


def _lf_ok(path: Path) -> bool:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw:
        return False
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return (not raw) or raw.endswith(b"\n")


def validate_h2_independent_evaluation(
    *,
    project_root: Path,
    config_path: Path,
    sample_dir: Path,
    reference_dir: Path,
    development_package_dir: Path,
    previous_heldout_sample_dir: Path,
    frozen_candidate_dir: Path,
    canonical_path: Path,
    inference_dir: Path,
    evaluation_dir: Path,
) -> tuple[list[tuple[str, bool, str]], dict[str, Any]]:
    root = project_root.resolve()
    config = load_h2_independent_evaluation_config(config_path.resolve())
    evaluation_dir = evaluation_dir.resolve()

    checks: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: Any = "") -> None:
        checks.append((name, bool(ok), str(detail)))

    add("evaluation_directory_exists", evaluation_dir.is_dir(), evaluation_dir)
    if not evaluation_dir.is_dir():
        return checks, {
            "report": REPORT_NAME,
            "validation_scope": "h2_independent_comparative_evaluation",
            "total_checks": len(checks),
            "required_failed_count": 1,
            "next_slice": "fix_h2_v03_independent_comparative_evaluation",
        }

    actual_files = {path.name for path in evaluation_dir.iterdir() if path.is_file()}
    add("exact_file_layout", actual_files == REQUIRED_FILES, sorted(actual_files))

    checksum_map: dict[str, str] = {}
    try:
        checksum_map = _parse_checksums(evaluation_dir / "checksums.txt")
        add("checksums_parse", True)
    except Exception as exc:
        add("checksums_parse", False, exc)
    add(
        "checksum_filename_set",
        set(checksum_map) == CHECKSUM_FILES,
        sorted(checksum_map),
    )
    for name in sorted(CHECKSUM_FILES):
        add(
            f"checksum:{name}",
            (evaluation_dir / name).is_file()
            and checksum_map.get(name) == _sha256_file(evaluation_dir / name),
            name,
        )
    for name in sorted(REQUIRED_FILES):
        path = evaluation_dir / name
        add(f"lf:{name}", path.is_file() and _lf_ok(path), name)

    try:
        manifest = H2IndependentEvaluationManifest.model_validate(
            _read_json(evaluation_dir / "manifest.json")
        )
        summary = H2IndependentEvaluationSummary.model_validate(
            _read_json(evaluation_dir / "comparative_summary.json")
        )
        add("manifest_schema_valid", True)
        add("summary_schema_valid", True)
    except Exception as exc:
        add("manifest_schema_valid", False, exc)
        add("summary_schema_valid", False, exc)
        failed = sum(not ok for _, ok, _ in checks)
        return checks, {
            "report": REPORT_NAME,
            "validation_scope": "h2_independent_comparative_evaluation",
            "total_checks": len(checks),
            "required_failed_count": failed,
            "next_slice": "fix_h2_v03_independent_comparative_evaluation",
        }

    add(
        "directory_matches_evaluation_id",
        evaluation_dir.name == config.execution.evaluation_id == manifest.evaluation_id,
        evaluation_dir.name,
    )
    add(
        "config_sha_matches",
        manifest.evaluation_config_sha256 == evaluation_contract_sha256(config),
        manifest.evaluation_config_sha256,
    )
    add("inference_id_matches", manifest.inference_id == config.inference.inference_id)
    add("candidate_id_matches", manifest.candidate_id == config.candidate.candidate_id)
    add(
        "candidate_fingerprint_matches",
        manifest.candidate_fingerprint_sha256
        == config.candidate.candidate_fingerprint_sha256,
    )
    add("sample_id_matches", manifest.sample_id == config.fresh_heldout.sample_id)
    add("review_id_matches", manifest.review_id == config.fresh_heldout.review_id)
    add(
        "document_count_matches",
        manifest.document_count == 48 == summary.document_count,
    )
    add(
        "reference_count_matches",
        manifest.reference_mention_count == 929 == summary.reference_mention_count,
    )
    add("baseline_count_matches", manifest.baseline_prediction_count == 830)
    add("h2_count_matches", manifest.h2_prediction_count == 830)
    add(
        "manifest_fail_closed_safety",
        all(
            (
                manifest.inference_validated_before_evaluation is True,
                manifest.reference_labels_used_for_evaluation is True,
                manifest.reference_labels_used_for_filtering is False,
                manifest.model_inference_executed_in_this_slice is False,
                manifest.threshold_tuning_executed is False,
                manifest.policy_revision_executed is False,
                manifest.span_mutated is False,
                manifest.evaluation_executed is True,
                manifest.acceptance_decision_made is False,
                manifest.canonical_truth_mutated is False,
                manifest.production_extractor_selected is False,
                manifest.full_corpus_build_authorized is False,
                manifest.publication_ready is False,
            )
        ),
    )
    add(
        "summary_fail_closed_safety",
        all(
            (
                summary.required_metric_denominators_present is True,
                summary.evaluation_executed is True,
                summary.acceptance_decision_made is False,
                summary.threshold_tuning_executed is False,
                summary.policy_revision_executed is False,
                summary.canonical_truth_mutated is False,
                summary.production_extractor_selected is False,
                summary.full_corpus_build_authorized is False,
            )
        ),
    )
    add(
        "next_slice_is_validation",
        manifest.next_slice
        == "validate_h2_v03_independent_comparative_evaluation",
        manifest.next_slice,
    )

    parent = _validate_parent_state(
        root=root,
        config_path=config_path.resolve(),
        sample_dir=sample_dir.resolve(),
        reference_dir=reference_dir.resolve(),
        development_package_dir=development_package_dir.resolve(),
        previous_heldout_sample_dir=previous_heldout_sample_dir.resolve(),
        frozen_candidate_dir=frozen_candidate_dir.resolve(),
        canonical_path=canonical_path.resolve(),
        inference_dir=inference_dir.resolve(),
    )
    add(
        "acceptance_gate_sha_matches",
        manifest.acceptance_gate_config_sha256 == parent["gate_sha"],
        manifest.acceptance_gate_config_sha256,
    )
    add(
        "base_evaluator_config_sha_matches",
        manifest.base_evaluator_config_sha256 == parent["base_config_sha"],
        manifest.base_evaluator_config_sha256,
    )
    add(
        "inference_manifest_sha_matches",
        manifest.inference_manifest_sha256 == parent["inference_manifest_sha"],
        manifest.inference_manifest_sha256,
    )
    add(
        "reference_mentions_sha_matches",
        manifest.reference_mentions_sha256
        == parent["inference_manifest"].reference_mentions_sha256,
        manifest.reference_mentions_sha256,
    )

    recomputed = compute_h2_independent_evaluation(
        parent=parent,
        sample_dir=sample_dir.resolve(),
        reference_dir=reference_dir.resolve(),
        inference_dir=inference_dir.resolve(),
    )
    recomputed_summary = recomputed["summary"]
    add(
        "comparative_summary_recomputes_exactly",
        summary.model_dump(mode="json")
        == recomputed_summary.model_dump(mode="json"),
    )

    expected_files = {
        "baseline_evaluation.json": _json_bytes(
            recomputed_summary.baseline_extraction
        ),
        "h2_evaluation.json": _json_bytes(recomputed_summary.h2_extraction),
        "same_span_cases.jsonl": _jsonl_bytes(recomputed["cases"]),
        "corrected_errors.jsonl": _jsonl_bytes(recomputed["corrected"]),
        "introduced_regressions.jsonl": _jsonl_bytes(recomputed["regressions"]),
        "model_to_method_direct_corrections.jsonl": _jsonl_bytes(
            recomputed["direct"]
        ),
        "model_to_method_wrong_to_wrong.jsonl": _jsonl_bytes(
            recomputed["wrong_to_wrong"]
        ),
    }
    for name, expected in expected_files.items():
        add(
            f"recomputed:{name}",
            (evaluation_dir / name).read_bytes() == expected,
            name,
        )

    case_rows = [
        H2ComparativeCase.model_validate(row)
        for row in _read_jsonl(evaluation_dir / "same_span_cases.jsonl")
    ]
    add(
        "same_span_case_ids_unique",
        len({row.case_id for row in case_rows}) == len(case_rows),
        len(case_rows),
    )
    add(
        "case_count_matches_summary",
        len(case_rows) == summary.same_span_pair_count,
        len(case_rows),
    )

    failed = sum(not ok for _, ok, _ in checks)
    result = {
        "report": REPORT_NAME,
        "validation_scope": "h2_independent_comparative_evaluation",
        "evaluation_id": manifest.evaluation_id,
        "inference_id": manifest.inference_id,
        "candidate_id": manifest.candidate_id,
        "sample_id": manifest.sample_id,
        "review_id": manifest.review_id,
        "document_count": manifest.document_count,
        "reference_mention_count": manifest.reference_mention_count,
        "baseline_prediction_count": manifest.baseline_prediction_count,
        "h2_prediction_count": manifest.h2_prediction_count,
        "same_span_pair_count": summary.same_span_pair_count,
        "typer_coverage": summary.typer_coverage,
        "baseline_same_span_accuracy": summary.baseline_typing.accuracy,
        "h2_same_span_accuracy": summary.h2_typing.accuracy,
        "same_span_accuracy_delta": summary.same_span_accuracy_delta,
        "baseline_macro_f1": summary.baseline_typing.macro_f1,
        "h2_macro_f1": summary.h2_typing.macro_f1,
        "macro_f1_delta": summary.macro_f1_delta,
        "corrected_errors": summary.corrected_errors,
        "introduced_regressions": summary.introduced_regressions,
        "net_corrected_cases": summary.net_corrected_cases,
        "regression_rate": summary.regression_rate,
        "baseline_model_to_method_count": summary.baseline_model_to_method_count,
        "h2_model_to_method_count": summary.h2_model_to_method_count,
        "model_to_method_reduction_fraction": (
            summary.model_to_method_reduction_fraction
        ),
        "h2_exact_f1": summary.h2_extraction.exact_f1,
        "h2_relaxed_f1": summary.h2_extraction.relaxed_f1,
        "evaluation_executed": True,
        "acceptance_decision_made": False,
        "threshold_tuning_executed": False,
        "policy_revision_executed": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "total_checks": len(checks),
        "required_failed_count": failed,
        "next_slice": (
            config.next_steps.after_validation
            if failed == 0
            else "fix_h2_v03_independent_comparative_evaluation"
        ),
    }
    return checks, result


__all__ = [
    "PROJECT_ROOT",
    "DEFAULT_CONFIG",
    "DEFAULT_CANONICAL",
    "REPORT_NAME",
    "REQUIRED_FILES",
    "CHECKSUM_FILES",
    "compute_h2_independent_evaluation",
    "plan_or_execute_h2_independent_evaluation",
    "validate_h2_independent_evaluation",
]
