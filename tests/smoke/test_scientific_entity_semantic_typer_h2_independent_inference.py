from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import pytest

from radar_core.contracts.scientific_entity_evidence import ScientificEntityType
from radar_core.contracts.scientific_entity_semantic_typer_candidate import (
    SemanticTyperPrediction,
    load_semantic_typer_config,
)
from radar_core.contracts.scientific_entity_semantic_typer_h2_independent_inference import (
    H2IndependentInferenceCase,
    load_h2_independent_inference_config,
)
from radar_core.entities.scientific_entity_gliner import PreparedText
from radar_core.entities.scientific_entity_semantic_typer import type_semantic_case
from radar_core.entities.scientific_entity_semantic_typer_h2_independent_inference import (
    _apply_h2_policy,
    plan_or_execute_h2_independent_inference,
)
import radar_core.entities.scientific_entity_semantic_typer_h2_independent_inference as inference_module


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "scientific_entity_semantic_typer_h2_independent_inference_v0.3.yaml"
SEMANTIC_CONFIG = ROOT / "configs" / "scientific_entity_semantic_typer_candidate_v0.3.yaml"
FIXED_TIME = datetime(2026, 9, 26, 10, 0, 0, tzinfo=timezone.utc)


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

    def predict_entities(
        self,
        text: str,
        labels: Sequence[str],
        *,
        threshold: float,
        flat_ner: bool,
        multi_label: bool,
    ) -> Sequence[Mapping[str, Any]]:
        assert threshold == 0.0
        assert flat_ner is False
        assert multi_label is True
        start = len("Target entity: ")
        end = text.index("\n", start)
        surface = text[start:end]
        return [
            {
                "start": start,
                "end": end,
                "text": surface,
                "label": label,
                "score": self.scores[label],
            }
            for label in labels
            if label in self.scores
        ]


def _case(*, case_id: str = "case:1", baseline: ScientificEntityType = ScientificEntityType.METHOD) -> H2IndependentInferenceCase:
    return H2IndependentInferenceCase(
        case_id=case_id,
        canonical_id="paper-1",
        source_field="abstract",
        source_text_sha256="1" * 64,
        baseline_prediction_evidence_id="evidence:" + "2" * 32,
        char_start=10,
        char_end=14,
        surface_text="BERT",
        baseline_entity_type=baseline,
        baseline_confidence_score=0.91,
        left_context="We evaluate ",
        right_context=" on downstream tasks.",
    )


def _semantic_prediction(
    case: H2IndependentInferenceCase,
    *,
    predicted: ScientificEntityType,
    margin: float | None,
    fallback: bool = False,
) -> SemanticTyperPrediction:
    return SemanticTyperPrediction(
        case_id=case.case_id,
        candidate_id="scientific-entity-semantic-typer-candidate-v0.3-h1",
        predicted_entity_type=predicted,
        used_baseline_fallback=fallback,
        selected_score=None if fallback else 0.8,
        second_best_entity_type=None if fallback else ScientificEntityType.METHOD,
        second_best_score=None if fallback else (0.8 - (margin or 0.0)),
        score_margin=None if fallback else margin,
        scored_type_count=0 if fallback else 2,
        per_type_scores={} if fallback else {
            predicted: 0.8,
            ScientificEntityType.METHOD: 0.8 - (margin or 0.0),
        },
        synthetic_text_sha256="3" * 64,
        context_trimmed=False,
    )


def test_config_freezes_exact_h2_candidate_sample_and_policy() -> None:
    config = load_h2_independent_inference_config(CONFIG)
    assert config.candidate.candidate_fingerprint_sha256 == (
        "6d3782fb1f2cc7219b7083bcf381c17c546491425e817c0f5620ff145bfa6966"
    )
    assert config.lineage.sample_id == (
        "scientific-entity-fresh-heldout-sample-v0.3-20260919T093837653829Z"
    )
    assert config.execution.h2_baseline_type == ScientificEntityType.METHOD
    assert config.execution.h2_semantic_typer_type == ScientificEntityType.MODEL
    assert config.execution.h2_threshold == 0.1
    assert config.execution.preserve_baseline_otherwise is True
    assert config.safety.plan_runs_model_inference is False
    assert config.safety.evaluation_allowed_in_this_slice is False
    assert config.safety.acceptance_decision_allowed_in_this_slice is False


def test_inference_case_schema_forbids_human_reference_fields() -> None:
    payload = _case().model_dump(mode="json")
    payload["reference_entity_type"] = "model"
    with pytest.raises(Exception):
        H2IndependentInferenceCase.model_validate(payload)


