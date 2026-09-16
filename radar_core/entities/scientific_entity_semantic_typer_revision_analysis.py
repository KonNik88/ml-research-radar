from __future__ import annotations

import hashlib
import json
import shutil
import statistics
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from radar_core.contracts.scientific_entity_evidence import ScientificEntityType
from radar_core.contracts.scientific_entity_semantic_typer_revision_analysis import (
    SELECTED_POLICY_SCHEMA_VERSION,
    SUMMARY_SCHEMA_VERSION,
    SelectedRevisionPolicy,
    ThresholdSweepRow,
    load_revision_analysis_config,
)
from radar_core.entities.scientific_entity_semantic_typer_evaluation import _metric_set


REPORT_NAME = "scientific_entity_semantic_typer_revision_analysis_v03"
REQUIRED_PARENT_FILES = (
    "manifest.json",
    "summary.json",
    "case_comparison.jsonl",
    "diagnostic_slices.json",
    "README.md",
    "checksums.txt",
)
REQUIRED_OUTPUT_FILES = (
    "manifest.json",
    "summary.json",
    "margin_sweep.json",
    "transition_breakdown.json",
    "selected_policy.json",
    "policy_case_outcomes.jsonl",
    "README.md",
    "checksums.txt",
)


class ScientificEntitySemanticTyperRevisionAnalysisError(ValueError):
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
        raise ScientificEntitySemanticTyperRevisionAnalysisError(f"Expected JSON object: {path}")
    return payload


def _read_jsonl_dicts(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not all(isinstance(row, dict) for row in rows):
        raise ScientificEntitySemanticTyperRevisionAnalysisError(f"Expected JSONL objects: {path}")
    return rows


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows).encode("utf-8")


def _checksums(payloads: dict[str, bytes]) -> bytes:
    return "".join(
        f"{hashlib.sha256(payloads[name]).hexdigest()}  {name}\n"
        for name in sorted(payloads)
        if name != "checksums.txt"
    ).encode("utf-8")


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


def _parent_checks(parent_summary: dict[str, Any], comparisons: Sequence[dict[str, Any]], config) -> None:
    expected = config.analysis
    actuals = {
        "case_count": parent_summary.get("case_count"),
        "primary_metric_eligible_count": parent_summary.get("primary_metric_eligible_count"),
        "corrected_errors": parent_summary.get("corrected_errors"),
        "introduced_regressions": parent_summary.get("introduced_regressions"),
        "net_corrected_cases": parent_summary.get("net_corrected_cases"),
        "baseline_model_to_method_count": parent_summary.get("baseline_model_to_method_count"),
    }
    expected_values = {
        "case_count": expected.expected_case_count,
        "primary_metric_eligible_count": expected.expected_primary_metric_eligible_count,
        "corrected_errors": expected.expected_corrected_errors,
        "introduced_regressions": expected.expected_introduced_regressions,
        "net_corrected_cases": expected.expected_net_corrected_cases,
        "baseline_model_to_method_count": expected.expected_baseline_model_to_method_count,
    }
    if actuals != expected_values:
        raise ScientificEntitySemanticTyperRevisionAnalysisError(
            f"Parent H1 evaluation summary drifted: actual={actuals}, expected={expected_values}"
        )
    decision = parent_summary.get("decision", {})
    if decision.get("decision") != expected.expected_parent_decision:
        raise ScientificEntitySemanticTyperRevisionAnalysisError("Parent H1 decision must be reject_candidate")
    if parent_summary.get("candidate_id") != expected.parent_candidate_id:
        raise ScientificEntitySemanticTyperRevisionAnalysisError("Parent H1 candidate_id drifted")
    if len(comparisons) != expected.expected_case_count:
        raise ScientificEntitySemanticTyperRevisionAnalysisError("Parent case_comparison count drifted")
    eligible = sum(bool(row.get("primary_metric_eligible")) for row in comparisons)
    if eligible != expected.expected_primary_metric_eligible_count:
        raise ScientificEntitySemanticTyperRevisionAnalysisError("Primary metric eligibility count drifted")


