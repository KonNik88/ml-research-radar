from __future__ import annotations

import argparse
import math
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from radar_core.ranking.scoring import minmax_normalize, rank_results
from scripts.evaluation.run_retrieval_eval import (
    graded_relevance_map,
    load_jsonl,
    metrics_at_k,
)
from scripts.evaluation.run_search_quality_controlled_experiments import (
    build_hybrid_candidates_from_cache,
    build_runtime,
    candidate_to_eval_result,
    compute_quality_composite,
    dump_json,
    dump_text,
    load_yaml,
    normalize_path,
    prepare_query_cache,
    ranked_to_eval_result,
    safe_float,
    utc_now_iso,
    utc_now_ts,
)


DEFAULT_CONFIG_PATH = Path("configs/ranking_evaluation_v1.yaml")
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/evaluation")


def mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(float(statistics.fmean(values)), 6)


def canonical_ids(results: list[dict[str, Any]]) -> list[str]:
    return [str(item.get("canonical_id") or "") for item in results]


def validate_profile(profile: dict[str, Any], tolerance: float) -> None:
    name = str(profile.get("name") or "").strip()
    if not name:
        raise ValueError("Every ranking profile must have a non-empty name")

    apply_ranking = bool(profile.get("apply_ranking"))
    weights = profile.get("weights")

    if not apply_ranking:
        if weights not in (None, {}):
            raise ValueError(f"Unranked profile {name!r} must not define weights")
        return

    if not isinstance(weights, dict):
        raise ValueError(f"Ranked profile {name!r} must define weights")

    required = {
        "retrieval",
        "recency",
        "source_support",
        "metadata_quality",
    }
    missing = required.difference(weights)
    if missing:
        raise ValueError(
            f"Ranked profile {name!r} is missing weights: {sorted(missing)}"
        )

    values = [safe_float(weights[key]) for key in sorted(required)]
    if any(value < 0.0 for value in values):
        raise ValueError(f"Ranked profile {name!r} contains negative weights")

    if abs(sum(values) - 1.0) > max(tolerance, 1e-6):
        raise ValueError(
            f"Ranked profile {name!r} weights must sum to 1.0; "
            f"actual={sum(values):.9f}"
        )


def profile_weights(profile: dict[str, Any]) -> dict[str, float]:
    weights = profile.get("weights") or {}
    return {
        "retrieval": safe_float(weights.get("retrieval")),
        "recency": safe_float(weights.get("recency")),
        "source_support": safe_float(weights.get("source_support")),
        "metadata_quality": safe_float(weights.get("metadata_quality")),
    }


def metric_delta_map(
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
) -> dict[str, dict[str, float]]:
    output: dict[str, dict[str, float]] = {}
    metric_names = ("hit", "precision", "recall", "mrr", "ndcg")

    for k in sorted(set(before) | set(after), key=int):
        before_row = before.get(k) or {}
        after_row = after.get(k) or {}
        output[k] = {
            metric: round(
                safe_float(after_row.get(metric))
                - safe_float(before_row.get(metric)),
                6,
            )
            for metric in metric_names
        }

    return output


def _relevant_top_k(
    ids: list[str],
    grades_by_id: dict[str, float],
    k: int,
) -> set[str]:
    return {
        canonical_id
        for canonical_id in ids[:k]
        if safe_float(grades_by_id.get(canonical_id)) > 0.0
    }