def test_shared_semantic_typer_runs_without_reference_labels() -> None:
    config = load_semantic_typer_config(SEMANTIC_CONFIG)
    prompts = {item.entity_type: item.prompt for item in config.semantic_typing.labels}
    backend = FakeSemanticBackend(
        {
            prompts[ScientificEntityType.MODEL]: 0.91,
            prompts[ScientificEntityType.METHOD]: 0.62,
            prompts[ScientificEntityType.TASK]: 0.20,
        }
    )
    prediction = type_semantic_case(config=config, case=_case(), backend=backend)
    assert prediction.predicted_entity_type == ScientificEntityType.MODEL
    assert prediction.score_margin == 0.29
    assert prediction.used_baseline_fallback is False


def test_h2_policy_overrides_only_frozen_method_to_model_rule() -> None:
    eligible = _case(case_id="eligible", baseline=ScientificEntityType.METHOD)
    low_margin = _case(case_id="low", baseline=ScientificEntityType.METHOD)
    wrong_baseline = _case(case_id="wrong-baseline", baseline=ScientificEntityType.TASK)
    fallback = _case(case_id="fallback", baseline=ScientificEntityType.METHOD)
    cases = (eligible, low_margin, wrong_baseline, fallback)
    semantic = (
        _semantic_prediction(eligible, predicted=ScientificEntityType.MODEL, margin=0.1),
        _semantic_prediction(low_margin, predicted=ScientificEntityType.MODEL, margin=0.099999),
        _semantic_prediction(wrong_baseline, predicted=ScientificEntityType.MODEL, margin=0.5),
        _semantic_prediction(fallback, predicted=ScientificEntityType.METHOD, margin=None, fallback=True),
    )
    rows = _apply_h2_policy(
        inference_id="inference-test",
        cases=cases,
        semantic_predictions=semantic,
        baseline_type=ScientificEntityType.METHOD,
        semantic_typer_type=ScientificEntityType.MODEL,
        threshold=0.1,
    )
    assert [row.h2_override_applied for row in rows] == [True, False, False, False]
    assert [row.final_entity_type for row in rows] == [
        ScientificEntityType.MODEL,
        ScientificEntityType.METHOD,
        ScientificEntityType.TASK,
        ScientificEntityType.METHOD,
    ]
    assert all(row.char_start == 10 and row.char_end == 14 and row.surface_text == "BERT" for row in rows)


def test_plan_is_non_writing_and_never_loads_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = load_h2_independent_inference_config(CONFIG)
    fake_parent = {
        "config": config,
        "reference_summary": {"required_failed_count": 0},
    }
    monkeypatch.setattr(inference_module, "_validate_parent_state", lambda **kwargs: fake_parent)

    def _forbidden(*args: Any, **kwargs: Any):
        raise AssertionError("PLAN must not load model backend")

    monkeypatch.setattr(inference_module, "load_native_gliner_backend", _forbidden)
    report = plan_or_execute_h2_independent_inference(
        project_root=ROOT,
        config_path=CONFIG,
        sample_dir=tmp_path / "sample",
        reference_dir=tmp_path / "reference",
        development_package_dir=tmp_path / "development",
        previous_heldout_sample_dir=tmp_path / "previous",
        frozen_candidate_dir=tmp_path / "candidate",
        canonical_path=tmp_path / "canonical.jsonl",
        inference_id="scientific-entity-semantic-typer-h2-independent-inference-v0.3-test",
        output_root=tmp_path / "out",
        execute=False,
        generated_at_utc=FIXED_TIME,
    )
    assert report["mode"] == "plan"
    assert report["phase_complete"] is False
    assert report["plan_runs_model_inference"] is False
    assert report["upstream_model_inference_executed"] is False
    assert report["semantic_typer_model_inference_executed"] is False
    assert report["evaluation_executed"] is False
    assert report["acceptance_decision_made"] is False
    assert not (tmp_path / "out").exists()


