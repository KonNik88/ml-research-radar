from __future__ import annotations

from pathlib import Path

import pytest

from radar_core.contracts.scientific_entity_fresh_heldout_evaluation import (
    load_scientific_entity_fresh_heldout_evaluation_config,
)
from radar_core.entities import scientific_entity_fresh_heldout_evaluation as mod

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "scientific_entity_fresh_heldout_evaluation_v0.2.yaml"


def _fixture_dirs(tmp_path: Path):
    project = tmp_path / "project"
    sample = project / "sample"
    reference = project / "reference"
    dev = project / "dev"
    canonical = project / "canonical.jsonl"
    for path in (sample, reference, dev):
        path.mkdir(parents=True)
    canonical.write_text("{}\n", encoding="utf-8")
    return project, sample, reference, dev, canonical


def _gate_summary() -> dict:
    return {
        "gate_config_sha256": "3" * 64,
        "minimum_exact_f1": 0.396882,
        "desirable_minimum_relaxed_f1": 0.414868,
        "relaxed_f1_is_hard_gate": False,
        "maximum_model_to_method_count": 43,
        "maximum_method_to_task_count": 25,
        "maximum_total_type_mismatch_count": 150,
        "maximum_method_semantic_sink_count": 74,
        "maximum_any_predicted_type_mismatch_sink_count": 74,
        "no_post_heldout_tuning": True,
    }


def _reference_summary() -> dict:
    return {"reference_validation_required_failed_count": 0}


def _policy_summary(project: Path) -> dict:
    return {
        "policy_validation_required_failed_count": 0,
        "policy_build_id": "scientific-entity-semantic-prompt-raw-floor-policy-fresh-v0.2c-20260901T130232963026Z",
        "selected_prediction_count": 773,
        "policy_extractor_fingerprint": "77af105871b227daa0d8c9e5501839addf229004795490a63bebe4f02672cf52",
        "policy_dir": project / "policy",
    }


def _patch_lineage(monkeypatch, project: Path) -> None:
    monkeypatch.setattr(mod, "_validate_gate", lambda **kwargs: _gate_summary())
    monkeypatch.setattr(
        mod,
        "_validate_base_evaluator",
        lambda **kwargs: {"evaluation_config_sha256": "7" * 64, "config_path": ROOT / "configs/scientific_entity_evaluation_v0.1.yaml"},
    )
    monkeypatch.setattr(mod, "_validate_reference_lineage", lambda **kwargs: _reference_summary())
    monkeypatch.setattr(mod, "_validate_policy_lineage", lambda **kwargs: _policy_summary(project))


def test_contract_freezes_exact_independent_evaluation_boundary() -> None:
    cfg = load_scientific_entity_fresh_heldout_evaluation_config(CONFIG)
    assert cfg.candidate.expected_prediction_count == 773
    assert cfg.fresh_heldout.expected_reference_mention_count == 944
    assert cfg.fresh_heldout.expected_document_count == 48
    assert cfg.candidate.title_threshold == 0.45
    assert cfg.candidate.abstract_threshold == 0.625
    assert cfg.candidate.entity_type_overrides == {}
    assert cfg.execution.plan_runs_evaluation is False
    assert cfg.safety.plan_may_expose_quality_metrics is False
    assert cfg.safety.acceptance_decision_in_this_slice is False


def test_acceptance_gate_snapshot_is_frozen_but_decision_deferred() -> None:
    cfg = load_scientific_entity_fresh_heldout_evaluation_config(CONFIG)
    gate = cfg.acceptance_gate_snapshot
    assert gate.minimum_exact_f1 == 0.396882
    assert gate.desirable_minimum_relaxed_f1 == 0.414868
    assert gate.relaxed_f1_is_hard_gate is False
    assert gate.maximum_model_to_method_count == 43
    assert gate.maximum_method_to_task_count == 25
    assert gate.maximum_total_type_mismatch_count == 150
    assert gate.maximum_method_semantic_sink_count == 74
    assert gate.maximum_any_predicted_type_mismatch_sink_count == 74
    assert gate.no_post_heldout_tuning is True
    assert gate.decision_made_in_this_slice is False


def test_plan_does_not_call_evaluator_or_expose_metrics(tmp_path: Path, monkeypatch) -> None:
    project, sample, reference, dev, canonical = _fixture_dirs(tmp_path)
    _patch_lineage(monkeypatch, project)
    called = {"evaluate": 0}
    monkeypatch.setattr(mod, "evaluate_evidence", lambda **kwargs: called.__setitem__("evaluate", called["evaluate"] + 1))
    report = mod.plan_or_execute_fresh_heldout_evaluation(
        project_root=project,
        config_path=CONFIG,
        sample_dir=sample,
        reference_dir=reference,
        development_package_dir=dev,
        canonical_path=canonical,
        execute=False,
    )
    assert called["evaluate"] == 0
    assert report["plan_runs_evaluation"] is False
    assert report["evaluation_executed"] is False
    assert report["acceptance_decision_made"] is False
    assert "exact_f1" not in report
    assert "model_to_method_count" not in report
    assert report["next_slice"] == "execute_frozen_v02c_fresh_heldout_evaluation_once"


