"""Immutable, one-shot H2 independent acceptance decision from frozen evidence.

The decision is deliberately separate from model inference and comparative evaluation.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping

from radar_core.contracts.scientific_entity_semantic_typer_h2_independent_acceptance_decision import (
    H2GateCheck,
    H2IndependentDecisionConfig,
    H2IndependentDecisionError,
    H2IndependentDecisionManifest,
    H2IndependentDecisionRecord,
    canonical_config_sha256,
    load_h2_independent_decision_config,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_independent_acceptance_gate import (
    canonical_config_sha256 as gate_config_sha256,
    load_h2_independent_acceptance_gate_config,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_independent_evaluation import (
    H2IndependentEvaluationManifest,
    H2IndependentEvaluationSummary,
    canonical_config_sha256 as evaluation_config_sha256,
    load_h2_independent_evaluation_config,
)
from radar_core.entities.scientific_entity_semantic_typer_h2_independent_evaluation import (
    DEFAULT_CANONICAL,
    validate_h2_independent_evaluation,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "scientific_entity_semantic_typer_h2_independent_acceptance_decision_v0.3.yaml"
REPORT_NAME = "scientific_entity_semantic_typer_h2_independent_acceptance_decision_v03"
REQUIRED_FILES = {"manifest.json", "decision.json", "historical_diagnostics.json", "README.md", "checksums.txt"}
CHECKSUM_FILES = REQUIRED_FILES - {"checksums.txt"}


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return (root / path if not path.is_absolute() else path).resolve()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise H2IndependentDecisionError(f"Expected JSON object: {path}")
    return payload


def _json_bytes(data: Any) -> bytes:
    payload = data.model_dump(mode="json") if hasattr(data, "model_dump") else data
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _checksums(payloads: Mapping[str, bytes]) -> bytes:
    return "".join(
        f"{hashlib.sha256(payloads[name]).hexdigest()}  {name}\n"
        for name in sorted(payloads) if name != "checksums.txt"
    ).encode("utf-8")


def _write_immutable(output_dir: Path, payloads: Mapping[str, bytes]) -> None:
    if output_dir.exists():
        raise FileExistsError(f"Immutable H2 decision already exists: {output_dir}")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.tmp-", dir=output_dir.parent))
    try:
        for name, data in payloads.items():
            (staging / name).write_bytes(data)
        staging.rename(output_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _lf_ok(path: Path) -> bool:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf") or b"\r" in raw:
        return False
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return not raw or raw.endswith(b"\n")


def _validate_frozen_state(
    *, project_root: Path, config_path: Path, evaluation_dir: Path,
    inference_dir: Path, sample_dir: Path, reference_dir: Path,
    development_package_dir: Path, previous_heldout_sample_dir: Path,
    frozen_candidate_dir: Path, canonical_path: Path,
) -> dict[str, Any]:
    root = project_root.resolve()
    config = load_h2_independent_decision_config(config_path.resolve())
    gate_path = _resolve(root, config.frozen_inputs.gate_config_path)
    gate = load_h2_independent_acceptance_gate_config(gate_path)
    gate_sha = gate_config_sha256(gate)
    if gate_sha != config.frozen_inputs.gate_config_sha256:
        raise H2IndependentDecisionError("Frozen acceptance-gate semantic SHA drifted")

    evaluation_config_path = _resolve(root, config.frozen_inputs.evaluation_config_path)
    evaluation_config = load_h2_independent_evaluation_config(evaluation_config_path)
    eval_sha = evaluation_config_sha256(evaluation_config)
    if any((
        evaluation_config.execution.evaluation_id != config.candidate.evaluation_id,
        evaluation_config.candidate.candidate_id != config.candidate.candidate_id,
        evaluation_config.candidate.candidate_fingerprint_sha256 != config.candidate.candidate_fingerprint_sha256,
        evaluation_config.acceptance_gate.config_sha256 != gate_sha,
        evaluation_config.inference.inference_id != config.candidate.inference_id,
        evaluation_config.fresh_heldout.sample_id != config.candidate.sample_id,
        evaluation_config.fresh_heldout.review_id != config.candidate.review_id,
        gate.candidate_lineage.candidate_id != config.candidate.candidate_id,
        gate.candidate_lineage.candidate_fingerprint_sha256 != config.candidate.candidate_fingerprint_sha256,
        gate.fresh_heldout_lineage.sample_id != config.candidate.sample_id,
        gate.fresh_heldout_lineage.review_id != config.candidate.review_id,
    )):
        raise H2IndependentDecisionError("Candidate or held-out lineage does not match frozen gate")

    # This validator performs independent recomputation of the entire Slice 6 package
    # and recursively checks inference, human-reference freeze and candidate lineage.
    checks, validation = validate_h2_independent_evaluation(
        project_root=root,
        config_path=evaluation_config_path,
        sample_dir=sample_dir.resolve(),
        reference_dir=reference_dir.resolve(),
        development_package_dir=development_package_dir.resolve(),
        previous_heldout_sample_dir=previous_heldout_sample_dir.resolve(),
        frozen_candidate_dir=frozen_candidate_dir.resolve(),
        canonical_path=canonical_path.resolve(),
        inference_dir=inference_dir.resolve(),
        evaluation_dir=evaluation_dir.resolve(),
    )
    if validation.get("required_failed_count") != 0 or any(not row[1] for row in checks):
        raise H2IndependentDecisionError("Upstream independent evaluation strict validation failed")
    if validation.get("next_slice") != "make_immutable_h2_independent_acceptance_decision":
        raise H2IndependentDecisionError("Upstream evaluation validation next_slice mismatch")

    manifest_path = evaluation_dir / "manifest.json"
    summary_path = evaluation_dir / "comparative_summary.json"
    manifest = H2IndependentEvaluationManifest.model_validate(_read_json(manifest_path))
    summary = H2IndependentEvaluationSummary.model_validate(_read_json(summary_path))
    if any((
        manifest.evaluation_id != config.candidate.evaluation_id,
        summary.evaluation_id != config.candidate.evaluation_id,
        manifest.inference_id != config.candidate.inference_id,
        summary.inference_id != config.candidate.inference_id,
        manifest.candidate_fingerprint_sha256 != config.candidate.candidate_fingerprint_sha256,
        manifest.acceptance_gate_config_sha256 != gate_sha,
        manifest.evaluation_config_sha256 != eval_sha,
        manifest.sample_id != config.candidate.sample_id,
        manifest.review_id != config.candidate.review_id,
        manifest.document_count != config.frozen_inputs.expected_evaluation_document_count,
        manifest.reference_mention_count != config.frozen_inputs.expected_reference_mention_count,
        manifest.baseline_prediction_count != config.frozen_inputs.expected_baseline_prediction_count,
        manifest.h2_prediction_count != config.frozen_inputs.expected_h2_prediction_count,
        not summary.required_metric_denominators_present,
    )):
        raise H2IndependentDecisionError("Frozen independent evaluation inputs drifted")

    # Human adequacy is an explicit hard gate, not an inference from positive F1.
    completion_path = reference_dir / "completion_manifest.json"
    reference_completion = _read_json(completion_path)
    if (reference_completion.get("reference_adequacy_passed") is not True
            or reference_completion.get("reference_frozen") is not True):
        raise H2IndependentDecisionError("Human reference adequacy / freeze is missing")

    return {
        "config": config, "gate": gate, "gate_sha": gate_sha,
        "evaluation_config_sha": eval_sha, "manifest": manifest, "summary": summary,
        "reference_adequacy_passed": True,
        "evaluation_strict_validation_passed": True,
        "evaluation_validation_total_checks": validation.get("total_checks"),
        "evaluation_manifest_sha": _sha(manifest_path),
        "evaluation_summary_sha": _sha(summary_path),
        "reference_completion_sha": _sha(completion_path),
    }


def _require_denominators(summary: H2IndependentEvaluationSummary) -> None:
    if (
        summary.required_metric_denominators_present is not True
        or summary.same_span_pair_count <= 0
        or summary.baseline_typing.correct_count <= 0
        or summary.baseline_model_to_method_count <= 0
        or any(row.reference_support <= 0 for row in summary.baseline_typing.per_type)
        or any(row.reference_support <= 0 for row in summary.h2_typing.per_type)
        or summary.baseline_typing.accuracy is None
        or summary.h2_typing.accuracy is None
        or summary.baseline_typing.macro_f1 is None
        or summary.h2_typing.macro_f1 is None
        or summary.h2_extraction.exact_f1 is None
    ):
        raise H2IndependentDecisionError("Insufficient required comparative denominator: fail closed")


def build_decision_record(
    *, config: H2IndependentDecisionConfig, gate: Any,
    summary: H2IndependentEvaluationSummary,
    reference_adequacy_passed: bool, fingerprint_matches: bool,
    strict_validation_passed: bool,
) -> H2IndependentDecisionRecord:
    if not strict_validation_passed:
        raise H2IndependentDecisionError("Cannot decide without independent strict validation")
    if gate.comparative_acceptance.required_metric_missing_denominator_policy != "fail_closed_evidence_insufficient":
        raise H2IndependentDecisionError("Missing-denominator policy drifted")
    _require_denominators(summary)
    comparative = gate.comparative_acceptance

    entries = (
        ("reference_adequacy", "==", bool(reference_adequacy_passed), True),
        ("candidate_fingerprint", "==", bool(fingerprint_matches), True),
        ("minimum_typer_coverage", ">=", summary.typer_coverage, comparative.minimum_typer_coverage),
        ("minimum_same_span_accuracy_delta", ">=", summary.same_span_accuracy_delta, comparative.minimum_same_span_accuracy_delta),
        ("minimum_net_corrected_cases", ">=", summary.net_corrected_cases, comparative.minimum_net_corrected_cases),
        ("maximum_regression_rate", "<=", summary.regression_rate, comparative.maximum_regression_rate),
        ("minimum_model_to_method_reduction_fraction", ">=", summary.model_to_method_reduction_fraction, comparative.minimum_model_to_method_reduction_fraction),
        ("minimum_macro_f1_delta", ">=", summary.macro_f1_delta, comparative.minimum_macro_f1_delta),
        ("minimum_exact_f1", ">=", summary.h2_extraction.exact_f1, comparative.minimum_exact_f1),
    )
    checks: list[H2GateCheck] = []
    for name, op, actual, threshold in entries:
        if actual is None:
            raise H2IndependentDecisionError(f"Missing required gate value: {name}")
        if type(actual) not in (float, int, bool) or type(threshold) not in (float, int, bool):
            raise H2IndependentDecisionError(f"Unsupported gate value: {name}")
        ok = (actual >= threshold if op == ">=" else actual <= threshold if op == "<=" else actual == threshold)
        checks.append(H2GateCheck(name=name, operator=op, actual=actual, threshold=threshold, passed=ok))

    all_hard_passed = all(item.passed for item in checks)
    semantics = gate.decision_semantics
    decision = (
        semantics.if_all_hard_gates_pass
        if all_hard_passed else semantics.if_any_hard_gate_fails
    )
    desirable_actual = summary.h2_extraction.relaxed_f1
    return H2IndependentDecisionRecord(
        decision_id=config.execution.decision_id,
        evaluation_id=config.candidate.evaluation_id,
        candidate_id=config.candidate.candidate_id,
        candidate_fingerprint_sha256=config.candidate.candidate_fingerprint_sha256,
        gate_config_sha256=config.frozen_inputs.gate_config_sha256,
        reference_adequacy_passed=reference_adequacy_passed,
        strictly_validated_evaluation=True,
        required_metric_denominators_present=True,
        hard_gates=checks,
        all_hard_gates_passed=all_hard_passed,
        decision=decision,
        desirable_relaxed_f1_threshold=comparative.desirable_minimum_relaxed_f1,
        desirable_relaxed_f1_actual=desirable_actual,
        desirable_relaxed_f1_met=(
            None if desirable_actual is None else
            desirable_actual >= comparative.desirable_minimum_relaxed_f1
        ),
        future_candidate_after_failure_requires_new_independent_heldout=True,
    )


def _historical_diagnostics(summary: H2IndependentEvaluationSummary, gate: Any) -> dict[str, Any]:
    historic = gate.historical_diagnostics
    baseline = summary.baseline_extraction
    candidate = summary.h2_extraction
    rows = (
        ("model_to_method", baseline.model_to_method_count, candidate.model_to_method_count, historic.historical_maximum_model_to_method_count),
        ("method_to_task", baseline.method_to_task_count, candidate.method_to_task_count, historic.historical_maximum_method_to_task_count),
        ("total_type_mismatch", baseline.total_type_mismatch_count, candidate.total_type_mismatch_count, historic.historical_maximum_total_type_mismatch_count),
        ("method_semantic_sink", baseline.method_semantic_sink_count, candidate.method_semantic_sink_count, historic.historical_maximum_method_semantic_sink_count),
        ("maximum_predicted_type_mismatch_sink", baseline.maximum_any_predicted_type_mismatch_sink_count, candidate.maximum_any_predicted_type_mismatch_sink_count, historic.historical_maximum_any_predicted_type_mismatch_sink_count),
    )
    return {
        "historical_raw_count_caps_are_hard_h2_gates": False,
        "not_comparable_as_acceptance_gates_across_disjoint_samples": True,
        "diagnostics": [
            {"name": name, "baseline": old, "h2": new, "historical_v02c_cap": cap}
            for name, old, new, cap in rows
        ],
        "model_to_method_direct_corrections": summary.model_to_method_direct_corrections,
        "model_to_method_wrong_to_wrong": summary.model_to_method_wrong_to_wrong,
        "corrected_errors": summary.corrected_errors,
        "introduced_regressions": summary.introduced_regressions,
    }


def _readme() -> bytes:
    return (
        "# H2 v0.3 independent immutable acceptance decision\n\n"
        "This package records the preregistered decision for the frozen H2 candidate\n"
        "after successful independent evaluation and read-only strict validation.\n\n"
        "All hard gates originate from the previously frozen gate configuration.\n"
        "The desirable relaxed F1 is NOT a hard gate. Historical v0.2c raw count\n"
        "caps are NOT gates on this disjoint v0.3 held-out.\n\n"
        "This decision is restricted to the bounded semantic typing intervention.\n"
        "No production extractor is selected; no full-corpus build is authorized.\n"
        "No inference, tuning, policy revision, canonical mutation or publication.\n"
    ).encode("utf-8")


def _expected_payloads(parent: Mapping[str, Any]) -> dict[str, bytes]:
    config = parent["config"]
    summary = parent["summary"]
    record = build_decision_record(
        config=config, gate=parent["gate"], summary=summary,
        reference_adequacy_passed=parent["reference_adequacy_passed"],
        fingerprint_matches=(parent["manifest"].candidate_fingerprint_sha256 == config.candidate.candidate_fingerprint_sha256),
        strict_validation_passed=parent["evaluation_strict_validation_passed"],
    )
    diagnostics = _historical_diagnostics(summary, parent["gate"])
    payloads: dict[str, bytes] = {
        "decision.json": _json_bytes(record),
        "historical_diagnostics.json": _json_bytes(diagnostics),
        "README.md": _readme(),
    }
    manifest = H2IndependentDecisionManifest(
        decision_id=config.execution.decision_id,
        candidate_id=config.candidate.candidate_id,
        candidate_fingerprint_sha256=config.candidate.candidate_fingerprint_sha256,
        evaluation_id=config.candidate.evaluation_id,
        sample_id=config.candidate.sample_id,
        review_id=config.candidate.review_id,
        decision_config_sha256=canonical_config_sha256(config),
        gate_config_sha256=parent["gate_sha"],
        evaluation_config_sha256=parent["evaluation_config_sha"],
        evaluation_manifest_sha256=parent["evaluation_manifest_sha"],
        evaluation_summary_sha256=parent["evaluation_summary_sha"],
        reference_completion_manifest_sha256=parent["reference_completion_sha"],
        files={key: hashlib.sha256(value).hexdigest() for key, value in payloads.items()},
        next_slice="validate_immutable_h2_independent_acceptance_decision",
    )
    payloads["manifest.json"] = _json_bytes(manifest)
    payloads["checksums.txt"] = _checksums(payloads)
    return payloads


def plan_or_execute_h2_independent_acceptance_decision(
    *, project_root: Path, config_path: Path, evaluation_dir: Path,
    inference_dir: Path, sample_dir: Path, reference_dir: Path,
    development_package_dir: Path, previous_heldout_sample_dir: Path,
    frozen_candidate_dir: Path, canonical_path: Path,
    execute: bool = False,
) -> dict[str, Any]:
    parent = _validate_frozen_state(
        project_root=project_root, config_path=config_path, evaluation_dir=evaluation_dir,
        inference_dir=inference_dir, sample_dir=sample_dir, reference_dir=reference_dir,
        development_package_dir=development_package_dir,
        previous_heldout_sample_dir=previous_heldout_sample_dir,
        frozen_candidate_dir=frozen_candidate_dir, canonical_path=canonical_path,
    )
    config = parent["config"]
    output_dir = _resolve(project_root.resolve(), config.execution.output_root) / config.execution.decision_id
    existed = output_dir.exists()
    if execute and existed:
        raise FileExistsError(f"One-shot H2 decision already exists: {output_dir}")
    report = {
        "report": REPORT_NAME, "mode": "execute" if execute else "plan",
        "phase_complete": False,
        "candidate_id": config.candidate.candidate_id,
        "candidate_fingerprint_sha256": config.candidate.candidate_fingerprint_sha256,
        "evaluation_id": config.candidate.evaluation_id,
        "decision_id": config.execution.decision_id,
        "gate_config_sha256": parent["gate_sha"],
        "evaluation_strict_validation_required_failed_count": 0,
        "evaluation_validation_total_checks": parent["evaluation_validation_total_checks"],
        "reference_adequacy_passed": True,
        "one_shot_already_executed": existed,
        "plan_makes_decision": False,
        "plan_exposes_quality_metrics": False,
        "decision_made": False,
        "model_inference_executed_in_this_slice": False,
        "evaluation_executed_in_this_slice": False,
        "threshold_tuning_executed": False,
        "policy_revision_executed": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "output_dir": str(output_dir).replace("\\", "/"),
        "next_slice": config.next_steps.after_plan,
    }
    if not execute:
        return report

    payloads = _expected_payloads(parent)
    _write_immutable(output_dir, payloads)
    record = H2IndependentDecisionRecord.model_validate(json.loads(payloads["decision.json"]))
    report.update({
        "phase_complete": True,
        "one_shot_already_executed": True,
        "decision_made": True,
        "decision": record.decision,
        "all_hard_gates_passed": record.all_hard_gates_passed,
        "hard_gate_count": len(record.hard_gates),
        "hard_gate_failed_count": sum(not row.passed for row in record.hard_gates),
        "desirable_relaxed_f1_met": record.desirable_relaxed_f1_met,
        "next_slice": config.next_steps.after_execute,
    })
    return report


def validate_h2_independent_acceptance_decision(
    *, project_root: Path, config_path: Path, decision_dir: Path,
    evaluation_dir: Path, inference_dir: Path, sample_dir: Path,
    reference_dir: Path, development_package_dir: Path,
    previous_heldout_sample_dir: Path, frozen_candidate_dir: Path,
    canonical_path: Path,
) -> tuple[list[tuple[str, bool, str]], dict[str, Any]]:
    checks: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: Any = "") -> None:
        checks.append((name, bool(ok), str(detail)))

    config = load_h2_independent_decision_config(config_path)
    decision_dir = decision_dir.resolve()
    add("decision_directory_exists", decision_dir.is_dir(), decision_dir)
    if not decision_dir.is_dir():
        return checks, {"report": REPORT_NAME, "total_checks": len(checks), "required_failed_count": 1}
    add("decision_id_matches_directory", decision_dir.name == config.execution.decision_id)
    actual = {p.name for p in decision_dir.iterdir() if p.is_file()}
    add("exact_file_layout", actual == REQUIRED_FILES, sorted(actual))
    for name in sorted(REQUIRED_FILES):
        add(f"utf8_lf:{name}", (decision_dir / name).is_file() and _lf_ok(decision_dir / name), name)

    try:
        raw_checksums = (decision_dir / "checksums.txt").read_text(encoding="utf-8").splitlines()
        parsed = {}
        for line in raw_checksums:
            digest, filename = line.split("  ", 1)
            if filename in parsed or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("Invalid checksums.txt")
            parsed[filename] = digest
        add("checksum_set_exact", set(parsed) == CHECKSUM_FILES)
        for name in sorted(CHECKSUM_FILES):
            add(f"checksum:{name}", (decision_dir / name).is_file() and parsed.get(name) == _sha(decision_dir / name))
    except Exception as exc:
        add("checksums_parse", False, exc)

    parent = _validate_frozen_state(
        project_root=project_root, config_path=config_path,
        evaluation_dir=evaluation_dir, inference_dir=inference_dir,
        sample_dir=sample_dir, reference_dir=reference_dir,
        development_package_dir=development_package_dir,
        previous_heldout_sample_dir=previous_heldout_sample_dir,
        frozen_candidate_dir=frozen_candidate_dir, canonical_path=canonical_path,
    )
    expected = _expected_payloads(parent)
    for name in sorted(REQUIRED_FILES):
        path = decision_dir / name
        add(f"independently_recomputed:{name}", path.is_file() and path.read_bytes() == expected[name])
    try:
        manifest = H2IndependentDecisionManifest.model_validate(_read_json(decision_dir / "manifest.json"))
        decision = H2IndependentDecisionRecord.model_validate(_read_json(decision_dir / "decision.json"))
        add("manifest_schema_valid", True)
        add("decision_schema_valid", True)
        add("manifest_matches_decision_id", manifest.decision_id == decision.decision_id == config.execution.decision_id)
        add("manifest_freezes_evaluation", manifest.evaluation_id == config.candidate.evaluation_id)
        add("gate_binding", manifest.gate_config_sha256 == config.frozen_inputs.gate_config_sha256 == decision.gate_config_sha256)
        add("no_production_authorization", all((not manifest.production_extractor_selected, not manifest.full_corpus_build_authorized, not decision.production_extractor_selected, not decision.full_corpus_build_authorized)))
    except Exception as exc:
        add("manifest_or_decision_schema_valid", False, exc)
    failed = sum(not ok for _, ok, _ in checks)
    return checks, {
        "report": REPORT_NAME,
        "decision_id": config.execution.decision_id,
        "evaluation_id": config.candidate.evaluation_id,
        "decision_made": failed == 0,
        "total_checks": len(checks),
        "required_failed_count": failed,
        "next_slice": config.next_steps.after_validation if failed == 0 else None,
    }
