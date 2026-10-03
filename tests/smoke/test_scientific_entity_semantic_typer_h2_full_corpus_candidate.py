from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import pytest

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
from radar_core.contracts.scientific_entity_semantic_typer_candidate import load_semantic_typer_config
from radar_core.contracts.scientific_entity_semantic_typer_h2_full_corpus_candidate import (
    H2FullCorpusFinalMention,
    load_h2_full_corpus_candidate_config,
)
from radar_core.entities.scientific_entity_gliner import PreparedText
from radar_core.entities.scientific_entity_semantic_prompt_raw_floor_policy import (
    load_raw_floor_policy_config,
)
from radar_core.entities.scientific_entity_semantic_typer_h2_full_corpus_candidate import (
    _final_row,
    plan_or_execute_h2_full_corpus_candidate,
    validate_h2_full_corpus_candidate,
)
import radar_core.entities.scientific_entity_semantic_typer_h2_full_corpus_candidate as mod

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "scientific_entity_semantic_typer_h2_full_corpus_candidate_v0.3.yaml"
SEMANTIC_CONFIG = ROOT / "configs" / "scientific_entity_semantic_typer_candidate_v0.3.yaml"
POLICY_CONFIG = ROOT / "configs" / "scientific_entity_semantic_prompt_raw_floor_policy_v0.2c.yaml"
FIXED = datetime(2026, 10, 3, 12, 0, 0, tzinfo=timezone.utc)


class FakeSemanticBackend:
    model_max_tokens = 384
    model_max_width = 12

    def __init__(self, scores: Mapping[str, float]) -> None:
        self.scores = dict(scores)

    def prepare_text(self, text: str, labels: Sequence[str]) -> PreparedText:
        del labels
        matches = list(re.finditer(r"\w+|[^\w\s]", text, flags=re.UNICODE))
        return PreparedText(
            tokens=tuple(match.group(0) for match in matches),
            token_starts=tuple(match.start() for match in matches),
            token_ends=tuple(match.end() for match in matches),
        )

    def predict_entities(self, text: str, labels: Sequence[str], *, threshold: float, flat_ner: bool, multi_label: bool):
        assert threshold == 0.0
        start = len("Target entity: ")
        end = text.index("\n", start)
        surface = text[start:end]
        return [
            {"start": start, "end": end, "text": surface, "label": label, "score": self.scores[label]}
            for label in labels
            if label in self.scores
        ]


def test_config_binds_exact_authorization_canonical_and_h2_policy() -> None:
    config = load_h2_full_corpus_candidate_config(CONFIG)
    assert config.authorization.authorization_id.endswith("3cc6e3c779fee351-6d3782fb")
    assert config.canonical_snapshot.document_count == 61075
    assert config.canonical_snapshot.sha256 == "3cc6e3c779fee351bcab605ad1b804acf0e4f8365718db96dad398959420b6ff"
    assert config.frozen_h2.baseline_type == ScientificEntityType.METHOD
    assert config.frozen_h2.semantic_typer_type == ScientificEntityType.MODEL
    assert config.frozen_h2.threshold == 0.1
    assert config.safety.production_latest_promotion_authorized is False


def test_semantic_scope_is_method_only_semantics_preserving() -> None:
    config = load_h2_full_corpus_candidate_config(CONFIG)
    assert config.frozen_h2.semantic_typer_scope == "baseline_method_mentions_only_semantics_preserving_optimization"
    assert config.frozen_h2.preserve_baseline_otherwise is True
    assert config.frozen_h2.span_mutation_allowed is False


def test_final_contract_rejects_non_method_override() -> None:
    payload = {
        "build_id": "build-1",
        "candidate_evidence_id": "evidence:" + "1" * 32,
        "final_mention_id": "mention:" + "2" * 32,
        "canonical_id": "paper-1",
        "source_field": "title",
        "source_text_sha256": "3" * 64,
        "char_start": 0,
        "char_end": 4,
        "surface_text": "BERT",
        "baseline_prediction_evidence_id": "evidence:" + "4" * 32,
        "baseline_entity_type": "task",
        "baseline_confidence_score": 0.9,
        "semantic_typer_case_id": "case-1",
        "semantic_typer_predicted_entity_type": "model",
        "semantic_typer_used_baseline_fallback": False,
        "semantic_typer_score_margin": 0.5,
        "h2_override_applied": True,
        "final_entity_type": "model",
        "materialization_fingerprint_sha256": "5" * 64,
    }
    with pytest.raises(Exception):
        H2FullCorpusFinalMention.model_validate(payload)


