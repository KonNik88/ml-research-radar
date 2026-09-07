from __future__ import annotations

import json
import shutil
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
from radar_core.contracts.scientific_entity_fresh_heldout_frozen_policy import (
    load_scientific_entity_fresh_heldout_frozen_policy_config,
)
from radar_core.entities import scientific_entity_fresh_heldout_frozen_policy as mod

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "scientific_entity_fresh_heldout_frozen_policy_v0.2.yaml"


def _raw_summary() -> dict:
    return {
        "candidate_id": "scientific-entity-semantic-prompt-raw-floor-extension-v0.2c",
        "sample_id": "scientific-entity-fresh-heldout-sample-v0.2-20260901T130232963026Z",
        "review_id": "scientific-entity-fresh-heldout-review-v0.2-20260901T130232963026Z",
        "build_id": "scientific-entity-gliner-small-v2.5-fresh-v0.2c-20260901T130232963026Z",
        "input_document_count": 48,
        "raw_mention_count": 1257,
        "reference_mention_count": 944,
        "model_inference_executed": True,
        "policy_applied": False,
        "evaluation_executed": False,
        "acceptance_decision_made": False,
        "required_failed_count": 0,
    }


def _copy_configs(project_root: Path) -> None:
    for relative in (
        "configs/scientific_entity_semantic_prompt_raw_floor_policy_v0.2c.yaml",
        "configs/scientific_entity_fresh_heldout_frozen_inference_v0.2.yaml",
    ):
        src = ROOT / relative
        dst = project_root / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())


def _fixture_dirs(tmp_path: Path):
    project_root = tmp_path / "project"
    sample = tmp_path / "sample"
    reference = tmp_path / "reference"
    dev = tmp_path / "dev"
    canonical = tmp_path / "canonical.jsonl"
    project_root.mkdir(); sample.mkdir(); reference.mkdir(); dev.mkdir()
    canonical.write_text("{}\n", encoding="utf-8")
    _copy_configs(project_root)
    return project_root, sample, reference, dev, canonical


def _descriptor() -> ScientificEntityExtractorDescriptor:
    return ScientificEntityExtractorDescriptor(
        schema_version=EXTRACTOR_SCHEMA_VERSION,
        name="ml_radar_gliner_small_v2_5_semantic_prompt_raw_floor_candidate",
        version="0.2.0c1",
        kind=ExtractorKind.STATISTICAL_MODEL,
        code_revision="fixture-code",
        config_sha256="b9b544194183e1cdf60a4632735acb6fe24788829bd1c75941293c5cd4360da6",
        environment_sha256="1"*64,
        model_name="gliner-community/gliner_small-v2.5",
        model_revision="f227d3cd637bd4e6757ae143935316d062393341",
        model_artifact_sha256="d444ff406b27affc07e3165b454c3adc9f25f228c81ede197a7b806f49d12c74",
        model_license="apache-2.0",
    )


def _mention(field: ScientificEntitySourceField, idx: int, score: float) -> ScientificEntityMentionEvidence:
    text = f"Entity{idx}"
    source_sha = sha256_text(text)
    mention_id = build_mention_id(
        canonical_id=f"doc-{idx}", source_field=field, source_text_sha256=source_sha,
        char_start=0, char_end=len(text), entity_type=ScientificEntityType.METHOD,
    )
    fp = "e43009f1127a445ddfd01352b47825391c2d12a2059ed53b9d35f7e5b12d8f13"
    return ScientificEntityMentionEvidence(
        schema_version=MENTION_SCHEMA_VERSION,
        evidence_id=build_evidence_id(mention_id=mention_id, extractor_fingerprint=fp),
        mention_id=mention_id,
        build_id="scientific-entity-gliner-small-v2.5-fresh-v0.2c-20260901T130232963026Z",
        canonical_id=f"doc-{idx}", entity_type=ScientificEntityType.METHOD,
        source_field=field, source_text_sha256=source_sha, char_start=0, char_end=len(text),
        surface_text=text, extractor_fingerprint=fp, confidence_kind=ConfidenceKind.MODEL_SCORE,
        confidence_score=score, calibration_id=None,
    )


