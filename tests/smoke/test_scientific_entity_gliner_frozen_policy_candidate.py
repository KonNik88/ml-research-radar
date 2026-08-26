from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from radar_core.contracts.scientific_entity_evidence import (
    ScientificEntityMentionEvidence,
    ScientificEntitySourceField,
)
from radar_core.contracts.scientific_entity_gliner_calibration import (
    CALIBRATION_PROFILES_SCHEMA_VERSION,
    ScientificEntityCalibrationProfileName,
    ScientificEntityCalibrationProfileSelection,
    ScientificEntityCalibrationProfiles,
    ScientificEntityCalibrationTrial,
    ScientificEntityCalibrationTrialStage,
    ScientificEntityGLiNERCalibrationManifest,
    ScientificEntityThresholdPolicy,
    build_calibration_trial_id,
)
from radar_core.entities.scientific_entity_gliner_frozen_policy import (
    FROZEN_ABSTRACT_THRESHOLD,
    FROZEN_TITLE_THRESHOLD,
    ScientificEntityGLiNERFrozenPolicyError,
    load_gliner_frozen_policy_config,
)
from scripts.entities.build_scientific_entity_gliner_frozen_policy_candidate import (
    REQUIRED_FILES,
    ScientificEntityGLiNERFrozenPolicyBuildError,
    build_frozen_policy_candidate,
    build_parser,
)
from scripts.entities.calibrate_scientific_entity_gliner import calibrate_gliner_predictions
from scripts.validation.check_scientific_entity_gliner_frozen_policy_candidate import (
    validate_frozen_policy_candidate,
)


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "configs" / "scientific_entity_gliner_frozen_policy_candidate_v0.1.yaml"
PARENT_FIXTURE = (
    ROOT
    / "tests"
    / "fixtures"
    / "scientific_entity_gliner_dev_calibration_v0_1"
    / "prediction_build"
)
FIXED_TIME = datetime(2026, 8, 24, 10, 0, 0, tzinfo=timezone.utc)
CALIBRATION_ID = "scientific-entity-gliner-frozen-policy-calibration-fixture-v0.1"
BUILD_ID = "scientific-entity-gliner-frozen-policy-fixture-v0.1"


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _write_json(path: Path, payload: object) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _prepare_calibration(tmp_path: Path) -> tuple[Path, str]:
    output_root = tmp_path / "calibrations"
    calibrate_gliner_predictions(
        output_root=output_root,
        calibration_id=CALIBRATION_ID,
        execute=True,
        generated_at_utc=FIXED_TIME,
    )
    calibration_dir = output_root / CALIBRATION_ID
    policy = ScientificEntityThresholdPolicy(
        default_threshold=0.50,
        source_field_thresholds={
            ScientificEntitySourceField.TITLE: 0.55,
            ScientificEntitySourceField.ABSTRACT: 0.65,
        },
        entity_type_thresholds={},
    )
    trial_id = build_calibration_trial_id(
        calibration_id=CALIBRATION_ID,
        stage=ScientificEntityCalibrationTrialStage.SOURCE_PAIR,
        policy=policy,
    )
    trials = [
        ScientificEntityCalibrationTrial.model_validate(row)
        for row in _read_jsonl(calibration_dir / "trials.jsonl")
    ]
    target = next(row for row in trials if row.trial_id == trial_id)
    profiles = ScientificEntityCalibrationProfiles.model_validate(
        _read_json(calibration_dir / "recommended_profiles.json")
    )
    replacements = []
    for row in profiles.selections:
        if row.profile_name != ScientificEntityCalibrationProfileName.BALANCED:
            replacements.append(row)
            continue
        replacements.append(
            ScientificEntityCalibrationProfileSelection(
                profile_name=ScientificEntityCalibrationProfileName.BALANCED,
                beta=1.0,
                trial_id=target.trial_id,
                selection_metric="exact_f_beta",
                selection_score=target.metrics.exact.f1,
                policy=target.policy,
                selected_prediction_count=target.selected_prediction_count,
                all_entity_types_represented=True,
                metrics=target.metrics,
                dev_only=True,
                promotion_authorized=False,
            )
        )
    patched_profiles = ScientificEntityCalibrationProfiles(
        schema_version=CALIBRATION_PROFILES_SCHEMA_VERSION,
        calibration_id=CALIBRATION_ID,
        selections=replacements,
        selected_trial_ids_may_repeat=True,
        selected_profile_is_production_extractor=False,
    )
    profiles_path = calibration_dir / "recommended_profiles.json"
    _write_json(profiles_path, patched_profiles.model_dump(mode="json"))

    manifest = ScientificEntityGLiNERCalibrationManifest.model_validate(
        _read_json(calibration_dir / "manifest.json")
    )
    manifest_payload = manifest.model_dump(mode="json")
    manifest_payload["profiles_sha256"] = _sha256_file(profiles_path)
    _write_json(calibration_dir / "manifest.json", manifest_payload)
    return calibration_dir, trial_id


