from __future__ import annotations

import hashlib
import json
import math
import re
from importlib import metadata as importlib_metadata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import yaml

ENTITY_TYPES = ("task", "method", "dataset", "metric", "model", "domain")
ERROR_KINDS = ("boundary_mismatch", "type_mismatch", "false_positive", "false_negative")
CONFIDENCE_GROUPS = ("exact", "relaxed_only", "boundary_mismatch", "type_mismatch", "false_positive")


class ScientificEntityHeldoutErrorAnalysisError(ValueError):
    pass

GLINER_WHITESPACE_PATTERN = re.compile(r"\w+(?:[-_]\w+)*|\S")


def _surface_from_span(text: str | None, start: int | None, end: int | None) -> str | None:
    if text is None or start is None or end is None:
        return None
    if not 0 <= int(start) <= int(end) <= len(text):
        raise ScientificEntityHeldoutErrorAnalysisError(
            f"Invalid source span: start={start} end={end} text_length={len(text)}"
        )
    return text[int(start):int(end)]


def _gliner_whitespace_split(text: str) -> list[tuple[str, int, int]]:
    return [(match.group(), match.start(), match.end()) for match in GLINER_WHITESPACE_PATTERN.finditer(text)]


def _verify_runtime_gliner_splitter(
    *,
    documents: Sequence[Mapping[str, Any]],
    splitter_type: str,
    required: bool,
) -> dict[str, Any]:
    try:
        from gliner.data_processing.tokenizer import WordsSplitter  # type: ignore
    except Exception as exc:
        if required:
            raise ScientificEntityHeldoutErrorAnalysisError(
                f"GLiNER WordsSplitter runtime verification required but unavailable: {exc}"
            ) from exc
        return {
            "required": False,
            "available": False,
            "verified": False,
            "gliner_version": None,
            "text_count_checked": 0,
        }
    if splitter_type != "whitespace":
        raise ScientificEntityHeldoutErrorAnalysisError(
            f"Only pinned whitespace splitter is supported by this audit, got {splitter_type}"
        )
    runtime_splitter = WordsSplitter(splitter_type)
    checked = 0
    for doc in documents:
        for field in ("title", "abstract"):
            text = doc.get(field)
            if not isinstance(text, str):
                continue
            expected = _gliner_whitespace_split(text)
            actual = list(runtime_splitter(text))
            if actual != expected:
                raise ScientificEntityHeldoutErrorAnalysisError(
                    f"Pinned whitespace splitter implementation disagrees with installed GLiNER for "
                    f"canonical_id={doc.get('canonical_id')} field={field}"
                )
            checked += 1
    try:
        gliner_version = importlib_metadata.version("gliner")
    except importlib_metadata.PackageNotFoundError:
        gliner_version = None
    return {
        "required": bool(required),
        "available": True,
        "verified": True,
        "gliner_version": gliner_version,
        "text_count_checked": checked,
    }


