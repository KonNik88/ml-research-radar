from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from pydantic import ValidationError

from radar_core.contracts.canonical_document import CanonicalDocument
from radar_core.contracts.scientific_entity_evaluation import (
    EVALUATION_ERROR_SCHEMA_VERSION,
    EVALUATION_MATCH_SCHEMA_VERSION,
    METRICS_SCHEMA_VERSION,
    PER_TYPE_METRICS_SCHEMA_VERSION,
    ScientificEntityDataSufficiency,
    ScientificEntityEvaluationError,
    ScientificEntityEvaluationErrorKind,
    ScientificEntityEvaluationManifest,
    ScientificEntityEvaluationMatch,
    ScientificEntityEvaluationMetrics,
    ScientificEntityMatchingMetrics,
    ScientificEntityMatchKind,
    ScientificEntityMetricCounts,
    ScientificEntityPerTypeMetricRow,
    ScientificEntityPerTypeMetrics,
    ScientificEntityReferenceMention,
    ScientificEntityReviewManifest,
    build_evaluation_error_id,
    build_evaluation_match_id,
    validate_reference_mention,
)
from radar_core.contracts.scientific_entity_evidence import (
    ScientificEntityEvidenceManifest,
    ScientificEntityMentionEvidence,
    ScientificEntitySourceField,
    ScientificEntityType,
    validate_mention_evidence,
)
from radar_core.entities.scientific_entity_evaluation import (
    ScientificEntityEvaluationConfig,
    evaluation_config_sha256,
    load_evaluation_config,
)


REPORT_BASENAME = "scientific_entity_evaluation"
REPORT_SCHEMA_VERSION = "scientific_entity_evaluation_validation_v0.1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = (
    PROJECT_ROOT / "configs" / "scientific_entity_evaluation_v0.1.yaml"
)
REQUIRED_FILES = (
    "manifest.json",
    "metrics.json",
    "per_type_metrics.json",
    "matches.jsonl",
    "errors.jsonl",
    "README.md",
    "checksums.txt",
)
CHECKSUM_FILES = REQUIRED_FILES[:-1]
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    ok: bool
    required: bool = True
    details: str | None = None


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


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now_utc().isoformat()


def _now_slug() -> str:
    return _now_utc().strftime("%Y%m%dT%H%M%S%fZ")


def _add(
    checks: list[CheckResult],
    name: str,
    ok: bool,
    details: str | None = None,
    *,
    required: bool = True,
) -> None:
    checks.append(CheckResult(name=name, ok=bool(ok), required=required, details=details))


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
                raise ValueError(f"JSONL exceeds hard limit {hard_limit}: {path}")
    return rows


def _text_is_utf8_lf(path: Path) -> tuple[bool, str | None]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return False, "UTF-8 BOM is forbidden"
    if b"\r" in raw:
        return False, "CR or CRLF line endings are forbidden"
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return False, f"invalid UTF-8: {exc}"
    if raw and not raw.endswith(b"\n"):
        return False, "text file must end with LF"
    return True, None


def _parse_checksums(path: Path) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if "  " not in raw_line:
            raise ValueError(f"Invalid checksum row at line {line_number}")
        digest, filename = raw_line.split("  ", 1)
        if not SHA256_RE.fullmatch(digest):
            raise ValueError(f"Invalid checksum digest at line {line_number}")
        if not filename or filename in parsed:
            raise ValueError(f"Invalid or duplicate checksum path at line {line_number}")
        parsed[filename] = digest
    return parsed


def _load_documents(
    path: Path,
    *,
    hard_limit: int,
) -> tuple[list[CanonicalDocument], dict[str, CanonicalDocument]]:
    rows = _read_jsonl(path, hard_limit=hard_limit)
    documents: list[CanonicalDocument] = []
    by_id: dict[str, CanonicalDocument] = {}
    for row in rows:
        document = CanonicalDocument.model_validate(row)
        if document.canonical_id in by_id:
            raise ValueError(f"Duplicate canonical_id: {document.canonical_id}")
        documents.append(document)
        by_id[document.canonical_id] = document
    if not documents:
        raise ValueError("Canonical-shaped input is empty")
    return documents, by_id


def _source_text(
    documents_by_id: Mapping[str, CanonicalDocument],
    record: ScientificEntityReferenceMention | ScientificEntityMentionEvidence,
) -> str:
    document = documents_by_id.get(record.canonical_id)
    if document is None:
        raise ValueError(f"Unknown canonical_id: {record.canonical_id}")
    value = (
        document.title
        if record.source_field == ScientificEntitySourceField.TITLE
        else document.abstract
    )
    if value is None or value == "":
        raise ValueError(
            f"Blank source text: {record.canonical_id}:{record.source_field.value}"
        )
    return value


def _same_text(left: Any, right: Any) -> bool:
    return (
        left.canonical_id == right.canonical_id
        and left.source_field == right.source_field
        and left.source_text_sha256 == right.source_text_sha256
    )


