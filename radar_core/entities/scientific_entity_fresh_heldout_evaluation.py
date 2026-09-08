from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from radar_core.contracts.scientific_entity_evaluation import (
    ScientificEntityEvaluationErrorKind,
    ScientificEntityEvaluationManifest,
    ScientificEntityEvaluationMetrics,
)
from radar_core.contracts.scientific_entity_fresh_heldout_evaluation import (
    ScientificEntityFreshHeldoutEvaluationConfig,
    ScientificEntityFreshHeldoutEvaluationError,
    load_scientific_entity_fresh_heldout_evaluation_config,
)
from radar_core.contracts.scientific_entity_fresh_heldout_frozen_policy import (
    FrozenPolicyDerivationManifest,
    load_scientific_entity_fresh_heldout_frozen_policy_config,
)
from radar_core.contracts.scientific_entity_fresh_heldout_gate import (
    canonical_config_sha256 as gate_config_sha256,
    load_scientific_entity_fresh_heldout_gate_config,
)
from radar_core.entities.scientific_entity_evaluation import (
    evaluation_config_sha256,
    load_evaluation_config,
)
from scripts.entities.evaluate_scientific_entity_evidence import evaluate_evidence
from scripts.validation.check_scientific_entity_evaluation import validate_evaluation

REPORT_NAME = "scientific_entity_fresh_heldout_evaluation_v02"


class FreshHeldoutEvaluationBuildError(RuntimeError):
    pass


