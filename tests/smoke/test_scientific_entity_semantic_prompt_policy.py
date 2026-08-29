from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from radar_core.contracts.scientific_entity_evidence import (
    CANONICAL_INPUT_SCHEMA_VERSION,
    EXTRACTOR_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    MENTION_SCHEMA_VERSION,
    ConfidenceKind,
    EntityEvidenceBuildStatus,
    ExtractorKind,
    ScientificEntityCanonicalInput,
    ScientificEntityEvidenceManifest,
    ScientificEntityExtractorDescriptor,
    ScientificEntityMentionEvidence,
    ScientificEntitySourceField,
    ScientificEntityType,
    build_evidence_id,
    build_extractor_fingerprint,
    build_mention_id,
    sha256_text,
)
from radar_core.entities.scientific_entity_gliner import gliner_config_sha256, load_gliner_config
from radar_core.entities.scientific_entity_semantic_prompt_policy import (
    DEFAULT_CONFIG_PATH,
    SemanticPromptPolicyError,
    build_semantic_prompt_policy,
    load_policy_config,
    validate_semantic_prompt_policy_build,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_CONFIG = PROJECT_ROOT / "configs" / "scientific_entity_gliner_semantic_prompt_candidate_v0.2a.yaml"


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8", newline="\n")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    package = tmp_path / "package"
    parent = tmp_path / "parent"
    package.mkdir()
    parent.mkdir()

    canonical = package / "canonical_documents.jsonl"
    canonical.write_text('{"canonical_id":"fixture-doc","title":"Alpha Beta","abstract":"Gamma Delta"}\n', encoding="utf-8", newline="\n")
    canonical_sha = _sha(canonical)
    _write_json(package / "manifest.json", {
        "package_id": "scientific-entity-semantic-prompt-development-v0.2a-fixture",
        "candidate_id": "scientific-entity-semantic-prompt-candidate-v0.2a",
        "combined_document_count": 72,
        "canonical_documents_sha256": canonical_sha,
        "future_v02_acceptance_requires_new_disjoint_heldout": True,
        "canonical_truth_mutated": False,
        "may_be_used_as_reconcile_input": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "publication_ready": False,
    })

    runtime = load_gliner_config(RUNTIME_CONFIG)
    descriptor = ScientificEntityExtractorDescriptor(
        schema_version=EXTRACTOR_SCHEMA_VERSION,
        name=runtime.extractor.name,
        version=runtime.extractor.version,
        kind=ExtractorKind.STATISTICAL_MODEL,
        code_revision="fixture-code-revision",
        config_sha256=gliner_config_sha256(runtime),
        environment_sha256="0" * 64,
        model_name=runtime.model.repository,
        model_revision=runtime.model.revision,
        model_artifact_sha256=runtime.model.artifact_sha256,
        model_license=runtime.model.license,
    )
    fingerprint = build_extractor_fingerprint(descriptor)
    parent_build_id = "scientific-entity-gliner-small-v2.5-v0.1-20260829T141340564165Z"

    specs = [
        (ScientificEntitySourceField.TITLE, "Alpha Beta", 0, 5, ScientificEntityType.MODEL, 0.60),
        (ScientificEntitySourceField.TITLE, "Alpha Beta", 6, 10, ScientificEntityType.METHOD, 0.54),
        (ScientificEntitySourceField.ABSTRACT, "Gamma Delta", 0, 5, ScientificEntityType.TASK, 0.70),
        (ScientificEntitySourceField.ABSTRACT, "Gamma Delta", 6, 11, ScientificEntityType.METRIC, 0.64),
    ]
    rows = []
    for source_field, source_text, start, end, entity_type, score in specs:
        source_sha = sha256_text(source_text)
        mention_id = build_mention_id(
            canonical_id="fixture-doc",
            source_field=source_field,
            source_text_sha256=source_sha,
            char_start=start,
            char_end=end,
            entity_type=entity_type,
        )
        row = ScientificEntityMentionEvidence(
            schema_version=MENTION_SCHEMA_VERSION,
            evidence_id=build_evidence_id(mention_id=mention_id, extractor_fingerprint=fingerprint),
            mention_id=mention_id,
            build_id=parent_build_id,
            canonical_id="fixture-doc",
            entity_type=entity_type,
            source_field=source_field,
            source_text_sha256=source_sha,
            char_start=start,
            char_end=end,
            surface_text=source_text[start:end],
            extractor_fingerprint=fingerprint,
            confidence_kind=ConfidenceKind.MODEL_SCORE,
            confidence_score=score,
            calibration_id=None,
        )
        rows.append(row.model_dump(mode="json"))
    _write_jsonl(parent / "mentions.jsonl", rows)
    manifest = ScientificEntityEvidenceManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        build_id=parent_build_id,
        status=EntityEvidenceBuildStatus.CANDIDATE,
        generated_at_utc=datetime(2026, 8, 29, 14, 13, 40, tzinfo=timezone.utc),
        canonical_input=ScientificEntityCanonicalInput(
            schema_version=CANONICAL_INPUT_SCHEMA_VERSION,
            path=str(canonical),
            sha256=canonical_sha,
            document_count=72,
            canonical_contract="CanonicalDocument",
        ),
        extractor=descriptor,
        extractor_fingerprint=fingerprint,
        offset_unit="unicode_codepoint",
        offset_interval="half_open",
        source_fields=[ScientificEntitySourceField.TITLE, ScientificEntitySourceField.ABSTRACT],
        entity_types=list(ScientificEntityType),
        mentions_file="mentions.jsonl",
        mention_count=len(rows),
        mentions_sha256=_sha(parent / "mentions.jsonl"),
        canonical_truth_mutated=False,
        may_be_used_as_reconcile_input=False,
        publication_ready=False,
    )
    _write_json(parent / "manifest.json", manifest.model_dump(mode="json"))
    return parent, package


