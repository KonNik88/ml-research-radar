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
    validate_mention_evidence,
)
from radar_core.contracts.scientific_entity_semantic_prompt_raw_floor_comparison import (
    COMPARISON_SCHEMA_VERSION,
    DIAGNOSTICS_SCHEMA_VERSION,
    GATE_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    PROGRESSION_SCHEMA_VERSION,
    RawFloorComparisonConfig,
    load_raw_floor_comparison_config,
)
from radar_core.contracts.scientific_entity_semantic_prompt_raw_floor_policy import (
    RawFloorPolicyDerivationManifest,
)
from radar_core.entities.scientific_entity_evaluation import evaluate_mentions, load_evaluation_config
from radar_core.entities.scientific_entity_semantic_prompt_comparison import (
    _aggregate_baselines,
    _diagnostics,
    _load_canonical,
    _load_source_baseline,
    _merge_diagnostics,
    _read_json,
    _read_jsonl,
    _resolve,
    _sha256_file,
    _source_text,
    _split_delta,
    _summary_from_baseline,
    _summary_from_result,
)
from radar_core.entities.scientific_entity_semantic_prompt_development import (
    validate_semantic_prompt_development_package,
)
from radar_core.entities.scientific_entity_semantic_prompt_raw_floor_policy import (
    validate_raw_floor_selected_policy_build,
)


REPORT_NAME = "scientific_entity_semantic_prompt_raw_floor_comparison_v02c"
DEFAULT_CONFIG_PATH = Path(
    "configs/scientific_entity_semantic_prompt_raw_floor_comparison_v0.2c.yaml"
)
DEFAULT_OUTPUT_ROOT = Path(
    "data/entities/scientific_entity_semantic_prompt_raw_floor_comparison/v0.2c"
)
REQUIRED_FILES = (
    "manifest.json",
    "comparison.json",
    "diagnostics.json",
    "progression.json",
    "gate_decision.json",
    "README.md",
    "checksums.txt",
)
CHECKSUM_FILES = REQUIRED_FILES[:-1]


class RawFloorComparisonBuildError(RuntimeError):
    """Raised when the v0.2c controlled comparison cannot be reproduced safely."""


@dataclass(frozen=True)
class PreparedComparison:
    report: dict[str, Any]
    manifest: dict[str, Any]
    comparison: dict[str, Any]
    diagnostics: dict[str, Any]
    progression: dict[str, Any]
    gate_decision: dict[str, Any]
    readme: str


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _jsonl_rows(path: Path) -> list[dict[str, Any]]:
    return _read_jsonl(path)


def _project_path(root: Path, path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(root.resolve())).replace("\\", "/")
    except ValueError:
        return str(resolved).replace("\\", "/")


def _safe_evaluation_id(comparison_id: str, split: str) -> str:
    digest = hashlib.sha256(f"{comparison_id}\n{split}".encode("utf-8")).hexdigest()[:32]
    return f"semantic-prompt-v02c-{split}-{digest}"


def _load_policy_predictions(
    *,
    policy_build_dir: Path,
    documents: Mapping[str, Any],
) -> tuple[
    ScientificEntityEvidenceManifest,
    RawFloorPolicyDerivationManifest,
    tuple[ScientificEntityMentionEvidence, ...],
]:
    manifest = ScientificEntityEvidenceManifest.model_validate(
        _read_json(policy_build_dir / "manifest.json")
    )
    derivation = RawFloorPolicyDerivationManifest.model_validate(
        _read_json(policy_build_dir / "derivation_manifest.json")
    )
    mentions_path = policy_build_dir / manifest.mentions_file
    if _sha256_file(mentions_path) != manifest.mentions_sha256:
        raise RawFloorComparisonBuildError("policy mentions checksum mismatch")
    predictions: list[ScientificEntityMentionEvidence] = []
    for row in _jsonl_rows(mentions_path):
        mention = ScientificEntityMentionEvidence.model_validate(row)
        document = documents.get(mention.canonical_id)
        if document is None:
            raise RawFloorComparisonBuildError(
                f"policy prediction outside development package: {mention.canonical_id}"
            )
        predictions.append(
            validate_mention_evidence(
                mention,
                source_text=_source_text(document, mention.source_field),
                extractor=manifest.extractor,
                manifest=manifest,
            )
        )
    if len(predictions) != manifest.mention_count:
        raise RawFloorComparisonBuildError("policy mention count drifted")
    return manifest, derivation, tuple(predictions)


def _verify_manifest_file(
    *,
    artifact_dir: Path,
    manifest: Mapping[str, Any],
    file_key: str,
    sha_key: str,
) -> Path:
    path = artifact_dir / str(manifest[file_key])
    if _sha256_file(path) != str(manifest[sha_key]):
        raise RawFloorComparisonBuildError(f"historical artifact checksum mismatch: {path}")
    return path


