from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from radar_core.contracts.scientific_entity_evidence import (
    ScientificEntityEvidenceManifest,
    ScientificEntityMentionEvidence,
    ScientificEntitySourceField,
    validate_mention_evidence,
)
from radar_core.contracts.scientific_entity_gliner_calibration import (
    ScientificEntityCalibrationTrialStage,
    ScientificEntityThresholdPolicy,
    build_calibration_trial_id,
)
from radar_core.contracts.scientific_entity_semantic_prompt_threshold_calibration import (
    CalibrationDiagnostics,
    CalibrationTrial,
    DIAGNOSTICS_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    SELECTED_POLICY_SCHEMA_VERSION,
    SelectedPolicy,
    SemanticPromptThresholdCalibrationConfig,
    SemanticPromptThresholdCalibrationError,
    load_semantic_prompt_threshold_calibration_config,
)
from radar_core.entities.scientific_entity_evaluation import (
    evaluate_mentions,
    load_evaluation_config,
)
from radar_core.entities.scientific_entity_gliner_calibration import filter_predictions
from radar_core.entities.scientific_entity_semantic_prompt_comparison import (
    _diagnostics,
    _load_canonical,
    _load_source_baseline,
    _read_json,
    _read_jsonl,
    _resolve,
    _source_text,
    _summary_from_result,
)
from radar_core.entities.scientific_entity_semantic_prompt_development import (
    validate_semantic_prompt_development_package,
)


REPORT_NAME = "scientific_entity_semantic_prompt_threshold_calibration_v02b"
DEFAULT_CONFIG_PATH = Path(
    "configs/scientific_entity_semantic_prompt_threshold_calibration_v0.2b.yaml"
)
REQUIRED_FILES = (
    "manifest.json",
    "trials.jsonl",
    "selected_policy.json",
    "diagnostics.json",
    "README.md",
    "checksums.txt",
)
CHECKSUM_FILES = REQUIRED_FILES[:-1]


class SemanticPromptThresholdCalibrationBuildError(RuntimeError):
    """Raised when v0.2b calibration cannot be prepared reproducibly."""


@dataclass(frozen=True)
class PreparedCalibration:
    report: dict[str, Any]
    manifest: dict[str, Any]
    trials: tuple[CalibrationTrial, ...]
    selected_policy: SelectedPolicy
    diagnostics: CalibrationDiagnostics
    readme: str


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_semantic_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def threshold_calibration_config_sha256(
    config: SemanticPromptThresholdCalibrationConfig,
) -> str:
    return hashlib.sha256(
        _canonical_semantic_json(config.model_dump(mode="json")).encode("utf-8")
    ).hexdigest()


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(rows: Sequence[Mapping[str, Any]]) -> bytes:
    return "".join(
        json.dumps(dict(row), ensure_ascii=False, separators=(",", ":")) + "\n"
        for row in rows
    ).encode("utf-8")


def _project_path(root: Path, path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(root.resolve())).replace("\\", "/")
    except ValueError:
        return str(resolved).replace("\\", "/")


def _verify_file_sha(path: Path, expected: str, label: str) -> None:
    actual = _sha256_file(path)
    if actual != expected:
        raise SemanticPromptThresholdCalibrationBuildError(
            f"{label} SHA-256 mismatch: expected={expected} actual={actual}"
        )


def _load_raw_predictions(
    *,
    raw_build_dir: Path,
    documents: Mapping[str, Any],
    config: SemanticPromptThresholdCalibrationConfig,
) -> tuple[ScientificEntityEvidenceManifest, tuple[ScientificEntityMentionEvidence, ...]]:
    manifest_path = raw_build_dir / "manifest.json"
    manifest = ScientificEntityEvidenceManifest.model_validate(_read_json(manifest_path))
    if manifest.build_id != config.lineage.raw_build_id:
        raise SemanticPromptThresholdCalibrationBuildError("raw build_id drifted")
    if manifest.extractor_fingerprint != config.lineage.raw_extractor_fingerprint:
        raise SemanticPromptThresholdCalibrationBuildError(
            "raw extractor_fingerprint drifted"
        )
    if manifest.canonical_input.document_count != config.lineage.expected_document_count:
        raise SemanticPromptThresholdCalibrationBuildError(
            "raw canonical document_count drifted"
        )
    if manifest.mention_count != config.lineage.expected_raw_prediction_count:
        raise SemanticPromptThresholdCalibrationBuildError(
            "raw prediction count drifted"
        )
    mentions_path = raw_build_dir / manifest.mentions_file
    _verify_file_sha(mentions_path, manifest.mentions_sha256, "raw mentions")
    predictions: list[ScientificEntityMentionEvidence] = []
    for row in _read_jsonl(mentions_path):
        prediction = ScientificEntityMentionEvidence.model_validate(row)
        document = documents.get(prediction.canonical_id)
        if document is None:
            raise SemanticPromptThresholdCalibrationBuildError(
                f"raw prediction outside development package: {prediction.canonical_id}"
            )
        predictions.append(
            validate_mention_evidence(
                prediction,
                source_text=_source_text(document, prediction.source_field),
                extractor=manifest.extractor,
                manifest=manifest,
            )
        )
    if len(predictions) != config.lineage.expected_raw_prediction_count:
        raise SemanticPromptThresholdCalibrationBuildError(
            "raw mentions file count drifted"
        )
    return manifest, tuple(predictions)