def _fixture_config(tmp_path: Path, *, calibration_id: str, trial_id: str) -> Path:
    payload = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    parent_manifest = _read_json(PARENT_FIXTURE / "manifest.json")
    payload["frozen"]["parent_build_id"] = parent_manifest["build_id"]
    payload["frozen"]["calibration_id"] = calibration_id
    payload["frozen"]["selected_trial_id"] = trial_id
    payload["frozen"]["expected_input_prediction_count"] = 17
    payload["frozen"]["expected_selected_prediction_count"] = 15
    payload["frozen"]["expected_rejected_prediction_count"] = 2
    path = tmp_path / "frozen_fixture_config.yaml"
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False, allow_unicode=True)
    return path


def _execute(tmp_path: Path) -> tuple[dict[str, object], Path, Path]:
    calibration_dir, trial_id = _prepare_calibration(tmp_path)
    config_path = _fixture_config(
        tmp_path,
        calibration_id=CALIBRATION_ID,
        trial_id=trial_id,
    )
    output_root = tmp_path / "builds"
    report = build_frozen_policy_candidate(
        config_path=config_path,
        parent_build_dir=PARENT_FIXTURE,
        calibration_dir=calibration_dir,
        output_root=output_root,
        build_id=BUILD_ID,
        status="fixture",
        execute=True,
        generated_at_utc=FIXED_TIME,
    )
    return report, output_root / BUILD_ID, config_path


def test_real_config_pins_exact_frozen_dev_decision() -> None:
    config = load_gliner_frozen_policy_config(CONFIG_PATH)
    assert config.frozen.parent_build_id == (
        "scientific-entity-gliner-small-v2.5-v0.1-20260822T143405630144Z"
    )
    assert config.frozen.calibration_id == (
        "scientific-entity-gliner-dev-calibration-v0.1-20260823T152930597192Z"
    )
    assert config.frozen.selected_trial_id == (
        "calibration-trial:1172aea9d875d59f3b39cc21488dec8f"
    )
    assert config.frozen.policy.source_field_thresholds[ScientificEntitySourceField.TITLE] == FROZEN_TITLE_THRESHOLD
    assert config.frozen.policy.source_field_thresholds[ScientificEntitySourceField.ABSTRACT] == FROZEN_ABSTRACT_THRESHOLD
    assert config.frozen.policy.entity_type_thresholds == {}
    assert config.frozen.expected_input_prediction_count == 546
    assert config.frozen.expected_selected_prediction_count == 391
    assert config.frozen.expected_rejected_prediction_count == 155


def test_config_rejects_threshold_drift(tmp_path: Path) -> None:
    payload = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    payload["frozen"]["policy"]["source_field_thresholds"]["abstract"] = 0.70
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with pytest.raises(Exception):
        load_gliner_frozen_policy_config(path)


def test_cli_exposes_no_threshold_override() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--title-threshold", "0.60"])


