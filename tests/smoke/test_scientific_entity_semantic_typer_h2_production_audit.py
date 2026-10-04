from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from radar_core.contracts.scientific_entity_evidence import ScientificEntitySourceField, ScientificEntityType
from radar_core.contracts.scientific_entity_semantic_typer_h2_full_corpus_candidate import H2FullCorpusFinalMention
from radar_core.contracts.scientific_entity_semantic_typer_h2_production_audit import H2ProductionAuditAnnotation, load_h2_production_audit_config
import radar_core.entities.scientific_entity_semantic_typer_h2_production_audit as mod

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "scientific_entity_semantic_typer_h2_production_audit_v0.3.yaml"


def _row(i: int, *, stratum: str) -> H2FullCorpusFinalMention:
    text = f"Entity{i} method"
    sha = hashlib.sha256(text.encode()).hexdigest()
    override = stratum == "override"
    fallback = stratum == "fallback_method"
    return H2FullCorpusFinalMention(
        build_id="b",
        candidate_evidence_id="evidence:" + f"{i:032x}"[-32:],
        final_mention_id="mention:" + f"{i+1000:032x}"[-32:],
        canonical_id=f"p{i}", source_field="title", source_text_sha256=sha,
        char_start=0, char_end=len(f"Entity{i}"), surface_text=f"Entity{i}",
        baseline_prediction_evidence_id="evidence:" + f"{i:032x}"[-32:],
        baseline_entity_type="method", baseline_confidence_score=0.9,
        semantic_typer_case_id=f"case-{i}",
        semantic_typer_predicted_entity_type="model" if override else "method",
        semantic_typer_used_baseline_fallback=fallback,
        semantic_typer_score_margin=0.2 if not fallback else None,
        h2_override_applied=override,
        final_entity_type="model" if override else "method",
        materialization_fingerprint_sha256="a" * 64,
    )


def test_config_freezes_blind_sample_and_promotion_gates() -> None:
    c = load_h2_production_audit_config(CONFIG)
    assert c.sampling.total_count == 240
    assert (c.sampling.override_count, c.sampling.preserved_method_count, c.sampling.fallback_method_count) == (100, 100, 40)
    assert c.annotation.prediction_blind is True
    assert c.promotion_gates.min_override_reference_model_rate == 0.45
    assert c.promotion_gates.max_override_reference_method_rate == 0.30
    assert c.safety.production_latest_promotion_authorized is False


def test_stratum_classification() -> None:
    assert mod._stratum(_row(1, stratum="override")) == "override"
    assert mod._stratum(_row(2, stratum="preserved_method")) == "preserved_method"
    assert mod._stratum(_row(3, stratum="fallback_method")) == "fallback_method"


def test_blind_case_contains_no_prediction_keys() -> None:
    config = load_h2_production_audit_config(CONFIG)
    selected = {"override": [_row(1, stratum="override")], "preserved_method": [], "fallback_method": []}
    source = {("p1", "title"): "Entity1 method"}
    cases = mod._build_blind_cases(config, selected, source)
    keys = set(cases[0].model_dump(mode="json"))
    assert not keys & mod.FORBIDDEN_BLIND_KEYS
    assert cases[0].surface_text == "Entity1"


def test_annotation_contract_requires_type_for_usable_span() -> None:
    base = dict(audit_id="a", audit_case_id="c", canonical_id="p", source_field="title", source_text_sha256=hashlib.sha256(b"BERT").hexdigest(), source_text="BERT", char_start=0, char_end=4, surface_text="BERT", annotation_confidence="high", annotation_complete=True)
    with pytest.raises(Exception):
        H2ProductionAuditAnnotation(**base, span_status="valid_entity_span", reference_entity_type=None)
    ok = H2ProductionAuditAnnotation(**base, span_status="valid_entity_span", reference_entity_type="model")
    assert ok.reference_entity_type == ScientificEntityType.MODEL


def test_plan_is_non_writing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = load_h2_production_audit_config(CONFIG)
    @dataclass
    class M:
        build_id: str = config.candidate.build_id
        materialization_fingerprint_sha256: str = config.candidate.materialization_fingerprint_sha256
    monkeypatch.setattr(mod, "_candidate_parent", lambda *args, **kwargs: {"manifest": M(), "summary": object()})
    report = mod.plan_or_execute_h2_production_audit_sample(project_root=ROOT, config_path=CONFIG, candidate_dir=tmp_path/"candidate", canonical_path=tmp_path/"canonical", output_root=tmp_path/"out", execute=False)
    assert report["plan_writes_output"] is False
    assert report["plan_reads_candidate_predictions"] is False
    assert not (tmp_path/"out").exists()


