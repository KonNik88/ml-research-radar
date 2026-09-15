from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from radar_core.contracts.scientific_entity_evidence import ScientificEntityType
from radar_core.contracts.scientific_entity_semantic_typer_candidate import (
    ScientificEntitySemanticTyperConfig,
    SemanticTyperDevelopmentCase,
    SemanticTyperPrediction,
)
from radar_core.entities.scientific_entity_gliner import GLiNERBackend


class ScientificEntitySemanticTyperError(ValueError):
    """Raised when target-focused semantic typing cannot be executed safely."""


@dataclass(frozen=True, slots=True)
class SyntheticTypingInput:
    text: str
    target_start: int
    target_end: int
    context_trimmed: bool


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _label_maps(config: ScientificEntitySemanticTyperConfig) -> tuple[tuple[str, ...], dict[str, ScientificEntityType]]:
    prompts = tuple(item.prompt for item in config.semantic_typing.labels)
    mapping = {
        item.prompt.strip().casefold(): item.entity_type
        for item in config.semantic_typing.labels
    }
    return prompts, mapping


def _build_synthetic_text(
    *,
    config: ScientificEntitySemanticTyperConfig,
    case: SemanticTyperDevelopmentCase,
    left_context: str,
    right_context: str,
) -> SyntheticTypingInput:
    typing = config.semantic_typing
    target_start = len(typing.synthetic_target_prefix)
    target_end = target_start + len(case.surface_text)
    context = f"{left_context}{typing.target_marker}{right_context}"
    text = (
        f"{typing.synthetic_target_prefix}{case.surface_text}\n"
        f"{typing.synthetic_context_prefix}{context}"
    )
    return SyntheticTypingInput(
        text=text,
        target_start=target_start,
        target_end=target_end,
        context_trimmed=(left_context != case.left_context or right_context != case.right_context),
    )


def prepare_synthetic_input(
    *,
    config: ScientificEntitySemanticTyperConfig,
    case: SemanticTyperDevelopmentCase,
    backend: GLiNERBackend,
) -> SyntheticTypingInput:
    """Build bounded target-focused text and refuse silent tokenizer truncation.

    The source span itself remains frozen. The original occurrence is replaced by a
    literal marker in the context, while the exact surface appears once in the target
    prefix. Context is trimmed deterministically from the far edges until the pinned
    GLiNER backend reports that the input fits its maximum token length.
    """

    prompts, _ = _label_maps(config)
    left = case.left_context[-config.semantic_typing.context_left_chars :]
    right = case.right_context[: config.semantic_typing.context_right_chars]

    while True:
        synthetic = _build_synthetic_text(
            config=config,
            case=case,
            left_context=left,
            right_context=right,
        )
        prepared = backend.prepare_text(synthetic.text, prompts)
        if len(prepared.tokens) <= backend.model_max_tokens:
            return synthetic
        if not left and not right:
            raise ScientificEntitySemanticTyperError(
                "Target-focused semantic typing input exceeds model_max_tokens even without context"
            )
        if len(left) >= len(right) and left:
            left = left[min(32, len(left)) :]
        elif right:
            right = right[: max(0, len(right) - 32)]


