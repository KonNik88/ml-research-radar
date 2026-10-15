from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from radar_core.contracts.scientific_entity_semantic_typer_h2_full_corpus_candidate import H2FullCorpusManifest, H2FullCorpusSummary
from radar_core.contracts.scientific_entity_semantic_typer_h2_production_authorization import H2ProductionAuthorizationManifest, H2ProductionAuthorizationRecord
from radar_core.contracts.scientific_entity_semantic_typer_h2_production_audit_evaluation import (
    EVALUATION_ID,
    H2ProductionAuditEvaluationManifest,
    H2ProductionAuditEvaluationSummary,
    H2ProductionAuditGateResult,
    H2ProductionAuditGateResults,
    H2ProductionAuditStratumMetrics,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_production_audit_reference import H2ProductionAuditReferenceManifest, H2ProductionAuditReferenceSummary
from radar_core.contracts.scientific_entity_semantic_typer_h2_production_promotion_decision import (
    AUTHORIZATION_ID,
    CANDIDATE_BUILD_ID,
    CANDIDATE_FINGERPRINT,
    CANDIDATE_ID,
    CANONICAL_SHA256,
    DECISION_ID,
    MATERIALIZATION_FINGERPRINT,
    REFERENCE_ID,
    H2ProductionPromotionDecisionRecord,
    canonical_config_sha256,
    load_h2_production_promotion_decision_config,
)
from radar_core.entities import scientific_entity_semantic_typer_h2_production_promotion_decision as mod


def _jbytes(value) -> bytes:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _write_package(path: Path, files: dict[str, bytes]) -> dict[str, str]:
    path.mkdir(parents=True)
    for name, data in files.items():
        (path / name).write_bytes(data)
    checks = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    (path / "checksums.txt").write_text("".join(f"{checks[name]}  {name}\n" for name in sorted(checks)), encoding="utf-8", newline="\n")
    return checks


def _parents(tmp_path: Path) -> tuple[Path, Path, Path, Path, dict[str, str]]:
    auth = tmp_path / "authorization"
    candidate = tmp_path / "candidate"
    reference = tmp_path / "reference"
    evaluation = tmp_path / "evaluation"

    auth_record = H2ProductionAuthorizationRecord(
        authorization_id=AUTHORIZATION_ID,
        authorization_scope="one_timestamped_full_corpus_candidate_materialization",
        gate_config_sha256="a" * 64,
        acceptance_decision_id="acceptance",
        candidate_id=CANDIDATE_ID,
        candidate_fingerprint_sha256=CANDIDATE_FINGERPRINT,
        canonical_path="data/analytics/reconciled/canonical_documents.jsonl",
        canonical_sha256=CANONICAL_SHA256,
        canonical_document_count=61075,
    )
    auth_readme = b"auth\n"
    auth_files0 = {"README.md": auth_readme, "authorization.json": _jbytes(auth_record)}
    auth_manifest = H2ProductionAuthorizationManifest(
        authorization_id=AUTHORIZATION_ID,
        authorization_config_sha256="b" * 64,
        gate_config_sha256="a" * 64,
        acceptance_decision_id="acceptance",
        candidate_id=CANDIDATE_ID,
        candidate_fingerprint_sha256=CANDIDATE_FINGERPRINT,
        canonical_path="data/analytics/reconciled/canonical_documents.jsonl",
        canonical_sha256=CANONICAL_SHA256,
        canonical_document_count=61075,
        files={name: hashlib.sha256(data).hexdigest() for name, data in auth_files0.items()},
        next_slice="validate_immutable_h2_production_authorization_record",
    )
    auth_checks = _write_package(auth, {**auth_files0, "manifest.json": _jbytes(auth_manifest)})

    dummy = {
        "README.md": b"candidate\n",
        "baseline_mentions.jsonl": b"baseline\n",
        "final_mentions.jsonl": b"final\n",
        "h2_overrides.jsonl": b"override\n",
        "semantic_typer_cases.jsonl": b"cases\n",
        "semantic_typer_predictions.jsonl": b"preds\n",
        "upstream_raw_mentions.jsonl": b"raw\n",
    }
    summary = H2FullCorpusSummary(
        build_id=CANDIDATE_BUILD_ID, input_document_count=61075, upstream_raw_mention_count=1396180,
        baseline_prediction_count=846264, baseline_method_count=260200, semantic_typer_case_count=260200,
        semantic_typer_scored_count=253481, semantic_typer_fallback_count=6719, typer_coverage_over_method_cases=0.974178,
        h2_override_count=33469, final_mention_count=846264,
        baseline_count_by_type={"dataset":70704,"domain":54673,"method":260200,"metric":70651,"model":248526,"task":141510},
        final_count_by_type={"dataset":70704,"domain":54673,"method":226731,"metric":70651,"model":281995,"task":141510},
        source_field_counts={"abstract":748660,"title":97604},
    )
    dummy["summary.json"] = _jbytes(summary)
    candidate_file_hashes = {name: hashlib.sha256(data).hexdigest() for name, data in dummy.items()}
    candidate_manifest = H2FullCorpusManifest(
        build_id=CANDIDATE_BUILD_ID, authorization_id=AUTHORIZATION_ID, candidate_id=CANDIDATE_ID,
        candidate_fingerprint_sha256=CANDIDATE_FINGERPRINT, materialization_config_sha256="c"*64,
        materialization_fingerprint_sha256=MATERIALIZATION_FINGERPRINT,
        canonical_path="data/analytics/reconciled/canonical_documents.jsonl", canonical_sha256=CANONICAL_SHA256,
        canonical_document_count=61075, upstream_runtime_config_sha256="d"*64, baseline_policy_config_sha256="e"*64,
        semantic_typer_config_sha256="f"*64, semantic_typer_fingerprint_sha256="1"*64, h2_threshold=0.1,
        upstream_raw_mention_count=1396180, baseline_prediction_count=846264, semantic_typer_case_count=260200,
        semantic_typer_scored_count=253481, semantic_typer_fallback_count=6719, h2_override_count=33469,
        final_mention_count=846264, files=candidate_file_hashes, exact_authorized_canonical_snapshot_verified=True,
        authorization_validated_before_model_load=True, reference_labels_used=False, threshold_tuning_executed=False,
        policy_revision_executed=False, span_mutated=False, canonical_truth_mutated=False,
        production_latest_promotion_authorized=False, latest_overwrite_allowed=False, publication_ready=False,
        candidate_validation_required_before_promotion=True, next_slice="validate_h2_full_corpus_candidate_materialization",
    )
    candidate_checks = _write_package(candidate, {**dummy, "manifest.json": _jbytes(candidate_manifest)})

    ref_annotations = b"{}\n"
    ref_summary = H2ProductionAuditReferenceSummary(
        reference_id=REFERENCE_ID, audit_id="scientific-entity-semantic-typer-h2-production-audit-v0.3-20261003T121605823276Z",
        annotation_row_count=240, completed_annotation_row_count=240,
        span_status_count={"valid_entity_span":216,"boundary_issue":11,"not_an_entity":13},
        reference_type_count={"dataset":5,"domain":9,"method":122,"model":80,"null":13,"task":11},
        confidence_count={"high":204,"medium":35,"low":1}, reviewer_note_nonempty_count=57,
        uncertain_count=0, not_an_entity_count=13, boundary_issue_count=11, valid_entity_span_count=216,
        uncertain_rate=0.0, not_an_entity_rate=13/240, boundary_issue_rate=11/240,
        promotion_gates_evaluated=False, sampled_strata_reconstructed=False, candidate_prediction_files_read=False,
    )
    ref_files0={"README.md":b"ref\n","annotation_summary.json":_jbytes(ref_summary),"reference_annotations.jsonl":ref_annotations}
    ref_manifest=H2ProductionAuditReferenceManifest(
        reference_id=REFERENCE_ID, audit_id="scientific-entity-semantic-typer-h2-production-audit-v0.3-20261003T121605823276Z",
        candidate_build_id=CANDIDATE_BUILD_ID,candidate_id=CANDIDATE_ID,candidate_fingerprint_sha256=CANDIDATE_FINGERPRINT,
        materialization_fingerprint_sha256=MATERIALIZATION_FINGERPRINT,canonical_sha256=CANONICAL_SHA256,canonical_document_count=61075,
        audit_config_file_sha256="0afad2d06452c22320fdc75775ad50ba02dee1a63910f2d76af0134ace1dbdfe",audit_config_canonical_sha256="c1f0f786c44149a3c5decbe96d96baf3ce778be3798929fe6064b05accfe9de9",audit_sample_manifest_sha256="4"*64,
        audit_cases_sha256="5"*64,blank_annotations_sha256="6"*64,completed_annotations_source_sha256=hashlib.sha256(ref_annotations).hexdigest(),
        reference_annotations_sha256=hashlib.sha256(ref_annotations).hexdigest(),annotation_summary_sha256=hashlib.sha256(ref_files0["annotation_summary.json"]).hexdigest(),
        annotator_ids=["human-reviewer-1"],annotation_row_count=240,completed_annotation_row_count=240,prediction_blind=True,reference_frozen=True,
        candidate_prediction_files_read=False,sampled_strata_reconstructed=False,unblinding_executed=False,promotion_gates_evaluated=False,
        model_inference_executed=False,threshold_tuning_executed=False,policy_revision_executed=False,candidate_mutated=False,
        canonical_truth_mutated=False,production_latest_promotion_authorized=False,latest_overwritten=False,publication_ready=False,
        next_slice="unblind_and_evaluate_h2_production_audit_promotion_gate",
    )
    ref_checks=_write_package(reference,{**ref_files0,"manifest.json":_jbytes(ref_manifest)})

    strata=[
        H2ProductionAuditStratumMetrics(stratum="override",total_count=100,usable_count=95,valid_entity_span_count=92,boundary_issue_count=3,not_an_entity_count=5,uncertain_count=0,reference_type_count={"dataset":4,"domain":1,"method":28,"metric":0,"model":62,"task":0},reference_model_rate=62/95,reference_method_rate=28/95,model_minus_method_rate=34/95,unresolved_or_not_entity_rate=.05,baseline_correct_count=28,final_correct_count=62,corrected_by_h2_count=62,regressed_by_h2_count=28),
        H2ProductionAuditStratumMetrics(stratum="preserved_method",total_count=100,usable_count=93,valid_entity_span_count=89,boundary_issue_count=4,not_an_entity_count=7,uncertain_count=0,reference_type_count={"dataset":1,"domain":8,"method":64,"metric":0,"model":13,"task":7},reference_model_rate=13/93,reference_method_rate=64/93,model_minus_method_rate=-51/93,unresolved_or_not_entity_rate=.07,baseline_correct_count=64,final_correct_count=64,corrected_by_h2_count=0,regressed_by_h2_count=0),
        H2ProductionAuditStratumMetrics(stratum="fallback_method",total_count=40,usable_count=39,valid_entity_span_count=35,boundary_issue_count=4,not_an_entity_count=1,uncertain_count=0,reference_type_count={"dataset":0,"domain":0,"method":30,"metric":0,"model":5,"task":4},reference_model_rate=5/39,reference_method_rate=30/39,model_minus_method_rate=-25/39,unresolved_or_not_entity_rate=.025,baseline_correct_count=30,final_correct_count=30,corrected_by_h2_count=0,regressed_by_h2_count=0),
    ]
    eval_summary=H2ProductionAuditEvaluationSummary(
        evaluation_id=EVALUATION_ID,audit_id="scientific-entity-semantic-typer-h2-production-audit-v0.3-20261003T121605823276Z",reference_id=REFERENCE_ID,
        audit_case_count=240,usable_count=227,uncertain_count=0,not_an_entity_count=13,boundary_issue_count=11,uncertain_rate=0,not_an_entity_rate=13/240,boundary_issue_rate=11/240,
        strata=strata,all_hard_gates_pass=True,gate_verdict="pass_h2_production_audit_gate",candidate_prediction_files_read=True,sampled_strata_reconstructed=True,unblinding_executed=True,promotion_gates_evaluated=True,
        model_inference_executed=False,threshold_tuning_executed=False,policy_revision_executed=False,candidate_mutated=False,canonical_truth_mutated=False,promotion_decision_made=False,production_latest_promotion_authorized=False,
    )
    gate_defs=[("g"+str(i),">=",0.0,1.0) for i in range(11)]
    gates=H2ProductionAuditGateResults(evaluation_id=EVALUATION_ID,gate_count=11,gates=[H2ProductionAuditGateResult(gate_name=n,comparator=c,threshold=t,observed_value=o,passed=True) for n,c,t,o in gate_defs],all_hard_gates_pass=True,gate_verdict="pass_h2_production_audit_gate",thresholds_revised_after_annotation=False,promotion_decision_made=False,production_latest_promotion_authorized=False)
    case_bytes=b"{}\n"
    eval_files0={"README.md":b"eval\n","case_evaluations.jsonl":case_bytes,"gate_results.json":_jbytes(gates),"summary.json":_jbytes(eval_summary)}
    eval_manifest=H2ProductionAuditEvaluationManifest(
        evaluation_id=EVALUATION_ID,audit_id="scientific-entity-semantic-typer-h2-production-audit-v0.3-20261003T121605823276Z",reference_id=REFERENCE_ID,candidate_build_id=CANDIDATE_BUILD_ID,candidate_id=CANDIDATE_ID,
        candidate_fingerprint_sha256=CANDIDATE_FINGERPRINT,materialization_fingerprint_sha256=MATERIALIZATION_FINGERPRINT,canonical_sha256=CANONICAL_SHA256,canonical_document_count=61075,
        evaluation_config_sha256="7"*64,audit_config_canonical_sha256="c1f0f786c44149a3c5decbe96d96baf3ce778be3798929fe6064b05accfe9de9",reference_freeze_config_canonical_sha256="82f058248696f6cd9828b81e33e20f9538d0521ac76e6c8bf84335aefaed626e",
        audit_sample_manifest_sha256="8"*64,reference_manifest_sha256=ref_checks["manifest.json"],candidate_manifest_sha256=candidate_checks["manifest.json"],candidate_final_mentions_sha256=candidate_checks["final_mentions.jsonl"],
        files={name:hashlib.sha256(data).hexdigest() for name,data in eval_files0.items()},audit_case_count=240,override_count=100,preserved_method_count=100,fallback_method_count=40,
        frozen_reference_verified_before_unblinding=True,deterministic_sample_reconstructed_exactly=True,candidate_prediction_files_read=True,sampled_strata_reconstructed=True,unblinding_executed=True,promotion_gates_evaluated=True,
        model_inference_executed=False,threshold_tuning_executed=False,policy_revision_executed=False,candidate_mutated=False,canonical_truth_mutated=False,promotion_decision_made=False,production_latest_promotion_authorized=False,latest_overwritten=False,publication_ready=False,next_slice="validate_h2_production_audit_evaluation",
    )
    eval_checks=_write_package(evaluation,{**eval_files0,"manifest.json":_jbytes(eval_manifest)})
    hashes={
        "authorization_manifest_sha256":auth_checks["manifest.json"],"authorization_record_sha256":auth_checks["authorization.json"],
        "candidate_manifest_sha256":candidate_checks["manifest.json"],"candidate_summary_sha256":candidate_checks["summary.json"],"candidate_final_mentions_sha256":candidate_checks["final_mentions.jsonl"],
        "reference_manifest_sha256":ref_checks["manifest.json"],"reference_summary_sha256":ref_checks["annotation_summary.json"],"reference_annotations_sha256":ref_checks["reference_annotations.jsonl"],
        "evaluation_manifest_sha256":eval_checks["manifest.json"],"evaluation_summary_sha256":eval_checks["summary.json"],"evaluation_gate_results_sha256":eval_checks["gate_results.json"],"evaluation_case_evaluations_sha256":eval_checks["case_evaluations.jsonl"],
    }
    return auth,candidate,reference,evaluation,hashes


def _config(tmp_path: Path, hashes: dict[str,str]) -> Path:
    payload=yaml.safe_load(mod.DEFAULT_CONFIG.read_text(encoding="utf-8"))
    payload["lineage"].update(hashes)
    path=tmp_path/"decision.yaml"
    path.write_text(yaml.safe_dump(payload,sort_keys=False),encoding="utf-8",newline="\n")
    return path


def test_config_is_decision_only() -> None:
    config=load_h2_production_promotion_decision_config(mod.DEFAULT_CONFIG)
    assert config.promotion_boundary.authorized_promotion_count == 1
    assert config.promotion_boundary.promotion_execution_allowed_in_this_slice is False
    assert config.safety.candidate_prediction_files_read_in_this_slice is False
    assert len(canonical_config_sha256(config)) == 64


def test_plan_verifies_lineage_but_does_not_authorize(tmp_path: Path) -> None:
    a,c,r,e,h=_parents(tmp_path); cfg=_config(tmp_path,h)
    result=mod.plan_or_execute_h2_production_promotion_decision(project_root=tmp_path,config_path=cfg,authorization_dir=a,candidate_dir=c,reference_dir=r,evaluation_dir=e,output_root=tmp_path/"out",execute=False)
    assert result["parent_lineage_verified"] is True
    assert result["all_hard_gates_pass"] is True
    assert result["promotion_decision_made"] is False
    assert result["production_latest_promotion_authorized"] is False
    assert result["plan_writes_output"] is False
    assert not Path(result["output_dir"]).exists()


def test_execute_writes_authorization_without_promotion(tmp_path: Path) -> None:
    a,c,r,e,h=_parents(tmp_path); cfg=_config(tmp_path,h)
    result=mod.plan_or_execute_h2_production_promotion_decision(project_root=tmp_path,config_path=cfg,authorization_dir=a,candidate_dir=c,reference_dir=r,evaluation_dir=e,output_root=tmp_path/"out",execute=True)
    decision=H2ProductionPromotionDecisionRecord.model_validate(json.loads((Path(result["output_dir"])/"decision.json").read_text()))
    assert decision.production_latest_promotion_authorized is True
    assert decision.promotion_executed is False
    assert decision.latest_overwritten is False
    assert decision.candidate_prediction_files_read_in_this_slice is False


def test_execute_refuses_overwrite(tmp_path: Path) -> None:
    a,c,r,e,h=_parents(tmp_path); cfg=_config(tmp_path,h)
    kwargs=dict(project_root=tmp_path,config_path=cfg,authorization_dir=a,candidate_dir=c,reference_dir=r,evaluation_dir=e,output_root=tmp_path/"out",execute=True)
    mod.plan_or_execute_h2_production_promotion_decision(**kwargs)
    with pytest.raises(FileExistsError):
        mod.plan_or_execute_h2_production_promotion_decision(**kwargs)


def test_preflight_rejects_failed_gate(tmp_path: Path) -> None:
    a,c,r,e,h=_parents(tmp_path)
    gates=json.loads((e/"gate_results.json").read_text())
    gates["gates"][0]["observed_value"]=-1.0
    gates["gates"][0]["passed"]=False
    gates["all_hard_gates_pass"]=False
    gates["gate_verdict"]="fail_h2_production_audit_gate"
    (e/"gate_results.json").write_bytes(_jbytes(gates))
    # keep the package internally checksummed so failure is semantic, not checksum-only
    em=json.loads((e/"manifest.json").read_text())
    em["files"]["gate_results.json"]=hashlib.sha256((e/"gate_results.json").read_bytes()).hexdigest()
    (e/"manifest.json").write_bytes(_jbytes(em))
    files=[p.name for p in e.iterdir() if p.is_file() and p.name!="checksums.txt"]
    (e/"checksums.txt").write_text("".join(f"{hashlib.sha256((e/n).read_bytes()).hexdigest()}  {n}\n" for n in sorted(files)),encoding="utf-8",newline="\n")
    h.update({"evaluation_manifest_sha256":hashlib.sha256((e/"manifest.json").read_bytes()).hexdigest(),"evaluation_gate_results_sha256":hashlib.sha256((e/"gate_results.json").read_bytes()).hexdigest()})
    cfg=_config(tmp_path,h)
    with pytest.raises(mod.H2ProductionPromotionDecisionError, match="promotion gate did not pass"):
        mod.plan_or_execute_h2_production_promotion_decision(project_root=tmp_path,config_path=cfg,authorization_dir=a,candidate_dir=c,reference_dir=r,evaluation_dir=e,output_root=tmp_path/"out",execute=False)


def test_preflight_binds_exact_final_mentions_hash_without_reading_file(tmp_path: Path) -> None:
    a,c,r,e,h=_parents(tmp_path); cfg=_config(tmp_path,h)
    # File bytes can change here without being read by 8E; 8F must re-hash before mutation.
    (c/"final_mentions.jsonl").write_bytes(b"tampered-after-evaluation\n")
    result=mod.plan_or_execute_h2_production_promotion_decision(project_root=tmp_path,config_path=cfg,authorization_dir=a,candidate_dir=c,reference_dir=r,evaluation_dir=e,output_root=tmp_path/"out",execute=False)
    assert result["candidate_final_mentions_sha256"] == h["candidate_final_mentions_sha256"]
    assert result["candidate_prediction_files_read_in_this_slice"] is False


def test_strict_validator_accepts_fresh_decision(tmp_path: Path) -> None:
    a,c,r,e,h=_parents(tmp_path); cfg=_config(tmp_path,h)
    result=mod.plan_or_execute_h2_production_promotion_decision(project_root=tmp_path,config_path=cfg,authorization_dir=a,candidate_dir=c,reference_dir=r,evaluation_dir=e,output_root=tmp_path/"out",execute=True)
    checks,summary=mod.validate_h2_production_promotion_decision(project_root=tmp_path,config_path=cfg,authorization_dir=a,candidate_dir=c,reference_dir=r,evaluation_dir=e,decision_dir=Path(result["output_dir"]))
    assert all(ok for _,ok,_ in checks)
    assert summary["required_failed_count"] == 0
    assert summary["production_latest_promotion_authorized"] is True
    assert summary["promotion_executed"] is False


def test_validator_detects_decision_tampering(tmp_path: Path) -> None:
    a,c,r,e,h=_parents(tmp_path); cfg=_config(tmp_path,h)
    result=mod.plan_or_execute_h2_production_promotion_decision(project_root=tmp_path,config_path=cfg,authorization_dir=a,candidate_dir=c,reference_dir=r,evaluation_dir=e,output_root=tmp_path/"out",execute=True)
    path=Path(result["output_dir"])/"README.md"
    path.write_text(path.read_text()+"tamper\n",encoding="utf-8",newline="\n")
    checks,summary=mod.validate_h2_production_promotion_decision(project_root=tmp_path,config_path=cfg,authorization_dir=a,candidate_dir=c,reference_dir=r,evaluation_dir=e,decision_dir=Path(result["output_dir"]))
    assert summary["required_failed_count"] > 0
    assert any(name=="checksum:README.md" and not ok for name,ok,_ in checks)


def test_production_config_binds_supplied_parent_hashes() -> None:
    config=load_h2_production_promotion_decision_config(mod.DEFAULT_CONFIG)
    assert config.lineage.authorization_manifest_sha256 == "0288986406e84b7ec76fd4c006892710313d4e9e95cd911f0b656c43e34d024f"
    assert config.lineage.reference_manifest_sha256 == "1c262a675402216e530424484cc8c7a45777622838dd72fbbd8efd6d92502fa9"
    assert config.lineage.candidate_manifest_sha256 == "64d4a728ef24891673b6915bdd7e41c3e241078b6f02077337607ea9b1177f62"
    assert config.lineage.evaluation_manifest_sha256 == "16ad9dddc2d6524644322631c1b0f188254f5a78168d096ca670e1d094cbc302"
    assert config.lineage.candidate_final_mentions_sha256 == "518f3984d3dcd2aa5e2a84c96eec2fadce8b6dc6b49eef0d7a908533145394c1"
