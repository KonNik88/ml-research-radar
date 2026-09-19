from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from radar_core.entities.scientific_entity_semantic_typer_h2_fresh_heldout_sample import (
    ScientificEntityH2FreshHeldoutSampleError,
    prepare_h2_fresh_heldout_sample,
    validate_h2_fresh_heldout_sample,
)

ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_ID = "scientific-entity-semantic-typer-candidate-v0.3-h2-selective-model-over-method"
DEV_ID = "scientific-entity-semantic-prompt-development-v0.2a-fixture"
OLD_SAMPLE_ID = "scientific-entity-fresh-heldout-sample-v0.2-fixture"
FREEZE_ID = "scientific-entity-semantic-typer-h2-frozen-candidate-v0.3-fixture"
FINGERPRINT = "1" * 64


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8", newline="\n",
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ids_sha(ids: list[str]) -> str:
    return hashlib.sha256(("\n".join(sorted(ids)) + "\n").encode()).hexdigest()


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path, Path]:
    consumed_dev = [
        {"canonical_id": f"dev-{i:03d}", "title": f"Dev {i}", "abstract": "Consumed development evidence.", "year": 2025}
        for i in range(72)
    ]
    consumed_old = [
        {"canonical_id": f"old-{i:03d}", "title": f"Old heldout {i}", "abstract": "Consumed fresh held-out evidence.", "year": 2026}
        for i in range(48)
    ]
    rich = (
        "classification named entity recognition machine translation contrastive learning transfer learning naive Bayes "
        "ImageNet CIFAR-10 benchmark dataset F1 score accuracy BLEU BERT transformer model language model "
        "medical imaging natural language processing computer vision"
    )
    fresh = [
        {"canonical_id": f"fresh-{i:03d}", "title": f"Fresh paper {i}: BERT classification", "abstract": f"{rich}. Unique {i}.", "year": 2026}
        for i in range(240)
    ]
    canonical = tmp_path / "canonical_documents.jsonl"
    _write_jsonl(canonical, consumed_dev + consumed_old + fresh)

    dev_dir = tmp_path / "development" / DEV_ID
    dev_canonical = dev_dir / "canonical_documents.jsonl"
    _write_jsonl(dev_canonical, consumed_dev)
    dev_manifest = {
        "schema_version": "scientific_entity_semantic_prompt_development_package_v0.2a",
        "package_id": DEV_ID,
        "combined_document_count": 72,
        "canonical_documents_sha256": _sha(dev_canonical),
    }
    _write_json(dev_dir / "manifest.json", dev_manifest)

    old_dir = tmp_path / "old" / OLD_SAMPLE_ID
    _write_jsonl(old_dir / "canonical_documents.sample.jsonl", consumed_old)
    old_ids = [row["canonical_id"] for row in consumed_old]
    old_manifest = {
        "schema_version": "scientific_entity_fresh_heldout_sample_manifest_v0.2",
        "sample_id": OLD_SAMPLE_ID,
        "selected_document_count": 48,
        "selected_canonical_ids": sorted(old_ids),
    }
    _write_json(old_dir / "manifest.json", old_manifest)

    freeze_dir = tmp_path / "freeze" / FREEZE_ID
    freeze_definition = {
        "schema_version": "scientific_entity_semantic_typer_h2_frozen_candidate_definition_v0.3",
        "candidate_id": CANDIDATE_ID,
        "candidate_fingerprint_sha256": FINGERPRINT,
        "candidate_status": "frozen_for_new_independent_acceptance",
        "requires_new_disjoint_prediction_blind_heldout": True,
    }
    _write_json(freeze_dir / "frozen_candidate.json", freeze_definition)
    freeze_manifest = {
        "schema_version": "scientific_entity_semantic_typer_h2_frozen_candidate_manifest_v0.3",
        "freeze_id": FREEZE_ID,
        "candidate_id": CANDIDATE_ID,
        "candidate_fingerprint_sha256": FINGERPRINT,
    }
    _write_json(freeze_dir / "manifest.json", freeze_manifest)

    config = {
        "schema_version": "scientific_entity_semantic_typer_h2_fresh_heldout_sample_config_v0.3",
        "layer": {"name": "scientific_entity_semantic_typer_h2_fresh_heldout_sample", "version": "v0.3", "status": "frozen_for_materialization", "layer_kind": "independent_prediction_blind_heldout_sample"},
        "candidate": {
            "candidate_id": CANDIDATE_ID,
            "freeze_id": FREEZE_ID,
            "candidate_fingerprint_sha256": FINGERPRINT,
            "expected_freeze_manifest_sha256": _sha(freeze_dir / "manifest.json"),
            "expected_frozen_candidate_sha256": _sha(freeze_dir / "frozen_candidate.json"),
        },
        "consumed_evidence_exclusion": {
            "development_package_id": DEV_ID,
            "expected_development_document_count": 72,
            "expected_development_manifest_sha256": _sha(dev_dir / "manifest.json"),
            "expected_development_canonical_sha256": _sha(dev_canonical),
            "previous_fresh_heldout_sample_id": OLD_SAMPLE_ID,
            "expected_previous_heldout_document_count": 48,
            "expected_previous_heldout_manifest_sha256": _sha(old_dir / "manifest.json"),
            "expected_previous_heldout_selected_ids_sha256": _ids_sha(old_ids),
            "expected_union_document_count": 120,
            "require_zero_overlap_between_consumed_sets": True,
            "exclude_all_consumed_documents": True,
        },
        "sampling": {
            "sampling_algorithm": "deterministic_hash_uniform_and_type_enriched_v0.3_h2",
            "sampling_seed": "ml-research-radar-scientific-entity-h2-fresh-heldout-v0.3",
            "canonical_input_path": "canonical_documents.jsonl",
            "require_title": True,
            "require_abstract": True,
            "uniform_document_count": 24,
            "type_enriched_documents_per_type": 4,
            "expected_document_count": 48,
            "expected_annotation_row_count": 96,
            "candidate_pool_per_stratum": 512,
            "source_fields": ["title", "abstract"],
            "enrichment_terms": {
                "task": ["classification", "named entity recognition", "machine translation"],
                "method": ["contrastive learning", "transfer learning", "naive Bayes"],
                "dataset": ["ImageNet", "CIFAR-10", "benchmark dataset"],
                "metric": ["F1 score", "accuracy", "BLEU"],
                "model": ["BERT", "transformer model", "language model"],
                "domain": ["medical imaging", "natural language processing", "computer vision"],
            },
        },
        "blindness": {
            "prediction_blind": True,
            "annotations_initially_empty": True,
            "candidate_predictions_may_be_read_during_sampling": False,
            "h1_predictions_may_be_read_during_sampling": False,
            "h2_inference_allowed_before_reference_freeze": False,
            "require_frozen_candidate_identity_before_sampling": True,
        },
        "safety": {
            "model_inference_allowed": False,
            "evaluation_allowed": False,
            "threshold_tuning_allowed": False,
            "policy_revision_allowed": False,
            "canonical_truth_mutation_allowed": False,
            "production_extractor_selection_allowed": False,
            "full_corpus_build_authorized": False,
        },
        "next_steps": {"after_sample_validation": "prediction_blind_manual_annotation_and_reference_freeze_for_h2"},
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return canonical, dev_dir, old_dir, freeze_dir, config_path, tmp_path / "output"


def _prepare(tmp_path: Path, *, execute: bool, sample_id: str = "scientific-entity-fresh-heldout-sample-v0.3-fixture"):
    canonical, dev_dir, old_dir, freeze_dir, config_path, output_root = _fixture(tmp_path)
    report = prepare_h2_fresh_heldout_sample(
        project_root=ROOT,
        config_path=config_path,
        canonical_path=canonical,
        development_package_dir=dev_dir,
        previous_heldout_sample_dir=old_dir,
        frozen_candidate_dir=freeze_dir,
        output_root=output_root,
        sample_id=sample_id,
        execute=execute,
        generated_at_utc=datetime(2026, 9, 19, 9, 30, tzinfo=timezone.utc),
    )
    return report, canonical, dev_dir, old_dir, freeze_dir, config_path


def test_plan_is_non_writing_and_excludes_all_120_consumed_documents(tmp_path: Path) -> None:
    report, *_ = _prepare(tmp_path, execute=False)
    assert report["phase_complete"] is False
    assert report["excluded_development_document_count"] == 72
    assert report["excluded_previous_heldout_document_count"] == 48
    assert report["excluded_consumed_union_document_count"] == 120
    assert report["excluded_consumed_ids_found_in_canonical"] == 120
    assert report["sample_consumed_union_overlap_count"] == 0
    assert report["selected_document_count"] == 48
    assert not Path(report["output_dir"]).exists()


def test_sample_shape_and_frozen_candidate_lineage(tmp_path: Path) -> None:
    report, *_ = _prepare(tmp_path, execute=False)
    assert report["uniform_document_count"] == 24
    assert report["type_enriched_document_count"] == 24
    assert report["candidate_id"] == CANDIDATE_ID
    assert report["candidate_fingerprint_sha256"] == FINGERPRINT
    assert report["type_enriched_count_by_type"] == {
        "task": 4, "method": 4, "dataset": 4, "metric": 4, "model": 4, "domain": 4,
    }


def test_execute_materializes_blank_prediction_blind_package(tmp_path: Path) -> None:
    report, *_ = _prepare(tmp_path, execute=True)
    directory = Path(report["output_dir"])
    rows = [json.loads(line) for line in (directory / "annotations_working.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 96
    assert all(row["annotation_complete"] is False and row["mentions"] == [] for row in rows)
    assert all("predicted_type" not in row and "score_margin" not in row for row in rows)
    assert report["prediction_blind"] is True
    assert report["h2_model_inference_executed"] is False
    assert report["reference_frozen"] is False


def test_validator_recomputes_exact_sample_and_disjointness(tmp_path: Path) -> None:
    report, canonical, dev_dir, old_dir, freeze_dir, config_path = _prepare(tmp_path, execute=True)
    checks, summary = validate_h2_fresh_heldout_sample(
        project_root=ROOT,
        config_path=config_path,
        canonical_path=canonical,
        development_package_dir=dev_dir,
        previous_heldout_sample_dir=old_dir,
        frozen_candidate_dir=freeze_dir,
        sample_dir=Path(report["output_dir"]),
    )
    assert all(ok for _, ok, _ in checks)
    assert summary["required_failed_count"] == 0
    assert summary["sample_consumed_union_overlap_count"] == 0


def test_selection_is_deterministic_across_sample_ids(tmp_path: Path) -> None:
    canonical, dev_dir, old_dir, freeze_dir, config_path, output_root = _fixture(tmp_path)
    common = dict(
        project_root=ROOT, config_path=config_path, canonical_path=canonical,
        development_package_dir=dev_dir, previous_heldout_sample_dir=old_dir,
        frozen_candidate_dir=freeze_dir, output_root=output_root, execute=False,
        generated_at_utc=datetime(2026, 9, 19, 9, 30, tzinfo=timezone.utc),
    )
    first = prepare_h2_fresh_heldout_sample(**common, sample_id="scientific-entity-fresh-heldout-sample-v0.3-a")
    second = prepare_h2_fresh_heldout_sample(**common, sample_id="scientific-entity-fresh-heldout-sample-v0.3-b")
    assert first["selected_canonical_ids_sha256"] == second["selected_canonical_ids_sha256"]


def test_missing_consumed_document_fails_closed(tmp_path: Path) -> None:
    canonical, dev_dir, old_dir, freeze_dir, config_path, output_root = _fixture(tmp_path)
    rows = [json.loads(line) for line in canonical.read_text(encoding="utf-8").splitlines()]
    _write_jsonl(canonical, [row for row in rows if row["canonical_id"] != "old-047"])
    try:
        prepare_h2_fresh_heldout_sample(
            project_root=ROOT, config_path=config_path, canonical_path=canonical,
            development_package_dir=dev_dir, previous_heldout_sample_dir=old_dir,
            frozen_candidate_dir=freeze_dir, output_root=output_root,
            sample_id="scientific-entity-fresh-heldout-sample-v0.3-missing", execute=False,
        )
    except ScientificEntityH2FreshHeldoutSampleError as exc:
        assert "does not contain all consumed evidence documents" in str(exc)
    else:
        raise AssertionError("Expected fail-closed consumed-evidence exclusion error")


def test_tampered_frozen_candidate_fingerprint_fails_closed(tmp_path: Path) -> None:
    canonical, dev_dir, old_dir, freeze_dir, config_path, output_root = _fixture(tmp_path)
    definition = json.loads((freeze_dir / "frozen_candidate.json").read_text(encoding="utf-8"))
    definition["candidate_fingerprint_sha256"] = "2" * 64
    _write_json(freeze_dir / "frozen_candidate.json", definition)
    try:
        prepare_h2_fresh_heldout_sample(
            project_root=ROOT, config_path=config_path, canonical_path=canonical,
            development_package_dir=dev_dir, previous_heldout_sample_dir=old_dir,
            frozen_candidate_dir=freeze_dir, output_root=output_root,
            sample_id="scientific-entity-fresh-heldout-sample-v0.3-tampered", execute=False,
        )
    except ScientificEntityH2FreshHeldoutSampleError:
        pass
    else:
        raise AssertionError("Expected frozen candidate lineage failure")
