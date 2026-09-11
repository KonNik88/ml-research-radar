from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from radar_core.contracts.scientific_entity_fresh_heldout_acceptance_decision import (
    AcceptanceCriterion,
    AcceptanceDecisionManifest,
    AcceptanceDecisionResult,
    ScientificEntityFreshHeldoutAcceptanceDecisionConfig,
    canonical_config_sha256 as decision_config_sha256,
    load_scientific_entity_fresh_heldout_acceptance_decision_config,
)
from radar_core.contracts.scientific_entity_fresh_heldout_evaluation import (
    load_scientific_entity_fresh_heldout_evaluation_config,
)
from radar_core.contracts.scientific_entity_fresh_heldout_gate import (
    ScientificEntityFreshHeldoutGateConfig,
    canonical_config_sha256 as gate_config_sha256,
    load_scientific_entity_fresh_heldout_gate_config,
)
from radar_core.entities.scientific_entity_fresh_heldout_evaluation import (
    validate_fresh_heldout_evaluation,
)

REPORT_NAME = "scientific_entity_fresh_heldout_acceptance_decision_v02"
REQUIRED_FILES = (
    "manifest.json",
    "decision.json",
    "criteria.jsonl",
    "README.md",
    "checksums.txt",
)
CHECKSUM_FILES = (
    "manifest.json",
    "decision.json",
    "criteria.jsonl",
    "README.md",
)


class FreshHeldoutAcceptanceDecisionBuildError(RuntimeError):
    pass


