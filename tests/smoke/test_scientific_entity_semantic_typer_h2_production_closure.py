from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from radar_core.contracts.scientific_entity_semantic_typer_h2_production_closure import (
    CANDIDATE_BUILD_ID, CANDIDATE_FINGERPRINT, CANDIDATE_ID, CANONICAL_SHA256, CLOSURE_ID,
    DECISION_ID, MATERIALIZATION_FINGERPRINT, PROMOTION_ID, load_h2_production_closure_config,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_production_promotion_decision import (
    AUTHORIZATION_ID, EVALUATION_ID, REFERENCE_ID,
    H2ProductionPromotionDecisionManifest, H2ProductionPromotionDecisionRecord,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_production_latest_promotion import (
    H2ProductionLatestPostValidation, H2ProductionLatestPromotionManifest,
    H2ProductionLatestPromotionRecord, PreviousLatestState, ScientificEntityProductionLatestPointer,
)
from radar_core.entities.scientific_entity_semantic_typer_h2_production_closure import (
    H2ProductionClosureError, plan_or_execute_h2_production_closure, validate_h2_production_closure,
)

PROD_CONFIG = Path(__file__).resolve().parents[2] / "configs" / "scientific_entity_semantic_typer_h2_production_closure_v0.3.yaml"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(value) -> bytes:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _write_package(directory: Path, payloads: dict[str, bytes]) -> str:
    directory.mkdir(parents=True)
    checks = {}
    for name, payload in payloads.items():
        (directory / name).write_bytes(payload)
        checks[name] = _sha(payload)
    ledger = "".join(f"{digest}  {name}\n" for name, digest in sorted(checks.items())).encode()
    (directory / "checksums.txt").write_bytes(ledger)
    return _sha(ledger)


def _fixture(tmp_path: Path):
    target = tmp_path / "candidate" / "final_mentions.jsonl"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"x\n" * 846264)
    target_sha = _sha(target.read_bytes())

    # Decision package.
    decision = H2ProductionPromotionDecisionRecord(
        decision_id=DECISION_ID, decision="authorize_controlled_h2_production_latest_promotion",
        authorization_id=AUTHORIZATION_ID, candidate_build_id=CANDIDATE_BUILD_ID,
        reference_id=REFERENCE_ID, evaluation_id=EVALUATION_ID, candidate_id=CANDIDATE_ID,
        candidate_fingerprint_sha256=CANDIDATE_FINGERPRINT,
        materialization_fingerprint_sha256=MATERIALIZATION_FINGERPRINT,
        canonical_sha256=CANONICAL_SHA256, canonical_document_count=61075,
        candidate_final_mentions_sha256=target_sha, evaluation_gate_count=11,
        evaluation_all_hard_gates_pass=True, evaluation_gate_verdict="pass_h2_production_audit_gate",
        thresholds_revised_after_annotation=False, promotion_decision_made=True,
        production_latest_promotion_authorized=True,
        authorization_scope="one_controlled_candidate_to_trusted_latest_promotion",
        authorized_promotion_count=1, exact_candidate_final_mentions_sha256_required_at_promotion=True,
        backup_previous_trusted_latest_required=True, rollback_path_required=True,
        post_promotion_validation_required=True, candidate_prediction_files_read_in_this_slice=False,
        model_inference_executed=False, threshold_tuning_executed=False, policy_revision_executed=False,
        candidate_mutated=False, canonical_truth_mutated=False, promotion_executed=False,
        latest_overwritten=False, publication_authorized=False,
        next_slice="build_controlled_h2_production_latest_promotion_tooling",
    )
    decision_b = _json(decision)
    readme_b = b"decision\n"
    decision_files = {"README.md": _sha(readme_b), "decision.json": _sha(decision_b)}
    decision_manifest = H2ProductionPromotionDecisionManifest(
        decision_id=DECISION_ID, decision_config_sha256="1"*64, authorization_id=AUTHORIZATION_ID,
        authorization_manifest_sha256="2"*64, authorization_record_sha256="3"*64,
        candidate_build_id=CANDIDATE_BUILD_ID, candidate_manifest_sha256="4"*64,
        candidate_summary_sha256="5"*64, candidate_final_mentions_sha256=target_sha,
        reference_id=REFERENCE_ID, reference_manifest_sha256="6"*64,
        reference_summary_sha256="7"*64, reference_annotations_sha256="8"*64,
        evaluation_id=EVALUATION_ID, evaluation_manifest_sha256="9"*64,
        evaluation_summary_sha256="a"*64, evaluation_gate_results_sha256="b"*64,
        evaluation_case_evaluations_sha256="c"*64, candidate_id=CANDIDATE_ID,
        candidate_fingerprint_sha256=CANDIDATE_FINGERPRINT,
        materialization_fingerprint_sha256=MATERIALIZATION_FINGERPRINT,
        canonical_sha256=CANONICAL_SHA256, canonical_document_count=61075,
        parent_lineage_verified=True, evaluation_gate_count=11, evaluation_all_hard_gates_pass=True,
        promotion_decision_made=True, production_latest_promotion_authorized=True,
        candidate_prediction_files_read_in_this_slice=False, model_inference_executed=False,
        threshold_tuning_executed=False, policy_revision_executed=False, candidate_mutated=False,
        canonical_truth_mutated=False, promotion_executed=False, latest_overwritten=False,
        publication_authorized=False, files=decision_files,
        next_slice="validate_immutable_h2_production_promotion_decision",
    )
    decision_dir = tmp_path / "decision"
    decision_manifest_b = _json(decision_manifest)
    decision_ledger_sha = _write_package(decision_dir, {"README.md": readme_b, "decision.json": decision_b, "manifest.json": decision_manifest_b})

    pointer = ScientificEntityProductionLatestPointer(
        promotion_id=PROMOTION_ID, decision_id=DECISION_ID, candidate_build_id=CANDIDATE_BUILD_ID,
        candidate_id=CANDIDATE_ID, candidate_fingerprint_sha256=CANDIDATE_FINGERPRINT,
        materialization_fingerprint_sha256=MATERIALIZATION_FINGERPRINT,
        candidate_final_mentions_sha256=target_sha, final_mention_count=846264, h2_override_count=33469,
        canonical_sha256=CANONICAL_SHA256, canonical_document_count=61075,
        artifact_path=str(target), promotion_record_path="promotion", artifact_is_immutable_candidate=True,
        artifact_retention_required=True, post_promotion_validation_required=True, publication_authorized=False,
    )
    pointer_b = _json(pointer)
    prev = PreviousLatestState(previous_latest_exists=False, rollback_action="remove_latest_pointer")
    post = H2ProductionLatestPostValidation(
        promotion_id=PROMOTION_ID, latest_pointer_exists=True, latest_pointer_matches_expected=True,
        target_artifact_exists=True, target_sha256_matches_authorized=True,
        target_line_count_matches_expected=True, target_sha256=target_sha, target_line_count=846264,
        post_promotion_validation_passed=True,
    )
    record = H2ProductionLatestPromotionRecord(
        promotion_id=PROMOTION_ID, decision_id=DECISION_ID, candidate_build_id=CANDIDATE_BUILD_ID,
        candidate_final_mentions_sha256=target_sha, final_mention_count=846264, h2_override_count=33469,
        canonical_sha256=CANONICAL_SHA256, canonical_document_count=61075,
        promotion_decision_validated=True, production_latest_promotion_authorized=True,
        previous_latest_exists=False, previous_latest_state_snapshotted=True, promotion_executed=True,
        trusted_latest_pointer_updated=True, post_promotion_validation_passed=True,
        exact_candidate_sha_verified_immediately_before_mutation=True, rollback_path_ready=True,
        rollback_command="rollback", candidate_mutated=False, canonical_truth_mutated=False,
        model_inference_executed=False, threshold_tuning_executed=False, policy_revision_executed=False,
        publication_authorized=False, next_slice="validate_h2_production_latest_promotion",
    )
    promo_readme = b"promotion\n"
    installed_b, post_b, prev_b, record_b = pointer_b, _json(post), _json(prev), _json(record)
    promo_files = {
        "README.md": _sha(promo_readme), "installed_latest.json": _sha(installed_b),
        "post_validation.json": _sha(post_b), "previous_latest_state.json": _sha(prev_b),
        "promotion.json": _sha(record_b),
    }
    promo_manifest = H2ProductionLatestPromotionManifest(
        promotion_id=PROMOTION_ID, promotion_config_sha256="d"*64, decision_id=DECISION_ID,
        candidate_build_id=CANDIDATE_BUILD_ID, candidate_final_mentions_sha256=target_sha,
        final_mention_count=846264, canonical_sha256=CANONICAL_SHA256, canonical_document_count=61075,
        latest_pointer_path=str(tmp_path / "trusted" / "latest.json"), latest_pointer_sha256=_sha(pointer_b),
        previous_latest_exists=False, previous_latest_state_sha256=_sha(prev_b), promotion_executed=True,
        trusted_latest_pointer_updated=True, post_promotion_validation_passed=True, rollback_path_ready=True,
        candidate_mutated=False, canonical_truth_mutated=False, publication_authorized=False,
        files=promo_files, next_slice="validate_h2_production_latest_promotion",
    )
    promotion_dir = tmp_path / "promotion"
    promo_manifest_b = _json(promo_manifest)
    promo_ledger_sha = _write_package(promotion_dir, {
        "README.md": promo_readme, "installed_latest.json": installed_b, "manifest.json": promo_manifest_b,
        "post_validation.json": post_b, "previous_latest_state.json": prev_b, "promotion.json": record_b,
    })
    latest = tmp_path / "trusted" / "latest.json"
    latest.parent.mkdir(parents=True)
    latest.write_bytes(pointer_b)

    cfg = yaml.safe_load(PROD_CONFIG.read_text())
    cfg["lineage"].update({
        "decision_sha256": _sha(decision_b), "decision_manifest_sha256": _sha(decision_manifest_b),
        "decision_checksums_sha256": decision_ledger_sha,
        "promotion_record_sha256": _sha(record_b), "promotion_manifest_sha256": _sha(promo_manifest_b),
        "promotion_post_validation_sha256": _sha(post_b), "promotion_checksums_sha256": promo_ledger_sha,
        "trusted_latest_pointer_sha256": _sha(pointer_b), "candidate_final_mentions_sha256": target_sha,
    })
    config = tmp_path / "closure.yaml"
    config.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    return config, decision_dir, promotion_dir, latest, tmp_path / "closures", target


def test_production_config_loads() -> None:
    cfg = load_h2_production_closure_config(PROD_CONFIG)
    assert cfg.execution.closure_id == CLOSURE_ID
    assert cfg.closure_policy.h2_v03_lifecycle_closed is True


def test_plan_is_read_only_and_revalidates_target(tmp_path: Path) -> None:
    config, decision, promotion, latest, output, _ = _fixture(tmp_path)
    report = plan_or_execute_h2_production_closure(
        project_root=tmp_path, config_path=config, decision_dir=decision, promotion_dir=promotion,
        trusted_latest_path=latest, output_root=output, execute=False,
    )
    assert report["trusted_target_revalidated_at_closure"] is True
    assert report["h2_v03_lifecycle_closed"] is False
    assert report["plan_writes_output"] is False
    assert not output.exists()


def test_execute_and_strict_validation(tmp_path: Path) -> None:
    config, decision, promotion, latest, output, _ = _fixture(tmp_path)
    report = plan_or_execute_h2_production_closure(
        project_root=tmp_path, config_path=config, decision_dir=decision, promotion_dir=promotion,
        trusted_latest_path=latest, output_root=output, execute=True,
    )
    assert report["h2_v03_lifecycle_closed"] is True
    closure = output / CLOSURE_ID
    checks, summary = validate_h2_production_closure(
        project_root=tmp_path, config_path=config, decision_dir=decision, promotion_dir=promotion,
        trusted_latest_path=latest, closure_dir=closure,
    )
    assert all(ok for _, ok, _ in checks)
    assert summary["required_failed_count"] == 0
    assert summary["h2_v03_lifecycle_closed"] is True


def test_execute_is_one_shot(tmp_path: Path) -> None:
    config, decision, promotion, latest, output, _ = _fixture(tmp_path)
    kwargs = dict(project_root=tmp_path, config_path=config, decision_dir=decision, promotion_dir=promotion,
                  trusted_latest_path=latest, output_root=output, execute=True)
    plan_or_execute_h2_production_closure(**kwargs)
    with pytest.raises(H2ProductionClosureError, match="already exists"):
        plan_or_execute_h2_production_closure(**kwargs)


def test_trusted_target_drift_fails_closed(tmp_path: Path) -> None:
    config, decision, promotion, latest, output, target = _fixture(tmp_path)
    target.write_bytes(b"drift\n")
    with pytest.raises(H2ProductionClosureError, match="SHA-256"):
        plan_or_execute_h2_production_closure(
            project_root=tmp_path, config_path=config, decision_dir=decision, promotion_dir=promotion,
            trusted_latest_path=latest, output_root=output, execute=False,
        )
    assert not output.exists()


def test_latest_pointer_drift_fails_closed(tmp_path: Path) -> None:
    config, decision, promotion, latest, output, _ = _fixture(tmp_path)
    latest.write_bytes(b'{"drift":true}\n')
    with pytest.raises(H2ProductionClosureError, match="pointer SHA"):
        plan_or_execute_h2_production_closure(
            project_root=tmp_path, config_path=config, decision_dir=decision, promotion_dir=promotion,
            trusted_latest_path=latest, output_root=output, execute=False,
        )


def test_decision_drift_fails_closed(tmp_path: Path) -> None:
    config, decision, promotion, latest, output, _ = _fixture(tmp_path)
    (decision / "decision.json").write_bytes(b"{}\n")
    with pytest.raises(H2ProductionClosureError, match="checksum mismatch"):
        plan_or_execute_h2_production_closure(
            project_root=tmp_path, config_path=config, decision_dir=decision, promotion_dir=promotion,
            trusted_latest_path=latest, output_root=output, execute=False,
        )


def test_closure_policy_forbids_reusing_old_audit_for_tuning() -> None:
    cfg = load_h2_production_closure_config(PROD_CONFIG)
    assert cfg.closure_policy.historical_production_audit_reference_reuse_for_tuning_allowed is False
    assert cfg.closure_policy.future_full_ner_coverage_audit_requires_fresh_prediction_blind_sample is True