def _fake_parent() -> dict[str, Any]:
    config = load_h2_full_corpus_candidate_config(CONFIG)
    semantic = load_semantic_typer_config(SEMANTIC_CONFIG)
    policy = load_raw_floor_policy_config(POLICY_CONFIG)
    return {
        "config": config,
        "authorization_summary": {"required_failed_count": 0, "total_checks": 30},
        "canonical_sha": config.canonical_snapshot.sha256,
        "canonical_count": config.canonical_snapshot.document_count,
        "runtime_config": object(),
        "runtime_sha": config.frozen_runtime.runtime_config_sha256,
        "policy_config": policy,
        "policy_sha": config.frozen_runtime.baseline_policy_config_sha256,
        "semantic_config": semantic,
        "semantic_sha": config.frozen_runtime.semantic_typer_config_sha256,
        "semantic_fp": config.frozen_runtime.semantic_typer_fingerprint_sha256,
    }


def test_plan_is_non_writing_and_does_not_load_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(mod, "_validate_parent", lambda **kwargs: _fake_parent())
    monkeypatch.setattr(mod, "load_native_gliner_backend", lambda **kwargs: (_ for _ in ()).throw(AssertionError("model load forbidden in plan")))
    report = plan_or_execute_h2_full_corpus_candidate(
        project_root=ROOT,
        config_path=CONFIG,
        authorization_dir=tmp_path / "auth",
        decision_dir=tmp_path / "decision",
        evaluation_dir=tmp_path / "eval",
        inference_dir=tmp_path / "inf",
        sample_dir=tmp_path / "sample",
        reference_dir=tmp_path / "reference",
        development_package_dir=tmp_path / "dev",
        previous_heldout_sample_dir=tmp_path / "prev",
        frozen_candidate_dir=tmp_path / "frozen",
        canonical_path=tmp_path / "canonical.jsonl",
        output_root=tmp_path / "out",
        build_id="candidate-plan",
        execute=False,
        generated_at_utc=FIXED,
    )
    assert report["mode"] == "plan"
    assert report["plan_runs_model_inference"] is False
    assert report["plan_writes_candidate"] is False
    assert report["candidate_build_executed"] is False
    assert not (tmp_path / "out").exists()


def test_final_row_preserves_non_method_identity_and_override_changes_method_identity() -> None:
    from radar_core.contracts.scientific_entity_semantic_typer_candidate import SemanticTyperPrediction
    from radar_core.contracts.scientific_entity_semantic_typer_h2_full_corpus_candidate import H2FullCorpusCase

    text = "BERT task"
    sha = sha256_text(text)
    task_mid = build_mention_id(canonical_id="p", source_field="title", source_text_sha256=sha, char_start=0, char_end=4, entity_type="task")
    task = ScientificEntityMentionEvidence(
        schema_version=MENTION_SCHEMA_VERSION,
        evidence_id=build_evidence_id(mention_id=task_mid, extractor_fingerprint="a" * 64),
        mention_id=task_mid,
        build_id="raw",
        canonical_id="p",
        entity_type="task",
        source_field="title",
        source_text_sha256=sha,
        char_start=0,
        char_end=4,
        surface_text="BERT",
        extractor_fingerprint="a" * 64,
        confidence_kind=ConfidenceKind.MODEL_SCORE,
        confidence_score=0.9,
        calibration_id=None,
    )
    preserved = _final_row(build_id="b", baseline=task, materialization_fingerprint="b" * 64, semantic_case=None, semantic_prediction=None, override=False)
    assert preserved.final_mention_id == task.mention_id
    assert preserved.final_entity_type == ScientificEntityType.TASK

    method_mid = build_mention_id(canonical_id="p", source_field="title", source_text_sha256=sha, char_start=0, char_end=4, entity_type="method")
    method = task.model_copy(update={
        "mention_id": method_mid,
        "evidence_id": build_evidence_id(mention_id=method_mid, extractor_fingerprint="a" * 64),
        "entity_type": ScientificEntityType.METHOD,
    })
    case = H2FullCorpusCase(
        case_id="case-1",
        canonical_id="p",
        source_field="title",
        source_text_sha256=sha,
        baseline_prediction_evidence_id=method.evidence_id,
        char_start=0,
        char_end=4,
        surface_text="BERT",
        baseline_entity_type="method",
        baseline_confidence_score=0.9,
        left_context="",
        right_context=" task",
    )
    pred = SemanticTyperPrediction(
        case_id="case-1",
        candidate_id="scientific-entity-semantic-typer-candidate-v0.3-h1",
        predicted_entity_type="model",
        used_baseline_fallback=False,
        selected_score=0.9,
        second_best_entity_type="method",
        second_best_score=0.7,
        score_margin=0.2,
        scored_type_count=2,
        per_type_scores={"model": 0.9, "method": 0.7},
        synthetic_text_sha256="c" * 64,
        context_trimmed=False,
    )
    overridden = _final_row(build_id="b", baseline=method, materialization_fingerprint="b" * 64, semantic_case=case, semantic_prediction=pred, override=True)
    assert overridden.final_entity_type == ScientificEntityType.MODEL
    assert overridden.final_mention_id != method.mention_id
    assert overridden.h2_override_applied is True


