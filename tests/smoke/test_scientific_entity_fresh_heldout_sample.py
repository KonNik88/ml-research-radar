from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from radar_core.entities.scientific_entity_fresh_heldout_sample import (
    ScientificEntityFreshHeldoutSampleError,
    prepare_fresh_heldout_sample,
    validate_fresh_heldout_sample,
)


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "scientific_entity_fresh_heldout_gate_v0.2.yaml"
DEVELOPMENT_PACKAGE_ID = "scientific-entity-semantic-prompt-development-v0.2a-20260829T140201009151Z"


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    canonical = tmp_path / "canonical_documents.jsonl"
    consumed = [
        {
            "canonical_id": f"dev-{index:03d}",
            "title": f"Consumed development paper {index}",
            "abstract": "Historical development evidence.",
            "year": 2025,
        }
        for index in range(72)
    ]
    rich = (
        "classification named entity recognition machine translation "
        "contrastive learning transfer learning naive Bayes "
        "ImageNet CIFAR-10 benchmark dataset F1 score accuracy BLEU "
        "BERT transformer model language model medical imaging "
        "natural language processing computer vision"
    )
    fresh = [
        {
            "canonical_id": f"fresh-{index:03d}",
            "title": f"Fresh paper {index}: classification with BERT",
            "abstract": f"{rich}. Unique sample document {index}.",
            "year": 2026,
            "source_ids": {"arxiv": f"2609.{index:05d}"},
        }
        for index in range(220)
    ]
    _write_jsonl(canonical, consumed + fresh)

    dev_dir = tmp_path / "development" / DEVELOPMENT_PACKAGE_ID
    dev_canonical = dev_dir / "canonical_documents.jsonl"
    _write_jsonl(dev_canonical, consumed)
    dev_manifest = {
        "schema_version": "scientific_entity_semantic_prompt_development_package_v0.2a",
        "package_id": DEVELOPMENT_PACKAGE_ID,
        "combined_document_count": 72,
        "canonical_documents_file": "canonical_documents.jsonl",
        "canonical_documents_sha256": _sha(dev_canonical),
    }
    (dev_dir / "manifest.json").write_text(
        json.dumps(dev_manifest, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return canonical, dev_dir, tmp_path / "output"


def _prepare(tmp_path: Path, *, execute: bool, sample_id: str = "scientific-entity-fresh-heldout-sample-v0.2-fixture"):
    canonical, dev_dir, output_root = _fixture(tmp_path)
    report = prepare_fresh_heldout_sample(
        project_root=ROOT,
        config_path=CONFIG,
        canonical_path=canonical,
        development_package_dir=dev_dir,
        output_root=output_root,
        sample_id=sample_id,
        execute=execute,
        generated_at_utc=datetime(2026, 9, 1, 9, 30, tzinfo=timezone.utc),
    )
    return report, canonical, dev_dir, output_root


def test_plan_is_non_writing_and_excludes_all_72_consumed_documents(tmp_path: Path) -> None:
    report, _, _, _ = _prepare(tmp_path, execute=False)
    assert report["phase_complete"] is False
    assert report["excluded_development_document_count"] == 72
    assert report["excluded_development_ids_found_in_canonical"] == 72
    assert report["heldout_development_overlap_count"] == 0
    assert report["selected_document_count"] == 48
    assert report["annotation_row_count"] == 96
    assert not Path(report["output_dir"]).exists()


def test_sample_shape_is_24_uniform_plus_4_per_entity_type(tmp_path: Path) -> None:
    report, _, _, _ = _prepare(tmp_path, execute=False)
    assert report["uniform_document_count"] == 24
    assert report["type_enriched_document_count"] == 24
    assert report["type_enriched_count_by_type"] == {
        "task": 4, "method": 4, "dataset": 4, "metric": 4, "model": 4, "domain": 4,
    }


def test_execute_materializes_blank_prediction_blind_package(tmp_path: Path) -> None:
    report, _, _, _ = _prepare(tmp_path, execute=True)
    directory = Path(report["output_dir"])
    rows = [json.loads(line) for line in (directory / "annotations_working.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 96
    assert all(row["annotation_complete"] is False for row in rows)
    assert all(row["mentions"] == [] for row in rows)
    assert all(row["reviewer_note"] is None for row in rows)
    assert report["prediction_blind"] is True
    assert report["model_inference_executed"] is False
    assert report["evaluation_executed"] is False


def test_independent_validator_recomputes_exact_sample(tmp_path: Path) -> None:
    report, canonical, dev_dir, _ = _prepare(tmp_path, execute=True)
    checks, summary = validate_fresh_heldout_sample(
        project_root=ROOT,
        config_path=CONFIG,
        canonical_path=canonical,
        development_package_dir=dev_dir,
        sample_dir=Path(report["output_dir"]),
    )
    assert all(ok for _, ok, _ in checks)
    assert summary["required_failed_count"] == 0
    assert summary["heldout_development_overlap_count"] == 0


def test_selection_is_deterministic_across_different_sample_ids(tmp_path: Path) -> None:
    canonical, dev_dir, output_root = _fixture(tmp_path)
    common = dict(
        project_root=ROOT,
        config_path=CONFIG,
        canonical_path=canonical,
        development_package_dir=dev_dir,
        output_root=output_root,
        execute=False,
        generated_at_utc=datetime(2026, 9, 1, 9, 30, tzinfo=timezone.utc),
    )
    first = prepare_fresh_heldout_sample(**common, sample_id="scientific-entity-fresh-heldout-sample-v0.2-a")
    second = prepare_fresh_heldout_sample(**common, sample_id="scientific-entity-fresh-heldout-sample-v0.2-b")
    assert first["selected_canonical_ids_sha256"] == second["selected_canonical_ids_sha256"]


def test_missing_consumed_development_id_in_current_canonical_fails_closed(tmp_path: Path) -> None:
    canonical, dev_dir, output_root = _fixture(tmp_path)
    rows = [json.loads(line) for line in canonical.read_text(encoding="utf-8").splitlines()]
    _write_jsonl(canonical, [row for row in rows if row["canonical_id"] != "dev-071"])
    try:
        prepare_fresh_heldout_sample(
            project_root=ROOT,
            config_path=CONFIG,
            canonical_path=canonical,
            development_package_dir=dev_dir,
            output_root=output_root,
            sample_id="scientific-entity-fresh-heldout-sample-v0.2-missing",
            execute=False,
        )
    except ScientificEntityFreshHeldoutSampleError as exc:
        assert "does not contain all consumed development papers" in str(exc)
    else:
        raise AssertionError("Expected fail-closed exclusion error")


def test_overwrite_is_forbidden(tmp_path: Path) -> None:
    report, canonical, dev_dir, output_root = _prepare(tmp_path, execute=True)
    try:
        prepare_fresh_heldout_sample(
            project_root=ROOT,
            config_path=CONFIG,
            canonical_path=canonical,
            development_package_dir=dev_dir,
            output_root=output_root,
            sample_id=report["sample_id"],
            execute=True,
        )
    except FileExistsError:
        pass
    else:
        raise AssertionError("Expected immutable output overwrite failure")


def test_validator_detects_tampered_blank_annotation_template(tmp_path: Path) -> None:
    report, canonical, dev_dir, _ = _prepare(tmp_path, execute=True)
    directory = Path(report["output_dir"])
    annotation_path = directory / "annotations_working.jsonl"
    rows = [json.loads(line) for line in annotation_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["annotation_complete"] = True
    _write_jsonl(annotation_path, rows)
    checks, summary = validate_fresh_heldout_sample(
        project_root=ROOT,
        config_path=CONFIG,
        canonical_path=canonical,
        development_package_dir=dev_dir,
        sample_dir=directory,
    )
    assert summary["required_failed_count"] > 0
    assert any(
        name == "annotations_are_blank_prediction_blind_template" and not ok
        for name, ok, _ in checks
    )
