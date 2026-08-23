from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pytest

from radar_core.contracts.scientific_entity_evidence import (
    ConfidenceKind,
    ExtractorKind,
    ScientificEntityExtractorDescriptor,
    ScientificEntityMentionEvidence,
    ScientificEntitySourceField,
    ScientificEntityType,
    build_evidence_id,
    build_extractor_fingerprint,
)
from radar_core.contracts.scientific_entity_evaluation import (
    ScientificEntityAnnotationMethod,
    ScientificEntityEvaluationManifest,
    build_reference_id,
)
from radar_core.contracts.scientific_entity_gliner_calibration import (
    ScientificEntityCalibrationDiagnostics,
    ScientificEntityCalibrationParetoFrontier,
    ScientificEntityCalibrationProfiles,
    ScientificEntityCalibrationTrial,
    ScientificEntityCalibrationTrialStage,
    ScientificEntityGLiNERCalibrationManifest,
    ScientificEntityThresholdPolicy,
    build_calibration_trial_id,
)
from radar_core.entities.scientific_entity_gliner_calibration import (
    ScientificEntityGLiNERCalibrationError,
    filter_predictions,
    gliner_calibration_config_sha256,
    load_gliner_calibration_config,
)
from scripts.entities.calibrate_scientific_entity_gliner import (
    REQUIRED_FILES,
    ScientificEntityGLiNERCalibrationBuildError,
    calibrate_gliner_predictions,
)
from scripts.entities.evaluate_scientific_entity_evidence import evaluate_evidence
from scripts.validation.check_scientific_entity_gliner_calibration import (
    validate_gliner_calibration,
)


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "configs" / "scientific_entity_gliner_dev_calibration_v0.1.yaml"
FIXTURE_ROOT = (
    ROOT
    / "tests"
    / "fixtures"
    / "scientific_entity_gliner_dev_calibration_v0_1"
)
FIXED_TIME = datetime(2026, 8, 23, 10, 0, 0, tzinfo=timezone.utc)
FIXED_ID = "scientific-entity-gliner-dev-calibration-fixture-v0.1"


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
        newline="\n",
    )


def _fixture_predictions() -> list[ScientificEntityMentionEvidence]:
    return [
        ScientificEntityMentionEvidence.model_validate(row)
        for row in _read_jsonl(FIXTURE_ROOT / "prediction_build" / "mentions.jsonl")
    ]


def _execute(tmp_path: Path) -> tuple[dict[str, object], Path]:
    report = calibrate_gliner_predictions(
        output_root=tmp_path,
        calibration_id=FIXED_ID,
        execute=True,
        generated_at_utc=FIXED_TIME,
    )
    return report, tmp_path / FIXED_ID


