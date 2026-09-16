from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from radar_core.contracts.scientific_entity_semantic_typer_revision_analysis import load_revision_analysis_config
from radar_core.entities.scientific_entity_semantic_typer_revision_analysis import (
    ScientificEntitySemanticTyperRevisionAnalysisError,
    analyze_revision,
    plan_or_execute_semantic_typer_revision_analysis,
    validate_semantic_typer_revision_analysis,
)

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "scientific_entity_semantic_typer_revision_analysis_v0.3.yaml"


def _row(index: int, *, ref: str, baseline: str, candidate: str, margin: float | None, eligible: bool = True) -> dict:
    baseline_correct = ref == baseline
    candidate_correct = ref == candidate
    return {
        "case_id": f"case-{index:04d}",
        "canonical_id": f"paper-{index:04d}",
        "source_field": "abstract",
        "reference_entity_type": ref,
        "baseline_entity_type": baseline,
        "candidate_entity_type": candidate,
        "baseline_correct": baseline_correct,
        "candidate_correct": candidate_correct,
        "corrected_error": (not baseline_correct and candidate_correct),
        "introduced_regression": (baseline_correct and not candidate_correct),
        "used_baseline_fallback": False,
        "selected_score": 0.9 if margin is not None else None,
        "score_margin": margin,
        "root_cause": None if baseline_correct else "clear_semantic_mistyping",
        "ambiguity_level": None if baseline_correct else "none",
        "primary_metric_eligible": eligible,
    }


def _fixture_rows() -> list[dict]:
    rows: list[dict] = []
    i = 0

    # 29 useful method->model H1 changes. Margin distribution makes 0.05, 0.10,
    # and 0.15 all pass while 0.00 fails the regression guardrail.
    correction_margins = [0.02] * 2 + [0.07] * 3 + [0.12] * 8 + [0.17] * 8 + [0.25] * 8
    for margin in correction_margins:
        i += 1
        rows.append(_row(i, ref="model", baseline="method", candidate="model", margin=margin))

    # Remaining 36 model->method baseline errors are not directly fixed by H1.
    for _ in range(36):
        i += 1
        rows.append(_row(i, ref="model", baseline="method", candidate="method", margin=0.2))

    # 20 harmful method->model changes.
    regression_margins = [0.02] * 10 + [0.07] * 2 + [0.12] * 3 + [0.17] * 1 + [0.25] * 4
    for margin in regression_margins:
        i += 1
        rows.append(_row(i, ref="method", baseline="method", candidate="model", margin=margin))

    # Other H1 corrections to reach 51 total.
    for _ in range(22):
        i += 1
        rows.append(_row(i, ref="dataset", baseline="model", candidate="dataset", margin=0.2))

    # Other H1 regressions to reach 83 total.
    for _ in range(63):
        i += 1
        rows.append(_row(i, ref="model", baseline="model", candidate="dataset", margin=0.1))

    # 20 wrong->wrong H1 transitions.
    for _ in range(20):
        i += 1
        rows.append(_row(i, ref="domain", baseline="dataset", candidate="model", margin=0.15))

    # Remaining baseline-wrong unchanged cases: 125 baseline wrong total.
    current_wrong = sum(not row["baseline_correct"] for row in rows)
    for _ in range(125 - current_wrong):
        i += 1
        rows.append(_row(i, ref="task", baseline="method", candidate="method", margin=0.1))

    # Remaining baseline-correct unchanged cases: 343 baseline correct total.
    current_correct = sum(row["baseline_correct"] for row in rows)
    for _ in range(343 - current_correct):
        i += 1
        rows.append(_row(i, ref="metric", baseline="metric", candidate="metric", margin=0.3))

    assert len(rows) == 468
    assert sum(row["baseline_correct"] for row in rows) == 343
    assert sum(row["corrected_error"] for row in rows) == 51
    assert sum(row["introduced_regression"] for row in rows) == 83
    assert sum(row["reference_entity_type"] == "model" and row["baseline_entity_type"] == "method" for row in rows) == 65

    # Six excluded reference-issue rows.
    for _ in range(6):
        i += 1
        rows.append(_row(i, ref="domain", baseline="domain", candidate="domain", margin=0.2, eligible=False))
    assert len(rows) == 474
    return rows


