from __future__ import annotations

import re
from types import SimpleNamespace

from radar_core.contracts.scientific_entity_semantic_prompt_raw_floor_calibration import (
    RawFloorCalibrationTrial,
)
from radar_core.contracts.scientific_entity_semantic_prompt_raw_floor_extension import (
    load_semantic_prompt_raw_floor_extension_config,
)
from radar_core.entities.scientific_entity_semantic_prompt_raw_floor_calibration import (
    DEFAULT_CONFIG_PATH,
    V02B_CONTROL,
    _compare_baseline_raw_evidence,
    _control_reproduced,
    _trial_evaluation_id,
    _v02b_control_thresholds,
    select_raw_floor_trial,
)


def _trial(
    *,
    title: float,
    combined_f1: float,
    relaxed_f1: float,
    recall: float,
    eligible: bool = True,
    trial_id: str | None = None,
) -> RawFloorCalibrationTrial:
    return RawFloorCalibrationTrial(
        calibration_id="calibration-v02c",
        trial_id=trial_id or f"trial-{title}",
        title_threshold=title,
        abstract_threshold=0.625,
        is_v02b_control_policy=title == 0.5,
        selected_prediction_count=100,
        old_dev_prediction_count=40,
        consumed_heldout_prediction_count=60,
        old_dev_exact_f1=0.4,
        consumed_heldout_exact_f1=0.4,
        consumed_heldout_relaxed_f1=0.42,
        combined_exact_precision=0.45,
        combined_exact_recall=recall,
        combined_exact_f1=combined_f1,
        combined_relaxed_f1=relaxed_f1,
        model_to_method_count=32,
        method_to_task_count=25,
        total_type_mismatch_count=138,
        method_semantic_sink_count=57,
        max_predicted_type_mismatch_sink_count=57,
        semantic_guardrails_passed=eligible,
        eligible_for_selection=eligible,
    )


def test_frozen_v02c_grid_is_title_only() -> None:
    config = load_semantic_prompt_raw_floor_extension_config(DEFAULT_CONFIG_PATH)
    assert config.raw_inference.candidate_floor == 0.4
    assert config.bounded_policy_search.title_thresholds == [
        0.4,
        0.425,
        0.45,
        0.475,
        0.5,
    ]
    assert config.bounded_policy_search.fixed_abstract_threshold == 0.625
    assert config.bounded_policy_search.expected_trial_count == 5
    assert config.bounded_policy_search.lower_abstract_thresholds_reopened is False


def test_selection_uses_combined_exact_f1_first() -> None:
    rows = [
        _trial(title=0.4, combined_f1=0.40, relaxed_f1=0.43, recall=0.37),
        _trial(title=0.45, combined_f1=0.41, relaxed_f1=0.42, recall=0.36),
    ]
    assert select_raw_floor_trial(rows).title_threshold == 0.45


def test_selection_ignores_ineligible_trial() -> None:
    rows = [
        _trial(title=0.4, combined_f1=0.50, relaxed_f1=0.50, recall=0.50, eligible=False),
        _trial(title=0.475, combined_f1=0.40, relaxed_f1=0.42, recall=0.36),
    ]
    assert select_raw_floor_trial(rows).title_threshold == 0.475


def test_selection_tie_break_prefers_relaxed_then_recall_then_stricter_title() -> None:
    rows = [
        _trial(title=0.4, combined_f1=0.40, relaxed_f1=0.42, recall=0.36),
        _trial(title=0.45, combined_f1=0.40, relaxed_f1=0.43, recall=0.35),
    ]
    assert select_raw_floor_trial(rows).title_threshold == 0.45

    rows = [
        _trial(title=0.4, combined_f1=0.40, relaxed_f1=0.43, recall=0.36),
        _trial(title=0.45, combined_f1=0.40, relaxed_f1=0.43, recall=0.37),
    ]
    assert select_raw_floor_trial(rows).title_threshold == 0.45

    rows = [
        _trial(title=0.4, combined_f1=0.40, relaxed_f1=0.43, recall=0.37),
        _trial(title=0.45, combined_f1=0.40, relaxed_f1=0.43, recall=0.37),
    ]
    assert select_raw_floor_trial(rows).title_threshold == 0.45


def test_control_reproduction_contract() -> None:
    row = _trial(
        title=0.5,
        combined_f1=V02B_CONTROL["combined_exact_f1"],
        relaxed_f1=0.419252,
        recall=0.360182,
    )
    row = row.model_copy(
        update={
            "consumed_heldout_exact_f1": V02B_CONTROL["consumed_heldout_exact_f1"],
            "model_to_method_count": V02B_CONTROL["model_to_method_count"],
            "method_to_task_count": V02B_CONTROL["method_to_task_count"],
            "total_type_mismatch_count": V02B_CONTROL["total_type_mismatch_count"],
            "method_semantic_sink_count": V02B_CONTROL["method_semantic_sink_count"],
        }
    )
    assert _control_reproduced(row) is True


