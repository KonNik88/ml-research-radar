from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_REPORT_PATH = Path(
    "artifacts/reports/evaluation/ranking_evaluation_latest.json"
)
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/evaluation")
DEFAULT_PRIMARY_K = 10
DEFAULT_TOP_N = 15


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Ranking evaluation report not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except Exception:
        return default
    return result if math.isfinite(result) else default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(float(statistics.fmean(values)), 6)


def metric_deltas_at_k(
    run: dict[str, Any],
    primary_k: int,
) -> dict[str, float]:
    row = (
        (run.get("metric_deltas") or {}).get(str(primary_k))
        or {}
    )
    return {
        metric: round(safe_float(row.get(metric)), 6)
        for metric in ("hit", "precision", "recall", "mrr", "ndcg")
    }


def candidate_rows_by_id(run: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("canonical_id") or ""): row
        for row in run.get("candidate_evidence") or []
        if row.get("canonical_id")
    }


def compact_candidate(
    row: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "canonical_id": row.get("canonical_id"),
        "title": row.get("title"),
        "relevant": bool(row.get("relevant")),
        "relevance_grade": safe_float(row.get("relevance_grade")),
        "rank_before": safe_int(row.get("rank_before")),
        "rank_after": safe_int(row.get("rank_after")),
        "rank_delta": safe_int(row.get("rank_delta")),
        "retrieval_score_raw": safe_float(row.get("retrieval_score_raw")),
        "retrieval_score_normalized": safe_float(
            row.get("retrieval_score_normalized")
        ),
        "recency_score": safe_float(row.get("recency_score")),
        "source_support_score": safe_float(
            row.get("source_support_score")
        ),
        "metadata_quality_score": safe_float(
            row.get("metadata_quality_score")
        ),
        "final_score": (
            safe_float(row.get("final_score"))
            if row.get("final_score") is not None
            else None
        ),
        "year": row.get("year"),
        "source_count": safe_int(row.get("source_count")),
    }


def compact_query_run(
    run: dict[str, Any],
    *,
    primary_k: int,
) -> dict[str, Any]:
    by_id = candidate_rows_by_id(run)
    removed_ids = list(run.get("relevant_removed_from_top_k") or [])
    added_ids = list(run.get("relevant_added_to_top_k") or [])
    deltas = metric_deltas_at_k(run, primary_k)

    return {
        "query_id": run.get("query_id"),
        "query": run.get("query"),
        "group": run.get("group"),
        "candidate_k": safe_int(run.get("candidate_k")),
        "profile_name": run.get("profile_name"),
        "effect_classification": run.get("effect_classification"),
        "metric_deltas_at_primary_k": deltas,
        "harm_score": round(
            max(0.0, -deltas["recall"]) * 4.0
            + max(0.0, -deltas["ndcg"]) * 3.0
            + max(0.0, -deltas["mrr"]) * 2.0
            + len(removed_ids) * 1.0,
            6,
        ),
        "help_score": round(
            max(0.0, deltas["recall"]) * 4.0
            + max(0.0, deltas["ndcg"]) * 3.0
            + max(0.0, deltas["mrr"]) * 2.0
            + len(added_ids) * 1.0,
            6,
        ),
        "moved_candidate_count": safe_int(
            run.get("moved_candidate_count")
        ),
        "relevant_moved_up_count": safe_int(
            run.get("relevant_moved_up_count")
        ),
        "relevant_moved_down_count": safe_int(
            run.get("relevant_moved_down_count")
        ),
        "removed_relevant": [
            compact_candidate(by_id.get(canonical_id))
            for canonical_id in removed_ids
        ],
        "added_relevant": [
            compact_candidate(by_id.get(canonical_id))
            for canonical_id in added_ids
        ],
        "result_ids_before": list(run.get("result_ids_before") or []),
        "result_ids_after": list(run.get("result_ids_after") or []),
    }


def profile_summary_map(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("profile_name") or ""): row
        for row in report.get("profile_summary") or []
        if row.get("profile_name")
    }