def _trial_evaluation_id(
    *,
    calibration_id: str,
    trial_id: str,
    split: str,
) -> str:
    """Build a short deterministic evaluation id accepted by the evaluation contract."""
    digest = hashlib.sha256(
        f"{calibration_id}\n{trial_id}\n{split}".encode("utf-8")
    ).hexdigest()[:32]
    return f"semantic-prompt-v02b-{split}-{digest}"


def evaluate_semantic_guardrails(
    *,
    config: SemanticPromptThresholdCalibrationConfig,
    diagnostics: Mapping[str, Any],
) -> dict[str, dict[str, object]]:
    sinks = diagnostics["predicted_type_mismatch_sinks"]
    max_sink = max(int(value) for value in sinks.values()) if sinks else 0
    guard = config.semantic_guardrails
    values = {
        "maximum_model_to_method_count": (
            int(diagnostics["type_confusions"].get("model->method", 0)),
            int(guard.maximum_model_to_method_count),
        ),
        "maximum_method_to_task_count": (
            int(diagnostics["type_confusions"].get("method->task", 0)),
            int(guard.maximum_method_to_task_count),
        ),
        "maximum_total_type_mismatch_count": (
            int(diagnostics["type_mismatch_total"]),
            int(guard.maximum_total_type_mismatch_count),
        ),
        "maximum_method_semantic_sink_count": (
            int(sinks.get("method", 0)),
            int(guard.maximum_method_semantic_sink_count),
        ),
        "maximum_any_predicted_type_mismatch_sink_count": (
            max_sink,
            int(guard.maximum_any_predicted_type_mismatch_sink_count),
        ),
    }
    return {
        name: {
            "observed": observed,
            "threshold": threshold,
            "passed": observed <= threshold,
        }
        for name, (observed, threshold) in values.items()
    }


def _metric_value(summary: Mapping[str, Any], *path: str) -> float | None:
    value: Any = summary
    for key in path:
        value = value[key]
    return None if value is None else float(value)


def _trial_sort_key(row: CalibrationTrial) -> tuple[Any, ...]:
    def desc(value: float | None) -> float:
        return -(-1.0 if value is None else float(value))

    return (
        desc(row.combined_exact_f1),
        desc(row.combined_relaxed_f1),
        desc(row.combined_exact_recall),
        -(row.title_threshold + row.abstract_threshold),
        -row.title_threshold,
        -row.abstract_threshold,
        row.trial_id,
    )


def select_trial(trials: Sequence[CalibrationTrial]) -> CalibrationTrial:
    eligible = [row for row in trials if row.eligible_for_selection]
    if not eligible:
        raise SemanticPromptThresholdCalibrationBuildError(
            "no threshold trial satisfies the frozen semantic guardrails"
        )
    return sorted(eligible, key=_trial_sort_key)[0]


def evaluate_selected_policy_gate(
    *,
    config: SemanticPromptThresholdCalibrationConfig,
    selected: CalibrationTrial,
) -> dict[str, dict[str, object]]:
    consumed_f1 = selected.consumed_heldout_exact_f1
    combined_f1 = selected.combined_exact_f1
    guardrails_passed = selected.semantic_guardrails_passed
    return {
        "minimum_consumed_heldout_exact_f1": {
            "observed": consumed_f1,
            "threshold": config.decision.selected_policy_minimum_consumed_heldout_exact_f1,
            "passed": consumed_f1 is not None
            and consumed_f1
            >= config.decision.selected_policy_minimum_consumed_heldout_exact_f1,
        },
        "minimum_combined_dev_exact_f1": {
            "observed": combined_f1,
            "threshold": config.decision.selected_policy_minimum_combined_dev_exact_f1,
            "passed": combined_f1 is not None
            and combined_f1 >= config.decision.selected_policy_minimum_combined_dev_exact_f1,
        },
        "semantic_guardrails": {
            "observed": guardrails_passed,
            "threshold": True,
            "passed": guardrails_passed,
        },
    }