def _span_values(
    reference: ScientificEntityReferenceMention,
    prediction: ScientificEntityMentionEvidence,
) -> tuple[int, int, float, int]:
    intersection = max(
        0,
        min(reference.char_end, prediction.char_end)
        - max(reference.char_start, prediction.char_start),
    )
    union = max(reference.char_end, prediction.char_end) - min(
        reference.char_start,
        prediction.char_start,
    )
    iou = intersection / union if union else 0.0
    boundary_distance = abs(reference.char_start - prediction.char_start) + abs(
        reference.char_end - prediction.char_end
    )
    return intersection, union, iou, boundary_distance


def _greedy_pairs(
    candidates: Sequence[tuple[tuple[Any, ...], Any, Any]],
) -> list[tuple[Any, Any]]:
    selected: list[tuple[Any, Any]] = []
    used_references: set[str] = set()
    used_predictions: set[str] = set()
    for _, reference, prediction in sorted(candidates, key=lambda row: row[0]):
        if reference.reference_id in used_references:
            continue
        if prediction.evidence_id in used_predictions:
            continue
        used_references.add(reference.reference_id)
        used_predictions.add(prediction.evidence_id)
        selected.append((reference, prediction))
    return selected


def _independent_pairs(
    *,
    references: Sequence[ScientificEntityReferenceMention],
    predictions: Sequence[ScientificEntityMentionEvidence],
    min_iou: float,
) -> tuple[
    list[tuple[ScientificEntityMatchKind, Any, Any]],
    list[tuple[ScientificEntityEvaluationErrorKind, Any | None, Any | None]],
]:
    exact_candidates: list[tuple[tuple[Any, ...], Any, Any]] = []
    for reference in references:
        for prediction in predictions:
            if not _same_text(reference, prediction):
                continue
            if reference.entity_type != prediction.entity_type:
                continue
            if (
                reference.char_start == prediction.char_start
                and reference.char_end == prediction.char_end
            ):
                exact_candidates.append(
                    ((reference.reference_id, prediction.evidence_id), reference, prediction)
                )
    exact = _greedy_pairs(exact_candidates)
    used_references = {reference.reference_id for reference, _ in exact}
    used_predictions = {prediction.evidence_id for _, prediction in exact}

    relaxed_candidates: list[tuple[tuple[Any, ...], Any, Any]] = []
    for reference in references:
        if reference.reference_id in used_references:
            continue
        for prediction in predictions:
            if prediction.evidence_id in used_predictions:
                continue
            if not _same_text(reference, prediction):
                continue
            if reference.entity_type != prediction.entity_type:
                continue
            intersection, _, iou, distance = _span_values(reference, prediction)
            if intersection > 0 and iou >= min_iou:
                relaxed_candidates.append(
                    (
                        (-iou, distance, reference.reference_id, prediction.evidence_id),
                        reference,
                        prediction,
                    )
                )
    relaxed = _greedy_pairs(relaxed_candidates)
    used_references.update(reference.reference_id for reference, _ in relaxed)
    used_predictions.update(prediction.evidence_id for _, prediction in relaxed)

    errors: list[
        tuple[ScientificEntityEvaluationErrorKind, Any | None, Any | None]
    ] = [
        (ScientificEntityEvaluationErrorKind.BOUNDARY_MISMATCH, reference, prediction)
        for reference, prediction in relaxed
    ]

    type_candidates: list[tuple[tuple[Any, ...], Any, Any]] = []
    for reference in references:
        if reference.reference_id in used_references:
            continue
        for prediction in predictions:
            if prediction.evidence_id in used_predictions:
                continue
            if not _same_text(reference, prediction):
                continue
            if reference.entity_type == prediction.entity_type:
                continue
            intersection, _, iou, distance = _span_values(reference, prediction)
            if intersection <= 0:
                continue
            exact_span_rank = int(
                not (
                    reference.char_start == prediction.char_start
                    and reference.char_end == prediction.char_end
                )
            )
            type_candidates.append(
                (
                    (
                        exact_span_rank,
                        -iou,
                        distance,
                        reference.reference_id,
                        prediction.evidence_id,
                    ),
                    reference,
                    prediction,
                )
            )
    type_pairs = _greedy_pairs(type_candidates)
    used_references.update(reference.reference_id for reference, _ in type_pairs)
    used_predictions.update(prediction.evidence_id for _, prediction in type_pairs)
    errors.extend(
        (ScientificEntityEvaluationErrorKind.TYPE_MISMATCH, reference, prediction)
        for reference, prediction in type_pairs
    )

    boundary_candidates: list[tuple[tuple[Any, ...], Any, Any]] = []
    for reference in references:
        if reference.reference_id in used_references:
            continue
        for prediction in predictions:
            if prediction.evidence_id in used_predictions:
                continue
            if not _same_text(reference, prediction):
                continue
            if reference.entity_type != prediction.entity_type:
                continue
            intersection, _, iou, distance = _span_values(reference, prediction)
            if intersection > 0:
                boundary_candidates.append(
                    (
                        (-iou, distance, reference.reference_id, prediction.evidence_id),
                        reference,
                        prediction,
                    )
                )
    boundary_pairs = _greedy_pairs(boundary_candidates)
    used_references.update(reference.reference_id for reference, _ in boundary_pairs)
    used_predictions.update(prediction.evidence_id for _, prediction in boundary_pairs)
    errors.extend(
        (ScientificEntityEvaluationErrorKind.BOUNDARY_MISMATCH, reference, prediction)
        for reference, prediction in boundary_pairs
    )
    errors.extend(
        (ScientificEntityEvaluationErrorKind.FALSE_POSITIVE, None, prediction)
        for prediction in predictions
        if prediction.evidence_id not in used_predictions
    )
    errors.extend(
        (ScientificEntityEvaluationErrorKind.FALSE_NEGATIVE, reference, None)
        for reference in references
        if reference.reference_id not in used_references
    )
    matches = [
        (ScientificEntityMatchKind.EXACT, reference, prediction)
        for reference, prediction in exact
    ] + [
        (ScientificEntityMatchKind.RELAXED, reference, prediction)
        for reference, prediction in relaxed
    ]
    return matches, errors


