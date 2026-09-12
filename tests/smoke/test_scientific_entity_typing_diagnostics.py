from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from radar_core.entities.scientific_entity_typing_diagnostics import (
    prepare_typing_diagnostics,
    validate_typing_diagnostics,
)
from scripts.entities.make_scientific_entity_typing_diagnostics import main

ROOT = Path(__file__).resolve().parents[2]
FIXED_ID = "scientific-entity-typing-diagnostics-v0.3-test"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _text_sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def _jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8", newline="\n")


def _fixture(tmp_path: Path):
    sample = tmp_path / "sample"; reference = tmp_path / "reference"; prediction = tmp_path / "prediction"; evaluation = tmp_path / "evaluation"; decision = tmp_path / "decision"
    text1 = "SWTformer improves segmentation."
    text2 = "Contrastive learning solves retrieval."
    docs = [
        {"canonical_id": "d1", "title": text1, "abstract": "A"},
        {"canonical_id": "d2", "title": text2, "abstract": "B"},
    ]
    refs = [
        {"reference_id": "r1", "canonical_id": "d1", "source_field": "title", "char_start": 0, "char_end": 9, "entity_type": "model", "surface_text": "SWTformer", "source_text_sha256": _text_sha(text1)},
        {"reference_id": "r2", "canonical_id": "d2", "source_field": "title", "char_start": 0, "char_end": 20, "entity_type": "task", "surface_text": "Contrastive learning", "source_text_sha256": _text_sha(text2)},
    ]
    preds = [
        {"evidence_id": "p1", "canonical_id": "d1", "source_field": "title", "char_start": 0, "char_end": 9, "entity_type": "method", "surface_text": "SWTformer", "source_text_sha256": _text_sha(text1), "confidence_score": 0.95},
        {"evidence_id": "p2", "canonical_id": "d2", "source_field": "title", "char_start": 0, "char_end": 20, "entity_type": "method", "surface_text": "Contrastive learning", "source_text_sha256": _text_sha(text2), "confidence_score": 0.75},
    ]
    _jsonl(sample / "canonical_documents.sample.jsonl", docs)
    _jsonl(reference / "reference_mentions.jsonl", refs)
    _jsonl(prediction / "mentions.jsonl", preds)
    errors = [
        {"error_id": "e1", "error_kind": "type_mismatch", "canonical_id": "d1", "source_field": "title", "source_text_sha256": _text_sha(text1), "reference_id": "r1", "prediction_evidence_id": "p1", "reference_entity_type": "model", "prediction_entity_type": "method", "reference_char_start": 0, "reference_char_end": 9, "prediction_char_start": 0, "prediction_char_end": 9, "char_iou": 1.0},
        {"error_id": "e2", "error_kind": "type_mismatch", "canonical_id": "d2", "source_field": "title", "source_text_sha256": _text_sha(text2), "reference_id": "r2", "prediction_evidence_id": "p2", "reference_entity_type": "task", "prediction_entity_type": "method", "reference_char_start": 0, "reference_char_end": 20, "prediction_char_start": 0, "prediction_char_end": 20, "char_iou": 1.0},
    ]
    _jsonl(evaluation / "errors.jsonl", errors)
    manifest = {
        "evaluation_id": "eval-x",
        "canonical_input": {"sha256": _sha(sample / "canonical_documents.sample.jsonl")},
        "review": {"reference_mentions_sha256": _sha(reference / "reference_mentions.jsonl")},
        "prediction": {"mentions_sha256": _sha(prediction / "mentions.jsonl")},
    }
    _json(evaluation / "manifest.json", manifest)
    _json(evaluation / "metrics.json", {"document_count": 2, "reference_mention_count": 2, "prediction_mention_count": 2})
    _json(decision / "decision.json", {
        "decision_id": "decision-x", "decision": "reject_v02c_independent_acceptance",
        "heldout_becomes_consumed_development_evidence": True,
        "future_candidate_requires_new_independent_heldout": True,
    })
    _json(decision / "manifest.json", {"decision_id": "decision-x"})
    cfg = {
        "schema_version": "scientific_entity_typing_diagnostics_config_v0.3",
        "analysis_name": "scientific_entity_typing_diagnostics",
        "analysis_version": "v0.3",
        "expected": {
            "evaluation_id": "eval-x", "decision_id": "decision-x", "decision": "reject_v02c_independent_acceptance",
            "evaluation_manifest_sha256": _sha(evaluation / "manifest.json"), "evaluation_errors_sha256": _sha(evaluation / "errors.jsonl"),
            "document_count": 2, "reference_mention_count": 2, "prediction_mention_count": 2,
            "type_mismatch_count": 2, "model_to_method_count": 1, "method_to_task_count": 0,
            "method_sink_count": 2, "maximum_sink_type": "method", "maximum_sink_count": 2,
        },
        "review": {
            "context_radius_chars": 40, "high_confidence_thresholds": [0.8, 0.9],
            "root_cause_labels": ["clear_semantic_mistyping", "other"],
            "recommended_action_labels": ["second_stage_typer", "other"],
        },
        "output": {"root": "unused"},
        "safety": {
            "analysis_only": True, "model_inference_allowed": False, "threshold_tuning_allowed": False,
            "policy_reapply_allowed": False, "evaluation_recompute_allowed": False, "canonical_truth_mutation_allowed": False,
            "production_extractor_selection_allowed": False, "full_corpus_build_authorized": False,
        },
        "next_steps": {"after_prepare": "review_typing_cases_and_assign_root_causes", "after_review": "design_one_bounded_v03_typing_hypothesis"},
    }
    config = tmp_path / "config.yaml"
    config.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8", newline="\n")
    return evaluation, decision, sample, reference, prediction, config