def test_policy_config_is_frozen() -> None:
    config = load_policy_config(DEFAULT_CONFIG_PATH)
    assert config.candidate.expected_document_count == 72
    assert config.policy.source_field_thresholds[ScientificEntitySourceField.TITLE] == 0.55
    assert config.policy.source_field_thresholds[ScientificEntitySourceField.ABSTRACT] == 0.65
    assert config.policy.entity_type_thresholds == {}
    assert config.safety.model_inference_allowed is False
    assert config.safety.threshold_tuning_allowed is False


def test_plan_selects_using_unchanged_source_policy(tmp_path: Path) -> None:
    parent, package = _fixture(tmp_path)
    report = build_semantic_prompt_policy(
        parent_build_dir=parent,
        development_package_dir=package,
        output_root=tmp_path / "out",
        generated_at_utc=datetime(2026, 8, 29, 15, 0, tzinfo=timezone.utc),
    )
    assert report["mode"] == "plan"
    assert report["input_prediction_count"] == 4
    assert report["selected_prediction_count"] == 2
    assert report["rejected_prediction_count"] == 2
    assert report["extractor_fingerprint_changed"] is True
    assert report["model_inference_executed"] is False
    assert not Path(report["output_dir"]).exists()


def test_execute_and_validator_reproduce_identity_and_lineage(tmp_path: Path) -> None:
    parent, package = _fixture(tmp_path)
    build_id = "scientific-entity-semantic-prompt-policy-v0.2a-20260829T150000000000Z"
    output_root = tmp_path / "out"
    report = build_semantic_prompt_policy(
        parent_build_dir=parent,
        development_package_dir=package,
        output_root=output_root,
        build_id=build_id,
        execute=True,
        generated_at_utc=datetime(2026, 8, 29, 15, 0, tzinfo=timezone.utc),
    )
    build_dir = output_root / build_id
    assert report["phase_complete"] is True
    assert set(path.name for path in build_dir.iterdir()) == {
        "mentions.jsonl", "manifest.json", "derivation_manifest.json",
        "evidence_lineage.jsonl", "data_quality_summary.json", "schema.json",
        "README.md", "checksums.txt",
    }
    validated = validate_semantic_prompt_policy_build(
        build_dir=build_dir,
        parent_build_dir=parent,
        development_package_dir=package,
    )
    assert validated["required_failed_count"] == 0
    assert validated["selected_prediction_count"] == 2
    assert validated["extractor_fingerprint_changed"] is True


def test_execute_is_immutable(tmp_path: Path) -> None:
    parent, package = _fixture(tmp_path)
    build_id = "scientific-entity-semantic-prompt-policy-v0.2a-20260829T150000000001Z"
    output_root = tmp_path / "out"
    build_semantic_prompt_policy(
        parent_build_dir=parent,
        development_package_dir=package,
        output_root=output_root,
        build_id=build_id,
        execute=True,
        generated_at_utc=datetime(2026, 8, 29, 15, 0, tzinfo=timezone.utc),
    )
    with pytest.raises(FileExistsError):
        build_semantic_prompt_policy(
            parent_build_dir=parent,
            development_package_dir=package,
            output_root=output_root,
            build_id=build_id,
            execute=True,
            generated_at_utc=datetime(2026, 8, 29, 15, 0, tzinfo=timezone.utc),
        )


def test_parent_runtime_config_sha_must_match_candidate(tmp_path: Path) -> None:
    parent, package = _fixture(tmp_path)
    manifest_path = parent / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["extractor"]["config_sha256"] = "f" * 64
    payload["extractor_fingerprint"] = build_extractor_fingerprint(payload["extractor"])
    _write_json(manifest_path, payload)
    with pytest.raises((SemanticPromptPolicyError, ValueError)):
        build_semantic_prompt_policy(
            parent_build_dir=parent,
            development_package_dir=package,
            output_root=tmp_path / "out",
        )
