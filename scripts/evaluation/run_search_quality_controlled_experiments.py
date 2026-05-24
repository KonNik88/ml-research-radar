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
        "PyYAML is required for controlled search quality experiments config loading."
    ) from exc

from radar_core.contracts.canonical_document import CanonicalDocument
from radar_core.ranking.scoring import rank_results
from scripts.evaluation.run_retrieval_eval import (
    compact_result,
    load_jsonl,
    metrics_at_k,
)
from services.api.runtime import get_runtime
from services.api.search_service import (
    _dense_search_with_model,
    _hybrid_search_with_model,
    _lexical_results_to_dicts,
    _load_search_scoring_params,
)
from services.api.settings import get_settings


DEFAULT_CONFIG_PATH = Path("configs/search_quality_controlled_experiments_v1.yaml")
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/evaluation")


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
        if not math.isfinite(value):
            return default
        return value
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


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


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Controlled experiments config not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Config must be a YAML mapping: {path}")
    return payload


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

    if snapshot.get("backend_mode") != "file":
        raise RuntimeError(
            "Controlled search quality experiments currently support file backend only."
        )

    return runtime


def doc_to_plain(doc: CanonicalDocument) -> dict[str, Any]:
    return {
        "canonical_id": doc.canonical_id,
        "title": doc.title,
        "abstract": doc.abstract,
        "authors": list(doc.authors or []),
        "year": doc.year,
        "doi": doc.doi,
        "primary_category": doc.primary_category,
        "categories": list(doc.categories or []),
        "tags": list(doc.tags or []),
        "concepts": list(getattr(doc, "concepts", []) or []),
        "keywords": list(getattr(doc, "keywords", []) or []),
        "venue": getattr(doc, "venue", None),
        "journal": getattr(doc, "journal", None),
        "conference": getattr(doc, "conference", None),
        "publisher": getattr(doc, "publisher", None),
        "publication_type": getattr(doc, "publication_type", None),
        "source_count": int(doc.source_count or 0),
        "unique_source_count": int(getattr(doc, "unique_source_count", 0) or 0),
    }


def candidate_to_eval_result(candidate: dict[str, Any], *, ranking: dict[str, Any] | None = None) -> dict[str, Any]:
    doc: CanonicalDocument = candidate["document"]

    retrieval: dict[str, Any] = {}
    for key in ("score", "hybrid_score", "lexical_score", "dense_score"):
        if key in candidate:
            retrieval[key] = float(candidate.get(key) or 0.0)

    payload = {
        "canonical_id": candidate.get("canonical_id") or doc.canonical_id,
        "title": candidate.get("title") or doc.title,
        "year": candidate.get("year") if candidate.get("year") is not None else doc.year,
        "doi": candidate.get("doi") if candidate.get("doi") is not None else doc.doi,
        "source_count": int(candidate.get("source_count") or doc.source_count or 0),
        "abstract": doc.abstract,
        "primary_category": doc.primary_category,
        "categories": list(doc.categories or []),
        "tags": list(doc.tags or []),
        "concepts": list(getattr(doc, "concepts", []) or []),
        "keywords": list(getattr(doc, "keywords", []) or []),
        "document": doc_to_plain(doc),
        "retrieval": retrieval,
    }

    if ranking is not None:
        payload["ranking"] = ranking

    return payload


def ranked_to_eval_result(ranked_result: Any) -> dict[str, Any]:
    raw = dict(ranked_result.raw)
    ranking = {
        "final_score": float(ranked_result.final_score),
        "retrieval_score": float(ranked_result.retrieval_score),
        "recency_score": float(ranked_result.recency_score),
        "source_support_score": float(ranked_result.source_support_score),
        "metadata_quality_score": float(ranked_result.metadata_quality_score),
    }
    return candidate_to_eval_result(raw, ranking=ranking)


def compute_quality_composite(metrics: dict[str, Any], weights: dict[str, float]) -> float:
    total_weight = sum(max(0.0, safe_float(v)) for v in weights.values())
    if total_weight <= 0:
        weights = {"recall": 0.40, "ndcg": 0.40, "mrr": 0.20}
        total_weight = 1.0

    value = 0.0
    for metric_name, weight in weights.items():
        value += (max(0.0, safe_float(weight)) / total_weight) * safe_float(metrics.get(metric_name), 0.0)

    return round(value, 6)


def make_variant_id(
    *,
    variant_type: str,
    name: str,
    candidate_k: int | None = None,
    rank: bool | None = None,
) -> str:
    parts = [variant_type, name]
    if candidate_k is not None:
        parts.append(f"k{candidate_k}")
    if rank is not None:
        parts.append("ranked" if rank else "unranked")
    return "__".join(parts)


