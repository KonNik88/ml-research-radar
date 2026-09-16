from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from radar_core.contracts.scientific_entity_evidence import ScientificEntityType
from radar_core.contracts.scientific_entity_semantic_typer_candidate import (
    SemanticTyperDevelopmentCase,
    SemanticTyperPrediction,
    load_semantic_typer_config,
    semantic_typer_config_sha256,
)
from radar_core.contracts.scientific_entity_semantic_typer_evaluation import (
    DEVELOPMENT_EVALUATION_SCHEMA_VERSION,
    DEVELOPMENT_EVALUATION_SUMMARY_SCHEMA_VERSION,
    SemanticTyperClassMetrics,
    SemanticTyperDevelopmentDecision,
    SemanticTyperGateResult,
    SemanticTyperMetricSet,
)
from radar_core.entities.scientific_entity_semantic_typer import semantic_typer_fingerprint
from radar_core.entities.scientific_entity_semantic_typer_candidate_inference import validate_semantic_typer_candidate_predictions


REPORT_NAME = "scientific_entity_semantic_typer_development_evaluation_v03"
REQUIRED_FILES = (
    "manifest.json",
    "summary.json",
    "case_comparison.jsonl",
    "diagnostic_slices.json",
    "README.md",
    "checksums.txt",
)


class ScientificEntitySemanticTyperEvaluationError(ValueError):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ScientificEntitySemanticTyperEvaluationError(f"Expected JSON object: {path}")
    return payload


