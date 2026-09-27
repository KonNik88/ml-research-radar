from __future__ import annotations

from pathlib import Path

import pytest

from radar_core.contracts.scientific_entity_evidence import ScientificEntityType
from radar_core.contracts.scientific_entity_semantic_typer_h2_independent_evaluation import (
    H2ComparativeCase,
    load_h2_independent_evaluation_config,
)
from radar_core.entities import (
    scientific_entity_semantic_typer_h2_independent_evaluation as mod,
)

ROOT = Path(__file__).resolve().parents[2]
CONFIG = (
    ROOT
    / "configs"
    / "scientific_entity_semantic_typer_h2_independent_evaluation_v0.3.yaml"
)


def _parent() -> dict:
    cfg = load_h2_independent_evaluation_config(CONFIG)
    return {
        "config": cfg,
        "gate_sha": cfg.acceptance_gate.config_sha256,
        "base_config_sha": "1" * 64,
        "evaluation_config_sha": "2" * 64,
        "inference_summary": {
            "required_failed_count": 0,
            "typer_coverage": 0.983133,
        },
    }


def _case(
    index: int,
    *,
    reference: ScientificEntityType,
    baseline: ScientificEntityType,
    h2: ScientificEntityType,
) -> H2ComparativeCase:
    return H2ComparativeCase(
        case_id=f"h2-comparative-case:{index:032x}",
        reference_id=f"reference:{index:032x}",
        baseline_prediction_evidence_id=f"evidence:{index:032x}",
        canonical_id=f"paper-{index}",
        source_field="title",
        source_text_sha256="a" * 64,
        char_start=0,
        char_end=4,
        surface_text="test",
        reference_entity_type=reference,
        baseline_entity_type=baseline,
        h2_entity_type=h2,
        h2_override_applied=(baseline != h2),
        baseline_correct=(baseline == reference),
        h2_correct=(h2 == reference),
    )


def test_contract_freezes_exact_h2_independent_evaluation_boundary() -> None:
    cfg = load_h2_independent_evaluation_config(CONFIG)
    assert cfg.candidate.candidate_fingerprint_sha256 == (
        "6d3782fb1f2cc7219b7083bcf381c17c546491425e817c0f5620ff145bfa6966"
    )
    assert cfg.inference.inference_id.endswith("20260927T102527705827Z")
    assert cfg.inference.expected_baseline_prediction_count == 830
    assert cfg.inference.expected_h2_prediction_count == 830
    assert cfg.fresh_heldout.expected_reference_mention_count == 929
    assert cfg.acceptance_gate.minimum_typer_coverage == 0.95
    assert cfg.acceptance_gate.minimum_same_span_accuracy_delta == 0.01
    assert cfg.acceptance_gate.minimum_net_corrected_cases == 5
    assert cfg.acceptance_gate.maximum_regression_rate == 0.05
    assert cfg.acceptance_gate.minimum_model_to_method_reduction_fraction == 0.1
    assert cfg.acceptance_gate.minimum_macro_f1_delta == 0.0
    assert cfg.acceptance_gate.minimum_exact_f1 == 0.396882
    assert cfg.acceptance_gate.desirable_minimum_relaxed_f1 == 0.414868
    assert cfg.safety.acceptance_decision_allowed_in_this_slice is False


def test_plan_is_non_writing_and_exposes_no_quality_metrics(
    tmp_path: Path, monkeypatch
) -> None:
    parent = _parent()
    monkeypatch.setattr(mod, "_validate_parent_state", lambda **kwargs: parent)

    report = mod.plan_or_execute_h2_independent_evaluation(
        project_root=tmp_path,
        config_path=CONFIG,
        sample_dir=tmp_path / "sample",
        reference_dir=tmp_path / "reference",
        development_package_dir=tmp_path / "dev",
        previous_heldout_sample_dir=tmp_path / "previous",
        frozen_candidate_dir=tmp_path / "candidate",
        canonical_path=tmp_path / "canonical.jsonl",
        inference_dir=tmp_path / "inference",
        execute=False,
    )
    assert report["phase_complete"] is False
    assert report["plan_runs_evaluation"] is False
    assert report["plan_exposes_quality_metrics"] is False
    assert report["evaluation_executed"] is False
    assert report["acceptance_decision_made"] is False
    assert "same_span_accuracy_delta" not in report
    assert "h2_exact_f1" not in report


def test_classification_snapshot_uses_all_six_types_and_exact_case_accuracy() -> None:
    cases = []
    index = 1
    for kind in ScientificEntityType:
        cases.append(_case(index, reference=kind, baseline=kind, h2=kind))
        index += 1
        wrong = ScientificEntityType.METHOD if kind != ScientificEntityType.METHOD else ScientificEntityType.TASK
        cases.append(_case(index, reference=kind, baseline=wrong, h2=kind))
        index += 1

    baseline = mod._classification_snapshot(
        cases,
        prediction_field="baseline_entity_type",
        decimal_places=6,
    )
    h2 = mod._classification_snapshot(
        cases,
        prediction_field="h2_entity_type",
        decimal_places=6,
    )
    assert baseline.case_count == 12
    assert baseline.correct_count == 6
    assert baseline.accuracy == 0.5
    assert h2.correct_count == 12
    assert h2.accuracy == 1.0
    assert h2.macro_f1 == 1.0
    assert len(h2.per_type) == 6


def test_classification_snapshot_marks_macro_f1_missing_when_type_support_is_absent() -> None:
    cases = [
        _case(
            1,
            reference=ScientificEntityType.MODEL,
            baseline=ScientificEntityType.METHOD,
            h2=ScientificEntityType.MODEL,
        )
    ]
    snapshot = mod._classification_snapshot(
        cases,
        prediction_field="h2_entity_type",
        decimal_places=6,
    )
    assert snapshot.accuracy == 1.0
    assert snapshot.macro_f1 is None


def test_model_to_method_direct_correction_semantics_are_unambiguous() -> None:
    case = _case(
        1,
        reference=ScientificEntityType.MODEL,
        baseline=ScientificEntityType.METHOD,
        h2=ScientificEntityType.MODEL,
    )
    assert case.baseline_correct is False
    assert case.h2_correct is True
    assert case.h2_override_applied is True
    assert (
        case.reference_entity_type == ScientificEntityType.MODEL
        and case.baseline_entity_type == ScientificEntityType.METHOD
        and case.h2_entity_type == ScientificEntityType.MODEL
    )


def test_execute_refuses_existing_immutable_evaluation_directory(
    tmp_path: Path, monkeypatch
) -> None:
    parent = _parent()
    monkeypatch.setattr(mod, "_validate_parent_state", lambda **kwargs: parent)
    cfg = parent["config"]
    output = tmp_path / cfg.execution.output_root / cfg.execution.evaluation_id
    output.mkdir(parents=True)

    with pytest.raises(FileExistsError):
        mod.plan_or_execute_h2_independent_evaluation(
            project_root=tmp_path,
            config_path=CONFIG,
            sample_dir=tmp_path / "sample",
            reference_dir=tmp_path / "reference",
            development_package_dir=tmp_path / "dev",
            previous_heldout_sample_dir=tmp_path / "previous",
            frozen_candidate_dir=tmp_path / "candidate",
            canonical_path=tmp_path / "canonical.jsonl",
            inference_dir=tmp_path / "inference",
            execute=True,
        )