def _expected_match(
    *,
    evaluation_id: str,
    kind: ScientificEntityMatchKind,
    reference: ScientificEntityReferenceMention,
    prediction: ScientificEntityMentionEvidence,
) -> ScientificEntityEvaluationMatch:
    intersection, union, iou, distance = _span_values(reference, prediction)
    return ScientificEntityEvaluationMatch(
        schema_version=EVALUATION_MATCH_SCHEMA_VERSION,
        match_id=build_evaluation_match_id(
            evaluation_id=evaluation_id,
            match_kind=kind,
            reference_id=reference.reference_id,
            evidence_id=prediction.evidence_id,
        ),
        evaluation_id=evaluation_id,
        match_kind=kind,
        reference_id=reference.reference_id,
        reference_mention_id=reference.mention_id,
        prediction_evidence_id=prediction.evidence_id,
        prediction_mention_id=prediction.mention_id,
        canonical_id=reference.canonical_id,
        source_field=reference.source_field,
        source_text_sha256=reference.source_text_sha256,
        entity_type=reference.entity_type,
        reference_char_start=reference.char_start,
        reference_char_end=reference.char_end,
        prediction_char_start=prediction.char_start,
        prediction_char_end=prediction.char_end,
        intersection_length=intersection,
        union_length=union,
        char_iou=round(iou, 12),
        boundary_distance=distance,
    )


def _expected_error(
    *,
    evaluation_id: str,
    kind: ScientificEntityEvaluationErrorKind,
    reference: ScientificEntityReferenceMention | None,
    prediction: ScientificEntityMentionEvidence | None,
) -> ScientificEntityEvaluationError:
    anchor = reference or prediction
    if anchor is None:
        raise ValueError("Missing error anchor")
    iou = None
    if reference is not None and prediction is not None:
        _, _, raw_iou, _ = _span_values(reference, prediction)
        iou = round(raw_iou, 12)
    return ScientificEntityEvaluationError(
        schema_version=EVALUATION_ERROR_SCHEMA_VERSION,
        error_id=build_evaluation_error_id(
            evaluation_id=evaluation_id,
            error_kind=kind,
            reference_id=reference.reference_id if reference else None,
            evidence_id=prediction.evidence_id if prediction else None,
        ),
        evaluation_id=evaluation_id,
        error_kind=kind,
        canonical_id=anchor.canonical_id,
        source_field=anchor.source_field,
        source_text_sha256=anchor.source_text_sha256,
        reference_id=reference.reference_id if reference else None,
        prediction_evidence_id=prediction.evidence_id if prediction else None,
        reference_entity_type=reference.entity_type if reference else None,
        prediction_entity_type=prediction.entity_type if prediction else None,
        reference_char_start=reference.char_start if reference else None,
        reference_char_end=reference.char_end if reference else None,
        prediction_char_start=prediction.char_start if prediction else None,
        prediction_char_end=prediction.char_end if prediction else None,
        char_iou=iou,
        manual_label=None,
    )


def _counts(
    *,
    tp: int,
    reference_support: int,
    prediction_support: int,
    decimal_places: int,
) -> ScientificEntityMetricCounts:
    fp = prediction_support - tp
    fn = reference_support - tp
    precision = round(tp / prediction_support, decimal_places) if prediction_support else None
    recall = round(tp / reference_support, decimal_places) if reference_support else None
    if precision is None or recall is None:
        f1 = None
    elif precision + recall == 0:
        f1 = 0.0
    else:
        f1 = round(2 * precision * recall / (precision + recall), decimal_places)
    return ScientificEntityMetricCounts(
        true_positive=tp,
        false_positive=fp,
        false_negative=fn,
        reference_support=reference_support,
        prediction_support=prediction_support,
        precision_denominator=prediction_support,
        recall_denominator=reference_support,
        precision=precision,
        recall=recall,
        f1=f1,
    )