def build_variants(config: dict[str, Any], search_top_k: int) -> list[dict[str, Any]]:
    experiments = config.get("experiments") or {}
    variants: list[dict[str, Any]] = []

    if bool(experiments.get("include_baselines", True)):
        baseline_candidate_k = max(search_top_k * 5, 50)
        variants.extend(
            [
                {
                    "variant_id": make_variant_id(
                        variant_type="baseline",
                        name="lexical",
                        candidate_k=baseline_candidate_k,
                        rank=False,
                    ),
                    "variant_type": "baseline",
                    "mode": "lexical",
                    "candidate_k": baseline_candidate_k,
                    "rank": False,
                    "lexical_weight": None,
                    "dense_weight": None,
                },
                {
                    "variant_id": make_variant_id(
                        variant_type="baseline",
                        name="dense",
                        candidate_k=baseline_candidate_k,
                        rank=False,
                    ),
                    "variant_type": "baseline",
                    "mode": "dense",
                    "candidate_k": baseline_candidate_k,
                    "rank": False,
                    "lexical_weight": None,
                    "dense_weight": None,
                },
            ]
        )

    candidate_k_values = [int(x) for x in experiments.get("candidate_k_values") or [max(search_top_k * 5, 50)]]
    rank_modes = [bool(x) for x in experiments.get("rank_modes") or [False, True]]
    weights = experiments.get("hybrid_weights") or []

    for weight_item in weights:
        name = str(weight_item.get("name") or "hybrid_weight")
        lexical_weight = safe_float(weight_item.get("lexical_weight"), 0.55)
        dense_weight = safe_float(weight_item.get("dense_weight"), 0.45)

        for candidate_k in candidate_k_values:
            for rank in rank_modes:
                variants.append(
                    {
                        "variant_id": make_variant_id(
                            variant_type="hybrid",
                            name=name,
                            candidate_k=int(candidate_k),
                            rank=rank,
                        ),
                        "variant_type": "hybrid",
                        "mode": "hybrid",
                        "candidate_k": int(candidate_k),
                        "rank": bool(rank),
                        "lexical_weight": lexical_weight,
                        "dense_weight": dense_weight,
                    }
                )

    return variants


