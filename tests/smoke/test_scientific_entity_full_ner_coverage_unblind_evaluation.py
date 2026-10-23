"""Scoring invariants and fail-closed synthetic selected-prediction read for 9D."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from radar_core.contracts.scientific_entity_full_ner_coverage_audit import FullNerCoverageAnnotationRow
from radar_core.contracts.scientific_entity_full_ner_coverage_unblind_evaluation import FullNerUnblindPrediction
from radar_core.entities.scientific_entity_full_ner_coverage_unblind_evaluation import (
    FullNerUnblindError, _collect_predictions, _diagnostics, _match, _metrics,
    _primary_partition, _stats, load_unblind_config,
)


def mention(start: int, end: int, kind: str, *, uncertain: bool = False):
    return SimpleNamespace(char_start=start, char_end=end, entity_type=kind,
                           surface_text=f"s{start}-{end}", uncertain=uncertain)


def test_exact_typed_vs_span_only():
    gold = [mention(0, 5, "model")]
    pred = [mention(0, 5, "method")]
    assert _match(gold, pred, "span_only_exact") == [(0, 0)]
    assert _match(gold, pred, "typed_exact") == []


def test_relaxed_iou_half_and_boundary():
    assert _match([mention(0, 10, "model")], [mention(5, 10, "model")], "typed_relaxed") == [(0, 0)]
    assert _match([mention(0, 10, "model")], [mention(6, 10, "model")], "typed_relaxed") == []


def test_maximize_cardinality_not_greedy():
    gold = [mention(0, 10, "task"), mention(8, 18, "task")]
    preds = [mention(0, 10, "task"), mention(0, 18, "task")]
    # gold0 pred0 exact; gold1 pred1 IoU 10/18; two matches beat one.
    assert len(_match(gold, preds, "typed_relaxed")) == 2


def test_maximum_iou_breaks_equal_cardinality():
    gold = [mention(0, 10, "task")]
    preds = [mention(0, 10, "task"), mention(2, 10, "task")]
    assert _match(gold, preds, "typed_relaxed") == [(0, 0)]


def test_deterministic_ties():
    gold = [mention(0, 10, "task"), mention(0, 10, "task")]
    preds = [mention(0, 10, "task"), mention(0, 10, "task")]
    a = _match(gold, preds, "typed_exact")
    assert a == _match(gold, preds, "typed_exact")
    assert len(a) == 2


def test_nested_gold_not_collapsed():
    gold = [mention(0, 18, "task"), mention(2, 6, "model")]
    preds = [mention(0, 18, "task"), mention(2, 6, "model")]
    assert len(_match(gold, preds, "typed_exact")) == 2


def test_primary_uncertain_only_predictions_ignored():
    row = SimpleNamespace(mentions=[mention(0, 10, "method", uncertain=True), mention(20, 30, "model")])
    pred = [mention(3, 7, "model"), mention(20, 30, "model")]
    gold, retained, ignored = _primary_partition(row, pred)
    assert len(gold) == 1 and len(retained) == 1 and ignored == 1


def test_certain_precedence_over_uncertain_overlap():
    row = SimpleNamespace(mentions=[mention(0, 10, "method", uncertain=True), mention(8, 15, "model")])
    gold, retained, ignored = _primary_partition(row, [mention(9, 12, "model")])
    assert len(gold) == 1 and len(retained) == 1 and ignored == 0


def test_duplicate_predictions_counted_separately():
    a = [mention(0, 5, "task")]
    b = [mention(0, 5, "task"), mention(0, 5, "task")]
    matches = _match(a, b, "typed_exact")
    assert _stats(len(matches), len(b)-len(matches), len(a)-len(matches))["fp"] == 1


def test_zero_denominator_is_null():
    s = _stats(0, 0, 0)
    assert s["precision"] is None and s["recall"] is None and s["f1"] is None


def test_diagnostics_type_only_and_boundary():
    gold = [mention(0, 10, "model"), mention(20, 30, "task")]
    preds = [SimpleNamespace(**vars(mention(0, 10, "method")),final_mention_id="a"),
             SimpleNamespace(**vars(mention(22, 30, "task")),final_mention_id="b")]
    result = _diagnostics(gold, preds, [])
    assert {r["category"] for r in result["diagnosed"]} == {"type_only_exact_span", "boundary_only_same_type"}


def _field(text: str = "ABCD", *, uncertain: bool = False) -> FullNerCoverageAnnotationRow:
    return FullNerCoverageAnnotationRow(
        schema_version="scientific_entity_full_ner_coverage_annotation_working_v0.1",
        audit_id="audit", audit_case_id="case01", canonical_id="paper01", source_field="title",
        source_text=text, source_text_sha256=hashlib.sha256(text.encode()).hexdigest(),
        mentions=[{"entity_type":"model", "char_start":0, "char_end":4, "surface_text":"ABCD", "uncertain":uncertain,
                   "reviewer_note":"ambiguous" if uncertain else None}],
        annotation_complete=True, reviewer_note=None,
    )


def _prediction(field: FullNerCoverageAnnotationRow) -> FullNerUnblindPrediction:
    return FullNerUnblindPrediction(
        schema_version="scientific_entity_full_ner_coverage_unblind_prediction_v0.1",
        audit_case_id=field.audit_case_id, canonical_id=field.canonical_id, source_field="title",
        final_mention_id="mention:" + "a"*32, char_start=0, char_end=4,
        surface_text="ABCD", entity_type="model", source_text_sha256=field.source_text_sha256,
    )


def test_metrics_primary_and_sensitivity():
    field = _field(uncertain=True)
    selected = {(field.canonical_id, field.source_field):[_prediction(field)]}
    primary, cases, _, ignored = _metrics([field],selected,sensitivity=False)
    alternative, _, _, other_ignored = _metrics([field],selected,sensitivity=True)
    assert ignored == 1 and other_ignored == 0
    assert primary["balanced"]["typed_exact"]["f1"] is None
    assert alternative["balanced"]["typed_exact"]["f1"] == 1
    assert len(cases) == 1


def test_config_freeze_accepts_expected_and_rejects_drift(tmp_path: Path):
    from radar_core.entities.scientific_entity_full_ner_coverage_unblind_evaluation import EXPECTED
    import yaml
    cfg = {**EXPECTED,
           "schema_version":"scientific_entity_full_ner_coverage_unblind_evaluation_config_v0.1",
           "evaluation_id":"scientific-entity-full-ner-coverage-unblind-evaluation-v0.1-3cc6e3c779fee351",
           **{k:"path" for k in ("policy_config_path", "policy_dir", "reference_dir", "trusted_latest_pointer_path", "output_dir")}}
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg),encoding="utf-8")
    assert load_unblind_config(path)["primary_panel"] == "typed_exact"
    cfg["model_inference_allowed"] = True
    path.write_text(yaml.safe_dump(cfg),encoding="utf-8")
    with pytest.raises(FullNerUnblindError):
        load_unblind_config(path)


def test_prediction_stream_sha_count_and_target_selection(tmp_path: Path,monkeypatch:pytest.MonkeyPatch):
    import radar_core.entities.scientific_entity_full_ner_coverage_unblind_evaluation as mod
    row = _field()
    payload = {"canonical_id":"paper01","source_field":"title", "build_id":"build",
               "source_text_sha256":row.source_text_sha256,"char_start":0,"char_end":4,
               "surface_text":"ABCD","final_mention_id":"mention:"+"a"*32,
               "final_entity_type":"model"}
    path = tmp_path / "final_mentions.jsonl"
    raw = (json.dumps(payload)+"\n"+json.dumps({"canonical_id":"unrelated", "source_field":"title"})+"\n").encode()
    path.write_bytes(raw)
    monkeypatch.setattr(mod.H2FullCorpusFinalMention, "model_validate", classmethod(lambda cls,obj: SimpleNamespace(**{**obj, "source_field": SimpleNamespace(value=obj["source_field"]), "final_entity_type": SimpleNamespace(value=obj["final_entity_type"])})))
    selected, lines = _collect_predictions(path,[row],expected_hash=hashlib.sha256(raw).hexdigest(),expected_count=2,expected_build="build")
    assert lines == 2 and len(selected[("paper01", "title")]) == 1
    with pytest.raises(FullNerUnblindError,match="SHA/count mismatch"):
        _collect_predictions(path,[row],expected_hash="0"*64,expected_count=2,expected_build="build")


def test_prediction_stream_rejects_source_drift(tmp_path: Path,monkeypatch:pytest.MonkeyPatch):
    import radar_core.entities.scientific_entity_full_ner_coverage_unblind_evaluation as mod
    row = _field()
    payload = {"canonical_id":"paper01","source_field":"title","build_id":"build",
               "source_text_sha256":"0"*64,"char_start":0,"char_end":4,"surface_text":"ABCD",
               "final_mention_id":"mention:"+"b"*32,"final_entity_type":"model"}
    path=tmp_path / "final_mentions.jsonl"
    raw=(json.dumps(payload)+"\n").encode()
    path.write_bytes(raw)
    monkeypatch.setattr(mod.H2FullCorpusFinalMention, "model_validate", classmethod(lambda cls,obj: SimpleNamespace(**{**obj, "source_field": SimpleNamespace(value=obj["source_field"]), "final_entity_type": SimpleNamespace(value=obj["final_entity_type"])})))
    with pytest.raises(FullNerUnblindError,match="Source text drift"):
        _collect_predictions(path,[row],expected_hash=hashlib.sha256(raw).hexdigest(),expected_count=1,expected_build="build")


def test_execute_validate_one_shot_and_tamper_detection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """End-to-end immutable writer/validator with wholly synthetic 120-field data."""
    import yaml
    import radar_core.entities.scientific_entity_full_ner_coverage_unblind_evaluation as mod

    fields = []
    mention_sequence = 0
    for i in range(120):
        n_mentions = 9 if i < 12 else 8  # 972 total
        text = "ABCDEFGH " * n_mentions
        mentions = []
        for j in range(n_mentions):
            uncertain = mention_sequence < 68
            mention_sequence += 1
            mentions.append({"entity_type":"method", "char_start":9*j, "char_end":9*j+8,
                             "surface_text":"ABCDEFGH", "uncertain":uncertain,
                             "reviewer_note":"unclear" if uncertain else None})
        fields.append(FullNerCoverageAnnotationRow(
            schema_version="scientific_entity_full_ner_coverage_annotation_working_v0.1",
            audit_id="audit", audit_case_id=f"case-{i:03d}", canonical_id=f"paper-{i:03d}",
            source_field="title" if i < 60 else "abstract", source_text=text,
            source_text_sha256=hashlib.sha256(text.encode()).hexdigest(),
            mentions=mentions,annotation_complete=True,reviewer_note=None,
        ))
    assert sum(len(r.mentions) for r in fields) == 972
    assert sum(m.uncertain for r in fields for m in r.mentions) == 68
    cfg = {**mod.EXPECTED,
           "schema_version":"scientific_entity_full_ner_coverage_unblind_evaluation_config_v0.1",
           "evaluation_id":"scientific-entity-full-ner-coverage-unblind-evaluation-v0.1-3cc6e3c779fee351",
           **{k:"fake" for k in ("policy_config_path", "policy_dir", "reference_dir", "trusted_latest_pointer_path")},
           "output_dir":"out/evaluation"}
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg),encoding="utf-8")
    prepared = {"cfg":cfg,"rows":fields,"candidate_path":tmp_path/"dummy",
                **{k:"0"*64 for k in ("config_sha","reference_manifest_sha","reference_annotation_sha",
                                       "policy_manifest_sha","policy_record_sha","pointer_sha")}}
    prepared["reference_annotation_sha"] = cfg["expected_reference_sha256"]
    selected = {(r.canonical_id,r.source_field):[] for r in fields}
    monkeypatch.setattr(mod,"_preflight",lambda *args:prepared)
    monkeypatch.setattr(mod,"_collect_predictions",lambda *args,**kwargs:(selected,846264))
    monkeypatch.setattr(mod,"_revalidate_inputs",lambda *args:None)
    assert mod.plan_unblind_evaluation(path,tmp_path)["production_prediction_file_read"] is False
    completed = mod.execute_unblind_evaluation(path,tmp_path)
    assert completed["evaluation_executed"] and completed["model_inference_executed"] is False
    assert mod.validate_unblind_evaluation(path,tmp_path)["required_failed_count"] == 0
    with pytest.raises(FullNerUnblindError, match="already exists"):
        mod.execute_unblind_evaluation(path,tmp_path)
    (tmp_path/"out/evaluation/summary.json").write_bytes(b"{}\n")
    assert mod.validate_unblind_evaluation(path,tmp_path)["required_failed_count"] > 0


def test_real_h2_candidate_record_contract_selected(tmp_path: Path):
    """Exercise real H2 Pydantic schema rather than a mocked source row."""
    row = _field()
    item = {
        "schema_version":"scientific_entity_semantic_typer_h2_full_corpus_final_mention_v0.3",
        "build_id":"build", "candidate_evidence_id":"evidence:"+"1"*32,
        "final_mention_id":"mention:"+"2"*32,
        "canonical_id":row.canonical_id,"source_field":row.source_field,
        "source_text_sha256":row.source_text_sha256,
        "char_start":0,"char_end":4,"surface_text":"ABCD",
        "baseline_prediction_evidence_id":"evidence:"+"3"*32,
        "baseline_entity_type":"task", "baseline_confidence_score":0.91,
        "h2_override_applied":False,"final_entity_type":"task",
        "materialization_fingerprint_sha256":"4"*64,
    }
    raw = (json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path = tmp_path / "candidate.jsonl"
    path.write_bytes(raw)
    selected, count = _collect_predictions(path,[row],expected_hash=hashlib.sha256(raw).hexdigest(),
                                           expected_count=1,expected_build="build")
    assert count == 1
    match = selected[(row.canonical_id,row.source_field)][0]
    assert match.entity_type == "task" and match.final_mention_id == item["final_mention_id"]


def test_prediction_stream_preserves_same_id_duplicate_rows_as_fp(tmp_path: Path):
    """9C: identical predictions are separate occurrences, not a hard error."""
    row = _field()
    payload = {
        "schema_version":"scientific_entity_semantic_typer_h2_full_corpus_final_mention_v0.3",
        "build_id":"build", "candidate_evidence_id":"evidence:" + "1" * 32,
        "final_mention_id":"mention:" + "2" * 32,
        "canonical_id":row.canonical_id, "source_field":row.source_field,
        "source_text_sha256":row.source_text_sha256,
        "char_start":0, "char_end":4, "surface_text":"ABCD",
        "baseline_prediction_evidence_id":"evidence:" + "3" * 32,
        "baseline_entity_type":"model", "baseline_confidence_score":0.91,
        "h2_override_applied":False, "final_entity_type":"model",
        "materialization_fingerprint_sha256":"4" * 64,
    }
    duplicate = {**payload,
                 "candidate_evidence_id":"evidence:" + "5" * 32,
                 "baseline_prediction_evidence_id":"evidence:" + "6" * 32}
    path = tmp_path / "final_mentions.jsonl"
    raw = b"".join((json.dumps(p, sort_keys=True) + "\n").encode() for p in [payload, duplicate])
    path.write_bytes(raw)
    selected, count = _collect_predictions(
        path, [row], expected_hash=hashlib.sha256(raw).hexdigest(),
        expected_count=2, expected_build="build")
    assert count == 2
    predictions = selected[(row.canonical_id, row.source_field)]
    assert len(predictions) == 2
    assert predictions[0].final_mention_id == predictions[1].final_mention_id
    scores, cases, _, _ = _metrics([row], selected, sensitivity=False)
    assert scores["balanced"]["typed_exact"]["tp"] == 1
    assert scores["balanced"]["typed_exact"]["fp"] == 1
    assert scores["balanced"]["typed_exact"]["fn"] == 0
    assert cases[0]["prediction_count"] == 2


def test_prediction_stream_rejects_conflicting_identity_for_same_id(tmp_path: Path):
    """A reused ID for a different span remains a fail-closed integrity error."""
    row = _field("ABCD XY")
    payload = {
        "schema_version":"scientific_entity_semantic_typer_h2_full_corpus_final_mention_v0.3",
        "build_id":"build", "candidate_evidence_id":"evidence:" + "1" * 32,
        "final_mention_id":"mention:" + "2" * 32,
        "canonical_id":row.canonical_id, "source_field":row.source_field,
        "source_text_sha256":row.source_text_sha256,
        "char_start":0, "char_end":4, "surface_text":"ABCD",
        "baseline_prediction_evidence_id":"evidence:" + "3" * 32,
        "baseline_entity_type":"model", "baseline_confidence_score":0.91,
        "h2_override_applied":False, "final_entity_type":"model",
        "materialization_fingerprint_sha256":"4" * 64,
    }
    conflict = {**payload, "char_start":5, "char_end":7, "surface_text":"XY",
                "candidate_evidence_id":"evidence:" + "5" * 32,
                "baseline_prediction_evidence_id":"evidence:" + "6" * 32}
    path = tmp_path / "final_mentions.jsonl"
    raw = b"".join((json.dumps(p, sort_keys=True) + "\n").encode() for p in [payload, conflict])
    path.write_bytes(raw)
    with pytest.raises(FullNerUnblindError, match="Conflicting identities"):
        _collect_predictions(path, [row], expected_hash=hashlib.sha256(raw).hexdigest(),
                             expected_count=2, expected_build="build")
