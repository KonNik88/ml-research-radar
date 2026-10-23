"""Synthetic safeguards for 9C (never touches actual ML Research Radar state)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from radar_core.contracts.scientific_entity_full_ner_coverage_reference import ReferenceManifest, ReferenceSummary
from radar_core.entities import scientific_entity_full_ner_coverage_scoring_policy as module


SOURCE_CONFIG = Path(__file__).resolve().parents[2] / "configs/scientific_entity_full_ner_coverage_scoring_policy_v0.1.yaml"


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    c = module.load_policy_config(SOURCE_CONFIG)
    c["reference_config_path"] = "frozen/parent_config.yaml"
    c["reference_dir"] = "frozen"
    c["trusted_latest_pointer_path"] = "latest.json"
    c["output_dir"] = "output"
    config_path = tmp_path / "policy_config.yaml"
    config_path.write_text(yaml.safe_dump(c,sort_keys=True),encoding="utf-8")
    ref = tmp_path / "frozen"
    ref.mkdir()
    manifest = ReferenceManifest(
        schema_version="scientific_entity_full_ner_coverage_reference_manifest_v0.1",
        audit_id=c["audit_id"],reference_id=c["reference_id"],
        sample_manifest_sha256="a"*64,audit_fields_sha256="b"*64,
        annotations_sha256=c["expected_annotations_sha256"],
        reference_summary_sha256="c"*64,
        trusted_candidate_build_id=c["expected_candidate_build_id"],
        trusted_final_mentions_sha256=c["expected_final_mentions_sha256"],
        canonical_sha256="d"*64,source_working_path="work.jsonl",
        source_working_sha256=c["expected_annotations_sha256"],complete_annotation_count=120,
        uncertainty_policy="preserve_as_unresolved_for_preregistered_scoring",
        unblinding_executed=False,production_prediction_files_read=False,
        canonical_mutated=False,production_latest_mutated=False,reference_frozen=True,
        next_slice="preregister",files={},
    )
    summary = ReferenceSummary(
        schema_version="scientific_entity_full_ner_coverage_reference_summary_v0.1",
        audit_id=c["audit_id"], reference_id=c["reference_id"],
        field_count=120,title_count=60,abstract_count=60,mention_count=972,
        uncertain_mention_count=68,fields_with_uncertain_mentions=42,overlap_pair_count=5,
        entity_type_counts={"model":972},uncertain_entity_type_counts={"model":68},
        annotation_complete=True,uncertain_flags_preserved=True,prediction_blind=True,
        production_predictions_read=False,future_unblind_not_executed=True,
    )
    (ref/"manifest.json").write_bytes(module._json_bytes(manifest.model_dump(mode="json")))
    (ref/"summary.json").write_bytes(module._json_bytes(summary.model_dump(mode="json")))
    # In production 9B validates exact bytes. Here use fixed 9B annotation hash fixture.
    (ref/"annotations.jsonl").write_bytes(b"fixture\n")
    (tmp_path/"latest.json").write_bytes(module._json_bytes({
        "state":"trusted_latest","candidate_build_id":c["expected_candidate_build_id"],
        "candidate_final_mentions_sha256":c["expected_final_mentions_sha256"],
        "final_mention_count":846264,
    }))
    (ref/"parent_config.yaml").write_text("unused: true\n",encoding="utf-8")
    monkeypatch.setattr(module,"validate_frozen_reference",lambda *_: {"reference_validated":True,"required_failed_count":0})
    # The marker above assumes the validated reference's annotation digest was checked;
    # content fixture bytes cannot recreate the frozen real SHA.
    monkeypatch.setattr(module,"_file_sha",lambda p: c["expected_annotations_sha256"] if Path(p).name=="annotations.jsonl" else module._sha(Path(p).read_bytes()))
    return config_path


def test_config_real_load():
    cfg=module.load_policy_config(SOURCE_CONFIG)
    assert cfg["relaxed_iou_threshold"]==0.5
    assert cfg["primary_panel"]=="typed_exact"
    assert cfg["unblind_authorized_in_this_slice"] is False


def test_plan_is_read_only(tmp_path,monkeypatch):
    cfg=_fixture(tmp_path,monkeypatch)
    plan=module.plan_scoring_policy(cfg,tmp_path)
    assert not plan["plan_writes_output"]
    assert not plan["production_prediction_file_read"]
    assert plan["frozen_field_count"]==120
    assert not (tmp_path/"output").exists()


def test_execute_and_strict_validation(tmp_path,monkeypatch):
    cfg=_fixture(tmp_path,monkeypatch)
    result=module.execute_scoring_policy(cfg,tmp_path)
    assert result["policy_preregistered"]
    assert module.validate_scoring_policy(cfg,tmp_path)["required_failed_count"]==0
    assert sorted(p.name for p in (tmp_path/"output").iterdir())==["README.md","checksums.txt","manifest.json","policy.json"]


def test_execute_one_shot(tmp_path,monkeypatch):
    cfg=_fixture(tmp_path,monkeypatch)
    module.execute_scoring_policy(cfg,tmp_path)
    with pytest.raises(module.FullNerScoringPolicyError,match="already exists"):
        module.execute_scoring_policy(cfg,tmp_path)


def test_config_refuses_unblind(tmp_path):
    d=module.load_policy_config(SOURCE_CONFIG)
    d["unblind_authorized_in_this_slice"]=True
    p=tmp_path/"bad.yaml"
    p.write_text(yaml.safe_dump(d),encoding="utf-8")
    with pytest.raises(module.FullNerScoringPolicyError,match="must not read"):
        module.load_policy_config(p)


def test_config_refuses_threshold_changes(tmp_path):
    d=module.load_policy_config(SOURCE_CONFIG)
    d["relaxed_iou_threshold"]=0.75
    p=tmp_path/"bad.yaml"
    p.write_text(yaml.safe_dump(d),encoding="utf-8")
    with pytest.raises(module.FullNerScoringPolicyError,match="drift"):
        module.load_policy_config(p)


def test_latest_pointer_drift_fails_closed(tmp_path,monkeypatch):
    cfg=_fixture(tmp_path,monkeypatch)
    p=tmp_path/"latest.json"
    val=json.loads(p.read_text());val["candidate_final_mentions_sha256"]="other"
    p.write_bytes(module._json_bytes(val))
    with pytest.raises(module.FullNerScoringPolicyError,match="pointer metadata changed"):
        module.plan_scoring_policy(cfg,tmp_path)
    assert not (tmp_path/"output").exists()


def test_reference_manifest_drift_fails_closed(tmp_path,monkeypatch):
    cfg=_fixture(tmp_path,monkeypatch)
    p=tmp_path/"frozen"/"manifest.json"
    val=json.loads(p.read_text());val["reference_id"]="wrong"
    p.write_bytes(module._json_bytes(val))
    with pytest.raises(module.FullNerScoringPolicyError,match="lineage mismatch"):
        module.plan_scoring_policy(cfg,tmp_path)


def test_policy_tamper_strict_rejected(tmp_path,monkeypatch):
    cfg=_fixture(tmp_path,monkeypatch)
    module.execute_scoring_policy(cfg,tmp_path)
    p=tmp_path/"output"/"policy.json"
    p.write_bytes(p.read_bytes()+b"\n")
    assert module.validate_scoring_policy(cfg,tmp_path)["required_failed_count"]>0


def test_ledger_tamper_strict_rejected(tmp_path,monkeypatch):
    cfg=_fixture(tmp_path,monkeypatch)
    module.execute_scoring_policy(cfg,tmp_path)
    p=tmp_path/"output"/"checksums.txt"
    p.write_bytes(b"invalid\n")
    assert module.validate_scoring_policy(cfg,tmp_path)["required_failed_count"]>0


def test_absent_policy_not_validated(tmp_path,monkeypatch):
    cfg=_fixture(tmp_path,monkeypatch)
    assert module.validate_scoring_policy(cfg,tmp_path)["required_failed_count"]>0


def test_policy_derivation_deterministic(tmp_path,monkeypatch):
    cfg=_fixture(tmp_path,monkeypatch)
    prep=module._preflight(cfg,tmp_path)
    assert module._content(prep)==module._content(prep)
