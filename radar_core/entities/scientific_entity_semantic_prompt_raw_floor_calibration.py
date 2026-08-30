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
    EntityEvidenceBuildStatus,
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
from radar_core.contracts.scientific_entity_semantic_prompt_raw_floor_calibration import (
    DIAGNOSTICS_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    SELECTED_POLICY_SCHEMA_VERSION,
    RawFloorCalibrationDiagnostics,
    RawFloorCalibrationTrial,
    RawFloorSelectedPolicy,
)
from radar_core.contracts.scientific_entity_semantic_prompt_raw_floor_extension import (
    SemanticPromptRawFloorExtensionConfig,
    canonical_config_sha256,
    load_semantic_prompt_raw_floor_extension_config,
)
from radar_core.entities.scientific_entity_evaluation import (
    evaluate_mentions,
    load_evaluation_config,
)
from radar_core.entities.scientific_entity_gliner import (
    gliner_config_sha256,
    load_gliner_config,
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


REPORT_NAME = "scientific_entity_semantic_prompt_raw_floor_calibration_v02c"
DEFAULT_CONFIG_PATH = Path(
    "configs/scientific_entity_semantic_prompt_raw_floor_extension_v0.2c.yaml"
)
DEFAULT_OUTPUT_ROOT = Path(
    "data/entities/scientific_entity_semantic_prompt_raw_floor_calibration/v0.2c"
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

V02B_CONTROL = {
    "title_threshold": 0.5,
    "abstract_threshold": 0.625,
    "combined_exact_f1": 0.398654,
    "consumed_heldout_exact_f1": 0.396453,
    "model_to_method_count": 32,
    "method_to_task_count": 25,
    "total_type_mismatch_count": 138,
    "method_semantic_sink_count": 57,
    "selected_prediction_count": 1062,
}


class SemanticPromptRawFloorCalibrationBuildError(RuntimeError):
    """Raised when v0.2c calibration cannot be reproduced safely."""


@dataclass(frozen=True)
class PreparedCalibration:
    report: dict[str, Any]
    manifest: dict[str, Any]
    trials: tuple[RawFloorCalibrationTrial, ...]
    selected_policy: RawFloorSelectedPolicy
    diagnostics: RawFloorCalibrationDiagnostics
    readme: str


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        raise SemanticPromptRawFloorCalibrationBuildError(
            f"{label} SHA-256 mismatch: expected={expected} actual={actual}"
        )


def _metric_value(summary: Mapping[str, Any], *path: str) -> float | None:
    value: Any = summary
    for key in path:
        value = value[key]
    return None if value is None else float(value)


def _trial_evaluation_id(
    *,
    calibration_id: str,
    trial_id: str,
    split: str,
) -> str:
    digest = hashlib.sha256(
        f"{calibration_id}\n{trial_id}\n{split}".encode("utf-8")
    ).hexdigest()[:32]
    return f"semantic-prompt-v02c-{split}-{digest}"


def _evaluate_semantic_guardrails(
    *,
    config: SemanticPromptRawFloorExtensionConfig,
    diagnostics: Mapping[str, Any],
) -> dict[str, dict[str, object]]:
    sinks = diagnostics["predicted_type_mismatch_sinks"]
    max_sink = max((int(value) for value in sinks.values()), default=0)
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


def _trial_sort_key(row: RawFloorCalibrationTrial) -> tuple[Any, ...]:
    def desc(value: float | None) -> float:
        return -(-1.0 if value is None else float(value))

    return (
        desc(row.combined_exact_f1),
        desc(row.combined_relaxed_f1),
        desc(row.combined_exact_recall),
        -row.title_threshold,
        row.trial_id,
    )


def select_raw_floor_trial(
    trials: Sequence[RawFloorCalibrationTrial],
) -> RawFloorCalibrationTrial:
    eligible = [row for row in trials if row.eligible_for_selection]
    if not eligible:
        raise SemanticPromptRawFloorCalibrationBuildError(
            "no v0.2c title-threshold trial satisfies frozen semantic guardrails"
        )
    return sorted(eligible, key=_trial_sort_key)[0]


def _evaluate_selected_policy_gate(
    *,
    config: SemanticPromptRawFloorExtensionConfig,
    selected: RawFloorCalibrationTrial,
) -> dict[str, dict[str, object]]:
    return {
        "minimum_consumed_heldout_exact_f1": {
            "observed": selected.consumed_heldout_exact_f1,
            "threshold": config.decision.selected_policy_minimum_consumed_heldout_exact_f1,
            "passed": selected.consumed_heldout_exact_f1 is not None
            and selected.consumed_heldout_exact_f1
            >= config.decision.selected_policy_minimum_consumed_heldout_exact_f1,
        },
        "minimum_combined_dev_exact_f1": {
            "observed": selected.combined_exact_f1,
            "threshold": config.decision.selected_policy_minimum_combined_dev_exact_f1,
            "passed": selected.combined_exact_f1 is not None
            and selected.combined_exact_f1
            >= config.decision.selected_policy_minimum_combined_dev_exact_f1,
        },
        "semantic_guardrails": {
            "observed": selected.semantic_guardrails_passed,
            "threshold": True,
            "passed": selected.semantic_guardrails_passed,
        },
    }


def _control_reproduced(row: RawFloorCalibrationTrial) -> bool:
    def close(actual: float | None, expected: float) -> bool:
        return actual is not None and abs(float(actual) - expected) <= 1e-6

    return (
        row.is_v02b_control_policy
        and close(row.combined_exact_f1, V02B_CONTROL["combined_exact_f1"])
        and close(
            row.consumed_heldout_exact_f1,
            V02B_CONTROL["consumed_heldout_exact_f1"],
        )
        and row.model_to_method_count == V02B_CONTROL["model_to_method_count"]
        and row.method_to_task_count == V02B_CONTROL["method_to_task_count"]
        and row.total_type_mismatch_count == V02B_CONTROL["total_type_mismatch_count"]
        and row.method_semantic_sink_count == V02B_CONTROL["method_semantic_sink_count"]
    )



def _load_baseline_raw_predictions(
    *,
    baseline_raw_build_dir: Path,
    documents: Mapping[str, Any],
    config: SemanticPromptRawFloorExtensionConfig,
    project_root: Path,
) -> tuple[ScientificEntityEvidenceManifest, tuple[ScientificEntityMentionEvidence, ...]]:
    baseline_manifest = ScientificEntityEvidenceManifest.model_validate(
        _read_json(baseline_raw_build_dir / "manifest.json")
    )
    if baseline_manifest.build_id != config.lineage.v02a_raw_build_id:
        raise SemanticPromptRawFloorCalibrationBuildError(
            "baseline raw build_id does not match frozen v0.2a lineage"
        )
    if (
        baseline_manifest.extractor_fingerprint
        != config.lineage.v02a_raw_extractor_fingerprint
    ):
        raise SemanticPromptRawFloorCalibrationBuildError(
            "baseline raw extractor fingerprint does not match frozen v0.2a lineage"
        )
    if baseline_manifest.canonical_input.document_count != config.lineage.expected_document_count:
        raise SemanticPromptRawFloorCalibrationBuildError(
            "baseline raw build document count drifted"
        )

    runtime_path = _resolve(project_root, config.lineage.baseline_runtime_config_path)
    runtime = load_gliner_config(runtime_path)
    if float(runtime.inference.threshold) != float(config.raw_inference.baseline_floor):
        raise SemanticPromptRawFloorCalibrationBuildError(
            "baseline runtime raw floor drifted"
        )
    if baseline_manifest.extractor.config_sha256 != gliner_config_sha256(runtime):
        raise SemanticPromptRawFloorCalibrationBuildError(
            "baseline raw build extractor config does not match frozen v0.2a runtime"
        )

    mentions_path = baseline_raw_build_dir / baseline_manifest.mentions_file
    _verify_file_sha(
        mentions_path,
        baseline_manifest.mentions_sha256,
        "baseline raw mentions",
    )
    predictions: list[ScientificEntityMentionEvidence] = []
    for row in _read_jsonl(mentions_path):
        mention = ScientificEntityMentionEvidence.model_validate(row)
        document = documents.get(mention.canonical_id)
        if document is None:
            raise SemanticPromptRawFloorCalibrationBuildError(
                f"baseline raw prediction outside development package: {mention.canonical_id}"
            )
        validated = validate_mention_evidence(
            mention,
            source_text=_source_text(document, mention.source_field),
            extractor=baseline_manifest.extractor,
            manifest=baseline_manifest,
        )
        if validated.confidence_score is None:
            raise SemanticPromptRawFloorCalibrationBuildError(
                "baseline raw predictions must carry model scores"
            )
        predictions.append(validated)

    if len(predictions) != baseline_manifest.mention_count:
        raise SemanticPromptRawFloorCalibrationBuildError(
            "baseline raw mentions file count does not match manifest"
        )
    if len(predictions) != 1430:
        raise SemanticPromptRawFloorCalibrationBuildError(
            "baseline v0.2a raw prediction count drifted from frozen 1430"
        )
    return baseline_manifest, tuple(predictions)



def _v02b_control_thresholds(
    config: SemanticPromptRawFloorExtensionConfig,
) -> tuple[float, float]:
    control = config.bounded_policy_search.v02b_selected_policy_control
    return float(control.title), float(control.abstract)


def _compare_baseline_raw_evidence(
    *,
    baseline_predictions: Sequence[ScientificEntityMentionEvidence],
    candidate_predictions: Sequence[ScientificEntityMentionEvidence],
    baseline_floor: float,
    control_title_threshold: float,
    control_abstract_threshold: float,
) -> dict[str, Any]:
    baseline_by_mention = {row.mention_id: row for row in baseline_predictions}
    candidate_by_mention = {row.mention_id: row for row in candidate_predictions}
    if len(baseline_by_mention) != len(baseline_predictions):
        raise SemanticPromptRawFloorCalibrationBuildError(
            "duplicate mention_id in baseline raw evidence"
        )
    if len(candidate_by_mention) != len(candidate_predictions):
        raise SemanticPromptRawFloorCalibrationBuildError(
            "duplicate mention_id in candidate raw evidence"
        )

    missing_ids = sorted(set(baseline_by_mention) - set(candidate_by_mention))
    shared_ids = set(baseline_by_mention) & set(candidate_by_mention)
    score_changed_ids = sorted(
        mention_id
        for mention_id in shared_ids
        if abs(
            float(baseline_by_mention[mention_id].confidence_score)
            - float(candidate_by_mention[mention_id].confidence_score)
        )
        > 1e-12
    )
    new_rows = [
        row
        for mention_id, row in candidate_by_mention.items()
        if mention_id not in baseline_by_mention
    ]
    new_ge_baseline = sorted(
        (
            row
            for row in new_rows
            if float(row.confidence_score) >= baseline_floor
        ),
        key=lambda row: row.mention_id,
    )

    def selected_by_control(row: ScientificEntityMentionEvidence) -> bool:
        threshold = (
            control_title_threshold
            if row.source_field == ScientificEntitySourceField.TITLE
            else control_abstract_threshold
        )
        return float(row.confidence_score) >= threshold

    new_selected_by_control = [
        row for row in new_rows if selected_by_control(row)
    ]
    return {
        "baseline_raw_evidence_preserved": not missing_ids and not score_changed_ids,
        "baseline_raw_missing_count": len(missing_ids),
        "baseline_raw_score_changed_count": len(score_changed_ids),
        "new_at_or_above_baseline_floor_count": len(new_ge_baseline),
        "new_selected_by_v02b_control_count": len(new_selected_by_control),
        "new_at_or_above_baseline_floor_mention_ids": [
            row.mention_id for row in new_ge_baseline
        ],
    }


def _load_raw_predictions(
    *,
    raw_build_dir: Path,
    documents: Mapping[str, Any],
    package_manifest: Mapping[str, Any],
    config: SemanticPromptRawFloorExtensionConfig,
    project_root: Path,
) -> tuple[ScientificEntityEvidenceManifest, tuple[ScientificEntityMentionEvidence, ...]]:
    raw_manifest = ScientificEntityEvidenceManifest.model_validate(
        _read_json(raw_build_dir / "manifest.json")
    )
    if raw_manifest.status != EntityEvidenceBuildStatus.CANDIDATE:
        raise SemanticPromptRawFloorCalibrationBuildError(
            "v0.2c raw build must have candidate status"
        )
    if raw_manifest.canonical_input.document_count != config.lineage.expected_document_count:
        raise SemanticPromptRawFloorCalibrationBuildError(
            "v0.2c raw build document count drifted"
        )
    if raw_manifest.canonical_input.sha256 != package_manifest["canonical_documents_sha256"]:
        raise SemanticPromptRawFloorCalibrationBuildError(
            "v0.2c raw build canonical input does not match development package"
        )

    runtime_path = _resolve(project_root, config.lineage.candidate_runtime_config_path)
    runtime = load_gliner_config(runtime_path)
    if float(runtime.inference.threshold) != float(config.raw_inference.candidate_floor):
        raise SemanticPromptRawFloorCalibrationBuildError(
            "candidate runtime raw floor drifted"
        )
    expected_runtime_sha = gliner_config_sha256(runtime)
    if raw_manifest.extractor.config_sha256 != expected_runtime_sha:
        raise SemanticPromptRawFloorCalibrationBuildError(
            "raw build extractor config does not match frozen v0.2c runtime"
        )
    if raw_manifest.extractor_fingerprint == config.lineage.v02a_raw_extractor_fingerprint:
        raise SemanticPromptRawFloorCalibrationBuildError(
            "v0.2c raw extractor fingerprint must differ from v0.2a"
        )
    if set(field.value for field in raw_manifest.source_fields) != {"title", "abstract"}:
        raise SemanticPromptRawFloorCalibrationBuildError(
            "raw source fields drifted"
        )

    mentions_path = raw_build_dir / raw_manifest.mentions_file
    _verify_file_sha(mentions_path, raw_manifest.mentions_sha256, "raw mentions")
    predictions: list[ScientificEntityMentionEvidence] = []
    for row in _read_jsonl(mentions_path):
        mention = ScientificEntityMentionEvidence.model_validate(row)
        document = documents.get(mention.canonical_id)
        if document is None:
            raise SemanticPromptRawFloorCalibrationBuildError(
                f"raw prediction outside development package: {mention.canonical_id}"
            )
        validated = validate_mention_evidence(
            mention,
            source_text=_source_text(document, mention.source_field),
            extractor=raw_manifest.extractor,
            manifest=raw_manifest,
        )
        if validated.confidence_score is None:
            raise SemanticPromptRawFloorCalibrationBuildError(
                "v0.2c raw predictions must carry model scores"
            )
        if float(validated.confidence_score) < float(config.raw_inference.candidate_floor):
            raise SemanticPromptRawFloorCalibrationBuildError(
                "raw prediction below frozen candidate floor"
            )
        predictions.append(validated)
    if len(predictions) != raw_manifest.mention_count:
        raise SemanticPromptRawFloorCalibrationBuildError(
            "raw mentions file count does not match manifest"
        )
    return raw_manifest, tuple(predictions)


def _prepare_calibration(
    *,
    project_root: Path,
    config_path: Path,
    development_package_dir: Path,
    baseline_raw_build_dir: Path,
    raw_build_dir: Path,
    calibration_id: str,
    generated_at_utc: datetime,
) -> PreparedCalibration:
    root = project_root.resolve()
    config = load_semantic_prompt_raw_floor_extension_config(config_path.resolve())

    baseline_design_path = _resolve(
        root, "configs/scientific_entity_semantic_prompt_candidate_v0.2a.yaml"
    )
    evaluation_config_path = _resolve(
        root, "configs/scientific_entity_evaluation_v0.1.yaml"
    )
    evaluation_config = load_evaluation_config(evaluation_config_path)

    package_validation = validate_semantic_prompt_development_package(
        project_root=root,
        design_config_path=baseline_design_path,
        package_dir=development_package_dir,
    )
    if package_validation["package_id"] != config.lineage.development_package_id:
        raise SemanticPromptRawFloorCalibrationBuildError(
            "development package_id drifted"
        )
    if package_validation["combined_document_count"] != config.lineage.expected_document_count:
        raise SemanticPromptRawFloorCalibrationBuildError(
            "development document count drifted"
        )

    package_manifest = _read_json(development_package_dir / "manifest.json")
    documents, membership = _load_canonical(development_package_dir)
    baseline_raw_manifest, baseline_raw_predictions = _load_baseline_raw_predictions(
        baseline_raw_build_dir=baseline_raw_build_dir,
        documents=documents,
        config=config,
        project_root=root,
    )
    raw_manifest, raw_predictions = _load_raw_predictions(
        raw_build_dir=raw_build_dir,
        documents=documents,
        package_manifest=package_manifest,
        config=config,
        project_root=root,
    )
    baseline_comparison = _compare_baseline_raw_evidence(
        baseline_predictions=baseline_raw_predictions,
        candidate_predictions=raw_predictions,
        baseline_floor=float(config.raw_inference.baseline_floor),
        control_title_threshold=_v02b_control_thresholds(config)[0],
        control_abstract_threshold=_v02b_control_thresholds(config)[1],
    )
    if not baseline_comparison["baseline_raw_evidence_preserved"]:
        raise SemanticPromptRawFloorCalibrationBuildError(
            "v0.2c candidate raw build does not preserve all frozen v0.2a raw "
            "mention identities and scores"
        )

    source_rows = package_manifest.get("sources")
    if not isinstance(source_rows, list) or len(source_rows) != 2:
        raise SemanticPromptRawFloorCalibrationBuildError(
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
        raise SemanticPromptRawFloorCalibrationBuildError(
            "combined reference count drifted"
        )

    trials: list[RawFloorCalibrationTrial] = []
    control_trial_id: str | None = None
    input_floor = float(config.raw_inference.candidate_floor)
    abstract_threshold = float(config.bounded_policy_search.fixed_abstract_threshold)

    for title_threshold in config.bounded_policy_search.title_thresholds:
        policy = ScientificEntityThresholdPolicy(
            default_threshold=input_floor,
            source_field_thresholds={
                ScientificEntitySourceField.TITLE: float(title_threshold),
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
            input_threshold=input_floor,
        )
        predictions_by_split = {
            split: tuple(
                row for row in selected if row.canonical_id in split_ids[split]
            )
            for split in ("old_dev_24", "consumed_v01_heldout_48")
        }
        if sum(len(rows) for rows in predictions_by_split.values()) != len(selected):
            raise SemanticPromptRawFloorCalibrationBuildError(
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
        semantic_rows = _evaluate_semantic_guardrails(
            config=config,
            diagnostics=held_diagnostics,
        )
        semantic_pass = all(bool(row["passed"]) for row in semantic_rows.values())
        is_control = (
            abs(float(title_threshold) - 0.5) <= 1e-12
            and abs(abstract_threshold - 0.625) <= 1e-12
        )
        if is_control:
            control_trial_id = trial_id

        trials.append(
            RawFloorCalibrationTrial(
                calibration_id=calibration_id,
                trial_id=trial_id,
                title_threshold=float(title_threshold),
                abstract_threshold=0.625,
                is_v02b_control_policy=is_control,
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
                    held_diagnostics["predicted_type_mismatch_sinks"].get("method", 0)
                ),
                max_predicted_type_mismatch_sink_count=max(
                    (
                        int(value)
                        for value in held_diagnostics[
                            "predicted_type_mismatch_sinks"
                        ].values()
                    ),
                    default=0,
                ),
                semantic_guardrails_passed=semantic_pass,
                eligible_for_selection=semantic_pass,
            )
        )

    if len(trials) != config.bounded_policy_search.expected_trial_count:
        raise SemanticPromptRawFloorCalibrationBuildError(
            "computed v0.2c trial count drifted"
        )
    if len({row.trial_id for row in trials}) != len(trials):
        raise SemanticPromptRawFloorCalibrationBuildError("duplicate trial_id")
    if control_trial_id is None:
        raise SemanticPromptRawFloorCalibrationBuildError(
            "v0.2b control policy missing from v0.2c title grid"
        )
    control = next(row for row in trials if row.trial_id == control_trial_id)
    control_metrics_reproduced = _control_reproduced(control)

    selected = select_raw_floor_trial(trials)
    hard_gates = _evaluate_selected_policy_gate(config=config, selected=selected)
    all_hard_gates = all(bool(row["passed"]) for row in hard_gates.values())
    desirable_threshold = (
        config.decision.selected_policy_minimum_consumed_heldout_relaxed_f1_desirable
    )
    desirable_signals = {
        "minimum_consumed_heldout_relaxed_f1": {
            "observed": selected.consumed_heldout_relaxed_f1,
            "threshold": desirable_threshold,
            "passed": selected.consumed_heldout_relaxed_f1 is not None
            and selected.consumed_heldout_relaxed_f1 >= desirable_threshold,
        }
    }
    selected_policy = RawFloorSelectedPolicy(
        calibration_id=calibration_id,
        selected_trial_id=selected.trial_id,
        title_threshold=selected.title_threshold,
        abstract_threshold=0.625,
        selection_objective=config.selection.primary_objective,
        hard_gates=hard_gates,
        desirable_signals=desirable_signals,
        all_hard_gates_passed=all_hard_gates,
        candidate_promising_for_future_freeze=all_hard_gates,
    )

    selected_at_floor = abs(
        selected.title_threshold - float(config.raw_inference.candidate_floor)
    ) <= 1e-12
    diagnostics = RawFloorCalibrationDiagnostics(
        calibration_id=calibration_id,
        trial_count=5,
        eligible_trial_count=sum(row.eligible_for_selection for row in trials),
        v02b_control_trial_id=control_trial_id,
        v02b_control_trial_eligible=control.eligible_for_selection,
        v02b_control_metrics_reproduced=control_metrics_reproduced,
        v02b_control_selected_prediction_delta=(
            control.selected_prediction_count
            - int(V02B_CONTROL["selected_prediction_count"])
        ),
        baseline_raw_evidence_preserved=bool(
            baseline_comparison["baseline_raw_evidence_preserved"]
        ),
        baseline_raw_missing_count=int(
            baseline_comparison["baseline_raw_missing_count"]
        ),
        baseline_raw_score_changed_count=int(
            baseline_comparison["baseline_raw_score_changed_count"]
        ),
        new_at_or_above_baseline_floor_count=int(
            baseline_comparison["new_at_or_above_baseline_floor_count"]
        ),
        new_selected_by_v02b_control_count=int(
            baseline_comparison["new_selected_by_v02b_control_count"]
        ),
        new_at_or_above_baseline_floor_mention_ids=list(
            baseline_comparison["new_at_or_above_baseline_floor_mention_ids"]
        ),
        selected_trial_id=selected.trial_id,
        selected_title_at_candidate_raw_floor=selected_at_floor,
        raw_input_floor_may_still_be_binding=selected_at_floor,
        raw_prediction_count=len(raw_predictions),
        raw_prediction_delta_vs_v02a=len(raw_predictions) - 1430,
    )

    trials_bytes = _jsonl_bytes(
        [row.model_dump(mode="json") for row in trials]
    )
    selected_bytes = _json_bytes(selected_policy.model_dump(mode="json"))
    diagnostics_bytes = _json_bytes(diagnostics.model_dump(mode="json"))
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "calibration_id": calibration_id,
        "candidate_id": config.lineage.candidate_id,
        "generated_at_utc": generated_at_utc.isoformat().replace("+00:00", "Z"),
        "config_path": _project_path(root, config_path),
        "config_sha256": canonical_config_sha256(config),
        "development_package_id": config.lineage.development_package_id,
        "development_package_manifest_sha256": _sha256_file(
            development_package_dir / "manifest.json"
        ),
        "baseline_raw_build_id": baseline_raw_manifest.build_id,
        "baseline_raw_build_manifest_sha256": _sha256_file(
            baseline_raw_build_dir / "manifest.json"
        ),
        "raw_build_id": raw_manifest.build_id,
        "raw_extractor_fingerprint": raw_manifest.extractor_fingerprint,
        "raw_build_manifest_sha256": _sha256_file(raw_build_dir / "manifest.json"),
        "raw_mentions_sha256": raw_manifest.mentions_sha256,
        "raw_input_floor": float(config.raw_inference.candidate_floor),
        "document_count": 72,
        "reference_mention_count": len(combined_references),
        "raw_prediction_count": len(raw_predictions),
        "raw_prediction_delta_vs_v02a": len(raw_predictions) - 1430,
        "trial_count": len(trials),
        "eligible_trial_count": diagnostics.eligible_trial_count,
        "v02b_control_metrics_reproduced": control_metrics_reproduced,
        "v02b_control_selected_prediction_delta": diagnostics.v02b_control_selected_prediction_delta,
        "baseline_raw_evidence_preserved": diagnostics.baseline_raw_evidence_preserved,
        "baseline_raw_missing_count": diagnostics.baseline_raw_missing_count,
        "baseline_raw_score_changed_count": diagnostics.baseline_raw_score_changed_count,
        "new_at_or_above_baseline_floor_count": diagnostics.new_at_or_above_baseline_floor_count,
        "new_selected_by_v02b_control_count": diagnostics.new_selected_by_v02b_control_count,
        "new_at_or_above_baseline_floor_mention_ids": diagnostics.new_at_or_above_baseline_floor_mention_ids,
        "selected_trial_id": selected.trial_id,
        "selected_title_threshold": selected.title_threshold,
        "selected_abstract_threshold": selected.abstract_threshold,
        "candidate_promising_for_future_freeze": all_hard_gates,
        "selected_title_at_candidate_raw_floor": selected_at_floor,
        "trials_file": "trials.jsonl",
        "trials_sha256": hashlib.sha256(trials_bytes).hexdigest(),
        "selected_policy_file": "selected_policy.json",
        "selected_policy_sha256": hashlib.sha256(selected_bytes).hexdigest(),
        "diagnostics_file": "diagnostics.json",
        "diagnostics_sha256": hashlib.sha256(diagnostics_bytes).hexdigest(),
        "model_inference_executed_during_calibration": False,
        "model_downloaded_during_calibration": False,
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
            "materialize_v02c_selected_policy_and_controlled_comparison"
            if all_hard_gates and not selected_at_floor
            else "review_remaining_raw_floor_binding_before_spending_fresh_heldout"
            if all_hard_gates and selected_at_floor
            else "choose_next_bounded_extractor_hypothesis_without_reusing_future_heldout"
        ),
    }
    readme = "\n".join(
        [
            "# Scientific Entity Semantic Prompt Raw-Floor Calibration v0.2c",
            "",
            f"calibration_id = `{calibration_id}`",
            f"raw_build_id = `{raw_manifest.build_id}`",
            f"raw_prediction_count = `{len(raw_predictions)}`",
            f"raw_prediction_delta_vs_v02a = `{len(raw_predictions) - 1430}`",
            f"trial_count = `{len(trials)}`",
            f"eligible_trial_count = `{diagnostics.eligible_trial_count}`",
            f"baseline_raw_evidence_preserved = `{str(diagnostics.baseline_raw_evidence_preserved).lower()}`",
            f"baseline_raw_missing_count = `{diagnostics.baseline_raw_missing_count}`",
            f"baseline_raw_score_changed_count = `{diagnostics.baseline_raw_score_changed_count}`",
            f"new_at_or_above_baseline_floor_count = `{diagnostics.new_at_or_above_baseline_floor_count}`",
            f"new_selected_by_v02b_control_count = `{diagnostics.new_selected_by_v02b_control_count}`",
            f"v02b_control_metrics_reproduced = `{str(control_metrics_reproduced).lower()}`",
            f"v02b_control_selected_prediction_delta = `{diagnostics.v02b_control_selected_prediction_delta}`",
            f"selected_trial_id = `{selected.trial_id}`",
            f"selected_title_threshold = `{selected.title_threshold}`",
            f"selected_abstract_threshold = `{selected.abstract_threshold}`",
            f"candidate_promising_for_future_freeze = `{str(all_hard_gates).lower()}`",
            f"selected_title_at_candidate_raw_floor = `{str(selected_at_floor).lower()}`",
            "",
            "This calibration performs no model inference. It evaluates only the five",
            "pre-frozen v0.2c title thresholds over the already-materialized 0.40 raw build,",
            "with abstract fixed at 0.625 and the v0.2b semantic guardrails unchanged.",
            "",
        ]
    )
    report = {
        "report": REPORT_NAME,
        "ok": True,
        "calibration_id": calibration_id,
        "raw_build_id": raw_manifest.build_id,
        "document_count": 72,
        "reference_mention_count": len(combined_references),
        "raw_prediction_count": len(raw_predictions),
        "raw_prediction_delta_vs_v02a": len(raw_predictions) - 1430,
        "trial_count": len(trials),
        "eligible_trial_count": diagnostics.eligible_trial_count,
        "baseline_raw_evidence_preserved": diagnostics.baseline_raw_evidence_preserved,
        "baseline_raw_missing_count": diagnostics.baseline_raw_missing_count,
        "baseline_raw_score_changed_count": diagnostics.baseline_raw_score_changed_count,
        "new_at_or_above_baseline_floor_count": diagnostics.new_at_or_above_baseline_floor_count,
        "new_selected_by_v02b_control_count": diagnostics.new_selected_by_v02b_control_count,
        "new_at_or_above_baseline_floor_mention_ids": diagnostics.new_at_or_above_baseline_floor_mention_ids,
        "v02b_control_metrics_reproduced": control_metrics_reproduced,
        "v02b_control_selected_prediction_delta": diagnostics.v02b_control_selected_prediction_delta,
        "selected_trial_id": selected.trial_id,
        "selected_title_threshold": selected.title_threshold,
        "selected_abstract_threshold": selected.abstract_threshold,
        "selected_combined_exact_f1": selected.combined_exact_f1,
        "selected_consumed_heldout_exact_f1": selected.consumed_heldout_exact_f1,
        "selected_consumed_heldout_relaxed_f1": selected.consumed_heldout_relaxed_f1,
        "selected_model_to_method_count": selected.model_to_method_count,
        "selected_method_to_task_count": selected.method_to_task_count,
        "selected_total_type_mismatch_count": selected.total_type_mismatch_count,
        "selected_method_semantic_sink_count": selected.method_semantic_sink_count,
        "all_hard_gates_passed": all_hard_gates,
        "candidate_promising_for_future_freeze": all_hard_gates,
        "selected_title_at_candidate_raw_floor": selected_at_floor,
        "raw_input_floor_may_still_be_binding": selected_at_floor,
        "model_inference_executed_during_calibration": False,
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
        "scientific-entity-semantic-prompt-raw-floor-calibration-v0.2c-"
        + generated_at_utc.strftime("%Y%m%dT%H%M%S%fZ")
    )


def build_semantic_prompt_raw_floor_calibration(
    *,
    project_root: Path,
    config_path: Path,
    development_package_dir: Path,
    baseline_raw_build_dir: Path,
    raw_build_dir: Path,
    output_root: Path | None = None,
    calibration_id: str | None = None,
    execute: bool = False,
    generated_at_utc: datetime | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or datetime.now(timezone.utc)
    if generated.tzinfo is None or generated.utcoffset() != timezone.utc.utcoffset(generated):
        raise SemanticPromptRawFloorCalibrationBuildError(
            "generated_at_utc must be timezone-aware UTC"
        )
    config = load_semantic_prompt_raw_floor_extension_config(config_path.resolve())
    selected_id = calibration_id or _default_calibration_id(generated)
    selected_output_root = output_root or _resolve(project_root, DEFAULT_OUTPUT_ROOT)
    output_dir = selected_output_root.resolve() / selected_id
    if execute and output_dir.exists():
        raise FileExistsError(f"immutable v0.2c calibration already exists: {output_dir}")

    prepared = _prepare_calibration(
        project_root=project_root,
        config_path=config_path,
        development_package_dir=development_package_dir,
        baseline_raw_build_dir=baseline_raw_build_dir,
        raw_build_dir=raw_build_dir,
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


def validate_semantic_prompt_raw_floor_calibration(
    *,
    project_root: Path,
    config_path: Path,
    calibration_dir: Path,
    development_package_dir: Path,
    baseline_raw_build_dir: Path,
    raw_build_dir: Path,
) -> dict[str, Any]:
    config = load_semantic_prompt_raw_floor_extension_config(config_path.resolve())
    resolved = calibration_dir.resolve()
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, details: str | None = None) -> None:
        checks.append(
            {"name": name, "ok": bool(ok), "required": True, "details": details}
        )

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
            RawFloorCalibrationTrial.model_validate(row)
            for row in _read_jsonl(resolved / "trials.jsonl")
        )
        selected = RawFloorSelectedPolicy.model_validate(
            _read_json(resolved / "selected_policy.json")
        )
        diagnostics = RawFloorCalibrationDiagnostics.model_validate(
            _read_json(resolved / "diagnostics.json")
        )
        add("output_contracts_parse", True)
    except Exception as exc:
        add("output_contracts_parse", False, f"{type(exc).__name__}: {exc}")
        return _validation_report(checks=checks, manifest=None)

    add("manifest_schema_version", manifest.get("schema_version") == MANIFEST_SCHEMA_VERSION)
    add("directory_matches_calibration_id", resolved.name == manifest.get("calibration_id"))
    add("config_sha256_matches", manifest.get("config_sha256") == canonical_config_sha256(config))
    add("candidate_id_matches", manifest.get("candidate_id") == config.lineage.candidate_id)
    add("development_package_id_matches", manifest.get("development_package_id") == config.lineage.development_package_id)
    add("raw_build_directory_matches", manifest.get("raw_build_id") == raw_build_dir.resolve().name)
    add("raw_input_floor_matches", manifest.get("raw_input_floor") == 0.4)
    add("document_count_matches", manifest.get("document_count") == 72)
    add("reference_count_matches", manifest.get("reference_mention_count") == 1316)
    add("trial_count_matches", len(trials) == 5)
    add("trial_ids_unique", len({row.trial_id for row in trials}) == 5)
    add(
        "title_grid_exact",
        {row.title_threshold for row in trials}
        == set(config.bounded_policy_search.title_thresholds),
    )
    add("abstract_fixed", {row.abstract_threshold for row in trials} == {0.625})
    add("exactly_one_v02b_control", sum(row.is_v02b_control_policy for row in trials) == 1)
    control = next((row for row in trials if row.is_v02b_control_policy), None)
    control_metrics_reproduced = control is not None and _control_reproduced(control)
    add(
        "v02b_control_metric_diagnostic_consistent",
        diagnostics.v02b_control_metrics_reproduced == control_metrics_reproduced,
    )
    add(
        "v02b_control_prediction_delta_recomputed",
        control is not None
        and diagnostics.v02b_control_selected_prediction_delta
        == control.selected_prediction_count - int(V02B_CONTROL["selected_prediction_count"]),
    )
    add(
        "raw_prediction_delta_recomputed",
        diagnostics.raw_prediction_delta_vs_v02a == diagnostics.raw_prediction_count - 1430,
    )

    try:
        documents, _ = _load_canonical(development_package_dir)
        baseline_manifest, baseline_predictions = _load_baseline_raw_predictions(
            baseline_raw_build_dir=baseline_raw_build_dir,
            documents=documents,
            config=config,
            project_root=project_root,
        )
        candidate_manifest, candidate_predictions = _load_raw_predictions(
            raw_build_dir=raw_build_dir,
            documents=documents,
            package_manifest=_read_json(development_package_dir / "manifest.json"),
            config=config,
            project_root=project_root,
        )
        baseline_comparison = _compare_baseline_raw_evidence(
            baseline_predictions=baseline_predictions,
            candidate_predictions=candidate_predictions,
            baseline_floor=float(config.raw_inference.baseline_floor),
            control_title_threshold=_v02b_control_thresholds(config)[0],
            control_abstract_threshold=_v02b_control_thresholds(config)[1],
        )
        add(
            "baseline_raw_build_id_matches",
            manifest.get("baseline_raw_build_id") == baseline_manifest.build_id,
        )
        add(
            "baseline_raw_build_manifest_sha",
            manifest.get("baseline_raw_build_manifest_sha256")
            == _sha256_file(baseline_raw_build_dir / "manifest.json"),
        )
        add(
            "baseline_raw_evidence_preserved",
            bool(baseline_comparison["baseline_raw_evidence_preserved"]),
        )
        add(
            "baseline_raw_missing_count_matches",
            diagnostics.baseline_raw_missing_count
            == baseline_comparison["baseline_raw_missing_count"],
        )
        add(
            "baseline_raw_score_changed_count_matches",
            diagnostics.baseline_raw_score_changed_count
            == baseline_comparison["baseline_raw_score_changed_count"],
        )
        add(
            "new_at_or_above_baseline_floor_count_matches",
            diagnostics.new_at_or_above_baseline_floor_count
            == baseline_comparison["new_at_or_above_baseline_floor_count"],
        )
        add(
            "new_selected_by_v02b_control_count_matches",
            diagnostics.new_selected_by_v02b_control_count
            == baseline_comparison["new_selected_by_v02b_control_count"],
        )
        add(
            "new_at_or_above_baseline_floor_ids_match",
            diagnostics.new_at_or_above_baseline_floor_mention_ids
            == baseline_comparison["new_at_or_above_baseline_floor_mention_ids"],
        )
    except Exception as exc:
        add(
            "baseline_raw_evidence_preserved",
            False,
            f"{type(exc).__name__}: {exc}",
        )

    trial_by_id = {row.trial_id: row for row in trials}
    add("selected_trial_exists", selected.selected_trial_id in trial_by_id)
    add(
        "selected_trial_is_eligible",
        selected.selected_trial_id in trial_by_id
        and trial_by_id[selected.selected_trial_id].eligible_for_selection,
    )
    if any(row.eligible_for_selection for row in trials):
        recomputed = select_raw_floor_trial(trials)
        add("selected_trial_recomputed", recomputed.trial_id == selected.selected_trial_id)
    else:
        add("selected_trial_recomputed", False, "no eligible trial")

    selected_trial = trial_by_id.get(selected.selected_trial_id)
    add(
        "selected_gate_recomputed",
        selected_trial is not None
        and selected.hard_gates
        == _evaluate_selected_policy_gate(config=config, selected=selected_trial),
    )
    add(
        "selected_promising_recomputed",
        selected.candidate_promising_for_future_freeze
        == all(bool(row["passed"]) for row in selected.hard_gates.values()),
    )
    selected_at_floor = (
        selected_trial is not None
        and abs(selected_trial.title_threshold - 0.4) <= 1e-12
    )
    add(
        "selected_floor_signal_recomputed",
        diagnostics.selected_title_at_candidate_raw_floor == selected_at_floor
        and diagnostics.raw_input_floor_may_still_be_binding == selected_at_floor,
    )

    required_false = (
        "model_inference_executed_during_calibration",
        "model_downloaded_during_calibration",
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

    try:
        generated = datetime.fromisoformat(
            str(manifest["generated_at_utc"]).replace("Z", "+00:00")
        )
        with tempfile.TemporaryDirectory(prefix="semantic-prompt-v02c-validation-") as tmp:
            report = build_semantic_prompt_raw_floor_calibration(
                project_root=project_root,
                config_path=config_path,
                development_package_dir=development_package_dir,
                baseline_raw_build_dir=baseline_raw_build_dir,
                raw_build_dir=raw_build_dir,
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
        add(
            "deterministic_byte_recomputation",
            False,
            f"{type(exc).__name__}: {exc}",
        )

    return _validation_report(checks=checks, manifest=manifest)


def _validation_report(
    *,
    checks: Sequence[Mapping[str, Any]],
    manifest: Mapping[str, Any] | None,
) -> dict[str, Any]:
    required_failed = [row for row in checks if row["required"] and not row["ok"]]
    return {
        "report": REPORT_NAME,
        "ok": not required_failed,
        "calibration_id": None if manifest is None else manifest.get("calibration_id"),
        "trial_count": None if manifest is None else manifest.get("trial_count"),
        "eligible_trial_count": None if manifest is None else manifest.get("eligible_trial_count"),
        "selected_title_threshold": None if manifest is None else manifest.get("selected_title_threshold"),
        "selected_abstract_threshold": None if manifest is None else manifest.get("selected_abstract_threshold"),
        "candidate_promising_for_future_freeze": None if manifest is None else manifest.get("candidate_promising_for_future_freeze"),
        "baseline_raw_evidence_preserved": None if manifest is None else manifest.get("baseline_raw_evidence_preserved"),
        "baseline_raw_missing_count": None if manifest is None else manifest.get("baseline_raw_missing_count"),
        "baseline_raw_score_changed_count": None if manifest is None else manifest.get("baseline_raw_score_changed_count"),
        "new_at_or_above_baseline_floor_count": None if manifest is None else manifest.get("new_at_or_above_baseline_floor_count"),
        "new_selected_by_v02b_control_count": None if manifest is None else manifest.get("new_selected_by_v02b_control_count"),
        "v02b_control_metrics_reproduced": None if manifest is None else manifest.get("v02b_control_metrics_reproduced"),
        "v02b_control_selected_prediction_delta": None if manifest is None else manifest.get("v02b_control_selected_prediction_delta"),
        "raw_prediction_count": None if manifest is None else manifest.get("raw_prediction_count"),
        "raw_prediction_delta_vs_v02a": None if manifest is None else manifest.get("raw_prediction_delta_vs_v02a"),
        "selected_title_at_candidate_raw_floor": None if manifest is None else manifest.get("selected_title_at_candidate_raw_floor"),
        "total_checks": len(checks),
        "required_failed_count": len(required_failed),
        "model_inference_executed_during_calibration": False if manifest is None else manifest.get("model_inference_executed_during_calibration"),
        "fresh_heldout_consumed": False if manifest is None else manifest.get("fresh_heldout_consumed"),
        "canonical_truth_mutated": False if manifest is None else manifest.get("canonical_truth_mutated"),
        "full_corpus_build_authorized": False if manifest is None else manifest.get("full_corpus_build_authorized"),
        "next_slice": None if manifest is None else manifest.get("next_slice"),
        "checks": list(checks),
    }
