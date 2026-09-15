from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from radar_core.contracts.canonical_document import CanonicalDocument
from radar_core.contracts.scientific_entity_evaluation import (
    ScientificEntityEvaluationError,
    ScientificEntityEvaluationErrorKind,
    ScientificEntityEvaluationManifest,
    ScientificEntityEvaluationMatch,
    ScientificEntityMatchKind,
    ScientificEntityReferenceMention,
)
from radar_core.contracts.scientific_entity_evidence import (
    ScientificEntityMentionEvidence,
    ScientificEntitySourceField,
)
from radar_core.contracts.scientific_entity_semantic_typer_candidate import (
    SemanticTyperDevelopmentCase,
    load_semantic_typer_config,
    semantic_typer_config_sha256,
)
from radar_core.contracts.scientific_entity_typing_root_cause_review import WorkingReviewRow
from radar_core.entities.scientific_entity_semantic_typer import semantic_typer_fingerprint
from radar_core.entities.scientific_entity_typing_root_cause_review import validate_final_review


REPORT_NAME = "scientific_entity_semantic_typer_development_v03"
PACKAGE_SCHEMA_VERSION = "scientific_entity_semantic_typer_development_package_v0.3"
SUMMARY_SCHEMA_VERSION = "scientific_entity_semantic_typer_development_summary_v0.3"
REQUIRED_FILES = (
    "manifest.json",
    "development_cases.jsonl",
    "summary.json",
    "README.md",
    "checksums.txt",
)


