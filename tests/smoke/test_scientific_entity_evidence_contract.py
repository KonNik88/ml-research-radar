from __future__ import annotations

import copy
import hashlib
import json
import shutil
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import yaml
from pydantic import ValidationError

from radar_core.contracts.scientific_entity_evidence import (
    ConfidenceKind,
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
    validate_mention_evidence,
)
from scripts.validation.check_scientific_entity_evidence_contract import (
    CONFIG_PATH,
    CONTRACT_PATH,
    REQUIRED_ENTITY_TYPES,
    REQUIRED_SOURCE_FIELDS,
    validate_contract,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "scientific_entity_evidence_v0_1"


@contextmanager
def _raises(expected: type[BaseException]) -> Iterator[None]:
    try:
        yield
    except expected:
        return
    raise AssertionError(f"Expected {expected.__name__}")


def _descriptor(
    *,
    name: str = "fixture",
    config_sha256: str | None = None,
) -> ScientificEntityExtractorDescriptor:
    return ScientificEntityExtractorDescriptor(
        schema_version="scientific_entity_extractor_descriptor_v0.1",
        name=name,
        version="0.1.0",
        kind="human_annotation",
        code_revision="test-revision",
        config_sha256=config_sha256 or ("1" * 64),
        environment_sha256="9" * 64,
    )


def _record(
    *,
    text: str = "β-VAE improves representation learning",
    entity_type: str = "model",
    extractor: ScientificEntityExtractorDescriptor | None = None,
) -> ScientificEntityMentionEvidence:
    descriptor = extractor or _descriptor()
    source_hash = sha256_text(text)
    mention_id = build_mention_id(
        canonical_id="synthetic-paper",
        source_field="title",
        source_text_sha256=source_hash,
        char_start=0,
        char_end=5,
        entity_type=entity_type,
    )
    fingerprint = build_extractor_fingerprint(descriptor)
    return ScientificEntityMentionEvidence(
        schema_version="scientific_entity_mention_evidence_v0.1",
        evidence_id=build_evidence_id(
            mention_id=mention_id,
            extractor_fingerprint=fingerprint,
        ),
        mention_id=mention_id,
        build_id="test-build",
        canonical_id="synthetic-paper",
        entity_type=entity_type,
        source_field="title",
        source_text_sha256=source_hash,
        char_start=0,
        char_end=5,
        surface_text="β-VAE",
        extractor_fingerprint=fingerprint,
        confidence_kind="not_available",
        confidence_score=None,
        calibration_id=None,
    )


def _manifest(
    descriptor: ScientificEntityExtractorDescriptor | None = None,
) -> ScientificEntityEvidenceManifest:
    extractor = descriptor or _descriptor()
    return ScientificEntityEvidenceManifest(
        schema_version="scientific_entity_evidence_manifest_v0.1",
        build_id="test-build",
        status="fixture",
        generated_at_utc=datetime.now(timezone.utc),
        canonical_input=ScientificEntityCanonicalInput(
            schema_version="scientific_entity_canonical_input_v0.1",
            path="fixture.jsonl",
            sha256="2" * 64,
            document_count=1,
            canonical_contract="CanonicalDocument",
        ),
        extractor=extractor,
        extractor_fingerprint=build_extractor_fingerprint(extractor),
        offset_unit="unicode_codepoint",
        offset_interval="half_open",
        source_fields=["title", "abstract"],
        entity_types=[item.value for item in ScientificEntityType],
        mentions_file="mentions.jsonl",
        mention_count=1,
        mentions_sha256="3" * 64,
        canonical_truth_mutated=False,
        may_be_used_as_reconcile_input=False,
        publication_ready=False,
    )


def _base_config() -> dict[str, Any]:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    assert isinstance(config, dict)
    for key, name in {
        "canonical_documents_path": "canonical_documents.jsonl",
        "extractor_descriptor_path": "extractor.json",
        "manifest_path": "manifest.json",
        "mentions_path": "mentions.jsonl",
    }.items():
        config["fixtures"][key] = str(FIXTURE_ROOT / name)
    return config


def _write_config(tmp_path: Path, config: dict[str, Any]) -> Path:
    path = tmp_path / "configs" / "scientific_entity_evidence.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def _validate(tmp_path: Path, config: dict[str, Any]) -> dict[str, Any]:
    return validate_contract(
        config_path=_write_config(tmp_path, config),
        contract_path=CONTRACT_PATH,
        write_reports=False,
    )


def test_default_contract_and_fixture_pass() -> None:
    report = validate_contract(write_reports=False)

    assert report["summary"]["ok"] is True
    assert report["summary"]["required_failed_count"] == 0
    assert report["summary"]["fixture_document_count"] == 1
    assert report["summary"]["fixture_mention_count"] == 6
    assert report["verdict"]["authorized_follow_on"] == (
        "bounded_scientific_entity_extractor_baseline_v0.1"
    )
    assert report["verdict"]["next_slice"] == (
        "bounded_scientific_entity_manual_review_evidence_v0.1"
    )


def test_executable_taxonomy_and_source_fields_are_exact() -> None:
    assert {item.value for item in ScientificEntityType} == REQUIRED_ENTITY_TYPES
    assert {item.value for item in ScientificEntitySourceField} == REQUIRED_SOURCE_FIELDS


def test_mention_identity_is_extractor_independent_but_evidence_is_not() -> None:
    first_extractor = _descriptor(name="first", config_sha256="1" * 64)
    second_extractor = _descriptor(name="second", config_sha256="2" * 64)
    first_record = _record(extractor=first_extractor)
    second_record = _record(extractor=second_extractor)

    assert first_record.mention_id == second_record.mention_id
    assert first_record.extractor_fingerprint != second_record.extractor_fingerprint
    assert first_record.evidence_id != second_record.evidence_id


def test_source_text_or_entity_type_change_changes_mention_identity() -> None:
    original = _record()
    changed_text = "β-VAE changes representation learning"
    changed_hash = sha256_text(changed_text)
    changed_text_id = build_mention_id(
        canonical_id=original.canonical_id,
        source_field=original.source_field,
        source_text_sha256=changed_hash,
        char_start=0,
        char_end=5,
        entity_type=original.entity_type,
    )
    changed_type_id = build_mention_id(
        canonical_id=original.canonical_id,
        source_field=original.source_field,
        source_text_sha256=original.source_text_sha256,
        char_start=0,
        char_end=5,
        entity_type="method",
    )

    assert changed_text_id != original.mention_id
    assert changed_type_id != original.mention_id


def test_unicode_codepoint_span_validates() -> None:
    text = "β-VAE improves representation learning"
    descriptor = _descriptor()
    record = _record(text=text, extractor=descriptor)

    validated = validate_mention_evidence(
        record,
        source_text=text,
        extractor=descriptor,
        manifest=_manifest(descriptor),
    )

    assert validated.surface_text == "β-VAE"
    assert text[validated.char_start : validated.char_end] == "β-VAE"


def test_surface_or_source_hash_mismatch_fails_closed() -> None:
    descriptor = _descriptor()
    record = _record(extractor=descriptor)
    wrong_surface = record.model_copy(update={"surface_text": "VAE"})
    wrong_hash = record.model_copy(update={"source_text_sha256": "0" * 64})

    with _raises(ValueError):
        validate_mention_evidence(
            wrong_surface,
            source_text="β-VAE improves representation learning",
            extractor=descriptor,
        )
    with _raises(ValueError):
        validate_mention_evidence(
            wrong_hash,
            source_text="β-VAE improves representation learning",
            extractor=descriptor,
        )


def test_mention_or_evidence_id_mismatch_fails_closed() -> None:
    descriptor = _descriptor()
    record = _record(extractor=descriptor)
    wrong_mention = record.model_copy(update={"mention_id": "mention:" + ("0" * 32)})
    wrong_evidence = record.model_copy(update={"evidence_id": "evidence:" + ("0" * 32)})

    with _raises(ValueError):
        validate_mention_evidence(
            wrong_mention,
            source_text="β-VAE improves representation learning",
            extractor=descriptor,
        )
    with _raises(ValueError):
        validate_mention_evidence(
            wrong_evidence,
            source_text="β-VAE improves representation learning",
            extractor=descriptor,
        )


def test_confidence_semantics_fail_closed() -> None:
    payload = _record().model_dump(mode="json")

    with _raises(ValidationError):
        ScientificEntityMentionEvidence.model_validate(
            {
                **payload,
                "confidence_kind": ConfidenceKind.NOT_AVAILABLE.value,
                "confidence_score": 0.9,
            }
        )
    with _raises(ValidationError):
        ScientificEntityMentionEvidence.model_validate(
            {
                **payload,
                "confidence_kind": ConfidenceKind.MODEL_SCORE.value,
                "confidence_score": None,
            }
        )
    with _raises(ValidationError):
        ScientificEntityMentionEvidence.model_validate(
            {
                **payload,
                "confidence_kind": ConfidenceKind.CALIBRATED_PROBABILITY.value,
                "confidence_score": 0.9,
                "calibration_id": None,
            }
        )
    with _raises(ValidationError):
        ScientificEntityMentionEvidence.model_validate(
            {
                **payload,
                "confidence_kind": ConfidenceKind.CALIBRATED_PROBABILITY.value,
                "confidence_score": 0.9,
                "calibration_id": "   ",
            }
        )


def test_required_nullable_and_safety_fields_cannot_be_omitted() -> None:
    mention_payload = _record().model_dump(mode="json")
    mention_payload.pop("confidence_score")
    with _raises(ValidationError):
        ScientificEntityMentionEvidence.model_validate(mention_payload)

    manifest_payload = _manifest().model_dump(mode="json")
    manifest_payload.pop("canonical_truth_mutated")
    with _raises(ValidationError):
        ScientificEntityEvidenceManifest.model_validate(manifest_payload)


def test_model_extractors_require_complete_immutable_provenance() -> None:
    with _raises(ValidationError):
        ScientificEntityExtractorDescriptor(
            schema_version="scientific_entity_extractor_descriptor_v0.1",
            name="model-extractor",
            version="1",
            kind="statistical_model",
            code_revision="commit",
            config_sha256="1" * 64,
            environment_sha256="9" * 64,
            model_name="example/model",
        )

    descriptor = ScientificEntityExtractorDescriptor(
        schema_version="scientific_entity_extractor_descriptor_v0.1",
        name="model-extractor",
        version="1",
        kind="statistical_model",
        code_revision="commit",
        config_sha256="1" * 64,
        environment_sha256="9" * 64,
        model_name="example/model",
        model_revision="immutable-revision",
        model_artifact_sha256="2" * 64,
        model_license="Apache-2.0",
    )
    assert descriptor.model_revision == "immutable-revision"


def test_manifest_rejects_fingerprint_and_timezone_drift() -> None:
    payload = _manifest().model_dump(mode="json")

    with _raises(ValidationError):
        ScientificEntityEvidenceManifest.model_validate(
            {**payload, "extractor_fingerprint": "0" * 64}
        )
    with _raises(ValidationError):
        ScientificEntityEvidenceManifest.model_validate(
            {**payload, "generated_at_utc": "2026-08-20T00:00:00"}
        )
    with _raises(ValidationError):
        ScientificEntityEvidenceManifest.model_validate(
            {**payload, "generated_at_utc": "2026-08-20T01:00:00+01:00"}
        )


def test_missing_entity_type_fails_contract_validation(tmp_path: Path) -> None:
    config = _base_config()
    config["entity_taxonomy"]["required_types"].remove("domain")
    report = _validate(tmp_path, config)

    assert report["summary"]["ok"] is False
    assert "entity_types_exact" in report["verdict"]["required_failed_checks"]


def test_unsafe_mutation_flag_fails_contract_validation(tmp_path: Path) -> None:
    config = _base_config()
    config["safety"]["may_mutate_canonical_corpus"] = True
    report = _validate(tmp_path, config)

    assert report["summary"]["ok"] is False
    assert "safety_false_flags_ok" in report["verdict"]["required_failed_checks"]
    assert report["verdict"]["canonical_mutation_allowed"] is True


def test_contract_slice_cannot_claim_generated_output(tmp_path: Path) -> None:
    config = _base_config()
    config["outputs"]["generated_in_this_slice"] = True
    report = _validate(tmp_path, config)

    assert report["summary"]["ok"] is False
    assert "outputs_not_generated" in report["verdict"]["required_failed_checks"]
    assert report["verdict"]["full_corpus_output_generated"] is True


def test_generated_output_root_must_remain_gitignored(tmp_path: Path) -> None:
    config = _base_config()
    config["outputs"]["expected_future_output_root"] = "wrong/output"
    config["outputs"]["generated_output_gitignore_rule"] = "/wrong-output/"
    report = _validate(tmp_path, config)

    assert report["summary"]["ok"] is False
    assert "output_root_exact" in report["verdict"]["required_failed_checks"]
    assert "generated_output_gitignore_rule_ok" in (
        report["verdict"]["required_failed_checks"]
    )
    assert "generated_output_gitignore_present" in (
        report["verdict"]["required_failed_checks"]
    )


def test_missing_contract_marker_fails_validation(tmp_path: Path) -> None:
    contract_path = tmp_path / "scientific_entity_evidence_contract_v0.1.md"
    contract_text = CONTRACT_PATH.read_text(encoding="utf-8").replace(
        "model_score_is_not_probability = true",
        "model score marker removed",
    )
    contract_path.write_text(contract_text, encoding="utf-8")
    config_path = _write_config(tmp_path, _base_config())

    report = validate_contract(
        config_path=config_path,
        contract_path=contract_path,
        write_reports=False,
    )

    assert report["summary"]["ok"] is False
    assert any(
        name.startswith("contract_marker:model_score_is_not_probability")
        for name in report["verdict"]["required_failed_checks"]
    )


def test_corrupt_fixture_span_and_hash_fail_validation(tmp_path: Path) -> None:
    fixture_copy = tmp_path / "fixture"
    shutil.copytree(FIXTURE_ROOT, fixture_copy)
    mentions_path = fixture_copy / "mentions.jsonl"
    rows = [json.loads(line) for line in mentions_path.read_text(encoding="utf-8").splitlines()]
    rows[0]["surface_text"] = "wrong"
    mentions_path.write_text(
        "\n".join(json.dumps(row, separators=(",", ":")) for row in rows) + "\n",
        encoding="utf-8",
    )

    config = _base_config()
    for key, name in {
        "canonical_documents_path": "canonical_documents.jsonl",
        "extractor_descriptor_path": "extractor.json",
        "manifest_path": "manifest.json",
        "mentions_path": "mentions.jsonl",
    }.items():
        config["fixtures"][key] = str(fixture_copy / name)
    report = _validate(tmp_path, config)

    assert report["summary"]["ok"] is False
    failed = report["verdict"]["required_failed_checks"]
    assert "fixture_manifest_mentions_sha256_matches" in failed
    assert "fixture_records_valid" in failed


def test_crlf_fixture_fails_explicit_line_ending_gates(tmp_path: Path) -> None:
    fixture_copy = tmp_path / "fixture"
    shutil.copytree(FIXTURE_ROOT, fixture_copy)
    canonical_path = fixture_copy / "canonical_documents.jsonl"
    mentions_path = fixture_copy / "mentions.jsonl"
    for path in (canonical_path, mentions_path):
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))

    manifest_path = fixture_copy / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["canonical_input"]["sha256"] = hashlib.sha256(
        canonical_path.read_bytes()
    ).hexdigest()
    manifest["mentions_sha256"] = hashlib.sha256(
        mentions_path.read_bytes()
    ).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    config = _base_config()
    for key, name in {
        "canonical_documents_path": "canonical_documents.jsonl",
        "extractor_descriptor_path": "extractor.json",
        "manifest_path": "manifest.json",
        "mentions_path": "mentions.jsonl",
    }.items():
        config["fixtures"][key] = str(fixture_copy / name)
    report = _validate(tmp_path, config)

    assert report["summary"]["ok"] is False
    failed = report["verdict"]["required_failed_checks"]
    assert "fixture_canonical_jsonl_lf_only" in failed
    assert "fixture_mentions_jsonl_lf_only" in failed
    assert "fixture_manifest_canonical_sha256_matches" not in failed
    assert "fixture_manifest_mentions_sha256_matches" not in failed


