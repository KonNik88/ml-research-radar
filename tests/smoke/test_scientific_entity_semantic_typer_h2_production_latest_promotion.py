from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from radar_core.contracts.scientific_entity_semantic_typer_h2_production_promotion_decision import (
    AUTHORIZATION_ID,
    EVALUATION_ID,
    REFERENCE_ID,
    H2ProductionPromotionDecisionManifest,
    H2ProductionPromotionDecisionRecord,
    canonical_config_sha256 as decision_config_sha256,
    load_h2_production_promotion_decision_config,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_production_latest_promotion import (
    CANDIDATE_BUILD_ID,
    CANDIDATE_FINGERPRINT,
    CANDIDATE_ID,
    CANONICAL_SHA256,
    DECISION_ID,
    MATERIALIZATION_FINGERPRINT,
    PROMOTION_ID,
    H2ProductionLatestPromotionError,
    PreviousLatestState,
    load_h2_production_latest_promotion_config,
)
from radar_core.entities.scientific_entity_semantic_typer_h2_production_latest_promotion import (
    plan_or_execute_h2_production_latest_promotion,
    plan_or_execute_h2_production_latest_rollback,
    validate_h2_production_latest_promotion,
)

ROOT = Path(__file__).resolve().parents[2]
PROD_CONFIG = ROOT / "configs" / "scientific_entity_semantic_typer_h2_production_latest_promotion_v0.3.yaml"
DECISION_CONFIG = ROOT / "configs" / "scientific_entity_semantic_typer_h2_production_promotion_decision_v0.3.yaml"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(obj) -> bytes:
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump(mode="json")
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _make_config(tmp_path: Path, final_sha: str, line_count: int = 3, overrides: int = 1) -> Path:
    cfg = load_h2_production_latest_promotion_config(PROD_CONFIG)
    payload = cfg.model_dump(mode="json")
    payload["lineage"]["candidate_final_mentions_sha256"] = final_sha
    payload["lineage"]["final_mention_count"] = line_count
    payload["lineage"]["h2_override_count"] = overrides
    path = tmp_path / "promotion.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8", newline="\n")
    return path


def _make_candidate(tmp_path: Path) -> tuple[Path, str]:
    d = tmp_path / "candidate"
    d.mkdir()
    final = b'{"x":1}\n{"x":2}\n{"x":3}\n'
    final_sha = _sha(final)
    (d / "final_mentions.jsonl").write_bytes(final)
    readme = b"candidate\n"
    (d / "README.md").write_bytes(readme)
    summary = {
        "build_id": CANDIDATE_BUILD_ID,
        "final_mention_count": 3,
        "h2_override_count": 1,
    }
    summary_b = _json_bytes(summary)
    (d / "summary.json").write_bytes(summary_b)
    manifest = {
        "build_id": CANDIDATE_BUILD_ID,
        "candidate_id": CANDIDATE_ID,
        "candidate_fingerprint_sha256": CANDIDATE_FINGERPRINT,
        "materialization_fingerprint_sha256": MATERIALIZATION_FINGERPRINT,
        "canonical_sha256": CANONICAL_SHA256,
        "canonical_document_count": 61075,
        "files": {"final_mentions.jsonl": final_sha},
        "reference_labels_used": False,
        "threshold_tuning_executed": False,
        "policy_revision_executed": False,
        "span_mutated": False,
        "canonical_truth_mutated": False,
        "production_latest_promotion_authorized": False,
        "latest_overwrite_allowed": False,
        "publication_ready": False,
    }
    manifest_b = _json_bytes(manifest)
    (d / "manifest.json").write_bytes(manifest_b)
    checksums = {
        "README.md": _sha(readme),
        "final_mentions.jsonl": final_sha,
        "manifest.json": _sha(manifest_b),
        "summary.json": _sha(summary_b),
    }
    (d / "checksums.txt").write_text("".join(f"{v}  {k}\n" for k, v in sorted(checksums.items())), encoding="utf-8", newline="\n")
    return d, final_sha


