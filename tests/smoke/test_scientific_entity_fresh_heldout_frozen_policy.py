from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from radar_core.contracts.scientific_entity_evidence import (
    ConfidenceKind,
    MENTION_SCHEMA_VERSION,
    ScientificEntityMentionEvidence,
    ScientificEntitySourceField,
    ScientificEntityType,
    build_evidence_id,
    build_mention_id,
    sha256_text,
)
from radar_core.contracts.scientific_entity_fresh_heldout_frozen_policy import (
    load_scientific_entity_fresh_heldout_frozen_policy_config,
)
from radar_core.entities import scientific_entity_fresh_heldout_frozen_policy as mod
from scripts.entities.apply_scientific_entity_fresh_heldout_frozen_policy import build_parser

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "scientific_entity_fresh_heldout_frozen_policy_v0.2.yaml"


def _mention(field, kind, score, span=(0, 5)):
    text = "Alpha Beta Gamma"
    source_sha = sha256_text(text)
    mention_id = build_mention_id(
        canonical_id="fixture-doc",
        source_field=field,
        source_text_sha256=source_sha,
        char_start=span[0],
        char_end=span[1],
        entity_type=kind,
    )
    fingerprint = "a" * 64
    return ScientificEntityMentionEvidence(
        schema_version=MENTION_SCHEMA_VERSION,
        evidence_id=build_evidence_id(mention_id=mention_id, extractor_fingerprint=fingerprint),
        mention_id=mention_id,
        build_id="raw-build",
        canonical_id="fixture-doc",
        entity_type=kind,
        source_field=field,
        source_text_sha256=source_sha,
        char_start=span[0],
        char_end=span[1],
        surface_text=text[span[0]:span[1]],
        extractor_fingerprint=fingerprint,
        confidence_kind=ConfidenceKind.MODEL_SCORE,
        confidence_score=score,
        calibration_id=None,
    )


def test_config_pins_exact_fresh_v02c_policy() -> None:
    c = load_scientific_entity_fresh_heldout_frozen_policy_config(CONFIG)
    assert c.candidate.expected_raw_mention_count == 1257
    assert c.candidate.expected_raw_extractor_fingerprint == "e43009f1127a445ddfd01352b47825391c2d12a2059ed53b9d35f7e5b12d8f13"
    assert c.fresh_heldout.expected_reference_mention_count == 944
    assert c.policy_origin.source_field_thresholds[ScientificEntitySourceField.TITLE] == 0.45
    assert c.policy_origin.source_field_thresholds[ScientificEntitySourceField.ABSTRACT] == 0.625
    assert c.policy_origin.entity_type_thresholds == {}
    assert c.safety.reference_comparison_allowed is False
    assert c.safety.evaluation_in_this_slice is False


def test_config_rejects_threshold_drift(tmp_path: Path) -> None:
    payload = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    payload["policy_origin"]["source_field_thresholds"]["abstract"] = 0.65
    p = tmp_path / "bad.yaml"
    p.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    with pytest.raises(Exception):
        load_scientific_entity_fresh_heldout_frozen_policy_config(p)


def test_cli_has_no_threshold_or_evaluation_override() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--abstract-threshold", "0.70"])
    with pytest.raises(SystemExit):
        parser.parse_args(["--evaluate"])


def test_materialize_applies_inclusive_title_and_abstract_thresholds() -> None:
    c = load_scientific_entity_fresh_heldout_frozen_policy_config(CONFIG)
    parents = [
        _mention(ScientificEntitySourceField.TITLE, ScientificEntityType.MODEL, 0.45, (0, 5)),
        _mention(ScientificEntitySourceField.TITLE, ScientificEntityType.METHOD, 0.449, (6, 10)),
        _mention(ScientificEntitySourceField.ABSTRACT, ScientificEntityType.TASK, 0.625, (0, 5)),
        _mention(ScientificEntitySourceField.ABSTRACT, ScientificEntityType.METRIC, 0.624, (11, 16)),
    ]
    rows, lineage = mod._materialize(
        parents=parents,
        contract=c,
        build_id="policy-build",
        fingerprint="b" * 64,
    )
    assert len(rows) == 2
    assert len(lineage) == 2
    assert {row.confidence_score for row in rows} == {0.45, 0.625}
    parent_by_id = {row.mention_id: row for row in parents}
    assert all(row.mention_id in parent_by_id for row in rows)
    assert all(row.confidence_score == parent_by_id[row.mention_id].confidence_score for row in rows)
    assert all(row.evidence_id != parent_by_id[row.mention_id].evidence_id for row in rows)