def build_profile_comparison(
    report: dict[str, Any],
) -> list[dict[str, Any]]:
    by_profile = profile_summary_map(report)
    baseline = by_profile.get("unranked") or {}
    baseline_quality = safe_float(baseline.get("quality_composite"))

    rows: list[dict[str, Any]] = []
    for name, row in by_profile.items():
        quality = safe_float(row.get("quality_composite"))
        rows.append(
            {
                "profile_name": name,
                "quality_composite": quality,
                "quality_delta_vs_unranked": round(
                    quality - baseline_quality,
                    6,
                ),
                "recall_at_10": safe_float(row.get("recall_at_10")),
                "ndcg_at_10": safe_float(row.get("ndcg_at_10")),
                "mrr_at_10": safe_float(row.get("mrr_at_10")),
                "mean_moved_candidate_count": safe_float(
                    row.get("mean_moved_candidate_count")
                ),
                "relevant_added_to_top_k_count": safe_int(
                    row.get("relevant_added_to_top_k_count")
                ),
                "relevant_removed_from_top_k_count": safe_int(
                    row.get("relevant_removed_from_top_k_count")
                ),
                "classification_counts": dict(
                    row.get("classification_counts") or {}
                ),
            }
        )

    rows.sort(
        key=lambda item: (
            safe_float(item.get("quality_composite")),
            -safe_int(item.get("relevant_removed_from_top_k_count")),
        ),
        reverse=True,
    )
    return rows


def build_profile_query_cases(
    report: dict[str, Any],
    *,
    profile_name: str,
    primary_k: int,
    top_n: int,
) -> dict[str, Any]:
    runs = [
        run
        for run in report.get("runs") or []
        if not run.get("error")
        and str(run.get("profile_name") or "") == profile_name
    ]
    compact = [
        compact_query_run(run, primary_k=primary_k)
        for run in runs
    ]

    harmful = sorted(
        compact,
        key=lambda row: (
            safe_float(row.get("harm_score")),
            -safe_float(
                (row.get("metric_deltas_at_primary_k") or {}).get("ndcg")
            ),
            safe_int(row.get("moved_candidate_count")),
        ),
        reverse=True,
    )
    helpful = sorted(
        compact,
        key=lambda row: (
            safe_float(row.get("help_score")),
            safe_float(
                (row.get("metric_deltas_at_primary_k") or {}).get("ndcg")
            ),
            safe_int(row.get("moved_candidate_count")),
        ),
        reverse=True,
    )

    classification_counts = Counter(
        str(row.get("effect_classification") or "")
        for row in compact
        if row.get("effect_classification")
    )

    return {
        "profile_name": profile_name,
        "runs_count": len(compact),
        "classification_counts": dict(classification_counts),
        "worst_cases": [
            row for row in harmful if row["harm_score"] > 0.0
        ][:top_n],
        "best_cases": [
            row for row in helpful if row["help_score"] > 0.0
        ][:top_n],
    }


