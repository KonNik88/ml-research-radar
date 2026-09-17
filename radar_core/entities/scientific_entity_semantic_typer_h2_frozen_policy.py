from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from radar_core.contracts.scientific_entity_evidence import ScientificEntityType
from radar_core.contracts.scientific_entity_semantic_typer_candidate import (
    load_semantic_typer_config,
    semantic_typer_config_sha256,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_frozen_policy import (
    MANIFEST_SCHEMA_VERSION,
    SUMMARY_SCHEMA_VERSION,
    FrozenH2Policy,
    load_h2_frozen_policy_config,
)
from radar_core.entities.scientific_entity_semantic_typer import semantic_typer_fingerprint
from radar_core.entities.scientific_entity_semantic_typer_evaluation import _metric_set


REPORT_NAME = "scientific_entity_semantic_typer_h2_frozen_policy_v03"
REQUIRED_REVISION_FILES = (
    "manifest.json",
    "summary.json",
    "margin_sweep.json",
    "transition_breakdown.json",
    "selected_policy.json",
    "policy_case_outcomes.jsonl",
    "README.md",
    "checksums.txt",
)
REQUIRED_EVALUATION_FILES = (
    "manifest.json",
    "summary.json",
    "case_comparison.jsonl",
    "diagnostic_slices.json",
    "README.md",
    "checksums.txt",
)
REQUIRED_PREDICTION_FILES = (
    "manifest.json",
    "predictions.jsonl",
    "summary.json",
    "README.md",
    "checksums.txt",
)
REQUIRED_OUTPUT_FILES = (
    "manifest.json",
    "frozen_policy.json",
    "development_reproduction.json",
    "summary.json",
    "README.md",
    "checksums.txt",
)


class ScientificEntitySemanticTyperH2FrozenPolicyError(ValueError):
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
        raise ScientificEntitySemanticTyperH2FrozenPolicyError(f"Expected JSON object: {path}")
    return payload


def _read_jsonl_dicts(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not all(isinstance(row, dict) for row in rows):
        raise ScientificEntitySemanticTyperH2FrozenPolicyError(f"Expected JSONL objects: {path}")
    return rows


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


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


def h2_candidate_identity_payload(config, h1_semantic_typer_fingerprint: str) -> dict[str, Any]:
    return {
        "candidate_id": config.candidate.candidate_id,
        "hypothesis": config.candidate.hypothesis,
        "semantic_typer_candidate_id": config.candidate.semantic_typer_candidate_id,
        "semantic_typer_fingerprint": h1_semantic_typer_fingerprint,
        "upstream_baseline_candidate_id": config.candidate.upstream_baseline_candidate_id,
        "policy_id": config.policy.policy_id,
        "baseline_type": ScientificEntityType(config.policy.baseline_type).value,
        "semantic_typer_type": ScientificEntityType(config.policy.semantic_typer_type).value,
        "score_field": config.policy.score_field,
        "operator": config.policy.operator,
        "margin_threshold": config.policy.margin_threshold,
        "preserve_baseline_otherwise": config.policy.preserve_baseline_otherwise,
        "use_baseline_type_as_post_inference_policy_condition_only": config.policy.use_baseline_type_as_post_inference_policy_condition_only,
    }


def h2_candidate_fingerprint(config, h1_semantic_typer_fingerprint: str) -> str:
    payload = json.dumps(
        h2_candidate_identity_payload(config, h1_semantic_typer_fingerprint),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def apply_h2_selective_override(
    *,
    config,
    baseline_type: ScientificEntityType | str,
    semantic_typer_type: ScientificEntityType | str,
    score_margin: float | None,
) -> tuple[ScientificEntityType, bool]:
    baseline = ScientificEntityType(baseline_type)
    typer = ScientificEntityType(semantic_typer_type)
    override = (
        baseline == ScientificEntityType(config.policy.baseline_type)
        and typer == ScientificEntityType(config.policy.semantic_typer_type)
        and score_margin is not None
        and float(score_margin) >= config.policy.margin_threshold
    )
    return (typer if override else baseline), override


def _require_files(directory: Path, names: Sequence[str], label: str) -> None:
    if not directory.is_dir():
        raise FileNotFoundError(f"{label} directory does not exist: {directory}")
    for name in names:
        if not (directory / name).is_file():
            raise FileNotFoundError(f"Missing {label} file: {directory / name}")


def _validate_parent_lineage(
    *,
    project_root: Path,
    config,
    revision_analysis_dir: Path,
    evaluation_dir: Path,
    prediction_dir: Path,
) -> dict[str, Any]:
    _require_files(revision_analysis_dir, REQUIRED_REVISION_FILES, "revision analysis")
    _require_files(evaluation_dir, REQUIRED_EVALUATION_FILES, "H1 evaluation")
    _require_files(prediction_dir, REQUIRED_PREDICTION_FILES, "H1 prediction")

    revision_manifest = _read_json(revision_analysis_dir / "manifest.json")
    revision_summary = _read_json(revision_analysis_dir / "summary.json")
    selected_policy = _read_json(revision_analysis_dir / "selected_policy.json")
    evaluation_manifest = _read_json(evaluation_dir / "manifest.json")
    evaluation_summary = _read_json(evaluation_dir / "summary.json")
    prediction_manifest = _read_json(prediction_dir / "manifest.json")
    prediction_summary = _read_json(prediction_dir / "summary.json")

    if revision_manifest.get("analysis_id") != config.lineage.revision_analysis_id:
        raise ScientificEntitySemanticTyperH2FrozenPolicyError("Revision analysis ID drifted")
    if revision_summary.get("parent_evaluation_id") != config.lineage.parent_evaluation_id:
        raise ScientificEntitySemanticTyperH2FrozenPolicyError("Revision parent evaluation ID drifted")
    if revision_summary.get("selected_policy_status") != "selected":
        raise ScientificEntitySemanticTyperH2FrozenPolicyError("Revision analysis must contain a selected H2 policy")
    if evaluation_summary.get("evaluation_id") != config.lineage.parent_evaluation_id:
        raise ScientificEntitySemanticTyperH2FrozenPolicyError("H1 evaluation ID drifted")
    if evaluation_summary.get("prediction_id") != config.lineage.parent_prediction_id:
        raise ScientificEntitySemanticTyperH2FrozenPolicyError("H1 evaluation prediction ID drifted")
    if evaluation_summary.get("decision", {}).get("decision") != config.lineage.expected_parent_decision:
        raise ScientificEntitySemanticTyperH2FrozenPolicyError("H1 evaluation decision must remain reject_candidate")
    if evaluation_summary.get("case_count") != config.lineage.expected_case_count:
        raise ScientificEntitySemanticTyperH2FrozenPolicyError("H1 evaluation case_count drifted")
    if evaluation_summary.get("primary_metric_eligible_count") != config.lineage.expected_primary_metric_eligible_count:
        raise ScientificEntitySemanticTyperH2FrozenPolicyError("H1 primary metric count drifted")
    if prediction_manifest.get("prediction_id") != config.lineage.parent_prediction_id:
        raise ScientificEntitySemanticTyperH2FrozenPolicyError("H1 prediction ID drifted")
    if prediction_manifest.get("candidate_id") != config.candidate.semantic_typer_candidate_id:
        raise ScientificEntitySemanticTyperH2FrozenPolicyError("H1 semantic typer candidate ID drifted")

    if revision_manifest.get("parent_evaluation_manifest_sha256") != _sha256_file(evaluation_dir / "manifest.json"):
        raise ScientificEntitySemanticTyperH2FrozenPolicyError("Revision analysis is not bound to supplied H1 evaluation manifest")
    if revision_manifest.get("parent_evaluation_summary_sha256") != _sha256_file(evaluation_dir / "summary.json"):
        raise ScientificEntitySemanticTyperH2FrozenPolicyError("Revision analysis is not bound to supplied H1 evaluation summary")
    if revision_manifest.get("parent_case_comparison_sha256") != _sha256_file(evaluation_dir / "case_comparison.jsonl"):
        raise ScientificEntitySemanticTyperH2FrozenPolicyError("Revision analysis is not bound to supplied H1 case comparison")
    if evaluation_manifest.get("prediction_manifest_sha256") != _sha256_file(prediction_dir / "manifest.json"):
        raise ScientificEntitySemanticTyperH2FrozenPolicyError("H1 evaluation is not bound to supplied H1 prediction manifest")

    h1_config_path = (project_root / config.candidate.semantic_typer_config_path).resolve()
    h1_config = load_semantic_typer_config(h1_config_path)
    h1_config_sha256 = semantic_typer_config_sha256(h1_config)
    h1_fingerprint = semantic_typer_fingerprint(h1_config)
    if prediction_manifest.get("semantic_typer_config_sha256") != h1_config_sha256:
        raise ScientificEntitySemanticTyperH2FrozenPolicyError("H1 prediction semantic typer config hash drifted")
    if prediction_manifest.get("semantic_typer_fingerprint") != h1_fingerprint:
        raise ScientificEntitySemanticTyperH2FrozenPolicyError("H1 prediction semantic typer fingerprint drifted")
    if prediction_summary.get("semantic_typer_fingerprint") != h1_fingerprint:
        raise ScientificEntitySemanticTyperH2FrozenPolicyError("H1 prediction summary semantic typer fingerprint drifted")

    expected_policy = config.policy
    if selected_policy.get("policy_id") != expected_policy.policy_id:
        raise ScientificEntitySemanticTyperH2FrozenPolicyError("Selected policy ID drifted")
    if selected_policy.get("baseline_type") != ScientificEntityType(expected_policy.baseline_type).value:
        raise ScientificEntitySemanticTyperH2FrozenPolicyError("Selected policy baseline type drifted")
    if selected_policy.get("semantic_typer_type") != ScientificEntityType(expected_policy.semantic_typer_type).value:
        raise ScientificEntitySemanticTyperH2FrozenPolicyError("Selected policy semantic typer type drifted")
    if selected_policy.get("score_field") != expected_policy.score_field:
        raise ScientificEntitySemanticTyperH2FrozenPolicyError("Selected policy score field drifted")
    if selected_policy.get("operator") != expected_policy.operator:
        raise ScientificEntitySemanticTyperH2FrozenPolicyError("Selected policy operator drifted")
    if selected_policy.get("threshold") != expected_policy.margin_threshold:
        raise ScientificEntitySemanticTyperH2FrozenPolicyError("Selected policy margin threshold drifted")
    if selected_policy.get("selection_rule") != expected_policy.selection_rule:
        raise ScientificEntitySemanticTyperH2FrozenPolicyError("Selected policy selection rule drifted")
    if selected_policy.get("plateau_thresholds") != expected_policy.selected_plateau_thresholds:
        raise ScientificEntitySemanticTyperH2FrozenPolicyError("Selected policy plateau drifted")

    return {
        "revision_manifest": revision_manifest,
        "revision_summary": revision_summary,
        "selected_policy": selected_policy,
        "evaluation_manifest": evaluation_manifest,
        "evaluation_summary": evaluation_summary,
        "prediction_manifest": prediction_manifest,
        "prediction_summary": prediction_summary,
        "h1_config_sha256": h1_config_sha256,
        "h1_fingerprint": h1_fingerprint,
    }


def reproduce_h2_development_policy(
    *,
    config,
    comparisons: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    eligible = [row for row in comparisons if bool(row.get("primary_metric_eligible"))]
    truth: list[ScientificEntityType] = []
    baseline_predictions: list[ScientificEntityType] = []
    final_predictions: list[ScientificEntityType] = []
    overrides = corrected = regressed = wrong_to_wrong = 0

    for row in eligible:
        reference = ScientificEntityType(row["reference_entity_type"])
        baseline = ScientificEntityType(row["baseline_entity_type"])
        typer = ScientificEntityType(row["candidate_entity_type"])
        final, override = apply_h2_selective_override(
            config=config,
            baseline_type=baseline,
            semantic_typer_type=typer,
            score_margin=row.get("score_margin"),
        )
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
        baseline_predictions.append(baseline)
        final_predictions.append(final)

    baseline_metrics = _metric_set(truth, baseline_predictions)
    final_metrics = _metric_set(truth, final_predictions)
    baseline_correct_count = baseline_metrics.correct_count
    baseline_m2m = sum(
        ref == ScientificEntityType.MODEL and pred == ScientificEntityType.METHOD
        for ref, pred in zip(truth, baseline_predictions)
    )
    final_m2m = sum(
        ref == ScientificEntityType.MODEL and pred == ScientificEntityType.METHOD
        for ref, pred in zip(truth, final_predictions)
    )
    return {
        "case_count": len(comparisons),
        "primary_metric_eligible_count": len(eligible),
        "baseline_correct_count": baseline_correct_count,
        "override_count": overrides,
        "corrected_errors": corrected,
        "introduced_regressions": regressed,
        "wrong_to_wrong_changes": wrong_to_wrong,
        "net_corrected_cases": corrected - regressed,
        "regression_rate": round(_safe_div(regressed, baseline_correct_count), 6),
        "baseline_accuracy": baseline_metrics.accuracy,
        "final_accuracy": final_metrics.accuracy,
        "same_span_accuracy_delta": round(final_metrics.accuracy - baseline_metrics.accuracy, 6),
        "baseline_macro_f1": baseline_metrics.macro_f1,
        "final_macro_f1": final_metrics.macro_f1,
        "macro_f1_delta": round(final_metrics.macro_f1 - baseline_metrics.macro_f1, 6),
        "baseline_model_to_method_count": baseline_m2m,
        "model_to_method_after_count": final_m2m,
        "model_to_method_reduction_fraction": round(_safe_div(baseline_m2m - final_m2m, baseline_m2m), 6),
    }


def _validate_reproduction(config, reproduction: Mapping[str, Any], revision_summary: Mapping[str, Any]) -> None:
    expected = config.expected_development_reproduction.model_dump(mode="json")
    actual = {key: reproduction.get(key) for key in expected}
    if actual != expected:
        raise ScientificEntitySemanticTyperH2FrozenPolicyError(
            f"H2 development reproduction drifted: actual={actual}, expected={expected}"
        )
    revision_metrics = revision_summary.get("selected_policy_metrics") or {}
    revision_actual = {key: revision_metrics.get(key) for key in expected}
    if revision_actual != expected:
        raise ScientificEntitySemanticTyperH2FrozenPolicyError(
            f"Revision selected-policy metrics drifted: actual={revision_actual}, expected={expected}"
        )


def plan_or_execute_h2_frozen_policy(
    *,
    project_root: Path,
    config_path: Path,
    revision_analysis_dir: Path,
    evaluation_dir: Path,
    prediction_dir: Path,
    freeze_id: str | None = None,
    output_root: Path | None = None,
    execute: bool = False,
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    root = project_root.resolve()
    config = load_h2_frozen_policy_config(config_path.resolve())
    revision_analysis_dir = revision_analysis_dir.resolve()
    evaluation_dir = evaluation_dir.resolve()
    prediction_dir = prediction_dir.resolve()
    parents = _validate_parent_lineage(
        project_root=root,
        config=config,
        revision_analysis_dir=revision_analysis_dir,
        evaluation_dir=evaluation_dir,
        prediction_dir=prediction_dir,
    )
    comparisons = _read_jsonl_dicts(evaluation_dir / "case_comparison.jsonl")
    if len(comparisons) != config.lineage.expected_case_count:
        raise ScientificEntitySemanticTyperH2FrozenPolicyError("H1 case comparison count drifted")

    generated_at = generated_at_utc or datetime.now(timezone.utc)
    if generated_at.tzinfo is None or generated_at.utcoffset() != timezone.utc.utcoffset(generated_at):
        raise ScientificEntitySemanticTyperH2FrozenPolicyError("generated_at_utc must be timezone-aware UTC")
    if freeze_id is None:
        freeze_id = "scientific-entity-semantic-typer-h2-frozen-policy-v0.3-" + generated_at.strftime("%Y%m%dT%H%M%S%fZ")
    selected_root = output_root.resolve() if output_root is not None else (
        root / "data/entities/scientific_entity_semantic_typer_h2_frozen_policy/v0.3"
    ).resolve()
    output_dir = selected_root / freeze_id
    if execute and output_dir.exists():
        raise FileExistsError(f"Immutable H2 frozen policy already exists: {output_dir}")

    candidate_fingerprint = h2_candidate_fingerprint(config, parents["h1_fingerprint"])
    report = {
        "report": REPORT_NAME,
        "mode": "execute" if execute else "plan",
        "phase_complete": False,
        "freeze_id": freeze_id,
        "candidate_id": config.candidate.candidate_id,
        "revision_analysis_id": config.lineage.revision_analysis_id,
        "parent_evaluation_id": config.lineage.parent_evaluation_id,
        "parent_prediction_id": config.lineage.parent_prediction_id,
        "semantic_typer_candidate_id": config.candidate.semantic_typer_candidate_id,
        "h2_candidate_fingerprint": candidate_fingerprint,
        "margin_threshold": config.policy.margin_threshold,
        "policy_frozen": False,
        "development_reproduction_executed": False,
        "new_model_inference_executed": False,
        "model_inference_threshold_tuning_executed": False,
        "policy_margin_threshold_calibration_executed": False,
        "independent_acceptance_executed": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "output_dir": str(output_dir).replace("\\", "/"),
        "next_slice": "execute_freeze_h2_selective_override_policy_once",
    }
    if not execute:
        return report

    reproduction = reproduce_h2_development_policy(config=config, comparisons=comparisons)
    _validate_reproduction(config, reproduction, parents["revision_summary"])

    frozen_policy = FrozenH2Policy(
        candidate_id=config.candidate.candidate_id,
        policy_id=config.policy.policy_id,
        semantic_typer_candidate_id=config.candidate.semantic_typer_candidate_id,
        semantic_typer_fingerprint=parents["h1_fingerprint"],
        baseline_type=ScientificEntityType(config.policy.baseline_type),
        semantic_typer_type=ScientificEntityType(config.policy.semantic_typer_type),
        score_field=config.policy.score_field,
        operator=config.policy.operator,
        margin_threshold=config.policy.margin_threshold,
        preserve_baseline_otherwise=config.policy.preserve_baseline_otherwise,
        use_baseline_type_as_post_inference_policy_condition_only=config.policy.use_baseline_type_as_post_inference_policy_condition_only,
        selection_rule=config.policy.selection_rule,
        selected_plateau_thresholds=config.policy.selected_plateau_thresholds,
        candidate_fingerprint=candidate_fingerprint,
    ).model_dump(mode="json")

    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "freeze_id": freeze_id,
        "generated_at_utc": generated_at.isoformat().replace("+00:00", "Z"),
        "candidate_id": config.candidate.candidate_id,
        "policy_id": config.policy.policy_id,
        "revision_analysis_id": config.lineage.revision_analysis_id,
        "revision_manifest_sha256": _sha256_file(revision_analysis_dir / "manifest.json"),
        "revision_summary_sha256": _sha256_file(revision_analysis_dir / "summary.json"),
        "revision_selected_policy_sha256": _sha256_file(revision_analysis_dir / "selected_policy.json"),
        "revision_policy_case_outcomes_sha256": _sha256_file(revision_analysis_dir / "policy_case_outcomes.jsonl"),
        "parent_evaluation_id": config.lineage.parent_evaluation_id,
        "parent_evaluation_manifest_sha256": _sha256_file(evaluation_dir / "manifest.json"),
        "parent_prediction_id": config.lineage.parent_prediction_id,
        "parent_prediction_manifest_sha256": _sha256_file(prediction_dir / "manifest.json"),
        "semantic_typer_config_sha256": parents["h1_config_sha256"],
        "semantic_typer_fingerprint": parents["h1_fingerprint"],
        "h2_candidate_fingerprint": candidate_fingerprint,
        "policy_frozen": True,
        "development_reproduction_executed": True,
        "new_model_inference_executed": False,
        "model_inference_threshold_tuning_executed": False,
        "policy_margin_threshold_calibration_executed": False,
        "independent_acceptance_executed": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "publication_ready": False,
        "future_candidate_requires_new_independent_heldout": True,
    }
    summary = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "freeze_id": freeze_id,
        "candidate_id": config.candidate.candidate_id,
        "policy_id": config.policy.policy_id,
        "semantic_typer_candidate_id": config.candidate.semantic_typer_candidate_id,
        "h2_candidate_fingerprint": candidate_fingerprint,
        "margin_threshold": config.policy.margin_threshold,
        "selected_plateau_thresholds": config.policy.selected_plateau_thresholds,
        "development_reproduction": reproduction,
        "policy_frozen": True,
        "development_reproduction_executed": True,
        "new_model_inference_executed": False,
        "model_inference_threshold_tuning_executed": False,
        "policy_margin_threshold_calibration_executed": False,
        "independent_acceptance_executed": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "future_candidate_requires_new_independent_heldout": True,
        "next_slice": config.next_steps["after_freeze"],
    }
    readme = (
        "# Scientific Entity Semantic Typer v0.3 H2 Frozen Policy\n\n"
        "Immutable composite candidate for independent-acceptance preparation.\n"
        "The frozen H1 semantic typer is retained, but its type overrides the frozen v0.2c baseline\n"
        "only for method -> model transitions with score margin >= 0.10. All other cases preserve\n"
        "the baseline type. No new inference, tuning, production selection, or acceptance occurs here.\n"
    ).encode("utf-8")
    payloads = {
        "manifest.json": _json_bytes(manifest),
        "frozen_policy.json": _json_bytes(frozen_policy),
        "development_reproduction.json": _json_bytes(reproduction),
        "summary.json": _json_bytes(summary),
        "README.md": readme,
    }
    payloads["checksums.txt"] = _checksums(payloads)
    _write_atomic(output_dir, payloads)
    report.update({
        "phase_complete": True,
        "policy_frozen": True,
        "development_reproduction_executed": True,
        "development_override_count": reproduction["override_count"],
        "development_net_corrected_cases": reproduction["net_corrected_cases"],
        "development_regression_rate": reproduction["regression_rate"],
        "development_same_span_accuracy_delta": reproduction["same_span_accuracy_delta"],
        "next_slice": summary["next_slice"],
    })
    return report


def validate_h2_frozen_policy(
    *,
    project_root: Path,
    config_path: Path,
    revision_analysis_dir: Path,
    evaluation_dir: Path,
    prediction_dir: Path,
    frozen_policy_dir: Path,
) -> tuple[list[tuple[str, bool, str]], dict[str, Any]]:
    root = project_root.resolve()
    config = load_h2_frozen_policy_config(config_path.resolve())
    revision_analysis_dir = revision_analysis_dir.resolve()
    evaluation_dir = evaluation_dir.resolve()
    prediction_dir = prediction_dir.resolve()
    frozen_policy_dir = frozen_policy_dir.resolve()
    checks: list[tuple[str, bool, str]] = []

    def add(name: str, ok: bool, detail: Any = "") -> None:
        checks.append((name, bool(ok), str(detail)))

    add("frozen_policy_dir_exists", frozen_policy_dir.is_dir(), frozen_policy_dir)
    for name in REQUIRED_OUTPUT_FILES:
        add(f"required_file:{name}", (frozen_policy_dir / name).is_file(), name)
    if not frozen_policy_dir.is_dir() or any(not (frozen_policy_dir / name).is_file() for name in REQUIRED_OUTPUT_FILES):
        summary = {
            "report": REPORT_NAME,
            "validation_scope": "h2_frozen_policy",
            "total_checks": len(checks),
            "required_failed_count": sum(not row[1] for row in checks),
            "next_slice": "fix_h2_frozen_policy_validation_failures",
        }
        return checks, summary

    try:
        parents = _validate_parent_lineage(
            project_root=root,
            config=config,
            revision_analysis_dir=revision_analysis_dir,
            evaluation_dir=evaluation_dir,
            prediction_dir=prediction_dir,
        )
        add("parent_lineage_valid", True, "")
    except Exception as exc:
        add("parent_lineage_valid", False, exc)
        parents = None

    stored_manifest = _read_json(frozen_policy_dir / "manifest.json")
    stored_policy = _read_json(frozen_policy_dir / "frozen_policy.json")
    stored_reproduction = _read_json(frozen_policy_dir / "development_reproduction.json")
    stored_summary = _read_json(frozen_policy_dir / "summary.json")
    comparisons = _read_jsonl_dicts(evaluation_dir / "case_comparison.jsonl")

    if parents is not None:
        recomputed_reproduction = reproduce_h2_development_policy(config=config, comparisons=comparisons)
        try:
            _validate_reproduction(config, recomputed_reproduction, parents["revision_summary"])
            add("development_reproduction_matches_frozen_expectation", True, "")
        except Exception as exc:
            add("development_reproduction_matches_frozen_expectation", False, exc)
        candidate_fingerprint = h2_candidate_fingerprint(config, parents["h1_fingerprint"])
        expected_policy = FrozenH2Policy(
            candidate_id=config.candidate.candidate_id,
            policy_id=config.policy.policy_id,
            semantic_typer_candidate_id=config.candidate.semantic_typer_candidate_id,
            semantic_typer_fingerprint=parents["h1_fingerprint"],
            baseline_type=ScientificEntityType(config.policy.baseline_type),
            semantic_typer_type=ScientificEntityType(config.policy.semantic_typer_type),
            score_field=config.policy.score_field,
            operator=config.policy.operator,
            margin_threshold=config.policy.margin_threshold,
            preserve_baseline_otherwise=config.policy.preserve_baseline_otherwise,
            use_baseline_type_as_post_inference_policy_condition_only=config.policy.use_baseline_type_as_post_inference_policy_condition_only,
            selection_rule=config.policy.selection_rule,
            selected_plateau_thresholds=config.policy.selected_plateau_thresholds,
            candidate_fingerprint=candidate_fingerprint,
        ).model_dump(mode="json")
        add("frozen_policy_recomputes_exactly", stored_policy == expected_policy, "frozen_policy")
        add("development_reproduction_recomputes_exactly", stored_reproduction == recomputed_reproduction, "development_reproduction")
        add("candidate_fingerprint", stored_manifest.get("h2_candidate_fingerprint") == candidate_fingerprint == stored_policy.get("candidate_fingerprint"), candidate_fingerprint)
        add("semantic_typer_fingerprint", stored_manifest.get("semantic_typer_fingerprint") == parents["h1_fingerprint"] == stored_policy.get("semantic_typer_fingerprint"), parents["h1_fingerprint"])
    else:
        recomputed_reproduction = None
        candidate_fingerprint = None

    add("manifest_schema", stored_manifest.get("schema_version") == MANIFEST_SCHEMA_VERSION, stored_manifest.get("schema_version"))
    add("summary_schema", stored_summary.get("schema_version") == SUMMARY_SCHEMA_VERSION, stored_summary.get("schema_version"))
    add("candidate_id", stored_manifest.get("candidate_id") == config.candidate.candidate_id == stored_summary.get("candidate_id"), stored_manifest.get("candidate_id"))
    add("revision_id", stored_manifest.get("revision_analysis_id") == config.lineage.revision_analysis_id, stored_manifest.get("revision_analysis_id"))
    add("revision_manifest_hash", stored_manifest.get("revision_manifest_sha256") == _sha256_file(revision_analysis_dir / "manifest.json"), stored_manifest.get("revision_manifest_sha256"))
    add("revision_summary_hash", stored_manifest.get("revision_summary_sha256") == _sha256_file(revision_analysis_dir / "summary.json"), stored_manifest.get("revision_summary_sha256"))
    add("revision_policy_hash", stored_manifest.get("revision_selected_policy_sha256") == _sha256_file(revision_analysis_dir / "selected_policy.json"), stored_manifest.get("revision_selected_policy_sha256"))
    add("revision_outcomes_hash", stored_manifest.get("revision_policy_case_outcomes_sha256") == _sha256_file(revision_analysis_dir / "policy_case_outcomes.jsonl"), stored_manifest.get("revision_policy_case_outcomes_sha256"))
    add("evaluation_manifest_hash", stored_manifest.get("parent_evaluation_manifest_sha256") == _sha256_file(evaluation_dir / "manifest.json"), stored_manifest.get("parent_evaluation_manifest_sha256"))
    add("prediction_manifest_hash", stored_manifest.get("parent_prediction_manifest_sha256") == _sha256_file(prediction_dir / "manifest.json"), stored_manifest.get("parent_prediction_manifest_sha256"))
    add("policy_frozen", stored_manifest.get("policy_frozen") is True and stored_summary.get("policy_frozen") is True, stored_manifest.get("policy_frozen"))
    add("development_reproduction_true", stored_manifest.get("development_reproduction_executed") is True and stored_summary.get("development_reproduction_executed") is True, stored_manifest.get("development_reproduction_executed"))
    add("new_model_inference_false", stored_manifest.get("new_model_inference_executed") is False and stored_summary.get("new_model_inference_executed") is False, stored_manifest.get("new_model_inference_executed"))
    add("model_threshold_tuning_false", stored_manifest.get("model_inference_threshold_tuning_executed") is False and stored_summary.get("model_inference_threshold_tuning_executed") is False, stored_manifest.get("model_inference_threshold_tuning_executed"))
    add("policy_calibration_false", stored_manifest.get("policy_margin_threshold_calibration_executed") is False and stored_summary.get("policy_margin_threshold_calibration_executed") is False, stored_manifest.get("policy_margin_threshold_calibration_executed"))
    add("independent_acceptance_false", stored_manifest.get("independent_acceptance_executed") is False and stored_summary.get("independent_acceptance_executed") is False, stored_manifest.get("independent_acceptance_executed"))
    add("canonical_not_mutated", stored_manifest.get("canonical_truth_mutated") is False and stored_summary.get("canonical_truth_mutated") is False, stored_manifest.get("canonical_truth_mutated"))
    add("production_not_selected", stored_manifest.get("production_extractor_selected") is False and stored_summary.get("production_extractor_selected") is False, stored_manifest.get("production_extractor_selected"))
    add("full_corpus_false", stored_manifest.get("full_corpus_build_authorized") is False and stored_summary.get("full_corpus_build_authorized") is False, stored_manifest.get("full_corpus_build_authorized"))
    add("future_heldout_required", stored_manifest.get("future_candidate_requires_new_independent_heldout") is True and stored_summary.get("future_candidate_requires_new_independent_heldout") is True, stored_manifest.get("future_candidate_requires_new_independent_heldout"))
    if recomputed_reproduction is not None:
        add("summary_reproduction", stored_summary.get("development_reproduction") == recomputed_reproduction, "summary.development_reproduction")

    checksum_lines = [line.strip() for line in (frozen_policy_dir / "checksums.txt").read_text(encoding="utf-8").splitlines() if line.strip()]
    parsed_checksums: dict[str, str] = {}
    for line in checksum_lines:
        digest, name = line.split("  ", 1)
        parsed_checksums[name] = digest
    for name in REQUIRED_OUTPUT_FILES:
        if name != "checksums.txt":
            add(f"checksum:{name}", parsed_checksums.get(name) == _sha256_file(frozen_policy_dir / name), name)

    failed = sum(not item[1] for item in checks)
    summary = {
        "report": REPORT_NAME,
        "validation_scope": "h2_frozen_policy",
        "freeze_id": stored_manifest.get("freeze_id"),
        "candidate_id": stored_manifest.get("candidate_id"),
        "margin_threshold": stored_policy.get("margin_threshold"),
        "policy_frozen": stored_manifest.get("policy_frozen") is True,
        "total_checks": len(checks),
        "required_failed_count": failed,
        "next_slice": stored_summary.get("next_slice") if failed == 0 else "fix_h2_frozen_policy_validation_failures",
    }
    return checks, summary


__all__ = [
    "REPORT_NAME",
    "ScientificEntitySemanticTyperH2FrozenPolicyError",
    "apply_h2_selective_override",
    "h2_candidate_fingerprint",
    "h2_candidate_identity_payload",
    "plan_or_execute_h2_frozen_policy",
    "reproduce_h2_development_policy",
    "validate_h2_frozen_policy",
]