def _make_decision(tmp_path: Path, final_sha: str, *, authorized: bool = True) -> Path:
    d = tmp_path / "decision"
    d.mkdir()
    decision_cfg_sha = decision_config_sha256(load_h2_production_promotion_decision_config(DECISION_CONFIG))
    decision = H2ProductionPromotionDecisionRecord(
        decision_id=DECISION_ID,
        decision="authorize_controlled_h2_production_latest_promotion",
        authorization_id=AUTHORIZATION_ID,
        candidate_build_id=CANDIDATE_BUILD_ID,
        reference_id=REFERENCE_ID,
        evaluation_id=EVALUATION_ID,
        candidate_id=CANDIDATE_ID,
        candidate_fingerprint_sha256=CANDIDATE_FINGERPRINT,
        materialization_fingerprint_sha256=MATERIALIZATION_FINGERPRINT,
        canonical_sha256=CANONICAL_SHA256,
        canonical_document_count=61075,
        candidate_final_mentions_sha256=final_sha,
        evaluation_gate_count=11,
        evaluation_all_hard_gates_pass=True,
        evaluation_gate_verdict="pass_h2_production_audit_gate",
        thresholds_revised_after_annotation=False,
        promotion_decision_made=True,
        production_latest_promotion_authorized=True,
        authorization_scope="one_controlled_candidate_to_trusted_latest_promotion",
        authorized_promotion_count=1,
        exact_candidate_final_mentions_sha256_required_at_promotion=True,
        backup_previous_trusted_latest_required=True,
        rollback_path_required=True,
        post_promotion_validation_required=True,
        candidate_prediction_files_read_in_this_slice=False,
        model_inference_executed=False,
        threshold_tuning_executed=False,
        policy_revision_executed=False,
        candidate_mutated=False,
        canonical_truth_mutated=False,
        promotion_executed=False,
        latest_overwritten=False,
        publication_authorized=False,
        next_slice="build_controlled_h2_production_latest_promotion_tooling",
    )
    if not authorized:
        raw = decision.model_dump(mode="json")
        raw["production_latest_promotion_authorized"] = False
        decision_b = _json_bytes(raw)
    else:
        decision_b = _json_bytes(decision)
    readme = b"decision\n"
    files = {"README.md": _sha(readme), "decision.json": _sha(decision_b)}
    manifest = H2ProductionPromotionDecisionManifest(
        decision_id=DECISION_ID,
        decision_config_sha256=decision_cfg_sha,
        authorization_id=AUTHORIZATION_ID,
        authorization_manifest_sha256="1" * 64,
        authorization_record_sha256="2" * 64,
        candidate_build_id=CANDIDATE_BUILD_ID,
        candidate_manifest_sha256="3" * 64,
        candidate_summary_sha256="4" * 64,
        candidate_final_mentions_sha256=final_sha,
        reference_id=REFERENCE_ID,
        reference_manifest_sha256="5" * 64,
        reference_summary_sha256="6" * 64,
        reference_annotations_sha256="7" * 64,
        evaluation_id=EVALUATION_ID,
        evaluation_manifest_sha256="8" * 64,
        evaluation_summary_sha256="9" * 64,
        evaluation_gate_results_sha256="a" * 64,
        evaluation_case_evaluations_sha256="b" * 64,
        candidate_id=CANDIDATE_ID,
        candidate_fingerprint_sha256=CANDIDATE_FINGERPRINT,
        materialization_fingerprint_sha256=MATERIALIZATION_FINGERPRINT,
        canonical_sha256=CANONICAL_SHA256,
        canonical_document_count=61075,
        parent_lineage_verified=True,
        evaluation_gate_count=11,
        evaluation_all_hard_gates_pass=True,
        promotion_decision_made=True,
        production_latest_promotion_authorized=True,
        candidate_prediction_files_read_in_this_slice=False,
        model_inference_executed=False,
        threshold_tuning_executed=False,
        policy_revision_executed=False,
        candidate_mutated=False,
        canonical_truth_mutated=False,
        promotion_executed=False,
        latest_overwritten=False,
        publication_authorized=False,
        files=files,
        next_slice="validate_immutable_h2_production_promotion_decision",
    )
    manifest_b = _json_bytes(manifest)
    (d / "README.md").write_bytes(readme)
    (d / "decision.json").write_bytes(decision_b)
    (d / "manifest.json").write_bytes(manifest_b)
    checks = {**files, "manifest.json": _sha(manifest_b)}
    (d / "checksums.txt").write_text("".join(f"{v}  {k}\n" for k, v in sorted(checks.items())), encoding="utf-8", newline="\n")
    return d


def _fixture(tmp_path: Path):
    candidate, sha = _make_candidate(tmp_path)
    config = _make_config(tmp_path, sha)
    decision = _make_decision(tmp_path, sha)
    trusted = tmp_path / "trusted"
    promotion_root = tmp_path / "promotions"
    return config, decision, candidate, trusted, promotion_root


def test_production_config_loads() -> None:
    cfg = load_h2_production_latest_promotion_config(PROD_CONFIG)
    assert cfg.execution.promotion_id == PROMOTION_ID
    assert cfg.trusted_latest.pointer_name == "latest.json"


def test_plan_is_non_mutating_first_promotion(tmp_path: Path) -> None:
    config, decision, candidate, trusted, promotion_root = _fixture(tmp_path)
    report = plan_or_execute_h2_production_latest_promotion(
        project_root=tmp_path, config_path=config, decision_config_path=DECISION_CONFIG,
        decision_dir=decision, candidate_dir=candidate, trusted_root=trusted,
        promotion_root=promotion_root, execute=False,
    )
    assert report["first_trusted_latest_bootstrap"] is True
    assert report["exact_candidate_sha_verified_in_plan"] is True
    assert report["plan_writes_output"] is False
    assert not trusted.exists()
    assert not promotion_root.exists()