def _candidate_inputs(tmp_path: Path) -> dict[str, Path]:
    documents = tmp_path / "candidate" / "canonical_documents.jsonl"
    documents.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        ROOT / "tests" / "fixtures" / "scientific_entity_evaluation_v0_1"
        / "canonical_documents.jsonl",
        documents,
    )

    review_id = "scientific-entity-calibration-candidate-test-review-v0.1"
    reference_rows = _read_jsonl(
        ROOT / "tests" / "fixtures" / "scientific_entity_evaluation_v0_1"
        / "reference_mentions.jsonl"
    )
    for row in reference_rows:
        row["review_id"] = review_id
        row["annotation_method"] = (
            ScientificEntityAnnotationMethod.MANUAL_ADJUDICATED.value
        )
        row["reference_id"] = build_reference_id(
            review_id=review_id,
            mention_id=str(row["mention_id"]),
            annotation_method=ScientificEntityAnnotationMethod.MANUAL_ADJUDICATED,
            annotation_pass=int(row["annotation_pass"]),
        )
    references = tmp_path / "candidate" / "reference_mentions.jsonl"
    _write_jsonl(references, reference_rows)

    review_payload = _read_json(
        ROOT / "tests" / "fixtures" / "scientific_entity_evaluation_v0_1"
        / "review_manifest.json"
    )
    review_payload.update(
        {
            "review_id": review_id,
            "status": "reviewed_candidate",
            "annotation_method": "manual_adjudicated",
            "annotation_guideline_version": "candidate-test-guideline-v0.1",
            "annotator_ids": ["candidate-test-reviewer"],
            "reference_mentions_sha256": hashlib.sha256(
                references.read_bytes()
            ).hexdigest(),
        }
    )
    review_manifest = tmp_path / "candidate" / "review_manifest.json"
    _write_json(review_manifest, review_payload)

    descriptor = ScientificEntityExtractorDescriptor(
        schema_version="scientific_entity_extractor_descriptor_v0.1",
        name="synthetic_statistical_candidate",
        version="0.1.0",
        kind=ExtractorKind.STATISTICAL_MODEL,
        code_revision="candidate-test-code-v0.1",
        config_sha256="1" * 64,
        environment_sha256="2" * 64,
        model_name="synthetic/test-model",
        model_revision="3" * 40,
        model_artifact_sha256="4" * 64,
        model_license="test-only",
    )
    fingerprint = build_extractor_fingerprint(descriptor)
    build_id = "scientific-entity-calibration-candidate-test-build-v0.1"
    prediction_rows = _read_jsonl(FIXTURE_ROOT / "prediction_build" / "mentions.jsonl")
    for row in prediction_rows:
        row["build_id"] = build_id
        row["extractor_fingerprint"] = fingerprint
        row["evidence_id"] = build_evidence_id(
            mention_id=str(row["mention_id"]),
            extractor_fingerprint=fingerprint,
        )
    prediction_dir = tmp_path / "candidate" / "prediction_build"
    prediction_mentions = prediction_dir / "mentions.jsonl"
    _write_jsonl(prediction_mentions, prediction_rows)

    prediction_payload = _read_json(FIXTURE_ROOT / "prediction_build" / "manifest.json")
    prediction_payload.update(
        {
            "build_id": build_id,
            "status": "candidate",
            "extractor": descriptor.model_dump(mode="json"),
            "extractor_fingerprint": fingerprint,
            "mentions_sha256": hashlib.sha256(
                prediction_mentions.read_bytes()
            ).hexdigest(),
        }
    )
    _write_json(prediction_dir / "manifest.json", prediction_payload)
    quality_payload = _read_json(
        FIXTURE_ROOT / "prediction_build" / "data_quality_summary.json"
    )
    quality_payload.update(
        {
            "build_id": build_id,
            "status": "candidate",
            "test_backend_injected": True,
        }
    )
    _write_json(prediction_dir / "data_quality_summary.json", quality_payload)

    evaluation_id = "scientific-entity-calibration-candidate-test-evaluation-v0.1"
    evaluation_root = tmp_path / "candidate" / "evaluations"
    evaluation_report = evaluate_evidence(
        documents_path=documents,
        review_manifest_path=review_manifest,
        reference_mentions_path=references,
        prediction_manifest_path=prediction_dir / "manifest.json",
        prediction_mentions_path=prediction_mentions,
        output_root=evaluation_root,
        evaluation_id=evaluation_id,
        status="candidate",
        max_documents=4,
        execute=True,
        generated_at_utc=FIXED_TIME,
    )
    return {
        "documents": documents,
        "review_manifest": review_manifest,
        "references": references,
        "prediction_dir": prediction_dir,
        "baseline_dir": Path(evaluation_report["output_dir"]),
    }


def _check_map(report: dict[str, object]) -> dict[str, bool]:
    return {
        row["name"]: row["ok"]
        for row in report["checks"]  # type: ignore[index]
    }


def test_config_declares_bounded_non_cartesian_search() -> None:
    config = load_gliner_calibration_config(CONFIG_PATH)

    assert config.search.declared_trial_count == 127
    assert len(config.search.global_thresholds) == 9
    assert len(config.search.title_thresholds) == 7
    assert len(config.search.abstract_thresholds) == 9
    assert len(config.search.type_probe_thresholds) == 9
    assert config.search.full_source_field_by_type_cartesian_search_allowed is False
    assert config.search.combined_type_specific_policy_selection_allowed is False
    assert config.search.type_probes_diagnostic_only is True


