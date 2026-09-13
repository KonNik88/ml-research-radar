from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from radar_core.entities.scientific_entity_typing_diagnostics import (
    prepare_typing_diagnostics,
)
from radar_core.entities.scientific_entity_typing_root_cause_review import (
    ScientificEntityTypingRootCauseReviewError,
    finalize_review,
    prepare_working_copy,
    validate_final_review,
    validate_working_copy,
)
from scripts.entities.make_scientific_entity_typing_root_cause_review import (
    main as make_main,
)
from scripts.validation.check_scientific_entity_typing_root_cause_review import (
    main as check_main,
)


ROOT = Path(__file__).resolve().parents[2]
PARENT_ID = "scientific-entity-typing-diagnostics-v0.3-test"
REVIEW_ID = "scientific-entity-typing-root-cause-review-v0.3-test"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _text_sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
        newline="\n",
    )


def _parent_diagnostics(tmp_path: Path) -> Path:
    sample = tmp_path / "sample"
    reference = tmp_path / "reference"
    prediction = tmp_path / "prediction"
    evaluation = tmp_path / "evaluation"
    decision = tmp_path / "decision"

    texts = {
        "d1": "SWTformer improves image segmentation.",
        "d2": "VAE-SSL improves anomaly detection.",
        "d3": "Transfer learning solves retrieval.",
    }
    docs = [
        {"canonical_id": doc_id, "title": text, "abstract": ""}
        for doc_id, text in texts.items()
    ]
    refs = [
        {
            "reference_id": "r1",
            "canonical_id": "d1",
            "source_field": "title",
            "char_start": 0,
            "char_end": 9,
            "entity_type": "model",
            "surface_text": "SWTformer",
            "source_text_sha256": _text_sha(texts["d1"]),
        },
        {
            "reference_id": "r2",
            "canonical_id": "d2",
            "source_field": "title",
            "char_start": 0,
            "char_end": 7,
            "entity_type": "model",
            "surface_text": "VAE-SSL",
            "source_text_sha256": _text_sha(texts["d2"]),
        },
        {
            "reference_id": "r3",
            "canonical_id": "d3",
            "source_field": "title",
            "char_start": 0,
            "char_end": 17,
            "entity_type": "method",
            "surface_text": "Transfer learning",
            "source_text_sha256": _text_sha(texts["d3"]),
        },
    ]
    preds = [
        {
            "evidence_id": "p1",
            "canonical_id": "d1",
            "source_field": "title",
            "char_start": 0,
            "char_end": 9,
            "entity_type": "method",
            "surface_text": "SWTformer",
            "source_text_sha256": _text_sha(texts["d1"]),
            "confidence_score": 0.95,
        },
        {
            "evidence_id": "p2",
            "canonical_id": "d2",
            "source_field": "title",
            "char_start": 0,
            "char_end": 7,
            "entity_type": "method",
            "surface_text": "VAE-SSL",
            "source_text_sha256": _text_sha(texts["d2"]),
            "confidence_score": 0.91,
        },
        {
            "evidence_id": "p3",
            "canonical_id": "d3",
            "source_field": "title",
            "char_start": 0,
            "char_end": 17,
            "entity_type": "task",
            "surface_text": "Transfer learning",
            "source_text_sha256": _text_sha(texts["d3"]),
            "confidence_score": 0.72,
        },
    ]
    errors = [
        {
            "error_id": "e1",
            "error_kind": "type_mismatch",
            "canonical_id": "d1",
            "source_field": "title",
            "source_text_sha256": _text_sha(texts["d1"]),
            "reference_id": "r1",
            "prediction_evidence_id": "p1",
            "reference_entity_type": "model",
            "prediction_entity_type": "method",
            "reference_char_start": 0,
            "reference_char_end": 9,
            "prediction_char_start": 0,
            "prediction_char_end": 9,
            "char_iou": 1.0,
        },
        {
            "error_id": "e2",
            "error_kind": "type_mismatch",
            "canonical_id": "d2",
            "source_field": "title",
            "source_text_sha256": _text_sha(texts["d2"]),
            "reference_id": "r2",
            "prediction_evidence_id": "p2",
            "reference_entity_type": "model",
            "prediction_entity_type": "method",
            "reference_char_start": 0,
            "reference_char_end": 7,
            "prediction_char_start": 0,
            "prediction_char_end": 7,
            "char_iou": 1.0,
        },
        {
            "error_id": "e3",
            "error_kind": "type_mismatch",
            "canonical_id": "d3",
            "source_field": "title",
            "source_text_sha256": _text_sha(texts["d3"]),
            "reference_id": "r3",
            "prediction_evidence_id": "p3",
            "reference_entity_type": "method",
            "prediction_entity_type": "task",
            "reference_char_start": 0,
            "reference_char_end": 17,
            "prediction_char_start": 0,
            "prediction_char_end": 17,
            "char_iou": 1.0,
        },
    ]

    _jsonl(sample / "canonical_documents.sample.jsonl", docs)
    _jsonl(reference / "reference_mentions.jsonl", refs)
    _jsonl(prediction / "mentions.jsonl", preds)
    _jsonl(evaluation / "errors.jsonl", errors)
    _json(
        evaluation / "manifest.json",
        {
            "evaluation_id": "eval-test",
            "canonical_input": {
                "sha256": _sha(sample / "canonical_documents.sample.jsonl")
            },
            "review": {
                "reference_mentions_sha256": _sha(
                    reference / "reference_mentions.jsonl"
                )
            },
            "prediction": {
                "mentions_sha256": _sha(prediction / "mentions.jsonl")
            },
        },
    )
    _json(
        evaluation / "metrics.json",
        {
            "document_count": 3,
            "reference_mention_count": 3,
            "prediction_mention_count": 3,
        },
    )
    _json(
        decision / "decision.json",
        {
            "decision_id": "decision-test",
            "decision": "reject_v02c_independent_acceptance",
            "heldout_becomes_consumed_development_evidence": True,
            "future_candidate_requires_new_independent_heldout": True,
        },
    )
    _json(decision / "manifest.json", {"decision_id": "decision-test"})

    parent_cfg = {
        "schema_version": "scientific_entity_typing_diagnostics_config_v0.3",
        "analysis_name": "scientific_entity_typing_diagnostics",
        "analysis_version": "v0.3",
        "expected": {
            "evaluation_id": "eval-test",
            "decision_id": "decision-test",
            "decision": "reject_v02c_independent_acceptance",
            "evaluation_manifest_sha256": _sha(evaluation / "manifest.json"),
            "evaluation_errors_sha256": _sha(evaluation / "errors.jsonl"),
            "document_count": 3,
            "reference_mention_count": 3,
            "prediction_mention_count": 3,
            "type_mismatch_count": 3,
            "model_to_method_count": 2,
            "method_to_task_count": 1,
            "method_sink_count": 2,
            "maximum_sink_type": "method",
            "maximum_sink_count": 2,
        },
        "review": {
            "context_radius_chars": 40,
            "high_confidence_thresholds": [0.8, 0.9],
            "root_cause_labels": [
                "clear_semantic_mistyping",
                "taxonomy_boundary_ambiguity",
                "annotation_reference_issue",
                "compound_or_nested_entity",
                "insufficient_context",
                "other",
            ],
            "recommended_action_labels": [
                "prompt_or_label_definition",
                "second_stage_typer",
                "ambiguity_rejection",
                "annotation_guideline",
                "span_handling",
                "no_change",
                "other",
            ],
        },
        "output": {"root": "unused"},
        "safety": {
            "analysis_only": True,
            "model_inference_allowed": False,
            "threshold_tuning_allowed": False,
            "policy_reapply_allowed": False,
            "evaluation_recompute_allowed": False,
            "canonical_truth_mutation_allowed": False,
            "production_extractor_selection_allowed": False,
            "full_corpus_build_authorized": False,
        },
        "next_steps": {
            "after_prepare": "review_typing_cases_and_assign_root_causes",
            "after_review": "design_one_bounded_v03_typing_hypothesis",
        },
    }
    parent_cfg_path = tmp_path / "parent_config.yaml"
    parent_cfg_path.write_text(
        yaml.safe_dump(parent_cfg, sort_keys=False),
        encoding="utf-8",
        newline="\n",
    )
    report = prepare_typing_diagnostics(
        project_root=ROOT,
        config_path=parent_cfg_path,
        evaluation_dir=evaluation,
        decision_dir=decision,
        sample_dir=sample,
        reference_dir=reference,
        prediction_dir=prediction,
        output_root=tmp_path / "diagnostics",
        analysis_id=PARENT_ID,
        execute=True,
        generated_at_utc="2026-09-13T00:00:00Z",
    )
    return Path(report["output_dir"])