def _gate_passes(row: dict[str, Any], config, typer_coverage: float) -> bool:
    gates = config.reuse_development_gates
    return all(
        (
            typer_coverage >= gates.minimum_typer_coverage,
            row["same_span_accuracy_delta"] >= gates.minimum_same_span_accuracy_delta,
            row["net_corrected_cases"] >= gates.minimum_net_corrected_cases,
            row["regression_rate"] <= gates.maximum_regression_rate,
            row["model_to_method_reduction_fraction"] >= gates.minimum_model_to_method_reduction_fraction,
            max(0.0, -row["macro_f1_delta"]) <= gates.maximum_macro_f1_drop,
        )
    )


def _threshold_row(
    eligible_rows: Sequence[dict[str, Any]],
    threshold: float,
    config,
    *,
    baseline_metrics,
    baseline_correct_count: int,
    baseline_model_to_method_count: int,
    typer_coverage: float,
) -> tuple[ThresholdSweepRow, list[dict[str, Any]]]:
    truth: list[ScientificEntityType] = []
    policy_predictions: list[ScientificEntityType] = []
    outcomes: list[dict[str, Any]] = []
    corrected = regressed = wrong_to_wrong = overrides = 0
    policy = config.policy_family
    for row in eligible_rows:
        reference = ScientificEntityType(row["reference_entity_type"])
        baseline = ScientificEntityType(row["baseline_entity_type"])
        h1_candidate = ScientificEntityType(row["candidate_entity_type"])
        margin = row.get("score_margin")
        override = (
            baseline == ScientificEntityType(policy.baseline_type)
            and h1_candidate == ScientificEntityType(policy.semantic_typer_type)
            and margin is not None
            and float(margin) >= threshold
        )
        final = h1_candidate if override else baseline
        baseline_correct = baseline == reference
        final_correct = final == reference
        if override:
            overrides += 1
            if (not baseline_correct) and final_correct:
                corrected += 1
            elif baseline_correct and (not final_correct):
                regressed += 1
            elif (not baseline_correct) and (not final_correct):
                wrong_to_wrong += 1
        truth.append(reference)
        policy_predictions.append(final)
        outcomes.append({
            "case_id": row["case_id"],
            "reference_entity_type": reference.value,
            "baseline_entity_type": baseline.value,
            "h1_candidate_entity_type": h1_candidate.value,
            "score_margin": margin,
            "override_applied": override,
            "final_entity_type": final.value,
            "baseline_correct": baseline_correct,
            "final_correct": final_correct,
            "corrected_error": (not baseline_correct and final_correct),
            "introduced_regression": (baseline_correct and not final_correct),
            "wrong_to_wrong_change": (override and not baseline_correct and not final_correct),
        })
    candidate_metrics = _metric_set(truth, policy_predictions)
    accuracy_delta = round(candidate_metrics.accuracy - baseline_metrics.accuracy, 6)
    macro_f1_delta = round(candidate_metrics.macro_f1 - baseline_metrics.macro_f1, 6)
    regression_rate = round(_safe_div(regressed, baseline_correct_count), 6)
    net = corrected - regressed
    m2m_after = sum(t == ScientificEntityType.MODEL and p == ScientificEntityType.METHOD for t, p in zip(truth, policy_predictions))
    reduction = round(_safe_div(baseline_model_to_method_count - m2m_after, baseline_model_to_method_count), 6)
    raw = {
        "threshold": round(threshold, 6),
        "override_count": overrides,
        "corrected_errors": corrected,
        "introduced_regressions": regressed,
        "wrong_to_wrong_changes": wrong_to_wrong,
        "net_corrected_cases": net,
        "regression_rate": regression_rate,
        "same_span_accuracy_delta": accuracy_delta,
        "macro_f1_delta": macro_f1_delta,
        "model_to_method_after_count": m2m_after,
        "model_to_method_reduction_fraction": reduction,
    }
    raw["all_reused_gates_passed"] = _gate_passes(raw, config, typer_coverage)
    raw["stable_plateau_member"] = False
    return ThresholdSweepRow.model_validate(raw), outcomes