def _parent_summary() -> dict:
    return {
        "case_count": 474,
        "primary_metric_eligible_count": 468,
        "corrected_errors": 51,
        "introduced_regressions": 83,
        "net_corrected_cases": -32,
        "baseline_model_to_method_count": 65,
        "typer_coverage": 0.989316,
        "candidate_id": "scientific-entity-semantic-typer-candidate-v0.3-h1",
        "evaluation_id": "scientific-entity-semantic-typer-development-evaluation-v0.3-fixture",
        "decision": {"decision": "reject_candidate"},
    }


def _write_parent(path: Path) -> None:
    path.mkdir(parents=True)
    rows = _fixture_rows()
    (path / "summary.json").write_text(json.dumps(_parent_summary()), encoding="utf-8")
    (path / "case_comparison.jsonl").write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8"
    )
    (path / "manifest.json").write_text(json.dumps({"fixture": True}), encoding="utf-8")
    (path / "diagnostic_slices.json").write_text("{}", encoding="utf-8")
    (path / "README.md").write_text("fixture\n", encoding="utf-8")
    (path / "checksums.txt").write_text("fixture\n", encoding="utf-8")


def test_config_freezes_one_selective_override_policy_family() -> None:
    config = load_revision_analysis_config(CONFIG)
    assert config.policy_family.baseline_type == "method"
    assert config.policy_family.semantic_typer_type == "model"
    assert config.policy_family.selection_rule == "lowest_interior_threshold_in_three_point_all_gate_pass_plateau"
    assert config.safety.new_model_inference_allowed is False
    assert config.safety.policy_margin_threshold_calibration_allowed is True


def test_revision_plan_is_non_writing_and_hides_selected_threshold(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    _write_parent(parent)
    report = plan_or_execute_semantic_typer_revision_analysis(
        project_root=ROOT,
        config_path=CONFIG,
        evaluation_dir=parent,
        analysis_id="revision-fixture",
        output_root=tmp_path / "out",
        execute=False,
    )
    assert report["phase_complete"] is False
    assert report["revision_metrics_exposed_in_plan"] is False
    assert report["policy_selected"] is False
    assert "selected_threshold" not in report
    assert not (tmp_path / "out" / "revision-fixture").exists()


def test_revision_analysis_selects_lowest_interior_stable_plateau_threshold() -> None:
    config = load_revision_analysis_config(CONFIG)
    summary, outcomes, sweep, extra = analyze_revision(_parent_summary(), _fixture_rows(), config)
    assert summary["selected_policy_status"] == "selected"
    assert summary["selected_threshold"] == 0.1
    assert summary["selected_plateau_thresholds"] == [0.05, 0.1, 0.15]
    selected = summary["selected_policy_metrics"]
    assert selected["all_reused_gates_passed"] is True
    assert selected["net_corrected_cases"] > 0
    assert selected["regression_rate"] <= 0.05
    assert len(outcomes) == 468
    assert extra["selected_policy"]["status"] == "selected"
    rows = {row["threshold"]: row for row in sweep["rows"]}
    assert rows[0.0]["all_reused_gates_passed"] is False
    assert rows[0.05]["all_reused_gates_passed"] is True
    assert rows[0.1]["stable_plateau_member"] is True


def test_revision_execute_and_strict_validator_roundtrip(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    _write_parent(parent)
    report = plan_or_execute_semantic_typer_revision_analysis(
        project_root=ROOT,
        config_path=CONFIG,
        evaluation_dir=parent,
        analysis_id="revision-fixture",
        output_root=tmp_path / "out",
        execute=True,
        generated_at_utc=datetime(2026, 9, 16, tzinfo=timezone.utc),
    )
    assert report["phase_complete"] is True
    assert report["policy_selected"] is True
    assert report["selected_threshold"] == 0.1
    analysis_dir = tmp_path / "out" / "revision-fixture"
    checks, summary = validate_semantic_typer_revision_analysis(
        project_root=ROOT,
        config_path=CONFIG,
        evaluation_dir=parent,
        analysis_dir=analysis_dir,
    )
    assert summary["required_failed_count"] == 0, [row for row in checks if not row[1]]
    assert summary["selected_threshold"] == 0.1


def test_parent_h1_drift_fails_closed() -> None:
    config = load_revision_analysis_config(CONFIG)
    summary = _parent_summary()
    summary["introduced_regressions"] = 82
    with pytest.raises(ScientificEntitySemanticTyperRevisionAnalysisError):
        analyze_revision(summary, _fixture_rows(), config)