def _review_config(tmp_path: Path, diagnostics_dir: Path) -> Path:
    summary = json.loads((diagnostics_dir / "summary.json").read_text())
    cfg = {
        "schema_version": "scientific_entity_typing_root_cause_review_config_v0.3",
        "review_name": "scientific_entity_typing_root_cause_review",
        "review_version": "v0.3",
        "parent": {
            "analysis_id": PARENT_ID,
            "evaluation_id": "eval-test",
            "decision_id": "decision-test",
            "diagnostic_manifest_sha256": _sha(diagnostics_dir / "manifest.json"),
            "diagnostic_summary_sha256": _sha(diagnostics_dir / "summary.json"),
            "typing_cases_sha256": _sha(diagnostics_dir / "typing_cases.jsonl"),
            "review_template_sha256": _sha(
                diagnostics_dir / "review_template.jsonl"
            ),
            "type_mismatch_count": 3,
            "same_span_type_mismatch_count": 3,
            "model_to_method_count": 2,
            "method_to_task_count": 1,
            "method_sink_count": 2,
        },
        "review": {
            "ambiguity_levels": ["none", "low", "medium", "high"],
            "root_cause_labels": [
                "clear_semantic_mistyping",
                "taxonomy_boundary_ambiguity",
                "annotation_reference_issue",
                "compound_or_nested_entity",
                "insufficient_context",
                "other",
            ],
            "recommended_action_labels": [
                "prompt_or_label_definition",
                "second_stage_typer",
                "ambiguity_rejection",
                "annotation_guideline",
                "span_handling",
                "no_change",
                "other",
            ],
            "note_required_for_other": True,
            "working_copy_may_be_partial": True,
            "finalization_requires_all_complete": True,
        },
        "output": {
            "working_root": str(tmp_path / "working"),
            "final_root": str(tmp_path / "final"),
        },
        "safety": {
            "human_review_only": True,
            "model_inference_allowed": False,
            "threshold_tuning_allowed": False,
            "policy_reapply_allowed": False,
            "evaluation_recompute_allowed": False,
            "canonical_truth_mutation_allowed": False,
            "production_extractor_selection_allowed": False,
            "full_corpus_build_authorized": False,
            "automatic_root_cause_assignment_allowed": False,
            "automatic_candidate_selection_allowed": False,
        },
        "next_steps": {
            "after_prepare": "complete_human_root_cause_review",
            "after_finalize": "inspect_root_cause_summary_and_select_one_bounded_v03_hypothesis",
        },
    }
    path = tmp_path / "review_config.yaml"
    path.write_text(
        yaml.safe_dump(cfg, sort_keys=False),
        encoding="utf-8",
        newline="\n",
    )
    return path