def test_plan_is_read_only_and_reports_frozen_counts(tmp_path: Path) -> None:
    calibration_dir, trial_id = _prepare_calibration(tmp_path)
    config_path = _fixture_config(tmp_path, calibration_id=CALIBRATION_ID, trial_id=trial_id)
    output_root = tmp_path / "builds"
    report = build_frozen_policy_candidate(
        config_path=config_path,
        parent_build_dir=PARENT_FIXTURE,
        calibration_dir=calibration_dir,
        output_root=output_root,
        build_id=BUILD_ID,
        status="fixture",
        generated_at_utc=FIXED_TIME,
    )
    assert report["mode"] == "plan"
    assert report["phase_complete"] is False
    assert report["input_prediction_count"] == 17
    assert report["selected_prediction_count"] == 15
    assert report["rejected_prediction_count"] == 2
    assert report["model_inference_executed"] is False
    assert not output_root.exists()


def test_execute_preserves_mentions_recomputes_evidence_and_writes_lineage(tmp_path: Path) -> None:
    report, build_dir, _ = _execute(tmp_path)
    assert report["phase_complete"] is True
    assert {path.name for path in build_dir.iterdir()} == set(REQUIRED_FILES)

    parent_rows = {
        row["mention_id"]: row for row in _read_jsonl(PARENT_FIXTURE / "mentions.jsonl")
    }
    candidate_rows = _read_jsonl(build_dir / "mentions.jsonl")
    lineage_rows = _read_jsonl(build_dir / "evidence_lineage.jsonl")
    assert len(candidate_rows) == len(lineage_rows) == 15
    lineage_by_mention = {row["mention_id"]: row for row in lineage_rows}
    for candidate in candidate_rows:
        parent = parent_rows[candidate["mention_id"]]
        assert candidate["mention_id"] == parent["mention_id"]
        assert candidate["evidence_id"] != parent["evidence_id"]
        assert candidate["surface_text"] == parent["surface_text"]
        assert candidate["entity_type"] == parent["entity_type"]
        assert candidate["source_field"] == parent["source_field"]
        assert candidate["char_start"] == parent["char_start"]
        assert candidate["char_end"] == parent["char_end"]
        assert candidate["confidence_score"] == parent["confidence_score"]
        line = lineage_by_mention[candidate["mention_id"]]
        assert line["parent_evidence_id"] == parent["evidence_id"]
        assert line["candidate_evidence_id"] == candidate["evidence_id"]


def test_execute_and_independent_validator_are_green(tmp_path: Path) -> None:
    _report, build_dir, config_path = _execute(tmp_path)
    validation = validate_frozen_policy_candidate(
        build_dir=build_dir,
        config_path=config_path,
        write_reports=False,
    )
    assert validation["summary"]["ok"] is True
    assert validation["summary"]["required_failed_count"] == 0
    assert validation["summary"]["mention_count"] == 15
    assert validation["verdict"]["production_extractor_selected"] is False
    assert validation["verdict"]["full_corpus_build_authorized"] is False


def test_overwrite_is_forbidden(tmp_path: Path) -> None:
    _report, build_dir, config_path = _execute(tmp_path)
    calibration_dir = tmp_path / "calibrations" / CALIBRATION_ID
    with pytest.raises(FileExistsError, match="overwrite is forbidden"):
        build_frozen_policy_candidate(
            config_path=config_path,
            parent_build_dir=PARENT_FIXTURE,
            calibration_dir=calibration_dir,
            output_root=build_dir.parent,
            build_id=BUILD_ID,
            status="fixture",
            execute=True,
            generated_at_utc=FIXED_TIME,
        )


def test_wrong_trial_fails_closed(tmp_path: Path) -> None:
    calibration_dir, trial_id = _prepare_calibration(tmp_path)
    config_path = _fixture_config(tmp_path, calibration_id=CALIBRATION_ID, trial_id=trial_id)
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    payload["frozen"]["selected_trial_id"] = "calibration-trial:" + "0" * 32
    config_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with pytest.raises(ScientificEntityGLiNERFrozenPolicyBuildError, match="frozen selected trial"):
        build_frozen_policy_candidate(
            config_path=config_path,
            parent_build_dir=PARENT_FIXTURE,
            calibration_dir=calibration_dir,
            output_root=tmp_path / "builds",
            build_id=BUILD_ID,
            status="fixture",
            generated_at_utc=FIXED_TIME,
        )
