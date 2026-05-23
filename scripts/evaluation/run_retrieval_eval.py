from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise RuntimeError(
        "PyYAML is required for retrieval evaluation config loading."
    ) from exc

from services.api.runtime import get_runtime
from services.api.search_service import run_search
from services.api.settings import get_settings


DEFAULT_CONFIG_PATH = Path("configs/retrieval_eval_v1.yaml")
DEFAULT_REPORTS_DIR = Path("artifacts/reports/evaluation")


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Retrieval eval config not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        payload = yaml.safe_load(f) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Retrieval eval config must be a YAML mapping: {path}")
    return payload


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Golden queries JSONL not found: {path}")

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"Golden query row must be JSON object at {path}:{line_no}")
            rows.append(row)
    return rows


def to_plain(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {k: to_plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_plain(v) for v in value]
    return value


def serialize_response(response: Any) -> dict[str, Any]:
    if hasattr(response, "model_dump"):
        payload = response.model_dump()
    elif isinstance(response, dict):
        payload = response
    else:
        raise TypeError(f"Unsupported search response type: {type(response)!r}")

    payload["meta"] = to_plain(payload.get("meta"))
    payload["results"] = [to_plain(item) for item in payload.get("results", [])]
    return payload


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").lower().replace("-", " ").split())


def get_nested(payload: dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = payload
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def document_from_result(result: dict[str, Any]) -> dict[str, Any]:
    doc = result.get("document")
    if isinstance(doc, dict):
        return doc
    return {}


def canonical_id_from_result(result: dict[str, Any]) -> str:
    doc = document_from_result(result)
    value = (
        result.get("canonical_id")
        or doc.get("canonical_id")
        or get_nested(result, "document", "canonical_id")
    )
    return str(value or "")


def title_from_result(result: dict[str, Any]) -> str:
    doc = document_from_result(result)
    return str(result.get("title") or doc.get("title") or "")


def result_search_text(result: dict[str, Any]) -> str:
    doc = document_from_result(result)
    parts: list[str] = []

    for key in (
        "title",
        "abstract",
        "primary_category",
        "venue",
        "journal",
        "conference",
        "publisher",
        "publication_type",
        "comment",
        "journal_ref",
        "language",
    ):
        value = result.get(key) or doc.get(key)
        if value:
            parts.append(str(value))

    for key in ("authors", "categories", "concepts", "keywords", "tags", "source_families"):
        value = result.get(key) or doc.get(key)
        if isinstance(value, list):
            parts.extend(str(x) for x in value if x)
        elif value:
            parts.append(str(value))

    return normalize_text(" ".join(parts))


def graded_relevance_map(case: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}

    for item in case.get("graded_relevance") or []:
        if not isinstance(item, dict):
            continue
        canonical_id = item.get("canonical_id")
        if not canonical_id:
            continue
        try:
            grade = float(item.get("grade", 1.0))
        except Exception:
            grade = 1.0
        out[str(canonical_id)] = max(0.0, grade)

    expected = case.get("expected") or {}
    for canonical_id in expected.get("canonical_ids") or []:
        canonical_id = str(canonical_id).strip()
        if canonical_id and canonical_id not in out:
            out[canonical_id] = 3.0

    return out


def weak_relevance_grade(result: dict[str, Any], case: dict[str, Any]) -> float:
    expected = case.get("expected") or {}
    title = normalize_text(title_from_result(result))
    text = result_search_text(result)

    title_substrings = [
        normalize_text(x)
        for x in expected.get("title_substrings") or []
        if normalize_text(x)
    ]
    if title_substrings and all(term in title for term in title_substrings):
        return 1.0

    title_any_substrings = [
        normalize_text(x)
        for x in expected.get("title_any_substrings") or []
        if normalize_text(x)
    ]
    if title_any_substrings and any(term in title for term in title_any_substrings):
        return 1.0

    must_have_any_terms = [
        normalize_text(x)
        for x in expected.get("must_have_any_terms") or []
        if normalize_text(x)
    ]
    if must_have_any_terms and any(term in text for term in must_have_any_terms):
        return 1.0

    return 0.0


def relevance_grade(result: dict[str, Any], case: dict[str, Any], grades_by_id: dict[str, float]) -> float:
    canonical_id = canonical_id_from_result(result)

    if canonical_id and canonical_id in grades_by_id:
        return float(grades_by_id[canonical_id])

    expected = case.get("expected") or {}

    # If a case has explicit canonical relevance labels, evaluate it strictly.
    # This prevents weak title/term matching from making the benchmark too easy.
    strict_canonical_relevance = bool(
        expected.get("strict_canonical_relevance", bool(grades_by_id))
    )

    if grades_by_id and strict_canonical_relevance:
        return 0.0

    return weak_relevance_grade(result, case)


def expected_relevant_count(case: dict[str, Any], grades_by_id: dict[str, float]) -> int:
    expected = case.get("expected") or {}

    explicit = expected.get("relevant_count")
    if explicit is not None:
        try:
            return max(1, int(explicit))
        except Exception:
            pass

    if grades_by_id:
        return max(1, len(grades_by_id))

    # For weak-pattern cases we do not know corpus-level relevant count,
    # so treat the task as "find at least one relevant result".
    if (
        expected.get("title_substrings")
        or expected.get("title_any_substrings")
        or expected.get("must_have_any_terms")
    ):
        return 1

    return 1


def dcg(grades: list[float]) -> float:
    total = 0.0
    for idx, grade in enumerate(grades, start=1):
        if grade <= 0:
            continue
        total += (2.0 ** grade - 1.0) / math.log2(idx + 1.0)
    return total


def ideal_grades_for_case(
    *,
    case: dict[str, Any],
    grades_by_id: dict[str, float],
    relevant_count: int,
    k: int,
) -> list[float]:
    known_grades = sorted((g for g in grades_by_id.values() if g > 0), reverse=True)
    if known_grades:
        return known_grades[:k]

    # Weak-pattern-only cases: ideal is a single grade-1 hit.
    return [1.0] * min(max(1, relevant_count), k)


def metrics_at_k(
    *,
    case: dict[str, Any],
    results: list[dict[str, Any]],
    k: int,
) -> dict[str, Any]:
    top = results[:k]
    grades_by_id = graded_relevance_map(case)
    relevant_count = expected_relevant_count(case, grades_by_id)

    grades = [
        relevance_grade(result, case, grades_by_id)
        for result in top
    ]
    relevant_flags = [grade > 0.0 for grade in grades]

    hits = sum(1 for flag in relevant_flags if flag)
    first_rank = None
    for idx, flag in enumerate(relevant_flags, start=1):
        if flag:
            first_rank = idx
            break

    precision = hits / max(1, len(top))
    recall = min(1.0, hits / max(1, relevant_count))
    hit = 1.0 if hits > 0 else 0.0
    mrr = 0.0 if first_rank is None else 1.0 / first_rank

    actual_dcg = dcg(grades)

    if grades_by_id:
        ideal_grades = ideal_grades_for_case(
            case=case,
            grades_by_id=grades_by_id,
            relevant_count=relevant_count,
            k=k,
        )
    else:
        # Weak-pattern-only cases do not have a known corpus-level relevant set.
        # For v1 baseline, approximate ideal ranking from observed weak matches
        # so nDCG remains bounded and diagnostic rather than mathematically inflated.
        ideal_grades = sorted([g for g in grades if g > 0.0], reverse=True)

    ideal_dcg = dcg(ideal_grades)
    ndcg = 0.0 if ideal_dcg <= 0 else min(1.0, actual_dcg / ideal_dcg)

    matched_results = []
    for idx, (result, grade) in enumerate(zip(top, grades), start=1):
        if grade <= 0:
            continue
        matched_results.append(
            {
                "rank": idx,
                "canonical_id": canonical_id_from_result(result),
                "title": title_from_result(result),
                "grade": round(float(grade), 6),
            }
        )

    return {
        "k": k,
        "results_count": len(top),
        "relevant_count_assumed": relevant_count,
        "hits_count": hits,
        "hit": round(hit, 6),
        "precision": round(float(precision), 6),
        "recall": round(float(recall), 6),
        "mrr": round(float(mrr), 6),
        "ndcg": round(float(ndcg), 6),
        "first_relevant_rank": first_rank,
        "matched_results": matched_results,
    }


def mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(float(sum(values) / len(values)), 6)


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    values = sorted(float(v) for v in values)
    if len(values) == 1:
        return round(values[0], 3)
    rank = (len(values) - 1) * p
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return round(values[int(rank)], 3)
    weight = rank - low
    return round(values[low] * (1 - weight) + values[high] * weight, 3)


def build_runtime(backend_mode: str):
    os.environ["ML_RADAR_SEARCH_BACKEND"] = backend_mode
    get_settings.cache_clear()

    runtime = get_runtime()
    runtime.load()
    snapshot = runtime.runtime_snapshot()

    if not snapshot.get("ready"):
        raise RuntimeError(
            f"Runtime not ready. backend={snapshot.get('backend_mode')}, "
            f"last_load_error={snapshot.get('last_load_error')}"
        )

    return runtime


def run_one_search(
    runtime: Any,
    *,
    query: str,
    mode_label: str,
    top_k: int,
) -> dict[str, Any]:
    if mode_label == "hybrid_ranked":
        mode = "hybrid"
        rank = True
    else:
        mode = mode_label
        rank = False

    t0 = time.perf_counter()
    response = run_search(
        runtime=runtime,
        query=query,
        mode=mode,
        top_k=top_k,
        rank=rank,
        year_from=None,
        year_to=None,
        category=None,
        source=None,
        publication_type=None,
        venue=None,
        open_access=None,
        has_code_link=None,
        offset=0,
        sort_by="relevance",
    )
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 3)

    payload = serialize_response(response)
    payload["mode_label"] = mode_label
    payload["effective_mode"] = mode
    payload["rank"] = rank
    payload["timing_ms_wall"] = elapsed_ms
    return payload


def compact_result(result: dict[str, Any]) -> dict[str, Any]:
    doc = document_from_result(result)
    retrieval = result.get("retrieval") if isinstance(result.get("retrieval"), dict) else {}
    ranking = result.get("ranking") if isinstance(result.get("ranking"), dict) else {}

    return {
        "canonical_id": canonical_id_from_result(result),
        "title": title_from_result(result),
        "year": result.get("year") or doc.get("year"),
        "source_count": result.get("source_count") or doc.get("source_count"),
        "retrieval": retrieval,
        "ranking": ranking,
    }


def summarize_mode(
    *,
    case_runs: list[dict[str, Any]],
    mode: str,
    primary_k: int,
    top_k_values: list[int],
) -> dict[str, Any]:
    rows = [
        run
        for case in case_runs
        for run in case.get("runs", [])
        if run.get("mode") == mode
    ]

    errors = [row for row in rows if row.get("error")]
    latencies = [float(row.get("timing_ms_wall") or 0.0) for row in rows if not row.get("error")]

    metrics_for_primary = [
        row.get("metrics", {}).get(str(primary_k)) or row.get("metrics", {}).get(primary_k)
        for row in rows
        if not row.get("error")
    ]
    metrics_for_primary = [m for m in metrics_for_primary if isinstance(m, dict)]

    summary: dict[str, Any] = {
        "mode": mode,
        "runs_count": len(rows),
        "error_count": len(errors),
        "empty_result_count": sum(1 for row in rows if not row.get("error") and row.get("results_count", 0) == 0),
        "empty_result_rate": round(
            sum(1 for row in rows if not row.get("error") and row.get("results_count", 0) == 0)
            / max(1, len([r for r in rows if not r.get("error")])),
            6,
        ),
        "latency_ms": {
            "p50": percentile(latencies, 0.50),
            "p95": percentile(latencies, 0.95),
            "mean": round(float(statistics.mean(latencies)), 3) if latencies else None,
        },
        f"hit_at_{primary_k}": mean([float(m.get("hit", 0.0)) for m in metrics_for_primary]),
        f"precision_at_{primary_k}": mean([float(m.get("precision", 0.0)) for m in metrics_for_primary]),
        f"recall_at_{primary_k}": mean([float(m.get("recall", 0.0)) for m in metrics_for_primary]),
        f"mrr_at_{primary_k}": mean([float(m.get("mrr", 0.0)) for m in metrics_for_primary]),
        f"ndcg_at_{primary_k}": mean([float(m.get("ndcg", 0.0)) for m in metrics_for_primary]),
    }

    for k in top_k_values:
        metrics_k = [
            row.get("metrics", {}).get(str(k)) or row.get("metrics", {}).get(k)
            for row in rows
            if not row.get("error")
        ]
        metrics_k = [m for m in metrics_k if isinstance(m, dict)]
        summary[f"hit_at_{k}"] = mean([float(m.get("hit", 0.0)) for m in metrics_k])
        summary[f"recall_at_{k}"] = mean([float(m.get("recall", 0.0)) for m in metrics_k])
        summary[f"mrr_at_{k}"] = mean([float(m.get("mrr", 0.0)) for m in metrics_k])
        summary[f"ndcg_at_{k}"] = mean([float(m.get("ndcg", 0.0)) for m in metrics_k])

    return summary


def summarize_groups(
    *,
    case_runs: list[dict[str, Any]],
    modes: list[str],
    primary_k: int,
) -> dict[str, Any]:
    by_group: dict[str, list[dict[str, Any]]] = {}
    for case in case_runs:
        by_group.setdefault(str(case.get("group") or "ungrouped"), []).append(case)

    out: dict[str, Any] = {}
    for group, cases in sorted(by_group.items()):
        group_summary: dict[str, Any] = {
            "cases_count": len(cases),
            "modes": {},
        }

        for mode in modes:
            metrics = []
            for case in cases:
                for run in case.get("runs", []):
                    if run.get("mode") != mode or run.get("error"):
                        continue
                    m = run.get("metrics", {}).get(str(primary_k)) or run.get("metrics", {}).get(primary_k)
                    if isinstance(m, dict):
                        metrics.append(m)

            group_summary["modes"][mode] = {
                f"hit_at_{primary_k}": mean([float(m.get("hit", 0.0)) for m in metrics]),
                f"recall_at_{primary_k}": mean([float(m.get("recall", 0.0)) for m in metrics]),
                f"mrr_at_{primary_k}": mean([float(m.get("mrr", 0.0)) for m in metrics]),
                f"ndcg_at_{primary_k}": mean([float(m.get("ndcg", 0.0)) for m in metrics]),
            }

        out[group] = group_summary

    return out

def metric_from_run(run: dict[str, Any], k: int, metric_name: str) -> float:
    metrics = run.get("metrics") or {}
    item = metrics.get(str(k)) or metrics.get(k) or {}
    try:
        return float(item.get(metric_name, 0.0) or 0.0)
    except Exception:
        return 0.0


def metric_from_mode_summary(
    mode_summary: dict[str, Any],
    mode: str,
    metric_name: str,
    k: int,
) -> float:
    key = f"{metric_name}_at_{k}"
    try:
        return float((mode_summary.get(mode) or {}).get(key, 0.0) or 0.0)
    except Exception:
        return 0.0


def latency_p50_from_mode_summary(mode_summary: dict[str, Any], mode: str) -> float | None:
    latency = (mode_summary.get(mode) or {}).get("latency_ms") or {}
    value = latency.get("p50")
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def build_pairwise_mode_comparison(
    *,
    mode_summary: dict[str, Any],
    modes: list[str],
    primary_k: int,
) -> dict[str, Any]:
    pairs = [
        ("hybrid", "lexical"),
        ("hybrid", "dense"),
        ("hybrid_ranked", "hybrid"),
        ("dense", "lexical"),
    ]

    out: dict[str, Any] = {}

    for left, right in pairs:
        if left not in modes or right not in modes:
            continue

        item: dict[str, Any] = {}
        for metric_name in ("hit", "recall", "mrr", "ndcg"):
            left_value = metric_from_mode_summary(
                mode_summary=mode_summary,
                mode=left,
                metric_name=metric_name,
                k=primary_k,
            )
            right_value = metric_from_mode_summary(
                mode_summary=mode_summary,
                mode=right,
                metric_name=metric_name,
                k=primary_k,
            )
            delta = round(left_value - right_value, 6)

            item[f"{metric_name}_at_{primary_k}"] = {
                left: round(left_value, 6),
                right: round(right_value, 6),
                "delta": delta,
                "winner": left if delta > 0 else right if delta < 0 else "tie",
            }

        left_p50 = latency_p50_from_mode_summary(mode_summary, left)
        right_p50 = latency_p50_from_mode_summary(mode_summary, right)
        latency_delta = None
        latency_ratio = None
        if left_p50 is not None and right_p50 not in (None, 0):
            latency_delta = round(left_p50 - right_p50, 3)
            latency_ratio = round(left_p50 / right_p50, 3)

        item["latency_p50_ms"] = {
            left: left_p50,
            right: right_p50,
            "delta": latency_delta,
            "ratio": latency_ratio,
            "faster": (
                left
                if left_p50 is not None and right_p50 is not None and left_p50 < right_p50
                else right
                if left_p50 is not None and right_p50 is not None and right_p50 < left_p50
                else "tie"
            ),
        }

        out[f"{left}_vs_{right}"] = item

    return out


def build_mode_ranking(
    *,
    mode_summary: dict[str, Any],
    modes: list[str],
    primary_k: int,
) -> dict[str, Any]:
    out: dict[str, Any] = {}

    for metric_name in ("hit", "recall", "mrr", "ndcg"):
        rows = []
        for mode in modes:
            rows.append(
                {
                    "mode": mode,
                    "value": metric_from_mode_summary(
                        mode_summary=mode_summary,
                        mode=mode,
                        metric_name=metric_name,
                        k=primary_k,
                    ),
                }
            )
        rows.sort(key=lambda x: x["value"], reverse=True)
        out[f"{metric_name}_at_{primary_k}"] = rows

    latency_rows = []
    for mode in modes:
        p50 = latency_p50_from_mode_summary(mode_summary, mode)
        if p50 is not None:
            latency_rows.append({"mode": mode, "p50_ms": p50})
    latency_rows.sort(key=lambda x: x["p50_ms"])

    out["latency_p50_ms"] = latency_rows
    return out


def build_query_mode_diagnostics(
    *,
    case_runs: list[dict[str, Any]],
    modes: list[str],
    primary_k: int,
) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []

    for case in case_runs:
        runs_by_mode = {
            run.get("mode"): run
            for run in case.get("runs", [])
            if run.get("mode") in modes and not run.get("error")
        }

        if not runs_by_mode:
            continue

        per_mode: dict[str, dict[str, float]] = {}
        for mode, run in runs_by_mode.items():
            per_mode[mode] = {
                "hit": metric_from_run(run, primary_k, "hit"),
                "recall": metric_from_run(run, primary_k, "recall"),
                "mrr": metric_from_run(run, primary_k, "mrr"),
                "ndcg": metric_from_run(run, primary_k, "ndcg"),
            }

        best_by_recall = sorted(
            per_mode.items(),
            key=lambda x: (x[1]["recall"], x[1]["mrr"], x[1]["ndcg"]),
            reverse=True,
        )
        best_by_mrr = sorted(
            per_mode.items(),
            key=lambda x: (x[1]["mrr"], x[1]["recall"], x[1]["ndcg"]),
            reverse=True,
        )
        best_by_ndcg = sorted(
            per_mode.items(),
            key=lambda x: (x[1]["ndcg"], x[1]["recall"], x[1]["mrr"]),
            reverse=True,
        )

        failed_modes = [
            mode
            for mode, values in per_mode.items()
            if values["hit"] <= 0.0
        ]

        notes: list[str] = []

        lexical = per_mode.get("lexical")
        dense = per_mode.get("dense")
        hybrid = per_mode.get("hybrid")
        hybrid_ranked = per_mode.get("hybrid_ranked")

        if lexical and lexical["hit"] <= 0 and dense and dense["hit"] > 0:
            notes.append("dense_recovers_lexical_failure")

        if lexical and dense and dense["recall"] > lexical["recall"]:
            notes.append("dense_recall_gt_lexical")

        if lexical and dense and lexical["recall"] > dense["recall"]:
            notes.append("lexical_recall_gt_dense")

        if hybrid and lexical and hybrid["recall"] > lexical["recall"]:
            notes.append("hybrid_recall_gt_lexical")

        if hybrid and dense and hybrid["recall"] > dense["recall"]:
            notes.append("hybrid_recall_gt_dense")

        if hybrid_ranked and hybrid and hybrid_ranked["recall"] > hybrid["recall"]:
            notes.append("hybrid_ranked_improves_recall")

        if hybrid_ranked and hybrid and hybrid_ranked["ndcg"] < hybrid["ndcg"]:
            notes.append("hybrid_ranked_lowers_ndcg")

        if hybrid and dense and hybrid["recall"] < dense["recall"]:
            notes.append("hybrid_recall_lt_dense")

        diagnostics.append(
            {
                "query_id": case.get("query_id"),
                "query": case.get("query"),
                "group": case.get("group"),
                "best_by_recall": best_by_recall[0][0] if best_by_recall else None,
                "best_by_mrr": best_by_mrr[0][0] if best_by_mrr else None,
                "best_by_ndcg": best_by_ndcg[0][0] if best_by_ndcg else None,
                "failed_modes": failed_modes,
                "notes": notes,
                "per_mode": per_mode,
            }
        )

    return diagnostics


def build_mode_comparison_summary(
    *,
    case_runs: list[dict[str, Any]],
    mode_summary: dict[str, Any],
    modes: list[str],
    primary_k: int,
) -> dict[str, Any]:
    query_diagnostics = build_query_mode_diagnostics(
        case_runs=case_runs,
        modes=modes,
        primary_k=primary_k,
    )

    note_counts: dict[str, int] = {}
    failed_mode_counts: dict[str, int] = {}

    for item in query_diagnostics:
        for note in item.get("notes", []):
            note_counts[note] = note_counts.get(note, 0) + 1
        for mode in item.get("failed_modes", []):
            failed_mode_counts[mode] = failed_mode_counts.get(mode, 0) + 1

    return {
        "primary_k": primary_k,
        "mode_ranking": build_mode_ranking(
            mode_summary=mode_summary,
            modes=modes,
            primary_k=primary_k,
        ),
        "pairwise": build_pairwise_mode_comparison(
            mode_summary=mode_summary,
            modes=modes,
            primary_k=primary_k,
        ),
        "query_diagnostics": query_diagnostics,
        "note_counts": dict(sorted(note_counts.items())),
        "failed_mode_counts": dict(sorted(failed_mode_counts.items())),
    }

def build_markdown(report: dict[str, Any]) -> str:
    primary_k = report["config"]["primary_k"]

    lines: list[str] = []
    lines.append("# Retrieval evaluation v1")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at_utc']}`")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Backend mode: `{report['runtime'].get('backend_mode')}`")
    lines.append(f"- Build id: `{report['runtime'].get('build_id')}`")
    lines.append(f"- Corpus doc count: `{report['runtime'].get('corpus_doc_count')}`")
    lines.append(f"- Enabled cases: **{report['summary']['enabled_cases_count']}**")
    lines.append(f"- Primary k: **{primary_k}**")
    lines.append("")

    lines.append("## Mode summary")
    lines.append("")
    lines.append("| Mode | Hit@K | Recall@K | MRR@K | nDCG@K | Empty rate | p50 ms | p95 ms |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for mode, row in report["mode_summary"].items():
        lat = row.get("latency_ms") or {}
        lines.append(
            f"| `{mode}` | "
            f"{row.get(f'hit_at_{primary_k}', 0):.3f} | "
            f"{row.get(f'recall_at_{primary_k}', 0):.3f} | "
            f"{row.get(f'mrr_at_{primary_k}', 0):.3f} | "
            f"{row.get(f'ndcg_at_{primary_k}', 0):.3f} | "
            f"{row.get('empty_result_rate', 0):.3f} | "
            f"{lat.get('p50')} | {lat.get('p95')} |"
        )
    lines.append("")

    comparison = report.get("comparison_summary") or {}
    mode_ranking = comparison.get("mode_ranking") or {}
    pairwise = comparison.get("pairwise") or {}
    query_diagnostics = comparison.get("query_diagnostics") or []
    note_counts = comparison.get("note_counts") or {}
    failed_mode_counts = comparison.get("failed_mode_counts") or {}

    lines.append("## Mode comparison diagnostics")
    lines.append("")

    lines.append("### Overall mode ranking")
    lines.append("")
    for metric_key, rows in mode_ranking.items():
        if not isinstance(rows, list) or not rows:
            continue

        lines.append(f"#### `{metric_key}`")
        for idx, row in enumerate(rows, start=1):
            if "value" in row:
                lines.append(f"{idx}. `{row['mode']}` — {row['value']:.3f}")
            elif "p50_ms" in row:
                lines.append(f"{idx}. `{row['mode']}` — {row['p50_ms']:.3f} ms")
        lines.append("")

    lines.append("### Pairwise deltas")
    lines.append("")
    if pairwise:
        lines.append("| Pair | Metric | Left | Right | Delta | Winner |")
        lines.append("|---|---|---:|---:|---:|---|")

        for pair_name, pair_item in pairwise.items():
            for metric_name, metric_item in pair_item.items():
                if metric_name == "latency_p50_ms":
                    continue

                modes_in_metric = [
                    key
                    for key in metric_item.keys()
                    if key not in {"delta", "winner"}
                ]
                if len(modes_in_metric) != 2:
                    continue

                left_mode, right_mode = modes_in_metric
                left_value = metric_item.get(left_mode)
                right_value = metric_item.get(right_mode)
                delta = metric_item.get("delta")
                winner = metric_item.get("winner")

                lines.append(
                    f"| `{pair_name}` | `{metric_name}` | "
                    f"{float(left_value):.3f} | {float(right_value):.3f} | "
                    f"{float(delta):+.3f} | `{winner}` |"
                )
        lines.append("")

    lines.append("### Diagnostic signals")
    lines.append("")
    if note_counts:
        for note, count in note_counts.items():
            lines.append(f"- `{note}`: **{count}**")
    else:
        lines.append("- none")
    lines.append("")

    lines.append("### Failed modes")
    lines.append("")
    if failed_mode_counts:
        for mode, count in failed_mode_counts.items():
            lines.append(f"- `{mode}`: **{count}**")
    else:
        lines.append("- none")
    lines.append("")

    lines.append("### Query-level mode comparison")
    lines.append("")
    lines.append("| Query | Best recall | Best MRR | Best nDCG | Failed modes | Notes |")
    lines.append("|---|---|---|---|---|---|")
    for item in query_diagnostics:
        failed = ", ".join(f"`{x}`" for x in item.get("failed_modes", [])) or "-"
        notes = ", ".join(f"`{x}`" for x in item.get("notes", [])) or "-"
        lines.append(
            f"| `{item.get('query_id')}` | "
            f"`{item.get('best_by_recall')}` | "
            f"`{item.get('best_by_mrr')}` | "
            f"`{item.get('best_by_ndcg')}` | "
            f"{failed} | {notes} |"
        )
    lines.append("")

    lines.append("## Query-level diagnostics")
    lines.append("")
    for case in report["cases"]:
        lines.append(f"### `{case['query_id']}` — {case['query']}")
        lines.append(f"- Group: `{case['group']}`")
        lines.append(f"- Intent: {case.get('intent') or ''}")
        lines.append("")
        lines.append("| Mode | Returned | Hit@K | Recall@K | MRR@K | First relevant | Wall ms |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        for run in case["runs"]:
            if run.get("error"):
                lines.append(f"| `{run['mode']}` | error | 0 | 0 | 0 | - | - |")
                continue
            metrics = run["metrics"].get(str(primary_k)) or run["metrics"].get(primary_k) or {}
            lines.append(
                f"| `{run['mode']}` | {run.get('results_count', 0)} | "
                f"{metrics.get('hit', 0):.3f} | {metrics.get('recall', 0):.3f} | "
                f"{metrics.get('mrr', 0):.3f} | "
                f"{metrics.get('first_relevant_rank') or '-'} | "
                f"{run.get('timing_ms_wall')} |"
            )
        lines.append("")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run retrieval evaluation over a curated golden query set.")
    parser.add_argument("--config-path", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--golden-queries-path", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--backend-mode", choices=["file", "db"], default=None)
    parser.add_argument("--top-k", type=int, default=None, help="Override max top-k for search calls.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_yaml(args.config_path)

    if config.get("schema_version") != "retrieval_eval_v1":
        raise ValueError(f"Unsupported schema_version: {config.get('schema_version')!r}")

    defaults = config.get("defaults") or {}
    paths = config.get("paths") or {}

    backend_mode = args.backend_mode or defaults.get("backend_mode") or "file"
    modes = list(defaults.get("modes") or ["lexical", "dense", "hybrid", "hybrid_ranked"])
    top_k_values = [int(k) for k in defaults.get("top_k_values") or [5, 10, 20]]
    top_k_values = sorted(set(k for k in top_k_values if k > 0))
    if not top_k_values:
        raise ValueError("top_k_values must contain at least one positive integer")

    primary_k = int(defaults.get("primary_k") or 10)
    if primary_k not in top_k_values:
        top_k_values.append(primary_k)
        top_k_values = sorted(set(top_k_values))

    search_top_k = int(args.top_k or max(top_k_values))

    golden_path = args.golden_queries_path or Path(paths.get("golden_queries_path", "data/eval/retrieval/golden_queries.jsonl"))
    output_dir = args.output_dir or Path(paths.get("output_dir", DEFAULT_REPORTS_DIR))

    golden_rows = load_jsonl(golden_path)
    enabled_cases = [row for row in golden_rows if row.get("enabled", True)]

    runtime = build_runtime(backend_mode)
    snapshot = runtime.runtime_snapshot()

    run_ts = utc_now_ts()

    case_runs: list[dict[str, Any]] = []

    for case in enabled_cases:
        query = str(case.get("query") or "").strip()
        if not query:
            continue

        case_report = {
            "query_id": str(case.get("query_id") or ""),
            "enabled": bool(case.get("enabled", True)),
            "group": str(case.get("group") or "ungrouped"),
            "query": query,
            "intent": case.get("intent"),
            "expected": case.get("expected") or {},
            "graded_relevance": case.get("graded_relevance") or [],
            "runs": [],
        }

        for mode in modes:
            try:
                search_payload = run_one_search(
                    runtime,
                    query=query,
                    mode_label=mode,
                    top_k=search_top_k,
                )
                raw_results = search_payload.get("results") or []
                compact_results = [compact_result(item) for item in raw_results]

                metrics = {
                    str(k): metrics_at_k(case=case, results=raw_results, k=k)
                    for k in top_k_values
                }

                case_report["runs"].append(
                    {
                        "mode": mode,
                        "effective_mode": search_payload.get("effective_mode"),
                        "rank": search_payload.get("rank"),
                        "results_count": len(raw_results),
                        "timing_ms_wall": search_payload.get("timing_ms_wall"),
                        "metrics": metrics,
                        "top_results": compact_results[: min(10, len(compact_results))],
                        "error": None,
                    }
                )
            except Exception as exc:
                case_report["runs"].append(
                    {
                        "mode": mode,
                        "effective_mode": None,
                        "rank": None,
                        "results_count": 0,
                        "timing_ms_wall": None,
                        "metrics": {},
                        "top_results": [],
                        "error": repr(exc),
                    }
                )

        case_runs.append(case_report)

    mode_summary = {
        mode: summarize_mode(
            case_runs=case_runs,
            mode=mode,
            primary_k=primary_k,
            top_k_values=top_k_values,
        )
        for mode in modes
    }

    comparison_summary = build_mode_comparison_summary(
        case_runs=case_runs,
        mode_summary=mode_summary,
        modes=modes,
        primary_k=primary_k,
    )

    report = {
        "schema_version": "retrieval_eval_v1",
        "report_name": "retrieval_eval",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "config_path": normalize_path(args.config_path),
        "golden_queries_path": normalize_path(golden_path),
        "config": {
            "backend_mode": backend_mode,
            "modes": modes,
            "top_k_values": top_k_values,
            "primary_k": primary_k,
            "search_top_k": search_top_k,
        },
        "runtime": {
            "backend_mode": snapshot.get("backend_mode"),
            "ready": snapshot.get("ready"),
            "build_id": snapshot.get("build_id"),
            "corpus_doc_count": snapshot.get("corpus_doc_count"),
            "embedding_model_name": snapshot.get("embedding_model_name"),
        },
        "summary": {
            "total_cases_count": len(golden_rows),
            "enabled_cases_count": len(enabled_cases),
            "executed_cases_count": len(case_runs),
            "modes_count": len(modes),
        },
        "mode_summary": mode_summary,
        "comparison_summary": comparison_summary,
        "group_summary": summarize_groups(
            case_runs=case_runs,
            modes=modes,
            primary_k=primary_k,
        ),
        "cases": case_runs,
    }

    latest_json = output_dir / "retrieval_eval_latest.json"
    latest_md = output_dir / "retrieval_eval_latest.md"
    hist_json = output_dir / "history" / f"retrieval_eval_{run_ts}.json"
    hist_md = output_dir / "history" / f"retrieval_eval_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(hist_json, report)
    dump_text(hist_md, build_markdown(report))

    print(f"[OK] schema_version={report['schema_version']}")
    print(f"[OK] backend_mode={snapshot.get('backend_mode')}")
    print(f"[OK] build_id={snapshot.get('build_id')}")
    print(f"[OK] corpus_doc_count={snapshot.get('corpus_doc_count')}")
    print(f"[OK] enabled_cases_count={len(enabled_cases)}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {hist_json}")
    print(f"[OK] history Markdown: {hist_md}")


if __name__ == "__main__":
    main()
