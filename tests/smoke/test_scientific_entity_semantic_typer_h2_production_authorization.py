from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from radar_core.contracts.scientific_entity_semantic_typer_h2_production_authorization import (
    H2ProductionAuthorizationRecord,
    canonical_config_sha256,
    load_h2_production_authorization_config,
)
from radar_core.entities import scientific_entity_semantic_typer_h2_production_authorization as mod


def _write_canonical(path: Path, n: int = 3) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"canonical_id": f"paper-{i}", "title": f"Paper {i}"} for i in range(n)]
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8", newline="\n")


def _green_gate(*args, **kwargs):
    checks = [(f"check-{i}", True, "") for i in range(17)]
    summary = {
        "required_failed_count": 0,
        "total_checks": 17,
        "accepted_independent_decision_verified": True,
        "production_authorization_made": False,
        "full_corpus_candidate_build_authorized": False,
        "production_latest_promotion_authorized": False,
    }
    return checks, summary


def _prepare_project(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    (root / "configs").mkdir(parents=True)
    source_config = mod.DEFAULT_CONFIG
    auth_config = root / "configs" / source_config.name
    auth_config.write_bytes(source_config.read_bytes())
    source_gate = mod.PROJECT_ROOT / "configs" / "scientific_entity_semantic_typer_h2_production_authorization_gate_v0.3.yaml"
    target_gate = root / "configs" / source_gate.name
    target_gate.write_bytes(source_gate.read_bytes())
    canonical = root / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"
    _write_canonical(canonical)
    return root, canonical


def test_config_loads_and_is_candidate_build_only() -> None:
    config = load_h2_production_authorization_config(mod.DEFAULT_CONFIG)
    assert config.authorization_boundary.authorized_candidate_build_count == 1
    assert config.authorization_boundary.production_latest_promotion_authorized is False
    assert config.authorization_boundary.canonical_truth_mutation_allowed is False
    assert len(canonical_config_sha256(config)) == 64


def test_authorization_id_binds_canonical_sha() -> None:
    config = load_h2_production_authorization_config(mod.DEFAULT_CONFIG)
    one = mod.build_authorization_id(config, canonical_sha256="a" * 64)
    two = mod.build_authorization_id(config, canonical_sha256="b" * 64)
    assert one != two
    assert one.endswith("aaaaaaaaaaaaaaaa-6d3782fb")


def test_canonical_snapshot_hash_and_count(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    canonical = root / "canonical.jsonl"
    _write_canonical(canonical, n=4)
    snap = mod._canonical_snapshot(root, canonical)
    assert snap["document_count"] == 4
    assert snap["sha256"] == hashlib.sha256(canonical.read_bytes()).hexdigest()


def test_plan_is_non_writing_and_non_authorizing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, canonical = _prepare_project(tmp_path)
    monkeypatch.setattr(mod, "_run_gate_validation", _green_gate)
    result = mod.plan_or_execute_h2_production_authorization(
        project_root=root,
        config_path=root / "configs" / mod.DEFAULT_CONFIG.name,
        decision_dir=root / "decision",
        evaluation_dir=root / "evaluation",
        inference_dir=root / "inference",
        sample_dir=root / "sample",
        reference_dir=root / "reference",
        development_package_dir=root / "development",
        previous_heldout_sample_dir=root / "previous",
        frozen_candidate_dir=root / "frozen",
        canonical_path=canonical,
        execute=False,
    )
    assert result["mode"] == "plan"
    assert result["authorization_made"] is False
    assert result["full_corpus_candidate_build_authorized"] is False
    assert not Path(result["output_dir"]).exists()


def test_execute_writes_candidate_only_authorization(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, canonical = _prepare_project(tmp_path)
    monkeypatch.setattr(mod, "_run_gate_validation", _green_gate)
    result = mod.plan_or_execute_h2_production_authorization(
        project_root=root,
        config_path=root / "configs" / mod.DEFAULT_CONFIG.name,
        decision_dir=root / "decision",
        evaluation_dir=root / "evaluation",
        inference_dir=root / "inference",
        sample_dir=root / "sample",
        reference_dir=root / "reference",
        development_package_dir=root / "development",
        previous_heldout_sample_dir=root / "previous",
        frozen_candidate_dir=root / "frozen",
        canonical_path=canonical,
        execute=True,
    )
    assert result["phase_complete"] is True
    assert result["full_corpus_candidate_build_authorized"] is True
    assert result["production_latest_promotion_authorized"] is False
    record = H2ProductionAuthorizationRecord.model_validate(
        json.loads((Path(result["output_dir"]) / "authorization.json").read_text(encoding="utf-8"))
    )
    assert record.authorized_candidate_build_count == 1
    assert record.canonical_truth_mutated is False


def test_execute_is_one_shot_for_same_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, canonical = _prepare_project(tmp_path)
    monkeypatch.setattr(mod, "_run_gate_validation", _green_gate)
    kwargs = dict(
        project_root=root,
        config_path=root / "configs" / mod.DEFAULT_CONFIG.name,
        decision_dir=root / "decision",
        evaluation_dir=root / "evaluation",
        inference_dir=root / "inference",
        sample_dir=root / "sample",
        reference_dir=root / "reference",
        development_package_dir=root / "development",
        previous_heldout_sample_dir=root / "previous",
        frozen_candidate_dir=root / "frozen",
        canonical_path=canonical,
        execute=True,
    )
    mod.plan_or_execute_h2_production_authorization(**kwargs)
    with pytest.raises(FileExistsError):
        mod.plan_or_execute_h2_production_authorization(**kwargs)


def test_strict_validator_accepts_fresh_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, canonical = _prepare_project(tmp_path)
    monkeypatch.setattr(mod, "_run_gate_validation", _green_gate)
    result = mod.plan_or_execute_h2_production_authorization(
        project_root=root,
        config_path=root / "configs" / mod.DEFAULT_CONFIG.name,
        decision_dir=root / "decision", evaluation_dir=root / "evaluation",
        inference_dir=root / "inference", sample_dir=root / "sample",
        reference_dir=root / "reference", development_package_dir=root / "development",
        previous_heldout_sample_dir=root / "previous", frozen_candidate_dir=root / "frozen",
        canonical_path=canonical, execute=True,
    )
    checks, summary = mod.validate_h2_production_authorization(
        project_root=root,
        config_path=root / "configs" / mod.DEFAULT_CONFIG.name,
        authorization_dir=Path(result["output_dir"]),
        decision_dir=root / "decision", evaluation_dir=root / "evaluation",
        inference_dir=root / "inference", sample_dir=root / "sample",
        reference_dir=root / "reference", development_package_dir=root / "development",
        previous_heldout_sample_dir=root / "previous", frozen_candidate_dir=root / "frozen",
        canonical_path=canonical,
    )
    assert all(ok for _, ok, _ in checks)
    assert summary["required_failed_count"] == 0
    assert summary["full_corpus_candidate_build_authorized"] is True
    assert summary["production_latest_promotion_authorized"] is False


def test_validator_detects_canonical_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, canonical = _prepare_project(tmp_path)
    monkeypatch.setattr(mod, "_run_gate_validation", _green_gate)
    result = mod.plan_or_execute_h2_production_authorization(
        project_root=root,
        config_path=root / "configs" / mod.DEFAULT_CONFIG.name,
        decision_dir=root / "decision", evaluation_dir=root / "evaluation",
        inference_dir=root / "inference", sample_dir=root / "sample",
        reference_dir=root / "reference", development_package_dir=root / "development",
        previous_heldout_sample_dir=root / "previous", frozen_candidate_dir=root / "frozen",
        canonical_path=canonical, execute=True,
    )
    with canonical.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps({"canonical_id": "paper-drift"}) + "\n")
    checks, summary = mod.validate_h2_production_authorization(
        project_root=root,
        config_path=root / "configs" / mod.DEFAULT_CONFIG.name,
        authorization_dir=Path(result["output_dir"]),
        decision_dir=root / "decision", evaluation_dir=root / "evaluation",
        inference_dir=root / "inference", sample_dir=root / "sample",
        reference_dir=root / "reference", development_package_dir=root / "development",
        previous_heldout_sample_dir=root / "previous", frozen_candidate_dir=root / "frozen",
        canonical_path=canonical,
    )
    assert summary["required_failed_count"] > 0
    assert any(name == "canonical_sha_matches" and not ok for name, ok, _ in checks)