def _run(tmp_path: Path, execute: bool):
    evaluation, decision, sample, reference, prediction, config = _fixture(tmp_path)
    return prepare_typing_diagnostics(
        project_root=ROOT, config_path=config, evaluation_dir=evaluation, decision_dir=decision,
        sample_dir=sample, reference_dir=reference, prediction_dir=prediction,
        output_root=tmp_path / "out", analysis_id=FIXED_ID, execute=execute,
        generated_at_utc="2026-09-12T00:00:00Z",
    )


def test_plan_is_non_writing_and_reports_expected_counts(tmp_path: Path) -> None:
    report = _run(tmp_path, execute=False)
    assert report["mode"] == "plan"
    assert report["type_mismatch_count"] == 2
    assert report["model_to_method_count"] == 1
    assert report["method_sink_count"] == 2
    assert report["root_causes_assigned"] is False
    assert not Path(report["output_dir"]).exists()


def test_execute_materializes_reviewable_package(tmp_path: Path) -> None:
    report = _run(tmp_path, execute=True)
    out = Path(report["output_dir"])
    assert sorted(p.name for p in out.iterdir()) == sorted(["manifest.json", "summary.json", "confusion_matrix.json", "typing_cases.jsonl", "review_template.jsonl", "README.md", "checksums.txt"])
    summary = json.loads((out / "summary.json").read_text())
    assert summary["same_span_type_mismatch_count"] == 2
    assert summary["high_confidence_at_0_9_count"] == 1


def test_review_template_is_prediction_visible_but_root_cause_blank(tmp_path: Path) -> None:
    report = _run(tmp_path, execute=True)
    out = Path(report["output_dir"])
    rows = [json.loads(x) for x in (out / "review_template.jsonl").read_text().splitlines() if x.strip()]
    assert rows[0]["reference_entity_type"] in {"model", "task"}
    assert all(row["root_cause"] is None for row in rows)
    assert all(row["review_status"] == "pending" for row in rows)


def test_high_confidence_semantic_error_is_preserved(tmp_path: Path) -> None:
    report = _run(tmp_path, execute=True)
    out = Path(report["output_dir"])
    rows = [json.loads(x) for x in (out / "typing_cases.jsonl").read_text().splitlines() if x.strip()]
    row = next(x for x in rows if x["confusion_pair"] == "model->method")
    assert row["prediction_confidence_score"] == 0.95
    assert row["high_confidence_at_0_9"] is True


def test_execute_is_fail_closed_when_output_exists(tmp_path: Path) -> None:
    _run(tmp_path, execute=True)
    try:
        _run(tmp_path, execute=True)
    except ValueError as exc:
        assert "output already exists" in str(exc)
    else:
        raise AssertionError("second execute should fail")


def test_decision_must_authorize_consumed_evidence(tmp_path: Path) -> None:
    evaluation, decision, sample, reference, prediction, config = _fixture(tmp_path)
    value = json.loads((decision / "decision.json").read_text())
    value["heldout_becomes_consumed_development_evidence"] = False
    _json(decision / "decision.json", value)
    try:
        prepare_typing_diagnostics(project_root=ROOT, config_path=config, evaluation_dir=evaluation, decision_dir=decision, sample_dir=sample, reference_dir=reference, prediction_dir=prediction, output_root=tmp_path / "out", analysis_id=FIXED_ID)
    except ValueError as exc:
        assert "consumed development evidence" in str(exc)
    else:
        raise AssertionError("missing consumed-evidence guard should fail")


def test_validator_recomputes_package_and_passes(tmp_path: Path) -> None:
    report = _run(tmp_path, execute=True)
    checks, summary = validate_typing_diagnostics(analysis_dir=Path(report["output_dir"]))
    assert summary["required_failed_count"] == 0
    assert all(ok for _, ok, _ in checks)


def test_validator_detects_tampering(tmp_path: Path) -> None:
    report = _run(tmp_path, execute=True)
    out = Path(report["output_dir"])
    path = out / "summary.json"
    path.write_text(path.read_text() + " ", encoding="utf-8")
    _, summary = validate_typing_diagnostics(analysis_dir=out)
    assert summary["required_failed_count"] > 0


def test_cli_plan(tmp_path: Path) -> None:
    evaluation, decision, sample, reference, prediction, config = _fixture(tmp_path)
    code = main([
        "--evaluation-dir", str(evaluation), "--decision-dir", str(decision), "--sample-dir", str(sample),
        "--reference-dir", str(reference), "--prediction-dir", str(prediction), "--config", str(config),
        "--output-root", str(tmp_path / "out"), "--analysis-id", FIXED_ID,
    ])
    assert code == 0
    assert not (tmp_path / "out" / FIXED_ID).exists()