def test_execute_calls_existing_evaluator_with_exact_frozen_inputs(tmp_path: Path, monkeypatch) -> None:
    project, sample, reference, dev, canonical = _fixture_dirs(tmp_path)
    _patch_lineage(monkeypatch, project)
    policy = project / "policy"
    policy.mkdir(parents=True)
    captured = {}

    def fake_evaluate(**kwargs):
        captured.update(kwargs)
        out = Path(kwargs["output_root"]) / kwargs["evaluation_id"]
        out.mkdir(parents=True)
        return {"phase_complete": True}

    monkeypatch.setattr(mod, "evaluate_evidence", fake_evaluate)
    monkeypatch.setattr(
        mod,
        "validate_evaluation",
        lambda **kwargs: {"required_failed_count": 0, "summary": {"total_checks": 123}},
    )
    monkeypatch.setattr(
        mod,
        "_evaluation_summary",
        lambda output_dir: {
            "evaluation_id": "scientific-entity-evaluation-fresh-v0.2c-20260901T130232963026Z",
            "document_count": 48,
            "reference_mention_count": 944,
            "prediction_mention_count": 773,
            "exact_precision": 0.4,
            "exact_recall": 0.3,
            "exact_f1": 0.342857,
            "relaxed_precision": 0.42,
            "relaxed_recall": 0.32,
            "relaxed_f1": 0.363243,
            "exact_match_count": 300,
            "relaxed_only_match_count": 12,
            "model_to_method_count": 40,
            "method_to_task_count": 20,
            "total_type_mismatch_count": 130,
            "method_semantic_sink_count": 60,
            "maximum_predicted_type_mismatch_sink_type": "method",
            "maximum_any_predicted_type_mismatch_sink_count": 60,
            "predicted_type_mismatch_sinks": {"method": 60},
        },
    )
    report = mod.plan_or_execute_fresh_heldout_evaluation(
        project_root=project,
        config_path=CONFIG,
        sample_dir=sample,
        reference_dir=reference,
        development_package_dir=dev,
        canonical_path=canonical,
        execute=True,
    )
    assert Path(captured["documents_path"]).name == "canonical_documents.sample.jsonl"
    assert Path(captured["review_manifest_path"]).name == "review_manifest.json"
    assert Path(captured["reference_mentions_path"]).name == "reference_mentions.jsonl"
    assert Path(captured["prediction_manifest_path"]).name == "manifest.json"
    assert Path(captured["prediction_mentions_path"]).name == "mentions.jsonl"
    assert captured["evaluation_id"] == "scientific-entity-evaluation-fresh-v0.2c-20260901T130232963026Z"
    assert captured["status"] == "candidate"
    assert captured["max_documents"] == 48
    assert captured["execute"] is True
    assert report["evaluation_executed"] is True
    assert report["acceptance_decision_made"] is False
    assert report["next_slice"] == "validate_frozen_v02c_fresh_heldout_evaluation"


def test_semantic_guardrails_are_derived_from_type_mismatch_errors_only() -> None:
    errors = [
        {"error_kind": "type_mismatch", "reference_entity_type": "model", "prediction_entity_type": "method"},
        {"error_kind": "type_mismatch", "reference_entity_type": "model", "prediction_entity_type": "method"},
        {"error_kind": "type_mismatch", "reference_entity_type": "method", "prediction_entity_type": "task"},
        {"error_kind": "type_mismatch", "reference_entity_type": "dataset", "prediction_entity_type": "method"},
        {"error_kind": "false_positive", "reference_entity_type": None, "prediction_entity_type": "method"},
    ]
    summary = mod.semantic_guardrails_from_errors(errors)
    assert summary["model_to_method_count"] == 2
    assert summary["method_to_task_count"] == 1
    assert summary["total_type_mismatch_count"] == 4
    assert summary["method_semantic_sink_count"] == 3
    assert summary["maximum_predicted_type_mismatch_sink_type"] == "method"
    assert summary["maximum_any_predicted_type_mismatch_sink_count"] == 3


def test_execute_refuses_existing_fixed_evaluation_output(tmp_path: Path, monkeypatch) -> None:
    project, sample, reference, dev, canonical = _fixture_dirs(tmp_path)
    _patch_lineage(monkeypatch, project)
    cfg = load_scientific_entity_fresh_heldout_evaluation_config(CONFIG)
    output = project / cfg.execution.output_root / cfg.execution.evaluation_id
    output.mkdir(parents=True)
    with pytest.raises(FileExistsError):
        mod.plan_or_execute_fresh_heldout_evaluation(
            project_root=project,
            config_path=CONFIG,
            sample_dir=sample,
            reference_dir=reference,
            development_package_dir=dev,
            canonical_path=canonical,
            execute=True,
        )


def test_test_output_path_is_isolated_from_repository_tree(tmp_path: Path) -> None:
    project, *_ = _fixture_dirs(tmp_path)
    cfg = load_scientific_entity_fresh_heldout_evaluation_config(CONFIG)
    output = (project / cfg.execution.output_root / cfg.execution.evaluation_id).resolve()
    assert output.is_relative_to(project.resolve())
    assert not output.is_relative_to(ROOT.resolve())