def test_plan_is_nonwriting_noninference_nonevaluation(tmp_path: Path, monkeypatch) -> None:
    c = load_scientific_entity_fresh_heldout_frozen_policy_config(CONFIG)
    raw = [_mention(ScientificEntitySourceField.TITLE, ScientificEntityType.MODEL, 0.7)]
    parent_manifest = type("Manifest", (), {
        "build_id": c.candidate.raw_build_id,
        "extractor_fingerprint": c.candidate.expected_raw_extractor_fingerprint,
    })()
    monkeypatch.setattr(mod, "_validate_policy_origin", lambda *a, **k: {
        "semantic_sha256": c.policy_origin.development_policy_config_sha256,
        "calibration_id": c.policy_origin.calibration_id,
        "selected_trial_id": c.policy_origin.selected_trial_id,
    })
    monkeypatch.setattr(mod, "_validate_raw_parent", lambda *a, **k: (
        parent_manifest,
        tuple(raw),
        {"reference_mention_count": 944, "required_failed_count": 0},
    ))
    monkeypatch.setattr(mod, "build_policy_filtered_extractor_descriptor", lambda **k: type("D", (), {})())
    monkeypatch.setattr(mod, "build_extractor_fingerprint", lambda x: "b" * 64)
    monkeypatch.setattr(mod, "_materialize", lambda **k: (tuple(raw), tuple()))

    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    cfg["execution"]["output_root"] = str(tmp_path / "outputs").replace("\\", "/")
    # Preserve strict Literal output_root by routing project_root instead; the real fixed path
    # is now under tmp_path and no repository data path is touched.
    project_root = tmp_path
    (project_root / "configs").mkdir(parents=True)
    policy_cfg = project_root / "configs" / CONFIG.name
    policy_cfg.write_text(CONFIG.read_text(encoding="utf-8"), encoding="utf-8")

    report = mod.plan_or_execute_frozen_policy(
        project_root=project_root,
        config_path=policy_cfg,
        sample_dir=tmp_path,
        reference_dir=tmp_path,
        development_package_dir=tmp_path,
        canonical_path=tmp_path / "canonical.jsonl",
        execute=False,
    )
    assert report["phase_complete"] is False
    assert report["plan_runs_model_inference"] is False
    assert report["new_model_inference_executed"] is False
    assert report["reference_comparison_executed"] is False
    assert report["evaluation_executed"] is False
    assert report["next_slice"] == "execute_frozen_v02c_policy_once"
    assert not Path(report["output_dir"]).exists()