def _prepare(tmp_path: Path):
    diagnostics = _parent_diagnostics(tmp_path)
    config = _review_config(tmp_path, diagnostics)
    report = prepare_working_copy(
        project_root=ROOT,
        config_path=config,
        diagnostics_dir=diagnostics,
        review_id=REVIEW_ID,
        working_root=tmp_path / "working",
        execute=True,
        generated_at_utc="2026-09-13T00:01:00Z",
    )
    return diagnostics, config, Path(report["output_dir"])


def _complete_all(working_dir: Path) -> None:
    path = working_dir / "review_working.jsonl"
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for idx, row in enumerate(rows):
        row["review_status"] = "complete"
        row["root_cause"] = (
            "clear_semantic_mistyping"
            if idx < 2
            else "taxonomy_boundary_ambiguity"
        )
        row["reference_type_confirmed"] = True
        row["prediction_type_plausible"] = idx == 2
        row["ambiguity_level"] = "none" if idx < 2 else "medium"
        row["recommended_action"] = (
            "second_stage_typer" if idx < 2 else "ambiguity_rejection"
        )
        row["review_notes"] = None
    _jsonl(path, rows)


def test_prepare_plan_is_non_writing(tmp_path: Path) -> None:
    diagnostics = _parent_diagnostics(tmp_path)
    config = _review_config(tmp_path, diagnostics)
    report = prepare_working_copy(
        project_root=ROOT,
        config_path=config,
        diagnostics_dir=diagnostics,
        review_id=REVIEW_ID,
        working_root=tmp_path / "working",
        execute=False,
    )
    assert report["phase"] == "prepare"
    assert report["mode"] == "plan"
    assert report["type_mismatch_count"] == 3
    assert report["working_pending_count"] == 3
    assert not Path(report["output_dir"]).exists()


