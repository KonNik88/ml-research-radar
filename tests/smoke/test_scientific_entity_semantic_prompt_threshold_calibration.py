from __future__ import annotations

from pathlib import Path
import re

from radar_core.contracts.scientific_entity_semantic_prompt_threshold_calibration import (
    CalibrationTrial,
    load_semantic_prompt_threshold_calibration_config,
)
from radar_core.entities.scientific_entity_semantic_prompt_threshold_calibration import (
    _trial_evaluation_id,
    evaluate_selected_policy_gate,
    evaluate_semantic_guardrails,
    select_trial,
    threshold_calibration_config_sha256,
)


ROOT = Path(__file__).resolve().parents[2]
CONFIG = (
    ROOT
    / "configs"
    / "scientific_entity_semantic_prompt_threshold_calibration_v0.2b.yaml"
)


def _trial(
    *,
    suffix: str,
    title: float,
    abstract: float,
    combined_f1: float,
    combined_relaxed: float,
    combined_recall: float,
    heldout_f1: float = 0.40,
    eligible: bool = True,
) -> CalibrationTrial:
    return CalibrationTrial(
        calibration_id="scientific-entity-semantic-prompt-threshold-calibration-v0.2b-test",
        trial_id=f"calibration-trial:{suffix}",
        title_threshold=title,
        abstract_threshold=abstract,
        is_inherited_v02a_policy=(title == 0.55 and abstract == 0.65),
        selected_prediction_count=900,
        old_dev_prediction_count=300,
        consumed_heldout_prediction_count=600,
        old_dev_exact_f1=0.39,
        consumed_heldout_exact_f1=heldout_f1,
        consumed_heldout_relaxed_f1=0.42,
        combined_exact_precision=0.44,
        combined_exact_recall=combined_recall,
        combined_exact_f1=combined_f1,
        combined_relaxed_f1=combined_relaxed,
        model_to_method_count=40,
        method_to_task_count=24,
        total_type_mismatch_count=145,
        method_semantic_sink_count=70,
        max_predicted_type_mismatch_sink_count=70,
        semantic_guardrails_passed=eligible,
        eligible_for_selection=eligible,
    )


def test_config_freezes_exact_35_trial_source_pair_grid() -> None:
    config = load_semantic_prompt_threshold_calibration_config(CONFIG)
    assert config.search.expected_trial_count == 35
    assert config.search.title_thresholds == [0.5, 0.525, 0.55, 0.575, 0.6]
    assert config.search.abstract_thresholds == [
        0.5,
        0.525,
        0.55,
        0.575,
        0.6,
        0.625,
        0.65,
    ]
    assert config.search.inherited_v02a_policy.title == 0.55
    assert config.search.inherited_v02a_policy.abstract == 0.65
    assert config.search.entity_type_overrides_allowed is False


def test_config_freezes_v02a_lineage_and_no_new_inference() -> None:
    config = load_semantic_prompt_threshold_calibration_config(CONFIG)
    assert config.lineage.expected_document_count == 72
    assert config.lineage.expected_reference_mention_count == 1316
    assert config.lineage.expected_raw_prediction_count == 1430
    assert config.lineage.raw_build_id == (
        "scientific-entity-gliner-small-v2.5-v0.1-20260829T141340564165Z"
    )
    assert config.safety.model_inference_allowed is False
    assert config.safety.prompt_changes_allowed is False
    assert config.safety.fresh_heldout_consumption_allowed is False
    assert config.safety.full_corpus_build_authorized is False


def test_config_hash_is_stable() -> None:
    first = load_semantic_prompt_threshold_calibration_config(CONFIG)
    second = load_semantic_prompt_threshold_calibration_config(CONFIG)
    assert threshold_calibration_config_sha256(first) == threshold_calibration_config_sha256(second)
    assert len(threshold_calibration_config_sha256(first)) == 64