def _parent_fixture(project_root: Path, rows: list[ScientificEntityMentionEvidence]) -> tuple[ScientificEntityEvidenceManifest, tuple[ScientificEntityMentionEvidence, ...], Path]:
    cfg = load_scientific_entity_fresh_heldout_frozen_policy_config(CONFIG)
    descriptor = _descriptor()
    manifest = ScientificEntityEvidenceManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        build_id=cfg.candidate.raw_build_id,
        status=EntityEvidenceBuildStatus.CANDIDATE,
        generated_at_utc="2026-09-05T08:00:00+00:00",
        canonical_input=ScientificEntityCanonicalInput(
            schema_version=CANONICAL_INPUT_SCHEMA_VERSION,
            path="fixture.jsonl", sha256="2"*64, document_count=48, canonical_contract="CanonicalDocument",
        ),
        extractor=descriptor,
        extractor_fingerprint=build_extractor_fingerprint(descriptor),
        offset_unit="unicode_codepoint", offset_interval="half_open",
        source_fields=[ScientificEntitySourceField.TITLE, ScientificEntitySourceField.ABSTRACT],
        entity_types=list(ScientificEntityType), mentions_file="mentions.jsonl", mention_count=len(rows),
        mentions_sha256="3"*64, canonical_truth_mutated=False,
        may_be_used_as_reconcile_input=False, publication_ready=False,
    )
    return manifest, tuple(rows), project_root / "raw"


def test_contract_freezes_exact_policy_and_boundary() -> None:
    cfg = load_scientific_entity_fresh_heldout_frozen_policy_config(CONFIG)
    assert cfg.candidate.expected_raw_prediction_count == 1257
    assert cfg.candidate.expected_raw_extractor_fingerprint == "e43009f1127a445ddfd01352b47825391c2d12a2059ed53b9d35f7e5b12d8f13"
    assert cfg.candidate.frozen_policy_config_sha256 == "9ad8d4f6728e49e04ed4bdc4cec6f4d2a23db82d55af71b4f71f33dabf84f62c"
    assert cfg.policy.title_threshold == 0.45
    assert cfg.policy.abstract_threshold == 0.625
    assert cfg.policy.entity_type_overrides == {}
    assert cfg.execution.plan_runs_policy_filtering is False
    assert cfg.execution.model_inference_allowed is False
    assert cfg.safety.fresh_heldout_policy_application_in_this_slice is True
    assert cfg.safety.evaluation_in_this_slice is False


def test_frozen_development_policy_config_semantics_match() -> None:
    cfg = load_scientific_entity_fresh_heldout_frozen_policy_config(CONFIG)
    info = mod._validate_frozen_policy_config(project_root=ROOT, contract=cfg)
    assert info["policy_sha256"] == cfg.candidate.frozen_policy_config_sha256


def test_thresholds_are_inclusive_and_source_specific() -> None:
    cfg = load_scientific_entity_fresh_heldout_frozen_policy_config(CONFIG)
    parents = [
        _mention(ScientificEntitySourceField.TITLE, 1, 0.45),
        _mention(ScientificEntitySourceField.TITLE, 2, 0.449999),
        _mention(ScientificEntitySourceField.ABSTRACT, 3, 0.625),
        _mention(ScientificEntitySourceField.ABSTRACT, 4, 0.624999),
    ]
    selected, _ = mod._materialize(parents, contract=cfg, build_id=cfg.execution.build_id, fingerprint="a"*64, parent_build_id=cfg.candidate.raw_build_id)
    assert [row.mention_id for row in selected] == [parents[0].mention_id, parents[2].mention_id]


def test_plan_does_not_filter_or_write(tmp_path: Path, monkeypatch) -> None:
    project_root, sample, reference, dev, canonical = _fixture_dirs(tmp_path)
    monkeypatch.setattr(mod, "_validate_raw_inference", lambda **kwargs: _raw_summary())
    called = {"load_parent": 0}
    monkeypatch.setattr(mod, "_load_parent", lambda **kwargs: called.__setitem__("load_parent", called["load_parent"] + 1))
    report = mod.plan_or_execute_frozen_policy(
        project_root=project_root, config_path=CONFIG, sample_dir=sample, reference_dir=reference,
        development_package_dir=dev, canonical_path=canonical, execute=False,
    )
    assert called["load_parent"] == 0
    assert report["plan_runs_policy_filtering"] is False
    assert report["policy_applied"] is False
    assert "selected_prediction_count" not in report
    assert report["next_slice"] == "execute_frozen_v02c_policy_once"
    assert not (project_root / "data/entities/scientific_entity_fresh_heldout_frozen_policy/v0.2" / report["build_id"]).exists()


