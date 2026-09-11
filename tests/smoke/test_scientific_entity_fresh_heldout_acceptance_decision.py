from __future__ import annotations

from pathlib import Path

import pytest

from radar_core.contracts.scientific_entity_fresh_heldout_acceptance_decision import (
    load_scientific_entity_fresh_heldout_acceptance_decision_config,
)
from radar_core.contracts.scientific_entity_fresh_heldout_gate import (
    load_scientific_entity_fresh_heldout_gate_config,
)
from radar_core.entities import scientific_entity_fresh_heldout_acceptance_decision as mod

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "scientific_entity_fresh_heldout_acceptance_decision_v0.2.yaml"
GATE = ROOT / "configs" / "scientific_entity_fresh_heldout_gate_v0.2.yaml"


def _fixture_dirs(tmp_path: Path):
    project = tmp_path / "project"
    sample = project / "sample"
    reference = project / "reference"
    development = project / "development"
    canonical = project / "canonical.jsonl"
    for path in (sample, reference, development):
        path.mkdir(parents=True)
    canonical.write_text("{}\n", encoding="utf-8")
    return project, sample, reference, development, canonical


def _evaluation_summary(**overrides) -> dict:
    payload = {
        "required_failed_count": 0,
        "candidate_id": "scientific-entity-semantic-prompt-raw-floor-extension-v0.2c",
        "sample_id": "scientific-entity-fresh-heldout-sample-v0.2-20260901T130232963026Z",
        "review_id": "scientific-entity-fresh-heldout-review-v0.2-20260901T130232963026Z",
        "evaluation_id": "scientific-entity-evaluation-fresh-v0.2c-20260901T130232963026Z",
        "document_count": 48,
        "reference_mention_count": 944,
        "prediction_mention_count": 773,
        "evaluation_executed": True,
        "acceptance_decision_made": False,
        "threshold_tuning_executed": False,
        "model_inference_executed": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "exact_f1": 0.399534,
        "relaxed_f1": 0.42516,
        "model_to_method_count": 70,
        "method_to_task_count": 15,
        "total_type_mismatch_count": 166,
        "method_semantic_sink_count": 84,
        "maximum_any_predicted_type_mismatch_sink_count": 84,
    }
    payload.update(overrides)
    return payload


def _validated_inputs() -> dict:
    return {
        "evaluation_config_path": ROOT / "configs/scientific_entity_fresh_heldout_evaluation_v0.2.yaml",
        "evaluation_config_sha256": "2" * 64,
        "evaluation_dir": ROOT / "fake-evaluation",
        "evaluation_summary": _evaluation_summary(),
        "evaluation_manifest_sha256": "3" * 64,
        "evaluation_metrics_sha256": "4" * 64,
        "evaluation_errors_sha256": "5" * 64,
        "evaluation_checksums_sha256": "6" * 64,
        "gate_config_path": GATE,
        "gate_config_sha256": "7" * 64,
        "gate": load_scientific_entity_fresh_heldout_gate_config(GATE),
    }


def _patch_inputs(monkeypatch) -> None:
    monkeypatch.setattr(mod, "_validated_inputs", lambda **kwargs: _validated_inputs())


def test_contract_freezes_exact_decision_lineage_and_one_shot_boundary() -> None:
    cfg = load_scientific_entity_fresh_heldout_acceptance_decision_config(CONFIG)
    assert cfg.candidate.expected_document_count == 48
    assert cfg.candidate.expected_reference_mention_count == 944
    assert cfg.candidate.expected_prediction_count == 773
    assert cfg.evaluation.evaluation_id == "scientific-entity-evaluation-fresh-v0.2c-20260901T130232963026Z"
    assert cfg.gate.config_semantic_sha256 == "353276e75adacf445146bdc3046fdaedc04e01588b0bbd76a11a5dc2b48a1efe"
    assert cfg.execution.one_shot_execute is True
    assert cfg.execution.plan_runs_decision is False
    assert cfg.execution.overwrite_allowed is False
    assert cfg.safety.evaluation_recomputation_allowed is False
    assert cfg.safety.threshold_tuning_allowed is False
    assert cfg.safety.gate_changes_allowed is False


def test_plan_validates_lineage_but_does_not_materialize_or_compute_decision(tmp_path: Path, monkeypatch) -> None:
    project, sample, reference, development, canonical = _fixture_dirs(tmp_path)
    _patch_inputs(monkeypatch)
    called = {"criteria": 0}

    def fail_if_called(*args, **kwargs):
        called["criteria"] += 1
        raise AssertionError("PLAN must not compute the decision")

    monkeypatch.setattr(mod, "build_acceptance_criteria", fail_if_called)
    report = mod.plan_or_execute_fresh_heldout_acceptance_decision(
        project_root=project,
        config_path=CONFIG,
        sample_dir=sample,
        reference_dir=reference,
        development_package_dir=development,
        canonical_path=canonical,
        execute=False,
    )
    assert called["criteria"] == 0
    assert report["plan_runs_decision"] is False
    assert report["decision_materialized"] is False
    assert report["evaluation_recomputed"] is False
    assert report["threshold_tuning_executed"] is False
    assert "decision" not in report
    assert not Path(report["output_dir"]).exists()
    assert report["next_slice"] == "execute_immutable_v02c_acceptance_decision_once"


