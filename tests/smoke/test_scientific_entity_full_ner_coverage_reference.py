"""Synthetic one-shot/safety coverage; does not touch real Radar data."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from radar_core.entities import scientific_entity_full_ner_coverage_reference as module


def _line(obj: dict) -> bytes:
    return (json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode()


def _setup(tmp_path:Path,monkeypatch:pytest.MonkeyPatch) -> tuple[Path,Path]:
    monkeypatch.setattr(module,"validate_sample_package",lambda *_: {"sample_validated":True,"required_failed_count":0})
    parent=tmp_path/"sample"
    parent.mkdir()
    sample_rows=[]
    annotations=[]
    for i,field in enumerate(["title","abstract"]):
        txt=f"BERT {i}"
        sha=hashlib.sha256(txt.encode()).hexdigest()
        fixed=dict(audit_id="audit",audit_case_id=f"coverage:{i}",canonical_id=f"c{i}",source_field=field,source_text=txt,source_text_sha256=sha)
        sample_rows.append(dict(schema_version="scientific_entity_full_ner_coverage_audit_field_v0.1",**fixed))
        annotations.append(dict(schema_version="scientific_entity_full_ner_coverage_annotation_working_v0.1",**fixed,
            annotation_complete=True,reviewer_note=None,mentions=[dict(entity_type="model",char_start=0,char_end=4,surface_text="BERT",uncertain=bool(i),reviewer_note="ambiguous" if i else None)]))
    (parent/"audit_fields.jsonl").write_bytes(b"".join(_line(x) for x in sample_rows))
    (parent/"manifest.json").write_bytes(_line(dict(audit_id="audit",prediction_blind=True,production_prediction_file_read=False,
        trusted_candidate_build_id="build",trusted_final_mentions_sha256="abc",canonical_sha256="def")))
    work=tmp_path/"work.jsonl"
    work.write_bytes(b"".join(_line(x) for x in annotations))
    config=dict(schema_version="scientific_entity_full_ner_coverage_reference_config_v0.1",
        audit_id="audit",reference_id="reference",parent_sampling_config_path="parent.yaml",
        parent_annotation_guide_path="guide.md",parent_sample_dir="sample",
        working_annotation_path="work.jsonl",output_dir="reference",
        expected_annotation_sha256=hashlib.sha256(work.read_bytes()).hexdigest(),
        expected_total_fields=2,expected_title_fields=1,expected_abstract_fields=1,
        expected_total_mentions=2,expected_uncertain_mentions=1,expected_overlap_pairs=0,
        unblind_authorized_in_this_slice=False,production_prediction_files_read_in_this_slice=False)
    config_path=tmp_path/"config.yaml"
    config_path.write_text(yaml.safe_dump(config),encoding="utf-8")
    return config_path,work


def test_plan_does_not_write(tmp_path,monkeypatch):
    cfg, _ = _setup(tmp_path,monkeypatch)
    result=module.plan_reference_freeze(cfg,tmp_path)
    assert result["annotation_complete_count"]==2
    assert result["uncertain_mention_count"]==1
    assert result["plan_writes_output"] is False
    assert not (tmp_path/"reference").exists()


def test_freeze_and_strict_validator(tmp_path,monkeypatch):
    cfg,work=_setup(tmp_path,monkeypatch)
    result=module.execute_reference_freeze(cfg,tmp_path)
    assert result["reference_frozen"]
    assert (tmp_path/"reference"/"annotations.jsonl").read_bytes()==work.read_bytes()
    validation=module.validate_frozen_reference(cfg,tmp_path)
    assert validation["required_failed_count"]==0,validation


def test_second_execute_fails_closed(tmp_path,monkeypatch):
    cfg,_=_setup(tmp_path,monkeypatch)
    module.execute_reference_freeze(cfg,tmp_path)
    with pytest.raises(module.FullNerReferenceError,match="already exists"):
        module.execute_reference_freeze(cfg,tmp_path)


def test_source_byte_drift_fails(tmp_path,monkeypatch):
    cfg,work=_setup(tmp_path,monkeypatch)
    work.write_bytes(work.read_bytes()+b"\n")
    with pytest.raises(module.FullNerReferenceError,match="SHA mismatch"):
        module.plan_reference_freeze(cfg,tmp_path)
    assert not (tmp_path/"reference").exists()


def test_source_content_drift_fails_even_with_updated_sha(tmp_path,monkeypatch):
    cfg,work=_setup(tmp_path,monkeypatch)
    text=work.read_text().replace('BERT 0','BERT 9',1)
    work.write_text(text,encoding="utf-8")
    data=yaml.safe_load(cfg.read_text()); data["expected_annotation_sha256"]=module._file_sha(work)
    cfg.write_text(yaml.safe_dump(data))
    with pytest.raises(module.FullNerReferenceError):
        module.plan_reference_freeze(cfg,tmp_path)


def test_not_complete_fails_even_with_updated_sha(tmp_path,monkeypatch):
    cfg,work=_setup(tmp_path,monkeypatch)
    rows=[json.loads(x) for x in work.read_text().splitlines()]
    rows[0]["annotation_complete"]=False
    work.write_bytes(b"".join(_line(x) for x in rows))
    data=yaml.safe_load(cfg.read_text());data["expected_annotation_sha256"]=module._file_sha(work)
    cfg.write_text(yaml.safe_dump(data))
    with pytest.raises(module.FullNerReferenceError,match="Incomplete"):
        module.plan_reference_freeze(cfg,tmp_path)


def test_uncertain_without_note_fails(tmp_path,monkeypatch):
    cfg,work=_setup(tmp_path,monkeypatch)
    rows=[json.loads(x) for x in work.read_text().splitlines()]
    rows[1]["mentions"][0]["reviewer_note"]=None
    work.write_bytes(b"".join(_line(x) for x in rows))
    data=yaml.safe_load(cfg.read_text());data["expected_annotation_sha256"]=module._file_sha(work)
    cfg.write_text(yaml.safe_dump(data))
    with pytest.raises(module.FullNerReferenceError,match="without explanation"):
        module.plan_reference_freeze(cfg,tmp_path)


def test_tampered_frozen_reference_rejected(tmp_path,monkeypatch):
    cfg,_=_setup(tmp_path,monkeypatch)
    module.execute_reference_freeze(cfg,tmp_path)
    p=tmp_path/"reference"/"annotations.jsonl"
    p.write_bytes(p.read_bytes().replace(b'BERT',b'XXXX'))
    assert module.validate_frozen_reference(cfg,tmp_path)["required_failed_count"]>0


def test_tampered_checksum_rejected(tmp_path,monkeypatch):
    cfg,_=_setup(tmp_path,monkeypatch)
    module.execute_reference_freeze(cfg,tmp_path)
    p=tmp_path/"reference"/"checksums.txt"
    p.write_bytes(b'bad  annotations.jsonl\n')
    assert module.validate_frozen_reference(cfg,tmp_path)["required_failed_count"]>0


def test_config_forbids_unblind(tmp_path,monkeypatch):
    cfg,_=_setup(tmp_path,monkeypatch)
    data=yaml.safe_load(cfg.read_text());data["unblind_authorized_in_this_slice"]=True
    cfg.write_text(yaml.safe_dump(data))
    with pytest.raises(module.FullNerReferenceError,match="prediction-blind"):
        module.plan_reference_freeze(cfg,tmp_path)
