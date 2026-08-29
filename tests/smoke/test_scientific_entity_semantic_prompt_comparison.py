from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from radar_core.contracts.scientific_entity_semantic_prompt_candidate import (
    load_semantic_prompt_candidate_config,
)
from radar_core.contracts.scientific_entity_semantic_prompt_comparison import (
    COMPARISON_MANIFEST_SCHEMA_VERSION,
    load_semantic_prompt_comparison_config,
)
import radar_core.entities.scientific_entity_semantic_prompt_comparison as comparison_module
from radar_core.entities.scientific_entity_semantic_prompt_comparison import (
    GATE_SCHEMA_VERSION,
    PreparedComparison,
    SemanticPromptComparisonBuildError,
    _aggregate_baselines,
    _validate_frozen_heldout_baseline,
    build_semantic_prompt_comparison,
    evaluate_development_gate,
    validate_semantic_prompt_comparison,
)


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "scientific_entity_semantic_prompt_comparison_v0.2a.yaml"
DESIGN = ROOT / "configs" / "scientific_entity_semantic_prompt_candidate_v0.2a.yaml"


def _metric(tp: int, fp: int, fn: int, precision: float, recall: float, f1: float) -> dict:
    return {
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "reference_support": tp + fn,
        "prediction_support": tp + fp,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def _candidate_summary() -> dict:
    empty = _metric(1, 1, 1, 0.5, 0.5, 0.5)
    per_type = {
        name: {"exact": dict(empty), "relaxed": dict(empty)}
        for name in ("task", "method", "dataset", "metric", "model", "domain")
    }
    per_type["metric"]["exact"]["f1"] = 0.22
    per_type["domain"]["exact"]["f1"] = 0.31
    per_type["task"]["exact"]["recall"] = 0.32
    per_type["model"]["exact"]["f1"] = 0.52
    return {
        "document_count": 48,
        "reference_mention_count": 881,
        "prediction_mention_count": 650,
        "overall": {
            "exact": _metric(350, 300, 531, 0.538462, 0.397276, 0.4),
            "relaxed": _metric(365, 285, 516, 0.561538, 0.414302, 0.42),
        },
        "per_type": per_type,
        "error_count_by_kind": {},
    }


def _candidate_diagnostics() -> dict:
    return {
        "type_mismatch_total": 176,
        "type_confusions": {"model->method": 44, "method->task": 28},
        "predicted_type_mismatch_sinks": {
            "task": 40,
            "method": 84,
            "dataset": 10,
            "metric": 12,
            "model": 20,
            "domain": 10,
        },
        "false_positive_by_type": {},
        "false_negative_by_type": {},
        "boundary_mismatch_count": 20,
    }


def _frozen_baseline_summary() -> dict:
    per_type = {
        name: {
            "exact": {"f1": 0.4, "recall": 0.4},
            "relaxed": {"f1": 0.4, "recall": 0.4},
        }
        for name in ("task", "method", "dataset", "metric", "model", "domain")
    }
    per_type["metric"]["exact"]["f1"] = 0.209877
    per_type["domain"]["exact"]["f1"] = 0.293707
    per_type["task"]["exact"]["recall"] = 0.308571
    per_type["model"]["exact"]["f1"] = 0.513369
    return {
        "overall": {"exact": {"f1": 0.396882}, "relaxed": {"f1": 0.414868}},
        "per_type": per_type,
    }


def _frozen_baseline_diagnostics() -> dict:
    return {
        "type_mismatch_total": 176,
        "type_confusions": {"model->method": 55, "method->task": 28},
        "predicted_type_mismatch_sinks": {"method": 94},
    }


def test_comparison_config_freezes_real_policy_count_and_splits() -> None:
    config = load_semantic_prompt_comparison_config(CONFIG)
    assert config.candidate.expected_document_count == 72
    assert config.candidate.expected_selected_prediction_count == 977
    assert set(config.candidate.compare_splits) == {
        "old_dev_24",
        "consumed_v01_heldout_48",
        "combined_dev_72",
    }
    assert config.safety.model_inference_allowed is False
    assert config.safety.threshold_tuning_allowed is False
    assert config.safety.current_48_is_independent_heldout_for_v02 is False


def test_frozen_consumed_heldout_baseline_is_enforced() -> None:
    design = load_semantic_prompt_candidate_config(DESIGN)
    _validate_frozen_heldout_baseline(
        design=design,
        summary=_frozen_baseline_summary(),
        diagnostics=_frozen_baseline_diagnostics(),
    )
    broken = _frozen_baseline_diagnostics()
    broken["type_confusions"] = {"model->method": 54, "method->task": 28}
    with pytest.raises(SemanticPromptComparisonBuildError, match="baseline drifted"):
        _validate_frozen_heldout_baseline(
            design=design,
            summary=_frozen_baseline_summary(),
            diagnostics=broken,
        )


def test_gate_requires_all_prefrozen_hard_guardrails() -> None:
    design = load_semantic_prompt_candidate_config(DESIGN)
    gate = evaluate_development_gate(
        design=design,
        candidate_summary=_candidate_summary(),
        candidate_diagnostics=_candidate_diagnostics(),
    )
    assert gate["schema_version"] == GATE_SCHEMA_VERSION
    assert gate["all_hard_guardrails_passed"] is True
    assert gate["candidate_promising_for_next_development_slice"] is True
    assert gate["production_acceptance"] is False
    assert gate["independent_v02_acceptance"] is False

    broken = _candidate_diagnostics()
    broken["type_confusions"] = {"model->method": 45, "method->task": 28}
    gate = evaluate_development_gate(
        design=design,
        candidate_summary=_candidate_summary(),
        candidate_diagnostics=broken,
    )
    assert gate["all_hard_guardrails_passed"] is False
    assert gate["hard_guardrails"]["maximum_model_to_method_count"]["passed"] is False


def test_disjoint_metric_aggregation_recomputes_micro_counts() -> None:
    base = {
        "document_count": 1,
        "reference_mention_count": 3,
        "prediction_mention_count": 3,
        "overall": {
            "exact": _metric(2, 1, 1, 0.666667, 0.666667, 0.666667),
            "relaxed": _metric(2, 1, 1, 0.666667, 0.666667, 0.666667),
        },
        "per_type": {
            name: {
                "exact": _metric(1, 0, 0, 1.0, 1.0, 1.0),
                "relaxed": _metric(1, 0, 0, 1.0, 1.0, 1.0),
            }
            for name in ("task", "method", "dataset", "metric", "model", "domain")
        },
        "error_count_by_kind": {
            "boundary_mismatch": 0,
            "type_mismatch": 1,
            "false_positive": 1,
            "false_negative": 1,
        },
    }
    combined = _aggregate_baselines(base, base)
    assert combined["document_count"] == 2
    assert combined["overall"]["exact"]["true_positive"] == 4
    assert combined["overall"]["exact"]["false_positive"] == 2
    assert combined["overall"]["exact"]["f1"] == 0.666667
    assert combined["error_count_by_kind"]["type_mismatch"] == 2


def test_artifact_write_validate_and_immutability(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    comparison_id = "scientific-entity-semantic-prompt-comparison-v0.2a-test"
    generated = datetime(2026, 8, 29, 16, 0, tzinfo=timezone.utc)
    manifest = {
        "schema_version": COMPARISON_MANIFEST_SCHEMA_VERSION,
        "comparison_id": comparison_id,
        "candidate_id": "scientific-entity-semantic-prompt-candidate-v0.2a",
        "generated_at_utc": generated.isoformat().replace("+00:00", "Z"),
    }
    prepared = PreparedComparison(
        report={
            "report": "scientific_entity_semantic_prompt_comparison_v02a",
            "ok": True,
            "comparison_id": comparison_id,
            "candidate_id": "scientific-entity-semantic-prompt-candidate-v0.2a",
            "development_document_count": 72,
            "reference_mention_count": 1316,
            "candidate_prediction_count": 977,
            "consumed_heldout_candidate_exact_f1": 0.4,
            "consumed_heldout_candidate_relaxed_f1": 0.42,
            "consumed_heldout_model_to_method_count": 44,
            "consumed_heldout_method_to_task_count": 28,
            "consumed_heldout_total_type_mismatch_count": 176,
            "consumed_heldout_method_semantic_sink_count": 84,
            "all_hard_guardrails_passed": True,
            "candidate_promising_for_next_development_slice": True,
            "model_inference_executed": False,
            "threshold_tuning_executed": False,
            "canonical_truth_mutated": False,
            "full_corpus_build_authorized": False,
            "production_extractor_selected": False,
            "next_slice": "consider_separate_v02_recalibration_then_fresh_disjoint_heldout",
        },
        manifest=manifest,
        comparison={"schema_version": "test", "comparison_id": comparison_id},
        diagnostics={"schema_version": "test", "comparison_id": comparison_id},
        gate_decision={"schema_version": "test", "comparison_id": comparison_id},
        readme="# fixture\n",
    )
    monkeypatch.setattr(comparison_module, "_prepare", lambda **kwargs: prepared)
    output_root = tmp_path / "out"
    report = build_semantic_prompt_comparison(
        project_root=ROOT,
        config_path=CONFIG,
        development_package_dir=tmp_path / "package",
        policy_build_dir=tmp_path / "policy",
        parent_raw_build_dir=tmp_path / "raw",
        output_root=output_root,
        comparison_id=comparison_id,
        execute=True,
        generated_at_utc=generated,
    )
    comparison_dir = output_root / comparison_id
    assert report["phase_complete"] is True
    assert (comparison_dir / "checksums.txt").is_file()
    validated = validate_semantic_prompt_comparison(
        project_root=ROOT,
        config_path=CONFIG,
        comparison_dir=comparison_dir,
        development_package_dir=tmp_path / "package",
        policy_build_dir=tmp_path / "policy",
        parent_raw_build_dir=tmp_path / "raw",
    )
    assert validated["required_failed_count"] == 0
    with pytest.raises(FileExistsError):
        build_semantic_prompt_comparison(
            project_root=ROOT,
            config_path=CONFIG,
            development_package_dir=tmp_path / "package",
            policy_build_dir=tmp_path / "policy",
            parent_raw_build_dir=tmp_path / "raw",
            output_root=output_root,
            comparison_id=comparison_id,
            execute=True,
            generated_at_utc=generated,
        )