def test_execute_and_validator_are_deterministic_without_evaluation(tmp_path: Path, monkeypatch) -> None:
    from datetime import datetime, timezone
    from radar_core.contracts.scientific_entity_evidence import (
        CANONICAL_INPUT_SCHEMA_VERSION,
        EXTRACTOR_SCHEMA_VERSION,
        MANIFEST_SCHEMA_VERSION,
        EntityEvidenceBuildStatus,
        ExtractorKind,
        ScientificEntityCanonicalInput,
        ScientificEntityEvidenceManifest,
        ScientificEntityExtractorDescriptor,
        build_extractor_fingerprint,
    )

    project_root = tmp_path / "project"
    project_root.mkdir()
    config_dir = project_root / "configs"
    config_dir.mkdir()
    config_path = config_dir / CONFIG.name
    config_path.write_text(CONFIG.read_text(encoding="utf-8"), encoding="utf-8")
    c = load_scientific_entity_fresh_heldout_frozen_policy_config(config_path)

    parent_descriptor = ScientificEntityExtractorDescriptor(
        schema_version=EXTRACTOR_SCHEMA_VERSION,
        name="fixture_raw_gliner",
        version="0.0.1",
        kind=ExtractorKind.STATISTICAL_MODEL,
        code_revision="fixture-code",
        config_sha256="1" * 64,
        environment_sha256="2" * 64,
        model_name="fixture-model",
        model_revision="fixture-revision",
        model_artifact_sha256="3" * 64,
        model_license="fixture-license",
    )
    parent_fingerprint = build_extractor_fingerprint(parent_descriptor)
    canonical_input = ScientificEntityCanonicalInput(
        schema_version=CANONICAL_INPUT_SCHEMA_VERSION,
        path="fixture/sample.jsonl",
        sha256="4" * 64,
        document_count=48,
        canonical_contract="CanonicalDocument",
    )

    parents = []
    for i in range(1257):
        text = "Alpha Beta Gamma"
        field = ScientificEntitySourceField.TITLE if i % 2 == 0 else ScientificEntitySourceField.ABSTRACT
        kind = list(ScientificEntityType)[i % len(ScientificEntityType)]
        source_sha = sha256_text(text)
        mention_id = build_mention_id(
            canonical_id=f"fixture-doc-{i:04d}",
            source_field=field,
            source_text_sha256=source_sha,
            char_start=0,
            char_end=5,
            entity_type=kind,
        )
        parents.append(ScientificEntityMentionEvidence(
            schema_version=MENTION_SCHEMA_VERSION,
            evidence_id=build_evidence_id(mention_id=mention_id, extractor_fingerprint=parent_fingerprint),
            mention_id=mention_id,
            build_id=c.candidate.raw_build_id,
            canonical_id=f"fixture-doc-{i:04d}",
            entity_type=kind,
            source_field=field,
            source_text_sha256=source_sha,
            char_start=0,
            char_end=5,
            surface_text="Alpha",
            extractor_fingerprint=parent_fingerprint,
            confidence_kind=ConfidenceKind.MODEL_SCORE,
            confidence_score=0.7,
            calibration_id=None,
        ))

    raw_root = project_root / c.candidate.raw_build_root / c.candidate.raw_build_id
    raw_root.mkdir(parents=True)
    raw_mentions = "".join(
        json.dumps(row.model_dump(mode="json"), sort_keys=True, separators=(",", ":")) + "\n"
        for row in parents
    )
    (raw_root / "mentions.jsonl").write_text(raw_mentions, encoding="utf-8", newline="\n")
    (raw_root / "manifest.json").write_text("{}\n", encoding="utf-8", newline="\n")

    parent_manifest = ScientificEntityEvidenceManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        build_id=c.candidate.raw_build_id,
        status=EntityEvidenceBuildStatus.CANDIDATE,
        generated_at_utc=datetime(2026, 9, 6, tzinfo=timezone.utc),
        canonical_input=canonical_input,
        extractor=parent_descriptor,
        extractor_fingerprint=parent_fingerprint,
        offset_unit="unicode_codepoint",
        offset_interval="half_open",
        source_fields=[ScientificEntitySourceField.TITLE, ScientificEntitySourceField.ABSTRACT],
        entity_types=list(ScientificEntityType),
        mentions_file="mentions.jsonl",
        mention_count=1257,
        mentions_sha256="5" * 64,
        canonical_truth_mutated=False,
        may_be_used_as_reconcile_input=False,
        publication_ready=False,
    )

    policy_descriptor = ScientificEntityExtractorDescriptor(
        schema_version=EXTRACTOR_SCHEMA_VERSION,
        name=c.extractor.name,
        version=c.extractor.version,
        kind=ExtractorKind.STATISTICAL_MODEL,
        code_revision="fixture-policy-code",
        config_sha256="6" * 64,
        environment_sha256="2" * 64,
        model_name="fixture-model",
        model_revision="fixture-revision",
        model_artifact_sha256="3" * 64,
        model_license="fixture-license",
    )

    monkeypatch.setattr(mod, "_validate_policy_origin", lambda *a, **k: {
        "semantic_sha256": c.policy_origin.development_policy_config_sha256,
        "calibration_id": c.policy_origin.calibration_id,
        "selected_trial_id": c.policy_origin.selected_trial_id,
    })
    monkeypatch.setattr(mod, "_validate_raw_parent", lambda *a, **k: (
        parent_manifest,
        tuple(parents),
        {"reference_mention_count": 944, "required_failed_count": 0},
    ))
    monkeypatch.setattr(mod, "build_policy_filtered_extractor_descriptor", lambda **k: policy_descriptor)
    monkeypatch.setattr(mod, "fresh_policy_config_sha256", lambda contract: policy_descriptor.config_sha256)

    report = mod.plan_or_execute_frozen_policy(
        project_root=project_root,
        config_path=config_path,
        sample_dir=tmp_path,
        reference_dir=tmp_path,
        development_package_dir=tmp_path,
        canonical_path=tmp_path / "canonical.jsonl",
        execute=True,
        generated_at_utc=datetime(2026, 9, 6, tzinfo=timezone.utc),
    )
    assert report["phase_complete"] is True
    assert report["selected_prediction_count"] == 1257
    assert report["rejected_prediction_count"] == 0
    assert report["new_model_inference_executed"] is False
    assert report["evaluation_executed"] is False

    checks, summary = mod.validate_frozen_policy_application(
        project_root=project_root,
        config_path=config_path,
        sample_dir=tmp_path,
        reference_dir=tmp_path,
        development_package_dir=tmp_path,
        canonical_path=tmp_path / "canonical.jsonl",
    )
    assert summary["required_failed_count"] == 0, [x for x in checks if not x[1]]
    assert summary["selected_prediction_count"] == 1257
    assert summary["evaluation_executed"] is False
    assert summary["next_slice"] == "evaluate_frozen_v02c_policy_once"