class ScientificEntitySemanticTyperDevelopmentError(ValueError):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_id(prefix: str, values: Sequence[object]) -> str:
    payload = json.dumps(list(values), ensure_ascii=False, separators=(",", ":"))
    return f"{prefix}:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ScientificEntitySemanticTyperDevelopmentError(
            f"Invalid JSON: {path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ScientificEntitySemanticTyperDevelopmentError(
            f"Expected JSON object: {path}"
        )
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            if not raw_line.strip():
                raise ScientificEntitySemanticTyperDevelopmentError(
                    f"Blank JSONL line is forbidden: {path}:{line_number}"
                )
            try:
                payload = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise ScientificEntitySemanticTyperDevelopmentError(
                    f"Invalid JSONL: {path}:{line_number}: {exc}"
                ) from exc
            if not isinstance(payload, dict):
                raise ScientificEntitySemanticTyperDevelopmentError(
                    f"Expected JSON object: {path}:{line_number}"
                )
            rows.append(payload)
    return rows


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(rows: Sequence[SemanticTyperDevelopmentCase]) -> bytes:
    return "".join(
        json.dumps(row.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
        + "\n"
        for row in rows
    ).encode("utf-8")


def _resolve(project_root: Path, value: str | Path) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    return candidate.resolve()


def _project_path(project_root: Path, path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(project_root.resolve())).replace("\\", "/")
    except ValueError:
        return str(resolved).replace("\\", "/")


def _source_text(document: CanonicalDocument, field: ScientificEntitySourceField) -> str:
    value = document.title if field == ScientificEntitySourceField.TITLE else document.abstract
    if value is None or value == "":
        raise ScientificEntitySemanticTyperDevelopmentError(
            f"Blank source text for {document.canonical_id}:{field.value}"
        )
    return value


def _load_documents(path: Path) -> dict[str, CanonicalDocument]:
    documents: dict[str, CanonicalDocument] = {}
    for row in _read_jsonl(path):
        document = CanonicalDocument.model_validate(row)
        if document.canonical_id in documents:
            raise ScientificEntitySemanticTyperDevelopmentError(
                f"Duplicate canonical_id: {document.canonical_id}"
            )
        documents[document.canonical_id] = document
    return documents


def _verify_sha(path: Path, expected: str, label: str) -> None:
    actual = _sha256_file(path)
    if actual != expected:
        raise ScientificEntitySemanticTyperDevelopmentError(
            f"{label} SHA-256 mismatch: expected={expected} actual={actual}"
        )


def _load_parent_evaluation(
    *,
    project_root: Path,
    evaluation_dir: Path,
    expected_evaluation_id: str,
) -> tuple[
    ScientificEntityEvaluationManifest,
    dict[str, CanonicalDocument],
    dict[str, ScientificEntityReferenceMention],
    dict[str, ScientificEntityMentionEvidence],
    tuple[ScientificEntityEvaluationMatch, ...],
    tuple[ScientificEntityEvaluationError, ...],
]:
    manifest = ScientificEntityEvaluationManifest.model_validate(
        _read_json(evaluation_dir / "manifest.json")
    )
    if manifest.evaluation_id != expected_evaluation_id:
        raise ScientificEntitySemanticTyperDevelopmentError(
            "Parent evaluation_id does not match frozen semantic typer config"
        )

    canonical_path = _resolve(project_root, manifest.canonical_input.path)
    _verify_sha(canonical_path, manifest.canonical_input.sha256, "canonical input")
    documents = _load_documents(canonical_path)
    if len(documents) != manifest.canonical_input.document_count:
        raise ScientificEntitySemanticTyperDevelopmentError(
            "Parent canonical document count drifted"
        )

    reference_path = _resolve(project_root, manifest.review.reference_mentions_path)
    prediction_path = _resolve(project_root, manifest.prediction.mentions_path)
    matches_path = evaluation_dir / manifest.matches_file
    errors_path = evaluation_dir / manifest.errors_file
    _verify_sha(reference_path, manifest.review.reference_mentions_sha256, "reference mentions")
    _verify_sha(prediction_path, manifest.prediction.mentions_sha256, "prediction mentions")
    _verify_sha(matches_path, manifest.matches_sha256, "evaluation matches")
    _verify_sha(errors_path, manifest.errors_sha256, "evaluation errors")

    references = {
        row.reference_id: row
        for row in (
            ScientificEntityReferenceMention.model_validate(payload)
            for payload in _read_jsonl(reference_path)
        )
    }
    predictions = {
        row.evidence_id: row
        for row in (
            ScientificEntityMentionEvidence.model_validate(payload)
            for payload in _read_jsonl(prediction_path)
        )
    }
    matches = tuple(
        ScientificEntityEvaluationMatch.model_validate(payload)
        for payload in _read_jsonl(matches_path)
    )
    errors = tuple(
        ScientificEntityEvaluationError.model_validate(payload)
        for payload in _read_jsonl(errors_path)
    )
    if len(references) != manifest.review.reference_mention_count:
        raise ScientificEntitySemanticTyperDevelopmentError("Parent reference count drifted")
    if len(predictions) != manifest.prediction.mention_count:
        raise ScientificEntitySemanticTyperDevelopmentError("Parent prediction count drifted")
    if len(matches) != manifest.match_count or len(errors) != manifest.error_count:
        raise ScientificEntitySemanticTyperDevelopmentError(
            "Parent evaluation match/error count drifted"
        )
    return manifest, documents, references, predictions, matches, errors


def _load_review_rows(review_dir: Path) -> dict[tuple[str, str], WorkingReviewRow]:
    rows: dict[tuple[str, str], WorkingReviewRow] = {}
    for payload in _read_jsonl(review_dir / "reviewed_cases.jsonl"):
        row = WorkingReviewRow.model_validate(payload)
        if row.review_status != "complete":
            raise ScientificEntitySemanticTyperDevelopmentError(
                "Final root-cause review contains a non-complete row"
            )
        key = (row.reference_id, row.prediction_evidence_id)
        if key in rows:
            raise ScientificEntitySemanticTyperDevelopmentError(
                f"Duplicate reviewed reference/prediction pair: {key}"
            )
        rows[key] = row
    return rows


def _context_parts(
    *,
    source_text: str,
    start: int,
    end: int,
    left_chars: int,
    right_chars: int,
) -> tuple[str, str]:
    return (
        source_text[max(0, start - left_chars) : start],
        source_text[end : min(len(source_text), end + right_chars)],
    )


def _make_case(
    *,
    config,
    evaluation_id: str,
    reference: ScientificEntityReferenceMention,
    prediction: ScientificEntityMentionEvidence,
    source_text: str,
    review: WorkingReviewRow | None,
) -> SemanticTyperDevelopmentCase:
    if reference.char_start != prediction.char_start or reference.char_end != prediction.char_end:
        raise ScientificEntitySemanticTyperDevelopmentError(
            "Semantic typer development case requires an identical frozen span"
        )
    if reference.source_text_sha256 != prediction.source_text_sha256:
        raise ScientificEntitySemanticTyperDevelopmentError(
            "Reference/prediction source text identity mismatch"
        )
    surface = source_text[reference.char_start : reference.char_end]
    if surface != reference.surface_text or surface != prediction.surface_text:
        raise ScientificEntitySemanticTyperDevelopmentError(
            "Reference/prediction surface does not match exact source slice"
        )
    left, right = _context_parts(
        source_text=source_text,
        start=reference.char_start,
        end=reference.char_end,
        left_chars=config.semantic_typing.context_left_chars,
        right_chars=config.semantic_typing.context_right_chars,
    )
    root_cause = review.root_cause if review is not None else None
    primary_eligible = root_cause != "annotation_reference_issue"
    case_id = _stable_id(
        "semantic-typer-dev-case",
        [evaluation_id, reference.reference_id, prediction.evidence_id],
    )
    return SemanticTyperDevelopmentCase(
        case_id=case_id,
        evaluation_id=evaluation_id,
        canonical_id=reference.canonical_id,
        source_field=reference.source_field.value,
        source_text_sha256=reference.source_text_sha256,
        reference_id=reference.reference_id,
        baseline_prediction_evidence_id=prediction.evidence_id,
        char_start=reference.char_start,
        char_end=reference.char_end,
        surface_text=surface,
        reference_entity_type=reference.entity_type,
        baseline_entity_type=prediction.entity_type,
        baseline_correct=reference.entity_type == prediction.entity_type,
        baseline_confidence_score=prediction.confidence_score,
        left_context=left,
        right_context=right,
        root_cause=root_cause,
        ambiguity_level=(review.ambiguity_level if review is not None else None),
        reference_type_confirmed=(
            review.reference_type_confirmed if review is not None else None
        ),
        primary_metric_eligible=primary_eligible,
    )


def materialize_development_cases(
    *,
    config,
    evaluation_id: str,
    documents: Mapping[str, CanonicalDocument],
    references: Mapping[str, ScientificEntityReferenceMention],
    predictions: Mapping[str, ScientificEntityMentionEvidence],
    matches: Sequence[ScientificEntityEvaluationMatch],
    errors: Sequence[ScientificEntityEvaluationError],
    review_rows: Mapping[tuple[str, str], WorkingReviewRow],
) -> tuple[SemanticTyperDevelopmentCase, ...]:
    cases: list[SemanticTyperDevelopmentCase] = []

    for match in matches:
        if match.match_kind != ScientificEntityMatchKind.EXACT:
            continue
        reference = references[match.reference_id]
        prediction = predictions[match.prediction_evidence_id]
        document = documents[reference.canonical_id]
        cases.append(
            _make_case(
                config=config,
                evaluation_id=evaluation_id,
                reference=reference,
                prediction=prediction,
                source_text=_source_text(document, reference.source_field),
                review=None,
            )
        )

    for error in errors:
        if error.error_kind != ScientificEntityEvaluationErrorKind.TYPE_MISMATCH:
            continue
        if (
            error.reference_char_start != error.prediction_char_start
            or error.reference_char_end != error.prediction_char_end
        ):
            continue
        if error.reference_id is None or error.prediction_evidence_id is None:
            raise ScientificEntitySemanticTyperDevelopmentError(
                "Same-span type mismatch is missing paired identities"
            )
        reference = references[error.reference_id]
        prediction = predictions[error.prediction_evidence_id]
        review = review_rows.get((reference.reference_id, prediction.evidence_id))
        if review is None:
            raise ScientificEntitySemanticTyperDevelopmentError(
                "Same-span type mismatch is missing from completed root-cause review"
            )
        document = documents[reference.canonical_id]
        cases.append(
            _make_case(
                config=config,
                evaluation_id=evaluation_id,
                reference=reference,
                prediction=prediction,
                source_text=_source_text(document, reference.source_field),
                review=review,
            )
        )

    field_order = {ScientificEntitySourceField.TITLE.value: 0, ScientificEntitySourceField.ABSTRACT.value: 1}
    cases.sort(
        key=lambda row: (
            row.canonical_id,
            field_order[row.source_field],
            row.char_start,
            row.char_end,
            row.reference_id,
            row.baseline_prediction_evidence_id,
        )
    )
    case_ids = [row.case_id for row in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ScientificEntitySemanticTyperDevelopmentError("Duplicate development case_id")
    return tuple(cases)


def _summary(cases: Sequence[SemanticTyperDevelopmentCase]) -> dict[str, Any]:
    root_causes = Counter(row.root_cause for row in cases if row.root_cause is not None)
    baseline_correct = sum(row.baseline_correct for row in cases)
    baseline_wrong = len(cases) - baseline_correct
    eligible = sum(row.primary_metric_eligible for row in cases)
    type_pairs = Counter(
        (row.reference_entity_type.value, row.baseline_entity_type.value)
        for row in cases
        if not row.baseline_correct
    )
    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "case_count": len(cases),
        "baseline_correct_same_span_count": baseline_correct,
        "baseline_wrong_same_span_count": baseline_wrong,
        "primary_metric_eligible_count": eligible,
        "primary_metric_excluded_count": len(cases) - eligible,
        "root_cause_counts_on_baseline_wrong": dict(sorted(root_causes.items())),
        "model_to_method_count": type_pairs.get(("model", "method"), 0),
        "method_to_task_count": type_pairs.get(("method", "task"), 0),
        "source_field_counts": dict(sorted(Counter(row.source_field for row in cases).items())),
        "reference_type_counts": dict(
            sorted(Counter(row.reference_entity_type.value for row in cases).items())
        ),
    }


def _readme(package_id: str, summary: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "# Scientific Entity Semantic Typer Development v0.3",
            "",
            f"package_id = `{package_id}`",
            "",
            "This immutable package materializes only same-span development cases from",
            "the already-consumed fresh v0.2c evaluation. Exact baseline matches provide",
            "the regression guardrail; same-span type mismatches provide correction targets.",
            "",
            "It reuses the frozen evaluation matching semantics. It does not rematch spans,",
            "run model inference, tune thresholds, mutate canonical truth, or authorize",
            "production/full-corpus extraction.",
            "",
            f"case_count = `{summary['case_count']}`",
            f"baseline_correct_same_span_count = `{summary['baseline_correct_same_span_count']}`",
            f"baseline_wrong_same_span_count = `{summary['baseline_wrong_same_span_count']}`",
            f"primary_metric_excluded_count = `{summary['primary_metric_excluded_count']}`",
            "",
            "The fresh 48-paper package is consumed development evidence. Any candidate",
            "influenced by this package requires a new disjoint prediction-blind held-out",
            "for independent acceptance.",
            "",
        ]
    )