def test_execute_and_validator_on_synthetic_single_document(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    parent = _fake_parent()
    parent["canonical_count"] = 1
    monkeypatch.setattr(mod, "_validate_parent", lambda **kwargs: parent)

    @dataclass(frozen=True)
    class Doc:
        canonical_id: str = "paper-1"
        title: str = "BERT method"
        abstract: str | None = None

    doc = Doc()
    monkeypatch.setattr(mod, "_iter_canonical", lambda path: iter((doc,)))
    monkeypatch.setattr(mod, "_raw_extractor", lambda *args, **kwargs: (None, "a" * 64, object()))
    sha = sha256_text(doc.title)
    mid = build_mention_id(canonical_id=doc.canonical_id, source_field="title", source_text_sha256=sha, char_start=0, char_end=4, entity_type="method")
    raw = ScientificEntityMentionEvidence(
        schema_version=MENTION_SCHEMA_VERSION,
        evidence_id=build_evidence_id(mention_id=mid, extractor_fingerprint="a" * 64),
        mention_id=mid,
        build_id="raw-test",
        canonical_id=doc.canonical_id,
        entity_type="method",
        source_field="title",
        source_text_sha256=sha,
        char_start=0,
        char_end=4,
        surface_text="BERT",
        extractor_fingerprint="a" * 64,
        confidence_kind=ConfidenceKind.MODEL_SCORE,
        confidence_score=0.9,
        calibration_id=None,
    )
    monkeypatch.setattr(mod, "_iter_raw_mentions_for_document", lambda **kwargs: (raw,))
    semantic = parent["semantic_config"]
    prompts = {item.entity_type: item.prompt for item in semantic.semantic_typing.labels}
    backend = FakeSemanticBackend({prompts[ScientificEntityType.MODEL]: 0.9, prompts[ScientificEntityType.METHOD]: 0.7})
    output_root = tmp_path / "out"
    report = plan_or_execute_h2_full_corpus_candidate(
        project_root=ROOT,
        config_path=CONFIG,
        authorization_dir=tmp_path / "auth",
        decision_dir=tmp_path / "decision",
        evaluation_dir=tmp_path / "eval",
        inference_dir=tmp_path / "inf",
        sample_dir=tmp_path / "sample",
        reference_dir=tmp_path / "reference",
        development_package_dir=tmp_path / "dev",
        previous_heldout_sample_dir=tmp_path / "prev",
        frozen_candidate_dir=tmp_path / "frozen",
        canonical_path=tmp_path / "canonical.jsonl",
        output_root=output_root,
        build_id="candidate-fixture",
        execute=True,
        backend=backend,
        allow_test_backend=True,
        generated_at_utc=FIXED,
    )
    assert report["phase_complete"] is True
    assert report["h2_override_count"] == 1
    assert report["final_mention_count"] == 1
    candidate_dir = output_root / "candidate-fixture"
    checks, summary = validate_h2_full_corpus_candidate(
        project_root=ROOT,
        config_path=CONFIG,
        candidate_dir=candidate_dir,
        authorization_dir=tmp_path / "auth",
        decision_dir=tmp_path / "decision",
        evaluation_dir=tmp_path / "eval",
        inference_dir=tmp_path / "inf",
        sample_dir=tmp_path / "sample",
        reference_dir=tmp_path / "reference",
        development_package_dir=tmp_path / "dev",
        previous_heldout_sample_dir=tmp_path / "prev",
        frozen_candidate_dir=tmp_path / "frozen",
        canonical_path=tmp_path / "canonical.jsonl",
    )
    assert all(ok for _, ok, _ in checks)
    assert summary["required_failed_count"] == 0
    assert summary["production_latest_promotion_authorized"] is False


def test_authorization_is_consumed_after_successful_manifest(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(mod, "_validate_parent", lambda **kwargs: _fake_parent())
    out = tmp_path / "out"
    child = out / "prior-build"
    child.mkdir(parents=True)
    config = load_h2_full_corpus_candidate_config(CONFIG)
    (child / "manifest.json").write_text('{"authorization_id":"' + config.authorization.authorization_id + '"}', encoding="utf-8")
    report = plan_or_execute_h2_full_corpus_candidate(
        project_root=ROOT,
        config_path=CONFIG,
        authorization_dir=tmp_path / "auth",
        decision_dir=tmp_path / "decision",
        evaluation_dir=tmp_path / "eval",
        inference_dir=tmp_path / "inf",
        sample_dir=tmp_path / "sample",
        reference_dir=tmp_path / "reference",
        development_package_dir=tmp_path / "dev",
        previous_heldout_sample_dir=tmp_path / "prev",
        frozen_candidate_dir=tmp_path / "frozen",
        canonical_path=tmp_path / "canonical.jsonl",
        output_root=out,
        execute=False,
        generated_at_utc=FIXED,
    )
    assert report["authorization_already_consumed"] is True
    with pytest.raises(Exception):
        plan_or_execute_h2_full_corpus_candidate(
            project_root=ROOT, config_path=CONFIG, authorization_dir=tmp_path / "auth", decision_dir=tmp_path / "decision",
            evaluation_dir=tmp_path / "eval", inference_dir=tmp_path / "inf", sample_dir=tmp_path / "sample",
            reference_dir=tmp_path / "reference", development_package_dir=tmp_path / "dev", previous_heldout_sample_dir=tmp_path / "prev",
            frozen_candidate_dir=tmp_path / "frozen", canonical_path=tmp_path / "canonical.jsonl", output_root=out, execute=True,
            backend=FakeSemanticBackend({}), allow_test_backend=True, generated_at_utc=FIXED,
        )


def test_execute_fails_closed_on_parent_snapshot_drift_before_model_load(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def _drift(**kwargs: Any):
        raise mod.H2FullCorpusCandidateError("Canonical SHA-256 no longer matches immutable authorization")

    monkeypatch.setattr(mod, "_validate_parent", _drift)

    def _forbidden(**kwargs: Any):
        raise AssertionError("model must not load after snapshot drift")

    monkeypatch.setattr(mod, "load_native_gliner_backend", _forbidden)
    with pytest.raises(Exception, match="Canonical SHA-256"):
        plan_or_execute_h2_full_corpus_candidate(
            project_root=ROOT,
            config_path=CONFIG,
            authorization_dir=tmp_path / "auth",
            decision_dir=tmp_path / "decision",
            evaluation_dir=tmp_path / "eval",
            inference_dir=tmp_path / "inf",
            sample_dir=tmp_path / "sample",
            reference_dir=tmp_path / "reference",
            development_package_dir=tmp_path / "dev",
            previous_heldout_sample_dir=tmp_path / "prev",
            frozen_candidate_dir=tmp_path / "frozen",
            canonical_path=tmp_path / "canonical.jsonl",
            output_root=tmp_path / "out",
            execute=True,
            generated_at_utc=FIXED,
        )