def test_config_freezes_dev_only_safety_boundary() -> None:
    config = load_gliner_calibration_config(CONFIG_PATH)

    assert config.safety.model_inference_allowed is False
    assert config.safety.model_or_tokenizer_download_allowed is False
    assert config.safety.provider_api_allowed is False
    assert config.safety.canonical_truth_mutation_allowed is False
    assert config.safety.full_corpus_build_authorized is False
    assert config.profiles.promotion_verdict_allowed is False
    assert config.profiles.require_all_entity_types_represented is True


def test_config_hash_is_semantic_and_duplicate_keys_fail(tmp_path: Path) -> None:
    config = load_gliner_calibration_config(CONFIG_PATH)
    first = gliner_calibration_config_sha256(config)
    second = gliner_calibration_config_sha256(
        load_gliner_calibration_config(CONFIG_PATH)
    )
    assert first == second
    assert len(first) == 64

    duplicate = tmp_path / "duplicate.yaml"
    duplicate.write_text(
        CONFIG_PATH.read_text(encoding="utf-8")
        + "\nschema_version: scientific_entity_gliner_dev_calibration_config_v0.1\n",
        encoding="utf-8",
    )
    with pytest.raises(ScientificEntityGLiNERCalibrationError, match="duplicate key"):
        load_gliner_calibration_config(duplicate)


def test_threshold_policy_uses_type_override_then_source_then_default() -> None:
    policy = ScientificEntityThresholdPolicy(
        default_threshold=0.7,
        source_field_thresholds={ScientificEntitySourceField.TITLE: 0.6},
        entity_type_thresholds={ScientificEntityType.MODEL: 0.8},
    )

    assert policy.effective_threshold(
        source_field=ScientificEntitySourceField.TITLE,
        entity_type=ScientificEntityType.METHOD,
    ) == 0.6
    assert policy.effective_threshold(
        source_field=ScientificEntitySourceField.ABSTRACT,
        entity_type=ScientificEntityType.METHOD,
    ) == 0.7
    assert policy.effective_threshold(
        source_field=ScientificEntitySourceField.TITLE,
        entity_type=ScientificEntityType.MODEL,
    ) == 0.8


def test_filter_is_inclusive_and_does_not_change_evidence() -> None:
    predictions = _fixture_predictions()
    policy = ScientificEntityThresholdPolicy(
        default_threshold=0.8,
        source_field_thresholds={},
        entity_type_thresholds={},
    )

    selected = filter_predictions(
        predictions,
        policy=policy,
        input_threshold=0.5,
    )

    assert len(selected) == 10
    assert min(row.confidence_score for row in selected if row.confidence_score) == 0.8
    assert all(row in predictions for row in selected)
    assert all(row.confidence_kind == ConfidenceKind.MODEL_SCORE for row in selected)
    assert all(row.calibration_id is None for row in selected)


@pytest.mark.parametrize(
    "field,value,match",
    [
        ("confidence_kind", ConfidenceKind.RULE_SCORE, "model_score"),
        ("calibration_id", "not-allowed", "null mention calibration_id"),
        ("confidence_score", 0.49, "below the declared input threshold"),
    ],
)
def test_filter_fails_closed_on_invalid_score_semantics(
    field: str,
    value: object,
    match: str,
) -> None:
    row = _fixture_predictions()[0].model_copy(update={field: value})
    policy = ScientificEntityThresholdPolicy(
        default_threshold=0.5,
        source_field_thresholds={},
        entity_type_thresholds={},
    )
    with pytest.raises(ScientificEntityGLiNERCalibrationError, match=match):
        filter_predictions([row], policy=policy, input_threshold=0.5)


def test_trial_identity_is_stable_and_stage_specific() -> None:
    policy = ScientificEntityThresholdPolicy(
        default_threshold=0.5,
        source_field_thresholds={},
        entity_type_thresholds={},
    )
    baseline = build_calibration_trial_id(
        calibration_id=FIXED_ID,
        stage=ScientificEntityCalibrationTrialStage.BASELINE,
        policy=policy,
    )
    repeated = build_calibration_trial_id(
        calibration_id=FIXED_ID,
        stage="baseline",
        policy=policy.model_dump(mode="json"),
    )
    global_trial = build_calibration_trial_id(
        calibration_id=FIXED_ID,
        stage="global",
        policy=policy,
    )

    assert baseline == repeated
    assert baseline != global_trial
    assert baseline.startswith("calibration-trial:")