def test_execute_and_strict_validation(tmp_path: Path) -> None:
    config, decision, candidate, trusted, promotion_root = _fixture(tmp_path)
    report = plan_or_execute_h2_production_latest_promotion(
        project_root=tmp_path, config_path=config, decision_config_path=DECISION_CONFIG,
        decision_dir=decision, candidate_dir=candidate, trusted_root=trusted,
        promotion_root=promotion_root, execute=True,
    )
    assert report["promotion_executed"] is True
    assert (trusted / "latest.json").is_file()
    promotion_dir = promotion_root / PROMOTION_ID
    checks, summary = validate_h2_production_latest_promotion(
        project_root=tmp_path, config_path=config, decision_config_path=DECISION_CONFIG,
        decision_dir=decision, candidate_dir=candidate, trusted_root=trusted,
        promotion_dir=promotion_dir,
    )
    assert all(ok for _, ok, _ in checks)
    assert summary["required_failed_count"] == 0
    assert summary["production_latest_active"] is True


def test_execute_is_one_shot(tmp_path: Path) -> None:
    config, decision, candidate, trusted, promotion_root = _fixture(tmp_path)
    kwargs = dict(project_root=tmp_path, config_path=config, decision_config_path=DECISION_CONFIG,
                  decision_dir=decision, candidate_dir=candidate, trusted_root=trusted,
                  promotion_root=promotion_root, execute=True)
    plan_or_execute_h2_production_latest_promotion(**kwargs)
    with pytest.raises(H2ProductionLatestPromotionError, match="already exists"):
        plan_or_execute_h2_production_latest_promotion(**kwargs)


def test_candidate_byte_drift_fails_closed(tmp_path: Path) -> None:
    config, decision, candidate, trusted, promotion_root = _fixture(tmp_path)
    (candidate / "final_mentions.jsonl").write_bytes(b"drift\n")
    with pytest.raises(H2ProductionLatestPromotionError, match="SHA-256"):
        plan_or_execute_h2_production_latest_promotion(
            project_root=tmp_path, config_path=config, decision_config_path=DECISION_CONFIG,
            decision_dir=decision, candidate_dir=candidate, trusted_root=trusted,
            promotion_root=promotion_root, execute=False,
        )
    assert not trusted.exists()


def test_unauthorized_decision_fails_closed(tmp_path: Path) -> None:
    candidate, sha = _make_candidate(tmp_path)
    config = _make_config(tmp_path, sha)
    decision = _make_decision(tmp_path, sha, authorized=False)
    with pytest.raises(Exception):
        plan_or_execute_h2_production_latest_promotion(
            project_root=tmp_path, config_path=config, decision_config_path=DECISION_CONFIG,
            decision_dir=decision, candidate_dir=candidate, trusted_root=tmp_path / "trusted",
            promotion_root=tmp_path / "promotions", execute=False,
        )


def test_previous_state_existing_bytes_are_self_validating() -> None:
    raw = b'{"old":true}\n'
    state = PreviousLatestState(
        previous_latest_exists=True,
        previous_latest_sha256=_sha(raw),
        previous_latest_bytes_base64=__import__("base64").b64encode(raw).decode("ascii"),
        rollback_action="restore_previous_latest_pointer",
    )
    assert state.previous_latest_exists is True


def test_rollback_plan_and_execute_restore_absent_bootstrap_state(tmp_path: Path) -> None:
    config, decision, candidate, trusted, promotion_root = _fixture(tmp_path)
    plan_or_execute_h2_production_latest_promotion(
        project_root=tmp_path, config_path=config, decision_config_path=DECISION_CONFIG,
        decision_dir=decision, candidate_dir=candidate, trusted_root=trusted,
        promotion_root=promotion_root, execute=True,
    )
    promotion_dir = promotion_root / PROMOTION_ID
    rollback_root = tmp_path / "rollbacks"
    plan = plan_or_execute_h2_production_latest_rollback(
        project_root=tmp_path, config_path=config, promotion_dir=promotion_dir,
        trusted_root=trusted, rollback_root=rollback_root, execute=False,
    )
    assert plan["rollback_action"] == "remove_latest_pointer"
    assert (trusted / "latest.json").is_file()
    result = plan_or_execute_h2_production_latest_rollback(
        project_root=tmp_path, config_path=config, promotion_dir=promotion_dir,
        trusted_root=trusted, rollback_root=rollback_root, execute=True,
    )
    assert result["rollback_postcheck_passed"] is True
    assert not (trusted / "latest.json").exists()


def test_rollback_refuses_pointer_drift(tmp_path: Path) -> None:
    config, decision, candidate, trusted, promotion_root = _fixture(tmp_path)
    plan_or_execute_h2_production_latest_promotion(
        project_root=tmp_path, config_path=config, decision_config_path=DECISION_CONFIG,
        decision_dir=decision, candidate_dir=candidate, trusted_root=trusted,
        promotion_root=promotion_root, execute=True,
    )
    (trusted / "latest.json").write_text('{"drift":true}\n', encoding="utf-8")
    with pytest.raises(H2ProductionLatestPromotionError, match="Rollback refused"):
        plan_or_execute_h2_production_latest_rollback(
            project_root=tmp_path, config_path=config, promotion_dir=promotion_root / PROMOTION_ID,
            trusted_root=trusted, rollback_root=tmp_path / "rollbacks", execute=False,
        )