def _build_gliner_windowing_audit(
    *,
    documents: Sequence[Mapping[str, Any]],
    references: Sequence[Mapping[str, Any]],
    errors: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Audit the actual v0.1 adapter windowing contract without model inference.

    The production candidate adapter never feeds a complete long abstract to
    ``predict_entities``.  It first obtains GLiNER WordsSplitter token maps,
    then calls the model on deterministic overlapping windows.  This audit
    mirrors that behavior and therefore must not reinterpret ``model_max_len``
    as a whole-document prefix cutoff.
    """
    audit_cfg = config.get("gliner_windowing_audit")
    if not isinstance(audit_cfg, Mapping):
        raise ScientificEntityHeldoutErrorAnalysisError(
            "gliner_windowing_audit config is required"
        )
    model_max_len = int(audit_cfg.get("model_max_len", 0))
    model_max_width = int(audit_cfg.get("model_max_width", 0))
    window_size = int(audit_cfg.get("window_size_tokens", 0))
    overlap = int(audit_cfg.get("window_overlap_tokens", -1))
    splitter_type = str(audit_cfg.get("words_splitter_type", ""))
    if model_max_len <= 0 or model_max_width <= 0:
        raise ScientificEntityHeldoutErrorAnalysisError(
            "gliner_windowing_audit model limits must be positive"
        )
    if window_size <= 0 or window_size > model_max_len:
        raise ScientificEntityHeldoutErrorAnalysisError(
            "window_size_tokens must be positive and <= model_max_len"
        )
    if overlap < model_max_width - 1 or overlap >= window_size:
        raise ScientificEntityHeldoutErrorAnalysisError(
            "window overlap must preserve max-width spans and be smaller than window size"
        )
    if splitter_type != "whitespace":
        raise ScientificEntityHeldoutErrorAnalysisError(
            f"Expected pinned words_splitter_type=whitespace, got {splitter_type}"
        )

    runtime = _verify_runtime_gliner_splitter(
        documents=documents,
        splitter_type=splitter_type,
        required=bool(audit_cfg.get("runtime_splitter_verification_required", False)),
    )
    step = window_size - overlap
    docs_by_id = _index(documents, "canonical_id")
    fn_reference_ids = {
        str(row["reference_id"])
        for row in errors
        if row.get("error_kind") == "false_negative"
        and row.get("reference_id") is not None
    }

    rows: list[dict[str, Any]] = []
    token_maps: dict[tuple[str, str], list[tuple[str, int, int]]] = {}
    windows_by_key: dict[tuple[str, str], list[dict[str, int]]] = {}
    by_field_values: dict[str, list[int]] = {"title": [], "abstract": []}
    total_windows = 0
    uncovered_token_count = 0
    max_observed_window_tokens = 0

    for doc in documents:
        canonical_id = str(doc["canonical_id"])
        for field in ("title", "abstract"):
            source_text = doc.get(field)
            if not isinstance(source_text, str):
                continue
            tokens = _gliner_whitespace_split(source_text)
            token_maps[(canonical_id, field)] = tokens
            token_count = len(tokens)
            by_field_values[field].append(token_count)
            windows: list[dict[str, int]] = []
            covered = [False] * token_count
            if token_count:
                for first in range(0, token_count, step):
                    last = min(first + window_size, token_count)
                    count = last - first
                    if count > model_max_len:
                        raise ScientificEntityHeldoutErrorAnalysisError(
                            "derived adapter window exceeds pinned model_max_len"
                        )
                    window = {
                        "first_splitter_token": first,
                        "last_splitter_token_exclusive": last,
                        "splitter_token_count": count,
                        "char_start": tokens[first][1],
                        "char_end": tokens[last - 1][2],
                    }
                    windows.append(window)
                    for index in range(first, last):
                        covered[index] = True
                    max_observed_window_tokens = max(max_observed_window_tokens, count)
                    if last == token_count:
                        break
            windows_by_key[(canonical_id, field)] = windows
            uncovered = sum(1 for value in covered if not value)
            uncovered_token_count += uncovered
            total_windows += len(windows)
            rows.append({
                "canonical_id": canonical_id,
                "source_field": field,
                "character_count": len(source_text),
                "splitter_token_count": token_count,
                "model_max_len": model_max_len,
                "window_size_tokens": window_size,
                "window_overlap_tokens": overlap,
                "window_step_tokens": step,
                "adapter_window_count": len(windows),
                "windowed": len(windows) > 1,
                "max_observed_window_token_count": max(
                    (row["splitter_token_count"] for row in windows), default=0
                ),
                "all_splitter_tokens_covered": uncovered == 0,
                "uncovered_splitter_token_count": uncovered,
                "windows": windows,
            })

    reference_rows: list[dict[str, Any]] = []
    for ref in references:
        canonical_id = str(ref["canonical_id"])
        field = str(ref["source_field"])
        source_text = _doc_text(docs_by_id.get(canonical_id), field)
        if source_text is None:
            continue
        start = int(ref["char_start"])
        end = int(ref["char_end"])
        tokens = token_maps.get((canonical_id, field), [])
        windows = windows_by_key.get((canonical_id, field), [])
        overlapping_indices = [
            index
            for index, (_, token_start, token_end) in enumerate(tokens)
            if token_start < end and token_end > start
        ]
        if overlapping_indices:
            first_token = min(overlapping_indices)
            last_token_exclusive = max(overlapping_indices) + 1
            splitter_width = last_token_exclusive - first_token
            containing_windows = sum(
                1
                for window in windows
                if int(window["first_splitter_token"]) <= first_token
                and int(window["last_splitter_token_exclusive"]) >= last_token_exclusive
            )
        else:
            first_token = None
            last_token_exclusive = None
            splitter_width = 0
            containing_windows = 0
        surface = _surface_from_span(source_text, start, end)
        reference_id = str(ref["reference_id"])
        reference_rows.append({
            "reference_id": reference_id,
            "canonical_id": canonical_id,
            "source_field": field,
            "entity_type": ref.get("entity_type"),
            "surface": surface,
            "char_start": start,
            "char_end": end,
            "splitter_first_token": first_token,
            "splitter_last_token_exclusive": last_token_exclusive,
            "splitter_token_width": splitter_width,
            "model_max_width": model_max_width,
            "exceeds_model_max_width": splitter_width > model_max_width,
            "fully_contained_in_at_least_one_adapter_window": containing_windows > 0,
            "containing_adapter_window_count": containing_windows,
            "markup_like_surface": bool(surface and "<" in surface and ">" in surface),
            "is_false_negative": reference_id in fn_reference_ids,
        })

    by_field: dict[str, Any] = {}
    for field, values in by_field_values.items():
        field_rows = [row for row in rows if row["source_field"] == field]
        by_field[field] = {
            "count": len(values),
            "min_splitter_tokens": min(values) if values else None,
            "median_splitter_tokens": _percentile([float(v) for v in values], 0.5),
            "mean_splitter_tokens": round(sum(values) / len(values), 3) if values else None,
            "p95_splitter_tokens": _percentile([float(v) for v in values], 0.95),
            "max_splitter_tokens": max(values) if values else None,
            "windowed_source_text_count": sum(int(row["windowed"]) for row in field_rows),
            "inference_window_count": sum(int(row["adapter_window_count"]) for row in field_rows),
        }

    rows.sort(key=lambda row: (str(row["canonical_id"]), str(row["source_field"])))
    reference_rows.sort(
        key=lambda row: (
            str(row["canonical_id"]),
            str(row["source_field"]),
            int(row["char_start"]),
            str(row["reference_id"]),
        )
    )
    too_wide = [row for row in reference_rows if row["exceeds_model_max_width"]]
    not_contained = [
        row for row in reference_rows
        if not row["fully_contained_in_at_least_one_adapter_window"]
    ]
    markup_rows = [row for row in reference_rows if row["markup_like_surface"]]

    return {
        "schema_version": "scientific_entity_gliner_windowing_completeness_audit_v0.1",
        "checkpoint_model_id": str(audit_cfg.get("checkpoint_model_id")),
        "checkpoint_revision": str(audit_cfg.get("checkpoint_revision")),
        "model_max_len": model_max_len,
        "model_max_width": model_max_width,
        "max_len_unit": "gliner_words_splitter_tokens_per_model_call",
        "max_width_unit": "gliner_words_splitter_tokens_per_candidate_span",
        "words_splitter_type": splitter_type,
        "splitter_implementation": "regex_equivalent_to_gliner_whitespace_words_splitter",
        "runtime_splitter_verification": runtime,
        "adapter_windowing": {
            "window_size_tokens": window_size,
            "window_overlap_tokens": overlap,
            "window_step_tokens": step,
            "whole_text_prefix_truncation_applied_by_adapter": False,
            "offsets_shifted_back_to_source_text": True,
        },
        "text_count": len(rows),
        "by_source_field": by_field,
        "source_texts_requiring_multiple_windows_count": sum(int(row["windowed"]) for row in rows),
        "total_adapter_inference_window_count": total_windows,
        "max_observed_window_token_count": max_observed_window_tokens,
        "window_exceeds_model_max_len_count": sum(
            1
            for row in rows
            for window in row["windows"]
            if int(window["splitter_token_count"]) > model_max_len
        ),
        "uncovered_splitter_token_count": uncovered_token_count,
        "all_source_splitter_tokens_covered_by_adapter_windows": uncovered_token_count == 0,
        "reference_mention_count": len(reference_rows),
        "reference_mentions_exceeding_model_max_width_count": len(too_wide),
        "false_negative_references_exceeding_model_max_width_count": sum(
            int(row["is_false_negative"]) for row in too_wide
        ),
        "reference_mentions_not_fully_contained_in_any_adapter_window_count": len(not_contained),
        "false_negative_references_not_fully_contained_in_any_adapter_window_count": sum(
            int(row["is_false_negative"]) for row in not_contained
        ),
        "markup_like_reference_mention_count": len(markup_rows),
        "markup_like_false_negative_reference_count": sum(
            int(row["is_false_negative"]) for row in markup_rows
        ),
        "rows": rows,
        "reference_mentions_exceeding_model_max_width": too_wide,
        "reference_mentions_not_fully_contained_in_any_adapter_window": not_contained,
        "markup_like_reference_mentions": markup_rows,
        "transformer_subword_limit_audited": False,
        "transformer_subword_truncation_claim_made": False,
        "model_inference_executed": False,
    }


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ScientificEntityHeldoutErrorAnalysisError(f"Expected JSON object: {path}")
    return payload


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line:
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ScientificEntityHeldoutErrorAnalysisError(
                f"Expected JSON object at {path}:{line_no}"
            )
        rows.append(payload)
    return rows


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_config(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ScientificEntityHeldoutErrorAnalysisError("Config must be a mapping")
    if payload.get("schema_version") != "scientific_entity_heldout_error_analysis_config_v0.1":
        raise ScientificEntityHeldoutErrorAnalysisError("Unexpected config schema_version")
    expected = payload.get("expected")
    safety = payload.get("safety")
    if not isinstance(expected, dict) or not isinstance(safety, dict):
        raise ScientificEntityHeldoutErrorAnalysisError("Config expected/safety sections are required")
    required_false = (
        "model_inference_allowed",
        "threshold_tuning_allowed",
        "model_or_tokenizer_download_allowed",
        "provider_api_allowed",
        "canonical_truth_mutation_allowed",
        "reconcile_input_allowed",
        "production_extractor_selection_allowed",
        "full_corpus_build_authorized",
        "publication_ready",
    )
    if safety.get("analysis_only") is not True:
        raise ScientificEntityHeldoutErrorAnalysisError("analysis_only must be true")
    for key in required_false:
        if safety.get(key) is not False:
            raise ScientificEntityHeldoutErrorAnalysisError(f"{key} must be false")
    audit = payload.get("gliner_windowing_audit")
    if not isinstance(audit, dict):
        raise ScientificEntityHeldoutErrorAnalysisError("gliner_windowing_audit section is required")
    model_max_len = int(audit.get("model_max_len", 0))
    model_max_width = int(audit.get("model_max_width", 0))
    window_size = int(audit.get("window_size_tokens", 0))
    overlap = int(audit.get("window_overlap_tokens", -1))
    if model_max_len <= 0 or model_max_width <= 0:
        raise ScientificEntityHeldoutErrorAnalysisError("pinned GLiNER model limits must be positive")
    if window_size <= 0 or window_size > model_max_len:
        raise ScientificEntityHeldoutErrorAnalysisError("window_size_tokens must be <= model_max_len")
    if overlap < model_max_width - 1 or overlap >= window_size:
        raise ScientificEntityHeldoutErrorAnalysisError("window overlap does not preserve max-width spans")
    if audit.get("words_splitter_type") != "whitespace":
        raise ScientificEntityHeldoutErrorAnalysisError("pinned words_splitter_type must be whitespace")
    if not str(audit.get("checkpoint_model_id", "")) or not str(audit.get("checkpoint_revision", "")):
        raise ScientificEntityHeldoutErrorAnalysisError("pinned checkpoint model id/revision are required")
    return payload


def resolve_project_path(project_root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else project_root / path


def _percentile(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    if not 0 <= q <= 1:
        raise ScientificEntityHeldoutErrorAnalysisError(f"Invalid percentile {q}")
    ordered = sorted(float(v) for v in values)
    if len(ordered) == 1:
        return round(ordered[0], 6)
    pos = (len(ordered) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        value = ordered[lo]
    else:
        value = ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)
    return round(value, 6)


def _confidence_summary(values: Iterable[float]) -> dict[str, Any]:
    rows = [float(v) for v in values]
    if not rows:
        return {
            "count": 0,
            "min": None,
            "p25": None,
            "median": None,
            "mean": None,
            "p75": None,
            "max": None,
        }
    return {
        "count": len(rows),
        "min": round(min(rows), 6),
        "p25": _percentile(rows, 0.25),
        "median": _percentile(rows, 0.5),
        "mean": round(sum(rows) / len(rows), 6),
        "p75": _percentile(rows, 0.75),
        "max": round(max(rows), 6),
    }


def _index(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        value = row.get(key)
        if value is None:
            continue
        token = str(value)
        if token in result:
            raise ScientificEntityHeldoutErrorAnalysisError(f"Duplicate {key}: {token}")
        result[token] = row
    return result


def _confidence(row: Mapping[str, Any] | None) -> float | None:
    if row is None:
        return None
    value = row.get("confidence_score")
    if value is None:
        return None
    return float(value)


def _safe_surface(row: Mapping[str, Any] | None) -> str | None:
    if row is None:
        return None
    value = row.get("surface")
    return None if value is None else str(value)


def _doc_text(doc: Mapping[str, Any] | None, field: str | None) -> str | None:
    if doc is None or field not in {"title", "abstract"}:
        return None
    value = doc.get(field)
    return value if isinstance(value, str) else None


def _excerpt(text: str | None, start: int | None, end: int | None, radius: int = 60) -> str | None:
    if text is None or start is None or end is None:
        return None
    left = max(0, int(start) - radius)
    right = min(len(text), int(end) + radius)
    return text[left:right]


def _validate_inputs(
    *,
    metrics: Mapping[str, Any],
    per_type_metrics: Mapping[str, Any],
    matches: Sequence[Mapping[str, Any]],
    errors: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> None:
    expected = config["expected"]
    evaluation_id = str(expected["evaluation_id"])
    if metrics.get("evaluation_id") != evaluation_id:
        raise ScientificEntityHeldoutErrorAnalysisError("metrics evaluation_id mismatch")
    if per_type_metrics.get("evaluation_id") != evaluation_id:
        raise ScientificEntityHeldoutErrorAnalysisError("per_type_metrics evaluation_id mismatch")
    for row in list(matches) + list(errors):
        if row.get("evaluation_id") != evaluation_id:
            raise ScientificEntityHeldoutErrorAnalysisError("row evaluation_id mismatch")
    scalar_checks = {
        "document_count": metrics.get("document_count"),
        "reference_mention_count": metrics.get("reference_mention_count"),
        "prediction_mention_count": metrics.get("prediction_mention_count"),
        "exact_match_count": metrics.get("exact_match_count"),
        "relaxed_only_match_count": metrics.get("relaxed_only_match_count"),
    }
    for key, actual in scalar_checks.items():
        if int(actual) != int(expected[key]):
            raise ScientificEntityHeldoutErrorAnalysisError(
                f"Expected {key}={expected[key]}, got {actual}"
            )
    if len(errors) != int(expected["error_count"]):
        raise ScientificEntityHeldoutErrorAnalysisError("error_count mismatch")
    error_counts_raw = Counter(str(row.get("error_kind")) for row in errors)
    unknown_error_kinds = set(error_counts_raw) - set(ERROR_KINDS)
    if unknown_error_kinds:
        raise ScientificEntityHeldoutErrorAnalysisError(
            f"Unknown error kinds: {sorted(unknown_error_kinds)}"
        )
    error_counts = {kind: int(error_counts_raw.get(kind, 0)) for kind in ERROR_KINDS}
    if error_counts != dict(expected["error_count_by_kind"]):
        raise ScientificEntityHeldoutErrorAnalysisError(
            f"error_count_by_kind mismatch: {error_counts}"
        )
    allowed_types = tuple(str(x) for x in expected["entity_types"])
    if tuple(allowed_types) != ENTITY_TYPES:
        raise ScientificEntityHeldoutErrorAnalysisError("entity type contract mismatch")


def compute_error_analysis(
    *,
    metrics: Mapping[str, Any],
    per_type_metrics: Mapping[str, Any],
    matches: Sequence[Mapping[str, Any]],
    errors: Sequence[Mapping[str, Any]],
    predictions: Sequence[Mapping[str, Any]],
    references: Sequence[Mapping[str, Any]],
    documents: Sequence[Mapping[str, Any]],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    _validate_inputs(
        metrics=metrics,
        per_type_metrics=per_type_metrics,
        matches=matches,
        errors=errors,
        config=config,
    )
    pred_by_evidence = _index(predictions, "evidence_id")
    ref_by_id = _index(references, "reference_id")
    docs_by_id = _index(documents, "canonical_id")

    expected = config["expected"]
    if len(predictions) != int(expected["prediction_mention_count"]):
        raise ScientificEntityHeldoutErrorAnalysisError("prediction mention physical count mismatch")
    if len(references) != int(expected["reference_mention_count"]):
        raise ScientificEntityHeldoutErrorAnalysisError("reference mention physical count mismatch")
    if len(documents) != int(expected["document_count"]):
        raise ScientificEntityHeldoutErrorAnalysisError("document physical count mismatch")

    confusion_counts: Counter[tuple[str, str]] = Counter()
    reference_mismatch_totals: Counter[str] = Counter()
    prediction_mismatch_totals: Counter[str] = Counter()
    for row in errors:
        if row.get("error_kind") != "type_mismatch":
            continue
        ref_type = str(row["reference_entity_type"])
        pred_type = str(row["prediction_entity_type"])
        confusion_counts[(ref_type, pred_type)] += 1
        reference_mismatch_totals[ref_type] += 1
        prediction_mismatch_totals[pred_type] += 1

    total_type_mismatches = sum(confusion_counts.values())
    confusion_rows: list[dict[str, Any]] = []
    for (ref_type, pred_type), count in sorted(
        confusion_counts.items(), key=lambda item: (-item[1], item[0][0], item[0][1])
    ):
        ref_total = reference_mismatch_totals[ref_type]
        pred_total = prediction_mismatch_totals[pred_type]
        confusion_rows.append(
            {
                "reference_entity_type": ref_type,
                "prediction_entity_type": pred_type,
                "count": count,
                "share_of_all_type_mismatches": round(count / total_type_mismatches, 6),
                "share_within_reference_type_mismatches": round(count / ref_total, 6),
                "share_within_prediction_type_mismatches": round(count / pred_total, 6),
            }
        )

    breakdown: dict[str, dict[str, int]] = {
        entity_type: {
            "exact_match": 0,
            "relaxed_only_match": 0,
            "boundary_mismatch": 0,
            "type_mismatch_as_reference": 0,
            "type_mismatch_as_prediction": 0,
            "false_positive": 0,
            "false_negative": 0,
        }
        for entity_type in ENTITY_TYPES
    }
    for row in matches:
        entity_type = str(row["entity_type"])
        kind = str(row["match_kind"])
        if kind == "exact":
            breakdown[entity_type]["exact_match"] += 1
        elif kind == "relaxed":
            breakdown[entity_type]["relaxed_only_match"] += 1
        else:
            raise ScientificEntityHeldoutErrorAnalysisError(f"Unknown match_kind: {kind}")
    for row in errors:
        kind = str(row["error_kind"])
        ref_type = row.get("reference_entity_type")
        pred_type = row.get("prediction_entity_type")
        if kind == "boundary_mismatch" and ref_type is not None:
            breakdown[str(ref_type)]["boundary_mismatch"] += 1
        elif kind == "type_mismatch":
            breakdown[str(ref_type)]["type_mismatch_as_reference"] += 1
            breakdown[str(pred_type)]["type_mismatch_as_prediction"] += 1
        elif kind == "false_positive" and pred_type is not None:
            breakdown[str(pred_type)]["false_positive"] += 1
        elif kind == "false_negative" and ref_type is not None:
            breakdown[str(ref_type)]["false_negative"] += 1

    confidence_values: dict[str, list[float]] = defaultdict(list)
    confidence_by_type: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    confidence_by_field: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    confusion_confidence: dict[tuple[str, str], list[float]] = defaultdict(list)

    for row in matches:
        pred = pred_by_evidence.get(str(row["prediction_evidence_id"]))
        score = _confidence(pred)
        if score is None:
            continue
        group = "exact" if row.get("match_kind") == "exact" else "relaxed_only"
        entity_type = str(row["entity_type"])
        field = str(row["source_field"])
        confidence_values[group].append(score)
        confidence_by_type[group][entity_type].append(score)
        confidence_by_field[group][field].append(score)

    for row in errors:
        kind = str(row["error_kind"])
        if kind == "false_negative":
            continue
        evidence_id = row.get("prediction_evidence_id")
        pred = pred_by_evidence.get(str(evidence_id)) if evidence_id else None
        score = _confidence(pred)
        if score is None:
            continue
        pred_type = str(row.get("prediction_entity_type") or pred.get("entity_type"))
        field = str(row["source_field"])
        confidence_values[kind].append(score)
        confidence_by_type[kind][pred_type].append(score)
        confidence_by_field[kind][field].append(score)
        if kind == "type_mismatch":
            pair = (str(row["reference_entity_type"]), pred_type)
            confusion_confidence[pair].append(score)

    confidence_payload = {
        "schema_version": "scientific_entity_heldout_confidence_analysis_v0.1",
        "confidence_scores_reinterpreted_as_probabilities": False,
        "groups": {
            group: _confidence_summary(confidence_values.get(group, []))
            for group in CONFIDENCE_GROUPS
        },
        "by_group_and_prediction_type": {
            group: {
                entity_type: _confidence_summary(confidence_by_type[group].get(entity_type, []))
                for entity_type in ENTITY_TYPES
            }
            for group in CONFIDENCE_GROUPS
        },
        "by_group_and_source_field": {
            group: {
                field: _confidence_summary(confidence_by_field[group].get(field, []))
                for field in ("title", "abstract")
            }
            for group in CONFIDENCE_GROUPS
        },
        "type_mismatch_pairs": [
            {
                "reference_entity_type": ref_type,
                "prediction_entity_type": pred_type,
                "confidence": _confidence_summary(values),
            }
            for (ref_type, pred_type), values in sorted(
                confusion_confidence.items(), key=lambda item: (-len(item[1]), item[0][0], item[0][1])
            )
        ],
    }

    field_lengths: dict[str, list[int]] = {"title": [], "abstract": []}
    for doc in documents:
        for field in field_lengths:
            text = doc.get(field)
            if isinstance(text, str):
                field_lengths[field].append(len(text))
    length_summary = {
        field: {
            "count": len(values),
            "min_chars": min(values) if values else None,
            "median_chars": _percentile([float(v) for v in values], 0.5),
            "mean_chars": round(sum(values) / len(values), 3) if values else None,
            "p95_chars": _percentile([float(v) for v in values], 0.95),
            "max_chars": max(values) if values else None,
        }
        for field, values in field_lengths.items()
    }
    windowing_audit = _build_gliner_windowing_audit(
        documents=documents,
        references=references,
        errors=errors,
        config=config,
    )

    examples_per_family = int(config.get("diagnostics", {}).get("representative_examples_per_family", 5))
    example_candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in errors:
        kind = str(row["error_kind"])
        ref = ref_by_id.get(str(row["reference_id"])) if row.get("reference_id") else None
        evidence_id = row.get("prediction_evidence_id")
        pred = pred_by_evidence.get(str(evidence_id)) if evidence_id else None
        canonical_id = str(row["canonical_id"])
        field = str(row["source_field"])
        doc = docs_by_id.get(canonical_id)
        ref_start = int(row["reference_char_start"]) if row.get("reference_char_start") is not None else None
        ref_end = int(row["reference_char_end"]) if row.get("reference_char_end") is not None else None
        pred_start = int(row["prediction_char_start"]) if row.get("prediction_char_start") is not None else None
        pred_end = int(row["prediction_char_end"]) if row.get("prediction_char_end") is not None else None
        score = _confidence(pred)
        if kind == "type_mismatch":
            family = f"type_mismatch:{row['reference_entity_type']}->{row['prediction_entity_type']}"
        elif kind == "false_positive":
            family = f"false_positive:{row['prediction_entity_type']}"
        elif kind == "false_negative":
            family = f"false_negative:{row['reference_entity_type']}"
        elif kind == "boundary_mismatch":
            family = f"boundary_mismatch:{row['reference_entity_type']}"
        else:
            family = kind
        source_text = _doc_text(doc, field)
        reference_surface = _surface_from_span(source_text, ref_start, ref_end)
        prediction_surface = _surface_from_span(source_text, pred_start, pred_end)
        stored_reference_surface = _safe_surface(ref)
        stored_prediction_surface = _safe_surface(pred)
        if stored_reference_surface is not None and reference_surface != stored_reference_surface:
            raise ScientificEntityHeldoutErrorAnalysisError(
                f"Reference surface/source slice mismatch for error_id={row['error_id']}"
            )
        if stored_prediction_surface is not None and prediction_surface != stored_prediction_surface:
            raise ScientificEntityHeldoutErrorAnalysisError(
                f"Prediction surface/source slice mismatch for error_id={row['error_id']}"
            )
        candidate = {
            "error_id": row["error_id"],
            "error_kind": kind,
            "family": family,
            "canonical_id": canonical_id,
            "source_field": field,
            "reference_entity_type": row.get("reference_entity_type"),
            "prediction_entity_type": row.get("prediction_entity_type"),
            "reference_surface": reference_surface,
            "prediction_surface": prediction_surface,
            "reference_char_start": ref_start,
            "reference_char_end": ref_end,
            "prediction_char_start": pred_start,
            "prediction_char_end": pred_end,
            "char_iou": row.get("char_iou"),
            "confidence_score": score,
            "source_excerpt": _excerpt(
                source_text,
                ref_start if ref_start is not None else pred_start,
                ref_end if ref_end is not None else pred_end,
            ),
        }
        example_candidates[family].append(candidate)

    selected_examples: list[dict[str, Any]] = []
    for family in sorted(example_candidates):
        rows = example_candidates[family]
        rows.sort(
            key=lambda row: (
                -(float(row["confidence_score"]) if row["confidence_score"] is not None else -1.0),
                str(row["canonical_id"]),
                str(row["error_id"]),
            )
        )
        for rank, row in enumerate(rows[:examples_per_family], start=1):
            selected_examples.append({"rank_within_family": rank, **row})

    per_type_lookup = {
        str(row["entity_type"]): row for row in per_type_metrics.get("rows", [])
    }
    type_confusions = {
        "schema_version": "scientific_entity_heldout_type_confusions_v0.1",
        "total_type_mismatch_count": total_type_mismatches,
        "rows": confusion_rows,
        "predicted_type_mismatch_totals": dict(sorted(prediction_mismatch_totals.items())),
        "reference_type_mismatch_totals": dict(sorted(reference_mismatch_totals.items())),
        "method_semantic_sink_share": round(
            prediction_mismatch_totals.get("method", 0) / total_type_mismatches, 6
        ) if total_type_mismatches else 0.0,
    }

    summary = {
        "schema_version": "scientific_entity_heldout_error_analysis_summary_v0.1",
        "evaluation_id": metrics["evaluation_id"],
        "document_count": metrics["document_count"],
        "reference_mention_count": metrics["reference_mention_count"],
        "prediction_mention_count": metrics["prediction_mention_count"],
        "exact_match_count": metrics["exact_match_count"],
        "relaxed_only_match_count": metrics["relaxed_only_match_count"],
        "error_count": len(errors),
        "error_count_by_kind": {kind: int(Counter(str(row["error_kind"]) for row in errors).get(kind, 0)) for kind in ERROR_KINDS},
        "per_type_exact": {
            entity_type: per_type_lookup[entity_type]["metrics"]["exact"]
            for entity_type in ENTITY_TYPES
        },
        "error_breakdown_by_type": breakdown,
        "source_text_character_length_summary": length_summary,
        "gliner_windowing_completeness_audit_available": True,
        "gliner_windowed_source_text_count": windowing_audit["source_texts_requiring_multiple_windows_count"],
        "gliner_total_inference_window_count": windowing_audit["total_adapter_inference_window_count"],
        "gliner_uncovered_splitter_token_count": windowing_audit["uncovered_splitter_token_count"],
        "gliner_reference_mentions_exceeding_model_max_width_count": windowing_audit["reference_mentions_exceeding_model_max_width_count"],
        "gliner_false_negative_references_exceeding_model_max_width_count": windowing_audit["false_negative_references_exceeding_model_max_width_count"],
        "gliner_markup_like_reference_mention_count": windowing_audit["markup_like_reference_mention_count"],
        "transformer_subword_limit_audit_available": False,
        "transformer_subword_truncation_claim_made": False,
        "analysis_only": True,
        "heldout_consumed_for_future_v02_tuning": True,
        "model_inference_executed": False,
        "threshold_tuning_executed": False,
        "canonical_truth_mutated": False,
        "production_extractor_selected": False,
        "full_corpus_build_authorized": False,
        "publication_ready": False,
        "next_slice": "review_error_analysis_then_freeze_one_v02_hypothesis",
    }

    return {
        "summary": summary,
        "type_confusions": type_confusions,
        "confidence_analysis": confidence_payload,
        "gliner_windowing_audit": windowing_audit,
        "error_examples": selected_examples,
    }