def _expected_metrics(
    *,
    evaluation_id: str,
    document_count: int,
    references: Sequence[ScientificEntityReferenceMention],
    predictions: Sequence[ScientificEntityMentionEvidence],
    pair_rows: Sequence[tuple[ScientificEntityMatchKind, Any, Any]],
    error_rows: Sequence[tuple[ScientificEntityEvaluationErrorKind, Any, Any]],
    config: ScientificEntityEvaluationConfig,
) -> tuple[ScientificEntityEvaluationMetrics, ScientificEntityPerTypeMetrics]:
    exact_ids = {
        reference.reference_id
        for kind, reference, _ in pair_rows
        if kind == ScientificEntityMatchKind.EXACT
    }
    relaxed_ids = {reference.reference_id for _, reference, _ in pair_rows}

    def selected_metrics(
        entity_type: ScientificEntityType | None = None,
        source_field: ScientificEntitySourceField | None = None,
    ) -> ScientificEntityMatchingMetrics:
        selected_references = [
            row
            for row in references
            if (entity_type is None or row.entity_type == entity_type)
            and (source_field is None or row.source_field == source_field)
        ]
        selected_predictions = [
            row
            for row in predictions
            if (entity_type is None or row.entity_type == entity_type)
            and (source_field is None or row.source_field == source_field)
        ]
        selected_ids = {row.reference_id for row in selected_references}
        return ScientificEntityMatchingMetrics(
            exact=_counts(
                tp=len(selected_ids & exact_ids),
                reference_support=len(selected_references),
                prediction_support=len(selected_predictions),
                decimal_places=config.metrics.decimal_places,
            ),
            relaxed=_counts(
                tp=len(selected_ids & relaxed_ids),
                reference_support=len(selected_references),
                prediction_support=len(selected_predictions),
                decimal_places=config.metrics.decimal_places,
            ),
        )

    rows = [
        ScientificEntityPerTypeMetricRow(
            entity_type=entity_type,
            metrics=selected_metrics(entity_type=entity_type),
            support_sufficient=(
                sum(row.entity_type == entity_type for row in references)
                >= config.metrics.minimum_reference_mentions_per_type
            ),
        )
        for entity_type in ScientificEntityType
    ]
    per_type = ScientificEntityPerTypeMetrics(
        schema_version=PER_TYPE_METRICS_SCHEMA_VERSION,
        evaluation_id=evaluation_id,
        minimum_reference_mentions_per_type=config.metrics.minimum_reference_mentions_per_type,
        rows=rows,
    )
    error_counts = Counter(kind for kind, _, _ in error_rows)
    metrics = ScientificEntityEvaluationMetrics(
        schema_version=METRICS_SCHEMA_VERSION,
        evaluation_id=evaluation_id,
        document_count=document_count,
        reference_mention_count=len(references),
        prediction_mention_count=len(predictions),
        matching_policy=config.matching.contract_policy(),
        micro=selected_metrics(),
        by_source_field={
            field: selected_metrics(source_field=field)
            for field in ScientificEntitySourceField
        },
        exact_match_count=sum(kind == ScientificEntityMatchKind.EXACT for kind, _, _ in pair_rows),
        relaxed_only_match_count=sum(
            kind == ScientificEntityMatchKind.RELAXED for kind, _, _ in pair_rows
        ),
        error_count_by_kind={
            kind: error_counts[kind] for kind in ScientificEntityEvaluationErrorKind
        },
        data_sufficiency=ScientificEntityDataSufficiency(
            minimum_document_count=config.metrics.minimum_document_count_for_promotion_evidence,
            minimum_reference_mentions_per_type=config.metrics.minimum_reference_mentions_per_type,
            document_count_sufficient=(
                document_count
                >= config.metrics.minimum_document_count_for_promotion_evidence
            ),
            per_type_support_sufficient={row.entity_type: row.support_sufficient for row in rows},
            promotion_sample_sufficient=False,
            metrics_are_descriptive_only=True,
        ),
        production_extractor_selected=False,
        full_corpus_build_authorized=False,
        canonical_truth_mutated=False,
        publication_ready=False,
    )
    return metrics, per_type


def _build_report(
    *,
    evaluation_dir: Path,
    config_path: Path,
    checks: Sequence[CheckResult],
    manifest: ScientificEntityEvaluationManifest | None,
    metrics: ScientificEntityEvaluationMetrics | None,
) -> dict[str, Any]:
    failed_required = [check for check in checks if check.required and not check.ok]
    warnings = [check for check in checks if not check.required and not check.ok]
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at_utc": _now_iso(),
        "status": "read_only_bounded_evaluation_validation",
        "evaluation_dir": _normalize_path(evaluation_dir),
        "config_path": _normalize_path(config_path),
        "summary": {
            "ok": not failed_required,
            "total_checks": len(checks),
            "passed_checks_count": sum(check.ok for check in checks),
            "required_failed_count": len(failed_required),
            "warning_count": len(warnings),
            "evaluation_id": manifest.evaluation_id if manifest else None,
            "evaluation_status": manifest.status.value if manifest else None,
            "document_count": metrics.document_count if metrics else None,
            "reference_mention_count": metrics.reference_mention_count if metrics else None,
            "prediction_mention_count": metrics.prediction_mention_count if metrics else None,
            "exact_match_count": metrics.exact_match_count if metrics else None,
            "relaxed_only_match_count": (
                metrics.relaxed_only_match_count if metrics else None
            ),
        },
        "checks": [asdict(check) for check in checks],
        "verdict": {
            "evaluation_valid": not failed_required,
            "metrics_descriptive_only": True,
            "production_extractor_selected": False,
            "full_corpus_build_authorized": False,
            "canonical_mutation_allowed": False,
            "reconcile_input_allowed": False,
            "publication_allowed": False,
            "required_failed_checks": [check.name for check in failed_required],
            "next_slice": (
                "bounded_scientific_entity_manual_review_evidence_v0.1"
                if not failed_required
                else None
            ),
        },
    }
    report["ok"] = report["summary"]["ok"]
    report["required_failed_count"] = report["summary"]["required_failed_count"]
    return report


