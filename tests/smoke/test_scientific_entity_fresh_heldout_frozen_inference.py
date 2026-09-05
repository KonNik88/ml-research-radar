from __future__ import annotations

import json
from pathlib import Path

import pytest

from radar_core.contracts.scientific_entity_fresh_heldout_frozen_inference import (
    load_scientific_entity_fresh_heldout_frozen_inference_config,
)
from radar_core.entities import scientific_entity_fresh_heldout_frozen_inference as mod

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "scientific_entity_fresh_heldout_frozen_inference_v0.2.yaml"


def _reference_summary():
    return {
        "sample_id": "scientific-entity-fresh-heldout-sample-v0.2-20260901T130232963026Z",
        "review_id": "scientific-entity-fresh-heldout-review-v0.2-20260901T130232963026Z",
        "document_count": 48,
        "annotation_row_count": 96,
        "reference_mention_count": 944,
        "uncertain_reference_mention_count": 0,
        "reference_count_by_type": {"task":150,"method":279,"dataset":66,"metric":86,"model":280,"domain":83},
        "reference_adequacy_passed": True,
        "prediction_blind": True,
        "model_inference_executed": False,
        "evaluation_executed": False,
        "required_failed_count": 0,
    }


def _fixture_dirs(tmp_path: Path):
    project_root = tmp_path / "project"
    sample = tmp_path / "sample"
    reference = tmp_path / "reference"
    dev = tmp_path / "dev"
    canonical = tmp_path / "canonical.jsonl"

    project_root.mkdir()
    sample.mkdir()
    reference.mkdir()
    dev.mkdir()
    (sample / "canonical_documents.sample.jsonl").write_text("{}\n", encoding="utf-8")
    canonical.write_text("{}\n", encoding="utf-8")

    # Runtime validation still uses the real frozen config semantics, but every
    # writable path is rooted under pytest's tmp_path. Tests must never touch
    # the real one-shot held-out artifact under the repository data/ tree.
    runtime_rel = Path(
        "configs/scientific_entity_gliner_semantic_prompt_raw_floor_candidate_v0.2c.yaml"
    )
    runtime_src = ROOT / runtime_rel
    runtime_dst = project_root / runtime_rel
    runtime_dst.parent.mkdir(parents=True, exist_ok=True)
    runtime_dst.write_bytes(runtime_src.read_bytes())

    return project_root, sample, reference, dev, canonical


def test_contract_freezes_exact_candidate_and_one_shot_boundary() -> None:
    cfg = load_scientific_entity_fresh_heldout_frozen_inference_config(CONFIG)
    assert cfg.candidate.runtime_config_sha256 == "b9b544194183e1cdf60a4632735acb6fe24788829bd1c75941293c5cd4360da6"
    assert cfg.candidate.raw_inference_floor == 0.4
    assert cfg.candidate.title_policy_threshold_after_raw_validation == 0.45
    assert cfg.candidate.abstract_policy_threshold_after_raw_validation == 0.625
    assert cfg.execution.max_documents == 48
    assert cfg.execution.one_shot_execute is True
    assert cfg.execution.plan_runs_model_inference is False
    assert cfg.safety.policy_application_in_this_slice is False
    assert cfg.safety.evaluation_in_this_slice is False


def test_runtime_config_semantic_sha_matches_frozen_v02c() -> None:
    cfg = load_scientific_entity_fresh_heldout_frozen_inference_config(CONFIG)
    info = mod._validate_runtime_config(project_root=ROOT, contract=cfg)
    assert info["runtime_sha256"] == cfg.candidate.runtime_config_sha256


def test_plan_is_non_inference_and_non_writing(tmp_path: Path, monkeypatch) -> None:
    project_root, sample, reference, dev, canonical = _fixture_dirs(tmp_path)
    monkeypatch.setattr(mod, "_validate_reference", lambda **kwargs: _reference_summary())
    called = {"builder": 0}
    monkeypatch.setattr(mod, "_run_existing_builder", lambda **kwargs: called.__setitem__("builder", called["builder"] + 1))
    report = mod.plan_or_execute_frozen_inference(
        project_root=project_root, config_path=CONFIG, sample_dir=sample, reference_dir=reference,
        development_package_dir=dev, canonical_path=canonical, execute=False,
    )
    assert called["builder"] == 0
    assert report["phase_complete"] is False
    assert report["plan_runs_model_inference"] is False
    assert report["model_inference_executed"] is False
    assert report["next_slice"] == "execute_frozen_v02c_raw_inference_once"


def test_execute_calls_existing_builder_with_exact_frozen_arguments(tmp_path: Path, monkeypatch) -> None:
    project_root, sample, reference, dev, canonical = _fixture_dirs(tmp_path)
    monkeypatch.setattr(mod, "_validate_reference", lambda **kwargs: _reference_summary())
    captured = {}
    def fake_builder(**kwargs):
        captured.update(kwargs)
        return {
            "build_id": "scientific-entity-gliner-small-v2.5-fresh-v0.2c-20260901T130232963026Z",
            "input_document_count": 48,
            "config_sha256": "b9b544194183e1cdf60a4632735acb6fe24788829bd1c75941293c5cd4360da6",
            "mention_count": 321,
            "extractor_fingerprint": "a"*64,
            "model_artifact_verified": True,
            "backbone_config_verified": True,
            "runtime_device_name": "fixture-cuda",
            "inference_duration_seconds": 1.0,
            "peak_cuda_memory_bytes": 1,
        }
    monkeypatch.setattr(mod, "_run_existing_builder", fake_builder)
    report = mod.plan_or_execute_frozen_inference(
        project_root=project_root, config_path=CONFIG, sample_dir=sample, reference_dir=reference,
        development_package_dir=dev, canonical_path=canonical, execute=True,
    )
    assert captured["max_documents"] == 48
    assert captured["status"] == "candidate"
    assert captured["execute"] is True
    assert captured["input_path"] == (sample / "canonical_documents.sample.jsonl")
    assert report["model_inference_executed"] is True
    assert report["raw_mention_count"] == 321
    assert report["policy_applied"] is False
    assert report["evaluation_executed"] is False
    assert report["next_slice"] == "validate_frozen_v02c_raw_inference"
    assert Path(captured["output_root"]).resolve().is_relative_to(project_root.resolve())
    assert not Path(captured["output_root"]).resolve().is_relative_to(ROOT.resolve())