def _mark_plateau_and_select(rows: list[ThresholdSweepRow], config) -> tuple[list[ThresholdSweepRow], SelectedRevisionPolicy]:
    passing = [row.all_reused_gates_passed for row in rows]
    stable_indexes: set[int] = set()
    for index in range(1, len(rows) - 1):
        if passing[index - 1] and passing[index] and passing[index + 1]:
            stable_indexes.add(index)
    updated = [row.model_copy(update={"stable_plateau_member": i in stable_indexes}) for i, row in enumerate(rows)]
    if stable_indexes:
        selected_index = min(stable_indexes)
        selected = updated[selected_index]
        plateau = [updated[selected_index - 1].threshold, selected.threshold, updated[selected_index + 1].threshold]
        policy = SelectedRevisionPolicy(
            status="selected",
            policy_id=config.policy_family.policy_id,
            baseline_type=ScientificEntityType(config.policy_family.baseline_type),
            semantic_typer_type=ScientificEntityType(config.policy_family.semantic_typer_type),
            score_field="score_margin",
            operator=">=",
            threshold=selected.threshold,
            selection_rule=config.policy_family.selection_rule,
            plateau_thresholds=plateau,
        )
    else:
        policy = SelectedRevisionPolicy(
            status="not_selected",
            policy_id=config.policy_family.policy_id,
            baseline_type=ScientificEntityType(config.policy_family.baseline_type),
            semantic_typer_type=ScientificEntityType(config.policy_family.semantic_typer_type),
            score_field="score_margin",
            operator=">=",
            threshold=None,
            selection_rule=config.policy_family.selection_rule,
            plateau_thresholds=[],
        )
    return updated, policy


