from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from radar_core.contracts.scientific_entity_semantic_typer_h2_production_authorization_gate import (
    H2ProductionAuthorizationGateConfig,
    canonical_config_sha256,
    load_h2_production_authorization_gate_config,
)

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "scientific_entity_semantic_typer_h2_production_authorization_gate_v0.3.yaml"


def _payload() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def test_gate_config_loads_and_is_frozen_non_authorizing():
    cfg = load_h2_production_authorization_gate_config(CONFIG)
    assert cfg.acceptance_lineage.candidate_fingerprint_sha256 == "6d3782fb1f2cc7219b7083bcf381c17c546491425e817c0f5620ff145bfa6966"
    assert cfg.bounded_intervention.threshold == 0.1
    assert cfg.safety.gate_slice_authorizes_full_corpus_candidate_build is False
    assert cfg.safety.gate_slice_authorizes_latest_promotion is False
    assert cfg.safety.overwrite_latest_allowed is False


def test_future_authorization_is_candidate_only_and_snapshot_bound():
    cfg = load_h2_production_authorization_gate_config(CONFIG)
    assert cfg.future_authorization_boundary.authorization_may_only_enable_timestamped_full_corpus_candidate_materialization
    assert cfg.future_authorization_boundary.authorization_must_bind_exact_canonical_snapshot
    assert cfg.future_authorization_boundary.authorization_does_not_imply_latest_promotion
    assert cfg.production_authorization_prerequisites.require_candidate_validation_before_promotion
    assert cfg.production_authorization_prerequisites.require_separate_promotion_decision


def test_policy_drift_fails_closed():
    payload = _payload()
    payload["bounded_intervention"]["threshold"] = 0.15
    with pytest.raises(ValidationError):
        H2ProductionAuthorizationGateConfig.model_validate(payload)


def test_candidate_fingerprint_drift_fails_closed():
    payload = _payload()
    payload["acceptance_lineage"]["candidate_fingerprint_sha256"] = "0" * 64
    with pytest.raises(ValidationError):
        H2ProductionAuthorizationGateConfig.model_validate(payload)


def test_gate_cannot_self_authorize_build():
    payload = _payload()
    payload["safety"]["gate_slice_authorizes_full_corpus_candidate_build"] = True
    with pytest.raises(ValidationError):
        H2ProductionAuthorizationGateConfig.model_validate(payload)


def test_gate_cannot_allow_latest_overwrite():
    payload = _payload()
    payload["safety"]["overwrite_latest_allowed"] = True
    with pytest.raises(ValidationError):
        H2ProductionAuthorizationGateConfig.model_validate(payload)


def test_unknown_config_field_is_rejected():
    payload = _payload()
    payload["safety"]["surprise"] = True
    with pytest.raises(ValidationError):
        H2ProductionAuthorizationGateConfig.model_validate(payload)


def test_canonical_config_hash_is_stable_shape():
    cfg = load_h2_production_authorization_gate_config(CONFIG)
    digest = canonical_config_sha256(cfg)
    assert len(digest) == 64
    assert set(digest) <= set("0123456789abcdef")
