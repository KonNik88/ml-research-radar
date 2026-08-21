from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.entities.build_scientific_entity_evidence_baseline import build_baseline
from scripts.entities.build_scientific_entity_manual_review_evidence import (
    ScientificEntityManualReviewBuildError,
    finalize_manual_review_evidence,
    prepare_manual_review_evidence,
)
from scripts.entities.evaluate_scientific_entity_evidence import evaluate_evidence
from radar_core.entities.scientific_entity_manual_review import (
    ScientificEntityManualReviewError,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = (
    PROJECT_ROOT / "tests" / "fixtures" / "scientific_entity_manual_review_evidence_v0_1"
)
ANNOTATIONS_PATH = FIXTURE_DIR / "completed_annotations.jsonl"
REVIEW_ID = "scientific-entity-manual-review-fixture-v0.1"
GENERATED_AT = datetime(2026, 8, 21, 12, 0, tzinfo=timezone.utc)


def _prepare(tmp_path: Path, *, execute: bool = True) -> tuple[dict[str, object], Path]:
    output_root = tmp_path / "prepared"
    report = prepare_manual_review_evidence(
        output_root=output_root,
        execute=execute,
        generated_at_utc=GENERATED_AT,
    )
    return report, output_root / REVIEW_ID


def _complete(tmp_path: Path) -> tuple[Path, Path]:
    _, prepared_dir = _prepare(tmp_path)
    completed_root = tmp_path / "completed"
    finalize_manual_review_evidence(
        prepared_dir=prepared_dir,
        annotations_path=ANNOTATIONS_PATH,
        annotator_ids=["synthetic-fixture-reviewer"],
        output_root=completed_root,
        execute=True,
        generated_at_utc=GENERATED_AT,
    )
    return prepared_dir, completed_root / REVIEW_ID


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
        newline="\n",
    )


def test_prepare_plan_is_write_free(tmp_path: Path) -> None:
    report, output_dir = _prepare(tmp_path, execute=False)

    assert report["mode"] == "plan"
    assert report["phase_complete"] is False
    assert report["sample_document_count"] == 8
    assert not output_dir.exists()


def test_prepare_execute_writes_exact_immutable_layout(tmp_path: Path) -> None:
    report, output_dir = _prepare(tmp_path)

    assert report["phase_complete"] is True
    assert report["uniform_document_count"] == 2
    assert report["type_enriched_document_count"] == 6
    assert {path.name for path in output_dir.iterdir()} == {
        "canonical_documents.sample.jsonl",
        "sample_assignments.jsonl",
        "annotation_template.jsonl",
        "manifest.json",
        "data_quality_summary.json",
        "README.md",
        "checksums.txt",
    }


