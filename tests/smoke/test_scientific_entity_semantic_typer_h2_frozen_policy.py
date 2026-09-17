from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from radar_core.contracts.scientific_entity_semantic_typer_candidate import (
    load_semantic_typer_config,
    semantic_typer_config_sha256,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_frozen_policy import load_h2_frozen_policy_config
from radar_core.entities.scientific_entity_semantic_typer import semantic_typer_fingerprint
from radar_core.entities.scientific_entity_semantic_typer_h2_frozen_policy import (
    ScientificEntitySemanticTyperH2FrozenPolicyError,
    apply_h2_selective_override,
    plan_or_execute_h2_frozen_policy,
    reproduce_h2_development_policy,
    validate_h2_frozen_policy,
)
from radar_core.entities.scientific_entity_semantic_typer_revision_analysis import (
    plan_or_execute_semantic_typer_revision_analysis,
)


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "scientific_entity_semantic_typer_h2_frozen_policy_v0.3.yaml"
REVISION_CONFIG = ROOT / "configs" / "scientific_entity_semantic_typer_revision_analysis_v0.3.yaml"
H1_CONFIG = ROOT / "configs" / "scientific_entity_semantic_typer_candidate_v0.3.yaml"

TYPES = ("task", "method", "dataset", "metric", "model", "domain")
BASELINE_MATRIX = {
    "task": (48, 2, 0, 0, 0, 0),
    "method": (15, 80, 0, 4, 0, 0),
    "dataset": (1, 5, 29, 0, 17, 0),
    "metric": (0, 0, 0, 25, 0, 0),
    "model": (1, 65, 1, 0, 149, 0),
    "domain": (0, 3, 7, 0, 4, 12),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _comparison_rows() -> list[dict]:
    rows: list[dict] = []
    index = 0
    method_correct_override_budget = 9
    model_method_correction_budget = 24
    low_margin_regression_budget = 10

    for reference in TYPES:
        for pred_index, count in enumerate(BASELINE_MATRIX[reference]):
            baseline = TYPES[pred_index]
            for _ in range(count):
                index += 1
                candidate = baseline
                margin = 0.2
                if reference == "model" and baseline == "method" and model_method_correction_budget:
                    candidate = "model"
                    margin = 0.2
                    model_method_correction_budget -= 1
                elif reference == "method" and baseline == "method" and method_correct_override_budget:
                    candidate = "model"
                    margin = 0.2
                    method_correct_override_budget -= 1
                elif reference == "method" and baseline == "method" and low_margin_regression_budget:
                    candidate = "model"
                    margin = 0.02
                    low_margin_regression_budget -= 1
                baseline_correct = reference == baseline
                candidate_correct = reference == candidate
                rows.append({
                    "case_id": f"case-{index:04d}",
                    "canonical_id": f"paper-{index:04d}",
                    "source_field": "abstract",
                    "reference_entity_type": reference,
                    "baseline_entity_type": baseline,
                    "candidate_entity_type": candidate,
                    "baseline_correct": baseline_correct,
                    "candidate_correct": candidate_correct,
                    "corrected_error": (not baseline_correct and candidate_correct),
                    "introduced_regression": (baseline_correct and not candidate_correct),
                    "used_baseline_fallback": False,
                    "selected_score": 0.9,
                    "score_margin": margin,
                    "root_cause": None if baseline_correct else "clear_semantic_mistyping",
                    "ambiguity_level": None if baseline_correct else "none",
                    "primary_metric_eligible": True,
                })

    assert len(rows) == 468
    for _ in range(6):
        index += 1
        rows.append({
            "case_id": f"case-{index:04d}",
            "canonical_id": f"paper-{index:04d}",
            "source_field": "abstract",
            "reference_entity_type": "domain",
            "baseline_entity_type": "domain",
            "candidate_entity_type": "domain",
            "baseline_correct": True,
            "candidate_correct": True,
            "corrected_error": False,
            "introduced_regression": False,
            "used_baseline_fallback": False,
            "selected_score": 0.9,
            "score_margin": 0.2,
            "root_cause": "annotation_reference_issue",
            "ambiguity_level": "low",
            "primary_metric_eligible": False,
        })
    assert len(rows) == 474
    return rows


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_parent_chain(tmp_path: Path) -> tuple[Path, Path, Path]:
    prediction_dir = tmp_path / "predictions"
    evaluation_dir = tmp_path / "evaluation"
    revision_dir_root = tmp_path / "revision-root"
    prediction_dir.mkdir()
    evaluation_dir.mkdir()

    h1_config = load_semantic_typer_config(H1_CONFIG)
    h1_config_sha = semantic_typer_config_sha256(h1_config)
    h1_fingerprint = semantic_typer_fingerprint(h1_config)
    prediction_id = "scientific-entity-semantic-typer-predictions-v0.3-20260916T151728352718Z"
    prediction_manifest = {
        "prediction_id": prediction_id,
        "candidate_id": "scientific-entity-semantic-typer-candidate-v0.3-h1",
        "semantic_typer_config_sha256": h1_config_sha,
        "semantic_typer_fingerprint": h1_fingerprint,
    }
    _write_json(prediction_dir / "manifest.json", prediction_manifest)
    _write_json(prediction_dir / "summary.json", {
        "prediction_id": prediction_id,
        "semantic_typer_fingerprint": h1_fingerprint,
    })
    (prediction_dir / "predictions.jsonl").write_text("{}\n", encoding="utf-8")
    (prediction_dir / "README.md").write_text("fixture\n", encoding="utf-8")
    (prediction_dir / "checksums.txt").write_text("fixture\n", encoding="utf-8")

    rows = _comparison_rows()
    evaluation_id = "scientific-entity-semantic-typer-development-evaluation-v0.3-20260916T152354530075Z"
    evaluation_manifest = {
        "evaluation_id": evaluation_id,
        "prediction_manifest_sha256": _sha256(prediction_dir / "manifest.json"),
    }
    _write_json(evaluation_dir / "manifest.json", evaluation_manifest)
    _write_json(evaluation_dir / "summary.json", {
        "case_count": 474,
        "primary_metric_eligible_count": 468,
        "corrected_errors": 51,
        "introduced_regressions": 83,
        "net_corrected_cases": -32,
        "baseline_model_to_method_count": 65,
        "typer_coverage": 0.989316,
        "candidate_id": "scientific-entity-semantic-typer-candidate-v0.3-h1",
        "prediction_id": prediction_id,
        "evaluation_id": evaluation_id,
        "decision": {"decision": "reject_candidate"},
    })
    (evaluation_dir / "case_comparison.jsonl").write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )
    _write_json(evaluation_dir / "diagnostic_slices.json", {})
    (evaluation_dir / "README.md").write_text("fixture\n", encoding="utf-8")
    (evaluation_dir / "checksums.txt").write_text("fixture\n", encoding="utf-8")

    revision_id = "scientific-entity-semantic-typer-revision-analysis-v0.3-20260916T155434556495Z"
    report = plan_or_execute_semantic_typer_revision_analysis(
        project_root=ROOT,
        config_path=REVISION_CONFIG,
        evaluation_dir=evaluation_dir,
        analysis_id=revision_id,
        output_root=revision_dir_root,
        execute=True,
        generated_at_utc=datetime(2026, 9, 16, 15, 54, 34, tzinfo=timezone.utc),
    )
    assert report["selected_threshold"] == 0.1
    revision_dir = revision_dir_root / revision_id
    return revision_dir, evaluation_dir, prediction_dir


def test_config_freezes_h2_policy_and_disables_recalibration() -> None:
    config = load_h2_frozen_policy_config(CONFIG)
    assert config.candidate.candidate_id == "scientific-entity-semantic-typer-candidate-v0.3-h2"
    assert config.policy.margin_threshold == 0.1
    assert config.policy.selected_plateau_thresholds == [0.05, 0.1, 0.15]
    assert config.safety.new_model_inference_allowed is False
    assert config.safety.policy_margin_threshold_calibration_allowed is False
    assert config.safety.future_candidate_requires_new_independent_heldout is True


def test_h2_policy_only_overrides_method_to_model_at_frozen_margin() -> None:
    config = load_h2_frozen_policy_config(CONFIG)
    final, override = apply_h2_selective_override(
        config=config, baseline_type="method", semantic_typer_type="model", score_margin=0.1
    )
    assert final.value == "model" and override is True
    final, override = apply_h2_selective_override(
        config=config, baseline_type="method", semantic_typer_type="model", score_margin=0.099
    )
    assert final.value == "method" and override is False
    final, override = apply_h2_selective_override(
        config=config, baseline_type="task", semantic_typer_type="model", score_margin=0.9
    )
    assert final.value == "task" and override is False
    final, override = apply_h2_selective_override(
        config=config, baseline_type="method", semantic_typer_type="dataset", score_margin=0.9
    )
    assert final.value == "method" and override is False


def test_development_reproduction_matches_frozen_metrics() -> None:
    config = load_h2_frozen_policy_config(CONFIG)
    reproduction = reproduce_h2_development_policy(config=config, comparisons=_comparison_rows())
    expected = config.expected_development_reproduction.model_dump(mode="json")
    assert {key: reproduction[key] for key in expected} == expected


def test_h2_freeze_plan_is_non_writing(tmp_path: Path) -> None:
    revision_dir, evaluation_dir, prediction_dir = _write_parent_chain(tmp_path)
    report = plan_or_execute_h2_frozen_policy(
        project_root=ROOT,
        config_path=CONFIG,
        revision_analysis_dir=revision_dir,
        evaluation_dir=evaluation_dir,
        prediction_dir=prediction_dir,
        freeze_id="h2-freeze-fixture",
        output_root=tmp_path / "out",
        execute=False,
    )
    assert report["phase_complete"] is False
    assert report["policy_frozen"] is False
    assert report["development_reproduction_executed"] is False
    assert report["margin_threshold"] == 0.1
    assert not (tmp_path / "out" / "h2-freeze-fixture").exists()


def test_h2_freeze_execute_and_strict_validator_roundtrip(tmp_path: Path) -> None:
    revision_dir, evaluation_dir, prediction_dir = _write_parent_chain(tmp_path)
    report = plan_or_execute_h2_frozen_policy(
        project_root=ROOT,
        config_path=CONFIG,
        revision_analysis_dir=revision_dir,
        evaluation_dir=evaluation_dir,
        prediction_dir=prediction_dir,
        freeze_id="h2-freeze-fixture",
        output_root=tmp_path / "out",
        execute=True,
        generated_at_utc=datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc),
    )
    assert report["phase_complete"] is True
    assert report["policy_frozen"] is True
    assert report["development_net_corrected_cases"] == 15
    frozen_dir = tmp_path / "out" / "h2-freeze-fixture"
    checks, summary = validate_h2_frozen_policy(
        project_root=ROOT,
        config_path=CONFIG,
        revision_analysis_dir=revision_dir,
        evaluation_dir=evaluation_dir,
        prediction_dir=prediction_dir,
        frozen_policy_dir=frozen_dir,
    )
    assert summary["required_failed_count"] == 0, [row for row in checks if not row[1]]
    assert summary["policy_frozen"] is True
    assert summary["margin_threshold"] == 0.1


def test_freeze_fails_closed_if_selected_threshold_drifts(tmp_path: Path) -> None:
    revision_dir, evaluation_dir, prediction_dir = _write_parent_chain(tmp_path)
    policy_path = revision_dir / "selected_policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    policy["threshold"] = 0.15
    _write_json(policy_path, policy)
    with pytest.raises(ScientificEntitySemanticTyperH2FrozenPolicyError):
        plan_or_execute_h2_frozen_policy(
            project_root=ROOT,
            config_path=CONFIG,
            revision_analysis_dir=revision_dir,
            evaluation_dir=evaluation_dir,
            prediction_dir=prediction_dir,
            freeze_id="h2-freeze-fixture",
            output_root=tmp_path / "out",
            execute=False,
        )