def run_variant(
    *,
    runtime: Any,
    query: str,
    variant: dict[str, Any],
    search_top_k: int,
    scoring_params: dict[str, float],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    documents = runtime.documents
    lexical_artifacts = runtime.lexical_artifacts
    dense_artifacts = runtime.dense_artifacts
    embedding_model = runtime.embedding_model

    if lexical_artifacts is None or dense_artifacts is None or embedding_model is None:
        raise RuntimeError("File runtime retrieval artifacts are not initialized")

    candidate_k = int(variant["candidate_k"])
    mode = variant["mode"]

    t0 = time.perf_counter()
    retrieval_timings: dict[str, float] = {}

    if mode == "lexical":
        t_retrieve = time.perf_counter()
        lexical_results = lexical_artifacts.index.search(query=query, top_k=candidate_k)
        raw_candidates = _lexical_results_to_dicts(lexical_results)
        retrieval_timings["retrieve_ms"] = round((time.perf_counter() - t_retrieve) * 1000.0, 3)
        eval_results = [
            candidate_to_eval_result(candidate)
            for candidate in raw_candidates[:search_top_k]
        ]

    elif mode == "dense":
        t_retrieve = time.perf_counter()
        raw_candidates = _dense_search_with_model(
            query=query,
            documents=documents,
            embeddings=dense_artifacts.embeddings,
            ids=dense_artifacts.ids,
            embedding_model=embedding_model,
            top_k=candidate_k,
        )
        retrieval_timings["retrieve_ms"] = round((time.perf_counter() - t_retrieve) * 1000.0, 3)
        eval_results = [
            candidate_to_eval_result(candidate)
            for candidate in raw_candidates[:search_top_k]
        ]

    elif mode == "hybrid":
        raw_candidates, hybrid_timings = _hybrid_search_with_model(
            query=query,
            documents=documents,
            lexical_index=lexical_artifacts.index,
            dense_embeddings=dense_artifacts.embeddings,
            dense_ids=dense_artifacts.ids,
            embedding_model=embedding_model,
            top_k=candidate_k,
            lexical_weight=safe_float(variant.get("lexical_weight"), 0.55),
            dense_weight=safe_float(variant.get("dense_weight"), 0.45),
        )
        retrieval_timings.update(hybrid_timings)
        retrieval_timings["retrieve_ms"] = round(
            safe_float(hybrid_timings.get("lexical_ms"))
            + safe_float(hybrid_timings.get("dense_ms"))
            + safe_float(hybrid_timings.get("hybrid_merge_ms")),
            3,
        )

        if bool(variant.get("rank")):
            t_rank = time.perf_counter()
            ranked_results = rank_results(
                raw_candidates,
                retrieval_score_field="hybrid_score",
                retrieval_weight=scoring_params["ranking_retrieval_weight"],
                recency_weight=scoring_params["ranking_recency_weight"],
                source_support_weight=scoring_params["ranking_source_support_weight"],
                metadata_quality_weight=scoring_params["ranking_metadata_quality_weight"],
            )
            retrieval_timings["rank_ms"] = round((time.perf_counter() - t_rank) * 1000.0, 3)
            eval_results = [
                ranked_to_eval_result(item)
                for item in ranked_results[:search_top_k]
            ]
        else:
            eval_results = [
                candidate_to_eval_result(candidate)
                for candidate in raw_candidates[:search_top_k]
            ]

    else:
        raise ValueError(f"Unsupported experiment mode: {mode}")

    wall_ms = round((time.perf_counter() - t0) * 1000.0, 3)
    retrieval_timings["wall_ms"] = wall_ms

    return eval_results, retrieval_timings


def summarize_variants(
    *,
    runs: list[dict[str, Any]],
    variants: list[dict[str, Any]],
    primary_k: int,
    top_k_values: list[int],
    quality_weights: dict[str, float],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for variant in variants:
        variant_id = variant["variant_id"]
        variant_runs = [
            run for run in runs
            if run.get("variant_id") == variant_id and not run.get("error")
        ]

        primary_metrics = [
            run.get("metrics", {}).get(str(primary_k)) or {}
            for run in variant_runs
        ]
        latencies = [safe_float(run.get("timing_ms_wall")) for run in variant_runs]

        summary: dict[str, Any] = {
            **variant,
            "runs_count": len(variant_runs),
            "error_count": len([run for run in runs if run.get("variant_id") == variant_id and run.get("error")]),
            "latency_ms": {
                "p50": percentile(latencies, 0.50),
                "p95": percentile(latencies, 0.95),
                "mean": round(float(statistics.mean(latencies)), 3) if latencies else None,
            },
        }

        for k in top_k_values:
            metrics_k = [
                run.get("metrics", {}).get(str(k)) or {}
                for run in variant_runs
            ]
            summary[f"hit_at_{k}"] = mean([safe_float(m.get("hit")) for m in metrics_k])
            summary[f"recall_at_{k}"] = mean([safe_float(m.get("recall")) for m in metrics_k])
            summary[f"mrr_at_{k}"] = mean([safe_float(m.get("mrr")) for m in metrics_k])
            summary[f"ndcg_at_{k}"] = mean([safe_float(m.get("ndcg")) for m in metrics_k])

        composite_input = {
            "recall": summary.get(f"recall_at_{primary_k}", 0.0),
            "ndcg": summary.get(f"ndcg_at_{primary_k}", 0.0),
            "mrr": summary.get(f"mrr_at_{primary_k}", 0.0),
        }
        summary["quality_composite"] = compute_quality_composite(composite_input, quality_weights)

        p50 = summary["latency_ms"]["p50"]
        summary["quality_per_second_p50"] = (
            round(summary["quality_composite"] / (safe_float(p50) / 1000.0), 6)
            if p50 and safe_float(p50) > 0
            else None
        )

        rows.append(summary)

    rows.sort(
        key=lambda x: (
            safe_float(x.get("quality_composite")),
            safe_float(x.get(f"recall_at_{primary_k}")),
            safe_float(x.get(f"ndcg_at_{primary_k}")),
        ),
        reverse=True,
    )
    return rows


def rank_variants(variant_summary: list[dict[str, Any]], primary_k: int) -> dict[str, list[dict[str, Any]]]:
    rankings: dict[str, list[dict[str, Any]]] = {}

    metric_keys = [
        f"hit_at_{primary_k}",
        f"recall_at_{primary_k}",
        f"mrr_at_{primary_k}",
        f"ndcg_at_{primary_k}",
        "quality_composite",
        "quality_per_second_p50",
    ]

    for metric_key in metric_keys:
        rows = [
            {
                "variant_id": item["variant_id"],
                "variant_type": item["variant_type"],
                "mode": item["mode"],
                "rank": item.get("rank"),
                "candidate_k": item.get("candidate_k"),
                "lexical_weight": item.get("lexical_weight"),
                "dense_weight": item.get("dense_weight"),
                "value": item.get(metric_key),
            }
            for item in variant_summary
            if item.get(metric_key) is not None
        ]
        rows.sort(key=lambda x: safe_float(x["value"]), reverse=True)
        rankings[metric_key] = rows

    latency_rows = [
        {
            "variant_id": item["variant_id"],
            "variant_type": item["variant_type"],
            "mode": item["mode"],
            "rank": item.get("rank"),
            "candidate_k": item.get("candidate_k"),
            "value": (item.get("latency_ms") or {}).get("p50"),
        }
        for item in variant_summary
        if (item.get("latency_ms") or {}).get("p50") is not None
    ]
    latency_rows.sort(key=lambda x: safe_float(x["value"]))
    rankings["latency_p50_ms"] = latency_rows

    return rankings


def build_pareto_frontier(variant_summary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    frontier: list[dict[str, Any]] = []

    for item in variant_summary:
        quality = safe_float(item.get("quality_composite"))
        latency = (item.get("latency_ms") or {}).get("p50")
        if latency is None:
            continue
        latency_f = safe_float(latency)

        dominated = False
        for other in variant_summary:
            if other["variant_id"] == item["variant_id"]:
                continue
            other_latency = (other.get("latency_ms") or {}).get("p50")
            if other_latency is None:
                continue
            other_quality = safe_float(other.get("quality_composite"))
            other_latency_f = safe_float(other_latency)

            if (
                other_quality >= quality
                and other_latency_f <= latency_f
                and (other_quality > quality or other_latency_f < latency_f)
            ):
                dominated = True
                break

        if not dominated:
            frontier.append(
                {
                    "variant_id": item["variant_id"],
                    "variant_type": item["variant_type"],
                    "mode": item["mode"],
                    "rank": item.get("rank"),
                    "candidate_k": item.get("candidate_k"),
                    "lexical_weight": item.get("lexical_weight"),
                    "dense_weight": item.get("dense_weight"),
                    "quality_composite": quality,
                    "latency_p50_ms": latency_f,
                    "quality_per_second_p50": item.get("quality_per_second_p50"),
                }
            )

    frontier.sort(key=lambda x: (-safe_float(x["quality_composite"]), safe_float(x["latency_p50_ms"])))
    return frontier


def build_rank_effects(
    *,
    variant_summary: list[dict[str, Any]],
    primary_k: int,
) -> list[dict[str, Any]]:
    by_key: dict[tuple[int, float, float], dict[bool, dict[str, Any]]] = {}

    for item in variant_summary:
        if item.get("variant_type") != "hybrid":
            continue
        key = (
            int(item.get("candidate_k") or 0),
            safe_float(item.get("lexical_weight")),
            safe_float(item.get("dense_weight")),
        )
        by_key.setdefault(key, {})[bool(item.get("rank"))] = item

    effects: list[dict[str, Any]] = []
    for (candidate_k, lexical_weight, dense_weight), pair in sorted(by_key.items()):
        if False not in pair or True not in pair:
            continue

        unranked = pair[False]
        ranked = pair[True]
        effects.append(
            {
                "candidate_k": candidate_k,
                "lexical_weight": lexical_weight,
                "dense_weight": dense_weight,
                f"recall_at_{primary_k}_delta": round(
                    safe_float(ranked.get(f"recall_at_{primary_k}"))
                    - safe_float(unranked.get(f"recall_at_{primary_k}")),
                    6,
                ),
                f"ndcg_at_{primary_k}_delta": round(
                    safe_float(ranked.get(f"ndcg_at_{primary_k}"))
                    - safe_float(unranked.get(f"ndcg_at_{primary_k}")),
                    6,
                ),
                "quality_composite_delta": round(
                    safe_float(ranked.get("quality_composite"))
                    - safe_float(unranked.get("quality_composite")),
                    6,
                ),
                "latency_p50_ms_delta": round(
                    safe_float((ranked.get("latency_ms") or {}).get("p50"))
                    - safe_float((unranked.get("latency_ms") or {}).get("p50")),
                    3,
                ),
                "ranked_variant_id": ranked["variant_id"],
                "unranked_variant_id": unranked["variant_id"],
            }
        )

    return effects


def build_weight_effects(
    *,
    variant_summary: list[dict[str, Any]],
    primary_k: int,
) -> list[dict[str, Any]]:
    rows = [
        item for item in variant_summary
        if item.get("variant_type") == "hybrid"
    ]
    rows.sort(
        key=lambda x: (
            int(x.get("candidate_k") or 0),
            bool(x.get("rank")),
            safe_float(x.get("dense_weight")),
        )
    )

    out: list[dict[str, Any]] = []
    for item in rows:
        out.append(
            {
                "variant_id": item["variant_id"],
                "candidate_k": item.get("candidate_k"),
                "rank": item.get("rank"),
                "lexical_weight": item.get("lexical_weight"),
                "dense_weight": item.get("dense_weight"),
                f"recall_at_{primary_k}": item.get(f"recall_at_{primary_k}"),
                f"ndcg_at_{primary_k}": item.get(f"ndcg_at_{primary_k}"),
                "quality_composite": item.get("quality_composite"),
                "latency_p50_ms": (item.get("latency_ms") or {}).get("p50"),
            }
        )

    return out


def build_query_winners(
    *,
    runs: list[dict[str, Any]],
    primary_k: int,
    quality_weights: dict[str, float],
) -> list[dict[str, Any]]:
    by_query: dict[str, list[dict[str, Any]]] = {}

    for run in runs:
        if run.get("error"):
            continue
        by_query.setdefault(str(run.get("query_id")), []).append(run)

    out: list[dict[str, Any]] = []
    for query_id, query_runs in sorted(by_query.items()):
        rows = []
        for run in query_runs:
            m = run.get("metrics", {}).get(str(primary_k)) or {}
            composite = compute_quality_composite(
                {
                    "recall": m.get("recall"),
                    "ndcg": m.get("ndcg"),
                    "mrr": m.get("mrr"),
                },
                quality_weights,
            )
            rows.append(
                {
                    "variant_id": run.get("variant_id"),
                    "query": run.get("query"),
                    "variant_type": run.get("variant_type"),
                    "mode": run.get("mode"),
                    "rank": run.get("rank"),
                    "candidate_k": run.get("candidate_k"),
                    "lexical_weight": run.get("lexical_weight"),
                    "dense_weight": run.get("dense_weight"),
                    "quality_composite": composite,
                    "recall": safe_float(m.get("recall")),
                    "ndcg": safe_float(m.get("ndcg")),
                    "mrr": safe_float(m.get("mrr")),
                    "hit": safe_float(m.get("hit")),
                    "timing_ms_wall": run.get("timing_ms_wall"),
                }
            )

        rows.sort(key=lambda x: (x["quality_composite"], x["recall"], x["ndcg"], x["mrr"]), reverse=True)
        if rows:
            out.append(
                {
                    "query_id": query_id,
                    "query": rows[0].get("query"),
                    "best_variant_id": rows[0]["variant_id"],
                    "best_quality_composite": rows[0]["quality_composite"],
                    "best_recall": rows[0]["recall"],
                    "best_ndcg": rows[0]["ndcg"],
                    "top_variants": rows[:5],
                }
            )

    return out


def build_recommendations(
    *,
    rankings: dict[str, list[dict[str, Any]]],
    pareto_frontier: list[dict[str, Any]],
    rank_effects: list[dict[str, Any]],
    primary_k: int,
) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []

    def top_variant(metric: str) -> dict[str, Any] | None:
        rows = rankings.get(metric) or []
        return rows[0] if rows else None

    best_quality = top_variant("quality_composite")
    best_recall = top_variant(f"recall_at_{primary_k}")
    best_ndcg = top_variant(f"ndcg_at_{primary_k}")
    fastest = top_variant("latency_p50_ms")
    best_tradeoff = top_variant("quality_per_second_p50")

    if best_quality:
        recommendations.append(
            {
                "type": "best_quality_composite",
                "priority": "high",
                "message": (
                    f"`{best_quality['variant_id']}` is the strongest controlled variant by quality composite. "
                    "Use it as the first candidate for deeper manual inspection."
                ),
            }
        )

    if best_recall:
        recommendations.append(
            {
                "type": "best_recall",
                "priority": "high",
                "message": (
                    f"`{best_recall['variant_id']}` is the strongest controlled variant by Recall@{primary_k}."
                ),
            }
        )

    if best_ndcg and best_quality and best_ndcg["variant_id"] != best_quality["variant_id"]:
        recommendations.append(
            {
                "type": "ranking_quality",
                "priority": "medium",
                "message": (
                    f"`{best_ndcg['variant_id']}` is best by nDCG@{primary_k}; "
                    "inspect whether rank quality and composite quality diverge."
                ),
            }
        )

    if fastest:
        recommendations.append(
            {
                "type": "latency_baseline",
                "priority": "medium",
                "message": (
                    f"`{fastest['variant_id']}` is fastest by p50 latency. "
                    "If this is a dense baseline, it remains the practical serving-speed reference."
                ),
            }
        )

    if best_tradeoff:
        recommendations.append(
            {
                "type": "quality_latency_tradeoff",
                "priority": "high",
                "message": (
                    f"`{best_tradeoff['variant_id']}` has the best quality-per-second tradeoff."
                ),
            }
        )

    positive_rank_effects = [
        item for item in rank_effects
        if safe_float(item.get(f"recall_at_{primary_k}_delta")) > 0
        or safe_float(item.get("quality_composite_delta")) > 0
    ]
    negative_ndcg_rank_effects = [
        item for item in rank_effects
        if safe_float(item.get(f"ndcg_at_{primary_k}_delta")) < 0
    ]

    if positive_rank_effects:
        recommendations.append(
            {
                "type": "rank_effect",
                "priority": "medium",
                "message": (
                    f"Ranking improved recall or composite quality in {len(positive_rank_effects)} hybrid settings. "
                    "Keep ranked hybrid in the next experiment round."
                ),
            }
        )

    if negative_ndcg_rank_effects:
        recommendations.append(
            {
                "type": "rank_effect",
                "priority": "medium",
                "message": (
                    f"Ranking lowered nDCG in {len(negative_ndcg_rank_effects)} hybrid settings. "
                    "Do not make ranked hybrid default without inspecting affected queries."
                ),
            }
        )

    if pareto_frontier:
        recommendations.append(
            {
                "type": "pareto_frontier",
                "priority": "medium",
                "message": (
                    "Controlled Pareto frontier variants: "
                    + ", ".join(f"`{item['variant_id']}`" for item in pareto_frontier)
                    + ". Carry these variants forward."
                ),
            }
        )

    return recommendations


def build_markdown(report: dict[str, Any]) -> str:
    primary_k = report["config"]["primary_k"]

    lines: list[str] = []
    lines.append("# Search quality controlled experiments v1")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at_utc']}`")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Backend mode: `{report['runtime'].get('backend_mode')}`")
    lines.append(f"- Build id: `{report['runtime'].get('build_id')}`")
    lines.append(f"- Corpus doc count: `{report['runtime'].get('corpus_doc_count')}`")
    lines.append(f"- Enabled cases: **{report['summary']['enabled_cases_count']}**")
    lines.append(f"- Variants: **{report['summary']['variants_count']}**")
    lines.append(f"- Primary k: **{primary_k}**")
    lines.append("")

    lines.append("## Variant summary")
    lines.append("")
    lines.append("| Variant | Type | Rank | k | Lex | Dense | Recall@K | MRR@K | nDCG@K | Composite | p50 ms | Quality/sec |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in report["variant_summary"]:
        lat = row.get("latency_ms") or {}
        lines.append(
            f"| `{row['variant_id']}` | `{row['variant_type']}` | "
            f"{row.get('rank')} | {row.get('candidate_k')} | "
            f"{row.get('lexical_weight')} | {row.get('dense_weight')} | "
            f"{row.get(f'recall_at_{primary_k}', 0):.3f} | "
            f"{row.get(f'mrr_at_{primary_k}', 0):.3f} | "
            f"{row.get(f'ndcg_at_{primary_k}', 0):.3f} | "
            f"{row.get('quality_composite', 0):.3f} | "
            f"{lat.get('p50')} | "
            f"{row.get('quality_per_second_p50')} |"
        )
    lines.append("")

    lines.append("## Rankings")
    lines.append("")
    for ranking_name, rows in report["rankings"].items():
        lines.append(f"### `{ranking_name}`")
        for idx, row in enumerate(rows[:10], start=1):
            lines.append(f"{idx}. `{row['variant_id']}` — {row['value']}")
        lines.append("")

    lines.append("## Pareto frontier")
    lines.append("")
    if report["pareto_frontier"]:
        lines.append("| Variant | Composite | p50 ms | Quality/sec |")
        lines.append("|---|---:|---:|---:|")
        for item in report["pareto_frontier"]:
            lines.append(
                f"| `{item['variant_id']}` | "
                f"{item['quality_composite']:.3f} | "
                f"{item['latency_p50_ms']:.3f} | "
                f"{item.get('quality_per_second_p50')} |"
            )
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Rank effects")
    lines.append("")
    if report["rank_effects"]:
        lines.append("| k | Lex | Dense | ΔRecall@K | ΔnDCG@K | ΔComposite | Δp50 ms |")
        lines.append("|---:|---:|---:|---:|---:|---:|---:|")
        for item in report["rank_effects"]:
            lines.append(
                f"| {item['candidate_k']} | {item['lexical_weight']:.2f} | {item['dense_weight']:.2f} | "
                f"{item.get(f'recall_at_{primary_k}_delta', 0):+.3f} | "
                f"{item.get(f'ndcg_at_{primary_k}_delta', 0):+.3f} | "
                f"{item.get('quality_composite_delta', 0):+.3f} | "
                f"{item.get('latency_p50_ms_delta', 0):+.3f} |"
            )
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Weight effects")
    lines.append("")
    if report["weight_effects"]:
        lines.append("| Variant | Rank | k | Lex | Dense | Recall@K | nDCG@K | Composite | p50 ms |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for item in report["weight_effects"]:
            lines.append(
                f"| `{item['variant_id']}` | {item.get('rank')} | {item.get('candidate_k')} | "
                f"{item.get('lexical_weight')} | {item.get('dense_weight')} | "
                f"{item.get(f'recall_at_{primary_k}', 0):.3f} | "
                f"{item.get(f'ndcg_at_{primary_k}', 0):.3f} | "
                f"{item.get('quality_composite', 0):.3f} | "
                f"{item.get('latency_p50_ms')} |"
            )
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Query winners")
    lines.append("")
    if report["query_winners"]:
        lines.append("| Query | Best variant | Composite | Recall | nDCG |")
        lines.append("|---|---|---:|---:|---:|")
        for item in report["query_winners"]:
            lines.append(
                f"| `{item['query_id']}` | `{item['best_variant_id']}` | "
                f"{item.get('best_quality_composite', 0):.3f} | "
                f"{item.get('best_recall', 0):.3f} | "
                f"{item.get('best_ndcg', 0):.3f} |"
            )
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Recommendations")
    lines.append("")
    if report["recommendations"]:
        for item in report["recommendations"]:
            lines.append(f"- **{item['priority']} / {item['type']}**: {item['message']}")
    else:
        lines.append("- none")
    lines.append("")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run controlled search quality experiments over retrieval weights/rank settings. "
            "This script is evaluation-only and does not modify API defaults."
        )
    )
    parser.add_argument("--config-path", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--golden-queries-path", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--backend-mode", choices=["file"], default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_ts = utc_now_ts()

    config = load_yaml(args.config_path)
    if config.get("schema_version") != "search_quality_controlled_experiments_v1":
        raise ValueError(f"Unsupported schema_version: {config.get('schema_version')!r}")

    defaults = config.get("defaults") or {}
    paths = config.get("paths") or {}
    analysis = config.get("analysis") or {}

    backend_mode = args.backend_mode or defaults.get("backend_mode") or "file"
    primary_k = int(defaults.get("primary_k") or 10)
    top_k_values = [int(k) for k in defaults.get("top_k_values") or [5, 10, 20]]
    if primary_k not in top_k_values:
        top_k_values.append(primary_k)
    top_k_values = sorted(set(k for k in top_k_values if k > 0))
    search_top_k = int(defaults.get("search_top_k") or max(top_k_values))

    quality_weights = analysis.get("quality_composite_weights") or {
        "recall": 0.40,
        "ndcg": 0.40,
        "mrr": 0.20,
    }

    golden_path = args.golden_queries_path or Path(paths.get("golden_queries_path", "data/eval/retrieval/golden_queries.jsonl"))
    output_dir = args.output_dir or Path(paths.get("output_dir", DEFAULT_OUTPUT_DIR))

    golden_rows = load_jsonl(golden_path)
    enabled_cases = [row for row in golden_rows if row.get("enabled", True)]

    runtime = build_runtime(backend_mode)
    snapshot = runtime.runtime_snapshot()
    scoring_params = _load_search_scoring_params()

    variants = build_variants(config, search_top_k=search_top_k)
    runs: list[dict[str, Any]] = []

    for case in enabled_cases:
        query = str(case.get("query") or "").strip()
        if not query:
            continue

        for variant in variants:
            try:
                eval_results, timings = run_variant(
                    runtime=runtime,
                    query=query,
                    variant=variant,
                    search_top_k=search_top_k,
                    scoring_params=scoring_params,
                )
                metrics = {
                    str(k): metrics_at_k(case=case, results=eval_results, k=k)
                    for k in top_k_values
                }

                runs.append(
                    {
                        "query_id": str(case.get("query_id") or ""),
                        "query": query,
                        "group": str(case.get("group") or "ungrouped"),
                        "variant_id": variant["variant_id"],
                        "variant_type": variant["variant_type"],
                        "mode": variant["mode"],
                        "rank": variant.get("rank"),
                        "candidate_k": variant.get("candidate_k"),
                        "lexical_weight": variant.get("lexical_weight"),
                        "dense_weight": variant.get("dense_weight"),
                        "results_count": len(eval_results),
                        "timing_ms_wall": timings.get("wall_ms"),
                        "timings": timings,
                        "metrics": metrics,
                        "top_results": [
                            compact_result(item)
                            for item in eval_results[: min(10, len(eval_results))]
                        ],
                        "error": None,
                    }
                )

            except Exception as exc:
                runs.append(
                    {
                        "query_id": str(case.get("query_id") or ""),
                        "query": query,
                        "group": str(case.get("group") or "ungrouped"),
                        "variant_id": variant["variant_id"],
                        "variant_type": variant["variant_type"],
                        "mode": variant["mode"],
                        "rank": variant.get("rank"),
                        "candidate_k": variant.get("candidate_k"),
                        "lexical_weight": variant.get("lexical_weight"),
                        "dense_weight": variant.get("dense_weight"),
                        "results_count": 0,
                        "timing_ms_wall": None,
                        "timings": {},
                        "metrics": {},
                        "top_results": [],
                        "error": repr(exc),
                    }
                )

    variant_summary = summarize_variants(
        runs=runs,
        variants=variants,
        primary_k=primary_k,
        top_k_values=top_k_values,
        quality_weights=quality_weights,
    )
    rankings = rank_variants(variant_summary, primary_k)
    pareto_frontier = build_pareto_frontier(variant_summary)
    rank_effects = build_rank_effects(
        variant_summary=variant_summary,
        primary_k=primary_k,
    )
    weight_effects = build_weight_effects(
        variant_summary=variant_summary,
        primary_k=primary_k,
    )
    query_winners = build_query_winners(
        runs=runs,
        primary_k=primary_k,
        quality_weights=quality_weights,
    )
    recommendations = build_recommendations(
        rankings=rankings,
        pareto_frontier=pareto_frontier,
        rank_effects=rank_effects,
        primary_k=primary_k,
    )

    report = {
        "schema_version": "search_quality_controlled_experiments_v1",
        "report_name": "search_quality_controlled_experiments",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "inputs": {
            "config_path": normalize_path(args.config_path),
            "golden_queries_path": normalize_path(golden_path),
        },
        "config": {
            "backend_mode": backend_mode,
            "primary_k": primary_k,
            "top_k_values": top_k_values,
            "search_top_k": search_top_k,
            "quality_composite_weights": quality_weights,
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
            "variants_count": len(variants),
            "runs_count": len(runs),
            "error_count": len([run for run in runs if run.get("error")]),
            "hybrid_variants_count": len([variant for variant in variants if variant.get("variant_type") == "hybrid"]),
        },
        "variants": variants,
        "variant_summary": variant_summary,
        "rankings": rankings,
        "pareto_frontier": pareto_frontier,
        "rank_effects": rank_effects,
        "weight_effects": weight_effects,
        "query_winners": query_winners,
        "recommendations": recommendations,
    }

    latest_json = output_dir / "search_quality_controlled_experiments_latest.json"
    latest_md = output_dir / "search_quality_controlled_experiments_latest.md"
    hist_json = output_dir / "history" / f"search_quality_controlled_experiments_{run_ts}.json"
    hist_md = output_dir / "history" / f"search_quality_controlled_experiments_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(hist_json, report)
    dump_text(hist_md, build_markdown(report))

    print(f"[OK] schema_version={report['schema_version']}")
    print(f"[OK] backend_mode={snapshot.get('backend_mode')}")
    print(f"[OK] build_id={snapshot.get('build_id')}")
    print(f"[OK] corpus_doc_count={snapshot.get('corpus_doc_count')}")
    print(f"[OK] enabled_cases_count={len(enabled_cases)}")
    print(f"[OK] variants_count={len(variants)}")
    print(f"[OK] runs_count={len(runs)}")
    print(f"[OK] error_count={report['summary']['error_count']}")
    print(f"[OK] pareto_frontier_count={len(pareto_frontier)}")
    print(f"[OK] recommendations_count={len(recommendations)}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {hist_json}")
    print(f"[OK] history Markdown: {hist_md}")


if __name__ == "__main__":
    main()