def test_prepared_fixture_is_prediction_blind_and_pending(tmp_path: Path) -> None:
    _, output_dir = _prepare(tmp_path)
    rows = [
        json.loads(line)
        for line in (output_dir / "annotation_template.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]

    assert len(rows) == 16
    assert all(row["mentions"] == [] for row in rows)
    assert all(row["annotation_complete"] is False for row in rows)
    assert all(
        not {
            "prediction",
            "predictions",
            "prediction_evidence_id",
            "evidence_id",
            "extractor",
            "extractor_fingerprint",
            "confidence_kind",
            "confidence_score",
        }.intersection(row)
        for row in rows
    )


def test_sampling_is_deterministic_across_output_roots(tmp_path: Path) -> None:
    _, first = _prepare(tmp_path / "one")
    _, second = _prepare(tmp_path / "two")

    for filename in (
        "canonical_documents.sample.jsonl",
        "sample_assignments.jsonl",
        "annotation_template.jsonl",
    ):
        assert (first / filename).read_bytes() == (second / filename).read_bytes()


def test_prepare_rejects_overwrite(tmp_path: Path) -> None:
    _prepare(tmp_path)

    with pytest.raises(FileExistsError):
        _prepare(tmp_path)


def test_prepare_rejects_silent_source_truncation(tmp_path: Path) -> None:
    with pytest.raises(ScientificEntityManualReviewBuildError, match="truncation"):
        prepare_manual_review_evidence(
            output_root=tmp_path / "prepared",
            max_source_documents=7,
            execute=False,
            generated_at_utc=GENERATED_AT,
        )


def test_candidate_status_rejects_noncanonical_fixture_input(tmp_path: Path) -> None:
    with pytest.raises(ScientificEntityManualReviewBuildError, match="current canonical"):
        prepare_manual_review_evidence(
            input_path=FIXTURE_DIR / "canonical_documents.jsonl",
            output_root=tmp_path / "prepared",
            status="candidate",
            execute=False,
            generated_at_utc=GENERATED_AT,
        )


def test_finalize_plan_is_write_free(tmp_path: Path) -> None:
    _, prepared_dir = _prepare(tmp_path)
    output_root = tmp_path / "completed"

    report = finalize_manual_review_evidence(
        prepared_dir=prepared_dir,
        annotations_path=ANNOTATIONS_PATH,
        annotator_ids=["synthetic-fixture-reviewer"],
        output_root=output_root,
        execute=False,
        generated_at_utc=GENERATED_AT,
    )

    assert report["phase_complete"] is False
    assert report["reference_mention_count"] == 6
    assert report["evaluation_harness_ready"] is True
    assert not (output_root / REVIEW_ID).exists()


def test_finalize_execute_writes_harness_compatible_review(tmp_path: Path) -> None:
    _, completed_dir = _complete(tmp_path)
    review_manifest = json.loads(
        (completed_dir / "review_manifest.json").read_text(encoding="utf-8")
    )
    references = (completed_dir / "reference_mentions.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()

    assert review_manifest["status"] == "reviewed_candidate"
    assert review_manifest["prediction_blind"] is True
    assert review_manifest["review_complete"] is True
    assert review_manifest["reference_mention_count"] == 6
    assert len(references) == 6
    assert {path.name for path in completed_dir.iterdir()} == {
        "completed_annotations.jsonl",
        "review_manifest.json",
        "reference_mentions.jsonl",
        "completion_manifest.json",
        "annotation_audit_summary.json",
        "README.md",
        "checksums.txt",
    }
    completion_manifest = json.loads(
        (completed_dir / "completion_manifest.json").read_text(encoding="utf-8")
    )
    assert completion_manifest["annotations_file"] == "completed_annotations.jsonl"
    assert Path(completion_manifest["annotations_path"]).resolve() == (
        completed_dir / "completed_annotations.jsonl"
    ).resolve()
    assert b"\r" not in (completed_dir / "completed_annotations.jsonl").read_bytes()


def test_finalize_rejects_incomplete_source_field_row(tmp_path: Path) -> None:
    _, prepared_dir = _prepare(tmp_path)
    rows = [json.loads(line) for line in ANNOTATIONS_PATH.read_text(encoding="utf-8").splitlines()]
    rows[0]["annotation_complete"] = False
    annotations = tmp_path / "incomplete.jsonl"
    _write_jsonl(annotations, rows)

    with pytest.raises(ScientificEntityManualReviewError, match="explicitly complete"):
        finalize_manual_review_evidence(
            prepared_dir=prepared_dir,
            annotations_path=annotations,
            annotator_ids=["reviewer"],
            output_root=tmp_path / "completed",
            execute=False,
            generated_at_utc=GENERATED_AT,
        )


def test_finalize_rejects_changed_source_text(tmp_path: Path) -> None:
    _, prepared_dir = _prepare(tmp_path)
    rows = [json.loads(line) for line in ANNOTATIONS_PATH.read_text(encoding="utf-8").splitlines()]
    rows[0]["source_text"] = "Changed source text"
    annotations = tmp_path / "changed.jsonl"
    _write_jsonl(annotations, rows)

    with pytest.raises(ValueError):
        finalize_manual_review_evidence(
            prepared_dir=prepared_dir,
            annotations_path=annotations,
            annotator_ids=["reviewer"],
            output_root=tmp_path / "completed",
            execute=False,
            generated_at_utc=GENERATED_AT,
        )


def test_finalize_requires_unique_nonblank_annotator_ids(tmp_path: Path) -> None:
    _, prepared_dir = _prepare(tmp_path)

    with pytest.raises(ScientificEntityManualReviewBuildError, match="duplicates"):
        finalize_manual_review_evidence(
            prepared_dir=prepared_dir,
            annotations_path=ANNOTATIONS_PATH,
            annotator_ids=["reviewer", "reviewer"],
            output_root=tmp_path / "completed",
            execute=False,
            generated_at_utc=GENERATED_AT,
        )


def test_finalize_rejects_overwrite(tmp_path: Path) -> None:
    prepared_dir, completed_dir = _complete(tmp_path)
    assert completed_dir.is_dir()

    with pytest.raises(FileExistsError):
        finalize_manual_review_evidence(
            prepared_dir=prepared_dir,
            annotations_path=ANNOTATIONS_PATH,
            annotator_ids=["synthetic-fixture-reviewer"],
            output_root=tmp_path / "completed",
            execute=True,
            generated_at_utc=GENERATED_AT,
        )


def test_completed_review_feeds_existing_evaluation_harness(tmp_path: Path) -> None:
    prepared_dir, completed_dir = _complete(tmp_path)
    prediction_root = tmp_path / "predictions"
    prediction_id = "scientific-entity-manual-review-test-predictions-v0.1"
    build_baseline(
        input_path=prepared_dir / "canonical_documents.sample.jsonl",
        output_root=prediction_root,
        build_id=prediction_id,
        status="candidate",
        execute=True,
        generated_at_utc=GENERATED_AT,
    )
    prediction_dir = prediction_root / prediction_id

    report = evaluate_evidence(
        documents_path=prepared_dir / "canonical_documents.sample.jsonl",
        review_manifest_path=completed_dir / "review_manifest.json",
        reference_mentions_path=completed_dir / "reference_mentions.jsonl",
        prediction_manifest_path=prediction_dir / "manifest.json",
        prediction_mentions_path=prediction_dir / "mentions.jsonl",
        output_root=tmp_path / "evaluation",
        evaluation_id="scientific-entity-manual-review-test-evaluation-v0.1",
        status="candidate",
        execute=False,
        generated_at_utc=GENERATED_AT,
    )

    assert report["input_document_count"] == 8
    assert report["reference_mention_count"] == 6
    assert report["prediction_mention_count"] == 6
    assert report["exact_match_count"] == 6
    assert report["error_count"] == 0
    assert report["production_extractor_selected"] is False
    assert report["full_corpus_build_authorized"] is False