def _markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Scientific Entity Evaluation validation",
        "",
        f"- Generated: `{report['generated_at_utc']}`",
        f"- Status: `{'OK' if report['summary']['ok'] else 'FAILED'}`",
        "- Scope: read-only bounded evaluation-directory validation.",
        "",
        "## Summary",
        "",
    ]
    lines.extend(f"- {key}: `{value}`" for key, value in report["summary"].items())
    lines.extend(["", "## Failed required checks", ""])
    failed = report["verdict"]["required_failed_checks"]
    lines.extend((f"- `{name}`" for name in failed) if failed else ["- none"])
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- metrics are descriptive only",
            "- no production extractor selection",
            "- no full-corpus authorization",
            "- no canonical or reconciliation mutation",
            "- no model/provider access",
            "- no publication",
            "",
        ]
    )
    return "\n".join(lines)


def _write_reports(
    report: dict[str, Any],
    report_dir: Path,
) -> tuple[Path, Path, Path, Path]:
    history_dir = report_dir / "history"
    report_dir.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    slug = _now_slug()
    latest_json = report_dir / f"{REPORT_BASENAME}_latest.json"
    latest_md = report_dir / f"{REPORT_BASENAME}_latest.md"
    history_json = history_dir / f"{REPORT_BASENAME}_{slug}.json"
    history_md = history_dir / f"{REPORT_BASENAME}_{slug}.md"
    report["report_paths"] = {
        "latest_json": _normalize_path(latest_json),
        "latest_markdown": _normalize_path(latest_md),
        "history_json": _normalize_path(history_json),
        "history_markdown": _normalize_path(history_md),
    }
    json_text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    markdown_text = _markdown(report)
    for path, text in (
        (latest_json, json_text),
        (latest_md, markdown_text),
        (history_json, json_text),
        (history_md, markdown_text),
    ):
        path.write_text(text, encoding="utf-8", newline="\n")
    return latest_json, latest_md, history_json, history_md