def test_actual_frozen_metrics_produce_reject_with_exact_four_failed_hard_criteria() -> None:
    gate = load_scientific_entity_fresh_heldout_gate_config(GATE)
    criteria = mod.build_acceptance_criteria(_evaluation_summary(), gate)
    result = mod.build_acceptance_decision_result(
        decision_id="test-decision",
        criteria=criteria,
        gate=gate,
    )
    by_name = {row.name: row for row in criteria}
    assert by_name["minimum_exact_f1"].passed is True
    assert by_name["desirable_minimum_relaxed_f1"].passed is True
    assert by_name["maximum_method_to_task_count"].passed is True
    assert result.decision == "reject_v02c_independent_acceptance"
    assert result.failed_hard_criteria == [
        "maximum_model_to_method_count",
        "maximum_total_type_mismatch_count",
        "maximum_method_semantic_sink_count",
        "maximum_any_predicted_type_mismatch_sink_count",
    ]
    assert result.hard_criteria_count == 6
    assert result.hard_criteria_passed_count == 2
    assert result.desirable_criteria_count == 1
    assert result.desirable_criteria_passed_count == 1
    assert result.heldout_becomes_consumed_development_evidence is True
    assert result.future_candidate_requires_new_independent_heldout is True


def test_all_hard_gates_pass_produces_accept_without_promoting_to_production() -> None:
    gate = load_scientific_entity_fresh_heldout_gate_config(GATE)
    summary = _evaluation_summary(
        model_to_method_count=43,
        method_to_task_count=25,
        total_type_mismatch_count=150,
        method_semantic_sink_count=74,
        maximum_any_predicted_type_mismatch_sink_count=74,
    )
    criteria = mod.build_acceptance_criteria(summary, gate)
    result = mod.build_acceptance_decision_result(
        decision_id="test-decision",
        criteria=criteria,
        gate=gate,
    )
    assert result.decision == "accept_as_independently_validated_bounded_extractor_v0.2"
    assert result.failed_hard_criteria == []
    assert result.production_extractor_selected is False
    assert result.full_corpus_build_authorized is False


def test_execute_materializes_immutable_reject_artifact_once(tmp_path: Path, monkeypatch) -> None:
    project, sample, reference, development, canonical = _fixture_dirs(tmp_path)
    _patch_inputs(monkeypatch)
    report = mod.plan_or_execute_fresh_heldout_acceptance_decision(
        project_root=project,
        config_path=CONFIG,
        sample_dir=sample,
        reference_dir=reference,
        development_package_dir=development,
        canonical_path=canonical,
        execute=True,
    )
    output = Path(report["output_dir"])
    assert report["phase_complete"] is True
    assert report["decision_materialized"] is True
    assert report["decision"] == "reject_v02c_independent_acceptance"
    assert report["failed_hard_criteria"] == [
        "maximum_model_to_method_count",
        "maximum_total_type_mismatch_count",
        "maximum_method_semantic_sink_count",
        "maximum_any_predicted_type_mismatch_sink_count",
    ]
    assert {p.name for p in output.iterdir()} == set(mod.REQUIRED_FILES)

    with pytest.raises(FileExistsError):
        mod.plan_or_execute_fresh_heldout_acceptance_decision(
            project_root=project,
            config_path=CONFIG,
            sample_dir=sample,
            reference_dir=reference,
            development_package_dir=development,
            canonical_path=canonical,
            execute=True,
        )


def test_valid_reject_is_engineering_green_not_validator_failure(tmp_path: Path, monkeypatch) -> None:
    project, sample, reference, development, canonical = _fixture_dirs(tmp_path)
    _patch_inputs(monkeypatch)
    mod.plan_or_execute_fresh_heldout_acceptance_decision(
        project_root=project,
        config_path=CONFIG,
        sample_dir=sample,
        reference_dir=reference,
        development_package_dir=development,
        canonical_path=canonical,
        execute=True,
    )
    checks, summary = mod.validate_fresh_heldout_acceptance_decision(
        project_root=project,
        config_path=CONFIG,
        sample_dir=sample,
        reference_dir=reference,
        development_package_dir=development,
        canonical_path=canonical,
    )
    assert all(ok for _, ok, _ in checks)
    assert summary["decision"] == "reject_v02c_independent_acceptance"
    assert len(summary["failed_hard_criteria"]) == 4
    assert summary["required_failed_count"] == 0
    assert summary["next_slice"] == "close_v02c_and_begin_typing_focused_diagnostics"


def test_validator_detects_artifact_tampering(tmp_path: Path, monkeypatch) -> None:
    project, sample, reference, development, canonical = _fixture_dirs(tmp_path)
    _patch_inputs(monkeypatch)
    report = mod.plan_or_execute_fresh_heldout_acceptance_decision(
        project_root=project,
        config_path=CONFIG,
        sample_dir=sample,
        reference_dir=reference,
        development_package_dir=development,
        canonical_path=canonical,
        execute=True,
    )
    output = Path(report["output_dir"])
    with (output / "README.md").open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("tampered\n")
    checks, summary = mod.validate_fresh_heldout_acceptance_decision(
        project_root=project,
        config_path=CONFIG,
        sample_dir=sample,
        reference_dir=reference,
        development_package_dir=development,
        canonical_path=canonical,
    )
    assert any(name == "checksum::README.md" and not ok for name, ok, _ in checks)
    assert summary["required_failed_count"] >= 1


def test_test_output_path_is_isolated_from_repository_tree(tmp_path: Path) -> None:
    project, *_ = _fixture_dirs(tmp_path)
    cfg = load_scientific_entity_fresh_heldout_acceptance_decision_config(CONFIG)
    output = (project / cfg.execution.output_root / cfg.execution.decision_id).resolve()
    assert output.is_relative_to(project.resolve())
    assert not output.is_relative_to(ROOT.resolve())