def _resolve(project_root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = project_root / path
    return path.resolve()


def _semantic_sha(payload: Any) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise FreshHeldoutEvaluationBuildError(f"Expected JSON object: {path}")
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip():
                raise FreshHeldoutEvaluationBuildError(f"Blank JSONL line: {path}:{line_number}")
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise FreshHeldoutEvaluationBuildError(f"Expected JSON object: {path}:{line_number}")
            rows.append(value)
    return rows


def _validate_gate(
    *, project_root: Path, contract: ScientificEntityFreshHeldoutEvaluationConfig
) -> dict[str, Any]:
    path = _resolve(project_root, contract.fresh_heldout.gate_config_path)
    gate = load_scientific_entity_fresh_heldout_gate_config(path)
    sha = gate_config_sha256(gate)
    if sha != contract.fresh_heldout.gate_config_semantic_sha256:
        raise FreshHeldoutEvaluationBuildError("Fresh held-out gate semantic SHA drifted")
    a = gate.acceptance
    snapshot = contract.acceptance_gate_snapshot
    exact = {
        "minimum_exact_f1": a.minimum_exact_f1,
        "desirable_minimum_relaxed_f1": a.desirable_minimum_relaxed_f1,
        "relaxed_f1_is_hard_gate": a.require_relaxed_f1_as_hard_gate,
        "maximum_model_to_method_count": a.maximum_model_to_method_count,
        "maximum_method_to_task_count": a.maximum_method_to_task_count,
        "maximum_total_type_mismatch_count": a.maximum_total_type_mismatch_count,
        "maximum_method_semantic_sink_count": a.maximum_method_semantic_sink_count,
        "maximum_any_predicted_type_mismatch_sink_count": a.maximum_any_predicted_type_mismatch_sink_count,
        "no_post_heldout_tuning": a.no_post_heldout_tuning,
    }
    frozen = snapshot.model_dump(mode="json")
    frozen.pop("decision_made_in_this_slice")
    if exact != frozen:
        raise FreshHeldoutEvaluationBuildError("Acceptance gate snapshot drifted")
    return {"gate_config_sha256": sha, **exact}


def _validate_base_evaluator(
    *, project_root: Path, contract: ScientificEntityFreshHeldoutEvaluationConfig
) -> dict[str, Any]:
    path = _resolve(project_root, contract.base_evaluator.config_path)
    config = load_evaluation_config(path)
    sha = evaluation_config_sha256(config)
    if sha != contract.base_evaluator.config_semantic_sha256:
        raise FreshHeldoutEvaluationBuildError("Base evaluator semantic SHA drifted")
    if config.matching.relaxed_min_char_iou != contract.base_evaluator.relaxed_min_char_iou:
        raise FreshHeldoutEvaluationBuildError("Base evaluator relaxed IoU drifted")
    if config.metrics.decimal_places != contract.base_evaluator.decimal_places:
        raise FreshHeldoutEvaluationBuildError("Base evaluator decimal_places drifted")
    return {"evaluation_config_sha256": sha, "config_path": path}


def _policy_semantic_sha(path: Path) -> str:
    cfg = load_scientific_entity_fresh_heldout_frozen_policy_config(path)
    return _semantic_sha(cfg.model_dump(mode="json"))


def _validate_policy_lineage(
    *,
    project_root: Path,
    contract: ScientificEntityFreshHeldoutEvaluationConfig,
    sample_dir: Path,
    reference_dir: Path,
    development_package_dir: Path,
    canonical_path: Path,
) -> dict[str, Any]:
    from radar_core.entities.scientific_entity_fresh_heldout_frozen_policy import (
        validate_frozen_policy_build,
    )

    policy_config_path = _resolve(project_root, contract.candidate.policy_contract_path)
    if _policy_semantic_sha(policy_config_path) != contract.candidate.policy_contract_semantic_sha256:
        raise FreshHeldoutEvaluationBuildError("Frozen policy contract semantic SHA drifted")
    _, summary = validate_frozen_policy_build(
        project_root=project_root,
        config_path=policy_config_path,
        sample_dir=sample_dir,
        reference_dir=reference_dir,
        development_package_dir=development_package_dir,
        canonical_path=canonical_path,
    )
    required = {
        "required_failed_count": 0,
        "build_id": contract.candidate.policy_build_id,
        "selected_prediction_count": contract.candidate.expected_prediction_count,
        "policy_applied": True,
        "evaluation_executed": False,
        "acceptance_decision_made": False,
    }
    for key, expected in required.items():
        if summary.get(key) != expected:
            raise FreshHeldoutEvaluationBuildError(
                f"Frozen policy lineage mismatch for {key}: {summary.get(key)!r} != {expected!r}"
            )
    policy_contract = load_scientific_entity_fresh_heldout_frozen_policy_config(policy_config_path)
    build_dir = _resolve(project_root, policy_contract.execution.output_root) / policy_contract.execution.build_id
    policy_manifest = _read_json(build_dir / "manifest.json")
    derivation = FrozenPolicyDerivationManifest.model_validate(_read_json(build_dir / "derivation_manifest.json"))
    if policy_manifest.get("extractor_fingerprint") != contract.candidate.expected_policy_extractor_fingerprint:
        raise FreshHeldoutEvaluationBuildError("Frozen policy extractor fingerprint drifted")
    if derivation.selected_prediction_count != contract.candidate.expected_prediction_count:
        raise FreshHeldoutEvaluationBuildError("Frozen policy selected count drifted")
    if derivation.title_threshold != contract.candidate.title_threshold or derivation.abstract_threshold != contract.candidate.abstract_threshold:
        raise FreshHeldoutEvaluationBuildError("Frozen policy thresholds drifted")
    if derivation.entity_type_overrides:
        raise FreshHeldoutEvaluationBuildError("Frozen policy type overrides drifted")
    return {
        "policy_validation_required_failed_count": 0,
        "policy_build_id": policy_contract.execution.build_id,
        "selected_prediction_count": derivation.selected_prediction_count,
        "policy_extractor_fingerprint": policy_manifest["extractor_fingerprint"],
        "policy_dir": build_dir,
    }


def _validate_reference_lineage(
    *,
    project_root: Path,
    contract: ScientificEntityFreshHeldoutEvaluationConfig,
    sample_dir: Path,
    reference_dir: Path,
    development_package_dir: Path,
    canonical_path: Path,
) -> dict[str, Any]:
    from radar_core.entities.scientific_entity_fresh_heldout_reference import (
        validate_frozen_reference_evidence,
    )

    _, summary = validate_frozen_reference_evidence(
        project_root=project_root,
        config_path=_resolve(project_root, "configs/scientific_entity_fresh_heldout_reference_freeze_v0.2.yaml"),
        sample_dir=sample_dir,
        canonical_path=canonical_path,
        development_package_dir=development_package_dir,
        reference_dir=reference_dir,
    )
    required = {
        "required_failed_count": 0,
        "sample_id": contract.fresh_heldout.sample_id,
        "review_id": contract.fresh_heldout.review_id,
        "document_count": contract.fresh_heldout.expected_document_count,
        "reference_mention_count": contract.fresh_heldout.expected_reference_mention_count,
        "reference_adequacy_passed": True,
        "prediction_blind": True,
        "evaluation_executed": False,
    }
    for key, expected in required.items():
        if summary.get(key) != expected:
            raise FreshHeldoutEvaluationBuildError(
                f"Frozen reference lineage mismatch for {key}: {summary.get(key)!r} != {expected!r}"
            )
    return {"reference_validation_required_failed_count": 0, **required}


def semantic_guardrails_from_errors(errors: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    pair_counts: Counter[tuple[str, str]] = Counter()
    predicted_sinks: Counter[str] = Counter()
    for row in errors:
        if row.get("error_kind") != ScientificEntityEvaluationErrorKind.TYPE_MISMATCH.value:
            continue
        ref = str(row.get("reference_entity_type"))
        pred = str(row.get("prediction_entity_type"))
        pair_counts[(ref, pred)] += 1
        predicted_sinks[pred] += 1
    total = sum(pair_counts.values())
    max_sink_type = None
    max_sink_count = 0
    if predicted_sinks:
        max_sink_type, max_sink_count = sorted(
            predicted_sinks.items(), key=lambda item: (-item[1], item[0])
        )[0]
    return {
        "model_to_method_count": pair_counts.get(("model", "method"), 0),
        "method_to_task_count": pair_counts.get(("method", "task"), 0),
        "total_type_mismatch_count": total,
        "method_semantic_sink_count": predicted_sinks.get("method", 0),
        "maximum_predicted_type_mismatch_sink_type": max_sink_type,
        "maximum_any_predicted_type_mismatch_sink_count": max_sink_count,
        "predicted_type_mismatch_sinks": dict(sorted(predicted_sinks.items())),
    }


def _evaluation_summary(evaluation_dir: Path) -> dict[str, Any]:
    manifest = ScientificEntityEvaluationManifest.model_validate(_read_json(evaluation_dir / "manifest.json"))
    metrics = ScientificEntityEvaluationMetrics.model_validate(_read_json(evaluation_dir / "metrics.json"))
    errors = _read_jsonl(evaluation_dir / "errors.jsonl")
    guardrails = semantic_guardrails_from_errors(errors)
    return {
        "evaluation_id": manifest.evaluation_id,
        "document_count": metrics.document_count,
        "reference_mention_count": metrics.reference_mention_count,
        "prediction_mention_count": metrics.prediction_mention_count,
        "exact_precision": metrics.micro.exact.precision,
        "exact_recall": metrics.micro.exact.recall,
        "exact_f1": metrics.micro.exact.f1,
        "relaxed_precision": metrics.micro.relaxed.precision,
        "relaxed_recall": metrics.micro.relaxed.recall,
        "relaxed_f1": metrics.micro.relaxed.f1,
        "exact_match_count": metrics.exact_match_count,
        "relaxed_only_match_count": metrics.relaxed_only_match_count,
        **guardrails,
    }


def plan_or_execute_fresh_heldout_evaluation(
    *,
    project_root: Path,
    config_path: Path,
    sample_dir: Path,
    reference_dir: Path,
    development_package_dir: Path,
    canonical_path: Path,
    execute: bool = False,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    contract = load_scientific_entity_fresh_heldout_evaluation_config(config_path.resolve())
    gate = _validate_gate(project_root=project_root, contract=contract)
    evaluator = _validate_base_evaluator(project_root=project_root, contract=contract)
    reference = _validate_reference_lineage(
        project_root=project_root,
        contract=contract,
        sample_dir=sample_dir.resolve(),
        reference_dir=reference_dir.resolve(),
        development_package_dir=development_package_dir.resolve(),
        canonical_path=canonical_path.resolve(),
    )
    policy = _validate_policy_lineage(
        project_root=project_root,
        contract=contract,
        sample_dir=sample_dir.resolve(),
        reference_dir=reference_dir.resolve(),
        development_package_dir=development_package_dir.resolve(),
        canonical_path=canonical_path.resolve(),
    )
    output_dir = _resolve(project_root, contract.execution.output_root) / contract.execution.evaluation_id
    already_executed = output_dir.exists()
    if execute and already_executed:
        raise FileExistsError(f"Fresh held-out evaluation is one-shot and already exists: {output_dir}")

    report: dict[str, Any] = {
        "report": REPORT_NAME,
        "mode": "execute" if execute else "plan",
        "phase_complete": False,
        "candidate_id": contract.candidate.candidate_id,
        "sample_id": contract.fresh_heldout.sample_id,
        "review_id": contract.fresh_heldout.review_id,
        "document_count": contract.fresh_heldout.expected_document_count,
        "reference_mention_count": contract.fresh_heldout.expected_reference_mention_count,
        "policy_build_id": policy["policy_build_id"],
        "prediction_mention_count": policy["selected_prediction_count"],
        "policy_extractor_fingerprint": policy["policy_extractor_fingerprint"],
        "policy_validation_required_failed_count": policy["policy_validation_required_failed_count"],
        "reference_validation_required_failed_count": reference["reference_validation_required_failed_count"],
        "gate_config_sha256": gate["gate_config_sha256"],
        "evaluation_config_sha256": evaluator["evaluation_config_sha256"],
        "evaluation_id": contract.execution.evaluation_id,
        "output_dir": str(output_dir).replace("\\", "/"),
        "one_shot_already_executed": already_executed,
        "plan_runs_evaluation": False,
        "model_inference_executed": False,
        "threshold_tuning_executed": False,
        "reference_labels_used_for_evaluation": True,
        "reference_labels_used_for_filtering": False,
        "evaluation_executed": False,
        "acceptance_decision_made": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "next_slice": contract.next_steps.after_plan,
    }
    if not execute:
        return report

    sample_documents = sample_dir.resolve() / contract.fresh_heldout.sample_documents_file
    review_manifest = reference_dir.resolve() / contract.fresh_heldout.reference_review_manifest_file
    references = reference_dir.resolve() / contract.fresh_heldout.reference_mentions_file
    policy_dir = Path(policy["policy_dir"])
    base_report = evaluate_evidence(
        config_path=Path(evaluator["config_path"]),
        documents_path=sample_documents,
        review_manifest_path=review_manifest,
        reference_mentions_path=references,
        prediction_manifest_path=policy_dir / "manifest.json",
        prediction_mentions_path=policy_dir / "mentions.jsonl",
        output_root=_resolve(project_root, contract.execution.output_root),
        evaluation_id=contract.execution.evaluation_id,
        status=contract.execution.status,
        max_documents=contract.execution.max_documents,
        execute=True,
    )
    if not base_report.get("phase_complete"):
        raise FreshHeldoutEvaluationBuildError("Base evaluator did not complete")
    validation = validate_evaluation(
        evaluation_dir=output_dir,
        config_path=Path(evaluator["config_path"]),
        write_reports=False,
    )
    if validation.get("required_failed_count") != 0:
        raise FreshHeldoutEvaluationBuildError(
            f"Base evaluation strict validation failed: {validation.get('required_failed_count')}"
        )
    metrics = _evaluation_summary(output_dir)
    report.update(metrics)
    report.update({
        "phase_complete": True,
        "one_shot_already_executed": True,
        "evaluation_executed": True,
        "base_evaluation_validation_total_checks": validation["summary"]["total_checks"],
        "base_evaluation_validation_required_failed_count": 0,
        "next_slice": contract.next_steps.after_execute,
    })
    return report


def validate_fresh_heldout_evaluation(
    *,
    project_root: Path,
    config_path: Path,
    sample_dir: Path,
    reference_dir: Path,
    development_package_dir: Path,
    canonical_path: Path,
) -> tuple[list[tuple[str, bool, str]], dict[str, Any]]:
    project_root = project_root.resolve()
    contract = load_scientific_entity_fresh_heldout_evaluation_config(config_path.resolve())
    gate = _validate_gate(project_root=project_root, contract=contract)
    evaluator = _validate_base_evaluator(project_root=project_root, contract=contract)
    reference = _validate_reference_lineage(
        project_root=project_root,
        contract=contract,
        sample_dir=sample_dir.resolve(),
        reference_dir=reference_dir.resolve(),
        development_package_dir=development_package_dir.resolve(),
        canonical_path=canonical_path.resolve(),
    )
    policy = _validate_policy_lineage(
        project_root=project_root,
        contract=contract,
        sample_dir=sample_dir.resolve(),
        reference_dir=reference_dir.resolve(),
        development_package_dir=development_package_dir.resolve(),
        canonical_path=canonical_path.resolve(),
    )
    output_dir = _resolve(project_root, contract.execution.output_root) / contract.execution.evaluation_id
    checks: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: Any = "") -> None:
        checks.append((name, bool(ok), str(detail)))

    add("reference_validation_passed", reference["reference_validation_required_failed_count"] == 0, reference["reference_validation_required_failed_count"])
    add("policy_validation_passed", policy["policy_validation_required_failed_count"] == 0, policy["policy_validation_required_failed_count"])
    add("output_directory_exists", output_dir.is_dir(), output_dir)
    if not output_dir.is_dir():
        return checks, _validation_summary(checks, contract, gate, reference, policy, None, None)

    base_validation = validate_evaluation(
        evaluation_dir=output_dir,
        config_path=Path(evaluator["config_path"]),
        write_reports=False,
    )
    add("base_evaluation_validation_passed", base_validation["required_failed_count"] == 0, base_validation["required_failed_count"])
    manifest = ScientificEntityEvaluationManifest.model_validate(_read_json(output_dir / "manifest.json"))
    metrics = ScientificEntityEvaluationMetrics.model_validate(_read_json(output_dir / "metrics.json"))
    semantic = semantic_guardrails_from_errors(_read_jsonl(output_dir / "errors.jsonl"))

    add("evaluation_id_exact", manifest.evaluation_id == contract.execution.evaluation_id, manifest.evaluation_id)
    add("evaluation_status_candidate", manifest.status.value == "candidate", manifest.status.value)
    add("sample_document_count_exact", metrics.document_count == 48, metrics.document_count)
    add("reference_count_exact", metrics.reference_mention_count == 944, metrics.reference_mention_count)
    add("prediction_count_exact", metrics.prediction_mention_count == 773, metrics.prediction_mention_count)
    add("review_id_exact", manifest.review.review_id == contract.fresh_heldout.review_id, manifest.review.review_id)
    add("policy_build_id_exact", manifest.prediction.build_id == contract.candidate.policy_build_id, manifest.prediction.build_id)
    add("policy_fingerprint_exact", manifest.prediction.extractor_fingerprint == contract.candidate.expected_policy_extractor_fingerprint, manifest.prediction.extractor_fingerprint)
    add("gate_sha_exact", gate["gate_config_sha256"] == contract.fresh_heldout.gate_config_semantic_sha256, gate["gate_config_sha256"])
    add("metrics_available", metrics.micro.exact.f1 is not None and metrics.micro.relaxed.f1 is not None, "")
    add("model_inference_not_run", manifest.model_downloaded is False and manifest.provider_api_called is False, "")
    add("canonical_truth_not_mutated", manifest.canonical_truth_mutated is False, "")
    add("production_not_selected", manifest.production_extractor_selected is False, "")
    add("full_corpus_not_authorized", manifest.full_corpus_build_authorized is False, "")
    add("acceptance_decision_not_made", contract.safety.acceptance_decision_in_this_slice is False, "")

    summary_metrics = {
        "exact_precision": metrics.micro.exact.precision,
        "exact_recall": metrics.micro.exact.recall,
        "exact_f1": metrics.micro.exact.f1,
        "relaxed_precision": metrics.micro.relaxed.precision,
        "relaxed_recall": metrics.micro.relaxed.recall,
        "relaxed_f1": metrics.micro.relaxed.f1,
        **semantic,
    }
    return checks, _validation_summary(
        checks, contract, gate, reference, policy, base_validation, summary_metrics
    )


def _validation_summary(
    checks: Sequence[tuple[str, bool, str]],
    contract: ScientificEntityFreshHeldoutEvaluationConfig,
    gate: Mapping[str, Any],
    reference: Mapping[str, Any],
    policy: Mapping[str, Any],
    base_validation: Mapping[str, Any] | None,
    metrics: Mapping[str, Any] | None,
) -> dict[str, Any]:
    failed = [name for name, ok, _ in checks if not ok]
    result: dict[str, Any] = {
        "report": REPORT_NAME,
        "candidate_id": contract.candidate.candidate_id,
        "sample_id": contract.fresh_heldout.sample_id,
        "review_id": contract.fresh_heldout.review_id,
        "evaluation_id": contract.execution.evaluation_id,
        "document_count": contract.fresh_heldout.expected_document_count,
        "reference_mention_count": contract.fresh_heldout.expected_reference_mention_count,
        "prediction_mention_count": contract.candidate.expected_prediction_count,
        "reference_validation_required_failed_count": reference.get("reference_validation_required_failed_count"),
        "policy_validation_required_failed_count": policy.get("policy_validation_required_failed_count"),
        "base_evaluation_validation_required_failed_count": None if base_validation is None else base_validation.get("required_failed_count"),
        "evaluation_executed": metrics is not None,
        "acceptance_decision_made": False,
        "threshold_tuning_executed": False,
        "model_inference_executed": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "total_checks": len(checks),
        "required_failed_count": len(failed),
        "next_slice": contract.next_steps.after_validation,
    }
    if metrics is not None:
        result.update(metrics)
    return result
