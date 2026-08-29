from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from radar_core.entities.scientific_entity_semantic_prompt_development import (
    SemanticPromptDevelopmentError,
    prepare_semantic_prompt_development_package,
    validate_semantic_prompt_development_package,
)


ROOT = Path(__file__).resolve().parents[2]
DESIGN_CONFIG = ROOT / "configs" / "scientific_entity_semantic_prompt_candidate_v0.2a.yaml"
EMPTY_SHA = hashlib.sha256(b"").hexdigest()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_source_eval(
    root: Path,
    *,
    name: str,
    count: int,
    start: int,
    review_id: str,
    evaluation_id: str,
) -> Path:
    source = root / name
    source.mkdir(parents=True)
    canonical = source / "canonical_documents.jsonl"
    rows = []
    for index in range(start, start + count):
        rows.append(
            {
                "canonical_id": f"paper-{index:03d}",
                "reconciliation_key": f"synthetic:paper-{index:03d}",
                "title": f"Synthetic paper {index}",
                "abstract": f"Synthetic abstract {index} for development package testing.",
            }
        )
    canonical.write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
        newline="\n",
    )
    references = source / "reference_mentions.jsonl"
    references.write_text("", encoding="utf-8", newline="\n")

    manifest = {
        "schema_version": "scientific_entity_evaluation_manifest_v0.1",
        "evaluation_id": evaluation_id,
        "status": "candidate",
        "generated_at_utc": "2026-08-29T12:00:00Z",
        "config_path": "configs/scientific_entity_evaluation_v0.1.yaml",
        "config_sha256": "0" * 64,
        "canonical_input": {
            "schema_version": "scientific_entity_canonical_input_v0.1",
            "path": str(canonical.resolve()).replace("\\", "/"),
            "sha256": _sha(canonical),
            "document_count": count,
            "canonical_contract": "CanonicalDocument",
        },
        "review": {
            "review_id": review_id,
            "status": "reviewed_candidate",
            "manifest_path": str((source / "review_manifest.json").resolve()).replace("\\", "/"),
            "manifest_sha256": "1" * 64,
            "reference_mentions_path": str(references.resolve()).replace("\\", "/"),
            "reference_mentions_sha256": EMPTY_SHA,
            "reference_mention_count": 0,
            "review_complete": True,
            "prediction_blind": True,
        },
        "prediction": {
            "build_id": f"scientific-entity-gliner-test-{name}-v0.1",
            "status": "candidate",
            "manifest_path": str((source / "prediction_manifest.json").resolve()).replace("\\", "/"),
            "manifest_sha256": "2" * 64,
            "mentions_path": str((source / "prediction_mentions.jsonl").resolve()).replace("\\", "/"),
            "mentions_sha256": EMPTY_SHA,
            "mention_count": 0,
            "extractor_fingerprint": "3" * 64,
        },
        "matching_policy": {
            "exact_requires_same_entity_type": True,
            "exact_requires_same_span": True,
            "exact_requires_same_text_identity": True,
            "relaxed_enabled": True,
            "relaxed_min_char_iou": 0.5,
            "relaxed_requires_same_entity_type": True,
            "relaxed_requires_same_text_identity": True,
            "relaxed_assignment": "deterministic_greedy_iou_desc_v0.1",
            "one_to_one": True,
        },
        "metrics_file": "metrics.json",
        "metrics_sha256": "4" * 64,
        "per_type_metrics_file": "per_type_metrics.json",
        "per_type_metrics_sha256": "5" * 64,
        "matches_file": "matches.jsonl",
        "matches_sha256": EMPTY_SHA,
        "match_count": 0,
        "errors_file": "errors.jsonl",
        "errors_sha256": EMPTY_SHA,
        "error_count": 0,
        "canonical_truth_mutated": False,
        "may_be_used_as_reconcile_input": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "model_downloaded": False,
        "provider_api_called": False,
        "redistribution_allowed": False,
        "publication_ready": False,
    }
    (source / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return source


def _sources(tmp_path: Path) -> tuple[Path, Path]:
    old = _write_source_eval(
        tmp_path,
        name="old",
        count=24,
        start=0,
        review_id="scientific-entity-manual-review-v0.1-20260821T131320262656Z",
        evaluation_id="scientific-entity-evaluation-v0.1-20260823T124036780234Z",
    )
    held = _write_source_eval(
        tmp_path,
        name="held",
        count=48,
        start=24,
        review_id="scientific-entity-heldout-review-v0.1-20260827T092900455472Z",
        evaluation_id="scientific-entity-evaluation-v0.1-20260827T113112815887Z",
    )
    return old, held


def test_plan_is_non_writing_and_finds_72_disjoint_documents(tmp_path: Path) -> None:
    old, held = _sources(tmp_path)
    output_root = tmp_path / "out"
    report = prepare_semantic_prompt_development_package(
        project_root=ROOT,
        design_config_path=DESIGN_CONFIG,
        old_dev_evaluation_dir=old,
        consumed_heldout_evaluation_dir=held,
        output_root=output_root,
        package_id="scientific-entity-semantic-prompt-development-v0.2a-test",
        execute=False,
        generated_at_utc=datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc),
    )
    assert report["mode"] == "plan"
    assert report["combined_document_count"] == 72
    assert report["source_split_overlap_count"] == 0
    assert report["model_inference_executed"] is False
    assert not output_root.exists()