def test_semantic_guardrails_preserve_at_least_half_v02a_gain() -> None:
    config = load_semantic_prompt_threshold_calibration_config(CONFIG)
    passing = {
        "type_mismatch_total": 150,
        "type_confusions": {"model->method": 43, "method->task": 25},
        "predicted_type_mismatch_sinks": {
            "task": 20,
            "method": 74,
            "dataset": 10,
            "metric": 12,
            "model": 20,
            "domain": 14,
        },
    }
    rows = evaluate_semantic_guardrails(config=config, diagnostics=passing)
    assert all(row["passed"] for row in rows.values())

    broken = dict(passing)
    broken["type_confusions"] = {"model->method": 44, "method->task": 25}
    rows = evaluate_semantic_guardrails(config=config, diagnostics=broken)
    assert rows["maximum_model_to_method_count"]["passed"] is False


def test_selection_maximizes_combined_exact_f1_before_ties() -> None:
    trials = [
        _trial(
            suffix="a",
            title=0.55,
            abstract=0.60,
            combined_f1=0.392,
            combined_relaxed=0.420,
            combined_recall=0.36,
        ),
        _trial(
            suffix="b",
            title=0.55,
            abstract=0.625,
            combined_f1=0.398,
            combined_relaxed=0.415,
            combined_recall=0.35,
        ),
    ]
    assert select_trial(trials).trial_id == "calibration-trial:b"


def test_selection_uses_relaxed_then_recall_then_stricter_policy() -> None:
    relaxed_wins = [
        _trial(
            suffix="a",
            title=0.50,
            abstract=0.60,
            combined_f1=0.398,
            combined_relaxed=0.420,
            combined_recall=0.36,
        ),
        _trial(
            suffix="b",
            title=0.55,
            abstract=0.60,
            combined_f1=0.398,
            combined_relaxed=0.421,
            combined_recall=0.35,
        ),
    ]
    assert select_trial(relaxed_wins).trial_id == "calibration-trial:b"

    stricter_wins = [
        _trial(
            suffix="c",
            title=0.50,
            abstract=0.60,
            combined_f1=0.398,
            combined_relaxed=0.421,
            combined_recall=0.36,
        ),
        _trial(
            suffix="d",
            title=0.55,
            abstract=0.60,
            combined_f1=0.398,
            combined_relaxed=0.421,
            combined_recall=0.36,
        ),
    ]
    assert select_trial(stricter_wins).trial_id == "calibration-trial:d"


def test_ineligible_trial_cannot_win_even_with_higher_f1() -> None:
    trials = [
        _trial(
            suffix="unsafe",
            title=0.50,
            abstract=0.50,
            combined_f1=0.45,
            combined_relaxed=0.46,
            combined_recall=0.43,
            eligible=False,
        ),
        _trial(
            suffix="safe",
            title=0.55,
            abstract=0.60,
            combined_f1=0.40,
            combined_relaxed=0.42,
            combined_recall=0.37,
            eligible=True,
        ),
    ]
    assert select_trial(trials).trial_id == "calibration-trial:safe"


def test_selected_policy_gate_requires_recovery_and_semantic_safety() -> None:
    config = load_semantic_prompt_threshold_calibration_config(CONFIG)
    selected = _trial(
        suffix="pass",
        title=0.525,
        abstract=0.60,
        combined_f1=0.40,
        combined_relaxed=0.42,
        combined_recall=0.37,
        heldout_f1=0.40,
        eligible=True,
    )
    gate = evaluate_selected_policy_gate(config=config, selected=selected)
    assert all(row["passed"] for row in gate.values())

    failed = selected.model_copy(update={"consumed_heldout_exact_f1": 0.39})
    gate = evaluate_selected_policy_gate(config=config, selected=failed)
    assert gate["minimum_consumed_heldout_exact_f1"]["passed"] is False


def test_trial_evaluation_id_is_short_deterministic_and_contract_safe() -> None:
    calibration_id = (
        "scientific-entity-semantic-prompt-threshold-calibration-v0.2b-"
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
    other_split = _trial_evaluation_id(
        calibration_id=calibration_id,
        trial_id=trial_id,
        split="combined-72",
    )

    assert first == second
    assert first != other_split
    assert len(first) <= 128
    assert ":" not in first
    assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", first)