def test_default_plan_reuses_frozen_fixture_without_writing(tmp_path: Path) -> None:
    output_root = tmp_path / "calibrations"
    report = calibrate_gliner_predictions(
        output_root=output_root,
        calibration_id=FIXED_ID,
        generated_at_utc=FIXED_TIME,
    )

    assert report["mode"] == "plan"
    assert report["phase_complete"] is False
    assert report["input_document_count"] == 4
    assert report["reference_mention_count"] == 18
    assert report["input_prediction_mention_count"] == 17
    assert report["trial_count"] == 127
    assert report["model_inference_executed"] is False
    assert report["model_downloaded"] is False
    assert not output_root.exists()


def test_fixture_profiles_are_deterministic_and_dev_only() -> None:
    report = calibrate_gliner_predictions(
        calibration_id=FIXED_ID,
        generated_at_utc=FIXED_TIME,
    )
    profiles = report["profile_summary"]

    assert set(profiles) == {
        "precision_oriented_f0_5",
        "balanced_f1",
        "recall_oriented_f2",
    }
    assert {row["trial_id"] for row in profiles.values()} == {
        "calibration-trial:861119cbffdc75d00d889cc7e650a7ce"
    }
    assert all(row["policy"]["default_threshold"] == 0.65 for row in profiles.values())
    assert all(row["exact"]["f1"] == 0.848485 for row in profiles.values())


def test_execute_writes_immutable_contract_valid_directory(tmp_path: Path) -> None:
    report, output_dir = _execute(tmp_path)

    assert report["phase_complete"] is True
    assert {path.name for path in output_dir.iterdir()} == set(REQUIRED_FILES)
    manifest = ScientificEntityGLiNERCalibrationManifest.model_validate(
        _read_json(output_dir / "manifest.json")
    )
    trials = [
        ScientificEntityCalibrationTrial.model_validate(row)
        for row in _read_jsonl(output_dir / "trials.jsonl")
    ]
    ScientificEntityCalibrationParetoFrontier.model_validate(
        _read_json(output_dir / "pareto_frontier.json")
    )
    profiles = ScientificEntityCalibrationProfiles.model_validate(
        _read_json(output_dir / "recommended_profiles.json")
    )
    ScientificEntityCalibrationDiagnostics.model_validate(
        _read_json(output_dir / "diagnostics.json")
    )

    assert manifest.search_space_trial_count == 127
    assert len(trials) == 127
    assert Counter(row.stage for row in trials) == {
        ScientificEntityCalibrationTrialStage.BASELINE: 1,
        ScientificEntityCalibrationTrialStage.GLOBAL: 9,
        ScientificEntityCalibrationTrialStage.SOURCE_PAIR: 63,
        ScientificEntityCalibrationTrialStage.TYPE_PROBE: 54,
    }
    assert manifest.confidence_scores_reinterpreted_as_probabilities is False
    assert manifest.calibration_id_written_to_mentions is False
    assert manifest.current_dev_set_becomes_held_out is False
    assert manifest.production_extractor_selected is False
    assert all(row.selected_prediction_count > 0 for row in profiles.selections)
    assert all(row.all_entity_types_represented for row in profiles.selections)
    assert all(row.metrics.exact.f1 is not None for row in profiles.selections)


def test_type_probe_trials_are_never_profile_eligible(tmp_path: Path) -> None:
    _, output_dir = _execute(tmp_path)
    trials = [
        ScientificEntityCalibrationTrial.model_validate(row)
        for row in _read_jsonl(output_dir / "trials.jsonl")
    ]
    diagnostics = ScientificEntityCalibrationDiagnostics.model_validate(
        _read_json(output_dir / "diagnostics.json")
    )

    probes = [
        row
        for row in trials
        if row.stage == ScientificEntityCalibrationTrialStage.TYPE_PROBE
    ]
    assert len(probes) == 54
    assert all(not row.eligible_for_profile_selection for row in probes)
    assert diagnostics.combined_type_specific_policy_selected is False
    assert {row.entity_type for row in diagnostics.type_probe_rows} == set(
        ScientificEntityType
    )


def test_execute_refuses_overwrite(tmp_path: Path) -> None:
    _execute(tmp_path)
    with pytest.raises(FileExistsError, match="overwrite is forbidden"):
        _execute(tmp_path)