def test_execute_and_validator_reproduce_package(tmp_path: Path) -> None:
    old, held = _sources(tmp_path)
    output_root = tmp_path / "out"
    package_id = "scientific-entity-semantic-prompt-development-v0.2a-test"
    report = prepare_semantic_prompt_development_package(
        project_root=ROOT,
        design_config_path=DESIGN_CONFIG,
        old_dev_evaluation_dir=old,
        consumed_heldout_evaluation_dir=held,
        output_root=output_root,
        package_id=package_id,
        execute=True,
        generated_at_utc=datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc),
    )
    package_dir = output_root / package_id
    assert report["phase_complete"] is True
    assert (package_dir / "canonical_documents.jsonl").is_file()
    assert (package_dir / "split_membership.jsonl").is_file()
    validation = validate_semantic_prompt_development_package(
        project_root=ROOT,
        design_config_path=DESIGN_CONFIG,
        package_dir=package_dir,
    )
    assert validation["ok"] is True
    assert validation["combined_document_count"] == 72
    assert validation["next_slice"] == "bounded_raw_candidate_inference_on_72_development_documents"


def test_overlap_fails_closed(tmp_path: Path) -> None:
    old = _write_source_eval(
        tmp_path,
        name="old",
        count=24,
        start=0,
        review_id="scientific-entity-manual-review-v0.1-20260821T131320262656Z",
        evaluation_id="scientific-entity-evaluation-v0.1-20260823T124036780234Z",
    )
    held = _write_source_eval(
        tmp_path,
        name="held",
        count=48,
        start=20,
        review_id="scientific-entity-heldout-review-v0.1-20260827T092900455472Z",
        evaluation_id="scientific-entity-evaluation-v0.1-20260827T113112815887Z",
    )
    with pytest.raises(SemanticPromptDevelopmentError, match="disjoint"):
        prepare_semantic_prompt_development_package(
            project_root=ROOT,
            design_config_path=DESIGN_CONFIG,
            old_dev_evaluation_dir=old,
            consumed_heldout_evaluation_dir=held,
            output_root=tmp_path / "out",
            execute=False,
        )


def test_consumed_heldout_lineage_drift_fails_closed(tmp_path: Path) -> None:
    old, held = _sources(tmp_path)
    manifest_path = held / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["evaluation_id"] = "scientific-entity-evaluation-v0.1-20260827T999999999999Z"
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(SemanticPromptDevelopmentError, match="evaluation_id"):
        prepare_semantic_prompt_development_package(
            project_root=ROOT,
            design_config_path=DESIGN_CONFIG,
            old_dev_evaluation_dir=old,
            consumed_heldout_evaluation_dir=held,
            output_root=tmp_path / "out",
            execute=False,
        )


def test_validator_detects_tampered_combined_canonical(tmp_path: Path) -> None:
    old, held = _sources(tmp_path)
    output_root = tmp_path / "out"
    package_id = "scientific-entity-semantic-prompt-development-v0.2a-test"
    prepare_semantic_prompt_development_package(
        project_root=ROOT,
        design_config_path=DESIGN_CONFIG,
        old_dev_evaluation_dir=old,
        consumed_heldout_evaluation_dir=held,
        output_root=output_root,
        package_id=package_id,
        execute=True,
        generated_at_utc=datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc),
    )
    package_dir = output_root / package_id
    canonical = package_dir / "canonical_documents.jsonl"
    canonical.write_text(canonical.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(SemanticPromptDevelopmentError, match="Checksum mismatch"):
        validate_semantic_prompt_development_package(
            project_root=ROOT,
            design_config_path=DESIGN_CONFIG,
            package_dir=package_dir,
        )