def _transition_breakdown(eligible_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    changed_rows = []
    for row in eligible_rows:
        if row["baseline_entity_type"] == row["candidate_entity_type"]:
            continue
        key = f'{row["baseline_entity_type"]}->{row["candidate_entity_type"]}'
        grouped[key].append(row)
        changed_rows.append(row)

    def summarize(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
        margins = [float(row["score_margin"]) for row in rows if row.get("score_margin") is not None]
        corrected = sum(bool(row["corrected_error"]) for row in rows)
        regressed = sum(bool(row["introduced_regression"]) for row in rows)
        wrong_wrong = sum((not row["baseline_correct"]) and (not row["candidate_correct"]) for row in rows)
        return {
            "case_count": len(rows),
            "corrected_errors": corrected,
            "introduced_regressions": regressed,
            "wrong_to_wrong_changes": wrong_wrong,
            "median_score_margin": round(statistics.median(margins), 6) if margins else None,
            "minimum_score_margin": round(min(margins), 6) if margins else None,
            "maximum_score_margin": round(max(margins), 6) if margins else None,
        }

    return {
        "changed_case_count": len(changed_rows),
        "by_transition": {key: summarize(value) for key, value in sorted(grouped.items())},
        "correction_margin_summary": summarize([row for row in changed_rows if row["corrected_error"]]),
        "regression_margin_summary": summarize([row for row in changed_rows if row["introduced_regression"]]),
        "wrong_to_wrong_margin_summary": summarize([
            row for row in changed_rows if (not row["baseline_correct"]) and (not row["candidate_correct"])
        ]),
    }


def analyze_revision(parent_summary: dict[str, Any], comparisons: Sequence[dict[str, Any]], config) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    _parent_checks(parent_summary, comparisons, config)
    eligible = [row for row in comparisons if row["primary_metric_eligible"]]
    truth = [ScientificEntityType(row["reference_entity_type"]) for row in eligible]
    baseline = [ScientificEntityType(row["baseline_entity_type"]) for row in eligible]
    baseline_metrics = _metric_set(truth, baseline)
    baseline_correct_count = sum(t == p for t, p in zip(truth, baseline))
    baseline_m2m = sum(t == ScientificEntityType.MODEL and p == ScientificEntityType.METHOD for t, p in zip(truth, baseline))
    typer_coverage = float(parent_summary["typer_coverage"])

    sweep: list[ThresholdSweepRow] = []
    outcomes_by_threshold: dict[float, list[dict[str, Any]]] = {}
    for threshold in config.policy_family.threshold_grid:
        row, outcomes = _threshold_row(
            eligible,
            float(threshold),
            config,
            baseline_metrics=baseline_metrics,
            baseline_correct_count=baseline_correct_count,
            baseline_model_to_method_count=baseline_m2m,
            typer_coverage=typer_coverage,
        )
        sweep.append(row)
        outcomes_by_threshold[row.threshold] = outcomes
    sweep, selected_policy = _mark_plateau_and_select(sweep, config)
    selected_row = next((row for row in sweep if selected_policy.threshold is not None and row.threshold == selected_policy.threshold), None)
    selected_outcomes = outcomes_by_threshold.get(selected_policy.threshold, []) if selected_policy.threshold is not None else []
    summary = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "parent_candidate_id": parent_summary["candidate_id"],
        "parent_evaluation_id": parent_summary["evaluation_id"],
        "parent_decision": parent_summary["decision"]["decision"],
        "case_count": len(comparisons),
        "primary_metric_eligible_count": len(eligible),
        "parent_corrected_errors": parent_summary["corrected_errors"],
        "parent_introduced_regressions": parent_summary["introduced_regressions"],
        "parent_net_corrected_cases": parent_summary["net_corrected_cases"],
        "policy_family_id": config.policy_family.policy_id,
        "selection_rule": config.policy_family.selection_rule,
        "selected_policy_status": selected_policy.status,
        "selected_threshold": selected_policy.threshold,
        "selected_plateau_thresholds": selected_policy.plateau_thresholds,
        "selected_policy_metrics": selected_row.model_dump(mode="json") if selected_row is not None else None,
        "new_model_inference_executed": False,
        "model_inference_threshold_tuning_executed": False,
        "policy_margin_threshold_calibration_executed": True,
        "independent_acceptance_executed": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "future_candidate_requires_new_independent_heldout": True,
        "next_slice": config.next_steps["if_selected"] if selected_policy.status == "selected" else config.next_steps["if_not_selected"],
    }
    transition_breakdown = _transition_breakdown(eligible)
    margin_sweep = {
        "policy_family_id": config.policy_family.policy_id,
        "selection_rule": config.policy_family.selection_rule,
        "typer_coverage_reused_from_h1": typer_coverage,
        "rows": [row.model_dump(mode="json") for row in sweep],
    }
    return summary, selected_outcomes, margin_sweep, {
        "transition_breakdown": transition_breakdown,
        "selected_policy": selected_policy.model_dump(mode="json"),
    }


def plan_or_execute_semantic_typer_revision_analysis(
    *,
    project_root: Path,
    config_path: Path,
    evaluation_dir: Path,
    analysis_id: str | None = None,
    output_root: Path | None = None,
    execute: bool = False,
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    root = project_root.resolve()
    config = load_revision_analysis_config(config_path.resolve())
    evaluation_dir = evaluation_dir.resolve()
    if not evaluation_dir.is_dir():
        raise FileNotFoundError(f"Parent H1 evaluation directory does not exist: {evaluation_dir}")
    for name in REQUIRED_PARENT_FILES:
        if not (evaluation_dir / name).is_file():
            raise FileNotFoundError(f"Missing parent H1 evaluation file: {evaluation_dir / name}")
    parent_summary = _read_json(evaluation_dir / "summary.json")
    comparisons = _read_jsonl_dicts(evaluation_dir / "case_comparison.jsonl")
    _parent_checks(parent_summary, comparisons, config)
    generated_at = generated_at_utc or datetime.now(timezone.utc)
    if analysis_id is None:
        analysis_id = config.analysis.analysis_id_prefix + "-" + generated_at.strftime("%Y%m%dT%H%M%S%fZ")
    selected_root = output_root.resolve() if output_root is not None else (root / "data/entities/scientific_entity_semantic_typer_revision_analysis/v0.3").resolve()
    output_dir = selected_root / analysis_id
    if execute and output_dir.exists():
        raise FileExistsError(f"Immutable semantic typer revision analysis already exists: {output_dir}")
    report = {
        "report": REPORT_NAME,
        "mode": "execute" if execute else "plan",
        "phase_complete": False,
        "analysis_id": analysis_id,
        "parent_evaluation_id": parent_summary.get("evaluation_id"),
        "parent_candidate_id": parent_summary.get("candidate_id"),
        "parent_decision": parent_summary.get("decision", {}).get("decision"),
        "case_count": len(comparisons),
        "primary_metric_eligible_count": sum(bool(row.get("primary_metric_eligible")) for row in comparisons),
        "revision_metrics_exposed_in_plan": False,
        "policy_selected": False,
        "new_model_inference_executed": False,
        "model_inference_threshold_tuning_executed": False,
        "policy_margin_threshold_calibration_executed": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "output_dir": str(output_dir).replace("\\", "/"),
        "next_slice": "execute_semantic_typer_revision_analysis_once",
    }
    if not execute:
        return report
    summary, selected_outcomes, margin_sweep, extra = analyze_revision(parent_summary, comparisons, config)
    selected_policy = extra["selected_policy"]
    transition_breakdown = extra["transition_breakdown"]
    outcome_bytes = _jsonl_bytes(selected_outcomes)
    manifest = {
        "schema_version": "scientific_entity_semantic_typer_revision_analysis_manifest_v0.3",
        "analysis_id": analysis_id,
        "generated_at_utc": generated_at.isoformat().replace("+00:00", "Z"),
        "parent_evaluation_id": parent_summary.get("evaluation_id"),
        "parent_candidate_id": parent_summary.get("candidate_id"),
        "parent_evaluation_manifest_sha256": _sha256_file(evaluation_dir / "manifest.json"),
        "parent_evaluation_summary_sha256": _sha256_file(evaluation_dir / "summary.json"),
        "parent_case_comparison_sha256": _sha256_file(evaluation_dir / "case_comparison.jsonl"),
        "selected_policy_status": selected_policy["status"],
        "policy_margin_threshold_calibration_executed": True,
        "new_model_inference_executed": False,
        "independent_acceptance_executed": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "future_candidate_requires_new_independent_heldout": True,
    }
    final_summary = {**summary, "analysis_id": analysis_id}
    readme = (
        "# Scientific Entity Semantic Typer v0.3 H1 Failure / Revision Analysis\n\n"
        "Deterministic calibration analysis over already-consumed H1 development evidence.\n"
        "No new model inference is executed. The selected H2 policy, if any, is development-only\n"
        "and still requires a new disjoint prediction-blind held-out for independent acceptance.\n"
    ).encode("utf-8")
    payloads = {
        "manifest.json": _json_bytes(manifest),
        "summary.json": _json_bytes(final_summary),
        "margin_sweep.json": _json_bytes(margin_sweep),
        "transition_breakdown.json": _json_bytes(transition_breakdown),
        "selected_policy.json": _json_bytes(selected_policy),
        "policy_case_outcomes.jsonl": outcome_bytes,
        "README.md": readme,
    }
    payloads["checksums.txt"] = _checksums(payloads)
    _write_atomic(output_dir, payloads)
    report.update({
        "phase_complete": True,
        "policy_selected": selected_policy["status"] == "selected",
        "selected_threshold": selected_policy.get("threshold"),
        "selected_plateau_thresholds": selected_policy.get("plateau_thresholds"),
        "selected_net_corrected_cases": (summary.get("selected_policy_metrics") or {}).get("net_corrected_cases"),
        "selected_regression_rate": (summary.get("selected_policy_metrics") or {}).get("regression_rate"),
        "selected_same_span_accuracy_delta": (summary.get("selected_policy_metrics") or {}).get("same_span_accuracy_delta"),
        "policy_margin_threshold_calibration_executed": True,
        "next_slice": summary["next_slice"],
    })
    return report


def validate_semantic_typer_revision_analysis(
    *,
    project_root: Path,
    config_path: Path,
    evaluation_dir: Path,
    analysis_dir: Path,
) -> tuple[list[tuple[str, bool, str]], dict[str, Any]]:
    del project_root
    config = load_revision_analysis_config(config_path.resolve())
    evaluation_dir = evaluation_dir.resolve()
    analysis_dir = analysis_dir.resolve()
    checks: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: Any = "") -> None:
        checks.append((name, bool(ok), str(detail)))

    add("analysis_dir_exists", analysis_dir.is_dir(), analysis_dir)
    for name in REQUIRED_OUTPUT_FILES:
        add(f"required_file:{name}", (analysis_dir / name).is_file(), name)
    if not analysis_dir.is_dir() or any(not (analysis_dir / name).is_file() for name in REQUIRED_OUTPUT_FILES):
        summary = {
            "report": REPORT_NAME,
            "validation_scope": "revision_analysis",
            "total_checks": len(checks),
            "required_failed_count": sum(not item[1] for item in checks),
            "next_slice": "fix_revision_analysis_validation_failures",
        }
        return checks, summary

    parent_summary = _read_json(evaluation_dir / "summary.json")
    comparisons = _read_jsonl_dicts(evaluation_dir / "case_comparison.jsonl")
    recomputed_summary, recomputed_outcomes, recomputed_sweep, recomputed_extra = analyze_revision(parent_summary, comparisons, config)
    stored_manifest = _read_json(analysis_dir / "manifest.json")
    stored_summary = _read_json(analysis_dir / "summary.json")
    stored_sweep = _read_json(analysis_dir / "margin_sweep.json")
    stored_transition = _read_json(analysis_dir / "transition_breakdown.json")
    stored_policy = _read_json(analysis_dir / "selected_policy.json")
    stored_outcomes = _read_jsonl_dicts(analysis_dir / "policy_case_outcomes.jsonl")

    analysis_id = stored_manifest.get("analysis_id")
    expected_summary = {**recomputed_summary, "analysis_id": analysis_id}
    add("parent_evaluation_id_matches", stored_manifest.get("parent_evaluation_id") == parent_summary.get("evaluation_id"), stored_manifest.get("parent_evaluation_id"))
    add("parent_candidate_id_matches", stored_manifest.get("parent_candidate_id") == parent_summary.get("candidate_id"), stored_manifest.get("parent_candidate_id"))
    add("parent_manifest_sha256_matches", stored_manifest.get("parent_evaluation_manifest_sha256") == _sha256_file(evaluation_dir / "manifest.json"), stored_manifest.get("parent_evaluation_manifest_sha256"))
    add("parent_summary_sha256_matches", stored_manifest.get("parent_evaluation_summary_sha256") == _sha256_file(evaluation_dir / "summary.json"), stored_manifest.get("parent_evaluation_summary_sha256"))
    add("parent_case_comparison_sha256_matches", stored_manifest.get("parent_case_comparison_sha256") == _sha256_file(evaluation_dir / "case_comparison.jsonl"), stored_manifest.get("parent_case_comparison_sha256"))
    add("summary_recomputes_exactly", stored_summary == expected_summary, "summary")
    add("margin_sweep_recomputes_exactly", stored_sweep == recomputed_sweep, "margin_sweep")
    add("transition_breakdown_recomputes_exactly", stored_transition == recomputed_extra["transition_breakdown"], "transition_breakdown")
    add("selected_policy_recomputes_exactly", stored_policy == recomputed_extra["selected_policy"], "selected_policy")
    add("policy_case_outcomes_recompute_exactly", stored_outcomes == recomputed_outcomes, len(stored_outcomes))
    add("new_model_inference_not_executed", stored_manifest.get("new_model_inference_executed") is False, stored_manifest.get("new_model_inference_executed"))
    add("independent_acceptance_not_executed", stored_manifest.get("independent_acceptance_executed") is False, stored_manifest.get("independent_acceptance_executed"))
    add("production_not_selected", stored_manifest.get("production_extractor_selected") is False, stored_manifest.get("production_extractor_selected"))
    add("full_corpus_not_authorized", stored_manifest.get("full_corpus_build_authorized") is False, stored_manifest.get("full_corpus_build_authorized"))

    checksum_lines = [line.strip() for line in (analysis_dir / "checksums.txt").read_text(encoding="utf-8").splitlines() if line.strip()]
    parsed_checksums = {}
    for line in checksum_lines:
        digest, name = line.split("  ", 1)
        parsed_checksums[name] = digest
    for name in REQUIRED_OUTPUT_FILES:
        if name == "checksums.txt":
            continue
        add(f"checksum:{name}", parsed_checksums.get(name) == _sha256_file(analysis_dir / name), name)

    failed = sum(not item[1] for item in checks)
    selected = stored_policy.get("status") == "selected"
    summary = {
        "report": REPORT_NAME,
        "validation_scope": "revision_analysis",
        "analysis_id": analysis_id,
        "policy_selected": selected,
        "selected_threshold": stored_policy.get("threshold"),
        "total_checks": len(checks),
        "required_failed_count": failed,
        "next_slice": stored_summary.get("next_slice") if failed == 0 else "fix_revision_analysis_validation_failures",
    }
    return checks, summary


__all__ = [
    "REPORT_NAME",
    "ScientificEntitySemanticTyperRevisionAnalysisError",
    "analyze_revision",
    "plan_or_execute_semantic_typer_revision_analysis",
    "validate_semantic_typer_revision_analysis",
]
