"""Offline decision-layer unit tests; never touch frozen human labels."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from radar_core.contracts.scientific_entity_semantic_typer_h2_independent_acceptance_gate import (
    load_h2_independent_acceptance_gate_config,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_independent_acceptance_decision import (
    H2IndependentDecisionError,
    H2IndependentDecisionRecord,
    load_h2_independent_decision_config,
)
from radar_core.entities import scientific_entity_semantic_typer_h2_independent_acceptance_decision as mod

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs/scientific_entity_semantic_typer_h2_independent_acceptance_decision_v0.3.yaml"
GATE = ROOT / "configs/scientific_entity_semantic_typer_h2_independent_acceptance_gate_v0.3.yaml"


def _summary(*, delta=0.027197, regression=0.021918, macro=0.013825, exact=0.42979, relaxed=0.466174):
    per_type = [NS(reference_support=21) for _ in range(6)]
    return NS(
        required_metric_denominators_present=True,
        same_span_pair_count=478,
        typer_coverage=0.983133,
        baseline_typing=NS(correct_count=365, accuracy=0.763598, macro_f1=0.770347, per_type=per_type),
        h2_typing=NS(correct_count=378, accuracy=0.790795, macro_f1=0.784172, per_type=per_type),
        same_span_accuracy_delta=delta,
        macro_f1_delta=macro,
        corrected_errors=21,
        introduced_regressions=8,
        net_corrected_cases=13,
        regression_rate=regression,
        baseline_model_to_method_count=51,
        h2_model_to_method_count=30,
        model_to_method_reduction_fraction=0.411765,
        model_to_method_direct_corrections=21,
        model_to_method_wrong_to_wrong=0,
        baseline_extraction=NS(model_to_method_count=60, method_to_task_count=20, total_type_mismatch_count=200, method_semantic_sink_count=90, maximum_any_predicted_type_mismatch_sink_count=95),
        h2_extraction=NS(exact_f1=exact, relaxed_f1=relaxed, model_to_method_count=39, method_to_task_count=20, total_type_mismatch_count=179, method_semantic_sink_count=69, maximum_any_predicted_type_mismatch_sink_count=75),
    )


def _record(**kwargs):
    return mod.build_decision_record(
        config=load_h2_independent_decision_config(CONFIG),
        gate=load_h2_independent_acceptance_gate_config(GATE),
        summary=kwargs.pop("summary", _summary()),
        reference_adequacy_passed=kwargs.pop("reference_adequacy_passed", True),
        fingerprint_matches=kwargs.pop("fingerprint_matches", True),
        strict_validation_passed=kwargs.pop("strict_validation_passed", True),
        **kwargs,
    )


def _parent():
    config = load_h2_independent_decision_config(CONFIG)
    return {
        "config": config,
        "gate": load_h2_independent_acceptance_gate_config(GATE),
        "gate_sha": config.frozen_inputs.gate_config_sha256,
        "evaluation_config_sha": "2" * 64,
        "manifest": NS(candidate_fingerprint_sha256=config.candidate.candidate_fingerprint_sha256),
        "summary": _summary(),
        "reference_adequacy_passed": True,
        "evaluation_strict_validation_passed": True,
        "evaluation_validation_total_checks": 55,
        "evaluation_manifest_sha": "3" * 64,
        "evaluation_summary_sha": "4" * 64,
        "reference_completion_sha": "5" * 64,
    }


def _call(modfn, project: Path, *, execute: bool):
    return modfn(
        project_root=project, config_path=CONFIG,
        evaluation_dir=project / "eval", inference_dir=project / "inference",
        sample_dir=project / "sample", reference_dir=project / "reference",
        development_package_dir=project / "dev", previous_heldout_sample_dir=project / "previous",
        frozen_candidate_dir=project / "frozen", canonical_path=project / "canonical.jsonl",
        execute=execute,
    )


def test_config_fixes_candidate_and_preserves_gate_semantics():
    config = load_h2_independent_decision_config(CONFIG)
    assert config.frozen_inputs.gate_config_sha256 == "3ed17739796807046269b88aab40ced2cc10ca1e45ff67dc8965a98070c17a89"
    assert config.execution.overwrite_allowed is False
    assert config.execution.plan_makes_decision is False
    assert config.safety.production_extractor_selected is False
    assert config.safety.full_corpus_build_authorized is False


def test_all_preregistered_gates_pass_in_synthetic_fixture():
    record = _record()
    assert record.all_hard_gates_passed is True
    assert len(record.hard_gates) == 9
    assert record.decision == "accept_h2_as_independently_validated_bounded_semantic_typing_intervention"
    assert record.production_extractor_selected is False
    assert record.full_corpus_build_authorized is False


def test_regression_rate_failure_rejects_without_tuning():
    record = _record(summary=_summary(regression=0.050001))
    assert record.decision == "reject_h2_independent_acceptance"
    assert [g.name for g in record.hard_gates if not g.passed] == ["maximum_regression_rate"]


def test_negative_macro_delta_is_hard_failure():
    record = _record(summary=_summary(macro=-0.000001))
    assert record.decision == "reject_h2_independent_acceptance"


def test_relaxed_f1_not_hard_and_old_caps_only_diagnostic():
    record = _record(summary=_summary(relaxed=0.0))
    assert record.desirable_relaxed_f1_met is False
    assert record.all_hard_gates_passed is True
    assert "historical" not in " ".join(row.name for row in record.hard_gates)


def test_reference_adequacy_and_fingerprint_are_hard_gates():
    record = _record(reference_adequacy_passed=False, fingerprint_matches=False)
    assert record.decision == "reject_h2_independent_acceptance"
    assert [g.name for g in record.hard_gates if not g.passed] == ["reference_adequacy", "candidate_fingerprint"]
    assert record.reference_adequacy_passed is False


def test_missing_denominator_fails_closed_without_a_verdict():
    s = _summary()
    s.baseline_model_to_method_count = 0
    with pytest.raises(H2IndependentDecisionError, match="Insufficient"):
        _record(summary=s)
    with pytest.raises(H2IndependentDecisionError, match="strict validation"):
        _record(strict_validation_passed=False)


def test_plan_is_no_write_and_has_no_metrics_or_decision(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "_validate_frozen_state", lambda **kwargs: _parent())
    report = _call(mod.plan_or_execute_h2_independent_acceptance_decision, tmp_path, execute=False)
    assert report["decision_made"] is False
    assert report["plan_makes_decision"] is False
    assert report["plan_exposes_quality_metrics"] is False
    assert "decision" not in report
    assert "same_span_accuracy_delta" not in report
    assert not (tmp_path / "data").exists()


def test_one_shot_atomic_immutable_artifact_and_validator(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "_validate_frozen_state", lambda **kwargs: _parent())
    report = _call(mod.plan_or_execute_h2_independent_acceptance_decision, tmp_path, execute=True)
    assert report["phase_complete"] is True
    assert report["decision_made"] is True
    assert report["all_hard_gates_passed"] is True
    decision_dir = Path(report["output_dir"])
    assert {p.name for p in decision_dir.iterdir()} == mod.REQUIRED_FILES
    decision = H2IndependentDecisionRecord.model_validate(mod._read_json(decision_dir / "decision.json"))
    assert len(decision.hard_gates) == 9
    with pytest.raises(FileExistsError):
        _call(mod.plan_or_execute_h2_independent_acceptance_decision, tmp_path, execute=True)
    kwargs = {
        "project_root": tmp_path, "config_path": CONFIG,
        "decision_dir": decision_dir, "evaluation_dir": tmp_path / "eval",
        "inference_dir": tmp_path / "inference", "sample_dir": tmp_path / "sample",
        "reference_dir": tmp_path / "reference", "development_package_dir": tmp_path / "dev",
        "previous_heldout_sample_dir": tmp_path / "previous",
        "frozen_candidate_dir": tmp_path / "frozen", "canonical_path": tmp_path / "canonical.jsonl",
    }
    checks, summary = mod.validate_h2_independent_acceptance_decision(**kwargs)
    assert summary["required_failed_count"] == 0, checks
    (decision_dir / "decision.json").write_text("{}\n", encoding="utf-8")
    checks, summary = mod.validate_h2_independent_acceptance_decision(**kwargs)
    assert summary["required_failed_count"] > 0
    assert any(name == "checksum:decision.json" and not ok for name, ok, _ in checks)