def _prepare_calibration(
    *,
    project_root: Path,
    config_path: Path,
    development_package_dir: Path,
    raw_build_dir: Path,
    v02a_comparison_dir: Path,
    calibration_id: str,
    generated_at_utc: datetime,
) -> PreparedCalibration:
    root = project_root.resolve()
    config = load_semantic_prompt_threshold_calibration_config(config_path.resolve())
    candidate_design_path = _resolve(root, config.lineage.candidate_design_config_path)
    evaluation_config_path = _resolve(root, config.lineage.evaluation_config_path)
    evaluation_config = load_evaluation_config(evaluation_config_path)

    package_validation = validate_semantic_prompt_development_package(
        project_root=root,
        design_config_path=candidate_design_path,
        package_dir=development_package_dir,
    )
    if package_validation["package_id"] != config.lineage.development_package_id:
        raise SemanticPromptThresholdCalibrationBuildError(
            "development package_id drifted"
        )
    if package_validation["combined_document_count"] != config.lineage.expected_document_count:
        raise SemanticPromptThresholdCalibrationBuildError(
            "development document count drifted"
        )

    comparison_manifest_path = v02a_comparison_dir / "manifest.json"
    comparison_manifest = _read_json(comparison_manifest_path)
    if comparison_manifest.get("comparison_id") != config.lineage.v02a_comparison_id:
        raise SemanticPromptThresholdCalibrationBuildError("v0.2a comparison_id drifted")
    gate_path = v02a_comparison_dir / str(comparison_manifest.get("gate_decision_file"))
    _verify_file_sha(
        gate_path,
        str(comparison_manifest.get("gate_decision_sha256")),
        "v0.2a gate decision",
    )
    v02a_gate = _read_json(gate_path)
    if v02a_gate.get("candidate_promising_for_next_development_slice") is not False:
        raise SemanticPromptThresholdCalibrationBuildError(
            "v0.2b requires the recorded v0.2a hard-gate failure"
        )

    package_manifest = _read_json(development_package_dir / "manifest.json")
    documents, membership = _load_canonical(development_package_dir)
    raw_manifest, raw_predictions = _load_raw_predictions(
        raw_build_dir=raw_build_dir,
        documents=documents,
        config=config,
    )
    if raw_manifest.canonical_input.sha256 != package_manifest["canonical_documents_sha256"]:
        raise SemanticPromptThresholdCalibrationBuildError(
            "raw build canonical input does not match development package"
        )

    source_rows = package_manifest.get("sources")
    if not isinstance(source_rows, list) or len(source_rows) != 2:
        raise SemanticPromptThresholdCalibrationBuildError(
            "development package must record two source evaluations"
        )
    source_by_split = {str(row["split"]): row for row in source_rows}
    split_ids = {
        split: {
            canonical_id
            for canonical_id, member_split in membership.items()
            if member_split == split
        }
        for split in ("old_dev_24", "consumed_v01_heldout_48")
    }
    baselines = {
        split: _load_source_baseline(
            root=root,
            source_descriptor=source_by_split[split],
            documents=documents,
            expected_ids=split_ids[split],
        )
        for split in ("old_dev_24", "consumed_v01_heldout_48")
    }
    combined_references = (
        baselines["old_dev_24"].references
        + baselines["consumed_v01_heldout_48"].references
    )
    if len(combined_references) != config.lineage.expected_reference_mention_count:
        raise SemanticPromptThresholdCalibrationBuildError(
            "combined reference count drifted"
        )

    trials: list[CalibrationTrial] = []
    inherited_trial_id: str | None = None
    for title_threshold in config.search.title_thresholds:
        for abstract_threshold in config.search.abstract_thresholds:
            policy = ScientificEntityThresholdPolicy(
                default_threshold=config.search.input_threshold,
                source_field_thresholds={
                    ScientificEntitySourceField.TITLE: title_threshold,
                    ScientificEntitySourceField.ABSTRACT: abstract_threshold,
                },
                entity_type_thresholds={},
            )
            trial_id = build_calibration_trial_id(
                calibration_id=calibration_id,
                stage=ScientificEntityCalibrationTrialStage.SOURCE_PAIR,
                policy=policy,
            )
            selected = filter_predictions(
                raw_predictions,
                policy=policy,
                input_threshold=config.search.input_threshold,
            )
            predictions_by_split = {
                split: tuple(
                    row for row in selected if row.canonical_id in split_ids[split]
                )
                for split in ("old_dev_24", "consumed_v01_heldout_48")
            }
            if sum(len(rows) for rows in predictions_by_split.values()) != len(selected):
                raise SemanticPromptThresholdCalibrationBuildError(
                    "trial predictions do not partition into development splits"
                )

            old_result = evaluate_mentions(
                evaluation_id=_trial_evaluation_id(
                    calibration_id=calibration_id,
                    trial_id=trial_id,
                    split="old-dev-24",
                ),
                document_count=24,
                references=baselines["old_dev_24"].references,
                predictions=predictions_by_split["old_dev_24"],
                config=evaluation_config,
            )
            held_result = evaluate_mentions(
                evaluation_id=_trial_evaluation_id(
                    calibration_id=calibration_id,
                    trial_id=trial_id,
                    split="consumed-48",
                ),
                document_count=48,
                references=baselines["consumed_v01_heldout_48"].references,
                predictions=predictions_by_split["consumed_v01_heldout_48"],
                config=evaluation_config,
            )
            combined_result = evaluate_mentions(
                evaluation_id=_trial_evaluation_id(
                    calibration_id=calibration_id,
                    trial_id=trial_id,
                    split="combined-72",
                ),
                document_count=72,
                references=combined_references,
                predictions=selected,
                config=evaluation_config,
            )
            old_summary = _summary_from_result(old_result)
            held_summary = _summary_from_result(held_result)
            combined_summary = _summary_from_result(combined_result)
            held_diagnostics = _diagnostics(held_result.errors)
            semantic_rows = evaluate_semantic_guardrails(
                config=config,
                diagnostics=held_diagnostics,
            )
            semantic_pass = all(bool(row["passed"]) for row in semantic_rows.values())
            is_inherited = (
                title_threshold == config.search.inherited_v02a_policy.title
                and abstract_threshold == config.search.inherited_v02a_policy.abstract
            )
            if is_inherited:
                inherited_trial_id = trial_id

            trials.append(
                CalibrationTrial(
                    calibration_id=calibration_id,
                    trial_id=trial_id,
                    title_threshold=title_threshold,
                    abstract_threshold=abstract_threshold,
                    is_inherited_v02a_policy=is_inherited,
                    selected_prediction_count=len(selected),
                    old_dev_prediction_count=len(predictions_by_split["old_dev_24"]),
                    consumed_heldout_prediction_count=len(
                        predictions_by_split["consumed_v01_heldout_48"]
                    ),
                    old_dev_exact_f1=_metric_value(old_summary, "overall", "exact", "f1"),
                    consumed_heldout_exact_f1=_metric_value(
                        held_summary, "overall", "exact", "f1"
                    ),
                    consumed_heldout_relaxed_f1=_metric_value(
                        held_summary, "overall", "relaxed", "f1"
                    ),
                    combined_exact_precision=_metric_value(
                        combined_summary, "overall", "exact", "precision"
                    ),
                    combined_exact_recall=_metric_value(
                        combined_summary, "overall", "exact", "recall"
                    ),
                    combined_exact_f1=_metric_value(
                        combined_summary, "overall", "exact", "f1"
                    ),
                    combined_relaxed_f1=_metric_value(
                        combined_summary, "overall", "relaxed", "f1"
                    ),
                    model_to_method_count=int(
                        held_diagnostics["type_confusions"].get("model->method", 0)
                    ),
                    method_to_task_count=int(
                        held_diagnostics["type_confusions"].get("method->task", 0)
                    ),
                    total_type_mismatch_count=int(
                        held_diagnostics["type_mismatch_total"]
                    ),
                    method_semantic_sink_count=int(
                        held_diagnostics["predicted_type_mismatch_sinks"].get(
                            "method", 0
                        )
                    ),
                    max_predicted_type_mismatch_sink_count=max(
                        int(value)
                        for value in held_diagnostics[
                            "predicted_type_mismatch_sinks"
                        ].values()
                    ),
                    semantic_guardrails_passed=semantic_pass,
                    eligible_for_selection=semantic_pass,
                )
            )

    if len(trials) != config.search.expected_trial_count:
        raise SemanticPromptThresholdCalibrationBuildError(
            "computed threshold trial count drifted"
        )
    if len({row.trial_id for row in trials}) != len(trials):
        raise SemanticPromptThresholdCalibrationBuildError("duplicate trial_id")
    if inherited_trial_id is None:
        raise SemanticPromptThresholdCalibrationBuildError(
            "inherited v0.2a policy missing from threshold grid"
        )

    selected = select_trial(trials)
    hard_gates = evaluate_selected_policy_gate(config=config, selected=selected)
    all_hard_gates = all(bool(row["passed"]) for row in hard_gates.values())
    desirable_threshold = (
        config.decision.selected_policy_minimum_consumed_heldout_relaxed_f1_desirable
    )
    desirable_signals = {
        "minimum_consumed_heldout_relaxed_f1": {
            "observed": selected.consumed_heldout_relaxed_f1,
            "threshold": desirable_threshold,
            "passed": (
                selected.consumed_heldout_relaxed_f1 is not None
                and selected.consumed_heldout_relaxed_f1 >= desirable_threshold
            ),
        }
    }
    selected_policy = SelectedPolicy(
        calibration_id=calibration_id,
        selected_trial_id=selected.trial_id,
        title_threshold=selected.title_threshold,
        abstract_threshold=selected.abstract_threshold,
        selection_objective=config.selection.primary_objective,
        hard_gates=hard_gates,
        desirable_signals=desirable_signals,
        all_hard_gates_passed=all_hard_gates,
        candidate_promising_for_future_freeze=all_hard_gates,
    )
    inherited = next(row for row in trials if row.trial_id == inherited_trial_id)
    diagnostics = CalibrationDiagnostics(
        calibration_id=calibration_id,
        trial_count=35,
        eligible_trial_count=sum(row.eligible_for_selection for row in trials),
        inherited_v02a_trial_id=inherited_trial_id,
        inherited_v02a_trial_eligible=inherited.eligible_for_selection,
        selected_trial_id=selected.trial_id,
        selected_trial_is_boundary_title_floor=(
            selected.title_threshold == min(config.search.title_thresholds)
        ),
        selected_trial_is_boundary_abstract_floor=(
            selected.abstract_threshold == min(config.search.abstract_thresholds)
        ),
        raw_input_floor_may_be_binding=(
            selected.title_threshold == config.search.input_threshold
            or selected.abstract_threshold == config.search.input_threshold
        ),
    )

    trials_bytes = _jsonl_bytes(
        [row.model_dump(mode="json") for row in trials]
    )
    selected_bytes = _json_bytes(selected_policy.model_dump(mode="json"))
    diagnostics_bytes = _json_bytes(diagnostics.model_dump(mode="json"))
    config_sha = threshold_calibration_config_sha256(config)
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "calibration_id": calibration_id,
        "candidate_id": config.lineage.candidate_id,
        "generated_at_utc": generated_at_utc.isoformat().replace("+00:00", "Z"),
        "config_path": _project_path(root, config_path),
        "config_sha256": config_sha,
        "development_package_id": config.lineage.development_package_id,
        "development_package_manifest_sha256": _sha256_file(
            development_package_dir / "manifest.json"
        ),
        "raw_build_id": config.lineage.raw_build_id,
        "raw_build_manifest_sha256": _sha256_file(raw_build_dir / "manifest.json"),
        "raw_mentions_sha256": raw_manifest.mentions_sha256,
        "v02a_comparison_id": config.lineage.v02a_comparison_id,
        "v02a_comparison_manifest_sha256": _sha256_file(comparison_manifest_path),
        "document_count": 72,
        "reference_mention_count": len(combined_references),
        "raw_prediction_count": len(raw_predictions),
        "trial_count": len(trials),
        "eligible_trial_count": diagnostics.eligible_trial_count,
        "selected_trial_id": selected.trial_id,
        "selected_title_threshold": selected.title_threshold,
        "selected_abstract_threshold": selected.abstract_threshold,
        "candidate_promising_for_future_freeze": all_hard_gates,
        "trials_file": "trials.jsonl",
        "trials_sha256": hashlib.sha256(trials_bytes).hexdigest(),
        "selected_policy_file": "selected_policy.json",
        "selected_policy_sha256": hashlib.sha256(selected_bytes).hexdigest(),
        "diagnostics_file": "diagnostics.json",
        "diagnostics_sha256": hashlib.sha256(diagnostics_bytes).hexdigest(),
        "model_inference_executed": False,
        "model_downloaded": False,
        "prompt_changes_executed": False,
        "threshold_search_executed": True,
        "fresh_heldout_consumed": False,
        "canonical_truth_mutated": False,
        "may_be_used_as_reconcile_input": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "publication_ready": False,
        "future_v02_acceptance_requires_new_disjoint_heldout": True,
        "next_slice": (
            "materialize_selected_v02b_policy_and_controlled_comparison"
            if all_hard_gates
            else "reject_threshold_hypothesis_and_choose_next_bounded_extractor_hypothesis"
        ),
    }
    readme = "\n".join(
        [
            "# Scientific Entity Semantic Prompt Threshold Calibration v0.2b",
            "",
            f"calibration_id = `{calibration_id}`",
            f"trial_count = `{len(trials)}`",
            f"eligible_trial_count = `{diagnostics.eligible_trial_count}`",
            f"selected_trial_id = `{selected.trial_id}`",
            f"selected_title_threshold = `{selected.title_threshold}`",
            f"selected_abstract_threshold = `{selected.abstract_threshold}`",
            f"candidate_promising_for_future_freeze = `{str(all_hard_gates).lower()}`",
            "",
            "This artifact searches only the frozen 35 source-field threshold pairs over",
            "the existing v0.2a raw predictions. It does not run GLiNER, change prompts,",
            "consume a fresh held-out set, mutate canonical truth, or authorize production.",
            "",
        ]
    )
    report = {
        "report": REPORT_NAME,
        "ok": True,
        "calibration_id": calibration_id,
        "document_count": 72,
        "reference_mention_count": len(combined_references),
        "raw_prediction_count": len(raw_predictions),
        "trial_count": len(trials),
        "eligible_trial_count": diagnostics.eligible_trial_count,
        "selected_trial_id": selected.trial_id,
        "selected_title_threshold": selected.title_threshold,
        "selected_abstract_threshold": selected.abstract_threshold,
        "selected_combined_exact_f1": selected.combined_exact_f1,
        "selected_consumed_heldout_exact_f1": selected.consumed_heldout_exact_f1,
        "selected_model_to_method_count": selected.model_to_method_count,
        "selected_method_to_task_count": selected.method_to_task_count,
        "selected_total_type_mismatch_count": selected.total_type_mismatch_count,
        "selected_method_semantic_sink_count": selected.method_semantic_sink_count,
        "all_hard_gates_passed": all_hard_gates,
        "candidate_promising_for_future_freeze": all_hard_gates,
        "raw_input_floor_may_be_binding": diagnostics.raw_input_floor_may_be_binding,
        "model_inference_executed": False,
        "prompt_changes_executed": False,
        "threshold_search_executed": True,
        "fresh_heldout_consumed": False,
        "canonical_truth_mutated": False,
        "full_corpus_build_authorized": False,
        "next_slice": manifest["next_slice"],
    }
    return PreparedCalibration(
        report=report,
        manifest=manifest,
        trials=tuple(trials),
        selected_policy=selected_policy,
        diagnostics=diagnostics,
        readme=readme,
    )