def test_control_reproduction_fails_on_metric_drift() -> None:
    row = _trial(
        title=0.5,
        combined_f1=V02B_CONTROL["combined_exact_f1"] + 0.001,
        relaxed_f1=0.419252,
        recall=0.360182,
    )
    row = row.model_copy(
        update={
            "consumed_heldout_exact_f1": V02B_CONTROL["consumed_heldout_exact_f1"],
        }
    )
    assert _control_reproduced(row) is False


def test_trial_evaluation_id_is_short_deterministic_and_contract_safe() -> None:
    calibration_id = (
        "scientific-entity-semantic-prompt-raw-floor-calibration-v0.2c-"
        "20260830T123456789012Z"
    )
    trial_id = "calibration-trial:" + ("a" * 64)
    first = _trial_evaluation_id(
        calibration_id=calibration_id,
        trial_id=trial_id,
        split="old-dev-24",
    )
    second = _trial_evaluation_id(
        calibration_id=calibration_id,
        trial_id=trial_id,
        split="old-dev-24",
    )
    assert first == second
    assert len(first) <= 128
    assert ":" not in first
    assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", first)


def test_decision_thresholds_remain_v02c_frozen_values() -> None:
    config = load_semantic_prompt_raw_floor_extension_config(DEFAULT_CONFIG_PATH)
    assert config.decision.selected_policy_minimum_consumed_heldout_exact_f1 == 0.396882
    assert config.decision.selected_policy_minimum_combined_dev_exact_f1 == 0.398654
    assert (
        config.decision.selected_policy_minimum_consumed_heldout_relaxed_f1_desirable
        == 0.419252
    )
    assert config.semantic_guardrails.maximum_method_to_task_count == 25


def test_baseline_preservation_allows_new_boundary_evidence() -> None:
    baseline = [
        SimpleNamespace(
            mention_id="mention:old",
            confidence_score=0.8,
            source_field=__import__(
                "radar_core.contracts.scientific_entity_evidence",
                fromlist=["ScientificEntitySourceField"],
            ).ScientificEntitySourceField.TITLE,
        )
    ]
    candidate = baseline + [
        SimpleNamespace(
            mention_id="mention:new-boundary",
            confidence_score=0.5,
            source_field=__import__(
                "radar_core.contracts.scientific_entity_evidence",
                fromlist=["ScientificEntitySourceField"],
            ).ScientificEntitySourceField.TITLE,
        )
    ]
    result = _compare_baseline_raw_evidence(
        baseline_predictions=baseline,
        candidate_predictions=candidate,
        baseline_floor=0.5,
        control_title_threshold=0.5,
        control_abstract_threshold=0.625,
    )
    assert result["baseline_raw_evidence_preserved"] is True
    assert result["baseline_raw_missing_count"] == 0
    assert result["baseline_raw_score_changed_count"] == 0
    assert result["new_at_or_above_baseline_floor_count"] == 1
    assert result["new_selected_by_v02b_control_count"] == 1
    assert result["new_at_or_above_baseline_floor_mention_ids"] == [
        "mention:new-boundary"
    ]


def test_baseline_preservation_fails_when_old_score_drifts() -> None:
    field = __import__(
        "radar_core.contracts.scientific_entity_evidence",
        fromlist=["ScientificEntitySourceField"],
    ).ScientificEntitySourceField.TITLE
    baseline = [
        SimpleNamespace(
            mention_id="mention:old",
            confidence_score=0.8,
            source_field=field,
        )
    ]
    candidate = [
        SimpleNamespace(
            mention_id="mention:old",
            confidence_score=0.79,
            source_field=field,
        )
    ]
    result = _compare_baseline_raw_evidence(
        baseline_predictions=baseline,
        candidate_predictions=candidate,
        baseline_floor=0.5,
        control_title_threshold=0.5,
        control_abstract_threshold=0.625,
    )
    assert result["baseline_raw_evidence_preserved"] is False
    assert result["baseline_raw_missing_count"] == 0
    assert result["baseline_raw_score_changed_count"] == 1


def test_v02b_control_thresholds_use_typed_model_attributes() -> None:
    config = load_semantic_prompt_raw_floor_extension_config(DEFAULT_CONFIG_PATH)
    title, abstract = _v02b_control_thresholds(config)
    assert title == 0.5
    assert abstract == 0.625

