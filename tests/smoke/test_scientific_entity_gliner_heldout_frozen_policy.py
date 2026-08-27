from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from radar_core.contracts.scientific_entity_evidence import ScientificEntitySourceField
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
from radar_core.entities.scientific_entity_gliner_heldout_policy import load_config
from scripts.entities.build_scientific_entity_gliner_heldout_frozen_policy import build, main, parser
from scripts.entities.calibrate_scientific_entity_gliner import calibrate_gliner_predictions
from scripts.validation.check_scientific_entity_gliner_heldout_frozen_policy import validate

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "scientific_entity_gliner_heldout_frozen_policy_v0.1.yaml"
PARENT_FIXTURE = ROOT / "tests" / "fixtures" / "scientific_entity_gliner_dev_calibration_v0_1" / "prediction_build"
FIXED = datetime(2026, 8, 27, 12, 0, 0, tzinfo=timezone.utc)
CAL_ID = "scientific-entity-gliner-heldout-policy-calibration-fixture-v0.1"
BUILD_ID = "scientific-entity-gliner-heldout-policy-fixture-v0.1"
REVIEW_ID = "scientific-entity-heldout-review-fixture-v0.1"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _read_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def _read_jsonl(p: Path):
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def _write_json(p: Path, payload) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def _prepare_calibration(tmp: Path) -> tuple[Path, str]:
    root = tmp / "calibrations"
    calibrate_gliner_predictions(output_root=root, calibration_id=CAL_ID, execute=True, generated_at_utc=FIXED)
    cal_dir = root / CAL_ID
    policy = ScientificEntityThresholdPolicy(
        default_threshold=0.50,
        source_field_thresholds={ScientificEntitySourceField.TITLE:0.55, ScientificEntitySourceField.ABSTRACT:0.65},
        entity_type_thresholds={},
    )
    trial_id = build_calibration_trial_id(calibration_id=CAL_ID, stage=ScientificEntityCalibrationTrialStage.SOURCE_PAIR, policy=policy)
    trials=[ScientificEntityCalibrationTrial.model_validate(x) for x in _read_jsonl(cal_dir/"trials.jsonl")]
    target=next(x for x in trials if x.trial_id==trial_id)
    profiles=ScientificEntityCalibrationProfiles.model_validate(_read_json(cal_dir/"recommended_profiles.json"))
    selections=[]
    for row in profiles.selections:
        if row.profile_name != ScientificEntityCalibrationProfileName.BALANCED:
            selections.append(row)
        else:
            selections.append(ScientificEntityCalibrationProfileSelection(
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
            ))
    patched=ScientificEntityCalibrationProfiles(
        schema_version=CALIBRATION_PROFILES_SCHEMA_VERSION,
        calibration_id=CAL_ID,
        selections=selections,
        selected_trial_ids_may_repeat=True,
        selected_profile_is_production_extractor=False,
    )
    _write_json(cal_dir/"recommended_profiles.json", patched.model_dump(mode="json"))
    manifest=ScientificEntityGLiNERCalibrationManifest.model_validate(_read_json(cal_dir/"manifest.json"))
    mp=manifest.model_dump(mode="json")
    mp["profiles_sha256"]=_sha(cal_dir/"recommended_profiles.json")
    _write_json(cal_dir/"manifest.json", mp)
    return root, trial_id


def _prepare_fixture(tmp: Path) -> tuple[Path, Path]:
    parent_root=tmp/"parents"
    parent_dir=parent_root/"scientific-entity-evaluation-fixture-predictions-v0.1"
    shutil.copytree(PARENT_FIXTURE,parent_dir)

    ids=["synthetic-baseline-001","synthetic-baseline-002","synthetic-baseline-004"] + [f"heldout-fixture-{i:03d}" for i in range(45)]
    prepared=tmp/"prepared"/REVIEW_ID
    prepared.mkdir(parents=True)
    sample=prepared/"canonical_documents.sample.jsonl"
    sample.write_text("".join(json.dumps({"canonical_id":x}, separators=(",",":"))+"\n" for x in ids),encoding="utf-8",newline="\n")
    prep={
        "review_id":REVIEW_ID,
        "selected_document_count":48,
        "prediction_blind":True,
        "heldout_dev_overlap_count":0,
        "files":{"canonical_documents.sample.jsonl":_sha(sample)},
    }
    _write_json(prepared/"preparation_manifest.json",prep)

    manifest=_read_json(parent_dir/"manifest.json")
    manifest["canonical_input"]["path"]=str(sample).replace("\\","/")
    manifest["canonical_input"]["sha256"]=_sha(sample)
    manifest["canonical_input"]["document_count"]=48
    _write_json(parent_dir/"manifest.json",manifest)
    quality=_read_json(parent_dir/"data_quality_summary.json")
    quality["input_document_count"]=48
    _write_json(parent_dir/"data_quality_summary.json",quality)
    return parent_root, prepared