def prepare_semantic_typer_development(
    *,
    project_root: Path,
    config_path: Path,
    evaluation_dir: Path,
    review_dir: Path,
    diagnostics_dir: Path,
    package_id: str | None = None,
    output_root: Path | None = None,
    execute: bool = False,
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    root = project_root.resolve()
    config = load_semantic_typer_config(config_path.resolve())
    evaluation_dir = evaluation_dir.resolve()
    review_dir = review_dir.resolve()
    diagnostics_dir = diagnostics_dir.resolve()

    checks, review_summary = validate_final_review(
        review_dir=review_dir,
        config_path=root / "configs" / "scientific_entity_typing_root_cause_review_v0.3.yaml",
        diagnostics_dir=diagnostics_dir,
    )
    if review_summary.get("required_failed_count") != 0:
        failed = [name for name, ok, _ in checks if not ok]
        raise ScientificEntitySemanticTyperDevelopmentError(
            f"Root-cause review validation failed: {failed}"
        )
    if review_summary.get("review_id") != config.parent_evidence.root_cause_review_id:
        raise ScientificEntitySemanticTyperDevelopmentError("Root-cause review id drifted")

    manifest, documents, references, predictions, matches, errors = _load_parent_evaluation(
        project_root=root,
        evaluation_dir=evaluation_dir,
        expected_evaluation_id=config.parent_evidence.evaluation_id,
    )
    if len(documents) != config.parent_evidence.expected_document_count:
        raise ScientificEntitySemanticTyperDevelopmentError("Parent document count drifted")
    if len(references) != config.parent_evidence.expected_reference_mention_count:
        raise ScientificEntitySemanticTyperDevelopmentError("Parent reference count drifted")
    if len(predictions) != config.parent_evidence.expected_prediction_mention_count:
        raise ScientificEntitySemanticTyperDevelopmentError("Parent prediction count drifted")

    type_mismatches = [
        row for row in errors if row.error_kind == ScientificEntityEvaluationErrorKind.TYPE_MISMATCH
    ]
    same_span_type_mismatches = [
        row
        for row in type_mismatches
        if row.reference_char_start == row.prediction_char_start
        and row.reference_char_end == row.prediction_char_end
    ]
    if len(type_mismatches) != config.parent_evidence.expected_type_mismatch_count:
        raise ScientificEntitySemanticTyperDevelopmentError("Parent type mismatch count drifted")
    if len(same_span_type_mismatches) != config.parent_evidence.expected_same_span_type_mismatch_count:
        raise ScientificEntitySemanticTyperDevelopmentError(
            "Parent same-span type mismatch count drifted"
        )

    review_rows = _load_review_rows(review_dir)
    cases = materialize_development_cases(
        config=config,
        evaluation_id=manifest.evaluation_id,
        documents=documents,
        references=references,
        predictions=predictions,
        matches=matches,
        errors=errors,
        review_rows=review_rows,
    )
    summary = _summary(cases)
    if summary["baseline_wrong_same_span_count"] != config.parent_evidence.expected_same_span_type_mismatch_count:
        raise ScientificEntitySemanticTyperDevelopmentError(
            "Materialized wrong same-span count does not match frozen parent evidence"
        )
    if summary["primary_metric_excluded_count"] != config.parent_evidence.expected_same_span_reference_issue_count:
        raise ScientificEntitySemanticTyperDevelopmentError(
            "Primary metric exclusion count does not match reviewed reference issues"
        )

    generated_at = generated_at_utc or datetime.now(timezone.utc)
    if generated_at.tzinfo is None or generated_at.utcoffset() != timezone.utc.utcoffset(generated_at):
        raise ScientificEntitySemanticTyperDevelopmentError(
            "generated_at_utc must be timezone-aware UTC"
        )
    if package_id is None:
        package_id = (
            "scientific-entity-semantic-typer-development-v0.3-"
            + generated_at.strftime("%Y%m%dT%H%M%S%fZ")
        )
    selected_root = (
        output_root.resolve()
        if output_root is not None
        else (root / config.development.development_root).resolve()
    )
    output_dir = selected_root / package_id
    if output_dir.exists():
        raise ScientificEntitySemanticTyperDevelopmentError(
            f"Immutable semantic typer development output already exists: {output_dir}"
        )

    case_bytes = _jsonl_bytes(cases)
    summary_payload = {
        **summary,
        "package_id": package_id,
        "evaluation_id": manifest.evaluation_id,
        "root_cause_review_id": config.parent_evidence.root_cause_review_id,
        "semantic_typer_candidate_id": config.candidate.candidate_id,
        "semantic_typer_fingerprint": semantic_typer_fingerprint(config),
        "model_inference_executed": False,
        "threshold_tuning_executed": False,
        "span_matching_recomputed": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "future_candidate_requires_new_independent_heldout": True,
        "next_slice": config.next_steps["after_prepare"],
    }
    manifest_payload = {
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "package_id": package_id,
        "generated_at_utc": generated_at.isoformat().replace("+00:00", "Z"),
        "semantic_typer_candidate_id": config.candidate.candidate_id,
        "semantic_typer_config_path": _project_path(root, config_path),
        "semantic_typer_config_sha256": semantic_typer_config_sha256(config),
        "semantic_typer_fingerprint": semantic_typer_fingerprint(config),
        "parent_evaluation_id": manifest.evaluation_id,
        "parent_evaluation_manifest_sha256": _sha256_file(evaluation_dir / "manifest.json"),
        "root_cause_review_id": config.parent_evidence.root_cause_review_id,
        "root_cause_review_manifest_sha256": _sha256_file(review_dir / "manifest.json"),
        "root_cause_reviewed_cases_sha256": _sha256_file(review_dir / "reviewed_cases.jsonl"),
        "development_cases_file": "development_cases.jsonl",
        "development_case_count": len(cases),
        "development_cases_sha256": hashlib.sha256(case_bytes).hexdigest(),
        "summary_file": "summary.json",
        "model_inference_executed": False,
        "threshold_tuning_executed": False,
        "span_matching_recomputed": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "publication_ready": False,
        "future_candidate_requires_new_independent_heldout": True,
    }

    report = {
        "report": REPORT_NAME,
        "mode": "execute" if execute else "plan",
        "phase_complete": bool(execute),
        "package_id": package_id,
        "evaluation_id": manifest.evaluation_id,
        "root_cause_review_id": config.parent_evidence.root_cause_review_id,
        "case_count": len(cases),
        "baseline_correct_same_span_count": summary["baseline_correct_same_span_count"],
        "baseline_wrong_same_span_count": summary["baseline_wrong_same_span_count"],
        "primary_metric_eligible_count": summary["primary_metric_eligible_count"],
        "primary_metric_excluded_count": summary["primary_metric_excluded_count"],
        "model_to_method_count": summary["model_to_method_count"],
        "method_to_task_count": summary["method_to_task_count"],
        "model_inference_executed": False,
        "threshold_tuning_executed": False,
        "span_matching_recomputed": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "output_dir": str(output_dir),
        "next_slice": (
            config.next_steps["after_prepare"]
            if execute
            else "execute_prepare_semantic_typer_development_once"
        ),
    }
    if not execute:
        return report

    selected_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{package_id}.tmp-", dir=selected_root))
    try:
        (staging / "development_cases.jsonl").write_bytes(case_bytes)
        (staging / "summary.json").write_bytes(_json_bytes(summary_payload))
        (staging / "manifest.json").write_bytes(_json_bytes(manifest_payload))
        (staging / "README.md").write_text(
            _readme(package_id, summary), encoding="utf-8", newline="\n"
        )
        checksum_rows = []
        for filename in REQUIRED_FILES[:-1]:
            checksum_rows.append(f"{_sha256_file(staging / filename)}  {filename}")
        (staging / "checksums.txt").write_text(
            "\n".join(checksum_rows) + "\n", encoding="utf-8", newline="\n"
        )
        staging.rename(output_dir)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return report


def validate_semantic_typer_development(
    *,
    project_root: Path,
    config_path: Path,
    package_dir: Path,
    evaluation_dir: Path,
    review_dir: Path,
    diagnostics_dir: Path,
) -> tuple[list[tuple[str, bool, str | None]], dict[str, Any]]:
    checks: list[tuple[str, bool, str | None]] = []

    def add(name: str, ok: bool, detail: str | None = None) -> None:
        checks.append((name, bool(ok), detail))

    resolved = package_dir.resolve()
    config = load_semantic_typer_config(config_path.resolve())
    add("package_directory_exists", resolved.is_dir())
    actual = {path.name for path in resolved.iterdir()} if resolved.is_dir() else set()
    add("required_file_layout_exact", actual == set(REQUIRED_FILES), str(sorted(actual)))
    for filename in REQUIRED_FILES:
        add(f"required_file_present:{filename}", (resolved / filename).is_file())

    try:
        manifest = _read_json(resolved / "manifest.json")
        summary = _read_json(resolved / "summary.json")
        cases = [SemanticTyperDevelopmentCase.model_validate(row) for row in _read_jsonl(resolved / "development_cases.jsonl")]
        add("artifacts_parse", True)
    except Exception as exc:
        add("artifacts_parse", False, str(exc))
        manifest = {}
        summary = {}
        cases = []

    checksum_map: dict[str, str] = {}
    try:
        for row in (resolved / "checksums.txt").read_text(encoding="utf-8").splitlines():
            digest, filename = row.split("  ", 1)
            checksum_map[filename] = digest
        add("checksums_parse", True)
    except Exception as exc:
        add("checksums_parse", False, str(exc))
    add("checksums_cover_expected", set(checksum_map) == set(REQUIRED_FILES[:-1]))
    for filename in REQUIRED_FILES[:-1]:
        add(
            f"checksum_matches:{filename}",
            (resolved / filename).is_file()
            and checksum_map.get(filename) == _sha256_file(resolved / filename),
        )

    add("manifest_schema_version", manifest.get("schema_version") == PACKAGE_SCHEMA_VERSION)
    add("candidate_id", manifest.get("semantic_typer_candidate_id") == config.candidate.candidate_id)
    add("config_sha", manifest.get("semantic_typer_config_sha256") == semantic_typer_config_sha256(config))
    add("typer_fingerprint", manifest.get("semantic_typer_fingerprint") == semantic_typer_fingerprint(config))
    add("parent_evaluation_id", manifest.get("parent_evaluation_id") == config.parent_evidence.evaluation_id)
    add("root_cause_review_id", manifest.get("root_cause_review_id") == config.parent_evidence.root_cause_review_id)
    add("case_count", manifest.get("development_case_count") == len(cases))
    cases_bytes = (resolved / "development_cases.jsonl").read_bytes() if (resolved / "development_cases.jsonl").is_file() else b""
    add("case_sha", manifest.get("development_cases_sha256") == hashlib.sha256(cases_bytes).hexdigest())
    add("unique_case_ids", len({row.case_id for row in cases}) == len(cases))
    add("all_spans_valid", all(row.char_end > row.char_start for row in cases))
    add("all_source_text_hashes_present", all(bool(row.source_text_sha256) for row in cases))
    add("wrong_same_span_count", summary.get("baseline_wrong_same_span_count") == config.parent_evidence.expected_same_span_type_mismatch_count)
    add("reference_issue_exclusions", summary.get("primary_metric_excluded_count") == config.parent_evidence.expected_same_span_reference_issue_count)
    add("model_inference_false", manifest.get("model_inference_executed") is False and summary.get("model_inference_executed") is False)
    add("threshold_tuning_false", manifest.get("threshold_tuning_executed") is False and summary.get("threshold_tuning_executed") is False)
    add("matching_recomputed_false", manifest.get("span_matching_recomputed") is False and summary.get("span_matching_recomputed") is False)
    add("canonical_mutation_false", manifest.get("canonical_truth_mutated") is False and summary.get("canonical_truth_mutated") is False)
    add("production_selection_false", manifest.get("production_extractor_selected") is False and summary.get("production_extractor_selected") is False)
    add("full_corpus_false", manifest.get("full_corpus_build_authorized") is False and summary.get("full_corpus_build_authorized") is False)
    add("future_heldout_required", manifest.get("future_candidate_requires_new_independent_heldout") is True and summary.get("future_candidate_requires_new_independent_heldout") is True)

    try:
        reproduced_report = prepare_semantic_typer_development(
            project_root=project_root,
            config_path=config_path,
            evaluation_dir=evaluation_dir,
            review_dir=review_dir,
            diagnostics_dir=diagnostics_dir,
            package_id=str(manifest.get("package_id")),
            output_root=resolved.parent / ".validation-plan-output",
            execute=False,
            generated_at_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        add("parent_lineage_revalidates", reproduced_report.get("case_count") == len(cases))
    except Exception as exc:
        add("parent_lineage_revalidates", False, str(exc))

    failed = [row for row in checks if not row[1]]
    validation_summary = {
        "report": REPORT_NAME,
        "validation_scope": "development_package",
        "package_id": manifest.get("package_id"),
        "case_count": len(cases),
        "baseline_correct_same_span_count": summary.get("baseline_correct_same_span_count"),
        "baseline_wrong_same_span_count": summary.get("baseline_wrong_same_span_count"),
        "primary_metric_eligible_count": summary.get("primary_metric_eligible_count"),
        "primary_metric_excluded_count": summary.get("primary_metric_excluded_count"),
        "total_checks": len(checks),
        "required_failed_count": len(failed),
        "next_slice": config.next_steps["after_prepare"] if not failed else "fix_development_package_validation_failures",
    }
    return checks, validation_summary


__all__ = [
    "REPORT_NAME",
    "REQUIRED_FILES",
    "ScientificEntitySemanticTyperDevelopmentError",
    "materialize_development_cases",
    "prepare_semantic_typer_development",
    "validate_semantic_typer_development",
]