def _parse_exact_target_scores(
    *,
    predictions: Sequence[Mapping[str, Any]],
    target_start: int,
    target_end: int,
    target_surface: str,
    type_by_prompt: Mapping[str, ScientificEntityType],
) -> dict[ScientificEntityType, float]:
    scores: dict[ScientificEntityType, float] = {}
    for prediction in predictions:
        try:
            start = int(prediction["start"])
            end = int(prediction["end"])
            surface = str(prediction["text"])
            label = str(prediction["label"]).strip().casefold()
            score = float(prediction["score"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ScientificEntitySemanticTyperError(
                f"Malformed semantic typer GLiNER prediction: {prediction!r}"
            ) from exc
        if not math.isfinite(score) or not 0.0 <= score <= 1.0:
            raise ScientificEntitySemanticTyperError(
                "Semantic typer GLiNER score must be finite in [0, 1]"
            )
        if start != target_start or end != target_end:
            continue
        if surface != target_surface:
            raise ScientificEntitySemanticTyperError(
                "Exact target offsets returned with a mismatching target surface"
            )
        entity_type = type_by_prompt.get(label)
        if entity_type is None:
            raise ScientificEntitySemanticTyperError(
                f"Unknown semantic typer label returned by GLiNER: {label!r}"
            )
        previous = scores.get(entity_type)
        if previous is None or score > previous:
            scores[entity_type] = score
    return scores


def type_development_case(
    *,
    config: ScientificEntitySemanticTyperConfig,
    case: SemanticTyperDevelopmentCase,
    backend: GLiNERBackend,
) -> SemanticTyperPrediction:
    prompts, type_by_prompt = _label_maps(config)
    synthetic = prepare_synthetic_input(config=config, case=case, backend=backend)
    predictions = backend.predict_entities(
        synthetic.text,
        prompts,
        threshold=config.semantic_typing.inference_threshold,
        flat_ner=config.semantic_typing.flat_ner,
        multi_label=config.semantic_typing.multi_label,
    )
    scores = _parse_exact_target_scores(
        predictions=predictions,
        target_start=synthetic.target_start,
        target_end=synthetic.target_end,
        target_surface=case.surface_text,
        type_by_prompt=type_by_prompt,
    )

    if not scores:
        return SemanticTyperPrediction(
            case_id=case.case_id,
            candidate_id=config.candidate.candidate_id,
            predicted_entity_type=case.baseline_entity_type,
            used_baseline_fallback=True,
            selected_score=None,
            second_best_entity_type=None,
            second_best_score=None,
            score_margin=None,
            scored_type_count=0,
            per_type_scores={},
            synthetic_text_sha256=_sha256_text(synthetic.text),
            context_trimmed=synthetic.context_trimmed,
        )

    canonical_order = {
        entity_type: index for index, entity_type in enumerate(ScientificEntityType)
    }
    ranked = sorted(
        scores.items(),
        key=lambda item: (-item[1], canonical_order[item[0]]),
    )
    selected_type, selected_score = ranked[0]
    second_type = None
    second_score = None
    margin = None
    if len(ranked) >= 2:
        second_type, second_score = ranked[1]
        margin = round(selected_score - second_score, 6)

    return SemanticTyperPrediction(
        case_id=case.case_id,
        candidate_id=config.candidate.candidate_id,
        predicted_entity_type=selected_type,
        used_baseline_fallback=False,
        selected_score=selected_score,
        second_best_entity_type=second_type,
        second_best_score=second_score,
        score_margin=margin,
        scored_type_count=len(scores),
        per_type_scores=scores,
        synthetic_text_sha256=_sha256_text(synthetic.text),
        context_trimmed=synthetic.context_trimmed,
    )


def semantic_typer_identity_payload(config: ScientificEntitySemanticTyperConfig) -> dict[str, Any]:
    return {
        "candidate_id": config.candidate.candidate_id,
        "upstream_runtime_config_path": config.candidate.upstream_runtime_config_path,
        "strategy": config.semantic_typing.strategy,
        "synthetic_target_prefix": config.semantic_typing.synthetic_target_prefix,
        "synthetic_context_prefix": config.semantic_typing.synthetic_context_prefix,
        "target_marker": config.semantic_typing.target_marker,
        "context_left_chars": config.semantic_typing.context_left_chars,
        "context_right_chars": config.semantic_typing.context_right_chars,
        "inference_threshold": config.semantic_typing.inference_threshold,
        "flat_ner": config.semantic_typing.flat_ner,
        "multi_label": config.semantic_typing.multi_label,
        "selection": config.semantic_typing.selection,
        "tie_breaker": config.semantic_typing.tie_breaker,
        "unscorable_policy": config.semantic_typing.unscorable_policy,
        "labels": [item.model_dump(mode="json") for item in config.semantic_typing.labels],
    }


def semantic_typer_fingerprint(config: ScientificEntitySemanticTyperConfig) -> str:
    payload = json.dumps(
        semantic_typer_identity_payload(config),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "ScientificEntitySemanticTyperError",
    "SyntheticTypingInput",
    "prepare_synthetic_input",
    "semantic_typer_fingerprint",
    "semantic_typer_identity_payload",
    "type_development_case",
]
