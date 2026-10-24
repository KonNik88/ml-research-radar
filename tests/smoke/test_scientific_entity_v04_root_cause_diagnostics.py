"""Synthetic tests for v0.4 historical-only review queue generation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from radar_core.entities.scientific_entity_v04_root_cause_diagnostics import (
    RootCauseReviewError,
    execute_root_cause_review,
    plan_root_cause_review,
)


def write_jsonl(p: Path, rows: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(tmp_path: Path) -> tuple[Path, Path]:
    er = tmp_path / "historical"
    ar = tmp_path / "reference" / "annotations.jsonl"
    c = {"audit_case_id": "title:1", "canonical_id": "paper-1", "source_field": "title", "source_text_sha256": "hash-1",
         "certain_reference_count": 1, "prediction_count": 0,
         "diagnostics": {"unmatched_gold_after_diagnosis": [{"start": 0, "end": 7, "surface": "Example", "type": "task"}],
                         "unmatched_prediction_after_diagnosis": [], "diagnosed": []}}
    d = {"audit_case_id": "abstract:2", "canonical_id": "paper-2", "source_field": "abstract", "source_text_sha256": "hash-2",
         "certain_reference_count": 1, "prediction_count": 2,
         "diagnostics": {"unmatched_gold_after_diagnosis": [],
                         "unmatched_prediction_after_diagnosis": [{"start": 7, "end": 11, "surface": "data", "type": "dataset", "id": "pred2"}],
                         "diagnosed": [{"category": "type_only_exact_span", "reference_start": 0, "reference_end": 5,
                                        "reference_surface": "Model", "reference_type": "model", "prediction_start": 0,
                                        "prediction_end": 5, "prediction_surface": "Model", "prediction_type": "method",
                                        "prediction_id": "pred1"}]}}
    anns = [
        {"audit_case_id": "title:1", "canonical_id": "paper-1", "source_field": "title", "source_text_sha256": "hash-1", "annotation_complete": True, "source_text": "Example task"},
        {"audit_case_id": "abstract:2", "canonical_id": "paper-2", "source_field": "abstract", "source_text_sha256": "hash-2", "annotation_complete": True, "source_text": "Model: data"},
    ]
    write_jsonl(er / "cases.jsonl", [c, d])
    write_jsonl(er / "selected_predictions.jsonl", [{"audit_case_id": "abstract:2", "id": i} for i in range(2)])
    (er / "summary.json").write_text("{}\n", encoding="utf-8")
    write_jsonl(ar, anns)
    manifest = {"evaluation_id": "ev-id", "reference_id": "ref-id", "evaluation_executed": True,
                "model_inference_executed": False, "production_mutated": False,
                "files": {name: sha(er / name) for name in ("cases.jsonl", "selected_predictions.jsonl", "summary.json")}}
    (er / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (er / "README.md").write_text("Synthetic 9D package\n", encoding="utf-8")
    manifest["files"]["README.md"] = sha(er / "README.md")
    (er / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (er / "checksums.txt").write_text(
        "".join(f"{sha(er / name)}  {name}\n" for name in (
            "README.md", "cases.jsonl", "manifest.json", "selected_predictions.jsonl", "summary.json"
        )), encoding="utf-8"
    )
    cfg = {"schema_version": "scientific_entity_v04_root_cause_diagnostics_config_v0.1", "review_id": "review-id",
           "evaluation_id": "ev-id", "reference_id": "ref-id", "evaluation_dir": "historical",
           "reference_annotations_path": "reference/annotations.jsonl", "output_dir": "work/review",
           "expected_reference_annotations_sha256": sha(ar), "expected_evaluation_cases": 2,
           "expected_evaluation_predictions": 2, "sampling_seed": "seed", "max_review_items_per_field": 3,
           "quotas": {"residual_fn": 1, "residual_fp": 1, "type_only_exact_span": 1,
                      "boundary_only_same_type": 0, "boundary_and_type": 0, "zero_prediction_title": 0},
           "model_inference_allowed": False, "production_prediction_file_read_allowed": False,
           "historical_evaluation_only": True, "threshold_tuning_allowed": False, "publication_authorized": False}
    config = tmp_path / "config.yaml"
    config.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return config, tmp_path


def test_plan_is_read_only(tmp_path: Path) -> None:
    config, root = fixture(tmp_path)
    result = plan_root_cause_review(config, root)
    assert result["selected_review_item_count"] == 3
    assert result["selected_by_bucket"]["zero_prediction_title"] == 0
    assert result["model_inference_executed"] is False
    assert result["full_production_predictions_read"] is False
    assert result["plan_writes_output"] is False
    assert not (root / "work").exists()


def test_execute_has_full_context_and_no_overwrite(tmp_path: Path) -> None:
    config, root = fixture(tmp_path)
    result = execute_root_cause_review(config, root)
    assert result["phase_complete"] is True
    rows = [json.loads(s) for s in (root / "work/review/review_items.jsonl").read_text(encoding="utf8").splitlines()]
    assert len(rows) == 3
    assert len({r["review_id"] for r in rows}) == 3
    assert all(r["review_status"] == "pending" and r["root_cause"] is None for r in rows)
    assert {r["source_text"] for r in rows} == {"Example task", "Model: data"}
    with pytest.raises(RootCauseReviewError, match="already exists"):
        execute_root_cause_review(config, root)


def test_deterministic_review_ids(tmp_path: Path) -> None:
    config, root = fixture(tmp_path)
    first = plan_root_cause_review(config, root)
    second = plan_root_cause_review(config, root)
    assert first == second


def test_blocks_modified_9d_cases(tmp_path: Path) -> None:
    config, root = fixture(tmp_path)
    (root / "historical/cases.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(RootCauseReviewError, match="checksum mismatch"):
        plan_root_cause_review(config, root)


def test_blocks_modified_frozen_reference(tmp_path: Path) -> None:
    config, root = fixture(tmp_path)
    with (root / "reference/annotations.jsonl").open("a", encoding="utf8") as f:
        f.write("{}\n")
    with pytest.raises(RootCauseReviewError, match="SHA mismatch"):
        plan_root_cause_review(config, root)


def test_refuses_unsafe_config(tmp_path: Path) -> None:
    config, root = fixture(tmp_path)
    cfg = yaml.safe_load(config.read_text(encoding="utf8"))
    cfg["model_inference_allowed"] = True
    config.write_text(yaml.safe_dump(cfg), encoding="utf8")
    with pytest.raises(RootCauseReviewError, match="Safety guard"):
        plan_root_cause_review(config, root)


def test_no_escape_from_repo(tmp_path: Path) -> None:
    config, root = fixture(tmp_path)
    cfg = yaml.safe_load(config.read_text(encoding="utf8"))
    cfg["output_dir"] = "../../outside"
    config.write_text(yaml.safe_dump(cfg), encoding="utf8")
    with pytest.raises(RootCauseReviewError, match="escapes repository"):
        plan_root_cause_review(config, root)


def test_insufficient_quota_is_error(tmp_path: Path) -> None:
    config, root = fixture(tmp_path)
    cfg = yaml.safe_load(config.read_text(encoding="utf8"))
    cfg["quotas"]["residual_fp"] = 100
    config.write_text(yaml.safe_dump(cfg), encoding="utf8")
    with pytest.raises(RootCauseReviewError, match="Quota residual_fp impossible"):
        plan_root_cause_review(config, root)


def test_boundary_span_validation(tmp_path: Path) -> None:
    config, root = fixture(tmp_path)
    cases = [json.loads(s) for s in (root / "historical/cases.jsonl").read_text(encoding="utf8").splitlines()]
    cases[1]["diagnostics"]["diagnosed"].append({"category": "boundary_only_same_type", "reference_start": 0, "reference_end": 5,
      "reference_surface": "Wrong", "reference_type": "model", "prediction_start": 0, "prediction_end": 5,
      "prediction_surface": "Model", "prediction_type": "model", "prediction_id": "pred1"})
    write_jsonl(root / "historical/cases.jsonl", cases)
    m = json.loads((root / "historical/manifest.json").read_text(encoding="utf8"))
    m["files"]["cases.jsonl"] = sha(root / "historical/cases.jsonl")
    (root / "historical/manifest.json").write_text(json.dumps(m), encoding="utf8")
    er = root / "historical"
    (er / "checksums.txt").write_text(
        "".join(f"{sha(er / name)}  {name}\n" for name in (
            "README.md", "cases.jsonl", "manifest.json", "selected_predictions.jsonl", "summary.json"
        )), encoding="utf8"
    )
    with pytest.raises(RootCauseReviewError, match="Non-exact reference surface"):
        plan_root_cause_review(config, root)


def test_same_evidence_not_selected_twice_in_different_buckets(tmp_path: Path) -> None:
    config, root = fixture(tmp_path)
    # The same zero-prediction title FN exists in both pools. Request it only
    # once; the other requested slot must fail rather than duplicating evidence.
    cfg = yaml.safe_load(config.read_text(encoding="utf8"))
    cfg["quotas"]["residual_fn"] = 1
    cfg["quotas"]["zero_prediction_title"] = 1
    config.write_text(yaml.safe_dump(cfg), encoding="utf8")
    with pytest.raises(RootCauseReviewError, match="Quota residual_fn impossible"):
        plan_root_cause_review(config, root)


def test_zero_prediction_title_selection(tmp_path: Path) -> None:
    config, root = fixture(tmp_path)
    cfg = yaml.safe_load(config.read_text(encoding="utf8"))
    cfg["quotas"] = {k: 0 for k in cfg["quotas"]}
    cfg["quotas"]["zero_prediction_title"] = 1
    config.write_text(yaml.safe_dump(cfg), encoding="utf8")
    r = execute_root_cause_review(config, root)
    assert r["selected_review_item_count"] == 1
    x = json.loads((root / "work/review/review_items.jsonl").read_text(encoding="utf8"))
    assert x["evidence_bucket"] == "zero_prediction_title"


def test_manifest_checksum_tampering_is_blocked(tmp_path: Path) -> None:
    config, root = fixture(tmp_path)
    (root / "historical/manifest.json").write_text("{}", encoding="utf8")
    with pytest.raises(RootCauseReviewError, match="checksum mismatch: manifest.json"):
        plan_root_cause_review(config, root)