def test_deterministic_hash_rank_selection(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = load_h2_production_audit_config(CONFIG)
    rows = []
    for i in range(1, 151): rows.append(_row(i, stratum="override"))
    for i in range(201, 351): rows.append(_row(i, stratum="preserved_method"))
    for i in range(401, 471): rows.append(_row(i, stratum="fallback_method"))
    p = tmp_path/"final_mentions.jsonl"; p.write_text("".join(json.dumps(x.model_dump(mode="json"), sort_keys=True)+"\n" for x in rows), encoding="utf-8")
    a = mod._select_final_rows(tmp_path, config); b = mod._select_final_rows(tmp_path, config)
    assert {k:[x.baseline_prediction_evidence_id for x in v] for k,v in a.items()} == {k:[x.baseline_prediction_evidence_id for x in v] for k,v in b.items()}
    assert {k:len(v) for k,v in a.items()} == {"override":100,"preserved_method":100,"fallback_method":40}


def test_execute_writes_prediction_blind_package(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = load_h2_production_audit_config(CONFIG)
    @dataclass
    class M:
        build_id: str = config.candidate.build_id
        materialization_fingerprint_sha256: str = config.candidate.materialization_fingerprint_sha256
    monkeypatch.setattr(mod, "_candidate_parent", lambda *args, **kwargs: {"manifest": M(), "summary": object()})
    selected = {
        "override": [_row(i, stratum="override") for i in range(1,101)],
        "preserved_method": [_row(i, stratum="preserved_method") for i in range(101,201)],
        "fallback_method": [_row(i, stratum="fallback_method") for i in range(201,241)],
    }
    monkeypatch.setattr(mod, "_select_final_rows", lambda *args, **kwargs: selected)
    source = {(r.canonical_id, "title"): f"Entity{int(r.canonical_id[1:])} method" for rows in selected.values() for r in rows}
    monkeypatch.setattr(mod, "_load_source_texts", lambda *args, **kwargs: source)
    report = mod.plan_or_execute_h2_production_audit_sample(project_root=ROOT, config_path=CONFIG, candidate_dir=tmp_path/"candidate", canonical_path=tmp_path/"canonical", output_root=tmp_path/"out", execute=True)
    out = Path(report["output_dir"])
    assert report["phase_complete"] is True
    assert {p.name for p in out.iterdir()} == set(mod.REQUIRED_FILES)
    first = json.loads((out/"audit_cases.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert not set(first) & mod.FORBIDDEN_BLIND_KEYS


def test_prepare_annotation_work_copies_blank_mutable_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = load_h2_production_audit_config(CONFIG)
    audit = tmp_path/"audit"; audit.mkdir()
    manifest = {"schema_version":"scientific_entity_semantic_typer_h2_production_audit_manifest_v0.3","audit_id":config.sampling.audit_id,"candidate_build_id":config.candidate.build_id,"candidate_id":config.candidate.candidate_id,"candidate_fingerprint_sha256":config.candidate.candidate_fingerprint_sha256,"materialization_fingerprint_sha256":config.candidate.materialization_fingerprint_sha256,"canonical_sha256":config.canonical_snapshot.sha256,"canonical_document_count":61075,"audit_config_sha256":"a"*64,"selection_seed_sha256":config.sampling.selection_seed_sha256,"blind_order_seed_sha256":config.sampling.blind_order_seed_sha256,"audit_case_count":240,"override_count":100,"preserved_method_count":100,"fallback_method_count":40,"prediction_blind":True,"sampled_stratum_exposed_in_cases":False,"candidate_prediction_exposed_in_cases":False,"semantic_scores_exposed_in_cases":False,"model_inference_executed":False,"threshold_tuning_executed":False,"policy_revision_executed":False,"canonical_truth_mutated":False,"production_latest_promotion_authorized":False}
    (audit/"manifest.json").write_text(json.dumps(manifest),encoding="utf-8"); (audit/"blank_annotations.jsonl").write_text("{}\n",encoding="utf-8"); (audit/"reviewer.html").write_text("<html></html>",encoding="utf-8")
    report = mod.prepare_h2_production_audit_annotation_work(project_root=ROOT, config_path=CONFIG, audit_dir=audit, output_root=tmp_path/"work", execute=True)
    assert (Path(report["output_dir"])/"annotations_working.jsonl").exists()
    assert report["working_copy_is_mutable_non_evidence"] is True


def test_validator_accepts_recomputed_synthetic_package(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = load_h2_production_audit_config(CONFIG)
    @dataclass
    class M:
        build_id: str = config.candidate.build_id
        materialization_fingerprint_sha256: str = config.candidate.materialization_fingerprint_sha256
    parent = {"manifest": M(), "summary": object()}
    monkeypatch.setattr(mod, "_candidate_parent", lambda *args, **kwargs: parent)
    selected = {
        "override": [_row(i, stratum="override") for i in range(1,101)],
        "preserved_method": [_row(i, stratum="preserved_method") for i in range(101,201)],
        "fallback_method": [_row(i, stratum="fallback_method") for i in range(201,241)],
    }
    monkeypatch.setattr(mod, "_select_final_rows", lambda *args, **kwargs: selected)
    source = {(r.canonical_id, "title"): f"Entity{int(r.canonical_id[1:])} method" for rows in selected.values() for r in rows}
    monkeypatch.setattr(mod, "_load_source_texts", lambda *args, **kwargs: source)
    report = mod.plan_or_execute_h2_production_audit_sample(
        project_root=ROOT, config_path=CONFIG, candidate_dir=tmp_path/"candidate",
        canonical_path=tmp_path/"canonical", output_root=tmp_path/"out", execute=True,
    )
    checks, summary = mod.validate_h2_production_audit_sample(
        project_root=ROOT, config_path=CONFIG, audit_dir=Path(report["output_dir"]),
        candidate_dir=tmp_path/"candidate", canonical_path=tmp_path/"canonical",
    )
    assert all(ok for _, ok, _ in checks)
    assert summary["required_failed_count"] == 0
    assert summary["prediction_blind"] is True
