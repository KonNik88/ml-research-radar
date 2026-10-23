from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from radar_core.entities.scientific_entity_full_ner_coverage_audit import (
    FullNerCoverageAuditError,
    execute_full_ner_coverage_audit,
    plan_full_ner_coverage_audit,
    validate_sample_package,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")


def _setup(tmp_path: Path) -> tuple[Path, Path]:
    canonical = tmp_path / "data/analytics/reconciled/canonical_documents.jsonl"
    canonical.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for i in range(160):
        rows.append({
            "canonical_id": f"doc-{i:03d}",
            "title": f"Model method task title {i}",
            "abstract": f"This abstract {i} describes a model, a method, a dataset and a metric for a scientific domain task.",
        })
    canonical.write_text("".join(json.dumps(x, sort_keys=True) + "\n" for x in rows), encoding="utf-8", newline="\n")

    latest = tmp_path / "data/entities/scientific_entity_production/v0.3/latest.json"
    _write_json(latest, {
        "state": "trusted_latest",
        "candidate_build_id": "candidate-build",
        "candidate_final_mentions_sha256": "f" * 64,
        "canonical_sha256": _sha(canonical),
    })

    closure_dir = tmp_path / "data/entities/closure"
    _write_json(closure_dir / "closure.json", {
        "closure_id": "closure-id",
        "h2_v03_lifecycle_closed": True,
        "future_full_ner_coverage_audit_requires_fresh_prediction_blind_sample": True,
        "future_h2_v03_tuning_allowed": False,
    })

    old = tmp_path / "data/entities/scientific_entity_fresh_heldout_sample/v0.1/x/sample.jsonl"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_text(json.dumps({"canonical_id": "doc-000"}) + "\n", encoding="utf-8", newline="\n")

    config = {
        "schema_version": "scientific_entity_full_ner_coverage_audit_config_v0.1",
        "audit_id": "audit-id",
        "sample_version": "v0.1",
        "sampling_seed": "seed",
        "canonical_path": "data/analytics/reconciled/canonical_documents.jsonl",
        "canonical_sha256": _sha(canonical),
        "canonical_document_count": 160,
        "production_latest_pointer_path": "data/entities/scientific_entity_production/v0.3/latest.json",
        "expected_trusted_candidate_build_id": "candidate-build",
        "expected_trusted_final_mentions_sha256": "f" * 64,
        "closure_dir": "data/entities/closure",
        "expected_closure_id": "closure-id",
        "sample_counts": {"title": 60, "abstract": 60},
        "historical_exclusion_roots": ["data/entities/scientific_entity_fresh_heldout_sample"],
        "sample_output_root": "data/entities/scientific_entity_full_ner_coverage_audit/v0.1",
        "annotation_work_root": "data/entities/scientific_entity_full_ner_coverage_annotation_work/v0.1",
        "prediction_blind": True,
        "production_prediction_file_read": False,
        "annotation_taxonomy": ["task", "method", "dataset", "metric", "model", "domain"],
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8", newline="\n")
    guide = tmp_path / "guide.md"
    guide.write_text("# guide\n", encoding="utf-8", newline="\n")
    return config_path, guide


def test_plan_is_read_only(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path)
    report = plan_full_ner_coverage_audit(config, tmp_path)
    assert report["mode"] == "plan"
    assert report["plan_writes_output"] is False
    assert report["sample_total_count"] == 120
    assert report["sample_output_exists"] is False


def test_plan_is_prediction_blind(tmp_path: Path) -> None:
    config, _ = _setup(tmp_path)
    report = plan_full_ner_coverage_audit(config, tmp_path)
    assert report["prediction_blind"] is True
    assert report["production_prediction_file_read"] is False


def test_execute_creates_sample_and_workspace(tmp_path: Path) -> None:
    config, guide = _setup(tmp_path)
    report = execute_full_ner_coverage_audit(config, tmp_path, guide)
    assert report["annotation_ready"] is True
    assert Path(report["annotation_file"]).exists()
    assert Path(report["annotation_guide"]).exists()


def test_execute_has_exact_field_counts(tmp_path: Path) -> None:
    config, guide = _setup(tmp_path)
    report = execute_full_ner_coverage_audit(config, tmp_path, guide)
    assert report["sample_title_count"] == 60
    assert report["sample_abstract_count"] == 60
    assert report["sample_total_count"] == 120


def test_historical_id_is_excluded(tmp_path: Path) -> None:
    config, guide = _setup(tmp_path)
    report = execute_full_ner_coverage_audit(config, tmp_path, guide)
    sample = Path(report["sample_dir"]) / "audit_fields.jsonl"
    ids = {json.loads(line)["canonical_id"] for line in sample.read_text(encoding="utf-8").splitlines()}
    assert "doc-000" not in ids


def test_sample_contains_no_prediction_metadata(tmp_path: Path) -> None:
    config, guide = _setup(tmp_path)
    report = execute_full_ner_coverage_audit(config, tmp_path, guide)
    sample = Path(report["sample_dir"]) / "audit_fields.jsonl"
    for line in sample.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        assert set(row) == {"schema_version", "audit_id", "audit_case_id", "canonical_id", "source_field", "source_text", "source_text_sha256"}


def test_execute_is_one_shot(tmp_path: Path) -> None:
    config, guide = _setup(tmp_path)
    execute_full_ner_coverage_audit(config, tmp_path, guide)
    try:
        execute_full_ner_coverage_audit(config, tmp_path, guide)
    except FullNerCoverageAuditError:
        pass
    else:
        raise AssertionError("second execute should fail")


def test_strict_validation_recomputes_sample(tmp_path: Path) -> None:
    config, guide = _setup(tmp_path)
    execute_full_ner_coverage_audit(config, tmp_path, guide)
    report = validate_sample_package(config, tmp_path, guide)
    assert report["sample_validated"] is True
    assert report["required_failed_count"] == 0