def test_execute_refuses_second_run_when_fixed_output_exists(tmp_path: Path, monkeypatch) -> None:
    project_root, sample, reference, dev, canonical = _fixture_dirs(tmp_path)
    monkeypatch.setattr(mod, "_validate_reference", lambda **kwargs: _reference_summary())
    cfg = load_scientific_entity_fresh_heldout_frozen_inference_config(CONFIG)
    output = project_root / cfg.execution.raw_output_root / cfg.execution.build_id
    output.mkdir(parents=True, exist_ok=True)
    try:
        with pytest.raises(FileExistsError):
            mod.plan_or_execute_frozen_inference(
                project_root=project_root, config_path=CONFIG, sample_dir=sample, reference_dir=reference,
                development_package_dir=dev, canonical_path=canonical, execute=True,
            )
    finally:
        output.rmdir()


def test_reference_drift_fails_closed(tmp_path: Path, monkeypatch) -> None:
    project_root, sample, reference, dev, canonical = _fixture_dirs(tmp_path)
    bad = _reference_summary(); bad["reference_mention_count"] = 943
    monkeypatch.setattr(mod, "_validate_reference", lambda **kwargs: bad)
    with pytest.raises(ValueError, match="reference lineage"):
        mod.plan_or_execute_frozen_inference(
            project_root=project_root, config_path=CONFIG, sample_dir=sample, reference_dir=reference,
            development_package_dir=dev, canonical_path=canonical, execute=False,
        )


def test_post_validator_combines_raw_and_reference_lineage(tmp_path: Path, monkeypatch) -> None:
    project_root, sample, reference, dev, canonical = _fixture_dirs(tmp_path)
    monkeypatch.setattr(mod, "_validate_reference", lambda **kwargs: _reference_summary())
    cfg = load_scientific_entity_fresh_heldout_frozen_inference_config(CONFIG)
    build = project_root / cfg.execution.raw_output_root / cfg.execution.build_id
    build.mkdir(parents=True, exist_ok=True)
    manifest = {
        "build_id": cfg.execution.build_id,
        "status": "candidate",
        "canonical_input": {"path": str((sample/"canonical_documents.sample.jsonl").resolve()), "document_count": 48},
        "extractor": {"config_sha256": cfg.candidate.runtime_config_sha256, "model_name": cfg.candidate.model_repository,
                      "model_revision": cfg.candidate.model_revision, "model_artifact_sha256": cfg.candidate.model_artifact_sha256},
        "mention_count": 321,
        "canonical_truth_mutated": False,
    }
    quality = {"threshold":0.4,"window_size_tokens":320,"window_overlap_tokens":64}
    (build/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    (build/'data_quality_summary.json').write_text(json.dumps(quality),encoding='utf-8')
    monkeypatch.setattr(mod, "_validate_existing_build", lambda **kwargs: {"required_failed_count":0})
    try:
        checks, summary = mod.validate_frozen_inference(
            project_root=project_root, config_path=CONFIG, sample_dir=sample, reference_dir=reference,
            development_package_dir=dev, canonical_path=canonical,
        )
        assert all(ok for _,ok,_ in checks)
        assert summary["required_failed_count"] == 0
        assert summary["raw_mention_count"] == 321
        assert summary["policy_applied"] is False
        assert summary["next_slice"] == "apply_frozen_v02c_policy_once"
    finally:
        shutil = __import__("shutil")
        shutil.rmtree(build)


def test_fixture_execute_paths_never_target_repository_data_tree(tmp_path: Path, monkeypatch) -> None:
    project_root, sample, reference, dev, canonical = _fixture_dirs(tmp_path)
    monkeypatch.setattr(mod, "_validate_reference", lambda **kwargs: _reference_summary())

    captured = {}

    def fake_builder(**kwargs):
        captured.update(kwargs)
        return {
            "build_id": "scientific-entity-gliner-small-v2.5-fresh-v0.2c-20260901T130232963026Z",
            "input_document_count": 48,
            "config_sha256": "b9b544194183e1cdf60a4632735acb6fe24788829bd1c75941293c5cd4360da6",
            "mention_count": 1,
            "extractor_fingerprint": "a" * 64,
            "model_artifact_verified": True,
            "backbone_config_verified": True,
            "runtime_device_name": "fixture",
            "inference_duration_seconds": 0.0,
            "peak_cuda_memory_bytes": 0,
        }

    monkeypatch.setattr(mod, "_run_existing_builder", fake_builder)

    mod.plan_or_execute_frozen_inference(
        project_root=project_root,
        config_path=CONFIG,
        sample_dir=sample,
        reference_dir=reference,
        development_package_dir=dev,
        canonical_path=canonical,
        execute=True,
    )

    output_root = Path(captured["output_root"]).resolve()
    assert output_root.is_relative_to(project_root.resolve())
    assert not output_root.is_relative_to(ROOT.resolve())
