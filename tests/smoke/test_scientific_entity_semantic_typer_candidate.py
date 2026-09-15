from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from radar_core.contracts.canonical_document import CanonicalDocument
from radar_core.contracts.scientific_entity_evaluation import (
    ScientificEntityEvaluationErrorKind,
    ScientificEntityReferenceMention,
)
from radar_core.contracts.scientific_entity_evidence import (
    ScientificEntityMentionEvidence,
    ScientificEntitySourceField,
    ScientificEntityType,
)
from radar_core.contracts.scientific_entity_semantic_typer_candidate import (
    SemanticTyperDevelopmentCase,
    load_semantic_typer_config,
    semantic_typer_config_sha256,
)
from radar_core.contracts.scientific_entity_typing_root_cause_review import WorkingReviewRow
from radar_core.entities.scientific_entity_evaluation import evaluate_mentions, load_evaluation_config
from radar_core.entities.scientific_entity_gliner import PreparedText
from radar_core.entities.scientific_entity_semantic_typer import (
    semantic_typer_fingerprint,
    type_development_case,
)
from radar_core.entities.scientific_entity_semantic_typer_development import (
    materialize_development_cases,
)


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs" / "scientific_entity_semantic_typer_candidate_v0.3.yaml"
EVAL_CONFIG = ROOT / "configs" / "scientific_entity_evaluation_v0.1.yaml"
EVAL_FIXTURE = ROOT / "tests" / "fixtures" / "scientific_entity_evaluation_v0_1"


class FakeSemanticTyperBackend:
    model_max_tokens = 384
    model_max_width = 12

    def __init__(self, scores: Mapping[str, float] | None = None) -> None:
        self.scores = dict(scores or {})

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
        prefix = "Target entity: "
        start = len(prefix)
        end = text.index("\n", start)
        surface = text[start:end]
        rows: list[dict[str, Any]] = []
        for label in labels:
            score = self.scores.get(label)
            if score is None:
                continue
            rows.append(
                {
                    "start": start,
                    "end": end,
                    "text": surface,
                    "label": label,
                    "score": score,
                }
            )
        return rows


def _case(*, baseline: str = "method") -> SemanticTyperDevelopmentCase:
    return SemanticTyperDevelopmentCase(
        case_id="semantic-typer-dev-case:test",
        evaluation_id="scientific-entity-evaluation-fresh-v0.2c-20260901T130232963026Z",
        canonical_id="paper-1",
        source_field="abstract",
        source_text_sha256="1" * 64,
        reference_id="reference:test",
        baseline_prediction_evidence_id="evidence:test",
        char_start=10,
        char_end=14,
        surface_text="BERT",
        reference_entity_type="model",
        baseline_entity_type=baseline,
        baseline_correct=baseline == "model",
        baseline_confidence_score=0.95,
        left_context="We evaluate ",
        right_context=" on downstream tasks.",
        root_cause="clear_semantic_mistyping" if baseline != "model" else None,
        ambiguity_level="none" if baseline != "model" else None,
        reference_type_confirmed=True if baseline != "model" else None,
        primary_metric_eligible=True,
    )


def test_config_freezes_one_bounded_second_stage_hypothesis() -> None:
    config = load_semantic_typer_config(CONFIG)
    assert config.candidate.hypothesis == (
        "target_focused_second_stage_semantic_typing_over_frozen_spans"
    )
    assert config.semantic_typing.multi_label is True
    assert config.semantic_typing.inference_threshold == 0.0
    assert config.semantic_typing.unscorable_policy == "preserve_baseline_type"
    assert [row.entity_type for row in config.semantic_typing.labels] == list(
        ScientificEntityType
    )
    assert config.safety.span_mutation_allowed is False
    assert config.safety.root_cause_labels_as_model_features_allowed is False
    assert config.safety.baseline_type_as_model_feature_allowed is False
    assert config.safety.future_candidate_requires_new_independent_heldout is True


def test_config_and_candidate_fingerprints_are_stable() -> None:
    config = load_semantic_typer_config(CONFIG)
    assert semantic_typer_config_sha256(config) == semantic_typer_config_sha256(config)
    assert semantic_typer_fingerprint(config) == semantic_typer_fingerprint(config)
    assert len(semantic_typer_fingerprint(config)) == 64


def test_typer_selects_highest_exact_target_score_independently_of_baseline() -> None:
    config = load_semantic_typer_config(CONFIG)
    prompts = {row.entity_type.value: row.prompt for row in config.semantic_typing.labels}
    backend = FakeSemanticTyperBackend(
        {
            prompts["model"]: 0.91,
            prompts["method"]: 0.62,
            prompts["task"]: 0.22,
        }
    )
    prediction = type_development_case(config=config, case=_case(), backend=backend)
    assert prediction.predicted_entity_type == ScientificEntityType.MODEL
    assert prediction.used_baseline_fallback is False
    assert prediction.selected_score == 0.91
    assert prediction.second_best_entity_type == ScientificEntityType.METHOD
    assert prediction.score_margin == 0.29
    assert prediction.scored_type_count == 3


