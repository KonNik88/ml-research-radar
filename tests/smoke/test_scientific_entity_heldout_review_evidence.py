from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from radar_core.contracts.scientific_entity_manual_review import BLIND_ANNOTATION_SCHEMA_VERSION
from radar_core.entities.scientific_entity_heldout_review import finalize_heldout_review
from scripts.validation.check_scientific_entity_heldout_review_evidence import run_validation


REVIEW_ID = "scientific-entity-heldout-review-v0.1-20260827T092900455472Z"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )


def make_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    prepared = tmp_path / "prepared" / REVIEW_ID
    prepared.mkdir(parents=True)
    documents = [
        {"canonical_id": "paper-a", "title": "Image classification with BERT", "abstract": "We report accuracy on ImageNet."},
        {"canonical_id": "paper-b", "title": "Graph learning", "abstract": "A transformer model is used for classification."},
    ]
    sample = prepared / "canonical_documents.sample.jsonl"
    write_jsonl(sample, documents)
    assignments = [
        {"schema_version": "scientific_entity_sample_assignment_v0.1", "review_id": REVIEW_ID, "canonical_id": "paper-a", "sample_stratum": "uniform", "enrichment_entity_type": None, "selection_score": "a" * 64, "stratum_rank": 1},
        {"schema_version": "scientific_entity_sample_assignment_v0.1", "review_id": REVIEW_ID, "canonical_id": "paper-b", "sample_stratum": "uniform", "enrichment_entity_type": None, "selection_score": "b" * 64, "stratum_rank": 2},
    ]
    assignment_path = prepared / "sample_assignments.jsonl"
    write_jsonl(assignment_path, assignments)
    rows = []
    for doc in documents:
        for field in ("title", "abstract"):
            text = doc[field]
            rows.append({
                "schema_version": BLIND_ANNOTATION_SCHEMA_VERSION,
                "review_id": REVIEW_ID,
                "canonical_id": doc["canonical_id"],
                "sample_stratum": "uniform",
                "enrichment_entity_type": None,
                "source_field": field,
                "source_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "source_text": text,
                "annotation_complete": False,
                "mentions": [],
                "reviewer_note": None,
            })
    blank = prepared / "annotations_working.jsonl"
    write_jsonl(blank, rows)
    completed_rows = json.loads("[" + ",".join(blank.read_text(encoding="utf-8").splitlines()) + "]")
    completed_rows[0]["annotation_complete"] = True
    completed_rows[0]["mentions"] = [{"entity_type": "task", "char_start": 0, "char_end": 20, "surface_text": "Image classification", "uncertain": False, "reviewer_note": None}]
    for row in completed_rows[1:]:
        row["annotation_complete"] = True
    completed = prepared / "annotations_completed.jsonl"
    write_jsonl(completed, completed_rows)
    (prepared / "selected_papers.tsv").write_text("canonical_id\ttitle\npaper-a\tA\npaper-b\tB\n", encoding="utf-8", newline="\n")
    prep_manifest = {
        "schema_version": "scientific_entity_heldout_preparation_manifest_v0.1",
        "review_id": REVIEW_ID,
        "generated_utc": "2026-08-27T09:29:00+00:00",
        "sampling_algorithm": "deterministic_hash_uniform_and_type_enriched_v0.1",
        "sampling_seed": "fixture",
        "canonical_input": "fixture",
        "canonical_input_sha256": "c" * 64,
        "excluded_dev_canonical_ids": [],
        "excluded_dev_document_count": 0,
        "heldout_dev_overlap_count": 0,
        "uniform_document_count": 2,
        "type_enriched_documents_per_type": 0,
        "type_enrichment_terms": {},
        "selected_document_count": 2,
        "annotation_row_count": 4,
        "prediction_blind": True,
        "annotations_initially_empty": True,
        "selected_canonical_ids": ["paper-a", "paper-b"],
        "files": {
            "annotations_working.jsonl": sha(blank),
            "sample_assignments.jsonl": sha(assignment_path),
            "canonical_documents.sample.jsonl": sha(sample),
            "selected_papers.tsv": sha(prepared / "selected_papers.tsv"),
        },
    }
    (prepared / "preparation_manifest.json").write_text(json.dumps(prep_manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    config = {
        "schema_version": "scientific_entity_heldout_review_evidence_config_v0.1",
        "review": {"review_id": REVIEW_ID, "annotation_method": "manual_adjudicated", "annotation_guideline_version": "scientific_entity_annotation_guidelines_v0.1", "annotation_passes": 1},
        "expected": {"document_count": 2, "annotation_row_count": 4, "reference_mention_count": 1, "uncertain_reference_mention_count": 0, "blank_annotations_sha256": sha(blank), "reference_count_by_type": {"task": 1, "method": 0, "dataset": 0, "metric": 0, "model": 0, "domain": 0}},
        "safety": {"prediction_blind": True, "heldout_dev_overlap_count": 0},
        "outputs": {"completed_root": str(tmp_path / "completed")},
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8", newline="\n")
    return prepared, completed, config_path


def test_plan_is_read_only_and_reports_frozen_counts(tmp_path: Path) -> None:
    prepared, completed, config = make_fixture(tmp_path)
    report = finalize_heldout_review(prepared_dir=prepared, annotations_path=completed, config_path=config, annotator_ids=["primary-reviewer"], execute=False)
    assert report["phase_complete"] is False
    assert report["document_count"] == 2
    assert report["annotation_row_count"] == 4
    assert report["reference_mention_count"] == 1
    assert not Path(report["output_dir"]).exists()


def test_execute_and_independent_validator(tmp_path: Path) -> None:
    prepared, completed, config = make_fixture(tmp_path)
    report = finalize_heldout_review(prepared_dir=prepared, annotations_path=completed, config_path=config, annotator_ids=["primary-reviewer"], execute=True)
    output = Path(report["output_dir"])
    assert output.is_dir()
    checks, summary = run_validation(output, prepared_dir=prepared, config_path=config)
    assert summary["reference_mention_count"] == 1
    assert all(check.ok for check in checks)


def test_blank_template_sha_is_fail_closed(tmp_path: Path) -> None:
    prepared, completed, config = make_fixture(tmp_path)
    with (prepared / "annotations_working.jsonl").open("a", encoding="utf-8") as handle:
        handle.write("\n")
    try:
        finalize_heldout_review(prepared_dir=prepared, annotations_path=completed, config_path=config, annotator_ids=["primary-reviewer"], execute=False)
    except Exception as exc:
        assert "Blank annotation SHA mismatch" in str(exc)
    else:
        raise AssertionError("Expected blank SHA mismatch")


def test_completed_annotations_cannot_change_source_text(tmp_path: Path) -> None:
    prepared, completed, config = make_fixture(tmp_path)
    rows = [json.loads(line) for line in completed.read_text(encoding="utf-8").splitlines()]
    rows[0]["source_text"] = rows[0]["source_text"] + " changed"
    rows[0]["source_text_sha256"] = hashlib.sha256(rows[0]["source_text"].encode("utf-8")).hexdigest()
    write_jsonl(completed, rows)
    try:
        finalize_heldout_review(prepared_dir=prepared, annotations_path=completed, config_path=config, annotator_ids=["primary-reviewer"], execute=False)
    except Exception as exc:
        assert "Annotation changed immutable field" in str(exc)
    else:
        raise AssertionError("Expected immutable source change failure")


def test_overwrite_is_forbidden(tmp_path: Path) -> None:
    prepared, completed, config = make_fixture(tmp_path)
    finalize_heldout_review(prepared_dir=prepared, annotations_path=completed, config_path=config, annotator_ids=["primary-reviewer"], execute=True)
    try:
        finalize_heldout_review(prepared_dir=prepared, annotations_path=completed, config_path=config, annotator_ids=["primary-reviewer"], execute=True)
    except FileExistsError:
        pass
    else:
        raise AssertionError("Expected immutable output overwrite failure")
