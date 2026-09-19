from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from radar_core.contracts.scientific_entity_semantic_typer_h2_frozen_candidate import load_h2_frozen_candidate_config
from radar_core.entities.scientific_entity_semantic_typer_h2_frozen_candidate import _candidate_definition
from radar_core.contracts.scientific_entity_semantic_typer_revision_analysis import SelectedRevisionPolicy


def test_h2_freeze_config_is_exactly_bounded() -> None:
    root = Path(__file__).resolve().parents[2]
    config = load_h2_frozen_candidate_config(root / "configs/scientific_entity_semantic_typer_h2_frozen_candidate_v0.3.yaml")
    assert config.selected_policy.baseline_type.value == "method"
    assert config.selected_policy.semantic_typer_type.value == "model"
    assert config.selected_policy.threshold == 0.1
    assert config.selected_policy.expected_plateau_thresholds == [0.05, 0.1, 0.15]
    assert config.safety.new_model_inference_allowed is False
    assert config.safety.threshold_tuning_allowed is False
    assert config.safety.future_candidate_requires_new_independent_heldout is True


def test_selected_policy_contract_rejects_threshold_drift() -> None:
    payload = {
        "status": "selected",
        "policy_id": "scientific-entity-semantic-typer-candidate-v0.3-h2-selective-model-over-method",
        "baseline_type": "method",
        "semantic_typer_type": "model",
        "score_field": "score_margin",
        "operator": ">=",
        "threshold": 0.1,
        "selection_rule": "lowest_interior_threshold_in_three_point_all_gate_pass_plateau",
        "plateau_thresholds": [0.05, 0.1, 0.15],
        "development_calibration_only": True,
        "independent_acceptance_executed": False,
        "future_candidate_requires_new_independent_heldout": True,
    }
    policy = SelectedRevisionPolicy.model_validate(payload)
    assert policy.threshold == 0.1
    assert policy.status == "selected"


def test_candidate_fingerprint_is_deterministic(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    config = load_h2_frozen_candidate_config(root / "configs/scientific_entity_semantic_typer_h2_frozen_candidate_v0.3.yaml")
    revision_dir = tmp_path / "rev"
    revision_dir.mkdir()
    (revision_dir / "manifest.json").write_text(json.dumps({"analysis_id": "analysis-x"}), encoding="utf-8")
    (revision_dir / "selected_policy.json").write_text("{}", encoding="utf-8")
    policy = SelectedRevisionPolicy.model_validate({
        "status": "selected",
        "policy_id": config.candidate.candidate_id,
        "baseline_type": "method",
        "semantic_typer_type": "model",
        "score_field": "score_margin",
        "operator": ">=",
        "threshold": 0.1,
        "selection_rule": config.selected_policy.selection_rule,
        "plateau_thresholds": [0.05, 0.1, 0.15],
        "development_calibration_only": True,
        "independent_acceptance_executed": False,
        "future_candidate_requires_new_independent_heldout": True,
    })
    manifest = {"analysis_id": "analysis-x"}
    d1 = _candidate_definition(
        config=config,
        revision_analysis_dir=revision_dir,
        revision_manifest=manifest,
        revision_policy=policy,
        parent_config_path=root / config.candidate.parent_semantic_typer_config_path,
        parent_config_sha="a" * 64,
    )
    d2 = _candidate_definition(
        config=config,
        revision_analysis_dir=revision_dir,
        revision_manifest=manifest,
        revision_policy=policy,
        parent_config_path=root / config.candidate.parent_semantic_typer_config_path,
        parent_config_sha="a" * 64,
    )
    assert d1.candidate_fingerprint_sha256 == d2.candidate_fingerprint_sha256
    assert len(d1.candidate_fingerprint_sha256) == 64
