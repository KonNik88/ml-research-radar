from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from radar_core.contracts.scientific_entity_fresh_heldout_reference import (
    load_scientific_entity_fresh_heldout_reference_config,
)
from radar_core.entities.scientific_entity_fresh_heldout_reference import (
    ScientificEntityFreshHeldoutReferenceError,
    freeze_reference_evidence,
    prepare_annotation_working_copy,
    validate_frozen_reference_evidence,
)
from radar_core.entities.scientific_entity_fresh_heldout_sample import (
    prepare_fresh_heldout_sample,
)


ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "configs" / "scientific_entity_fresh_heldout_gate_v0.2.yaml"
CONFIG = ROOT / "configs" / "scientific_entity_fresh_heldout_reference_freeze_v0.2.yaml"
DEV_PACKAGE_ID = "scientific-entity-semantic-prompt-development-v0.2a-20260829T140201009151Z"
FIXTURE_SAMPLE_ID = "scientific-entity-fresh-heldout-sample-v0.2-20260901T130232963026Z"


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


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path):
    consumed = [
        {
            "canonical_id": f"dev-{index:03d}",
            "title": f"Consumed paper {index}",
            "abstract": "Historical development evidence.",
            "year": 2025,
        }
        for index in range(72)
    ]
    rich = (
        "classification contrastive learning ImageNet accuracy BERT computer vision "
        "named entity recognition transfer learning CIFAR-10 F1 score transformer model "
        "natural language processing machine translation naive Bayes benchmark dataset BLEU "
        "language model medical imaging"
    )
    fresh = [
        {
            "canonical_id": f"fresh-{index:03d}",
            "title": f"Fresh {index}: {rich}",
            "abstract": f"{rich}. Unique document {index}.",
            "year": 2026,
        }
        for index in range(240)
    ]
    canonical = tmp_path / "canonical_documents.jsonl"
    _write_jsonl(canonical, consumed + fresh)

    dev_dir = tmp_path / "development" / DEV_PACKAGE_ID
    dev_canonical = dev_dir / "canonical_documents.jsonl"
    _write_jsonl(dev_canonical, consumed)
    (dev_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "scientific_entity_semantic_prompt_development_package_v0.2a",
                "package_id": DEV_PACKAGE_ID,
                "combined_document_count": 72,
                "canonical_documents_file": "canonical_documents.jsonl",
                "canonical_documents_sha256": _sha(dev_canonical),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    # The production reference-freeze config binds the real selected-ID SHA. For the
    # fixture, create the deterministic sample then rewrite only this config copy's SHA
    # in a temporary config so the same identity checks are exercised.
    sample_root = tmp_path / "sample_root"
    sample_report = prepare_fresh_heldout_sample(
        project_root=ROOT,
        config_path=GATE,
        canonical_path=canonical,
        development_package_dir=dev_dir,
        output_root=sample_root,
        sample_id=FIXTURE_SAMPLE_ID,
        execute=True,
        generated_at_utc=datetime(2026, 9, 1, 13, 2, 32, 963026, tzinfo=timezone.utc),
    )
    sample_dir = Path(sample_report["output_dir"])

    cfg = CONFIG.read_text(encoding="utf-8")
    cfg = cfg.replace(
        "0c4bf55fa47192d8523a5ccd0d89b3326562ff6b464f108d330d87286feb7d7a",
        sample_report["selected_canonical_ids_sha256"],
    )
    fixture_config = tmp_path / "reference_config.yaml"
    fixture_config.write_text(cfg, encoding="utf-8", newline="\n")
    return canonical, dev_dir, sample_dir, fixture_config


def _complete_annotations(sample_dir: Path, output: Path, *, uncertain: bool = False, drop_type: str | None = None) -> None:
    rows = [
        json.loads(line)
        for line in (sample_dir / "annotations_working.jsonl").read_text(encoding="utf-8").splitlines()
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
            assert start >= 0
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


def test_config_freezes_real_sample_identity_and_reference_adequacy() -> None:
    config = load_scientific_entity_fresh_heldout_reference_config(CONFIG)
    assert config.sample.sample_id == FIXTURE_SAMPLE_ID
    assert config.sample.expected_document_count == 48
    assert config.sample.expected_annotation_row_count == 96
    assert config.sample.expected_development_overlap_count == 0
    assert config.annotation.minimum_reference_mentions_per_type == 20
    assert config.annotation.require_zero_unresolved_uncertain_mentions is True
    assert config.safety.candidate_inference_allowed_before_reference_freeze is False


def test_working_copy_plan_is_non_writing_and_prediction_blind(tmp_path: Path) -> None:
    canonical, dev_dir, sample_dir, config = _fixture(tmp_path)
    report = prepare_annotation_working_copy(
        project_root=ROOT,
        config_path=config,
        sample_dir=sample_dir,
        canonical_path=canonical,
        development_package_dir=dev_dir,
        output_root=tmp_path / "work",
        execute=False,
    )
    assert report["phase_complete"] is False
    assert report["annotation_row_count"] == 96
    assert report["prediction_blind"] is True
    assert report["model_inference_executed"] is False
    assert not Path(report["output_dir"]).exists()


def test_working_copy_execute_preserves_immutable_sample(tmp_path: Path) -> None:
    canonical, dev_dir, sample_dir, config = _fixture(tmp_path)
    blank_sha_before = _sha(sample_dir / "annotations_working.jsonl")
    report = prepare_annotation_working_copy(
        project_root=ROOT,
        config_path=config,
        sample_dir=sample_dir,
        canonical_path=canonical,
        development_package_dir=dev_dir,
        output_root=tmp_path / "work",
        execute=True,
    )
    output = Path(report["output_dir"])
    assert (output / "annotations_completed.jsonl").read_bytes() == (sample_dir / "annotations_working.jsonl").read_bytes()
    assert _sha(sample_dir / "annotations_working.jsonl") == blank_sha_before


def test_freeze_plan_and_execute_require_complete_adequate_zero_uncertainty(tmp_path: Path) -> None:
    canonical, dev_dir, sample_dir, config = _fixture(tmp_path)
    completed = tmp_path / "annotations_completed.jsonl"
    _complete_annotations(sample_dir, completed)
    plan = freeze_reference_evidence(
        project_root=ROOT,
        config_path=config,
        sample_dir=sample_dir,
        canonical_path=canonical,
        development_package_dir=dev_dir,
        annotations_path=completed,
        annotator_ids=["primary-reviewer"],
        output_root=tmp_path / "frozen",
        execute=False,
        generated_at_utc=datetime(2026, 9, 2, 8, 0, tzinfo=timezone.utc),
    )
    assert plan["phase_complete"] is False
    assert plan["reference_adequacy_passed"] is True
    assert plan["uncertain_reference_mention_count"] == 0
    assert all(value >= 20 for value in plan["reference_count_by_type"].values())
    assert not Path(plan["output_dir"]).exists()

    executed = freeze_reference_evidence(
        project_root=ROOT,
        config_path=config,
        sample_dir=sample_dir,
        canonical_path=canonical,
        development_package_dir=dev_dir,
        annotations_path=completed,
        annotator_ids=["primary-reviewer"],
        output_root=tmp_path / "frozen",
        execute=True,
        generated_at_utc=datetime(2026, 9, 2, 8, 0, tzinfo=timezone.utc),
    )
    assert executed["phase_complete"] is True
    assert Path(executed["output_dir"]).is_dir()


def test_independent_validator_recomputes_references_and_sample_lineage(tmp_path: Path) -> None:
    canonical, dev_dir, sample_dir, config = _fixture(tmp_path)
    completed = tmp_path / "annotations_completed.jsonl"
    _complete_annotations(sample_dir, completed)
    report = freeze_reference_evidence(
        project_root=ROOT,
        config_path=config,
        sample_dir=sample_dir,
        canonical_path=canonical,
        development_package_dir=dev_dir,
        annotations_path=completed,
        annotator_ids=["primary-reviewer"],
        output_root=tmp_path / "frozen",
        execute=True,
        generated_at_utc=datetime(2026, 9, 2, 8, 0, tzinfo=timezone.utc),
    )
    checks, summary = validate_frozen_reference_evidence(
        project_root=ROOT,
        config_path=config,
        sample_dir=sample_dir,
        canonical_path=canonical,
        development_package_dir=dev_dir,
        reference_dir=Path(report["output_dir"]),
    )
    assert all(ok for _, ok, _ in checks)
    assert summary["required_failed_count"] == 0
    assert summary["reference_adequacy_passed"] is True


def test_uncertain_mentions_fail_closed(tmp_path: Path) -> None:
    canonical, dev_dir, sample_dir, config = _fixture(tmp_path)
    completed = tmp_path / "annotations_completed.jsonl"
    _complete_annotations(sample_dir, completed, uncertain=True)
    try:
        freeze_reference_evidence(
            project_root=ROOT,
            config_path=config,
            sample_dir=sample_dir,
            canonical_path=canonical,
            development_package_dir=dev_dir,
            annotations_path=completed,
            annotator_ids=["primary-reviewer"],
            output_root=tmp_path / "frozen",
            execute=False,
        )
    except ScientificEntityFreshHeldoutReferenceError as exc:
        assert "zero uncertain mentions" in str(exc)
    else:
        raise AssertionError("Expected zero-uncertainty fail-closed error")


def test_reference_adequacy_below_20_for_one_type_fails_closed(tmp_path: Path) -> None:
    canonical, dev_dir, sample_dir, config = _fixture(tmp_path)
    completed = tmp_path / "annotations_completed.jsonl"
    _complete_annotations(sample_dir, completed, drop_type="domain")
    try:
        freeze_reference_evidence(
            project_root=ROOT,
            config_path=config,
            sample_dir=sample_dir,
            canonical_path=canonical,
            development_package_dir=dev_dir,
            annotations_path=completed,
            annotator_ids=["primary-reviewer"],
            output_root=tmp_path / "frozen",
            execute=False,
        )
    except ScientificEntityFreshHeldoutReferenceError as exc:
        assert "reference adequacy failed" in str(exc)
        assert "domain" in str(exc)
    else:
        raise AssertionError("Expected reference adequacy failure")


def test_completed_annotations_cannot_mutate_source_text(tmp_path: Path) -> None:
    canonical, dev_dir, sample_dir, config = _fixture(tmp_path)
    completed = tmp_path / "annotations_completed.jsonl"
    _complete_annotations(sample_dir, completed)
    rows = [json.loads(line) for line in completed.read_text(encoding="utf-8").splitlines()]
    rows[0]["source_text"] = rows[0]["source_text"] + " changed"
    rows[0]["source_text_sha256"] = hashlib.sha256(rows[0]["source_text"].encode("utf-8")).hexdigest()
    _write_jsonl(completed, rows)
    try:
        freeze_reference_evidence(
            project_root=ROOT,
            config_path=config,
            sample_dir=sample_dir,
            canonical_path=canonical,
            development_package_dir=dev_dir,
            annotations_path=completed,
            annotator_ids=["primary-reviewer"],
            output_root=tmp_path / "frozen",
            execute=False,
        )
    except Exception as exc:
        assert "immutable field source_text" in str(exc)
    else:
        raise AssertionError("Expected immutable source mutation failure")


def test_frozen_reference_overwrite_is_forbidden(tmp_path: Path) -> None:
    canonical, dev_dir, sample_dir, config = _fixture(tmp_path)
    completed = tmp_path / "annotations_completed.jsonl"
    _complete_annotations(sample_dir, completed)
    kwargs = dict(
        project_root=ROOT,
        config_path=config,
        sample_dir=sample_dir,
        canonical_path=canonical,
        development_package_dir=dev_dir,
        annotations_path=completed,
        annotator_ids=["primary-reviewer"],
        output_root=tmp_path / "frozen",
        execute=True,
        generated_at_utc=datetime(2026, 9, 2, 8, 0, tzinfo=timezone.utc),
    )
    freeze_reference_evidence(**kwargs)
    try:
        freeze_reference_evidence(**kwargs)
    except FileExistsError:
        pass
    else:
        raise AssertionError("Expected immutable reference overwrite failure")