def _load_v02a_history(
    *,
    artifact_dir: Path,
    config: RawFloorComparisonConfig,
) -> dict[str, Any]:
    manifest = _read_json(artifact_dir / "manifest.json")
    if manifest.get("comparison_id") != config.historical_inputs.v02a_comparison_id:
        raise RawFloorComparisonBuildError("v0.2a historical comparison_id drifted")
    if artifact_dir.name != config.historical_inputs.v02a_comparison_id:
        raise RawFloorComparisonBuildError("v0.2a historical directory name drifted")
    comparison = _read_json(
        _verify_manifest_file(
            artifact_dir=artifact_dir,
            manifest=manifest,
            file_key="comparison_file",
            sha_key="comparison_sha256",
        )
    )
    diagnostics = _read_json(
        _verify_manifest_file(
            artifact_dir=artifact_dir,
            manifest=manifest,
            file_key="diagnostics_file",
            sha_key="diagnostics_sha256",
        )
    )
    return {
        "manifest": manifest,
        "comparison": comparison,
        "diagnostics": diagnostics,
    }


def _load_v02b_history(
    *,
    artifact_dir: Path,
    config: RawFloorComparisonConfig,
) -> dict[str, Any]:
    manifest = _read_json(artifact_dir / "manifest.json")
    if manifest.get("calibration_id") != config.historical_inputs.v02b_calibration_id:
        raise RawFloorComparisonBuildError("v0.2b historical calibration_id drifted")
    if artifact_dir.name != config.historical_inputs.v02b_calibration_id:
        raise RawFloorComparisonBuildError("v0.2b historical directory name drifted")
    selected_path = _verify_manifest_file(
        artifact_dir=artifact_dir,
        manifest=manifest,
        file_key="selected_policy_file",
        sha_key="selected_policy_sha256",
    )
    diagnostics_path = _verify_manifest_file(
        artifact_dir=artifact_dir,
        manifest=manifest,
        file_key="diagnostics_file",
        sha_key="diagnostics_sha256",
    )
    trials_path = _verify_manifest_file(
        artifact_dir=artifact_dir,
        manifest=manifest,
        file_key="trials_file",
        sha_key="trials_sha256",
    )
    selected = _read_json(selected_path)
    diagnostics = _read_json(diagnostics_path)
    trials = _jsonl_rows(trials_path)
    trial_id = selected.get("selected_trial_id") or manifest.get("selected_trial_id")
    trial = next((row for row in trials if row.get("trial_id") == trial_id), None)
    if trial is None:
        raise RawFloorComparisonBuildError("v0.2b selected trial missing")
    if float(trial["title_threshold"]) != 0.5 or float(trial["abstract_threshold"]) != 0.625:
        raise RawFloorComparisonBuildError("v0.2b historical selected thresholds drifted")
    if float(trial["combined_exact_f1"]) != 0.398654:
        raise RawFloorComparisonBuildError("v0.2b combined exact F1 drifted")
    if float(trial["consumed_heldout_exact_f1"]) != 0.396453:
        raise RawFloorComparisonBuildError("v0.2b consumed exact F1 drifted")
    return {
        "manifest": manifest,
        "selected_policy": selected,
        "diagnostics": diagnostics,
        "selected_trial": trial,
    }


def _close(actual: Any, expected: float) -> bool:
    return actual is not None and abs(float(actual) - float(expected)) <= 1e-6


