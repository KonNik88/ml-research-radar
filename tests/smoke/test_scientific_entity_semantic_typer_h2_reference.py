from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from radar_core.contracts.scientific_entity_semantic_typer_h2_independent_acceptance_gate import (
    canonical_config_sha256 as acceptance_gate_canonical_sha256,
    load_h2_independent_acceptance_gate_config,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_reference import (
    ACCEPTANCE_GATE_CONFIG_SHA256,
    CANDIDATE_FINGERPRINT,
    CANDIDATE_ID,
    REVIEW_ID,
    SAMPLE_ID,
    SELECTED_IDS_SHA256,
    ScientificEntityH2ReferenceError,
    load_h2_reference_config,
)
from radar_core.entities import scientific_entity_semantic_typer_h2_reference as target


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "scientific_entity_semantic_typer_h2_reference_freeze_v0.3.yaml"
GATE = ROOT / "configs" / "scientific_entity_semantic_typer_h2_independent_acceptance_gate_v0.3.yaml"


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
        newline="\n",
    )


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _fixture_sample(tmp_path: Path) -> Path:
    sample_dir = tmp_path / SAMPLE_ID
    sample_dir.mkdir(parents=True)
    text = (
        "classification contrastive learning ImageNet accuracy BERT computer vision"
    )
    rows: list[dict] = []
    documents: list[dict] = []
    assignments: list[dict] = []
    for index in range(48):
        canonical_id = f"paper-{index:03d}"
        documents.append(
            {"canonical_id": canonical_id, "title": text, "abstract": text}
        )
        assignments.append({"canonical_id": canonical_id})
        for source_field in ("title", "abstract"):
            rows.append(
                {
                    "schema_version": "scientific_entity_blind_annotation_v0.1",
                    "review_id": REVIEW_ID,
                    "canonical_id": canonical_id,
                    "sample_stratum": "uniform",
                    "enrichment_entity_type": None,
                    "source_field": source_field,
                    "source_text_sha256": _sha_text(text),
                    "source_text": text,
                    "annotation_complete": False,
                    "mentions": [],
                    "reviewer_note": None,
                }
            )
    _write_jsonl(sample_dir / "annotations_working.jsonl", rows)
    _write_jsonl(sample_dir / "canonical_documents.sample.jsonl", documents)
    _write_jsonl(sample_dir / "sample_assignments.jsonl", assignments)
    (sample_dir / "manifest.json").write_text("{}\n", encoding="utf-8", newline="\n")
    (sample_dir / "exclusion_provenance.json").write_text(
        "{}\n", encoding="utf-8", newline="\n"
    )
    return sample_dir