def _resolve(project_root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = project_root / path
    return path.resolve()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _semantic_sha(payload: Any) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _json_bytes(payload: Any) -> bytes:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(rows: Sequence[Any]) -> bytes:
    lines = []
    for row in rows:
        if hasattr(row, "model_dump"):
            row = row.model_dump(mode="json")
        lines.append(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return (("\n".join(lines) + "\n") if lines else "").encode("utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise FreshHeldoutAcceptanceDecisionBuildError(f"Expected JSON object: {path}")
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip():
                raise FreshHeldoutAcceptanceDecisionBuildError(
                    f"Blank JSONL line: {path}:{line_number}"
                )
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise FreshHeldoutAcceptanceDecisionBuildError(
                    f"Expected JSON object: {path}:{line_number}"
                )
            rows.append(value)
    return rows


def _evaluation_config_semantic_sha(path: Path) -> str:
    cfg = load_scientific_entity_fresh_heldout_evaluation_config(path)
    return _semantic_sha(cfg.model_dump(mode="json"))


def _validate_exact_file_sha(path: Path, expected: str, label: str) -> None:
    actual = _sha256_file(path)
    if actual != expected:
        raise FreshHeldoutAcceptanceDecisionBuildError(
            f"{label} SHA drifted: {actual} != {expected}"
        )


def _validated_inputs(
    *,
    project_root: Path,
    contract: ScientificEntityFreshHeldoutAcceptanceDecisionConfig,
    sample_dir: Path,
    reference_dir: Path,
    development_package_dir: Path,
    canonical_path: Path,
) -> dict[str, Any]:
    evaluation_config_path = _resolve(project_root, contract.evaluation.config_path)
    evaluation_cfg = load_scientific_entity_fresh_heldout_evaluation_config(evaluation_config_path)
    evaluation_cfg_sha = _evaluation_config_semantic_sha(evaluation_config_path)
    if evaluation_cfg_sha != contract.evaluation.config_semantic_sha256:
        raise FreshHeldoutAcceptanceDecisionBuildError("Fresh-heldout evaluation config semantic SHA drifted")
    if evaluation_cfg.execution.evaluation_id != contract.evaluation.evaluation_id:
        raise FreshHeldoutAcceptanceDecisionBuildError("Fresh-heldout evaluation ID drifted")

    evaluation_dir = (
        _resolve(project_root, evaluation_cfg.execution.output_root)
        / evaluation_cfg.execution.evaluation_id
    )
    if not evaluation_dir.is_dir():
        raise FileNotFoundError(f"Fresh-heldout evaluation directory not found: {evaluation_dir}")
    _validate_exact_file_sha(
        evaluation_dir / "manifest.json",
        contract.evaluation.manifest_sha256,
        "evaluation manifest",
    )
    _validate_exact_file_sha(
        evaluation_dir / "metrics.json",
        contract.evaluation.metrics_sha256,
        "evaluation metrics",
    )
    _validate_exact_file_sha(
        evaluation_dir / "errors.jsonl",
        contract.evaluation.errors_sha256,
        "evaluation errors",
    )
    _validate_exact_file_sha(
        evaluation_dir / "checksums.txt",
        contract.evaluation.checksums_sha256,
        "evaluation checksums",
    )

    _, evaluation_summary = validate_fresh_heldout_evaluation(
        project_root=project_root,
        config_path=evaluation_config_path,
        sample_dir=sample_dir.resolve(),
        reference_dir=reference_dir.resolve(),
        development_package_dir=development_package_dir.resolve(),
        canonical_path=canonical_path.resolve(),
    )
    required = {
        "required_failed_count": contract.evaluation.required_validation_failed_count,
        "candidate_id": contract.candidate.candidate_id,
        "sample_id": contract.candidate.sample_id,
        "review_id": contract.candidate.review_id,
        "evaluation_id": contract.evaluation.evaluation_id,
        "document_count": contract.candidate.expected_document_count,
        "reference_mention_count": contract.candidate.expected_reference_mention_count,
        "prediction_mention_count": contract.candidate.expected_prediction_count,
        "evaluation_executed": True,
        "acceptance_decision_made": False,
        "threshold_tuning_executed": False,
        "model_inference_executed": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
    }
    for key, expected in required.items():
        if evaluation_summary.get(key) != expected:
            raise FreshHeldoutAcceptanceDecisionBuildError(
                f"Evaluation lineage mismatch for {key}: "
                f"{evaluation_summary.get(key)!r} != {expected!r}"
            )

    evaluation_manifest = _read_json(evaluation_dir / "manifest.json")
    prediction = evaluation_manifest.get("prediction") or {}
    if prediction.get("build_id") != contract.candidate.policy_build_id:
        raise FreshHeldoutAcceptanceDecisionBuildError("Evaluation policy build ID drifted")
    if prediction.get("extractor_fingerprint") != contract.candidate.policy_extractor_fingerprint:
        raise FreshHeldoutAcceptanceDecisionBuildError("Evaluation policy fingerprint drifted")

    gate_config_path = _resolve(project_root, contract.gate.config_path)
    gate = load_scientific_entity_fresh_heldout_gate_config(gate_config_path)
    gate_sha = gate_config_sha256(gate)
    if gate_sha != contract.gate.config_semantic_sha256:
        raise FreshHeldoutAcceptanceDecisionBuildError("Fresh-heldout gate semantic SHA drifted")
    if gate.acceptance.decision_role != contract.gate.decision_role:
        raise FreshHeldoutAcceptanceDecisionBuildError("Fresh-heldout gate decision role drifted")
    if gate.acceptance.all_hard_gates_required_for_acceptance is not True:
        raise FreshHeldoutAcceptanceDecisionBuildError("All hard gates must remain required")
    if gate.acceptance.require_relaxed_f1_as_hard_gate is not False:
        raise FreshHeldoutAcceptanceDecisionBuildError("Relaxed F1 must remain desirable, not hard")
    if gate.acceptance.no_post_heldout_tuning is not True:
        raise FreshHeldoutAcceptanceDecisionBuildError("No-post-heldout-tuning guard drifted")

    return {
        "evaluation_config_path": evaluation_config_path,
        "evaluation_config_sha256": evaluation_cfg_sha,
        "evaluation_dir": evaluation_dir,
        "evaluation_summary": evaluation_summary,
        "evaluation_manifest_sha256": _sha256_file(evaluation_dir / "manifest.json"),
        "evaluation_metrics_sha256": _sha256_file(evaluation_dir / "metrics.json"),
        "evaluation_errors_sha256": _sha256_file(evaluation_dir / "errors.jsonl"),
        "evaluation_checksums_sha256": _sha256_file(evaluation_dir / "checksums.txt"),
        "gate_config_path": gate_config_path,
        "gate_config_sha256": gate_sha,
        "gate": gate,
    }


def _criterion(
    *,
    name: str,
    observed: float | int,
    operator: str,
    threshold: float | int,
    hard: bool,
) -> AcceptanceCriterion:
    if operator == ">=":
        passed = observed >= threshold
    elif operator == "<=":
        passed = observed <= threshold
    else:
        raise FreshHeldoutAcceptanceDecisionBuildError(f"Unsupported operator: {operator}")
    return AcceptanceCriterion(
        name=name,
        observed=observed,
        operator=operator,
        threshold=threshold,
        hard=hard,
        passed=passed,
    )


def build_acceptance_criteria(
    evaluation_summary: Mapping[str, Any],
    gate: ScientificEntityFreshHeldoutGateConfig,
) -> tuple[AcceptanceCriterion, ...]:
    a = gate.acceptance
    return (
        _criterion(
            name="minimum_exact_f1",
            observed=float(evaluation_summary["exact_f1"]),
            operator=">=",
            threshold=a.minimum_exact_f1,
            hard=True,
        ),
        _criterion(
            name="desirable_minimum_relaxed_f1",
            observed=float(evaluation_summary["relaxed_f1"]),
            operator=">=",
            threshold=a.desirable_minimum_relaxed_f1,
            hard=False,
        ),
        _criterion(
            name="maximum_model_to_method_count",
            observed=int(evaluation_summary["model_to_method_count"]),
            operator="<=",
            threshold=a.maximum_model_to_method_count,
            hard=True,
        ),
        _criterion(
            name="maximum_method_to_task_count",
            observed=int(evaluation_summary["method_to_task_count"]),
            operator="<=",
            threshold=a.maximum_method_to_task_count,
            hard=True,
        ),
        _criterion(
            name="maximum_total_type_mismatch_count",
            observed=int(evaluation_summary["total_type_mismatch_count"]),
            operator="<=",
            threshold=a.maximum_total_type_mismatch_count,
            hard=True,
        ),
        _criterion(
            name="maximum_method_semantic_sink_count",
            observed=int(evaluation_summary["method_semantic_sink_count"]),
            operator="<=",
            threshold=a.maximum_method_semantic_sink_count,
            hard=True,
        ),
        _criterion(
            name="maximum_any_predicted_type_mismatch_sink_count",
            observed=int(evaluation_summary["maximum_any_predicted_type_mismatch_sink_count"]),
            operator="<=",
            threshold=a.maximum_any_predicted_type_mismatch_sink_count,
            hard=True,
        ),
    )


def build_acceptance_decision_result(
    *,
    decision_id: str,
    criteria: Sequence[AcceptanceCriterion],
    gate: ScientificEntityFreshHeldoutGateConfig,
) -> AcceptanceDecisionResult:
    hard = [row for row in criteria if row.hard]
    desirable = [row for row in criteria if not row.hard]
    failed_hard = [row.name for row in hard if not row.passed]
    failed_desirable = [row.name for row in desirable if not row.passed]
    rejected = bool(failed_hard)
    decision = (
        gate.decision_semantics.if_any_hard_gate_fails
        if rejected
        else gate.decision_semantics.if_all_hard_gates_pass
    )
    return AcceptanceDecisionResult(
        decision_id=decision_id,
        decision=decision,
        hard_criteria_count=len(hard),
        hard_criteria_passed_count=sum(row.passed for row in hard),
        failed_hard_criteria=failed_hard,
        desirable_criteria_count=len(desirable),
        desirable_criteria_passed_count=sum(row.passed for row in desirable),
        failed_desirable_criteria=failed_desirable,
        heldout_becomes_consumed_development_evidence=(
            rejected and gate.decision_semantics.failed_heldout_becomes_consumed_development_evidence
        ),
        future_candidate_requires_new_independent_heldout=(
            rejected and gate.decision_semantics.future_candidate_after_failure_requires_new_independent_heldout
        ),
        production_extractor_selected=False,
        full_corpus_build_authorized=False,
    )


def _build_readme(
    *,
    result: AcceptanceDecisionResult,
    criteria: Sequence[AcceptanceCriterion],
) -> str:
    lines = [
        "# Scientific Entity Fresh Held-Out Acceptance Decision v0.2",
        "",
        "This immutable artifact applies the pre-frozen fresh-v0.2 acceptance gate to the already validated one-shot v0.2c evaluation.",
        "",
        f"- decision: `{result.decision}`",
        f"- failed hard criteria: `{len(result.failed_hard_criteria)}`",
        f"- production extractor selected: `{str(result.production_extractor_selected).lower()}`",
        f"- full-corpus build authorized: `{str(result.full_corpus_build_authorized).lower()}`",
        "- model inference executed: `false`",
        "- policy reapplied: `false`",
        "- evaluation recomputed: `false`",
        "- threshold tuning executed: `false`",
        "- gate changed: `false`",
        "",
        "## Criteria",
        "",
    ]
    for row in criteria:
        role = "hard" if row.hard else "desirable"
        lines.append(
            f"- `{row.name}`: observed `{row.observed}` {row.operator} threshold `{row.threshold}` -> "
            f"`{'PASS' if row.passed else 'FAIL'}` ({role})"
        )
    lines.extend([
        "",
        "A scientifically correct REJECT is a valid decision artifact. It is not an engineering validation failure.",
        "",
    ])
    return "\n".join(lines)


def plan_or_execute_fresh_heldout_acceptance_decision(
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
    contract = load_scientific_entity_fresh_heldout_acceptance_decision_config(config_path.resolve())
    inputs = _validated_inputs(
        project_root=project_root,
        contract=contract,
        sample_dir=sample_dir.resolve(),
        reference_dir=reference_dir.resolve(),
        development_package_dir=development_package_dir.resolve(),
        canonical_path=canonical_path.resolve(),
    )
    output_dir = _resolve(project_root, contract.execution.output_root) / contract.execution.decision_id
    already_executed = output_dir.exists()
    if execute and already_executed:
        raise FileExistsError(
            f"Fresh-heldout acceptance decision is one-shot and already exists: {output_dir}"
        )

    report: dict[str, Any] = {
        "report": REPORT_NAME,
        "mode": "execute" if execute else "plan",
        "phase_complete": False,
        "candidate_id": contract.candidate.candidate_id,
        "sample_id": contract.candidate.sample_id,
        "review_id": contract.candidate.review_id,
        "policy_build_id": contract.candidate.policy_build_id,
        "policy_extractor_fingerprint": contract.candidate.policy_extractor_fingerprint,
        "document_count": contract.candidate.expected_document_count,
        "reference_mention_count": contract.candidate.expected_reference_mention_count,
        "prediction_mention_count": contract.candidate.expected_prediction_count,
        "evaluation_id": contract.evaluation.evaluation_id,
        "evaluation_validation_required_failed_count": inputs["evaluation_summary"]["required_failed_count"],
        "evaluation_manifest_sha256": inputs["evaluation_manifest_sha256"],
        "evaluation_metrics_sha256": inputs["evaluation_metrics_sha256"],
        "evaluation_errors_sha256": inputs["evaluation_errors_sha256"],
        "gate_config_sha256": inputs["gate_config_sha256"],
        "decision_id": contract.execution.decision_id,
        "output_dir": str(output_dir).replace("\\", "/"),
        "one_shot_already_executed": already_executed,
        "plan_runs_decision": False,
        "decision_materialized": False,
        "evaluation_recomputed": False,
        "model_inference_executed": False,
        "policy_reapplied": False,
        "threshold_tuning_executed": False,
        "gate_changed": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "next_slice": contract.next_steps.after_plan,
    }
    if not execute:
        return report

    criteria = build_acceptance_criteria(inputs["evaluation_summary"], inputs["gate"])
    result = build_acceptance_decision_result(
        decision_id=contract.execution.decision_id,
        criteria=criteria,
        gate=inputs["gate"],
    )
    manifest = AcceptanceDecisionManifest(
        decision_id=contract.execution.decision_id,
        generated_at_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        candidate_id=contract.candidate.candidate_id,
        sample_id=contract.candidate.sample_id,
        review_id=contract.candidate.review_id,
        policy_build_id=contract.candidate.policy_build_id,
        policy_extractor_fingerprint=contract.candidate.policy_extractor_fingerprint,
        document_count=contract.candidate.expected_document_count,
        reference_mention_count=contract.candidate.expected_reference_mention_count,
        prediction_mention_count=contract.candidate.expected_prediction_count,
        decision_config_path=str(config_path.resolve().relative_to(project_root)).replace("\\", "/")
        if config_path.resolve().is_relative_to(project_root)
        else str(config_path.resolve()).replace("\\", "/"),
        decision_config_semantic_sha256=decision_config_sha256(contract),
        evaluation_config_path=contract.evaluation.config_path,
        evaluation_config_semantic_sha256=inputs["evaluation_config_sha256"],
        evaluation_id=contract.evaluation.evaluation_id,
        evaluation_manifest_sha256=inputs["evaluation_manifest_sha256"],
        evaluation_metrics_sha256=inputs["evaluation_metrics_sha256"],
        evaluation_errors_sha256=inputs["evaluation_errors_sha256"],
        evaluation_checksums_sha256=inputs["evaluation_checksums_sha256"],
        evaluation_validation_required_failed_count=0,
        gate_config_path=contract.gate.config_path,
        gate_config_semantic_sha256=inputs["gate_config_sha256"],
        evaluation_recomputed=False,
        model_inference_executed=False,
        policy_reapplied=False,
        threshold_tuning_executed=False,
        gate_changed=False,
        canonical_truth_mutated=False,
        production_extractor_selected=False,
        full_corpus_build_authorized=False,
    )
    readme = _build_readme(result=result, criteria=criteria)

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{contract.execution.decision_id}.tmp-", dir=output_dir.parent)
    )
    try:
        (staging / "manifest.json").write_bytes(_json_bytes(manifest))
        (staging / "decision.json").write_bytes(_json_bytes(result))
        (staging / "criteria.jsonl").write_bytes(_jsonl_bytes(criteria))
        (staging / "README.md").write_text(readme, encoding="utf-8", newline="\n")
        checksum_lines = [
            f"{_sha256_file(staging / filename)}  {filename}" for filename in CHECKSUM_FILES
        ]
        (staging / "checksums.txt").write_text(
            "\n".join(checksum_lines) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        staging.rename(output_dir)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    report.update({
        "phase_complete": True,
        "one_shot_already_executed": True,
        "decision_materialized": True,
        "decision": result.decision,
        "failed_hard_criteria": list(result.failed_hard_criteria),
        "hard_criteria_passed_count": result.hard_criteria_passed_count,
        "hard_criteria_count": result.hard_criteria_count,
        "desirable_criteria_passed_count": result.desirable_criteria_passed_count,
        "desirable_criteria_count": result.desirable_criteria_count,
        "next_slice": contract.next_steps.after_execute,
    })
    return report


def _text_is_utf8_lf(path: Path) -> tuple[bool, str | None]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return False, "UTF-8 BOM is forbidden"
    if b"\r" in raw:
        return False, "CR/CRLF is forbidden"
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return False, f"invalid UTF-8: {exc}"
    if raw and not raw.endswith(b"\n"):
        return False, "text file must end with LF"
    return True, None


def validate_fresh_heldout_acceptance_decision(
    *,
    project_root: Path,
    config_path: Path,
    sample_dir: Path,
    reference_dir: Path,
    development_package_dir: Path,
    canonical_path: Path,
) -> tuple[list[tuple[str, bool, str]], dict[str, Any]]:
    project_root = project_root.resolve()
    contract = load_scientific_entity_fresh_heldout_acceptance_decision_config(config_path.resolve())
    inputs = _validated_inputs(
        project_root=project_root,
        contract=contract,
        sample_dir=sample_dir.resolve(),
        reference_dir=reference_dir.resolve(),
        development_package_dir=development_package_dir.resolve(),
        canonical_path=canonical_path.resolve(),
    )
    output_dir = _resolve(project_root, contract.execution.output_root) / contract.execution.decision_id
    checks: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: Any = "") -> None:
        checks.append((name, bool(ok), str(detail)))

    add(
        "evaluation_validation_passed",
        inputs["evaluation_summary"]["required_failed_count"] == 0,
        inputs["evaluation_summary"]["required_failed_count"],
    )
    add("decision_directory_exists", output_dir.is_dir(), output_dir)
    if not output_dir.is_dir():
        return checks, _validation_summary(checks, contract, None, None)

    files = {path.name for path in output_dir.iterdir() if path.is_file()}
    dirs = {path.name for path in output_dir.iterdir() if path.is_dir()}
    add("required_files_exact", files == set(REQUIRED_FILES), sorted(files))
    add("nested_directories_absent", not dirs, sorted(dirs))
    if files != set(REQUIRED_FILES):
        return checks, _validation_summary(checks, contract, None, None)

    for filename in REQUIRED_FILES:
        ok, detail = _text_is_utf8_lf(output_dir / filename)
        add(f"utf8_lf::{filename}", ok, detail or "")

    checksum_rows: dict[str, str] = {}
    for line in (output_dir / "checksums.txt").read_text(encoding="utf-8").splitlines():
        parts = line.split("  ", 1)
        if len(parts) == 2:
            checksum_rows[parts[1]] = parts[0]
    add("checksums_cover_exact_files", set(checksum_rows) == set(CHECKSUM_FILES), sorted(checksum_rows))
    for filename in CHECKSUM_FILES:
        add(
            f"checksum::{filename}",
            checksum_rows.get(filename) == _sha256_file(output_dir / filename),
            filename,
        )

    manifest = AcceptanceDecisionManifest.model_validate(_read_json(output_dir / "manifest.json"))
    result = AcceptanceDecisionResult.model_validate(_read_json(output_dir / "decision.json"))
    criteria = tuple(
        AcceptanceCriterion.model_validate(row) for row in _read_jsonl(output_dir / "criteria.jsonl")
    )
    expected_criteria = build_acceptance_criteria(inputs["evaluation_summary"], inputs["gate"])
    expected_result = build_acceptance_decision_result(
        decision_id=contract.execution.decision_id,
        criteria=expected_criteria,
        gate=inputs["gate"],
    )

    add("decision_id_exact", manifest.decision_id == result.decision_id == contract.execution.decision_id, manifest.decision_id)
    add("candidate_id_exact", manifest.candidate_id == contract.candidate.candidate_id, manifest.candidate_id)
    add("sample_id_exact", manifest.sample_id == contract.candidate.sample_id, manifest.sample_id)
    add("review_id_exact", manifest.review_id == contract.candidate.review_id, manifest.review_id)
    add("policy_build_id_exact", manifest.policy_build_id == contract.candidate.policy_build_id, manifest.policy_build_id)
    add("policy_fingerprint_exact", manifest.policy_extractor_fingerprint == contract.candidate.policy_extractor_fingerprint, manifest.policy_extractor_fingerprint)
    add("counts_exact", (
        manifest.document_count == contract.candidate.expected_document_count
        and manifest.reference_mention_count == contract.candidate.expected_reference_mention_count
        and manifest.prediction_mention_count == contract.candidate.expected_prediction_count
    ), f"{manifest.document_count}/{manifest.reference_mention_count}/{manifest.prediction_mention_count}")
    add("decision_config_sha_exact", manifest.decision_config_semantic_sha256 == decision_config_sha256(contract), manifest.decision_config_semantic_sha256)
    add("evaluation_config_sha_exact", manifest.evaluation_config_semantic_sha256 == inputs["evaluation_config_sha256"], manifest.evaluation_config_semantic_sha256)
    add("evaluation_id_exact", manifest.evaluation_id == contract.evaluation.evaluation_id, manifest.evaluation_id)
    add("evaluation_manifest_sha_exact", manifest.evaluation_manifest_sha256 == inputs["evaluation_manifest_sha256"], manifest.evaluation_manifest_sha256)
    add("evaluation_metrics_sha_exact", manifest.evaluation_metrics_sha256 == inputs["evaluation_metrics_sha256"], manifest.evaluation_metrics_sha256)
    add("evaluation_errors_sha_exact", manifest.evaluation_errors_sha256 == inputs["evaluation_errors_sha256"], manifest.evaluation_errors_sha256)
    add("evaluation_checksums_sha_exact", manifest.evaluation_checksums_sha256 == inputs["evaluation_checksums_sha256"], manifest.evaluation_checksums_sha256)
    add("gate_sha_exact", manifest.gate_config_semantic_sha256 == inputs["gate_config_sha256"], manifest.gate_config_semantic_sha256)
    add("criteria_exact", [row.model_dump(mode="json") for row in criteria] == [row.model_dump(mode="json") for row in expected_criteria], len(criteria))
    add("decision_result_exact", result.model_dump(mode="json") == expected_result.model_dump(mode="json"), result.decision)
    add("evaluation_not_recomputed", manifest.evaluation_recomputed is False, "")
    add("model_inference_not_run", manifest.model_inference_executed is False, "")
    add("policy_not_reapplied", manifest.policy_reapplied is False, "")
    add("threshold_tuning_not_run", manifest.threshold_tuning_executed is False, "")
    add("gate_not_changed", manifest.gate_changed is False, "")
    add("canonical_truth_not_mutated", manifest.canonical_truth_mutated is False, "")
    add("production_not_selected", manifest.production_extractor_selected is False and result.production_extractor_selected is False, "")
    add("full_corpus_not_authorized", manifest.full_corpus_build_authorized is False and result.full_corpus_build_authorized is False, "")

    return checks, _validation_summary(checks, contract, result, criteria)


def _validation_summary(
    checks: Sequence[tuple[str, bool, str]],
    contract: ScientificEntityFreshHeldoutAcceptanceDecisionConfig,
    result: AcceptanceDecisionResult | None,
    criteria: Sequence[AcceptanceCriterion] | None,
) -> dict[str, Any]:
    failed = [name for name, ok, _ in checks if not ok]
    summary: dict[str, Any] = {
        "report": REPORT_NAME,
        "candidate_id": contract.candidate.candidate_id,
        "sample_id": contract.candidate.sample_id,
        "review_id": contract.candidate.review_id,
        "evaluation_id": contract.evaluation.evaluation_id,
        "decision_id": contract.execution.decision_id,
        "decision_materialized": result is not None,
        "decision": None if result is None else result.decision,
        "failed_hard_criteria": [] if result is None else list(result.failed_hard_criteria),
        "hard_criteria_count": None if result is None else result.hard_criteria_count,
        "hard_criteria_passed_count": None if result is None else result.hard_criteria_passed_count,
        "desirable_criteria_count": None if result is None else result.desirable_criteria_count,
        "desirable_criteria_passed_count": None if result is None else result.desirable_criteria_passed_count,
        "criterion_count": 0 if criteria is None else len(criteria),
        "evaluation_recomputed": False,
        "model_inference_executed": False,
        "policy_reapplied": False,
        "threshold_tuning_executed": False,
        "gate_changed": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "total_checks": len(checks),
        "required_failed_count": len(failed),
        "next_slice": contract.next_steps.after_validation,
    }
    return summary