def test_prepare_execute_creates_enriched_mutable_working_copy(tmp_path: Path) -> None:
    _, _, working_dir = _prepare(tmp_path)
    assert sorted(p.name for p in working_dir.iterdir()) == sorted(
        ["working_manifest.json", "review_working.jsonl", "REVIEW_GUIDE.md"]
    )
    rows = [
        json.loads(line)
        for line in (working_dir / "review_working.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert len(rows) == 3
    assert rows[0]["canonical_id"] == "d1"
    assert rows[0]["source_field"] == "title"
    assert "reference_id" in rows[0]
    assert "prediction_evidence_id" in rows[0]
    assert rows[0]["same_span"] is True
    assert rows[0]["review_status"] == "pending"


def test_partial_working_copy_is_structurally_valid(tmp_path: Path) -> None:
    diagnostics, config, working_dir = _prepare(tmp_path)
    checks, summary = validate_working_copy(
        working_dir=working_dir,
        config_path=config,
        diagnostics_dir=diagnostics,
    )
    assert summary["required_failed_count"] == 0
    assert summary["complete_count"] == 0
    assert summary["pending_count"] == 3
    assert summary["review_complete"] is False
    assert all(ok for _, ok, _ in checks)


def test_completed_working_copy_becomes_finalize_ready(tmp_path: Path) -> None:
    diagnostics, config, working_dir = _prepare(tmp_path)
    _complete_all(working_dir)
    _, summary = validate_working_copy(
        working_dir=working_dir,
        config_path=config,
        diagnostics_dir=diagnostics,
    )
    assert summary["required_failed_count"] == 0
    assert summary["complete_count"] == 3
    assert summary["pending_count"] == 0
    assert summary["review_complete"] is True
    assert summary["next_slice"] == "finalize_completed_root_cause_review"


def test_factual_tampering_is_detected(tmp_path: Path) -> None:
    diagnostics, config, working_dir = _prepare(tmp_path)
    path = working_dir / "review_working.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    rows[0]["canonical_id"] = "tampered"
    _jsonl(path, rows)
    _, summary = validate_working_copy(
        working_dir=working_dir,
        config_path=config,
        diagnostics_dir=diagnostics,
    )
    assert summary["required_failed_count"] > 0


def test_pending_row_cannot_carry_partial_structured_review(tmp_path: Path) -> None:
    diagnostics, config, working_dir = _prepare(tmp_path)
    path = working_dir / "review_working.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    rows[0]["root_cause"] = "clear_semantic_mistyping"
    _jsonl(path, rows)
    _, summary = validate_working_copy(
        working_dir=working_dir,
        config_path=config,
        diagnostics_dir=diagnostics,
    )
    assert summary["required_failed_count"] > 0


def test_finalize_rejects_incomplete_working_copy(tmp_path: Path) -> None:
    diagnostics, config, working_dir = _prepare(tmp_path)
    try:
        finalize_review(
            project_root=ROOT,
            config_path=config,
            diagnostics_dir=diagnostics,
            working_dir=working_dir,
            final_root=tmp_path / "final",
            execute=False,
        )
    except ScientificEntityTypingRootCauseReviewError as exc:
        assert "review incomplete" in str(exc)
    else:
        raise AssertionError("incomplete review should not finalize")


def test_finalize_plan_then_execute_and_validate(tmp_path: Path) -> None:
    diagnostics, config, working_dir = _prepare(tmp_path)
    _complete_all(working_dir)

    plan = finalize_review(
        project_root=ROOT,
        config_path=config,
        diagnostics_dir=diagnostics,
        working_dir=working_dir,
        final_root=tmp_path / "final",
        execute=False,
    )
    assert plan["mode"] == "plan"
    assert plan["reviewed_case_count"] == 3
    assert not Path(plan["output_dir"]).exists()

    report = finalize_review(
        project_root=ROOT,
        config_path=config,
        diagnostics_dir=diagnostics,
        working_dir=working_dir,
        final_root=tmp_path / "final",
        execute=True,
        generated_at_utc="2026-09-13T00:02:00Z",
    )
    review_dir = Path(report["output_dir"])
    assert sorted(p.name for p in review_dir.iterdir()) == sorted(
        [
            "manifest.json",
            "summary.json",
            "reviewed_cases.jsonl",
            "root_cause_breakdown.json",
            "README.md",
            "checksums.txt",
        ]
    )
    breakdown = json.loads((review_dir / "root_cause_breakdown.json").read_text())
    assert breakdown["root_cause_counts"]["clear_semantic_mistyping"] == 2
    assert breakdown["root_cause_counts"]["taxonomy_boundary_ambiguity"] == 1

    checks, summary = validate_final_review(
        review_dir=review_dir,
        config_path=config,
        diagnostics_dir=diagnostics,
    )
    assert summary["required_failed_count"] == 0
    assert summary["root_causes_assigned"] is True
    assert all(ok for _, ok, _ in checks)


def test_finalize_is_one_shot(tmp_path: Path) -> None:
    diagnostics, config, working_dir = _prepare(tmp_path)
    _complete_all(working_dir)
    finalize_review(
        project_root=ROOT,
        config_path=config,
        diagnostics_dir=diagnostics,
        working_dir=working_dir,
        final_root=tmp_path / "final",
        execute=True,
    )
    try:
        finalize_review(
            project_root=ROOT,
            config_path=config,
            diagnostics_dir=diagnostics,
            working_dir=working_dir,
            final_root=tmp_path / "final",
            execute=True,
        )
    except ScientificEntityTypingRootCauseReviewError as exc:
        assert "final output already exists" in str(exc)
    else:
        raise AssertionError("second finalize execute should fail")


def test_cli_prepare_and_validator(tmp_path: Path) -> None:
    diagnostics = _parent_diagnostics(tmp_path)
    config = _review_config(tmp_path, diagnostics)
    code = make_main(
        [
            "--phase",
            "prepare",
            "--diagnostics-dir",
            str(diagnostics),
            "--config",
            str(config),
            "--review-id",
            REVIEW_ID,
            "--working-root",
            str(tmp_path / "working"),
            "--execute",
        ]
    )
    assert code == 0
    working_dir = tmp_path / "working" / REVIEW_ID
    code = check_main(
        [
            "--working-dir",
            str(working_dir),
            "--diagnostics-dir",
            str(diagnostics),
            "--config",
            str(config),
            "--strict",
        ]
    )
    assert code == 0