def classify_ranking_effect(
    *,
    before_ids: list[str],
    after_ids: list[str],
    grades_by_id: dict[str, float],
    metrics_before: dict[str, dict[str, Any]],
    metrics_after: dict[str, dict[str, Any]],
    primary_k: int,
    tolerance: float,
) -> tuple[str, dict[str, Any]]:
    if not grades_by_id:
        return "insufficient_labels", {
            "relevant_added_to_top_k": [],
            "relevant_removed_from_top_k": [],
            "same_top_k_set": set(before_ids[:primary_k]) == set(after_ids[:primary_k]),
            "same_top_k_order": before_ids[:primary_k] == after_ids[:primary_k],
        }

    before_relevant = _relevant_top_k(before_ids, grades_by_id, primary_k)
    after_relevant = _relevant_top_k(after_ids, grades_by_id, primary_k)

    removed = sorted(before_relevant - after_relevant)
    added = sorted(after_relevant - before_relevant)

    before_top = before_ids[:primary_k]
    after_top = after_ids[:primary_k]
    same_set = set(before_top) == set(after_top)
    same_order = before_top == after_top

    before_primary = metrics_before.get(str(primary_k)) or {}
    after_primary = metrics_after.get(str(primary_k)) or {}
    protected_metrics = ("hit", "recall", "mrr", "ndcg")
    deltas = {
        metric: safe_float(after_primary.get(metric))
        - safe_float(before_primary.get(metric))
        for metric in protected_metrics
    }

    details = {
        "relevant_added_to_top_k": added,
        "relevant_removed_from_top_k": removed,
        "same_top_k_set": same_set,
        "same_top_k_order": same_order,
        "primary_metric_deltas": {
            key: round(value, 6) for key, value in deltas.items()
        },
    }

    if removed:
        return "ranking_removed_relevant_from_top_k", details

    if added:
        return "ranking_added_relevant_to_top_k", details

    has_negative = any(value < -tolerance for value in deltas.values())
    has_positive = any(value > tolerance for value in deltas.values())

    if has_negative:
        return "ranking_hurt_order", details

    if has_positive:
        return "ranking_helped", details

    if same_order:
        return "ranking_no_effect", details

    if same_set:
        return "tie_or_boundary_effect", details

    # Different non-relevant candidates crossed the boundary without changing
    # explicit relevance metrics. Keep this visible as a boundary effect.
    return "tie_or_boundary_effect", details


def rank_positions(ids: list[str]) -> dict[str, int]:
    return {
        canonical_id: rank
        for rank, canonical_id in enumerate(ids, start=1)
    }


def build_candidate_evidence(
    *,
    candidates: list[dict[str, Any]],
    before_ids: list[str],
    ranked_results: list[Any],
    grades_by_id: dict[str, float],
    apply_ranking: bool,
) -> list[dict[str, Any]]:
    before_position = rank_positions(before_ids)
    after_ids = [item.canonical_id for item in ranked_results] if apply_ranking else before_ids
    after_position = rank_positions(after_ids)

    by_id = {
        item.canonical_id: item
        for item in ranked_results
    }
    raw_by_id = {
        str(candidate["canonical_id"]): candidate
        for candidate in candidates
    }

    rows: list[dict[str, Any]] = []
    for canonical_id in after_ids:
        item = by_id[canonical_id]
        raw = raw_by_id[canonical_id]
        rank_before = before_position[canonical_id]
        rank_after = after_position[canonical_id]

        rows.append(
            {
                "canonical_id": canonical_id,
                "title": str(raw.get("title") or ""),
                "relevant": safe_float(grades_by_id.get(canonical_id)) > 0.0,
                "relevance_grade": safe_float(grades_by_id.get(canonical_id)),
                "rank_before": rank_before,
                "rank_after": rank_after,
                "rank_delta": rank_before - rank_after,
                "retrieval_score_raw": safe_float(raw.get("hybrid_score")),
                "retrieval_score_normalized": float(item.retrieval_score),
                "recency_score": float(item.recency_score),
                "source_support_score": float(item.source_support_score),
                "metadata_quality_score": float(item.metadata_quality_score),
                "final_score": float(item.final_score) if apply_ranking else None,
                "year": raw.get("year"),
                "source_count": int(raw.get("source_count") or 0),
            }
        )

    return rows


def moved_candidate_summary(
    *,
    before_ids: list[str],
    after_ids: list[str],
    grades_by_id: dict[str, float],
    primary_k: int,
) -> dict[str, Any]:
    before_position = rank_positions(before_ids)
    after_position = rank_positions(after_ids)
    shared = set(before_position).intersection(after_position)

    moved = [
        canonical_id
        for canonical_id in shared
        if before_position[canonical_id] != after_position[canonical_id]
    ]
    relevant_up = [
        canonical_id
        for canonical_id in moved
        if safe_float(grades_by_id.get(canonical_id)) > 0.0
        and after_position[canonical_id] < before_position[canonical_id]
    ]
    relevant_down = [
        canonical_id
        for canonical_id in moved
        if safe_float(grades_by_id.get(canonical_id)) > 0.0
        and after_position[canonical_id] > before_position[canonical_id]
    ]

    before_relevant = _relevant_top_k(before_ids, grades_by_id, primary_k)
    after_relevant = _relevant_top_k(after_ids, grades_by_id, primary_k)

    return {
        "moved_candidate_count": len(moved),
        "relevant_moved_up_count": len(relevant_up),
        "relevant_moved_down_count": len(relevant_down),
        "relevant_added_to_top_k": sorted(after_relevant - before_relevant),
        "relevant_removed_from_top_k": sorted(before_relevant - after_relevant),
    }