def test_typer_uses_canonical_order_as_deterministic_score_tie_breaker() -> None:
    config = load_semantic_typer_config(CONFIG)
    prompts = {row.entity_type.value: row.prompt for row in config.semantic_typing.labels}
    backend = FakeSemanticTyperBackend(
        {prompts["task"]: 0.8, prompts["method"]: 0.8}
    )
    prediction = type_development_case(config=config, case=_case(), backend=backend)
    assert prediction.predicted_entity_type == ScientificEntityType.TASK
    assert prediction.selected_score == 0.8
    assert prediction.score_margin == 0.0


def test_typer_preserves_baseline_only_when_exact_target_is_unscorable() -> None:
    config = load_semantic_typer_config(CONFIG)
    prediction = type_development_case(
        config=config,
        case=_case(baseline="method"),
        backend=FakeSemanticTyperBackend({}),
    )
    assert prediction.predicted_entity_type == ScientificEntityType.METHOD
    assert prediction.used_baseline_fallback is True
    assert prediction.selected_score is None
    assert prediction.scored_type_count == 0


def _load_fixture_rows(path: Path, model) -> list[Any]:
    return [
        model.model_validate(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_development_materializer_reuses_existing_evaluator_pairing() -> None:
    config = load_semantic_typer_config(CONFIG)
    evaluation_config = load_evaluation_config(EVAL_CONFIG)
    documents = {
        row.canonical_id: row
        for row in _load_fixture_rows(
            EVAL_FIXTURE / "canonical_documents.jsonl", CanonicalDocument
        )
    }
    references = _load_fixture_rows(
        EVAL_FIXTURE / "reference_mentions.jsonl", ScientificEntityReferenceMention
    )
    predictions = _load_fixture_rows(
        EVAL_FIXTURE / "prediction_build" / "mentions.jsonl",
        ScientificEntityMentionEvidence,
    )
    result = evaluate_mentions(
        evaluation_id="scientific-entity-evaluation-fixture-semantic-typer-v0.3",
        document_count=len(documents),
        references=references,
        predictions=predictions,
        config=evaluation_config,
    )
    reference_by_id = {row.reference_id: row for row in references}
    prediction_by_id = {row.evidence_id: row for row in predictions}

    review_rows: dict[tuple[str, str], WorkingReviewRow] = {}
    same_span_type_errors = [
        row
        for row in result.errors
        if row.error_kind == ScientificEntityEvaluationErrorKind.TYPE_MISMATCH
        and row.reference_char_start == row.prediction_char_start
        and row.reference_char_end == row.prediction_char_end
    ]
    for index, error in enumerate(same_span_type_errors, start=1):
        assert error.reference_id is not None
        assert error.prediction_evidence_id is not None
        reference = reference_by_id[error.reference_id]
        prediction = prediction_by_id[error.prediction_evidence_id]
        review_rows[(reference.reference_id, prediction.evidence_id)] = WorkingReviewRow(
            diagnostic_case_id=f"diagnostic-case-{index}",
            error_id=error.error_id,
            evaluation_id=error.evaluation_id,
            canonical_id=reference.canonical_id,
            source_field=reference.source_field.value,
            reference_id=reference.reference_id,
            prediction_evidence_id=prediction.evidence_id,
            reference_entity_type=reference.entity_type.value,
            prediction_entity_type=prediction.entity_type.value,
            confusion_pair=f"{reference.entity_type.value}->{prediction.entity_type.value}",
            pair_count=1,
            pair_rank=index,
            reference_char_start=reference.char_start,
            reference_char_end=reference.char_end,
            prediction_char_start=prediction.char_start,
            prediction_char_end=prediction.char_end,
            char_iou=1.0,
            same_span=True,
            reference_surface=reference.surface_text,
            prediction_surface=prediction.surface_text,
            source_excerpt=reference.surface_text,
            prediction_confidence_score=prediction.confidence_score or 0.0,
            high_confidence_at_0_8=False,
            high_confidence_at_0_9=False,
            review_status="complete",
            root_cause=(
                "annotation_reference_issue" if index == 1 else "clear_semantic_mistyping"
            ),
            reference_type_confirmed=False if index == 1 else True,
            prediction_type_plausible=False,
            ambiguity_level="low",
            recommended_action=(
                "annotation_guideline" if index == 1 else "second_stage_typer"
            ),
            review_notes="fixture",
        )

    cases = materialize_development_cases(
        config=config,
        evaluation_id="scientific-entity-evaluation-fixture-semantic-typer-v0.3",
        documents=documents,
        references=reference_by_id,
        predictions=prediction_by_id,
        matches=result.matches,
        errors=result.errors,
        review_rows=review_rows,
    )

    exact_match_count = sum(row.match_kind.value == "exact" for row in result.matches)
    assert len(cases) == exact_match_count + len(same_span_type_errors)
    assert sum(row.baseline_correct for row in cases) == exact_match_count
    assert sum(not row.baseline_correct for row in cases) == len(same_span_type_errors)
    assert sum(not row.primary_metric_eligible for row in cases) == (
        1 if same_span_type_errors else 0
    )
    assert all(row.surface_text for row in cases)
    assert all(row.char_end > row.char_start for row in cases)