def _complete_annotations(
    sample_dir: Path,
    output: Path,
    *,
    uncertain: bool = False,
    drop_type: str | None = None,
) -> None:
    rows = [
        json.loads(line)
        for line in (sample_dir / "annotations_working.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    phrases = {
        "task": "classification",
        "method": "contrastive learning",
        "dataset": "ImageNet",
        "metric": "accuracy",
        "model": "BERT",
        "domain": "computer vision",
    }
    for row in rows:
        row["annotation_complete"] = True
        row["mentions"] = []
        for entity_type, phrase in phrases.items():
            if entity_type == drop_type:
                continue
            start = row["source_text"].find(phrase)
            row["mentions"].append(
                {
                    "entity_type": entity_type,
                    "char_start": start,
                    "char_end": start + len(phrase),
                    "surface_text": phrase,
                    "uncertain": uncertain and entity_type == "task",
                    "reviewer_note": None,
                }
            )
    _write_jsonl(output, rows)


def _patch_parent_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    config = load_h2_reference_config(CONFIG)
    manifest = SimpleNamespace(
        sample_id=SAMPLE_ID,
        review_id=REVIEW_ID,
        candidate_id=CANDIDATE_ID,
        candidate_fingerprint_sha256=CANDIDATE_FINGERPRINT,
    )

    def fake_parent_state(**kwargs):
        return (
            config,
            manifest,
            SELECTED_IDS_SHA256,
            ACCEPTANCE_GATE_CONFIG_SHA256,
            {"required_failed_count": 0},
        )

    monkeypatch.setattr(target, "_validate_parent_state", fake_parent_state)


def test_config_freezes_h2_lineage_and_reference_adequacy() -> None:
    config = load_h2_reference_config(CONFIG)
    assert config.candidate.candidate_id == CANDIDATE_ID
    assert config.candidate.candidate_fingerprint_sha256 == CANDIDATE_FINGERPRINT
    assert config.sample.sample_id == SAMPLE_ID
    assert config.sample.review_id == REVIEW_ID
    assert config.sample.expected_document_count == 48
    assert config.sample.expected_annotation_row_count == 96
    assert config.sample.expected_consumed_union_document_count == 120
    assert config.sample.expected_consumed_union_overlap_count == 0
    assert config.annotation.minimum_reference_mentions_per_type == 20
    assert config.annotation.require_zero_unresolved_uncertain_mentions is True
    assert config.safety.h2_inference_allowed_before_reference_freeze is False
    assert config.next_steps.after_reference_freeze == "run_frozen_h2_independent_inference"
    gate = load_h2_independent_acceptance_gate_config(GATE)
    assert acceptance_gate_canonical_sha256(gate) == ACCEPTANCE_GATE_CONFIG_SHA256


def test_working_copy_plan_is_non_writing_and_prediction_blind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_parent_validation(monkeypatch)
    sample_dir = _fixture_sample(tmp_path)
    report = target.prepare_annotation_working_copy(
        project_root=ROOT,
        config_path=CONFIG,
        acceptance_gate_config_path=GATE,
        sample_dir=sample_dir,
        canonical_path=tmp_path / "canonical.jsonl",
        development_package_dir=tmp_path / "development",
        previous_heldout_sample_dir=tmp_path / "previous",
        frozen_candidate_dir=tmp_path / "frozen",
        output_root=tmp_path / "work",
        execute=False,
    )
    assert report["phase_complete"] is False
    assert report["annotation_row_count"] == 96
    assert report["prediction_blind"] is True
    assert report["candidate_predictions_visible_during_annotation"] is False
    assert report["h2_model_inference_executed"] is False
    assert report["evaluation_executed"] is False
    assert not Path(report["output_dir"]).exists()


def test_working_copy_execute_preserves_blank_sample(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_parent_validation(monkeypatch)
    sample_dir = _fixture_sample(tmp_path)
    blank_before = (sample_dir / "annotations_working.jsonl").read_bytes()
    report = target.prepare_annotation_working_copy(
        project_root=ROOT,
        config_path=CONFIG,
        acceptance_gate_config_path=GATE,
        sample_dir=sample_dir,
        canonical_path=tmp_path / "canonical.jsonl",
        development_package_dir=tmp_path / "development",
        previous_heldout_sample_dir=tmp_path / "previous",
        frozen_candidate_dir=tmp_path / "frozen",
        output_root=tmp_path / "work",
        execute=True,
    )
    output = Path(report["output_dir"])
    assert (output / "annotations_completed.jsonl").read_bytes() == blank_before
    assert (sample_dir / "annotations_working.jsonl").read_bytes() == blank_before


def test_freeze_plan_and_execute_require_complete_adequate_zero_uncertainty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_parent_validation(monkeypatch)
    sample_dir = _fixture_sample(tmp_path)
    completed = tmp_path / "annotations_completed.jsonl"
    _complete_annotations(sample_dir, completed)
    common = dict(
        project_root=ROOT,
        config_path=CONFIG,
        acceptance_gate_config_path=GATE,
        sample_dir=sample_dir,
        canonical_path=tmp_path / "canonical.jsonl",
        development_package_dir=tmp_path / "development",
        previous_heldout_sample_dir=tmp_path / "previous",
        frozen_candidate_dir=tmp_path / "frozen",
        annotations_path=completed,
        annotator_ids=["primary-reviewer"],
        output_root=tmp_path / "reference",
        generated_at_utc=datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc),
    )
    plan = target.freeze_reference_evidence(**common, execute=False)
    assert plan["phase_complete"] is False
    assert plan["reference_adequacy_passed"] is True
    assert plan["uncertain_reference_mention_count"] == 0
    assert all(value >= 20 for value in plan["reference_count_by_type"].values())
    assert plan["h2_model_inference_executed"] is False
    assert plan["evaluation_executed"] is False

    executed = target.freeze_reference_evidence(**common, execute=True)
    assert executed["phase_complete"] is True
    assert Path(executed["output_dir"]).is_dir()


def test_freeze_rejects_uncertain_reference_mentions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_parent_validation(monkeypatch)
    sample_dir = _fixture_sample(tmp_path)
    completed = tmp_path / "annotations_completed.jsonl"
    _complete_annotations(sample_dir, completed, uncertain=True)
    with pytest.raises(ScientificEntityH2ReferenceError, match="zero uncertain mentions"):
        target.freeze_reference_evidence(
            project_root=ROOT,
            config_path=CONFIG,
            acceptance_gate_config_path=GATE,
            sample_dir=sample_dir,
            canonical_path=tmp_path / "canonical.jsonl",
            development_package_dir=tmp_path / "development",
            previous_heldout_sample_dir=tmp_path / "previous",
            frozen_candidate_dir=tmp_path / "frozen",
            annotations_path=completed,
            annotator_ids=["primary-reviewer"],
            output_root=tmp_path / "reference",
            execute=False,
            generated_at_utc=datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc),
        )


def test_independent_validator_recomputes_reference_and_lineage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_parent_validation(monkeypatch)
    sample_dir = _fixture_sample(tmp_path)
    completed = tmp_path / "annotations_completed.jsonl"
    _complete_annotations(sample_dir, completed)
    report = target.freeze_reference_evidence(
        project_root=ROOT,
        config_path=CONFIG,
        acceptance_gate_config_path=GATE,
        sample_dir=sample_dir,
        canonical_path=tmp_path / "canonical.jsonl",
        development_package_dir=tmp_path / "development",
        previous_heldout_sample_dir=tmp_path / "previous",
        frozen_candidate_dir=tmp_path / "frozen",
        annotations_path=completed,
        annotator_ids=["primary-reviewer"],
        output_root=tmp_path / "reference",
        execute=True,
        generated_at_utc=datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc),
    )
    checks, summary = target.validate_frozen_reference_evidence(
        project_root=ROOT,
        config_path=CONFIG,
        acceptance_gate_config_path=GATE,
        sample_dir=sample_dir,
        canonical_path=tmp_path / "canonical.jsonl",
        development_package_dir=tmp_path / "development",
        previous_heldout_sample_dir=tmp_path / "previous",
        frozen_candidate_dir=tmp_path / "frozen",
        reference_dir=Path(report["output_dir"]),
    )
    assert all(ok for _, ok, _ in checks)
    assert summary["required_failed_count"] == 0
    assert summary["candidate_fingerprint_sha256"] == CANDIDATE_FINGERPRINT
    assert summary["independent_acceptance_gate_config_sha256"] == ACCEPTANCE_GATE_CONFIG_SHA256
    assert summary["reference_frozen"] is True
    assert summary["h2_model_inference_executed"] is False
    assert summary["evaluation_executed"] is False
    assert summary["next_slice"] == "run_frozen_h2_independent_inference"
