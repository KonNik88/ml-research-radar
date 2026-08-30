from __future__ import annotations

import re

from radar_core.contracts.scientific_entity_semantic_prompt_raw_floor_comparison import (
    load_raw_floor_comparison_config,
)
from radar_core.entities.scientific_entity_semantic_prompt_raw_floor_comparison import (
    DEFAULT_CONFIG_PATH,
    _evaluate_gate,
    _safe_evaluation_id,
)


def _summary(*, exact_f1: float, relaxed_f1: float, prediction_count: int = 100) -> dict:
    return {
        "overall": {
            "exact": {"precision": 0.45, "recall": 0.37, "f1": exact_f1, "tp": 1, "fp": 1, "fn": 1},
            "relaxed": {"precision": 0.47, "recall": 0.39, "f1": relaxed_f1, "tp": 1, "fp": 1, "fn": 1},
        },
        "per_type": {},
        "prediction_mention_count": prediction_count,
    }


def _diag(*, m2m: int = 32, m2t: int = 25, total: int = 140, method_sink: int = 58) -> dict:
    return {
        "type_confusions": {"model->method": m2m, "method->task": m2t},
        "type_mismatch_total": total,
        "predicted_type_mismatch_sinks": {
            "method": method_sink,
            "task": 20,
            "model": 10,
            "dataset": 5,
            "metric": 5,
            "domain": 5,
        },
    }


def test_frozen_v02c_comparison_contract() -> None:
    config = load_raw_floor_comparison_config(DEFAULT_CONFIG_PATH)
    assert config.candidate.expected_document_count == 72
    assert config.candidate.expected_reference_mention_count == 1316
    assert config.candidate.expected_selected_prediction_count == 1077
    assert config.candidate.selected_trial_id == "calibration-trial:adcd020d8bce5af1ff157f4303e0b171"
    assert config.hard_guardrails.minimum_consumed_heldout_exact_f1 == 0.396882
    assert config.hard_guardrails.minimum_combined_dev_exact_f1 == 0.398654
    assert config.hard_guardrails.maximum_method_to_task_count == 25
    assert config.safety.fresh_heldout_consumption_allowed is False


def test_safe_evaluation_id_is_contract_safe() -> None:
    value = _safe_evaluation_id(
        "scientific-entity-semantic-prompt-raw-floor-comparison-v0.2c-20260830T123456789012Z",
        "consumed-v01-heldout-48",
    )
    assert len(value) <= 128
    assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value)


def test_gate_passes_exact_frozen_v02c_selected_metrics() -> None:
    config = load_raw_floor_comparison_config(DEFAULT_CONFIG_PATH)
    summaries = {
        "consumed_v01_heldout_48": _summary(exact_f1=0.4, relaxed_f1=0.422642),
        "combined_dev_72": _summary(exact_f1=0.403677, relaxed_f1=0.43),
    }
    diagnostics = {
        "consumed_v01_heldout_48": _diag(),
        "combined_dev_72": _diag(),
    }
    gate = _evaluate_gate(
        config=config,
        candidate_summaries=summaries,
        candidate_diagnostics=diagnostics,
    )
    assert gate["calibration_reproduction_passed"] is True
    assert gate["all_hard_guardrails_passed"] is True
    assert gate["candidate_ready_for_development_freeze"] is True
    assert gate["next_slice"] == "freeze_v02c_development_candidate_and_prepare_new_disjoint_prediction_blind_heldout"


def test_gate_rejects_semantic_guardrail_regression() -> None:
    config = load_raw_floor_comparison_config(DEFAULT_CONFIG_PATH)
    summaries = {
        "consumed_v01_heldout_48": _summary(exact_f1=0.4, relaxed_f1=0.422642),
        "combined_dev_72": _summary(exact_f1=0.403677, relaxed_f1=0.43),
    }
    diagnostics = {
        "consumed_v01_heldout_48": _diag(m2t=26),
        "combined_dev_72": _diag(m2t=26),
    }
    try:
        _evaluate_gate(
            config=config,
            candidate_summaries=summaries,
            candidate_diagnostics=diagnostics,
        )
    except Exception as exc:
        assert "does not reproduce selected calibration trial" in str(exc)
    else:
        raise AssertionError("calibration reproduction must fail closed on semantic drift")