def test_reordered_fixture_records_fail_deterministic_order_gate(
    tmp_path: Path,
) -> None:
    fixture_copy = tmp_path / "fixture"
    shutil.copytree(FIXTURE_ROOT, fixture_copy)
    mentions_path = fixture_copy / "mentions.jsonl"
    lines = mentions_path.read_text(encoding="utf-8").splitlines()
    mentions_path.write_text("\n".join(reversed(lines)) + "\n", encoding="utf-8")

    manifest_path = fixture_copy / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["mentions_sha256"] = hashlib.sha256(mentions_path.read_bytes()).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    config = _base_config()
    for key, name in {
        "canonical_documents_path": "canonical_documents.jsonl",
        "extractor_descriptor_path": "extractor.json",
        "manifest_path": "manifest.json",
        "mentions_path": "mentions.jsonl",
    }.items():
        config["fixtures"][key] = str(fixture_copy / name)
    report = _validate(tmp_path, config)

    assert report["summary"]["ok"] is False
    assert "fixture_mentions_deterministically_ordered" in (
        report["verdict"]["required_failed_checks"]
    )


def test_optional_canonical_path_check_fails_for_missing_path(tmp_path: Path) -> None:
    config = _base_config()
    config["canonical_input"]["path"] = "missing/canonical.jsonl"
    config_path = _write_config(tmp_path, config)

    report = validate_contract(
        config_path=config_path,
        contract_path=CONTRACT_PATH,
        check_canonical_path=True,
        write_reports=False,
    )

    assert report["summary"]["ok"] is False
    assert "configured_canonical_path_exists" in report["verdict"]["required_failed_checks"]


def test_fixture_config_mutations_do_not_modify_repository_config(tmp_path: Path) -> None:
    before = CONFIG_PATH.read_bytes()
    config = copy.deepcopy(_base_config())
    config["layer"]["status"] = "generated"
    report = _validate(tmp_path, config)

    assert report["summary"]["ok"] is False
    assert CONFIG_PATH.read_bytes() == before