def _evaluate_gate(
    *,
    config: RawFloorComparisonConfig,
    candidate_summaries: Mapping[str, Mapping[str, Any]],
    candidate_diagnostics: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    held = candidate_summaries["consumed_v01_heldout_48"]
    combined = candidate_summaries["combined_dev_72"]
    diag = candidate_diagnostics["consumed_v01_heldout_48"]
    sinks = diag["predicted_type_mismatch_sinks"]
    max_sink = max((int(value) for value in sinks.values()), default=0)
    hard = config.hard_guardrails
    observations = {
        "minimum_consumed_heldout_exact_f1": (
            held["overall"]["exact"]["f1"],
            hard.minimum_consumed_heldout_exact_f1,
            float(held["overall"]["exact"]["f1"]) >= hard.minimum_consumed_heldout_exact_f1,
        ),
        "minimum_combined_dev_exact_f1": (
            combined["overall"]["exact"]["f1"],
            hard.minimum_combined_dev_exact_f1,
            float(combined["overall"]["exact"]["f1"]) >= hard.minimum_combined_dev_exact_f1,
        ),
        "maximum_model_to_method_count": (
            int(diag["type_confusions"].get("model->method", 0)),
            hard.maximum_model_to_method_count,
            int(diag["type_confusions"].get("model->method", 0)) <= hard.maximum_model_to_method_count,
        ),
        "maximum_method_to_task_count": (
            int(diag["type_confusions"].get("method->task", 0)),
            hard.maximum_method_to_task_count,
            int(diag["type_confusions"].get("method->task", 0)) <= hard.maximum_method_to_task_count,
        ),
        "maximum_total_type_mismatch_count": (
            int(diag["type_mismatch_total"]),
            hard.maximum_total_type_mismatch_count,
            int(diag["type_mismatch_total"]) <= hard.maximum_total_type_mismatch_count,
        ),
        "maximum_method_semantic_sink_count": (
            int(sinks.get("method", 0)),
            hard.maximum_method_semantic_sink_count,
            int(sinks.get("method", 0)) <= hard.maximum_method_semantic_sink_count,
        ),
        "maximum_any_predicted_type_mismatch_sink_count": (
            max_sink,
            hard.maximum_any_predicted_type_mismatch_sink_count,
            max_sink <= hard.maximum_any_predicted_type_mismatch_sink_count,
        ),
    }
    rows = {
        name: {"observed": observed, "threshold": threshold, "passed": passed}
        for name, (observed, threshold, passed) in observations.items()
    }
    hard_passed = all(row["passed"] for row in rows.values())
    inv = config.selected_calibration_invariants
    reproduction = {
        "combined_exact_f1": {
            "observed": combined["overall"]["exact"]["f1"],
            "expected": inv.combined_exact_f1,
            "passed": _close(combined["overall"]["exact"]["f1"], inv.combined_exact_f1),
        },
        "consumed_heldout_exact_f1": {
            "observed": held["overall"]["exact"]["f1"],
            "expected": inv.consumed_heldout_exact_f1,
            "passed": _close(held["overall"]["exact"]["f1"], inv.consumed_heldout_exact_f1),
        },
        "consumed_heldout_relaxed_f1": {
            "observed": held["overall"]["relaxed"]["f1"],
            "expected": inv.consumed_heldout_relaxed_f1,
            "passed": _close(held["overall"]["relaxed"]["f1"], inv.consumed_heldout_relaxed_f1),
        },
        "model_to_method_count": {
            "observed": int(diag["type_confusions"].get("model->method", 0)),
            "expected": inv.model_to_method_count,
            "passed": int(diag["type_confusions"].get("model->method", 0)) == inv.model_to_method_count,
        },
        "method_to_task_count": {
            "observed": int(diag["type_confusions"].get("method->task", 0)),
            "expected": inv.method_to_task_count,
            "passed": int(diag["type_confusions"].get("method->task", 0)) == inv.method_to_task_count,
        },
        "total_type_mismatch_count": {
            "observed": int(diag["type_mismatch_total"]),
            "expected": inv.total_type_mismatch_count,
            "passed": int(diag["type_mismatch_total"]) == inv.total_type_mismatch_count,
        },
        "method_semantic_sink_count": {
            "observed": int(sinks.get("method", 0)),
            "expected": inv.method_semantic_sink_count,
            "passed": int(sinks.get("method", 0)) == inv.method_semantic_sink_count,
        },
    }
    reproduction_passed = all(row["passed"] for row in reproduction.values())
    if not reproduction_passed:
        raise RawFloorComparisonBuildError(
            "materialized v0.2c policy evaluation does not reproduce selected calibration trial"
        )
    return {
        "schema_version": GATE_SCHEMA_VERSION,
        "evaluation_role": "development_candidate_freeze_not_independent_acceptance",
        "calibration_reproduction": reproduction,
        "calibration_reproduction_passed": reproduction_passed,
        "hard_guardrails": rows,
        "all_hard_guardrails_passed": hard_passed,
        "candidate_ready_for_development_freeze": hard_passed and reproduction_passed,
        "production_acceptance": False,
        "independent_v02_acceptance": False,
        "fresh_heldout_consumed": False,
        "full_corpus_build_authorized": False,
        "future_v02_acceptance_requires_new_disjoint_heldout": True,
        "next_slice": (
            "freeze_v02c_development_candidate_and_prepare_new_disjoint_prediction_blind_heldout"
            if hard_passed and reproduction_passed
            else "choose_next_bounded_extractor_hypothesis_without_spending_future_heldout"
        ),
    }


def _progression(
    *,
    comparison_id: str,
    v02a: Mapping[str, Any],
    v02b: Mapping[str, Any],
    candidate_summaries: Mapping[str, Mapping[str, Any]],
    candidate_diagnostics: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    v02a_cmp = v02a["comparison"]
    v02a_diag = v02a["diagnostics"]
    b_trial = v02b["selected_trial"]
    held = candidate_summaries["consumed_v01_heldout_48"]
    combined = candidate_summaries["combined_dev_72"]
    cdiag = candidate_diagnostics["consumed_v01_heldout_48"]

    def stage_from_full(summary: Mapping[str, Any], diag: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "overall_exact_f1": summary["overall"]["exact"]["f1"],
            "overall_relaxed_f1": summary["overall"]["relaxed"]["f1"],
            "prediction_mention_count": summary["prediction_mention_count"],
            "model_to_method_count": diag["type_confusions"].get("model->method", 0),
            "method_to_task_count": diag["type_confusions"].get("method->task", 0),
            "total_type_mismatch_count": diag["type_mismatch_total"],
            "method_semantic_sink_count": diag["predicted_type_mismatch_sinks"].get("method", 0),
        }

    return {
        "schema_version": PROGRESSION_SCHEMA_VERSION,
        "comparison_id": comparison_id,
        "note": "The 48-paper view is consumed development evidence for v0.2; only a future new disjoint sample may serve as independent acceptance evidence.",
        "consumed_48_progression": {
            "v0.1_frozen_baseline": stage_from_full(
                v02a_cmp["splits"]["consumed_v01_heldout_48"]["baseline"],
                v02a_diag["splits"]["consumed_v01_heldout_48"]["baseline"],
            ),
            "v0.2a_semantic_prompts_inherited_policy": stage_from_full(
                v02a_cmp["splits"]["consumed_v01_heldout_48"]["candidate"],
                v02a_diag["splits"]["consumed_v01_heldout_48"]["candidate"],
            ),
            "v0.2b_threshold_calibration_selected": {
                "overall_exact_f1": b_trial["consumed_heldout_exact_f1"],
                "overall_relaxed_f1": b_trial.get("consumed_heldout_relaxed_f1"),
                "prediction_mention_count": b_trial["consumed_heldout_prediction_count"],
                "model_to_method_count": b_trial["model_to_method_count"],
                "method_to_task_count": b_trial["method_to_task_count"],
                "total_type_mismatch_count": b_trial["total_type_mismatch_count"],
                "method_semantic_sink_count": b_trial["method_semantic_sink_count"],
            },
            "v0.2c_raw_floor_selected_policy": stage_from_full(held, cdiag),
        },
        "combined_72_progression": {
            "v0.1_frozen_baseline": {
                "overall_exact_f1": v02a_cmp["splits"]["combined_dev_72"]["baseline"]["overall"]["exact"]["f1"],
                "overall_relaxed_f1": v02a_cmp["splits"]["combined_dev_72"]["baseline"]["overall"]["relaxed"]["f1"],
                "prediction_mention_count": v02a_cmp["splits"]["combined_dev_72"]["baseline"]["prediction_mention_count"],
            },
            "v0.2a_semantic_prompts_inherited_policy": {
                "overall_exact_f1": v02a_cmp["splits"]["combined_dev_72"]["candidate"]["overall"]["exact"]["f1"],
                "overall_relaxed_f1": v02a_cmp["splits"]["combined_dev_72"]["candidate"]["overall"]["relaxed"]["f1"],
                "prediction_mention_count": v02a_cmp["splits"]["combined_dev_72"]["candidate"]["prediction_mention_count"],
            },
            "v0.2b_threshold_calibration_selected": {
                "overall_exact_f1": b_trial["combined_exact_f1"],
                "overall_relaxed_f1": b_trial.get("combined_relaxed_f1"),
                "prediction_mention_count": b_trial["selected_prediction_count"],
            },
            "v0.2c_raw_floor_selected_policy": {
                "overall_exact_f1": combined["overall"]["exact"]["f1"],
                "overall_relaxed_f1": combined["overall"]["relaxed"]["f1"],
                "prediction_mention_count": combined["prediction_mention_count"],
            },
        },
    }


def _prepare(
    *,
    project_root: Path,
    config_path: Path,
    development_package_dir: Path,
    policy_build_dir: Path,
    parent_raw_build_dir: Path,
    calibration_dir: Path,
    v02a_comparison_dir: Path,
    v02b_calibration_dir: Path,
    comparison_id: str,
    generated_at_utc: datetime,
) -> PreparedComparison:
    root = project_root.resolve()
    config = load_raw_floor_comparison_config(config_path.resolve())
    evaluation_config = load_evaluation_config(
        _resolve(root, config.candidate.evaluation_config_path)
    )

    package_validation = validate_semantic_prompt_development_package(
        project_root=root,
        design_config_path=_resolve(
            root, "configs/scientific_entity_semantic_prompt_candidate_v0.2a.yaml"
        ),
        package_dir=development_package_dir,
    )
    policy_validation = validate_raw_floor_selected_policy_build(
        build_dir=policy_build_dir,
        parent_build_dir=parent_raw_build_dir,
        development_package_dir=development_package_dir,
        calibration_dir=calibration_dir,
        config_path=_resolve(root, config.candidate.policy_config_path),
    )
    if policy_validation["required_failed_count"] != 0:
        raise RawFloorComparisonBuildError("v0.2c selected-policy build failed validation")
    if package_validation["package_id"] != config.candidate.development_package_id:
        raise RawFloorComparisonBuildError("development package_id drifted")
    if package_validation["combined_document_count"] != config.candidate.expected_document_count:
        raise RawFloorComparisonBuildError("development document count drifted")
    if policy_validation["build_id"] != config.candidate.policy_build_id:
        raise RawFloorComparisonBuildError("v0.2c policy build_id drifted")
    if policy_validation["selected_prediction_count"] != config.candidate.expected_selected_prediction_count:
        raise RawFloorComparisonBuildError("v0.2c selected prediction count drifted")

    package_manifest = _read_json(development_package_dir / "manifest.json")
    documents, membership = _load_canonical(development_package_dir)
    policy_manifest, derivation, predictions = _load_policy_predictions(
        policy_build_dir=policy_build_dir,
        documents=documents,
    )
    if derivation.calibration_id != config.candidate.calibration_id:
        raise RawFloorComparisonBuildError("policy calibration lineage drifted")
    if derivation.selected_trial_id != config.candidate.selected_trial_id:
        raise RawFloorComparisonBuildError("policy selected trial lineage drifted")
    if len(predictions) != config.candidate.expected_selected_prediction_count:
        raise RawFloorComparisonBuildError("policy prediction count drifted")
    if policy_manifest.canonical_input.sha256 != package_manifest["canonical_documents_sha256"]:
        raise RawFloorComparisonBuildError("policy canonical input does not match package")

    source_rows = package_manifest.get("sources")
    if not isinstance(source_rows, list) or len(source_rows) != 2:
        raise RawFloorComparisonBuildError("development package source descriptors drifted")
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
    combined_refs = (
        baselines["old_dev_24"].references
        + baselines["consumed_v01_heldout_48"].references
    )
    if len(combined_refs) != config.candidate.expected_reference_mention_count:
        raise RawFloorComparisonBuildError("reference count drifted")

    predictions_by_split = {
        split: tuple(row for row in predictions if row.canonical_id in split_ids[split])
        for split in ("old_dev_24", "consumed_v01_heldout_48")
    }
    if sum(len(rows) for rows in predictions_by_split.values()) != len(predictions):
        raise RawFloorComparisonBuildError("policy predictions do not partition into 24 / 48")

    candidate_summaries: dict[str, dict[str, Any]] = {}
    candidate_diagnostics: dict[str, dict[str, Any]] = {}
    baseline_summaries: dict[str, dict[str, Any]] = {}
    baseline_diagnostics: dict[str, dict[str, Any]] = {}
    for split in ("old_dev_24", "consumed_v01_heldout_48"):
        result = evaluate_mentions(
            evaluation_id=_safe_evaluation_id(comparison_id, split),
            document_count=len(split_ids[split]),
            references=baselines[split].references,
            predictions=predictions_by_split[split],
            config=evaluation_config,
        )
        candidate_summaries[split] = _summary_from_result(result)
        candidate_diagnostics[split] = _diagnostics(result.errors)
        baseline_summaries[split] = _summary_from_baseline(baselines[split])
        baseline_diagnostics[split] = _diagnostics(baselines[split].errors)

    combined_result = evaluate_mentions(
        evaluation_id=_safe_evaluation_id(comparison_id, "combined-dev-72"),
        document_count=72,
        references=combined_refs,
        predictions=predictions,
        config=evaluation_config,
    )
    candidate_summaries["combined_dev_72"] = _summary_from_result(combined_result)
    candidate_diagnostics["combined_dev_72"] = _diagnostics(combined_result.errors)
    baseline_summaries["combined_dev_72"] = _aggregate_baselines(
        baseline_summaries["old_dev_24"],
        baseline_summaries["consumed_v01_heldout_48"],
    )
    baseline_diagnostics["combined_dev_72"] = _merge_diagnostics(
        baseline_diagnostics["old_dev_24"],
        baseline_diagnostics["consumed_v01_heldout_48"],
    )
    if _aggregate_baselines(
        candidate_summaries["old_dev_24"],
        candidate_summaries["consumed_v01_heldout_48"],
    ) != candidate_summaries["combined_dev_72"]:
        raise RawFloorComparisonBuildError("combined candidate metrics do not aggregate exactly")
    if _merge_diagnostics(
        candidate_diagnostics["old_dev_24"],
        candidate_diagnostics["consumed_v01_heldout_48"],
    ) != candidate_diagnostics["combined_dev_72"]:
        raise RawFloorComparisonBuildError("combined candidate diagnostics do not aggregate exactly")

    gate = _evaluate_gate(
        config=config,
        candidate_summaries=candidate_summaries,
        candidate_diagnostics=candidate_diagnostics,
    )
    v02a = _load_v02a_history(artifact_dir=v02a_comparison_dir, config=config)
    v02b = _load_v02b_history(artifact_dir=v02b_calibration_dir, config=config)
    progression = _progression(
        comparison_id=comparison_id,
        v02a=v02a,
        v02b=v02b,
        candidate_summaries=candidate_summaries,
        candidate_diagnostics=candidate_diagnostics,
    )

    comparison = {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "comparison_id": comparison_id,
        "candidate_id": config.candidate.candidate_id,
        "evaluation_role": "development_candidate_freeze_not_independent_acceptance",
        "splits": {
            split: {
                "baseline": baseline_summaries[split],
                "candidate": candidate_summaries[split],
                "delta": _split_delta(candidate_summaries[split], baseline_summaries[split]),
            }
            for split in config.candidate.compare_splits
        },
    }
    diagnostics = {
        "schema_version": DIAGNOSTICS_SCHEMA_VERSION,
        "comparison_id": comparison_id,
        "splits": {
            split: {
                "baseline": baseline_diagnostics[split],
                "candidate": candidate_diagnostics[split],
                "delta": {
                    "type_mismatch_total": candidate_diagnostics[split]["type_mismatch_total"]
                    - baseline_diagnostics[split]["type_mismatch_total"],
                    "model_to_method": candidate_diagnostics[split]["type_confusions"].get("model->method", 0)
                    - baseline_diagnostics[split]["type_confusions"].get("model->method", 0),
                    "method_to_task": candidate_diagnostics[split]["type_confusions"].get("method->task", 0)
                    - baseline_diagnostics[split]["type_confusions"].get("method->task", 0),
                    "method_semantic_sink": candidate_diagnostics[split]["predicted_type_mismatch_sinks"].get("method", 0)
                    - baseline_diagnostics[split]["predicted_type_mismatch_sinks"].get("method", 0),
                },
            }
            for split in config.candidate.compare_splits
        },
    }

    held = candidate_summaries["consumed_v01_heldout_48"]
    combined = candidate_summaries["combined_dev_72"]
    held_diag = candidate_diagnostics["consumed_v01_heldout_48"]
    comparison_bytes = _json_bytes(comparison)
    diagnostics_bytes = _json_bytes(diagnostics)
    progression_bytes = _json_bytes(progression)
    gate_bytes = _json_bytes(gate)
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "comparison_id": comparison_id,
        "candidate_id": config.candidate.candidate_id,
        "generated_at_utc": generated_at_utc.isoformat().replace("+00:00", "Z"),
        "config_path": _project_path(root, config_path),
        "config_sha256": _sha256_file(config_path),
        "development_package_id": package_manifest["package_id"],
        "development_package_manifest_sha256": _sha256_file(development_package_dir / "manifest.json"),
        "policy_build_id": policy_manifest.build_id,
        "policy_manifest_sha256": _sha256_file(policy_build_dir / "manifest.json"),
        "policy_derivation_manifest_sha256": _sha256_file(policy_build_dir / "derivation_manifest.json"),
        "calibration_id": derivation.calibration_id,
        "calibration_manifest_sha256": _sha256_file(calibration_dir / "manifest.json"),
        "v02a_comparison_id": config.historical_inputs.v02a_comparison_id,
        "v02a_comparison_manifest_sha256": _sha256_file(v02a_comparison_dir / "manifest.json"),
        "v02b_calibration_id": config.historical_inputs.v02b_calibration_id,
        "v02b_calibration_manifest_sha256": _sha256_file(v02b_calibration_dir / "manifest.json"),
        "development_document_count": 72,
        "reference_mention_count": len(combined_refs),
        "candidate_prediction_count": len(predictions),
        "split_candidate_prediction_counts": {
            "old_dev_24": len(predictions_by_split["old_dev_24"]),
            "consumed_v01_heldout_48": len(predictions_by_split["consumed_v01_heldout_48"]),
            "combined_dev_72": len(predictions),
        },
        "comparison_file": "comparison.json",
        "comparison_sha256": hashlib.sha256(comparison_bytes).hexdigest(),
        "diagnostics_file": "diagnostics.json",
        "diagnostics_sha256": hashlib.sha256(diagnostics_bytes).hexdigest(),
        "progression_file": "progression.json",
        "progression_sha256": hashlib.sha256(progression_bytes).hexdigest(),
        "gate_decision_file": "gate_decision.json",
        "gate_decision_sha256": hashlib.sha256(gate_bytes).hexdigest(),
        "calibration_reproduction_passed": gate["calibration_reproduction_passed"],
        "all_hard_guardrails_passed": gate["all_hard_guardrails_passed"],
        "candidate_ready_for_development_freeze": gate["candidate_ready_for_development_freeze"],
        "model_inference_executed": False,
        "threshold_tuning_executed": False,
        "fresh_heldout_consumed": False,
        "canonical_truth_mutated": False,
        "may_be_used_as_reconcile_input": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "publication_ready": False,
        "current_48_is_independent_heldout_for_v02": False,
        "future_v02_acceptance_requires_new_disjoint_heldout": True,
        "next_slice": gate["next_slice"],
    }
    readme = "\n".join(
        [
            "# Scientific Entity Semantic Prompt Raw-Floor Controlled Comparison v0.2c",
            "",
            f"comparison_id = `{comparison_id}`",
            f"policy_build_id = `{policy_manifest.build_id}`",
            f"calibration_id = `{derivation.calibration_id}`",
            "",
            "This immutable artifact evaluates the frozen v0.2c selected policy on the",
            "same consumed 24 / 48 / 72 development evidence and records historical",
            "progression from v0.1 through v0.2c.",
            "",
            "The 48-paper view is not an independent v0.2 held-out set.",
            "",
            f"candidate_prediction_count = `{len(predictions)}`",
            f"consumed_48_exact_f1 = `{held['overall']['exact']['f1']}`",
            f"consumed_48_relaxed_f1 = `{held['overall']['relaxed']['f1']}`",
            f"combined_72_exact_f1 = `{combined['overall']['exact']['f1']}`",
            f"model_to_method = `{held_diag['type_confusions'].get('model->method', 0)}`",
            f"method_to_task = `{held_diag['type_confusions'].get('method->task', 0)}`",
            f"type_mismatch_total = `{held_diag['type_mismatch_total']}`",
            f"method_semantic_sink = `{held_diag['predicted_type_mismatch_sinks'].get('method', 0)}`",
            f"calibration_reproduction_passed = `{str(gate['calibration_reproduction_passed']).lower()}`",
            f"all_hard_guardrails_passed = `{str(gate['all_hard_guardrails_passed']).lower()}`",
            f"candidate_ready_for_development_freeze = `{str(gate['candidate_ready_for_development_freeze']).lower()}`",
            f"next_slice = `{gate['next_slice']}`",
            "",
            "No model inference, threshold tuning, fresh-held-out consumption, canonical",
            "mutation, production selection, or full-corpus authorization occurs here.",
            "",
        ]
    )
    report = {
        "report": REPORT_NAME,
        "comparison_id": comparison_id,
        "development_document_count": 72,
        "reference_mention_count": len(combined_refs),
        "candidate_prediction_count": len(predictions),
        "old_dev_candidate_exact_f1": candidate_summaries["old_dev_24"]["overall"]["exact"]["f1"],
        "consumed_heldout_candidate_exact_f1": held["overall"]["exact"]["f1"],
        "consumed_heldout_candidate_relaxed_f1": held["overall"]["relaxed"]["f1"],
        "combined_candidate_exact_f1": combined["overall"]["exact"]["f1"],
        "consumed_heldout_model_to_method_count": held_diag["type_confusions"].get("model->method", 0),
        "consumed_heldout_method_to_task_count": held_diag["type_confusions"].get("method->task", 0),
        "consumed_heldout_total_type_mismatch_count": held_diag["type_mismatch_total"],
        "consumed_heldout_method_semantic_sink_count": held_diag["predicted_type_mismatch_sinks"].get("method", 0),
        "calibration_reproduction_passed": gate["calibration_reproduction_passed"],
        "all_hard_guardrails_passed": gate["all_hard_guardrails_passed"],
        "candidate_ready_for_development_freeze": gate["candidate_ready_for_development_freeze"],
        "model_inference_executed": False,
        "threshold_tuning_executed": False,
        "fresh_heldout_consumed": False,
        "canonical_truth_mutated": False,
        "full_corpus_build_authorized": False,
        "next_slice": gate["next_slice"],
    }
    return PreparedComparison(
        report=report,
        manifest=manifest,
        comparison=comparison,
        diagnostics=diagnostics,
        progression=progression,
        gate_decision=gate,
        readme=readme,
    )


def _default_comparison_id(now: datetime) -> str:
    return (
        "scientific-entity-semantic-prompt-raw-floor-comparison-v0.2c-"
        + now.strftime("%Y%m%dT%H%M%S%fZ")
    )


def build_raw_floor_comparison(
    *,
    project_root: Path,
    development_package_dir: Path,
    policy_build_dir: Path,
    parent_raw_build_dir: Path,
    calibration_dir: Path,
    v02a_comparison_dir: Path,
    v02b_calibration_dir: Path,
    config_path: Path = DEFAULT_CONFIG_PATH,
    output_root: Path | None = None,
    comparison_id: str | None = None,
    execute: bool = False,
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    now = generated_at_utc or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() != timezone.utc.utcoffset(now):
        raise RawFloorComparisonBuildError("generated_at_utc must be timezone-aware UTC")
    config = load_raw_floor_comparison_config(config_path.resolve())
    selected_id = comparison_id or _default_comparison_id(now)
    selected_root = (output_root or _resolve(project_root, config.outputs.root)).resolve()
    output_dir = selected_root / selected_id
    if execute and output_dir.exists():
        raise FileExistsError(f"immutable v0.2c comparison already exists: {output_dir}")

    prepared = _prepare(
        project_root=project_root,
        config_path=config_path,
        development_package_dir=development_package_dir,
        policy_build_dir=policy_build_dir,
        parent_raw_build_dir=parent_raw_build_dir,
        calibration_dir=calibration_dir,
        v02a_comparison_dir=v02a_comparison_dir,
        v02b_calibration_dir=v02b_calibration_dir,
        comparison_id=selected_id,
        generated_at_utc=now,
    )
    if execute:
        output_dir.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{selected_id}.tmp-", dir=output_dir.parent))
        try:
            (staging / "manifest.json").write_bytes(_json_bytes(prepared.manifest))
            (staging / "comparison.json").write_bytes(_json_bytes(prepared.comparison))
            (staging / "diagnostics.json").write_bytes(_json_bytes(prepared.diagnostics))
            (staging / "progression.json").write_bytes(_json_bytes(prepared.progression))
            (staging / "gate_decision.json").write_bytes(_json_bytes(prepared.gate_decision))
            (staging / "README.md").write_text(prepared.readme, encoding="utf-8", newline="\n")
            (staging / "checksums.txt").write_text(
                "\n".join(
                    f"{_sha256_file(staging / filename)}  {filename}"
                    for filename in CHECKSUM_FILES
                )
                + "\n",
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


def _text_ok(path: Path) -> tuple[bool, str | None]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return False, "UTF-8 BOM forbidden"
    if b"\r" in raw:
        return False, "CR/CRLF forbidden"
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return False, f"invalid UTF-8: {exc}"
    if raw and not raw.endswith(b"\n"):
        return False, "text file must end with LF"
    return True, None


def validate_raw_floor_comparison(
    *,
    project_root: Path,
    comparison_dir: Path,
    development_package_dir: Path,
    policy_build_dir: Path,
    parent_raw_build_dir: Path,
    calibration_dir: Path,
    v02a_comparison_dir: Path,
    v02b_calibration_dir: Path,
    config_path: Path = DEFAULT_CONFIG_PATH,
) -> dict[str, Any]:
    config = load_raw_floor_comparison_config(config_path.resolve())
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, details: str | None = None) -> None:
        checks.append({"name": name, "ok": bool(ok), "required": True, "details": details})

    resolved = comparison_dir.resolve()
    add("comparison_directory_exists", resolved.is_dir(), str(resolved))
    if not resolved.is_dir():
        return _validation_report(checks, None)
    actual_files = {p.name for p in resolved.iterdir() if p.is_file()}
    actual_dirs = {p.name for p in resolved.iterdir() if p.is_dir()}
    add("required_files_exact", actual_files == set(REQUIRED_FILES))
    add("nested_directories_absent", not actual_dirs)
    if actual_files != set(REQUIRED_FILES):
        return _validation_report(checks, None)
    for filename in REQUIRED_FILES:
        ok, details = _text_ok(resolved / filename)
        add(f"utf8_lf::{filename}", ok, details)

    checksum_rows: dict[str, str] = {}
    for line in (resolved / "checksums.txt").read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, filename = line.split("  ", 1)
            checksum_rows[filename] = digest
    add("checksum_file_set_exact", set(checksum_rows) == set(CHECKSUM_FILES))
    for filename in CHECKSUM_FILES:
        add(
            f"checksum_matches::{filename}",
            checksum_rows.get(filename) == _sha256_file(resolved / filename),
        )

    manifest = _read_json(resolved / "manifest.json")
    add("manifest_schema_version", manifest.get("schema_version") == MANIFEST_SCHEMA_VERSION)
    add("directory_matches_comparison_id", resolved.name == manifest.get("comparison_id"))
    add("candidate_id_matches", manifest.get("candidate_id") == config.candidate.candidate_id)
    add("development_document_count", manifest.get("development_document_count") == 72)
    add("reference_mention_count", manifest.get("reference_mention_count") == 1316)
    add("candidate_prediction_count", manifest.get("candidate_prediction_count") == 1077)
    add("policy_build_id_matches", manifest.get("policy_build_id") == config.candidate.policy_build_id)
    add("calibration_id_matches", manifest.get("calibration_id") == config.candidate.calibration_id)
    add("v02a_history_id_matches", manifest.get("v02a_comparison_id") == config.historical_inputs.v02a_comparison_id)
    add("v02b_history_id_matches", manifest.get("v02b_calibration_id") == config.historical_inputs.v02b_calibration_id)
    add("calibration_reproduction_passed", manifest.get("calibration_reproduction_passed") is True)
    add("hard_guardrails_passed", manifest.get("all_hard_guardrails_passed") is True)
    add("ready_for_development_freeze", manifest.get("candidate_ready_for_development_freeze") is True)
    for key in (
        "model_inference_executed",
        "threshold_tuning_executed",
        "fresh_heldout_consumed",
        "canonical_truth_mutated",
        "may_be_used_as_reconcile_input",
        "production_extractor_selected",
        "full_corpus_build_authorized",
        "publication_ready",
        "current_48_is_independent_heldout_for_v02",
    ):
        add(f"safety_false::{key}", manifest.get(key) is False)
    add(
        "fresh_heldout_requirement_preserved",
        manifest.get("future_v02_acceptance_requires_new_disjoint_heldout") is True,
    )
    add(
        "upstream_policy_manifest_sha",
        manifest.get("policy_manifest_sha256") == _sha256_file(policy_build_dir / "manifest.json"),
    )
    add(
        "upstream_calibration_manifest_sha",
        manifest.get("calibration_manifest_sha256") == _sha256_file(calibration_dir / "manifest.json"),
    )
    add(
        "v02a_history_manifest_sha",
        manifest.get("v02a_comparison_manifest_sha256") == _sha256_file(v02a_comparison_dir / "manifest.json"),
    )
    add(
        "v02b_history_manifest_sha",
        manifest.get("v02b_calibration_manifest_sha256") == _sha256_file(v02b_calibration_dir / "manifest.json"),
    )

    try:
        generated = datetime.fromisoformat(str(manifest["generated_at_utc"]).replace("Z", "+00:00"))
        with tempfile.TemporaryDirectory(prefix="semantic-prompt-v02c-comparison-validation-") as tmp:
            report = build_raw_floor_comparison(
                project_root=project_root,
                development_package_dir=development_package_dir,
                policy_build_dir=policy_build_dir,
                parent_raw_build_dir=parent_raw_build_dir,
                calibration_dir=calibration_dir,
                v02a_comparison_dir=v02a_comparison_dir,
                v02b_calibration_dir=v02b_calibration_dir,
                config_path=config_path,
                output_root=Path(tmp),
                comparison_id=str(manifest["comparison_id"]),
                execute=True,
                generated_at_utc=generated,
            )
            rebuilt = Path(report["output_dir"])
            mismatches = [
                filename
                for filename in REQUIRED_FILES
                if (resolved / filename).read_bytes() != (rebuilt / filename).read_bytes()
            ]
            add("deterministic_byte_recomputation", not mismatches, None if not mismatches else str(mismatches))
    except Exception as exc:
        add("deterministic_byte_recomputation", False, f"{type(exc).__name__}: {exc}")

    return _validation_report(checks, manifest)


def _validation_report(
    checks: Sequence[Mapping[str, Any]],
    manifest: Mapping[str, Any] | None,
) -> dict[str, Any]:
    failed = [row for row in checks if row["required"] and not row["ok"]]
    return {
        "report": REPORT_NAME,
        "comparison_id": None if manifest is None else manifest.get("comparison_id"),
        "development_document_count": None if manifest is None else manifest.get("development_document_count"),
        "reference_mention_count": None if manifest is None else manifest.get("reference_mention_count"),
        "candidate_prediction_count": None if manifest is None else manifest.get("candidate_prediction_count"),
        "calibration_reproduction_passed": None if manifest is None else manifest.get("calibration_reproduction_passed"),
        "all_hard_guardrails_passed": None if manifest is None else manifest.get("all_hard_guardrails_passed"),
        "candidate_ready_for_development_freeze": None if manifest is None else manifest.get("candidate_ready_for_development_freeze"),
        "total_checks": len(checks),
        "required_failed_count": len(failed),
        "model_inference_executed": False if manifest is None else manifest.get("model_inference_executed"),
        "fresh_heldout_consumed": False if manifest is None else manifest.get("fresh_heldout_consumed"),
        "canonical_truth_mutated": False if manifest is None else manifest.get("canonical_truth_mutated"),
        "full_corpus_build_authorized": False if manifest is None else manifest.get("full_corpus_build_authorized"),
        "next_slice": None if manifest is None else manifest.get("next_slice"),
        "checks": list(checks),
    }