def test_execute_applies_policy_without_model_or_evaluation(tmp_path: Path, monkeypatch) -> None:
    project_root, sample, reference, dev, canonical = _fixture_dirs(tmp_path)
    monkeypatch.setattr(mod, "_validate_raw_inference", lambda **kwargs: _raw_summary())
    cfg = load_scientific_entity_fresh_heldout_frozen_policy_config(CONFIG)
    parents = [
        _mention(ScientificEntitySourceField.TITLE, 1, 0.80),
        _mention(ScientificEntitySourceField.TITLE, 2, 0.44),
        _mention(ScientificEntitySourceField.ABSTRACT, 3, 0.70),
        _mention(ScientificEntitySourceField.ABSTRACT, 4, 0.61),
    ]
    # The real contract requires 1257 parent rows; pad with title rows below threshold.
    for idx in range(5, 1258):
        parents.append(_mention(ScientificEntitySourceField.TITLE, idx, 0.40))
    parent_manifest, parent_rows, raw_dir = _parent_fixture(project_root, parents)
    # Preserve the exact frozen raw fingerprint in the fixture manifest/rows.
    parent_manifest = parent_manifest.model_copy(update={"extractor_fingerprint": cfg.candidate.expected_raw_extractor_fingerprint})
    monkeypatch.setattr(mod, "_load_parent", lambda **kwargs: (parent_manifest, parent_rows, raw_dir))
    monkeypatch.setattr(mod, "_build_descriptor", lambda **kwargs: ScientificEntityExtractorDescriptor(
        schema_version=EXTRACTOR_SCHEMA_VERSION, name=cfg.extractor.name, version=cfg.extractor.version,
        kind=ExtractorKind.STATISTICAL_MODEL, code_revision="fixture-policy-code", config_sha256="4"*64,
        environment_sha256="1"*64, model_name="gliner-community/gliner_small-v2.5",
        model_revision="f227d3cd637bd4e6757ae143935316d062393341",
        model_artifact_sha256="d444ff406b27affc07e3165b454c3adc9f25f228c81ede197a7b806f49d12c74", model_license="apache-2.0",
    ))
    report = mod.plan_or_execute_frozen_policy(
        project_root=project_root, config_path=CONFIG, sample_dir=sample, reference_dir=reference,
        development_package_dir=dev, canonical_path=canonical, execute=True,
        generated_at_utc=__import__("datetime").datetime(2026,9,7,tzinfo=__import__("datetime").timezone.utc),
    )
    assert report["phase_complete"] is True
    assert report["policy_applied"] is True
    assert report["selected_prediction_count"] == 2
    assert report["rejected_prediction_count"] == 1255
    assert report["model_inference_executed"] is False
    assert report["threshold_tuning_executed"] is False
    assert report["reference_labels_used_for_filtering"] is False
    assert report["evaluation_executed"] is False
    assert report["next_slice"] == "validate_frozen_v02c_policy_application"
    output = project_root / cfg.execution.output_root / cfg.execution.build_id
    assert output.is_dir()
    assert len((output / "mentions.jsonl").read_text(encoding="utf-8").splitlines()) == 2


def test_execute_refuses_second_fixed_output(tmp_path: Path, monkeypatch) -> None:
    project_root, sample, reference, dev, canonical = _fixture_dirs(tmp_path)
    monkeypatch.setattr(mod, "_validate_raw_inference", lambda **kwargs: _raw_summary())
    cfg = load_scientific_entity_fresh_heldout_frozen_policy_config(CONFIG)
    output = project_root / cfg.execution.output_root / cfg.execution.build_id
    output.mkdir(parents=True)
    with pytest.raises(FileExistsError):
        mod.plan_or_execute_frozen_policy(
            project_root=project_root, config_path=CONFIG, sample_dir=sample, reference_dir=reference,
            development_package_dir=dev, canonical_path=canonical, execute=True,
        )