def aggregate_sensitivity(
    report: dict[str, Any],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in report.get("candidate_pool_sensitivity") or []:
        grouped[str(row.get("profile_name") or "")].append(row)

    output: list[dict[str, Any]] = []
    component_names = (
        "retrieval_score_normalized",
        "recency_score",
        "source_support_score",
        "metadata_quality_score",
        "final_score",
    )

    for profile_name, rows in grouped.items():
        component_summary: dict[str, dict[str, Any]] = {}
        for component in component_names:
            mean_changes: list[float] = []
            max_changes: list[float] = []
            changed_counts: list[int] = []

            for row in rows:
                stats = (
                    (row.get("component_changes") or {}).get(component)
                    or {}
                )
                if stats.get("mean_abs_change") is not None:
                    mean_changes.append(
                        safe_float(stats.get("mean_abs_change"))
                    )
                if stats.get("max_abs_change") is not None:
                    max_changes.append(
                        safe_float(stats.get("max_abs_change"))
                    )
                changed_counts.append(
                    safe_int(stats.get("changed_count"))
                )

            component_summary[component] = {
                "mean_of_mean_abs_change": mean(mean_changes),
                "max_abs_change_observed": (
                    round(max(max_changes), 6)
                    if max_changes
                    else None
                ),
                "mean_changed_candidate_count": mean(
                    [float(value) for value in changed_counts]
                ),
            }

        output.append(
            {
                "profile_name": profile_name,
                "comparisons_count": len(rows),
                "top_k_set_equal_rate": mean(
                    [
                        1.0 if bool(row.get("top_k_set_equal")) else 0.0
                        for row in rows
                    ]
                ),
                "top_k_order_equal_rate": mean(
                    [
                        1.0 if bool(row.get("top_k_order_equal")) else 0.0
                        for row in rows
                    ]
                ),
                "mean_top_k_overlap_ratio": mean(
                    [
                        safe_float(row.get("top_k_overlap_ratio"))
                        for row in rows
                    ]
                ),
                "component_summary": component_summary,
            }
        )

    output.sort(key=lambda row: str(row.get("profile_name") or ""))
    return output


def build_signal_diagnosis(
    report: dict[str, Any],
) -> dict[str, Any]:
    profile_rows = build_profile_comparison(report)
    by_name = {
        str(row.get("profile_name") or ""): row
        for row in profile_rows
    }

    current = by_name.get("current") or {}
    metadata = by_name.get("retrieval_plus_metadata_quality") or {}
    recency = by_name.get("retrieval_plus_recency") or {}
    source_support = by_name.get("retrieval_plus_source_support") or {}

    return {
        "current_vs_unranked": {
            "quality_delta": safe_float(
                current.get("quality_delta_vs_unranked")
            ),
            "relevant_removed": safe_int(
                current.get("relevant_removed_from_top_k_count")
            ),
            "mean_moved_candidates": safe_float(
                current.get("mean_moved_candidate_count")
            ),
        },
        "metadata_quality_signal": {
            "quality_delta_vs_unranked": safe_float(
                metadata.get("quality_delta_vs_unranked")
            ),
            "relevant_removed": safe_int(
                metadata.get("relevant_removed_from_top_k_count")
            ),
            "interpretation": (
                "closest_to_baseline_but_not_better"
                if metadata
                else "profile_missing"
            ),
        },
        "recency_signal": {
            "quality_delta_vs_unranked": safe_float(
                recency.get("quality_delta_vs_unranked")
            ),
            "relevant_removed": safe_int(
                recency.get("relevant_removed_from_top_k_count")
            ),
            "interpretation": (
                "harmful_under_current_labels"
                if safe_float(
                    recency.get("quality_delta_vs_unranked")
                ) < 0.0
                else "non_harmful"
            ),
        },
        "source_support_signal": {
            "quality_delta_vs_unranked": safe_float(
                source_support.get("quality_delta_vs_unranked")
            ),
            "relevant_removed": safe_int(
                source_support.get("relevant_removed_from_top_k_count")
            ),
            "interpretation": (
                "harmful_under_current_labels"
                if safe_float(
                    source_support.get("quality_delta_vs_unranked")
                ) < 0.0
                else "non_harmful"
            ),
        },
    }


def build_analysis(
    report: dict[str, Any],
    *,
    primary_k: int,
    top_n: int,
) -> dict[str, Any]:
    if report.get("schema_version") != "ranking_evaluation_v1":
        raise ValueError(
            "Unsupported ranking evaluation schema: "
            f"{report.get('schema_version')!r}"
        )

    profile_rows = build_profile_comparison(report)
    selected_profiles = (
        "current",
        "retrieval_plus_metadata_quality",
        "retrieval_plus_recency",
        "retrieval_plus_source_support",
    )
    query_cases = {
        profile_name: build_profile_query_cases(
            report,
            profile_name=profile_name,
            primary_k=primary_k,
            top_n=top_n,
        )
        for profile_name in selected_profiles
    }

    return {
        "schema_version": "ranking_evaluation_analysis_v1",
        "report_name": "ranking_evaluation_analysis",
        "generated_at_utc": utc_now_iso(),
        "source_evaluation": {
            "schema_version": report.get("schema_version"),
            "generated_at_utc": report.get("generated_at_utc"),
            "run_ts": report.get("run_ts"),
            "runtime": report.get("runtime"),
            "summary": report.get("summary"),
            "decision": report.get("decision"),
        },
        "analysis_config": {
            "primary_k": primary_k,
            "top_n": top_n,
            "selected_profiles": list(selected_profiles),
        },
        "profile_comparison": profile_rows,
        "signal_diagnosis": build_signal_diagnosis(report),
        "query_cases": query_cases,
        "candidate_pool_sensitivity": aggregate_sensitivity(report),
        "accepted_interpretation": {
            "recommended_outcome": (
                (report.get("decision") or {}).get(
                    "recommended_outcome"
                )
            ),
            "public_default_change": False,
            "reference_profile": "unranked",
            "best_ranked_profile": (
                (report.get("decision") or {}).get(
                    "best_ranked_profile"
                )
            ),
            "statement": (
                "No evaluated heuristic ranking profile exceeded the "
                "unranked hybrid baseline. The current heuristic ranking "
                "materially reduces retrieval quality and removes explicitly "
                "relevant papers from top-k results."
            ),
        },
    }


def _format_candidate(candidate: dict[str, Any] | None) -> str:
    if not candidate:
        return "unknown candidate"
    return (
        f"`{candidate.get('canonical_id')}` "
        f"(rank {candidate.get('rank_before')} → "
        f"{candidate.get('rank_after')}, "
        f"retrieval={safe_float(candidate.get('retrieval_score_normalized')):.4f}, "
        f"recency={safe_float(candidate.get('recency_score')):.4f}, "
        f"source={safe_float(candidate.get('source_support_score')):.4f}, "
        f"metadata={safe_float(candidate.get('metadata_quality_score')):.4f})"
    )


def build_markdown(analysis: dict[str, Any]) -> str:
    source = analysis.get("source_evaluation") or {}
    decision = source.get("decision") or {}
    summary = source.get("summary") or {}

    lines: list[str] = []
    lines.append("# Ranking Evaluation Analysis v1")
    lines.append("")
    lines.append(
        f"- Generated at: `{analysis.get('generated_at_utc')}`"
    )
    lines.append(
        f"- Build ID: `{(source.get('runtime') or {}).get('build_id')}`"
    )
    lines.append(
        f"- Corpus documents: "
        f"`{(source.get('runtime') or {}).get('corpus_doc_count')}`"
    )
    lines.append(
        f"- Evaluated runs: `{summary.get('runs_count')}`"
    )
    lines.append(
        f"- Recommended outcome: "
        f"`{decision.get('recommended_outcome')}`"
    )
    lines.append("")

    lines.append("## Accepted interpretation")
    lines.append("")
    lines.append(
        (analysis.get("accepted_interpretation") or {}).get(
            "statement",
            "",
        )
    )
    lines.append("")
    lines.append(
        "No public ranking default is changed by this analysis."
    )
    lines.append("")

    lines.append("## Profile comparison")
    lines.append("")
    lines.append(
        "| profile | quality | Δ vs unranked | recall@10 | "
        "nDCG@10 | MRR@10 | relevant removed |"
    )
    lines.append(
        "|---|---:|---:|---:|---:|---:|---:|"
    )
    for row in analysis.get("profile_comparison") or []:
        lines.append(
            "| {profile} | {quality:.6f} | {delta:.6f} | "
            "{recall:.6f} | {ndcg:.6f} | {mrr:.6f} | "
            "{removed} |".format(
                profile=row.get("profile_name"),
                quality=safe_float(row.get("quality_composite")),
                delta=safe_float(row.get("quality_delta_vs_unranked")),
                recall=safe_float(row.get("recall_at_10")),
                ndcg=safe_float(row.get("ndcg_at_10")),
                mrr=safe_float(row.get("mrr_at_10")),
                removed=safe_int(
                    row.get("relevant_removed_from_top_k_count")
                ),
            )
        )
    lines.append("")

    lines.append("## Signal diagnosis")
    lines.append("")
    for signal, values in (
        analysis.get("signal_diagnosis") or {}
    ).items():
        lines.append(f"### {signal}")
        for key, value in values.items():
            lines.append(f"- {key}: `{value}`")
        lines.append("")

    current_cases = (
        (analysis.get("query_cases") or {}).get("current")
        or {}
    )

    lines.append("## Most harmful current-ranking cases")
    lines.append("")
    for index, row in enumerate(
        current_cases.get("worst_cases") or [],
        start=1,
    ):
        deltas = row.get("metric_deltas_at_primary_k") or {}
        lines.append(
            f"### {index}. {row.get('query_id')} — "
            f"{row.get('query')}"
        )
        lines.append(
            f"- candidate_k: `{row.get('candidate_k')}`"
        )
        lines.append(
            f"- classification: "
            f"`{row.get('effect_classification')}`"
        )
        lines.append(
            f"- Δ Recall@10: `{safe_float(deltas.get('recall')):.6f}`"
        )
        lines.append(
            f"- Δ nDCG@10: `{safe_float(deltas.get('ndcg')):.6f}`"
        )
        lines.append(
            f"- Δ MRR@10: `{safe_float(deltas.get('mrr')):.6f}`"
        )
        for candidate in row.get("removed_relevant") or []:
            lines.append(
                f"- removed relevant: {_format_candidate(candidate)}"
            )
        lines.append("")

    lines.append("## Candidate-pool sensitivity")
    lines.append("")
    lines.append(
        "| profile | comparisons | top-k set equal | "
        "top-k order equal | mean overlap |"
    )
    lines.append("|---|---:|---:|---:|---:|")
    for row in analysis.get("candidate_pool_sensitivity") or []:
        lines.append(
            "| {profile} | {count} | {set_rate:.6f} | "
            "{order_rate:.6f} | {overlap:.6f} |".format(
                profile=row.get("profile_name"),
                count=safe_int(row.get("comparisons_count")),
                set_rate=safe_float(row.get("top_k_set_equal_rate")),
                order_rate=safe_float(row.get("top_k_order_equal_rate")),
                overlap=safe_float(row.get("mean_top_k_overlap_ratio")),
            )
        )
    lines.append("")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a compact, human-readable analysis from the full "
            "ranking evaluation evidence report."
        )
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=DEFAULT_REPORT_PATH,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
    )
    parser.add_argument(
        "--primary-k",
        type=int,
        default=DEFAULT_PRIMARY_K,
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=DEFAULT_TOP_N,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_ts = utc_now_ts()

    report = load_json(args.report_path)
    analysis = build_analysis(
        report,
        primary_k=args.primary_k,
        top_n=args.top_n,
    )

    output_dir = args.output_dir
    latest_json = (
        output_dir / "ranking_evaluation_analysis_latest.json"
    )
    latest_md = (
        output_dir / "ranking_evaluation_analysis_latest.md"
    )
    history_json = (
        output_dir
        / "history"
        / f"ranking_evaluation_analysis_{run_ts}.json"
    )
    history_md = (
        output_dir
        / "history"
        / f"ranking_evaluation_analysis_{run_ts}.md"
    )

    dump_json(latest_json, analysis)
    dump_text(latest_md, build_markdown(analysis))
    dump_json(history_json, analysis)
    dump_text(history_md, build_markdown(analysis))

    current_cases = (
        (analysis.get("query_cases") or {}).get("current")
        or {}
    )
    interpretation = analysis.get("accepted_interpretation") or {}

    print(f"[OK] schema_version={analysis.get('schema_version')}")
    print(
        "[OK] source_runs_count="
        f"{((analysis.get('source_evaluation') or {}).get('summary') or {}).get('runs_count')}"
    )
    print(
        "[OK] recommended_outcome="
        f"{interpretation.get('recommended_outcome')}"
    )
    print(
        "[OK] current_worst_cases_count="
        f"{len(current_cases.get('worst_cases') or [])}"
    )
    print(
        "[OK] current_best_cases_count="
        f"{len(current_cases.get('best_cases') or [])}"
    )
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {history_json}")
    print(f"[OK] history Markdown: {history_md}")


if __name__ == "__main__":
    main()
