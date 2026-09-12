from __future__ import annotations

import hashlib
import json
import shutil
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from radar_core.contracts.scientific_entity_typing_diagnostics import (
    ScientificEntityTypingDiagnosticsConfig,
    TypingCase,
    TypingReviewRow,
)

REPORT_NAME = "scientific_entity_typing_diagnostics_v03"
OUTPUT_FILES = (
    "manifest.json",
    "summary.json",
    "confusion_matrix.json",
    "typing_cases.jsonl",
    "review_template.jsonl",
    "README.md",
    "checksums.txt",
)


class ScientificEntityTypingDiagnosticsError(ValueError):
    pass


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ScientificEntityTypingDiagnosticsError(f"Expected JSON object: {path}")
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ScientificEntityTypingDiagnosticsError(f"Expected JSON object at {path}:{line_no}")
        rows.append(value)
    return rows


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _semantic_config_sha(config: ScientificEntityTypingDiagnosticsConfig) -> str:
    payload = json.dumps(config.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_typing_diagnostics_config(path: Path) -> ScientificEntityTypingDiagnosticsConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return ScientificEntityTypingDiagnosticsConfig.model_validate(raw)


def _index(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        value = str(row.get(key) or "")
        if not value:
            raise ScientificEntityTypingDiagnosticsError(f"Missing {key}")
        if value in out:
            raise ScientificEntityTypingDiagnosticsError(f"Duplicate {key}: {value}")
        out[value] = row
    return out


def _excerpt(text: str, start: int, end: int, radius: int) -> str:
    return text[max(0, start - radius): min(len(text), end + radius)]


def _confidence_summary(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "min": None, "median": None, "mean": None, "max": None}
    return {
        "count": len(values),
        "min": round(min(values), 9),
        "median": round(statistics.median(values), 9),
        "mean": round(statistics.fmean(values), 9),
        "max": round(max(values), 9),
    }


def _validated_inputs(
    *,
    config: ScientificEntityTypingDiagnosticsConfig,
    evaluation_dir: Path,
    decision_dir: Path,
    sample_dir: Path,
    reference_dir: Path,
    prediction_dir: Path,
) -> dict[str, Any]:
    for directory in (evaluation_dir, decision_dir, sample_dir, reference_dir, prediction_dir):
        if not directory.is_dir():
            raise FileNotFoundError(directory)

    evaluation_manifest_path = evaluation_dir / "manifest.json"
    evaluation_errors_path = evaluation_dir / "errors.jsonl"
    metrics_path = evaluation_dir / "metrics.json"
    decision_path = decision_dir / "decision.json"
    decision_manifest_path = decision_dir / "manifest.json"
    documents_path = sample_dir / "canonical_documents.sample.jsonl"
    references_path = reference_dir / "reference_mentions.jsonl"
    predictions_path = prediction_dir / "mentions.jsonl"
    for path in (
        evaluation_manifest_path, evaluation_errors_path, metrics_path,
        decision_path, decision_manifest_path, documents_path, references_path, predictions_path,
    ):
        if not path.is_file():
            raise FileNotFoundError(path)

    if _sha256_file(evaluation_manifest_path) != config.expected.evaluation_manifest_sha256:
        raise ScientificEntityTypingDiagnosticsError("evaluation manifest SHA drifted")
    if _sha256_file(evaluation_errors_path) != config.expected.evaluation_errors_sha256:
        raise ScientificEntityTypingDiagnosticsError("evaluation errors SHA drifted")

    em = _json(evaluation_manifest_path)
    metrics = _json(metrics_path)
    decision = _json(decision_path)
    dm = _json(decision_manifest_path)
    if em.get("evaluation_id") != config.expected.evaluation_id:
        raise ScientificEntityTypingDiagnosticsError("evaluation ID drifted")
    if dm.get("decision_id") != config.expected.decision_id or decision.get("decision_id") != config.expected.decision_id:
        raise ScientificEntityTypingDiagnosticsError("decision ID drifted")
    if decision.get("decision") != config.expected.decision:
        raise ScientificEntityTypingDiagnosticsError("acceptance decision is not the pinned REJECT")
    if decision.get("heldout_becomes_consumed_development_evidence") is not True:
        raise ScientificEntityTypingDiagnosticsError("heldout is not authorized as consumed development evidence")
    if decision.get("future_candidate_requires_new_independent_heldout") is not True:
        raise ScientificEntityTypingDiagnosticsError("future-candidate heldout guard is missing")

    expected_counts = {
        "document_count": config.expected.document_count,
        "reference_mention_count": config.expected.reference_mention_count,
        "prediction_mention_count": config.expected.prediction_mention_count,
    }
    for key, expected in expected_counts.items():
        if int(metrics.get(key, -1)) != expected:
            raise ScientificEntityTypingDiagnosticsError(f"{key} drifted")

    # Verify the exact source artifacts used by evaluation.
    canonical = em.get("canonical_input") or {}
    review = em.get("review") or {}
    prediction = em.get("prediction") or {}
    if _sha256_file(documents_path) != canonical.get("sha256"):
        raise ScientificEntityTypingDiagnosticsError("sample documents SHA does not match evaluation lineage")
    if _sha256_file(references_path) != review.get("reference_mentions_sha256"):
        raise ScientificEntityTypingDiagnosticsError("reference mentions SHA does not match evaluation lineage")
    if _sha256_file(predictions_path) != prediction.get("mentions_sha256"):
        raise ScientificEntityTypingDiagnosticsError("prediction mentions SHA does not match evaluation lineage")

    documents = _jsonl(documents_path)
    references = _jsonl(references_path)
    predictions = _jsonl(predictions_path)
    errors = _jsonl(evaluation_errors_path)
    if len(documents) != config.expected.document_count:
        raise ScientificEntityTypingDiagnosticsError("document row count drifted")
    if len(references) != config.expected.reference_mention_count:
        raise ScientificEntityTypingDiagnosticsError("reference row count drifted")
    if len(predictions) != config.expected.prediction_mention_count:
        raise ScientificEntityTypingDiagnosticsError("prediction row count drifted")

    return {
        "evaluation_manifest": em,
        "decision": decision,
        "decision_manifest": dm,
        "metrics": metrics,
        "documents": documents,
        "references": references,
        "predictions": predictions,
        "errors": errors,
        "sha": {
            "evaluation_manifest": _sha256_file(evaluation_manifest_path),
            "evaluation_errors": _sha256_file(evaluation_errors_path),
            "decision": _sha256_file(decision_path),
            "decision_manifest": _sha256_file(decision_manifest_path),
            "documents": _sha256_file(documents_path),
            "references": _sha256_file(references_path),
            "predictions": _sha256_file(predictions_path),
        },
    }


def compute_typing_diagnostics(
    *,
    config: ScientificEntityTypingDiagnosticsConfig,
    inputs: Mapping[str, Any],
) -> dict[str, Any]:
    docs = _index(inputs["documents"], "canonical_id")
    refs = _index(inputs["references"], "reference_id")
    preds = _index(inputs["predictions"], "evidence_id")
    type_errors = [row for row in inputs["errors"] if row.get("error_kind") == "type_mismatch"]
    if len(type_errors) != config.expected.type_mismatch_count:
        raise ScientificEntityTypingDiagnosticsError("type mismatch count drifted")

    pair_counts = Counter(
        (str(row["reference_entity_type"]), str(row["prediction_entity_type"]))
        for row in type_errors
    )
    pred_sink = Counter(str(row["prediction_entity_type"]) for row in type_errors)
    ref_source = Counter(str(row["reference_entity_type"]) for row in type_errors)
    source_fields = Counter(str(row["source_field"]) for row in type_errors)
    if pair_counts[("model", "method")] != config.expected.model_to_method_count:
        raise ScientificEntityTypingDiagnosticsError("model->method count drifted")
    if pair_counts[("method", "task")] != config.expected.method_to_task_count:
        raise ScientificEntityTypingDiagnosticsError("method->task count drifted")
    if pred_sink["method"] != config.expected.method_sink_count:
        raise ScientificEntityTypingDiagnosticsError("method sink count drifted")
    max_sink_type, max_sink_count = sorted(pred_sink.items(), key=lambda item: (-item[1], item[0]))[0]
    if (max_sink_type, max_sink_count) != (config.expected.maximum_sink_type, config.expected.maximum_sink_count):
        raise ScientificEntityTypingDiagnosticsError("maximum sink drifted")

    ranked_pairs = sorted(pair_counts.items(), key=lambda item: (-item[1], item[0][0], item[0][1]))
    pair_rank = {pair: rank for rank, (pair, _) in enumerate(ranked_pairs, start=1)}
    pair_conf: dict[tuple[str, str], list[float]] = {pair: [] for pair in pair_counts}
    all_conf: list[float] = []
    cases: list[TypingCase] = []

    for row in sorted(type_errors, key=lambda item: str(item["error_id"])):
        canonical_id = str(row["canonical_id"])
        field = str(row["source_field"])
        doc = docs.get(canonical_id)
        ref = refs.get(str(row["reference_id"]))
        pred = preds.get(str(row["prediction_evidence_id"]))
        if doc is None or ref is None or pred is None:
            raise ScientificEntityTypingDiagnosticsError(f"broken error lineage for {row['error_id']}")
        text = doc.get(field)
        if not isinstance(text, str):
            raise ScientificEntityTypingDiagnosticsError(f"missing source text for {row['error_id']}")
        if _sha256_text(text) != row.get("source_text_sha256"):
            raise ScientificEntityTypingDiagnosticsError(f"source text SHA drift for {row['error_id']}")
        rs, re = int(row["reference_char_start"]), int(row["reference_char_end"])
        ps, pe = int(row["prediction_char_start"]), int(row["prediction_char_end"])
        if not (0 <= rs < re <= len(text) and 0 <= ps < pe <= len(text)):
            raise ScientificEntityTypingDiagnosticsError(f"invalid span for {row['error_id']}")
        reference_surface = text[rs:re]
        prediction_surface = text[ps:pe]
        # Reference/prediction source contracts must agree with the evaluation row.
        ref_surface = ref.get("surface_text", ref.get("surface"))
        pred_surface = pred.get("surface_text", pred.get("surface"))
        if isinstance(ref_surface, str) and ref_surface != reference_surface:
            raise ScientificEntityTypingDiagnosticsError(f"reference surface drift for {row['error_id']}")
        if isinstance(pred_surface, str) and pred_surface != prediction_surface:
            raise ScientificEntityTypingDiagnosticsError(f"prediction surface drift for {row['error_id']}")
        confidence = float(pred.get("confidence_score"))
        ref_type = str(row["reference_entity_type"])
        pred_type = str(row["prediction_entity_type"])
        pair = (ref_type, pred_type)
        pair_conf[pair].append(confidence)
        all_conf.append(confidence)
        case_id = "typingcase:" + hashlib.sha256(
            f"{config.expected.evaluation_id}|{row['error_id']}".encode("utf-8")
        ).hexdigest()[:32]
        cases.append(TypingCase(
            diagnostic_case_id=case_id,
            error_id=str(row["error_id"]),
            evaluation_id=config.expected.evaluation_id,
            canonical_id=canonical_id,
            source_field=field,
            reference_id=str(row["reference_id"]),
            prediction_evidence_id=str(row["prediction_evidence_id"]),
            reference_entity_type=ref_type,
            prediction_entity_type=pred_type,
            confusion_pair=f"{ref_type}->{pred_type}",
            pair_count=pair_counts[pair],
            pair_rank=pair_rank[pair],
            reference_char_start=rs,
            reference_char_end=re,
            prediction_char_start=ps,
            prediction_char_end=pe,
            char_iou=float(row["char_iou"]),
            same_span=(rs == ps and re == pe),
            reference_surface=reference_surface,
            prediction_surface=prediction_surface,
            source_excerpt=_excerpt(text, min(rs, ps), max(re, pe), config.review.context_radius_chars),
            prediction_confidence_score=confidence,
            high_confidence_at_0_8=confidence >= 0.8,
            high_confidence_at_0_9=confidence >= 0.9,
        ))

    same_span_count = sum(case.same_span for case in cases)
    confusion_rows = []
    for pair, count in ranked_pairs:
        values = pair_conf[pair]
        confusion_rows.append({
            "reference_entity_type": pair[0],
            "prediction_entity_type": pair[1],
            "confusion_pair": f"{pair[0]}->{pair[1]}",
            "count": count,
            "rank": pair_rank[pair],
            "share_of_type_mismatches": round(count / len(cases), 6),
            "confidence": _confidence_summary(values),
            "high_confidence_at_0_8_count": sum(value >= 0.8 for value in values),
            "high_confidence_at_0_9_count": sum(value >= 0.9 for value in values),
        })

    summary = {
        "schema_version": "scientific_entity_typing_diagnostics_summary_v0.3",
        "evaluation_id": config.expected.evaluation_id,
        "decision_id": config.expected.decision_id,
        "decision": config.expected.decision,
        "document_count": config.expected.document_count,
        "reference_mention_count": config.expected.reference_mention_count,
        "prediction_mention_count": config.expected.prediction_mention_count,
        "type_mismatch_count": len(cases),
        "same_span_type_mismatch_count": same_span_count,
        "same_span_type_mismatch_share": round(same_span_count / len(cases), 6),
        "source_field_counts": dict(sorted(source_fields.items())),
        "predicted_type_sink_counts": dict(sorted(pred_sink.items())),
        "reference_type_source_counts": dict(sorted(ref_source.items())),
        "model_to_method_count": pair_counts[("model", "method")],
        "method_to_task_count": pair_counts[("method", "task")],
        "method_sink_count": pred_sink["method"],
        "maximum_sink_type": max_sink_type,
        "maximum_sink_count": max_sink_count,
        "confidence_all_type_mismatches": _confidence_summary(all_conf),
        "high_confidence_at_0_8_count": sum(value >= 0.8 for value in all_conf),
        "high_confidence_at_0_9_count": sum(value >= 0.9 for value in all_conf),
        "review_status": "prepared_not_reviewed",
        "root_causes_assigned": False,
        "analysis_only": True,
        "model_inference_executed": False,
        "threshold_tuning_executed": False,
        "policy_reapplied": False,
        "evaluation_recomputed": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "future_candidate_requires_new_independent_heldout": True,
        "next_slice": config.next_steps["after_prepare"],
    }
    confusion = {
        "schema_version": "scientific_entity_typing_confusion_matrix_v0.3",
        "type_mismatch_count": len(cases),
        "rows": confusion_rows,
        "predicted_type_sink_counts": dict(sorted(pred_sink.items())),
        "reference_type_source_counts": dict(sorted(ref_source.items())),
    }
    review_rows = [TypingReviewRow(
        diagnostic_case_id=case.diagnostic_case_id,
        error_id=case.error_id,
        confusion_pair=case.confusion_pair,
        reference_surface=case.reference_surface,
        prediction_surface=case.prediction_surface,
        source_excerpt=case.source_excerpt,
        reference_entity_type=case.reference_entity_type,
        prediction_entity_type=case.prediction_entity_type,
        prediction_confidence_score=case.prediction_confidence_score,
    ) for case in cases]
    return {"summary": summary, "confusion": confusion, "cases": cases, "review_rows": review_rows}


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def _write_jsonl(path: Path, rows: Sequence[Any]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            if hasattr(row, "model_dump"):
                row = row.model_dump(mode="json")
            fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def _readme(config: ScientificEntityTypingDiagnosticsConfig, summary: Mapping[str, Any]) -> str:
    return f"""# Scientific Entity Typing Diagnostics v0.3\n\nThis package consumes the formally rejected fresh v0.2c held-out only after the immutable acceptance decision authorized it as development evidence.\n\n## Scope\n\n- type mismatches only: `{summary['type_mismatch_count']}`\n- model -> method: `{summary['model_to_method_count']}`\n- method -> task: `{summary['method_to_task_count']}`\n- method sink: `{summary['method_sink_count']}`\n- same-span type mismatches: `{summary['same_span_type_mismatch_count']}` (`{summary['same_span_type_mismatch_share']:.3f}`)\n- root causes are **not** assigned automatically\n- model inference, threshold tuning, policy reapplication, and evaluation recomputation are forbidden\n\n`review_template.jsonl` is a human-review working template. Allowed root-cause labels are: `{', '.join(config.review.root_cause_labels)}`.\nAllowed recommended-action labels are: `{', '.join(config.review.recommended_action_labels)}`.\n\nAny v0.3 candidate informed by this package requires a new independent prediction-blind held-out.\n"""


def prepare_typing_diagnostics(
    *,
    project_root: Path,
    config_path: Path,
    evaluation_dir: Path,
    decision_dir: Path,
    sample_dir: Path,
    reference_dir: Path,
    prediction_dir: Path,
    output_root: Path | None = None,
    analysis_id: str | None = None,
    execute: bool = False,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    config = load_typing_diagnostics_config(config_path.resolve())
    inputs = _validated_inputs(
        config=config,
        evaluation_dir=evaluation_dir.resolve(),
        decision_dir=decision_dir.resolve(),
        sample_dir=sample_dir.resolve(),
        reference_dir=reference_dir.resolve(),
        prediction_dir=prediction_dir.resolve(),
    )
    diagnostic = compute_typing_diagnostics(config=config, inputs=inputs)
    if analysis_id is None:
        analysis_id = "scientific-entity-typing-diagnostics-v0.3-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    root = (output_root.resolve() if output_root else (project_root / config.output.root).resolve())
    output_dir = root / analysis_id
    if output_dir.exists():
        raise ScientificEntityTypingDiagnosticsError(f"output already exists: {output_dir}")

    report = {
        "report": REPORT_NAME,
        "mode": "execute" if execute else "plan",
        "phase_complete": bool(execute),
        "analysis_id": analysis_id,
        "evaluation_id": config.expected.evaluation_id,
        "decision_id": config.expected.decision_id,
        **{key: diagnostic["summary"][key] for key in (
            "type_mismatch_count", "same_span_type_mismatch_count", "same_span_type_mismatch_share",
            "model_to_method_count", "method_to_task_count", "method_sink_count",
            "maximum_sink_type", "maximum_sink_count", "high_confidence_at_0_8_count", "high_confidence_at_0_9_count",
        )},
        "root_causes_assigned": False,
        "model_inference_executed": False,
        "threshold_tuning_executed": False,
        "policy_reapplied": False,
        "evaluation_recomputed": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "output_dir": str(output_dir),
        "next_slice": config.next_steps["after_prepare"] if execute else "execute_typing_diagnostics_preparation_once",
    }
    if not execute:
        return report

    root.mkdir(parents=True, exist_ok=True)
    staging = root / f".{analysis_id}.staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    try:
        manifest = {
            "schema_version": "scientific_entity_typing_diagnostics_manifest_v0.3",
            "analysis_id": analysis_id,
            "generated_at_utc": generated_at_utc or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "evaluation_id": config.expected.evaluation_id,
            "decision_id": config.expected.decision_id,
            "decision": config.expected.decision,
            "config_path": str(config_path.resolve()),
            "config_semantic_sha256": _semantic_config_sha(config),
            "input_sha256": inputs["sha"],
            "output_files": list(OUTPUT_FILES),
            "analysis_only": True,
            "root_causes_assigned": False,
            "model_inference_executed": False,
            "threshold_tuning_executed": False,
            "policy_reapplied": False,
            "evaluation_recomputed": False,
            "canonical_truth_mutated": False,
            "production_extractor_selected": False,
            "full_corpus_build_authorized": False,
            "future_candidate_requires_new_independent_heldout": True,
        }
        _write_json(staging / "manifest.json", manifest)
        _write_json(staging / "summary.json", diagnostic["summary"])
        _write_json(staging / "confusion_matrix.json", diagnostic["confusion"])
        _write_jsonl(staging / "typing_cases.jsonl", diagnostic["cases"])
        _write_jsonl(staging / "review_template.jsonl", diagnostic["review_rows"])
        (staging / "README.md").write_text(_readme(config, diagnostic["summary"]), encoding="utf-8", newline="\n")
        checksum_lines = []
        for name in OUTPUT_FILES[:-1]:
            checksum_lines.append(f"{_sha256_file(staging / name)}  {name}\n")
        (staging / "checksums.txt").write_text("".join(checksum_lines), encoding="utf-8", newline="\n")
        staging.rename(output_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return report


def validate_typing_diagnostics(*, analysis_dir: Path) -> tuple[list[tuple[str, bool, str]], dict[str, Any]]:
    analysis_dir = analysis_dir.resolve()
    checks: list[tuple[str, bool, str]] = []
    def add(name: str, ok: bool, detail: Any = "") -> None:
        checks.append((name, bool(ok), str(detail)))

    add("analysis_dir_exists", analysis_dir.is_dir(), analysis_dir)
    if not analysis_dir.is_dir():
        return checks, {"report": REPORT_NAME, "required_failed_count": 1, "total_checks": 1}
    names = sorted(path.name for path in analysis_dir.iterdir() if path.is_file())
    add("exact_file_set", names == sorted(OUTPUT_FILES), names)
    for name in OUTPUT_FILES:
        add(f"file_exists::{name}", (analysis_dir / name).is_file(), name)
    if not all((analysis_dir / name).is_file() for name in OUTPUT_FILES):
        failed = [name for name, ok, _ in checks if not ok]
        return checks, {"report": REPORT_NAME, "required_failed_count": len(failed), "total_checks": len(checks)}

    expected_checksums: dict[str, str] = {}
    for line in (analysis_dir / "checksums.txt").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        expected_checksums[name] = digest
    for name in OUTPUT_FILES[:-1]:
        add(f"checksum_matches::{name}", expected_checksums.get(name) == _sha256_file(analysis_dir / name), name)

    manifest = _json(analysis_dir / "manifest.json")
    summary = _json(analysis_dir / "summary.json")
    confusion = _json(analysis_dir / "confusion_matrix.json")
    cases = [TypingCase.model_validate(row) for row in _jsonl(analysis_dir / "typing_cases.jsonl")]
    reviews = [TypingReviewRow.model_validate(row) for row in _jsonl(analysis_dir / "review_template.jsonl")]
    add("type_mismatch_count_matches_cases", summary.get("type_mismatch_count") == len(cases), len(cases))
    add("review_row_count_matches_cases", len(reviews) == len(cases), len(reviews))
    add("case_ids_unique", len({row.diagnostic_case_id for row in cases}) == len(cases), "")
    add("error_ids_unique", len({row.error_id for row in cases}) == len(cases), "")
    pair_counts = Counter((row.reference_entity_type, row.prediction_entity_type) for row in cases)
    pred_sink = Counter(row.prediction_entity_type for row in cases)
    same_span = sum(row.same_span for row in cases)
    add("model_to_method_arithmetic", summary.get("model_to_method_count") == pair_counts[("model", "method")], pair_counts[("model", "method")])
    add("method_to_task_arithmetic", summary.get("method_to_task_count") == pair_counts[("method", "task")], pair_counts[("method", "task")])
    add("method_sink_arithmetic", summary.get("method_sink_count") == pred_sink["method"], pred_sink["method"])
    add("same_span_arithmetic", summary.get("same_span_type_mismatch_count") == same_span, same_span)
    add("root_causes_not_assigned", summary.get("root_causes_assigned") is False and all(row.root_cause is None for row in reviews), "")
    for key in (
        "model_inference_executed", "threshold_tuning_executed", "policy_reapplied",
        "evaluation_recomputed", "canonical_truth_mutated", "production_extractor_selected",
        "full_corpus_build_authorized",
    ):
        add(f"safety::{key}", summary.get(key) is False and manifest.get(key) is False, "")
    add("future_heldout_guard", summary.get("future_candidate_requires_new_independent_heldout") is True and manifest.get("future_candidate_requires_new_independent_heldout") is True, "")
    add("confusion_total_matches", confusion.get("type_mismatch_count") == len(cases), confusion.get("type_mismatch_count"))

    failed = [name for name, ok, _ in checks if not ok]
    validation_summary = {
        "report": REPORT_NAME,
        "analysis_id": manifest.get("analysis_id"),
        "evaluation_id": summary.get("evaluation_id"),
        "decision_id": summary.get("decision_id"),
        "type_mismatch_count": len(cases),
        "same_span_type_mismatch_count": same_span,
        "model_to_method_count": pair_counts[("model", "method")],
        "method_to_task_count": pair_counts[("method", "task")],
        "method_sink_count": pred_sink["method"],
        "root_causes_assigned": False,
        "total_checks": len(checks),
        "required_failed_count": len(failed),
        "next_slice": "review_typing_cases_and_assign_root_causes",
    }
    return checks, validation_summary