def _fixture_config(tmp: Path) -> Path:
    parent_root, prepared=_prepare_fixture(tmp)
    calibration_root, trial_id=_prepare_calibration(tmp)
    payload=yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    payload["heldout"].update({"review_id":REVIEW_ID,"prepared_dir":str(prepared).replace("\\","/")})
    payload["parent"].update({
        "build_id":"scientific-entity-evaluation-fixture-predictions-v0.1",
        "build_root":str(parent_root).replace("\\","/"),
        "expected_input_prediction_count":17,
        "expected_selected_prediction_count":15,
        "expected_rejected_prediction_count":2,
    })
    payload["policy_origin"].update({"calibration_id":CAL_ID,"calibration_root":str(calibration_root).replace("\\","/"),"selected_trial_id":trial_id})
    payload["outputs"]["root"]=str(tmp/"outputs").replace("\\","/")
    path=tmp/"config.yaml"
    path.write_text(yaml.safe_dump(payload,sort_keys=False),encoding="utf-8")
    return path


def test_real_config_pins_exact_heldout_application() -> None:
    c=load_config(CONFIG)
    assert c.parent.build_id == "scientific-entity-gliner-small-v2.5-v0.1-20260827T111030652864Z"
    assert (c.parent.expected_input_prediction_count,c.parent.expected_selected_prediction_count,c.parent.expected_rejected_prediction_count)==(1145,787,358)
    assert c.heldout.review_id == "scientific-entity-heldout-review-v0.1-20260827T092900455472Z"
    assert c.policy_origin.selected_trial_id == "calibration-trial:1172aea9d875d59f3b39cc21488dec8f"


def test_config_rejects_threshold_drift(tmp_path: Path) -> None:
    payload=yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    payload["policy_origin"]["policy"]["source_field_thresholds"]["abstract"]=0.70
    p=tmp_path/"bad.yaml"; p.write_text(yaml.safe_dump(payload,sort_keys=False),encoding="utf-8")
    with pytest.raises(Exception):
        load_config(p)


def test_cli_has_no_threshold_override() -> None:
    with pytest.raises(SystemExit):
        parser().parse_args(["--abstract-threshold","0.70"])




def test_cli_main_wires_config_to_build(tmp_path: Path) -> None:
    config = _fixture_config(tmp_path)
    rc = main([
        "--config", str(config),
        "--build-id", BUILD_ID,
        "--status", "fixture",
    ])
    assert rc == 0

def test_plan_execute_and_validator(tmp_path: Path) -> None:
    config=_fixture_config(tmp_path)
    planned=build(config_path=config,build_id=BUILD_ID,status="fixture",generated_at_utc=FIXED)
    assert planned["phase_complete"] is False
    assert (planned["input_prediction_count"],planned["selected_prediction_count"],planned["rejected_prediction_count"])==(17,15,2)
    assert planned["model_inference_executed"] is False
    executed=build(config_path=config,build_id=BUILD_ID,status="fixture",execute=True,generated_at_utc=FIXED)
    build_dir=Path(yaml.safe_load(config.read_text())["outputs"]["root"])/BUILD_ID
    assert executed["phase_complete"] is True
    report=validate(build_dir=build_dir,config_path=config)
    assert report["ok"] is True
    assert report["required_failed_count"] == 0
    assert report["selected_prediction_count"] == 15


def test_overwrite_forbidden(tmp_path: Path) -> None:
    config=_fixture_config(tmp_path)
    build(config_path=config,build_id=BUILD_ID,status="fixture",execute=True,generated_at_utc=FIXED)
    with pytest.raises(FileExistsError):
        build(config_path=config,build_id=BUILD_ID,status="fixture",execute=True,generated_at_utc=FIXED)