def test_raw_count_drift_fails_closed(tmp_path: Path, monkeypatch) -> None:
    project_root, sample, reference, dev, canonical = _fixture_dirs(tmp_path)
    bad = _raw_summary(); bad["raw_mention_count"] = 1256
    monkeypatch.setattr(mod, "_validate_raw_inference", lambda **kwargs: bad)
    with pytest.raises(ValueError, match="raw inference lineage"):
        mod.plan_or_execute_frozen_policy(
            project_root=project_root, config_path=CONFIG, sample_dir=sample, reference_dir=reference,
            development_package_dir=dev, canonical_path=canonical, execute=False,
        )


def test_test_outputs_are_isolated_from_repository_tree(tmp_path: Path) -> None:
    project_root, *_ = _fixture_dirs(tmp_path)
    cfg = load_scientific_entity_fresh_heldout_frozen_policy_config(CONFIG)
    output = (project_root / cfg.execution.output_root / cfg.execution.build_id).resolve()
    assert output.is_relative_to(project_root.resolve())
    assert not output.is_relative_to(ROOT.resolve())

def test_execute_then_validator_round_trip_is_green(tmp_path: Path, monkeypatch) -> None:
    project_root, sample, reference, dev, canonical = _fixture_dirs(tmp_path)
    monkeypatch.setattr(mod, "_validate_raw_inference", lambda **kwargs: _raw_summary())
    cfg = load_scientific_entity_fresh_heldout_frozen_policy_config(CONFIG)
    parents = [
        _mention(ScientificEntitySourceField.TITLE, 1, 0.45),
        _mention(ScientificEntitySourceField.TITLE, 2, 0.44),
        _mention(ScientificEntitySourceField.ABSTRACT, 3, 0.625),
        _mention(ScientificEntitySourceField.ABSTRACT, 4, 0.61),
    ]
    for idx in range(5, 1258):
        parents.append(_mention(ScientificEntitySourceField.TITLE, idx, 0.40))
    parent_manifest, parent_rows, raw_dir = _parent_fixture(project_root, parents)
    parent_manifest = parent_manifest.model_copy(update={"extractor_fingerprint": cfg.candidate.expected_raw_extractor_fingerprint})
    monkeypatch.setattr(mod, "_load_parent", lambda **kwargs: (parent_manifest, parent_rows, raw_dir))
    policy_descriptor = ScientificEntityExtractorDescriptor(
        schema_version=EXTRACTOR_SCHEMA_VERSION, name=cfg.extractor.name, version=cfg.extractor.version,
        kind=ExtractorKind.STATISTICAL_MODEL, code_revision="fixture-policy-code", config_sha256="4"*64,
        environment_sha256="1"*64, model_name="gliner-community/gliner_small-v2.5",
        model_revision="f227d3cd637bd4e6757ae143935316d062393341",
        model_artifact_sha256="d444ff406b27affc07e3165b454c3adc9f25f228c81ede197a7b806f49d12c74", model_license="apache-2.0",
    )
    monkeypatch.setattr(mod, "_build_descriptor", lambda **kwargs: policy_descriptor)
    mod.plan_or_execute_frozen_policy(
        project_root=project_root, config_path=CONFIG, sample_dir=sample, reference_dir=reference,
        development_package_dir=dev, canonical_path=canonical, execute=True,
        generated_at_utc=__import__("datetime").datetime(2026,9,7,tzinfo=__import__("datetime").timezone.utc),
    )
    checks, summary = mod.validate_frozen_policy_build(
        project_root=project_root, config_path=CONFIG, sample_dir=sample, reference_dir=reference,
        development_package_dir=dev, canonical_path=canonical,
    )
    assert all(ok for _, ok, _ in checks)
    assert summary["required_failed_count"] == 0
    assert summary["selected_prediction_count"] == 2
    assert summary["rejected_prediction_count"] == 1255
    assert summary["policy_applied"] is True
    assert summary["evaluation_executed"] is False
    assert summary["next_slice"] == "evaluate_frozen_v02c_on_fresh_heldout_once"