def test_execute_then_validator_preserves_reference_free_inference_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from dataclasses import dataclass

    from radar_core.contracts.scientific_entity_evidence import (
        ConfidenceKind,
        MENTION_SCHEMA_VERSION,
        ScientificEntityMentionEvidence,
        ScientificEntitySourceField,
        build_evidence_id,
        build_mention_id,
        sha256_text,
    )
    from radar_core.entities.scientific_entity_semantic_prompt_raw_floor_policy import (
        DEFAULT_CONFIG_PATH as RAW_FLOOR_POLICY_CONFIG,
        load_raw_floor_policy_config,
    )

    config = load_h2_independent_inference_config(CONFIG)
    semantic_config = load_semantic_typer_config(SEMANTIC_CONFIG)
    policy_config = load_raw_floor_policy_config(RAW_FLOOR_POLICY_CONFIG)

    fake_parent = {
        "config": config,
        "reference_summary": {"required_failed_count": 0},
        "inference_config_sha": inference_module.inference_config_sha256(config),
        "semantic_config": semantic_config,
        "policy_config": policy_config,
        "runtime_config": object(),
        "gate_sha": "1" * 64,
        "sample_manifest_sha": "2" * 64,
        "candidate_manifest_sha": "3" * 64,
        "candidate_definition_sha": "4" * 64,
        "reference_completion_sha": "5" * 64,
        "reference_mentions_sha": "6" * 64,
        "semantic_config_sha": "7" * 64,
        "runtime_sha": "8" * 64,
        "policy_sha": "9" * 64,
    }
    monkeypatch.setattr(inference_module, "_validate_parent_state", lambda **kwargs: fake_parent)

    @dataclass(frozen=True)
    class FakeDocument:
        canonical_id: str
        title: str
        abstract: str | None = None

    document = FakeDocument(canonical_id="paper-1", title="BERT method")
    monkeypatch.setattr(inference_module, "_load_documents", lambda *args, **kwargs: (document,))

    source_sha = sha256_text(document.title)
    mention_id = build_mention_id(
        canonical_id=document.canonical_id,
        source_field=ScientificEntitySourceField.TITLE,
        source_text_sha256=source_sha,
        char_start=0,
        char_end=4,
        entity_type=ScientificEntityType.METHOD,
    )
    raw_mention = ScientificEntityMentionEvidence(
        schema_version=MENTION_SCHEMA_VERSION,
        evidence_id=build_evidence_id(mention_id=mention_id, extractor_fingerprint="a" * 64),
        mention_id=mention_id,
        build_id="raw-test",
        canonical_id=document.canonical_id,
        entity_type=ScientificEntityType.METHOD,
        source_field=ScientificEntitySourceField.TITLE,
        source_text_sha256=source_sha,
        char_start=0,
        char_end=4,
        surface_text="BERT",
        extractor_fingerprint="a" * 64,
        confidence_kind=ConfidenceKind.MODEL_SCORE,
        confidence_score=0.9,
        calibration_id=None,
    )
    monkeypatch.setattr(
        inference_module,
        "_extract_raw_mentions",
        lambda **kwargs: (raw_mention,),
    )

    prompts = {item.entity_type: item.prompt for item in semantic_config.semantic_typing.labels}
    backend = FakeSemanticBackend(
        {
            prompts[ScientificEntityType.MODEL]: 0.91,
            prompts[ScientificEntityType.METHOD]: 0.70,
            prompts[ScientificEntityType.TASK]: 0.10,
        }
    )
    inference_id = "scientific-entity-semantic-typer-h2-independent-inference-v0.3-fixture"
    output_root = tmp_path / "out"

    report = plan_or_execute_h2_independent_inference(
        project_root=ROOT,
        config_path=CONFIG,
        sample_dir=tmp_path / "sample",
        reference_dir=tmp_path / "reference",
        development_package_dir=tmp_path / "development",
        previous_heldout_sample_dir=tmp_path / "previous",
        frozen_candidate_dir=tmp_path / "candidate",
        canonical_path=tmp_path / "canonical.jsonl",
        inference_id=inference_id,
        output_root=output_root,
        execute=True,
        backend=backend,
        allow_test_backend=True,
        generated_at_utc=FIXED_TIME,
    )
    assert report["phase_complete"] is True
    assert report["evaluation_executed"] is False
    assert report["h2_override_count"] == 1
    assert report["next_slice"] == "validate_h2_v03_independent_inference_evidence"

    inference_dir = output_root / inference_id
    checks, summary = inference_module.validate_h2_independent_inference(
        project_root=ROOT,
        config_path=CONFIG,
        sample_dir=tmp_path / "sample",
        reference_dir=tmp_path / "reference",
        development_package_dir=tmp_path / "development",
        previous_heldout_sample_dir=tmp_path / "previous",
        frozen_candidate_dir=tmp_path / "candidate",
        canonical_path=tmp_path / "canonical.jsonl",
        inference_dir=inference_dir,
    )
    assert all(ok for _, ok, _ in checks)
    assert summary["required_failed_count"] == 0
    assert summary["next_slice"] == "run_h2_independent_comparative_evaluation"

    case_payload = json.loads((inference_dir / "semantic_typer_cases.jsonl").read_text(encoding="utf-8"))
    assert "reference_entity_type" not in case_payload
    prediction_payload = json.loads((inference_dir / "h2_predictions.jsonl").read_text(encoding="utf-8"))
    assert prediction_payload["baseline_entity_type"] == "method"
    assert prediction_payload["final_entity_type"] == "model"
    assert prediction_payload["h2_override_applied"] is True