def _component_map(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("canonical_id") or ""): row
        for row in run.get("candidate_evidence") or []
        if row.get("canonical_id")
    }


def build_candidate_pool_sensitivity_pair(
    *,
    smaller: dict[str, Any],
    larger: dict[str, Any],
    primary_k: int,
) -> dict[str, Any]:
    smaller_components = _component_map(smaller)
    larger_components = _component_map(larger)
    shared_ids = sorted(set(smaller_components).intersection(larger_components))

    component_names = (
        "retrieval_score_normalized",
        "recency_score",
        "source_support_score",
        "metadata_quality_score",
        "final_score",
    )

    component_changes: dict[str, dict[str, float | None]] = {}
    for component in component_names:
        deltas: list[float] = []
        for canonical_id in shared_ids:
            left = smaller_components[canonical_id].get(component)
            right = larger_components[canonical_id].get(component)
            if left is None or right is None:
                continue
            deltas.append(abs(safe_float(right) - safe_float(left)))

        component_changes[component] = {
            "mean_abs_change": mean(deltas) if deltas else None,
            "max_abs_change": round(max(deltas), 6) if deltas else None,
            "changed_count": sum(1 for value in deltas if value > 1e-12),
        }

    smaller_ids = list(smaller.get("result_ids_after") or [])
    larger_ids = list(larger.get("result_ids_after") or [])
    smaller_top = smaller_ids[:primary_k]
    larger_top = larger_ids[:primary_k]
    overlap_count = len(set(smaller_top).intersection(larger_top))

    metric_deltas = metric_delta_map(
        smaller.get("metrics_after") or {},
        larger.get("metrics_after") or {},
    )

    return {
        "query_id": smaller.get("query_id"),
        "query": smaller.get("query"),
        "profile_name": smaller.get("profile_name"),
        "smaller_candidate_k": smaller.get("candidate_k"),
        "larger_candidate_k": larger.get("candidate_k"),
        "shared_candidate_count": len(shared_ids),
        "component_changes": component_changes,
        "top_k_overlap_count": overlap_count,
        "top_k_overlap_ratio": round(overlap_count / max(1, primary_k), 6),
        "top_k_set_equal": set(smaller_top) == set(larger_top),
        "top_k_order_equal": smaller_top == larger_top,
        "metric_deltas": metric_deltas,
    }


def build_candidate_pool_sensitivity(
    *,
    runs: list[dict[str, Any]],
    candidate_k_values: list[int],
    primary_k: int,
) -> list[dict[str, Any]]:
    successful = [run for run in runs if not run.get("error")]
    grouped: dict[tuple[str, str], dict[int, dict[str, Any]]] = defaultdict(dict)

    for run in successful:
        grouped[
            (str(run.get("query_id")), str(run.get("profile_name")))
        ][int(run.get("candidate_k") or 0)] = run

    output: list[dict[str, Any]] = []
    ordered_depths = sorted(candidate_k_values)
    for (_, _), by_depth in sorted(grouped.items()):
        for smaller_k, larger_k in zip(ordered_depths, ordered_depths[1:]):
            if smaller_k not in by_depth or larger_k not in by_depth:
                continue
            output.append(
                build_candidate_pool_sensitivity_pair(
                    smaller=by_depth[smaller_k],
                    larger=by_depth[larger_k],
                    primary_k=primary_k,
                )
            )

    return output