def validate_evaluation(
    *,
    evaluation_dir: Path,
    config_path: Path = DEFAULT_CONFIG_PATH,
    write_reports: bool = True,
    report_dir: Path | None = None,
) -> dict[str, Any]:
    evaluation_dir = evaluation_dir.resolve()
    config_path = config_path.resolve()
    checks: list[CheckResult] = []
    manifest: ScientificEntityEvaluationManifest | None = None
    metrics: ScientificEntityEvaluationMetrics | None = None
    per_type: ScientificEntityPerTypeMetrics | None = None
    matches: list[ScientificEntityEvaluationMatch] = []
    errors: list[ScientificEntityEvaluationError] = []
    config: ScientificEntityEvaluationConfig | None = None

    try:
        config = load_evaluation_config(config_path)
        _add(checks, "config_valid", True)
    except Exception as exc:
        _add(checks, "config_valid", False, str(exc))

    _add(checks, "evaluation_directory_exists", evaluation_dir.is_dir())
    actual_files = (
        {path.name for path in evaluation_dir.iterdir()}
        if evaluation_dir.is_dir()
        else set()
    )
    _add(checks, "required_file_layout_exact", actual_files == set(REQUIRED_FILES))
    for filename in REQUIRED_FILES:
        path = evaluation_dir / filename
        ok = path.is_file()
        _add(checks, f"required_file_present:{filename}", ok)
        if ok:
            lf_ok, details = _text_is_utf8_lf(path)
            _add(checks, f"output_utf8_lf:{filename}", lf_ok, details)

    checksums: dict[str, str] = {}
    checksum_path = evaluation_dir / "checksums.txt"
    if checksum_path.is_file():
        try:
            checksums = _parse_checksums(checksum_path)
            _add(checks, "checksums_parse", True)
        except Exception as exc:
            _add(checks, "checksums_parse", False, str(exc))
    _add(checks, "checksums_cover_expected_files", set(checksums) == set(CHECKSUM_FILES))
    for filename in CHECKSUM_FILES:
        path = evaluation_dir / filename
        _add(
            checks,
            f"checksum_matches:{filename}",
            path.is_file() and checksums.get(filename) == _sha256_file(path),
        )

    readme_path = evaluation_dir / "README.md"
    readme = ""
    if readme_path.is_file():
        try:
            readme = readme_path.read_text(encoding="utf-8")
            _add(checks, "readme_parse", True)
        except (OSError, UnicodeError) as exc:
            _add(checks, "readme_parse", False, str(exc))
    else:
        _add(checks, "readme_parse", False, "README.md is missing")
    _add(checks, "readme_marks_derived", "derived and rebuildable" in readme)
    _add(
        checks,
        "readme_rejects_canonical_truth",
        "not canonical paper truth" in readme,
    )
    _add(
        checks,
        "readme_rejects_full_corpus_authorization",
        "not a full-corpus authorization" in readme,
    )
    _add(
        checks,
        "readme_rejects_publication",
        "not publication ready" in readme,
    )

    try:
        manifest = ScientificEntityEvaluationManifest.model_validate(
            _read_json(evaluation_dir / "manifest.json")
        )
        _add(checks, "manifest_schema_valid", True)
    except Exception as exc:
        _add(checks, "manifest_schema_valid", False, str(exc))
    try:
        metrics = ScientificEntityEvaluationMetrics.model_validate(
            _read_json(evaluation_dir / "metrics.json")
        )
        _add(checks, "metrics_schema_valid", True)
    except Exception as exc:
        _add(checks, "metrics_schema_valid", False, str(exc))
    try:
        per_type = ScientificEntityPerTypeMetrics.model_validate(
            _read_json(evaluation_dir / "per_type_metrics.json")
        )
        _add(checks, "per_type_metrics_schema_valid", True)
    except Exception as exc:
        _add(checks, "per_type_metrics_schema_valid", False, str(exc))
    try:
        match_rows = _read_jsonl(
            evaluation_dir / "matches.jsonl",
            hard_limit=5000,
        )
        matches = [ScientificEntityEvaluationMatch.model_validate(row) for row in match_rows]
        _add(checks, "matches_schema_valid", True)
    except Exception as exc:
        _add(checks, "matches_schema_valid", False, str(exc))
    try:
        error_rows = _read_jsonl(
            evaluation_dir / "errors.jsonl",
            hard_limit=10000,
        )
        errors = [ScientificEntityEvaluationError.model_validate(row) for row in error_rows]
        _add(checks, "errors_schema_valid", True)
    except Exception as exc:
        _add(checks, "errors_schema_valid", False, str(exc))

    if manifest is not None:
        _add(
            checks,
            "directory_matches_evaluation_id",
            evaluation_dir.name == manifest.evaluation_id,
        )
        _add(
            checks,
            "readme_evaluation_id_matches",
            manifest.evaluation_id in readme,
        )
        _add(
            checks,
            "manifest_config_path_matches",
            _resolve_project_path(manifest.config_path) == config_path,
        )
        _add(
            checks,
            "manifest_config_sha_matches",
            config is not None
            and manifest.config_sha256 == evaluation_config_sha256(config),
        )
        _add(
            checks,
            "manifest_matching_policy_matches_config",
            config is not None
            and manifest.matching_policy == config.matching.contract_policy(),
        )
        metrics_path = evaluation_dir / "metrics.json"
        per_type_path = evaluation_dir / "per_type_metrics.json"
        matches_path = evaluation_dir / "matches.jsonl"
        errors_path = evaluation_dir / "errors.jsonl"
        _add(
            checks,
            "manifest_metrics_sha_matches",
            metrics_path.is_file()
            and manifest.metrics_sha256 == _sha256_file(metrics_path),
        )
        _add(
            checks,
            "manifest_per_type_sha_matches",
            per_type_path.is_file()
            and manifest.per_type_metrics_sha256 == _sha256_file(per_type_path),
        )
        _add(
            checks,
            "manifest_matches_sha_matches",
            matches_path.is_file()
            and manifest.matches_sha256 == _sha256_file(matches_path),
        )
        _add(
            checks,
            "manifest_errors_sha_matches",
            errors_path.is_file()
            and manifest.errors_sha256 == _sha256_file(errors_path),
        )
        _add(checks, "manifest_match_count_matches", manifest.match_count == len(matches))
        _add(checks, "manifest_error_count_matches", manifest.error_count == len(errors))
        _add(checks, "manifest_fail_closed_safety", all((
            manifest.canonical_truth_mutated is False,
            manifest.may_be_used_as_reconcile_input is False,
            manifest.production_extractor_selected is False,
            manifest.full_corpus_build_authorized is False,
            manifest.model_downloaded is False,
            manifest.provider_api_called is False,
            manifest.redistribution_allowed is False,
            manifest.publication_ready is False,
        )))

    if manifest is not None and metrics is not None and per_type is not None and config is not None:
        documents_path = _resolve_project_path(manifest.canonical_input.path)
        review_manifest_path = _resolve_project_path(manifest.review.manifest_path)
        references_path = _resolve_project_path(manifest.review.reference_mentions_path)
        prediction_manifest_path = _resolve_project_path(manifest.prediction.manifest_path)
        predictions_path = _resolve_project_path(manifest.prediction.mentions_path)
        inputs = (
            documents_path,
            review_manifest_path,
            references_path,
            prediction_manifest_path,
            predictions_path,
        )
        _add(checks, "all_input_paths_exist", all(path.is_file() for path in inputs))
        if all(path.is_file() for path in inputs):
            try:
                documents, documents_by_id = _load_documents(
                    documents_path,
                    hard_limit=config.safety.hard_max_documents,
                )
                review_manifest = ScientificEntityReviewManifest.model_validate(
                    _read_json(review_manifest_path)
                )
                prediction_manifest = ScientificEntityEvidenceManifest.model_validate(
                    _read_json(prediction_manifest_path)
                )
                reference_rows = _read_jsonl(
                    references_path,
                    hard_limit=config.safety.hard_max_reference_mentions,
                )
                prediction_rows = _read_jsonl(
                    predictions_path,
                    hard_limit=config.safety.hard_max_prediction_mentions,
                )
                references = [
                    ScientificEntityReferenceMention.model_validate(row)
                    for row in reference_rows
                ]
                predictions = [
                    ScientificEntityMentionEvidence.model_validate(row)
                    for row in prediction_rows
                ]
                for reference in references:
                    validate_reference_mention(
                        reference,
                        source_text=_source_text(documents_by_id, reference),
                        review_id=review_manifest.review_id,
                    )
                    if reference.annotation_method != review_manifest.annotation_method:
                        raise ValueError(
                            "Reference annotation_method does not match review manifest"
                        )
                    if reference.annotation_pass > review_manifest.annotation_passes:
                        raise ValueError(
                            "Reference annotation_pass exceeds review manifest passes"
                        )
                    if reference.source_field not in review_manifest.source_fields:
                        raise ValueError(
                            "Reference source_field is not declared by review manifest"
                        )
                    if reference.entity_type not in review_manifest.entity_types:
                        raise ValueError(
                            "Reference entity_type is not declared by review manifest"
                        )
                for prediction in predictions:
                    validate_mention_evidence(
                        prediction,
                        source_text=_source_text(documents_by_id, prediction),
                        extractor=prediction_manifest.extractor,
                        manifest=prediction_manifest,
                    )
                _add(checks, "input_contracts_and_spans_valid", True)
                _add(
                    checks,
                    "reference_ids_unique",
                    len({row.reference_id for row in references}) == len(references),
                )
                _add(
                    checks,
                    "reference_mention_ids_unique",
                    len({row.mention_id for row in references}) == len(references),
                )
                _add(
                    checks,
                    "prediction_evidence_ids_unique",
                    len({row.evidence_id for row in predictions}) == len(predictions),
                )
                _add(
                    checks,
                    "prediction_mention_ids_unique",
                    len({row.mention_id for row in predictions}) == len(predictions),
                )
                _add(
                    checks,
                    "canonical_input_sha_matches",
                    manifest.canonical_input.sha256 == _sha256_file(documents_path),
                )
                _add(
                    checks,
                    "canonical_input_count_matches",
                    manifest.canonical_input.document_count == len(documents),
                )
                _add(
                    checks,
                    "input_manifests_canonical_identity_matches",
                    all(
                        (
                            review_manifest.canonical_input.sha256
                            == manifest.canonical_input.sha256,
                            review_manifest.canonical_input.document_count
                            == manifest.canonical_input.document_count,
                            review_manifest.canonical_input.canonical_contract
                            == manifest.canonical_input.canonical_contract,
                            prediction_manifest.canonical_input.sha256
                            == manifest.canonical_input.sha256,
                            prediction_manifest.canonical_input.document_count
                            == manifest.canonical_input.document_count,
                            prediction_manifest.canonical_input.canonical_contract
                            == manifest.canonical_input.canonical_contract,
                        )
                    ),
                )
                _add(
                    checks,
                    "review_descriptor_matches_manifest",
                    all(
                        (
                            manifest.review.review_id == review_manifest.review_id,
                            manifest.review.status == review_manifest.status,
                            manifest.review.reference_mention_count
                            == review_manifest.reference_mention_count,
                            manifest.review.review_complete
                            == review_manifest.review_complete,
                            manifest.review.prediction_blind
                            == review_manifest.prediction_blind,
                        )
                    ),
                )
                _add(
                    checks,
                    "review_manifest_sha_matches",
                    manifest.review.manifest_sha256
                    == _sha256_file(review_manifest_path),
                )
                _add(
                    checks,
                    "reference_mentions_sha_matches",
                    manifest.review.reference_mentions_sha256
                    == _sha256_file(references_path),
                )
                _add(
                    checks,
                    "review_manifest_reference_evidence_matches",
                    review_manifest.reference_mention_count == len(references)
                    and review_manifest.reference_mentions_sha256
                    == _sha256_file(references_path),
                )
                _add(
                    checks,
                    "prediction_descriptor_matches_manifest",
                    all(
                        (
                            manifest.prediction.build_id
                            == prediction_manifest.build_id,
                            manifest.prediction.status
                            == prediction_manifest.status.value,
                            manifest.prediction.mention_count
                            == prediction_manifest.mention_count,
                            manifest.prediction.extractor_fingerprint
                            == prediction_manifest.extractor_fingerprint,
                        )
                    ),
                )
                _add(
                    checks,
                    "prediction_manifest_sha_matches",
                    manifest.prediction.manifest_sha256
                    == _sha256_file(prediction_manifest_path),
                )
                _add(
                    checks,
                    "prediction_mentions_sha_matches",
                    manifest.prediction.mentions_sha256
                    == _sha256_file(predictions_path),
                )
                _add(
                    checks,
                    "prediction_manifest_evidence_matches",
                    prediction_manifest.mention_count == len(predictions)
                    and prediction_manifest.mentions_sha256
                    == _sha256_file(predictions_path),
                )

                pair_rows, diagnostic_rows = _independent_pairs(
                    references=references,
                    predictions=predictions,
                    min_iou=config.matching.relaxed_min_char_iou,
                )
                expected_matches = [
                    _expected_match(
                        evaluation_id=manifest.evaluation_id,
                        kind=kind,
                        reference=reference,
                        prediction=prediction,
                    )
                    for kind, reference, prediction in pair_rows
                ]
                expected_matches.sort(key=lambda row: (row.match_kind.value, row.match_id))
                expected_errors = [
                    _expected_error(
                        evaluation_id=manifest.evaluation_id,
                        kind=kind,
                        reference=reference,
                        prediction=prediction,
                    )
                    for kind, reference, prediction in diagnostic_rows
                ]
                expected_errors.sort(key=lambda row: (row.error_kind.value, row.error_id))
                expected_metrics, expected_per_type = _expected_metrics(
                    evaluation_id=manifest.evaluation_id,
                    document_count=len(documents),
                    references=references,
                    predictions=predictions,
                    pair_rows=pair_rows,
                    error_rows=diagnostic_rows,
                    config=config,
                )
                _add(
                    checks,
                    "matches_independently_recomputed",
                    [row.model_dump(mode="json") for row in matches]
                    == [row.model_dump(mode="json") for row in expected_matches],
                )
                _add(
                    checks,
                    "errors_independently_recomputed",
                    [row.model_dump(mode="json") for row in errors]
                    == [row.model_dump(mode="json") for row in expected_errors],
                )
                _add(
                    checks,
                    "metrics_independently_recomputed",
                    metrics.model_dump(mode="json")
                    == expected_metrics.model_dump(mode="json"),
                )
                _add(
                    checks,
                    "per_type_metrics_independently_recomputed",
                    per_type.model_dump(mode="json")
                    == expected_per_type.model_dump(mode="json"),
                )
                _add(
                    checks,
                    "matches_are_one_to_one",
                    len({row.reference_id for row in matches}) == len(matches)
                    and len({row.prediction_evidence_id for row in matches}) == len(matches),
                )
            except Exception as exc:
                _add(checks, "input_contracts_and_spans_valid", False, str(exc))
                _add(checks, "independent_recomputation_completed", False, str(exc))

    report = _build_report(
        evaluation_dir=evaluation_dir,
        config_path=config_path,
        checks=checks,
        manifest=manifest,
        metrics=metrics,
    )
    if write_reports:
        selected_report_dir = (
            report_dir.resolve()
            if report_dir is not None
            else _resolve_project_path(
                config.validation.report_dir
                if config is not None
                else "artifacts/reports/validation"
            )
        )
        _write_reports(report, selected_report_dir)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate one immutable Scientific Entity Evaluation v0.1 directory."
    )
    parser.add_argument("--evaluation-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--no-write-reports", action="store_true")
    parser.add_argument("--report-dir", type=Path, default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = validate_evaluation(
            evaluation_dir=args.evaluation_dir,
            config_path=args.config,
            write_reports=not args.no_write_reports,
            report_dir=args.report_dir,
        )
    except (OSError, ValueError, ValidationError) as exc:
        print(f"[FAILED] report={REPORT_BASENAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 1
    status = "OK" if report["summary"]["ok"] else "FAILED"
    print(f"[{status}] report={REPORT_BASENAME}")
    print(f"[{status}] total_checks={report['summary']['total_checks']}")
    print(f"[{status}] required_failed_count={report['summary']['required_failed_count']}")
    print(f"[{status}] evaluation_id={report['summary']['evaluation_id']}")
    print(f"[{status}] document_count={report['summary']['document_count']}")
    print(f"[{status}] reference_mention_count={report['summary']['reference_mention_count']}")
    print(f"[{status}] prediction_mention_count={report['summary']['prediction_mention_count']}")
    print(f"[{status}] next_slice={report['verdict']['next_slice']}")
    if report["verdict"]["required_failed_checks"]:
        print("[FAILED] required_failed_checks:")
        for name in report["verdict"]["required_failed_checks"]:
            print(f"- {name}")
    if args.strict and not report["summary"]["ok"]:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