def test_fixture_status_rejects_spoofed_prediction_directory(tmp_path: Path) -> None:
    copied = tmp_path / "prediction_build"
    shutil.copytree(FIXTURE_ROOT / "prediction_build", copied)

    with pytest.raises(
        ScientificEntityGLiNERCalibrationBuildError,
        match="reserved for the tracked calibration fixture",
    ):
        calibrate_gliner_predictions(
            prediction_build_dir=copied,
            calibration_id=FIXED_ID,
        )


def test_current_canonical_path_is_rejected_before_read() -> None:
    with pytest.raises(
        ScientificEntityGLiNERCalibrationBuildError,
        match="Current canonical corpus is forbidden",
    ):
        calibrate_gliner_predictions(
            documents_path=ROOT
            / "data"
            / "analytics"
            / "reconciled"
            / "canonical_documents.jsonl",
            calibration_id=FIXED_ID,
        )


def test_candidate_status_rejects_fixture_inputs() -> None:
    with pytest.raises(
        ScientificEntityGLiNERCalibrationBuildError,
        match="reviewed_candidate",
    ):
        calibrate_gliner_predictions(
            status="candidate",
            calibration_id=FIXED_ID,
        )


def test_candidate_mode_executes_and_validates_hash_pinned_inputs(
    tmp_path: Path,
) -> None:
    inputs = _candidate_inputs(tmp_path)
    calibration_id = "scientific-entity-calibration-candidate-test-v0.1"
    output_root = tmp_path / "candidate" / "calibrations"

    report = calibrate_gliner_predictions(
        documents_path=inputs["documents"],
        review_manifest_path=inputs["review_manifest"],
        reference_mentions_path=inputs["references"],
        prediction_build_dir=inputs["prediction_dir"],
        baseline_evaluation_dir=inputs["baseline_dir"],
        output_root=output_root,
        calibration_id=calibration_id,
        status="candidate",
        max_documents=4,
        execute=True,
        generated_at_utc=FIXED_TIME,
    )
    checked = validate_gliner_calibration(
        calibration_dir=Path(report["output_dir"]),
        write_reports=False,
    )

    assert report["trial_count"] == 127
    assert report["next_slice"] == "review_and_freeze_one_gliner_dev_policy_v0.1"
    assert checked["summary"]["ok"] is True
    assert checked["summary"]["calibration_status"] == "candidate"


def test_baseline_metrics_are_hash_pinned_and_recomputed() -> None:
    baseline_dir = FIXTURE_ROOT / "baseline_evaluation"
    manifest = ScientificEntityEvaluationManifest.model_validate(
        _read_json(baseline_dir / "manifest.json")
    )
    metrics_sha = hashlib.sha256(
        (baseline_dir / "metrics.json").read_bytes()
    ).hexdigest()

    assert metrics_sha == manifest.metrics_sha256
    report = calibrate_gliner_predictions(
        calibration_id=FIXED_ID,
        generated_at_utc=FIXED_TIME,
    )
    assert report["trial_count"] == 127


def test_validator_recomputes_every_output_byte(tmp_path: Path) -> None:
    _, output_dir = _execute(tmp_path)
    report = validate_gliner_calibration(
        calibration_dir=output_dir,
        write_reports=False,
    )

    assert report["summary"]["ok"] is True
    checks = _check_map(report)
    assert checks["deterministic_recomputation_matches_all_outputs"] is True
    assert checks["type_probes_are_diagnostic_only"] is True
    assert report["verdict"]["production_extractor_selected"] is False
    assert report["verdict"]["full_corpus_build_authorized"] is False


def test_validator_fails_on_corrupted_output(tmp_path: Path) -> None:
    _, output_dir = _execute(tmp_path)
    readme = output_dir / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + "tampered\n",
        encoding="utf-8",
        newline="\n",
    )

    report = validate_gliner_calibration(
        calibration_dir=output_dir,
        write_reports=False,
    )

    assert report["summary"]["ok"] is False
    failed = set(report["verdict"]["required_failed_checks"])
    assert "checksum_matches::README.md" in failed
    assert "deterministic_recomputation_matches_all_outputs" in failed