def aggregate_runs(
    *,
    runs: list[dict[str, Any]],
    profiles: list[dict[str, Any]],
    candidate_k_values: list[int],
    metric_k_values: list[int],
    primary_k: int,
    quality_weights: dict[str, float],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_profile_depth: list[dict[str, Any]] = []
    by_profile: list[dict[str, Any]] = []

    for profile in profiles:
        profile_name = str(profile["name"])
        profile_runs_all = [
            run
            for run in runs
            if run.get("profile_name") == profile_name and not run.get("error")
        ]

        for candidate_k in candidate_k_values:
            selected = [
                run
                for run in profile_runs_all
                if int(run.get("candidate_k") or 0) == candidate_k
            ]
            row: dict[str, Any] = {
                "profile_name": profile_name,
                "candidate_k": candidate_k,
                "runs_count": len(selected),
                "error_count": len(
                    [
                        run
                        for run in runs
                        if run.get("profile_name") == profile_name
                        and int(run.get("candidate_k") or 0) == candidate_k
                        and run.get("error")
                    ]
                ),
                "classification_counts": dict(
                    Counter(
                        str(run.get("effect_classification"))
                        for run in selected
                        if run.get("effect_classification")
                    )
                ),
            }

            for k in metric_k_values:
                metrics = [
                    (run.get("metrics_after") or {}).get(str(k)) or {}
                    for run in selected
                ]
                for metric in ("hit", "precision", "recall", "mrr", "ndcg"):
                    row[f"{metric}_at_{k}"] = mean(
                        [safe_float(item.get(metric)) for item in metrics]
                    )

            row["quality_composite"] = compute_quality_composite(
                {
                    "recall": row.get(f"recall_at_{primary_k}", 0.0),
                    "ndcg": row.get(f"ndcg_at_{primary_k}", 0.0),
                    "mrr": row.get(f"mrr_at_{primary_k}", 0.0),
                },
                quality_weights,
            )
            by_profile_depth.append(row)

        overall: dict[str, Any] = {
            "profile_name": profile_name,
            "runs_count": len(profile_runs_all),
            "classification_counts": dict(
                Counter(
                    str(run.get("effect_classification"))
                    for run in profile_runs_all
                    if run.get("effect_classification")
                )
            ),
            "relevant_removed_from_top_k_count": sum(
                len(run.get("relevant_removed_from_top_k") or [])
                for run in profile_runs_all
            ),
            "relevant_added_to_top_k_count": sum(
                len(run.get("relevant_added_to_top_k") or [])
                for run in profile_runs_all
            ),
            "mean_moved_candidate_count": mean(
                [safe_float(run.get("moved_candidate_count")) for run in profile_runs_all]
            ),
        }

        for k in metric_k_values:
            metrics = [
                (run.get("metrics_after") or {}).get(str(k)) or {}
                for run in profile_runs_all
            ]
            for metric in ("hit", "precision", "recall", "mrr", "ndcg"):
                overall[f"{metric}_at_{k}"] = mean(
                    [safe_float(item.get(metric)) for item in metrics]
                )

        overall["quality_composite"] = compute_quality_composite(
            {
                "recall": overall.get(f"recall_at_{primary_k}", 0.0),
                "ndcg": overall.get(f"ndcg_at_{primary_k}", 0.0),
                "mrr": overall.get(f"mrr_at_{primary_k}", 0.0),
            },
            quality_weights,
        )
        by_profile.append(overall)

    by_profile_depth.sort(
        key=lambda row: (
            str(row["profile_name"]),
            int(row["candidate_k"]),
        )
    )
    by_profile.sort(
        key=lambda row: safe_float(row.get("quality_composite")),
        reverse=True,
    )
    return by_profile_depth, by_profile


def build_preliminary_decision(
    *,
    profile_summary: list[dict[str, Any]],
    tolerance: float,
) -> dict[str, Any]:
    by_name = {
        str(row.get("profile_name")): row
        for row in profile_summary
    }
    baseline = by_name.get("unranked") or {}
    current = by_name.get("current") or {}

    baseline_quality = safe_float(baseline.get("quality_composite"))
    current_quality = safe_float(current.get("quality_composite"))
    current_removed = int(current.get("relevant_removed_from_top_k_count") or 0)

    ranked_candidates = [
        row
        for row in profile_summary
        if row.get("profile_name") not in {"unranked", "retrieval_only"}
    ]
    best_ranked = max(
        ranked_candidates,
        key=lambda row: safe_float(row.get("quality_composite")),
        default=None,
    )

    if best_ranked is None:
        outcome = "preserve_current_optional_behavior"
        reason = "No ranked candidate summary is available."
    else:
        best_quality = safe_float(best_ranked.get("quality_composite"))
        best_removed = int(best_ranked.get("relevant_removed_from_top_k_count") or 0)

        if best_quality <= baseline_quality + tolerance:
            outcome = "reject_heuristic_reranking"
            reason = (
                "No evaluated heuristic profile exceeds the unranked quality "
                "composite beyond tolerance."
            )
        elif best_removed > 0:
            outcome = "preserve_current_optional_behavior"
            reason = (
                "The best heuristic profile improves aggregate quality but "
                "removes explicitly relevant papers from at least one top-k result."
            )
        else:
            outcome = "promote_simplified_heuristic_in_follow_up"
            reason = (
                "A heuristic candidate exceeds the unranked aggregate quality "
                "without observed relevant-paper top-k loss; manual review and "
                "strict validation are still required."
            )

    return {
        "status": "preliminary_evidence_only",
        "automatic_public_change_allowed": False,
        "recommended_outcome": outcome,
        "reason": reason,
        "unranked_quality_composite": baseline_quality,
        "current_quality_composite": current_quality,
        "current_relevant_removed_from_top_k_count": current_removed,
        "best_ranked_profile": (
            best_ranked.get("profile_name")
            if best_ranked is not None
            else None
        ),
        "best_ranked_quality_composite": (
            safe_float(best_ranked.get("quality_composite"))
            if best_ranked is not None
            else None
        ),
        "requires_manual_review": True,
        "requires_strict_validator": True,
    }


def build_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    decision = report.get("decision") or {}
    profile_summary = report.get("profile_summary") or []

    lines: list[str] = []
    lines.append("# Ranking Evaluation and Hardening v1")
    lines.append("")
    lines.append(f"- Generated at: `{report.get('generated_at_utc')}`")
    lines.append(f"- Build ID: `{(report.get('runtime') or {}).get('build_id')}`")
    lines.append(f"- Corpus documents: `{(report.get('runtime') or {}).get('corpus_doc_count')}`")
    lines.append(f"- Enabled queries: `{summary.get('enabled_cases_count')}`")
    lines.append(f"- Profiles: `{summary.get('profiles_count')}`")
    lines.append(f"- Candidate depths: `{summary.get('candidate_depths_count')}`")
    lines.append(f"- Runs: `{summary.get('runs_count')}`")
    lines.append(f"- Errors: `{summary.get('error_count')}`")
    lines.append(f"- Determinism failures: `{summary.get('determinism_failure_count')}`")
    lines.append("")

    lines.append("## Profile summary")
    lines.append("")
    lines.append("| profile | quality | recall@10 | nDCG@10 | MRR@10 | relevant removed |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for row in profile_summary:
        lines.append(
            "| {profile} | {quality:.6f} | {recall:.6f} | {ndcg:.6f} | "
            "{mrr:.6f} | {removed} |".format(
                profile=row.get("profile_name"),
                quality=safe_float(row.get("quality_composite")),
                recall=safe_float(row.get("recall_at_10")),
                ndcg=safe_float(row.get("ndcg_at_10")),
                mrr=safe_float(row.get("mrr_at_10")),
                removed=int(row.get("relevant_removed_from_top_k_count") or 0),
            )
        )
    lines.append("")

    lines.append("## Preliminary decision")
    lines.append("")
    lines.append(f"- Status: `{decision.get('status')}`")
    lines.append(f"- Recommended outcome: `{decision.get('recommended_outcome')}`")
    lines.append(f"- Best ranked profile: `{decision.get('best_ranked_profile')}`")
    lines.append(f"- Reason: {decision.get('reason')}")
    lines.append("")
    lines.append(
        "This decision is evidence-only. It does not change the public ranking "
        "default and must be reviewed together with the strict validator and "
        "per-query candidate movements."
    )
    lines.append("")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate free-form search ranking profiles while holding hybrid "
            "retrieval candidates and weights fixed."
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
    if config.get("schema_version") != "ranking_evaluation_v1":
        raise ValueError(
            f"Unsupported schema_version: {config.get('schema_version')!r}"
        )

    defaults = config.get("defaults") or {}
    paths = config.get("paths") or {}
    analysis = config.get("analysis") or {}

    backend_mode = args.backend_mode or str(defaults.get("backend_mode") or "file")
    lexical_weight = safe_float(defaults.get("lexical_weight"), 0.55)
    dense_weight = safe_float(defaults.get("dense_weight"), 0.45)
    candidate_k_values = sorted(
        {
            int(value)
            for value in defaults.get("candidate_k_values") or [50, 100]
        }
    )
    search_top_k = int(defaults.get("search_top_k") or 20)
    metric_k_values = sorted(
        {
            int(value)
            for value in defaults.get("metric_k_values") or [5, 10, 20]
        }
    )
    primary_k = int(defaults.get("primary_k") or 10)
    if primary_k not in metric_k_values:
        metric_k_values.append(primary_k)
        metric_k_values.sort()

    tolerance = safe_float(defaults.get("numeric_tolerance"), 1e-12)
    determinism_repeats = max(
        2,
        int(defaults.get("determinism_repeats") or 2),
    )
    quality_weights = analysis.get("quality_composite_weights") or {
        "recall": 0.40,
        "ndcg": 0.40,
        "mrr": 0.20,
    }

    profiles = list(config.get("profiles") or [])
    if not profiles:
        raise ValueError("No ranking profiles configured")

    profile_names = [str(profile.get("name") or "") for profile in profiles]
    if len(profile_names) != len(set(profile_names)):
        raise ValueError("Ranking profile names must be unique")

    for profile in profiles:
        validate_profile(profile, tolerance)

    if "unranked" not in profile_names:
        raise ValueError("The config must include the unranked baseline profile")

    golden_path = args.golden_queries_path or Path(
        paths.get(
            "golden_queries_path",
            "data/eval/retrieval/golden_queries.jsonl",
        )
    )
    output_dir = args.output_dir or Path(
        paths.get("output_dir", DEFAULT_OUTPUT_DIR)
    )

    golden_rows = load_jsonl(golden_path)
    enabled_cases = [
        row
        for row in golden_rows
        if row.get("enabled", True)
    ]

    if bool(analysis.get("require_explicit_relevance_labels", True)):
        enabled_cases = [
            row
            for row in enabled_cases
            if graded_relevance_map(row)
        ]

    runtime = build_runtime(backend_mode)
    snapshot = runtime.runtime_snapshot()
    max_candidate_k = max(candidate_k_values)

    runs: list[dict[str, Any]] = []
    query_cache_meta: list[dict[str, Any]] = []

    for case in enabled_cases:
        query_id = str(case.get("query_id") or "")
        query = str(case.get("query") or "").strip()
        if not query:
            continue

        query_cache = prepare_query_cache(
            runtime=runtime,
            query=query,
            max_candidate_k=max_candidate_k,
        )
        cache_timing = query_cache.get("retrieval_cache_timing_ms") or {}
        query_cache_meta.append(
            {
                "query_id": query_id,
                "query": query,
                "max_candidate_k": max_candidate_k,
                "lexical_ms": cache_timing.get("lexical_ms"),
                "dense_ms": cache_timing.get("dense_ms"),
            }
        )

        grades_by_id = graded_relevance_map(case)

        for candidate_k in candidate_k_values:
            try:
                raw_candidates, merge_timings = build_hybrid_candidates_from_cache(
                    runtime=runtime,
                    query_cache=query_cache,
                    candidate_k=candidate_k,
                    lexical_weight=lexical_weight,
                    dense_weight=dense_weight,
                )
            except Exception as exc:
                for profile in profiles:
                    runs.append(
                        {
                            "query_id": query_id,
                            "query": query,
                            "group": str(case.get("group") or "ungrouped"),
                            "candidate_k": candidate_k,
                            "profile_name": profile.get("name"),
                            "apply_ranking": bool(profile.get("apply_ranking")),
                            "weights": profile.get("weights"),
                            "error": repr(exc),
                        }
                    )
                continue

            before_ids = [
                str(candidate.get("canonical_id") or "")
                for candidate in raw_candidates
            ]
            unranked_eval = [
                candidate_to_eval_result(candidate)
                for candidate in raw_candidates[:search_top_k]
            ]
            metrics_before = {
                str(k): metrics_at_k(
                    case=case,
                    results=unranked_eval,
                    k=k,
                )
                for k in metric_k_values
            }

            # Component scores are independent of profile weights. Compute the
            # baseline component map once through the production scorer.
            baseline_components = rank_results(
                raw_candidates,
                retrieval_score_field="hybrid_score",
                retrieval_weight=1.0,
                recency_weight=0.0,
                source_support_weight=0.0,
                metadata_quality_weight=0.0,
            )

            for profile in profiles:
                profile_name = str(profile["name"])
                apply_ranking = bool(profile.get("apply_ranking"))
                weights = profile_weights(profile)

                try:
                    t0 = time.perf_counter()

                    if apply_ranking:
                        ranked_results = rank_results(
                            raw_candidates,
                            retrieval_score_field="hybrid_score",
                            retrieval_weight=weights["retrieval"],
                            recency_weight=weights["recency"],
                            source_support_weight=weights["source_support"],
                            metadata_quality_weight=weights["metadata_quality"],
                        )
                    else:
                        ranked_results = baseline_components

                    after_ids = (
                        [item.canonical_id for item in ranked_results]
                        if apply_ranking
                        else before_ids
                    )
                    eval_results = (
                        [
                            ranked_to_eval_result(item)
                            for item in ranked_results[:search_top_k]
                        ]
                        if apply_ranking
                        else unranked_eval
                    )
                    metrics_after = {
                        str(k): metrics_at_k(
                            case=case,
                            results=eval_results,
                            k=k,
                        )
                        for k in metric_k_values
                    }

                    repeated_orders: list[list[str]] = []
                    repeated_scores: list[list[float]] = []
                    for _ in range(determinism_repeats):
                        repeated = (
                            rank_results(
                                raw_candidates,
                                retrieval_score_field="hybrid_score",
                                retrieval_weight=weights["retrieval"],
                                recency_weight=weights["recency"],
                                source_support_weight=weights["source_support"],
                                metadata_quality_weight=weights["metadata_quality"],
                            )
                            if apply_ranking
                            else baseline_components
                        )
                        repeated_orders.append(
                            (
                                [item.canonical_id for item in repeated]
                                if apply_ranking
                                else before_ids
                            )
                        )
                        repeated_scores.append(
                            [
                                float(item.final_score)
                                for item in repeated
                            ]
                        )

                    deterministic_order = all(
                        order == repeated_orders[0]
                        for order in repeated_orders[1:]
                    )
                    deterministic_scores = all(
                        len(scores) == len(repeated_scores[0])
                        and all(
                            abs(left - right) <= tolerance
                            for left, right in zip(
                                repeated_scores[0],
                                scores,
                            )
                        )
                        for scores in repeated_scores[1:]
                    )

                    classification = None
                    classification_details: dict[str, Any] = {}
                    if apply_ranking:
                        classification, classification_details = classify_ranking_effect(
                            before_ids=before_ids,
                            after_ids=after_ids,
                            grades_by_id=grades_by_id,
                            metrics_before=metrics_before,
                            metrics_after=metrics_after,
                            primary_k=primary_k,
                            tolerance=tolerance,
                        )

                    movement = moved_candidate_summary(
                        before_ids=before_ids,
                        after_ids=after_ids,
                        grades_by_id=grades_by_id,
                        primary_k=primary_k,
                    )
                    evidence = build_candidate_evidence(
                        candidates=raw_candidates,
                        before_ids=before_ids,
                        ranked_results=ranked_results,
                        grades_by_id=grades_by_id,
                        apply_ranking=apply_ranking,
                    )

                    elapsed_ms = round(
                        (time.perf_counter() - t0) * 1000.0,
                        3,
                    )

                    runs.append(
                        {
                            "query_id": query_id,
                            "query": query,
                            "group": str(case.get("group") or "ungrouped"),
                            "candidate_k": candidate_k,
                            "profile_name": profile_name,
                            "apply_ranking": apply_ranking,
                            "weights": weights if apply_ranking else None,
                            "results_count": len(eval_results),
                            "candidate_count": len(raw_candidates),
                            "result_ids_before": before_ids[:search_top_k],
                            "result_ids_after": after_ids[:search_top_k],
                            "metrics_before": metrics_before,
                            "metrics_after": metrics_after,
                            "metric_deltas": metric_delta_map(
                                metrics_before,
                                metrics_after,
                            ),
                            "effect_classification": classification,
                            "classification_details": classification_details,
                            **movement,
                            "candidate_evidence": evidence,
                            "determinism": {
                                "repeats": determinism_repeats,
                                "order_equal": deterministic_order,
                                "scores_equal_within_tolerance": deterministic_scores,
                                "ok": deterministic_order and deterministic_scores,
                            },
                            "timings": {
                                "hybrid_merge_ms": merge_timings.get("hybrid_merge_ms"),
                                "ranking_evaluation_ms": elapsed_ms,
                            },
                            "error": None,
                        }
                    )

                except Exception as exc:
                    runs.append(
                        {
                            "query_id": query_id,
                            "query": query,
                            "group": str(case.get("group") or "ungrouped"),
                            "candidate_k": candidate_k,
                            "profile_name": profile_name,
                            "apply_ranking": apply_ranking,
                            "weights": weights if apply_ranking else None,
                            "error": repr(exc),
                        }
                    )

    profile_depth_summary, profile_summary = aggregate_runs(
        runs=runs,
        profiles=profiles,
        candidate_k_values=candidate_k_values,
        metric_k_values=metric_k_values,
        primary_k=primary_k,
        quality_weights=quality_weights,
    )
    sensitivity = build_candidate_pool_sensitivity(
        runs=runs,
        candidate_k_values=candidate_k_values,
        primary_k=primary_k,
    )
    decision = build_preliminary_decision(
        profile_summary=profile_summary,
        tolerance=tolerance,
    )

    classification_counts = Counter(
        str(run.get("effect_classification"))
        for run in runs
        if run.get("effect_classification")
    )
    determinism_failures = [
        run
        for run in runs
        if not run.get("error")
        and not (run.get("determinism") or {}).get("ok", False)
    ]
    errors = [run for run in runs if run.get("error")]

    report = {
        "schema_version": "ranking_evaluation_v1",
        "report_name": "ranking_evaluation",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "inputs": {
            "config_path": normalize_path(args.config_path),
            "golden_queries_path": normalize_path(golden_path),
        },
        "config": {
            "backend_mode": backend_mode,
            "search_mode": "hybrid",
            "lexical_weight": lexical_weight,
            "dense_weight": dense_weight,
            "candidate_k_values": candidate_k_values,
            "search_top_k": search_top_k,
            "metric_k_values": metric_k_values,
            "primary_k": primary_k,
            "numeric_tolerance": tolerance,
            "determinism_repeats": determinism_repeats,
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
            "profiles_count": len(profiles),
            "candidate_depths_count": len(candidate_k_values),
            "expected_runs_count": (
                len(enabled_cases)
                * len(profiles)
                * len(candidate_k_values)
            ),
            "runs_count": len(runs),
            "error_count": len(errors),
            "ranked_comparisons_count": len(
                [run for run in runs if run.get("apply_ranking")]
            ),
            "classification_counts": dict(classification_counts),
            "determinism_failure_count": len(determinism_failures),
            "candidate_pool_sensitivity_rows_count": len(sensitivity),
        },
        "query_cache_meta": query_cache_meta,
        "profiles": profiles,
        "runs": runs,
        "profile_depth_summary": profile_depth_summary,
        "profile_summary": profile_summary,
        "candidate_pool_sensitivity": sensitivity,
        "decision": decision,
    }

    latest_json = output_dir / "ranking_evaluation_latest.json"
    latest_md = output_dir / "ranking_evaluation_latest.md"
    history_json = (
        output_dir
        / "history"
        / f"ranking_evaluation_{run_ts}.json"
    )
    history_md = (
        output_dir
        / "history"
        / f"ranking_evaluation_{run_ts}.md"
    )

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(history_json, report)
    dump_text(history_md, build_markdown(report))

    print(f"[OK] schema_version={report['schema_version']}")
    print(f"[OK] backend_mode={snapshot.get('backend_mode')}")
    print(f"[OK] build_id={snapshot.get('build_id')}")
    print(f"[OK] corpus_doc_count={snapshot.get('corpus_doc_count')}")
    print(f"[OK] enabled_cases_count={len(enabled_cases)}")
    print(f"[OK] profiles_count={len(profiles)}")
    print(f"[OK] candidate_depths_count={len(candidate_k_values)}")
    print(f"[OK] expected_runs_count={report['summary']['expected_runs_count']}")
    print(f"[OK] runs_count={len(runs)}")
    print(f"[OK] error_count={len(errors)}")
    print(f"[OK] determinism_failure_count={len(determinism_failures)}")
    print(f"[OK] decision={decision.get('recommended_outcome')}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {history_json}")
    print(f"[OK] history Markdown: {history_md}")


if __name__ == "__main__":
    main()