def _default_calibration_id(generated_at_utc: datetime) -> str:
    return (
        "scientific-entity-semantic-prompt-threshold-calibration-v0.2b-"
        + generated_at_utc.strftime("%Y%m%dT%H%M%S%fZ")
    )


def build_semantic_prompt_threshold_calibration(
    *,
    project_root: Path,
    config_path: Path,
    development_package_dir: Path,
    raw_build_dir: Path,
    v02a_comparison_dir: Path,
    output_root: Path | None = None,
    calibration_id: str | None = None,
    execute: bool = False,
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or datetime.now(timezone.utc)
    if generated.tzinfo is None or generated.utcoffset() != timezone.utc.utcoffset(generated):
        raise SemanticPromptThresholdCalibrationBuildError(
            "generated_at_utc must be timezone-aware UTC"
        )
    config = load_semantic_prompt_threshold_calibration_config(config_path.resolve())
    selected_id = calibration_id or _default_calibration_id(generated)
    selected_output_root = output_root or _resolve(project_root, config.outputs.root)
    output_dir = selected_output_root.resolve() / selected_id
    if execute and output_dir.exists():
        raise FileExistsError(
            f"immutable threshold calibration already exists: {output_dir}"
        )

    prepared = _prepare_calibration(
        project_root=project_root,
        config_path=config_path,
        development_package_dir=development_package_dir,
        raw_build_dir=raw_build_dir,
        v02a_comparison_dir=v02a_comparison_dir,
        calibration_id=selected_id,
        generated_at_utc=generated,
    )

    if execute:
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(
            tempfile.mkdtemp(prefix=f".{selected_id}.tmp-", dir=output_dir.parent)
        )
        try:
            (staging / "manifest.json").write_bytes(_json_bytes(prepared.manifest))
            (staging / "trials.jsonl").write_bytes(
                _jsonl_bytes(
                    [row.model_dump(mode="json") for row in prepared.trials]
                )
            )
            (staging / "selected_policy.json").write_bytes(
                _json_bytes(prepared.selected_policy.model_dump(mode="json"))
            )
            (staging / "diagnostics.json").write_bytes(
                _json_bytes(prepared.diagnostics.model_dump(mode="json"))
            )
            (staging / "README.md").write_text(
                prepared.readme, encoding="utf-8", newline="\n"
            )
            checksum_lines = [
                f"{_sha256_file(staging / filename)}  {filename}"
                for filename in CHECKSUM_FILES
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

    report = dict(prepared.report)
    report.update(
        {
            "mode": "execute" if execute else "plan",
            "phase_complete": execute,
            "output_dir": str(output_dir).replace("\\", "/"),
        }
    )
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


def validate_semantic_prompt_threshold_calibration(
    *,
    project_root: Path,
    config_path: Path,
    calibration_dir: Path,
    development_package_dir: Path,
    raw_build_dir: Path,
    v02a_comparison_dir: Path,
) -> dict[str, Any]:
    config = load_semantic_prompt_threshold_calibration_config(config_path.resolve())
    resolved = calibration_dir.resolve()
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, details: str | None = None) -> None:
        checks.append({"name": name, "ok": bool(ok), "required": True, "details": details})

    add("calibration_directory_exists", resolved.is_dir(), str(resolved))
    if not resolved.is_dir():
        return _validation_report(checks=checks, manifest=None)

    actual_files = {path.name for path in resolved.iterdir() if path.is_file()}
    actual_dirs = {path.name for path in resolved.iterdir() if path.is_dir()}
    add("required_files_exact", actual_files == set(REQUIRED_FILES))
    add("nested_directories_absent", not actual_dirs)
    if actual_files != set(REQUIRED_FILES):
        return _validation_report(checks=checks, manifest=None)

    for filename in REQUIRED_FILES:
        ok, details = _text_is_utf8_lf(resolved / filename)
        add(f"utf8_lf::{filename}", ok, details)

    checksum_rows: dict[str, str] = {}
    try:
        for line in (resolved / "checksums.txt").read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            digest, filename = line.split("  ", 1)
            checksum_rows[filename] = digest
    except Exception as exc:
        add("checksums_parse", False, f"{type(exc).__name__}: {exc}")
        return _validation_report(checks=checks, manifest=None)
    add("checksum_file_set_exact", set(checksum_rows) == set(CHECKSUM_FILES))
    for filename in CHECKSUM_FILES:
        add(
            f"checksum_matches::{filename}",
            checksum_rows.get(filename) == _sha256_file(resolved / filename),
        )

    try:
        manifest = _read_json(resolved / "manifest.json")
        trials = tuple(
            CalibrationTrial.model_validate(row)
            for row in _read_jsonl(resolved / "trials.jsonl")
        )
        selected = SelectedPolicy.model_validate(_read_json(resolved / "selected_policy.json"))
        diagnostics = CalibrationDiagnostics.model_validate(_read_json(resolved / "diagnostics.json"))
        add("output_contracts_parse", True)
    except Exception as exc:
        add("output_contracts_parse", False, f"{type(exc).__name__}: {exc}")
        return _validation_report(checks=checks, manifest=None)

    add("manifest_schema_version", manifest.get("schema_version") == MANIFEST_SCHEMA_VERSION)
    add("directory_matches_calibration_id", resolved.name == manifest.get("calibration_id"))
    add(
        "config_sha256_matches",
        manifest.get("config_sha256") == threshold_calibration_config_sha256(config),
    )
    add("candidate_id_matches", manifest.get("candidate_id") == config.lineage.candidate_id)
    add(
        "development_package_id_matches",
        manifest.get("development_package_id") == config.lineage.development_package_id,
    )
    add("raw_build_id_matches", manifest.get("raw_build_id") == config.lineage.raw_build_id)
    add(
        "v02a_comparison_id_matches",
        manifest.get("v02a_comparison_id") == config.lineage.v02a_comparison_id,
    )
    add("document_count_matches", manifest.get("document_count") == 72)
    add(
        "reference_mention_count_matches",
        manifest.get("reference_mention_count") == config.lineage.expected_reference_mention_count,
    )
    add(
        "raw_prediction_count_matches",
        manifest.get("raw_prediction_count") == config.lineage.expected_raw_prediction_count,
    )
    add("trial_count_matches", len(trials) == config.search.expected_trial_count == 35)
    add("trial_ids_unique", len({row.trial_id for row in trials}) == len(trials))
    add(
        "grid_exact",
        {(row.title_threshold, row.abstract_threshold) for row in trials}
        == {
            (title, abstract)
            for title in config.search.title_thresholds
            for abstract in config.search.abstract_thresholds
        },
    )
    add("exactly_one_inherited_trial", sum(row.is_inherited_v02a_policy for row in trials) == 1)
    trial_by_id = {row.trial_id: row for row in trials}
    add("selected_trial_exists", selected.selected_trial_id in trial_by_id)
    add(
        "selected_trial_is_eligible",
        selected.selected_trial_id in trial_by_id
        and trial_by_id[selected.selected_trial_id].eligible_for_selection,
    )
    if any(row.eligible_for_selection for row in trials):
        recomputed_selected = select_trial(trials)
        add("selected_trial_recomputed", recomputed_selected.trial_id == selected.selected_trial_id)
    else:
        add("selected_trial_recomputed", False, "no eligible trial")
    add("diagnostics_trial_count", diagnostics.trial_count == 35)
    add(
        "diagnostics_eligible_count",
        diagnostics.eligible_trial_count == sum(row.eligible_for_selection for row in trials),
    )
    add("diagnostics_selected_trial", diagnostics.selected_trial_id == selected.selected_trial_id)
    add(
        "selected_gate_recomputed",
        selected.hard_gates
        == evaluate_selected_policy_gate(
            config=config, selected=trial_by_id[selected.selected_trial_id]
        ),
    )
    add(
        "selected_promising_recomputed",
        selected.candidate_promising_for_future_freeze
        == all(bool(row["passed"]) for row in selected.hard_gates.values()),
    )
    required_false = (
        "model_inference_executed",
        "model_downloaded",
        "prompt_changes_executed",
        "fresh_heldout_consumed",
        "canonical_truth_mutated",
        "may_be_used_as_reconcile_input",
        "production_extractor_selected",
        "full_corpus_build_authorized",
        "publication_ready",
    )
    for key in required_false:
        add(f"safety_false::{key}", manifest.get(key) is False)
    add("threshold_search_executed", manifest.get("threshold_search_executed") is True)
    add(
        "fresh_heldout_requirement_preserved",
        manifest.get("future_v02_acceptance_requires_new_disjoint_heldout") is True,
    )

    add(
        "development_package_manifest_sha",
        manifest.get("development_package_manifest_sha256")
        == _sha256_file(development_package_dir / "manifest.json"),
    )
    add(
        "raw_build_manifest_sha",
        manifest.get("raw_build_manifest_sha256")
        == _sha256_file(raw_build_dir / "manifest.json"),
    )
    add(
        "v02a_comparison_manifest_sha",
        manifest.get("v02a_comparison_manifest_sha256")
        == _sha256_file(v02a_comparison_dir / "manifest.json"),
    )

    try:
        generated = datetime.fromisoformat(str(manifest["generated_at_utc"]).replace("Z", "+00:00"))
        with tempfile.TemporaryDirectory(prefix="semantic-prompt-v02b-validation-") as tmp:
            report = build_semantic_prompt_threshold_calibration(
                project_root=project_root,
                config_path=config_path,
                development_package_dir=development_package_dir,
                raw_build_dir=raw_build_dir,
                v02a_comparison_dir=v02a_comparison_dir,
                output_root=Path(tmp),
                calibration_id=str(manifest["calibration_id"]),
                execute=True,
                generated_at_utc=generated,
            )
            rebuilt = Path(report["output_dir"])
            mismatches = [
                filename
                for filename in REQUIRED_FILES
                if (resolved / filename).read_bytes() != (rebuilt / filename).read_bytes()
            ]
            add(
                "deterministic_byte_recomputation",
                not mismatches,
                None if not mismatches else f"mismatches={mismatches}",
            )
    except Exception as exc:
        add("deterministic_byte_recomputation", False, f"{type(exc).__name__}: {exc}")

    return _validation_report(checks=checks, manifest=manifest)


def _validation_report(
    *,
    checks: Sequence[Mapping[str, Any]],
    manifest: Mapping[str, Any] | None,
) -> dict[str, Any]:
    failed = [row for row in checks if row["required"] and not row["ok"]]
    selected_title = None if manifest is None else manifest.get("selected_title_threshold")
    selected_abstract = None if manifest is None else manifest.get("selected_abstract_threshold")
    promising = None if manifest is None else manifest.get("candidate_promising_for_future_freeze")
    return {
        "report": REPORT_NAME,
        "ok": not failed,
        "total_checks": len(checks),
        "required_failed_count": len(failed),
        "calibration_id": None if manifest is None else manifest.get("calibration_id"),
        "trial_count": None if manifest is None else manifest.get("trial_count"),
        "eligible_trial_count": None if manifest is None else manifest.get("eligible_trial_count"),
        "selected_title_threshold": selected_title,
        "selected_abstract_threshold": selected_abstract,
        "candidate_promising_for_future_freeze": promising,
        "model_inference_executed": False,
        "fresh_heldout_consumed": False,
        "canonical_truth_mutated": False,
        "full_corpus_build_authorized": False,
        "checks": list(checks),
        "next_slice": (
            None
            if failed or manifest is None
            else manifest.get("next_slice")
        ),
    }