def _read_jsonl(path: Path, model) -> list[Any]:
    return [model.model_validate(json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows).encode("utf-8")


def _checksums(payloads: dict[str, bytes]) -> bytes:
    return "".join(f"{hashlib.sha256(payloads[name]).hexdigest()}  {name}\n" for name in sorted(payloads) if name != "checksums.txt").encode("utf-8")


def _write_atomic(output_dir: Path, payloads: dict[str, bytes]) -> None:
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        for name, data in payloads.items():
            (temp / name).write_bytes(data)
        temp.rename(output_dir)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def _safe_div(num: int, den: int) -> float:
    return 0.0 if den == 0 else num / den


def _metric_set(truth: Sequence[ScientificEntityType], pred: Sequence[ScientificEntityType]) -> SemanticTyperMetricSet:
    if len(truth) != len(pred) or not truth:
        raise ScientificEntitySemanticTyperEvaluationError("Metric inputs must be non-empty and aligned")
    correct = sum(t == p for t, p in zip(truth, pred))
    per_type: list[SemanticTyperClassMetrics] = []
    for entity_type in ScientificEntityType:
        tp = sum(t == entity_type and p == entity_type for t, p in zip(truth, pred))
        fp = sum(t != entity_type and p == entity_type for t, p in zip(truth, pred))
        fn = sum(t == entity_type and p != entity_type for t, p in zip(truth, pred))
        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
        per_type.append(SemanticTyperClassMetrics(entity_type=entity_type, support=sum(t == entity_type for t in truth), precision=round(precision, 6), recall=round(recall, 6), f1=round(f1, 6)))
    return SemanticTyperMetricSet(
        case_count=len(truth),
        correct_count=correct,
        accuracy=round(correct / len(truth), 6),
        macro_f1=round(sum(row.f1 for row in per_type) / len(per_type), 6),
        per_type=per_type,
    )


def _gate(name: str, actual: float | int, op: str, threshold: float | int) -> SemanticTyperGateResult:
    passed = actual >= threshold if op == ">=" else actual <= threshold
    return SemanticTyperGateResult(gate_name=name, passed=passed, actual=actual, operator=op, threshold=threshold)


def _slice(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"case_count": 0}
    corrected = sum(row["baseline_correct"] is False and row["candidate_correct"] is True for row in rows)
    regressed = sum(row["baseline_correct"] is True and row["candidate_correct"] is False for row in rows)
    return {
        "case_count": len(rows),
        "baseline_correct_count": sum(row["baseline_correct"] for row in rows),
        "candidate_correct_count": sum(row["candidate_correct"] for row in rows),
        "corrected_errors": corrected,
        "introduced_regressions": regressed,
        "net_corrected_cases": corrected - regressed,
        "fallback_count": sum(row["used_baseline_fallback"] for row in rows),
    }


def evaluate_candidate(cases: Sequence[SemanticTyperDevelopmentCase], predictions: Sequence[SemanticTyperPrediction], config) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    if len(cases) != len(predictions) or [c.case_id for c in cases] != [p.case_id for p in predictions]:
        raise ScientificEntitySemanticTyperEvaluationError("Development cases and predictions are not aligned")
    comparisons: list[dict[str, Any]] = []
    for case, pred in zip(cases, predictions):
        baseline_correct = case.baseline_entity_type == case.reference_entity_type
        candidate_correct = pred.predicted_entity_type == case.reference_entity_type
        comparisons.append({
            "case_id": case.case_id,
            "canonical_id": case.canonical_id,
            "source_field": case.source_field,
            "reference_entity_type": case.reference_entity_type.value,
            "baseline_entity_type": case.baseline_entity_type.value,
            "candidate_entity_type": pred.predicted_entity_type.value,
            "baseline_correct": baseline_correct,
            "candidate_correct": candidate_correct,
            "corrected_error": (not baseline_correct and candidate_correct),
            "introduced_regression": (baseline_correct and not candidate_correct),
            "used_baseline_fallback": pred.used_baseline_fallback,
            "selected_score": pred.selected_score,
            "score_margin": pred.score_margin,
            "root_cause": case.root_cause,
            "ambiguity_level": case.ambiguity_level,
            "primary_metric_eligible": case.primary_metric_eligible,
        })
    primary_indices = [i for i, case in enumerate(cases) if case.primary_metric_eligible]
    eligible_cases = [cases[i] for i in primary_indices]
    eligible_preds = [predictions[i] for i in primary_indices]
    eligible_rows = [comparisons[i] for i in primary_indices]
    truth = [row.reference_entity_type for row in eligible_cases]
    baseline = [row.baseline_entity_type for row in eligible_cases]
    candidate = [row.predicted_entity_type for row in eligible_preds]
    baseline_metrics = _metric_set(truth, baseline)
    candidate_metrics = _metric_set(truth, candidate)
    corrected = sum(row["corrected_error"] for row in eligible_rows)
    regressed = sum(row["introduced_regression"] for row in eligible_rows)
    baseline_correct_count = sum(row["baseline_correct"] for row in eligible_rows)
    fallback_count = sum(row["used_baseline_fallback"] for row in eligible_rows)
    typer_coverage = round((len(eligible_rows) - fallback_count) / len(eligible_rows), 6)
    regression_rate = round(_safe_div(regressed, baseline_correct_count), 6)
    net = corrected - regressed
    baseline_model_to_method = sum(row.reference_entity_type == ScientificEntityType.MODEL and row.baseline_entity_type == ScientificEntityType.METHOD for row in eligible_cases)
    candidate_model_to_method = sum(c.reference_entity_type == ScientificEntityType.MODEL and p.predicted_entity_type == ScientificEntityType.METHOD for c, p in zip(eligible_cases, eligible_preds))
    model_to_method_reduction = round(_safe_div(baseline_model_to_method - candidate_model_to_method, baseline_model_to_method), 6) if baseline_model_to_method else 0.0
    baseline_method_to_task = sum(row.reference_entity_type == ScientificEntityType.METHOD and row.baseline_entity_type == ScientificEntityType.TASK for row in eligible_cases)
    candidate_method_to_task = sum(c.reference_entity_type == ScientificEntityType.METHOD and p.predicted_entity_type == ScientificEntityType.TASK for c, p in zip(eligible_cases, eligible_preds))
    accuracy_delta = round(candidate_metrics.accuracy - baseline_metrics.accuracy, 6)
    macro_f1_delta = round(candidate_metrics.macro_f1 - baseline_metrics.macro_f1, 6)
    gates = [
        _gate("minimum_typer_coverage", typer_coverage, ">=", config.development_gate.minimum_typer_coverage),
        _gate("minimum_same_span_accuracy_delta", accuracy_delta, ">=", config.development_gate.minimum_same_span_accuracy_delta),
        _gate("minimum_net_corrected_cases", net, ">=", config.development_gate.minimum_net_corrected_cases),
        _gate("maximum_regression_rate", regression_rate, "<=", config.development_gate.maximum_regression_rate),
        _gate("minimum_model_to_method_reduction_fraction", model_to_method_reduction, ">=", config.development_gate.minimum_model_to_method_reduction_fraction),
        _gate("maximum_macro_f1_drop", max(0.0, -macro_f1_delta), "<=", config.development_gate.maximum_macro_f1_drop),
    ]
    all_pass = all(row.passed for row in gates)
    positive = net > 0 and accuracy_delta > 0
    decision_value = "freeze_for_independent_acceptance" if all_pass else ("revise_candidate" if positive else "reject_candidate")
    decision = SemanticTyperDevelopmentDecision(decision=decision_value, all_gates_passed=all_pass, positive_net_improvement=positive)
    summary = {
        "schema_version": DEVELOPMENT_EVALUATION_SUMMARY_SCHEMA_VERSION,
        "case_count": len(cases),
        "primary_metric_eligible_count": len(eligible_cases),
        "primary_metric_excluded_count": len(cases) - len(eligible_cases),
        "baseline_metrics": baseline_metrics.model_dump(mode="json"),
        "candidate_metrics": candidate_metrics.model_dump(mode="json"),
        "same_span_accuracy_delta": accuracy_delta,
        "macro_f1_delta": macro_f1_delta,
        "corrected_errors": corrected,
        "introduced_regressions": regressed,
        "net_corrected_cases": net,
        "regression_rate": regression_rate,
        "typer_coverage": typer_coverage,
        "baseline_model_to_method_count": baseline_model_to_method,
        "candidate_model_to_method_count": candidate_model_to_method,
        "model_to_method_reduction_fraction": model_to_method_reduction,
        "baseline_method_to_task_count": baseline_method_to_task,
        "candidate_method_to_task_count": candidate_method_to_task,
        "gates": [row.model_dump(mode="json") for row in gates],
        "decision": decision.model_dump(mode="json"),
    }
    by_root: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_ambiguity: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_field: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in eligible_rows:
        by_root[str(row["root_cause"] or "baseline_correct_no_root_cause")].append(row)
        by_ambiguity[str(row["ambiguity_level"] or "baseline_correct_no_ambiguity")].append(row)
        by_field[row["source_field"]].append(row)
    diagnostics = {
        "by_source_field": {key: _slice(value) for key, value in sorted(by_field.items())},
        "by_root_cause": {key: _slice(value) for key, value in sorted(by_root.items())},
        "by_ambiguity_level": {key: _slice(value) for key, value in sorted(by_ambiguity.items())},
        "model_to_method": _slice([row for row in eligible_rows if row["reference_entity_type"] == "model" and row["baseline_entity_type"] == "method"]),
        "method_to_task": _slice([row for row in eligible_rows if row["reference_entity_type"] == "method" and row["baseline_entity_type"] == "task"]),
    }
    return summary, comparisons, diagnostics


def plan_or_execute_semantic_typer_development_evaluation(*, project_root: Path, config_path: Path, package_dir: Path, prediction_dir: Path, evaluation_id: str | None = None, output_root: Path | None = None, execute: bool = False, generated_at_utc: datetime | None = None) -> dict[str, Any]:
    root = project_root.resolve()
    config = load_semantic_typer_config(config_path.resolve())
    pred_checks, pred_summary = validate_semantic_typer_candidate_predictions(project_root=root, config_path=config_path, package_dir=package_dir, prediction_dir=prediction_dir)
    if pred_summary.get("required_failed_count") != 0:
        raise ScientificEntitySemanticTyperEvaluationError("Prediction package failed strict validation")
    cases = _read_jsonl(package_dir / "development_cases.jsonl", SemanticTyperDevelopmentCase)
    predictions = _read_jsonl(prediction_dir / "predictions.jsonl", SemanticTyperPrediction)
    generated_at = generated_at_utc or datetime.now(timezone.utc)
    if evaluation_id is None:
        evaluation_id = "scientific-entity-semantic-typer-development-evaluation-v0.3-" + generated_at.strftime("%Y%m%dT%H%M%S%fZ")
    selected_root = output_root.resolve() if output_root is not None else (root / "data/entities/scientific_entity_semantic_typer_evaluation/v0.3").resolve()
    output_dir = selected_root / evaluation_id
    if execute and output_dir.exists():
        raise FileExistsError(f"Immutable semantic typer evaluation output already exists: {output_dir}")
    report = {
        "report": REPORT_NAME,
        "mode": "execute" if execute else "plan",
        "phase_complete": False,
        "evaluation_id": evaluation_id,
        "prediction_id": pred_summary.get("prediction_id"),
        "package_id": pred_summary.get("package_id"),
        "case_count": len(cases),
        "primary_metric_eligible_count": sum(row.primary_metric_eligible for row in cases),
        "quality_metrics_exposed_in_plan": False,
        "development_decision_made": False,
        "threshold_tuning_executed": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "output_dir": str(output_dir).replace("\\", "/"),
        "next_slice": "execute_semantic_typer_development_evaluation_once",
    }
    if not execute:
        return report
    summary, comparisons, diagnostics = evaluate_candidate(cases, predictions, config)
    comparison_bytes = _jsonl_bytes(comparisons)
    manifest = {
        "schema_version": DEVELOPMENT_EVALUATION_SCHEMA_VERSION,
        "evaluation_id": evaluation_id,
        "generated_at_utc": generated_at.isoformat().replace("+00:00", "Z"),
        "package_id": pred_summary.get("package_id"),
        "prediction_id": pred_summary.get("prediction_id"),
        "development_manifest_sha256": _sha256_file(package_dir / "manifest.json"),
        "prediction_manifest_sha256": _sha256_file(prediction_dir / "manifest.json"),
        "candidate_id": config.candidate.candidate_id,
        "semantic_typer_config_sha256": semantic_typer_config_sha256(config),
        "semantic_typer_fingerprint": semantic_typer_fingerprint(config),
        "case_comparison_file": "case_comparison.jsonl",
        "case_comparison_count": len(comparisons),
        "case_comparison_sha256": hashlib.sha256(comparison_bytes).hexdigest(),
        "development_decision_made": True,
        "independent_acceptance_executed": False,
        "threshold_tuning_executed": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "publication_ready": False,
        "future_candidate_requires_new_independent_heldout": True,
    }
    final_summary = {
        **summary,
        "evaluation_id": evaluation_id,
        "package_id": pred_summary.get("package_id"),
        "prediction_id": pred_summary.get("prediction_id"),
        "candidate_id": config.candidate.candidate_id,
        "development_decision_made": True,
        "independent_acceptance_executed": False,
        "threshold_tuning_executed": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "future_candidate_requires_new_independent_heldout": True,
        "next_slice": "freeze_candidate_and_prepare_new_independent_heldout" if summary["decision"]["decision"] == "freeze_for_independent_acceptance" else "inspect_development_failures_before_any_candidate_revision",
    }
    readme = (
        "# Scientific Entity Semantic Typer v0.3 Development Evaluation\n\n"
        "Baseline-vs-candidate evaluation on consumed same-span development evidence only.\n"
        "This is not independent acceptance and does not authorize production or full-corpus inference.\n"
    ).encode("utf-8")
    payloads = {
        "manifest.json": _json_bytes(manifest),
        "summary.json": _json_bytes(final_summary),
        "case_comparison.jsonl": comparison_bytes,
        "diagnostic_slices.json": _json_bytes(diagnostics),
        "README.md": readme,
    }
    payloads["checksums.txt"] = _checksums(payloads)
    _write_atomic(output_dir, payloads)
    report.update({
        "phase_complete": True,
        "development_decision_made": True,
        "decision": summary["decision"]["decision"],
        "all_gates_passed": summary["decision"]["all_gates_passed"],
        "typer_coverage": summary["typer_coverage"],
        "same_span_accuracy_delta": summary["same_span_accuracy_delta"],
        "macro_f1_delta": summary["macro_f1_delta"],
        "net_corrected_cases": summary["net_corrected_cases"],
        "regression_rate": summary["regression_rate"],
        "model_to_method_reduction_fraction": summary["model_to_method_reduction_fraction"],
        "next_slice": final_summary["next_slice"],
    })
    return report


def validate_semantic_typer_development_evaluation(*, project_root: Path, config_path: Path, package_dir: Path, prediction_dir: Path, evaluation_dir: Path) -> tuple[list[tuple[str, bool, str]], dict[str, Any]]:
    root = project_root.resolve()
    config = load_semantic_typer_config(config_path.resolve())
    pred_checks, pred_summary = validate_semantic_typer_candidate_predictions(project_root=root, config_path=config_path, package_dir=package_dir, prediction_dir=prediction_dir)
    checks: list[tuple[str, bool, str]] = []
    def add(name: str, ok: bool, detail: Any = "") -> None:
        checks.append((name, bool(ok), str(detail)))
    add("prediction_package_valid", pred_summary.get("required_failed_count") == 0, pred_summary.get("required_failed_count"))
    evaluation_dir = evaluation_dir.resolve()
    add("evaluation_dir_exists", evaluation_dir.is_dir(), evaluation_dir)
    for name in REQUIRED_FILES:
        add(f"required_file:{name}", (evaluation_dir / name).is_file(), name)
    if not evaluation_dir.is_dir():
        summary = {"report": REPORT_NAME, "validation_scope": "development_evaluation", "total_checks": len(checks), "required_failed_count": sum(not row[1] for row in checks), "next_slice": "fix_development_evaluation_validation_failures"}
        return checks, summary
    manifest = _read_json(evaluation_dir / "manifest.json")
    summary_payload = _read_json(evaluation_dir / "summary.json")
    comparisons = [json.loads(line) for line in (evaluation_dir / "case_comparison.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    cases = _read_jsonl(package_dir / "development_cases.jsonl", SemanticTyperDevelopmentCase)
    predictions = _read_jsonl(prediction_dir / "predictions.jsonl", SemanticTyperPrediction)
    recomputed, recomparisons, _ = evaluate_candidate(cases, predictions, config)
    add("schema_version", manifest.get("schema_version") == DEVELOPMENT_EVALUATION_SCHEMA_VERSION)
    add("candidate_id", manifest.get("candidate_id") == config.candidate.candidate_id)
    add("config_sha256", manifest.get("semantic_typer_config_sha256") == semantic_typer_config_sha256(config))
    add("typer_fingerprint", manifest.get("semantic_typer_fingerprint") == semantic_typer_fingerprint(config))
    add("parent_development_hash", manifest.get("development_manifest_sha256") == _sha256_file(package_dir / "manifest.json"))
    add("parent_prediction_hash", manifest.get("prediction_manifest_sha256") == _sha256_file(prediction_dir / "manifest.json"))
    add("comparison_count", manifest.get("case_comparison_count") == len(cases) == len(comparisons))
    add("comparison_sha256", manifest.get("case_comparison_sha256") == _sha256_file(evaluation_dir / "case_comparison.jsonl"))
    add("comparison_recomputes", comparisons == recomparisons)
    for key in ("same_span_accuracy_delta", "macro_f1_delta", "corrected_errors", "introduced_regressions", "net_corrected_cases", "regression_rate", "typer_coverage", "baseline_model_to_method_count", "candidate_model_to_method_count", "model_to_method_reduction_fraction", "baseline_method_to_task_count", "candidate_method_to_task_count"):
        add(f"metric:{key}", summary_payload.get(key) == recomputed.get(key), f"{summary_payload.get(key)!r} vs {recomputed.get(key)!r}")
    add("gates_recompute", summary_payload.get("gates") == recomputed.get("gates"))
    add("decision_recomputes", summary_payload.get("decision") == recomputed.get("decision"))
    add("development_decision_true", manifest.get("development_decision_made") is True and summary_payload.get("development_decision_made") is True)
    add("independent_acceptance_false", manifest.get("independent_acceptance_executed") is False and summary_payload.get("independent_acceptance_executed") is False)
    add("threshold_tuning_false", manifest.get("threshold_tuning_executed") is False and summary_payload.get("threshold_tuning_executed") is False)
    add("canonical_not_mutated", manifest.get("canonical_truth_mutated") is False and summary_payload.get("canonical_truth_mutated") is False)
    add("production_not_selected", manifest.get("production_extractor_selected") is False and summary_payload.get("production_extractor_selected") is False)
    add("full_corpus_false", manifest.get("full_corpus_build_authorized") is False and summary_payload.get("full_corpus_build_authorized") is False)
    add("future_heldout_required", manifest.get("future_candidate_requires_new_independent_heldout") is True and summary_payload.get("future_candidate_requires_new_independent_heldout") is True)
    checksum_text = (evaluation_dir / "checksums.txt").read_text(encoding="utf-8")
    for name in REQUIRED_FILES:
        if name != "checksums.txt":
            add(f"checksum:{name}", f"{_sha256_file(evaluation_dir / name)}  {name}" in checksum_text, name)
    failed = [row for row in checks if not row[1]]
    validation_summary = {
        "report": REPORT_NAME,
        "validation_scope": "development_evaluation",
        "evaluation_id": manifest.get("evaluation_id"),
        "decision": summary_payload.get("decision", {}).get("decision"),
        "all_gates_passed": summary_payload.get("decision", {}).get("all_gates_passed"),
        "total_checks": len(checks),
        "required_failed_count": len(failed),
        "next_slice": summary_payload.get("next_slice") if not failed else "fix_development_evaluation_validation_failures",
    }
    return checks, validation_summary


__all__ = [
    "REPORT_NAME",
    "REQUIRED_FILES",
    "ScientificEntitySemanticTyperEvaluationError",
    "evaluate_candidate",
    "plan_or_execute_semantic_typer_development_evaluation",
    "validate_semantic_typer_development_evaluation",
]
