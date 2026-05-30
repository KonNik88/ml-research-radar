from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PyYAML is required for search quality experiment config loading.") from exc


DEFAULT_CONFIG_PATH = Path("configs/search_quality_experiments_v1.yaml")
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


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Search quality experiments config not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Config must be a YAML mapping: {path}")
    return payload


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"JSON report not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON report must be an object: {path}")
    return payload


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


def get_metric(mode_summary: dict[str, Any], mode: str, metric: str, k: int) -> float:
    return safe_float((mode_summary.get(mode) or {}).get(f"{metric}_at_{k}"), 0.0)


def get_latency(mode_summary: dict[str, Any], mode: str, key: str = "p50") -> float | None:
    latency = (mode_summary.get(mode) or {}).get("latency_ms") or {}
    if latency.get(key) is None:
        return None
    return safe_float(latency.get(key), 0.0)


def compute_quality_composite(
    *,
    mode_summary: dict[str, Any],
    mode: str,
    primary_k: int,
    weights: dict[str, float],
) -> float:
    total_weight = sum(max(0.0, safe_float(v)) for v in weights.values())
    if total_weight <= 0:
        weights = {"recall": 0.4, "ndcg": 0.4, "mrr": 0.2}
        total_weight = 1.0

    value = 0.0
    for metric, weight in weights.items():
        weight_f = max(0.0, safe_float(weight))
        value += (weight_f / total_weight) * get_metric(mode_summary, mode, metric, primary_k)

    return round(value, 6)


def build_mode_table(
    *,
    retrieval_eval: dict[str, Any],
    modes: list[str],
    primary_k: int,
    quality_weights: dict[str, float],
) -> list[dict[str, Any]]:
    mode_summary = retrieval_eval.get("mode_summary") or {}
    rows: list[dict[str, Any]] = []

    for mode in modes:
        if mode not in mode_summary:
            continue

        p50 = get_latency(mode_summary, mode, "p50")
        p95 = get_latency(mode_summary, mode, "p95")
        composite = compute_quality_composite(
            mode_summary=mode_summary,
            mode=mode,
            primary_k=primary_k,
            weights=quality_weights,
        )

        quality_per_second = None
        if p50 is not None and p50 > 0:
            quality_per_second = round(composite / (p50 / 1000.0), 6)

        rows.append(
            {
                "mode": mode,
                f"hit_at_{primary_k}": get_metric(mode_summary, mode, "hit", primary_k),
                f"recall_at_{primary_k}": get_metric(mode_summary, mode, "recall", primary_k),
                f"mrr_at_{primary_k}": get_metric(mode_summary, mode, "mrr", primary_k),
                f"ndcg_at_{primary_k}": get_metric(mode_summary, mode, "ndcg", primary_k),
                "empty_result_rate": safe_float((mode_summary.get(mode) or {}).get("empty_result_rate"), 0.0),
                "latency_p50_ms": p50,
                "latency_p95_ms": p95,
                "quality_composite": composite,
                "quality_per_second_p50": quality_per_second,
            }
        )

    return rows


def rank_modes(mode_table: list[dict[str, Any]], primary_k: int) -> dict[str, list[dict[str, Any]]]:
    rankings: dict[str, list[dict[str, Any]]] = {}

    metrics = [
        f"hit_at_{primary_k}",
        f"recall_at_{primary_k}",
        f"mrr_at_{primary_k}",
        f"ndcg_at_{primary_k}",
        "quality_composite",
        "quality_per_second_p50",
    ]

    for metric in metrics:
        rows = [
            {"mode": row["mode"], "value": row.get(metric)}
            for row in mode_table
            if row.get(metric) is not None
        ]
        rows.sort(key=lambda x: safe_float(x["value"]), reverse=True)
        rankings[metric] = rows

    latency_rows = [
        {"mode": row["mode"], "value": row.get("latency_p50_ms")}
        for row in mode_table
        if row.get("latency_p50_ms") is not None
    ]
    latency_rows.sort(key=lambda x: safe_float(x["value"]))
    rankings["latency_p50_ms"] = latency_rows

    return rankings


def build_pareto_frontier(mode_table: list[dict[str, Any]]) -> list[dict[str, Any]]:
    frontier: list[dict[str, Any]] = []

    for row in mode_table:
        mode = row["mode"]
        quality = safe_float(row.get("quality_composite"))
        latency = row.get("latency_p50_ms")

        if latency is None:
            continue

        latency_f = safe_float(latency)
        dominated = False

        for other in mode_table:
            if other["mode"] == mode or other.get("latency_p50_ms") is None:
                continue

            other_quality = safe_float(other.get("quality_composite"))
            other_latency = safe_float(other.get("latency_p50_ms"))

            if (
                other_quality >= quality
                and other_latency <= latency_f
                and (other_quality > quality or other_latency < latency_f)
            ):
                dominated = True
                break

        if not dominated:
            frontier.append(
                {
                    "mode": mode,
                    "quality_composite": quality,
                    "latency_p50_ms": latency_f,
                    "quality_per_second_p50": row.get("quality_per_second_p50"),
                }
            )

    frontier.sort(key=lambda x: (-safe_float(x["quality_composite"]), safe_float(x["latency_p50_ms"])))
    return frontier


def build_pairwise_summary(
    *,
    mode_table: list[dict[str, Any]],
    pairs: list[dict[str, str]],
    primary_k: int,
) -> list[dict[str, Any]]:
    by_mode = {row["mode"]: row for row in mode_table}
    out: list[dict[str, Any]] = []

    metrics = [
        f"hit_at_{primary_k}",
        f"recall_at_{primary_k}",
        f"mrr_at_{primary_k}",
        f"ndcg_at_{primary_k}",
        "quality_composite",
    ]

    for pair in pairs:
        left = pair.get("left")
        right = pair.get("right")
        if not left or not right or left not in by_mode or right not in by_mode:
            continue

        item: dict[str, Any] = {
            "left": left,
            "right": right,
            "metrics": {},
        }

        for metric in metrics:
            left_value = safe_float(by_mode[left].get(metric))
            right_value = safe_float(by_mode[right].get(metric))
            delta = round(left_value - right_value, 6)
            item["metrics"][metric] = {
                "left": left_value,
                "right": right_value,
                "delta": delta,
                "winner": left if delta > 0 else right if delta < 0 else "tie",
            }

        left_latency = by_mode[left].get("latency_p50_ms")
        right_latency = by_mode[right].get("latency_p50_ms")
        if left_latency is not None and right_latency is not None:
            left_latency_f = safe_float(left_latency)
            right_latency_f = safe_float(right_latency)
            item["latency_p50_ms"] = {
                "left": left_latency_f,
                "right": right_latency_f,
                "delta": round(left_latency_f - right_latency_f, 3),
                "ratio": round(left_latency_f / right_latency_f, 3) if right_latency_f > 0 else None,
                "faster": left if left_latency_f < right_latency_f else right if right_latency_f < left_latency_f else "tie",
            }

        out.append(item)

    return out


def build_query_signal_summary(retrieval_eval: dict[str, Any]) -> dict[str, Any]:
    comparison = retrieval_eval.get("comparison_summary") or {}
    query_diagnostics = comparison.get("query_diagnostics") or []

    best_recall_counts: dict[str, int] = {}
    best_ndcg_counts: dict[str, int] = {}
    failed_mode_counts: dict[str, int] = {}
    note_counts: dict[str, int] = {}
    interesting_cases: list[dict[str, Any]] = []

    for item in query_diagnostics:
        best_recall = item.get("best_by_recall")
        best_ndcg = item.get("best_by_ndcg")
        if best_recall:
            best_recall_counts[best_recall] = best_recall_counts.get(best_recall, 0) + 1
        if best_ndcg:
            best_ndcg_counts[best_ndcg] = best_ndcg_counts.get(best_ndcg, 0) + 1

        for mode in item.get("failed_modes") or []:
            failed_mode_counts[mode] = failed_mode_counts.get(mode, 0) + 1

        for note in item.get("notes") or []:
            note_counts[note] = note_counts.get(note, 0) + 1

        if item.get("failed_modes") or item.get("notes"):
            interesting_cases.append(
                {
                    "query_id": item.get("query_id"),
                    "query": item.get("query"),
                    "best_by_recall": best_recall,
                    "best_by_ndcg": best_ndcg,
                    "failed_modes": item.get("failed_modes") or [],
                    "notes": item.get("notes") or [],
                }
            )

    return {
        "best_recall_counts": dict(sorted(best_recall_counts.items())),
        "best_ndcg_counts": dict(sorted(best_ndcg_counts.items())),
        "failed_mode_counts": dict(sorted(failed_mode_counts.items())),
        "note_counts": dict(sorted(note_counts.items())),
        "interesting_cases": interesting_cases,
    }



def build_group_mode_recommendations(
    *,
    retrieval_eval: dict[str, Any],
    primary_k: int,
) -> list[dict[str, Any]]:
    """Build lightweight group-level recommendations from retrieval_eval.group_summary.

    This is diagnostic only: it should guide inspection and future experiments,
    not silently change production defaults.
    """
    group_summary = retrieval_eval.get("group_summary") or {}
    out: list[dict[str, Any]] = []

    for group, row in sorted(group_summary.items()):
        modes = row.get("modes") or {}
        if not isinstance(modes, dict) or not modes:
            continue

        mode_rows: list[dict[str, Any]] = []
        for mode, metrics in modes.items():
            if not isinstance(metrics, dict):
                continue
            recall = safe_float(metrics.get(f"recall_at_{primary_k}"))
            ndcg = safe_float(metrics.get(f"ndcg_at_{primary_k}"))
            mrr = safe_float(metrics.get(f"mrr_at_{primary_k}"))
            composite = safe_float(
                metrics.get("quality_composite"),
                (0.4 * recall) + (0.4 * ndcg) + (0.2 * mrr),
            )
            mode_rows.append(
                {
                    "mode": mode,
                    f"recall_at_{primary_k}": round(recall, 6),
                    f"ndcg_at_{primary_k}": round(ndcg, 6),
                    f"mrr_at_{primary_k}": round(mrr, 6),
                    "quality_composite": round(composite, 6),
                }
            )

        if not mode_rows:
            continue

        by_composite = sorted(
            mode_rows,
            key=lambda item: (
                safe_float(item.get("quality_composite")),
                safe_float(item.get(f"recall_at_{primary_k}")),
                safe_float(item.get(f"ndcg_at_{primary_k}")),
            ),
            reverse=True,
        )
        by_recall = sorted(
            mode_rows,
            key=lambda item: (
                safe_float(item.get(f"recall_at_{primary_k}")),
                safe_float(item.get(f"ndcg_at_{primary_k}")),
                safe_float(item.get(f"mrr_at_{primary_k}")),
            ),
            reverse=True,
        )
        best = by_composite[0]
        best_recall = by_recall[0]

        dense = next((item for item in mode_rows if item["mode"] == "dense"), None)
        lexical = next((item for item in mode_rows if item["mode"] == "lexical"), None)
        hybrid = next((item for item in mode_rows if item["mode"] == "hybrid"), None)
        hybrid_ranked = next((item for item in mode_rows if item["mode"] == "hybrid_ranked"), None)

        notes: list[str] = []
        if dense and lexical and safe_float(dense.get(f"recall_at_{primary_k}")) > safe_float(lexical.get(f"recall_at_{primary_k}")):
            notes.append("dense_recall_gt_lexical")
        if lexical and dense and safe_float(lexical.get(f"recall_at_{primary_k}")) > safe_float(dense.get(f"recall_at_{primary_k}")):
            notes.append("lexical_recall_gt_dense")
        if hybrid and dense and safe_float(hybrid.get(f"recall_at_{primary_k}")) > safe_float(dense.get(f"recall_at_{primary_k}")):
            notes.append("hybrid_recall_gt_dense")
        if hybrid and lexical and safe_float(hybrid.get(f"recall_at_{primary_k}")) > safe_float(lexical.get(f"recall_at_{primary_k}")):
            notes.append("hybrid_recall_gt_lexical")
        if hybrid_ranked and hybrid:
            if safe_float(hybrid_ranked.get(f"recall_at_{primary_k}")) > safe_float(hybrid.get(f"recall_at_{primary_k}")):
                notes.append("hybrid_ranked_recall_gt_hybrid")
            if safe_float(hybrid_ranked.get(f"ndcg_at_{primary_k}")) < safe_float(hybrid.get(f"ndcg_at_{primary_k}")):
                notes.append("hybrid_ranked_ndcg_lt_hybrid")

        out.append(
            {
                "group": group,
                "cases_count": safe_int(row.get("cases_count")),
                "best_mode_by_composite": best["mode"],
                "best_mode_by_recall": best_recall["mode"],
                "best_composite": best.get("quality_composite"),
                f"best_recall_at_{primary_k}": best_recall.get(f"recall_at_{primary_k}"),
                "mode_metrics": mode_rows,
                "notes": notes,
            }
        )

    return out

def build_recommendations(
    *,
    rankings: dict[str, list[dict[str, Any]]],
    pareto_frontier: list[dict[str, Any]],
    query_signal_summary: dict[str, Any],
    primary_k: int,
) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []

    def top_mode(metric: str) -> str | None:
        rows = rankings.get(metric) or []
        return rows[0]["mode"] if rows else None

    best_recall = top_mode(f"recall_at_{primary_k}")
    best_ndcg = top_mode(f"ndcg_at_{primary_k}")
    fastest = top_mode("latency_p50_ms")
    best_tradeoff = top_mode("quality_per_second_p50")

    if fastest:
        recommendations.append(
            {
                "type": "serving_latency",
                "priority": "high",
                "message": (
                    f"`{fastest}` is the fastest mode by p50 latency. "
                    "Use it as the first baseline for latency-sensitive serving experiments."
                ),
            }
        )

    if best_recall:
        recommendations.append(
            {
                "type": "quality_recall",
                "priority": "high",
                "message": (
                    f"`{best_recall}` is the strongest mode by Recall@{primary_k}. "
                    "Use it as the target quality baseline for recall-oriented search."
                ),
            }
        )

    if best_ndcg and best_ndcg != best_recall:
        recommendations.append(
            {
                "type": "quality_ranking",
                "priority": "medium",
                "message": (
                    f"`{best_ndcg}` is the strongest mode by nDCG@{primary_k}. "
                    "Inspect whether ranking quality and recall are pulling in different directions."
                ),
            }
        )

    if best_tradeoff:
        recommendations.append(
            {
                "type": "quality_latency_tradeoff",
                "priority": "high",
                "message": (
                    f"`{best_tradeoff}` has the best quality-per-second tradeoff by p50 latency. "
                    "Use this as a practical baseline before introducing Qdrant/pgvector/rerankers."
                ),
            }
        )

    failed_modes = query_signal_summary.get("failed_mode_counts") or {}
    if failed_modes:
        recommendations.append(
            {
                "type": "failure_analysis",
                "priority": "high",
                "message": (
                    f"Some modes failed on labeled queries: {failed_modes}. "
                    "Keep failure cases as regression examples before tuning retrieval."
                ),
            }
        )

    notes = query_signal_summary.get("note_counts") or {}

    if notes.get("dense_recovers_lexical_failure", 0) > 0:
        recommendations.append(
            {
                "type": "dense_fallback",
                "priority": "high",
                "message": (
                    "Dense retrieval recovers at least one lexical failure. "
                    "Preserve dense retrieval as a required component of production-quality search."
                ),
            }
        )

    if notes.get("lexical_recall_gt_dense", 0) > 0:
        recommendations.append(
            {
                "type": "lexical_signal",
                "priority": "medium",
                "message": (
                    "Lexical retrieval beats dense on some labeled cases. "
                    "Do not replace lexical search blindly; keep hybrid/lexical signals in future experiments."
                ),
            }
        )

    if notes.get("hybrid_ranked_improves_recall", 0) > 0:
        recommendations.append(
            {
                "type": "ranking_layer",
                "priority": "medium",
                "message": (
                    "The ranking layer improves recall on at least one query. "
                    "Evaluate ranked vs unranked hybrid before changing ranking weights."
                ),
            }
        )

    if notes.get("hybrid_ranked_lowers_ndcg", 0) > 0:
        recommendations.append(
            {
                "type": "ranking_layer",
                "priority": "medium",
                "message": (
                    "The ranking layer lowers nDCG on some queries. "
                    "Inspect those cases before making ranked hybrid the default everywhere."
                ),
            }
        )

    if pareto_frontier:
        recommendations.append(
            {
                "type": "pareto_frontier",
                "priority": "medium",
                "message": (
                    "Pareto frontier modes: "
                    + ", ".join(f"`{item['mode']}`" for item in pareto_frontier)
                    + ". These are the best quality/latency candidates to carry forward."
                ),
            }
        )

    return recommendations


def build_markdown(report: dict[str, Any]) -> str:
    primary_k = report["config"]["primary_k"]

    lines: list[str] = []
    lines.append("# Search quality experiments v1")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at_utc']}`")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Input retrieval eval report: `{report['inputs']['retrieval_eval_report_path']}`")
    lines.append(f"- Retrieval build id: `{report['input_retrieval_eval']['build_id']}`")
    lines.append(f"- Corpus doc count: `{report['input_retrieval_eval']['corpus_doc_count']}`")
    lines.append(f"- Enabled eval cases: **{report['input_retrieval_eval']['enabled_cases_count']}**")
    lines.append(f"- Primary k: **{primary_k}**")
    lines.append("")

    lines.append("## Mode quality and latency table")
    lines.append("")
    lines.append("| Mode | Hit@K | Recall@K | MRR@K | nDCG@K | Quality composite | p50 ms | p95 ms | Quality/sec |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in report["mode_table"]:
        lines.append(
            f"| `{row['mode']}` | "
            f"{row.get(f'hit_at_{primary_k}', 0):.3f} | "
            f"{row.get(f'recall_at_{primary_k}', 0):.3f} | "
            f"{row.get(f'mrr_at_{primary_k}', 0):.3f} | "
            f"{row.get(f'ndcg_at_{primary_k}', 0):.3f} | "
            f"{row.get('quality_composite', 0):.3f} | "
            f"{row.get('latency_p50_ms')} | "
            f"{row.get('latency_p95_ms')} | "
            f"{row.get('quality_per_second_p50')} |"
        )
    lines.append("")

    lines.append("## Rankings")
    lines.append("")
    for ranking_name, rows in report["rankings"].items():
        lines.append(f"### `{ranking_name}`")
        for idx, row in enumerate(rows, start=1):
            lines.append(f"{idx}. `{row['mode']}` — {row['value']}")
        lines.append("")

    lines.append("## Pareto frontier")
    lines.append("")
    if report["pareto_frontier"]:
        lines.append("| Mode | Quality composite | p50 ms | Quality/sec |")
        lines.append("|---|---:|---:|---:|")
        for item in report["pareto_frontier"]:
            lines.append(
                f"| `{item['mode']}` | {item['quality_composite']:.3f} | "
                f"{item['latency_p50_ms']:.3f} | {item.get('quality_per_second_p50')} |"
            )
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Pairwise summary")
    lines.append("")
    if report["pairwise_summary"]:
        lines.append("| Pair | Metric | Left | Right | Delta | Winner |")
        lines.append("|---|---|---:|---:|---:|---|")
        for pair in report["pairwise_summary"]:
            pair_name = f"{pair['left']}_vs_{pair['right']}"
            for metric_name, metric_item in pair.get("metrics", {}).items():
                lines.append(
                    f"| `{pair_name}` | `{metric_name}` | "
                    f"{metric_item['left']:.3f} | {metric_item['right']:.3f} | "
                    f"{metric_item['delta']:+.3f} | `{metric_item['winner']}` |"
                )
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Query signal summary")
    lines.append("")
    q = report["query_signal_summary"]

    lines.append("### Best recall counts")
    if q.get("best_recall_counts"):
        for mode, count in q["best_recall_counts"].items():
            lines.append(f"- `{mode}`: **{count}**")
    else:
        lines.append("- none")
    lines.append("")

    lines.append("### Failed mode counts")
    if q.get("failed_mode_counts"):
        for mode, count in q["failed_mode_counts"].items():
            lines.append(f"- `{mode}`: **{count}**")
    else:
        lines.append("- none")
    lines.append("")

    lines.append("### Diagnostic note counts")
    if q.get("note_counts"):
        for note, count in q["note_counts"].items():
            lines.append(f"- `{note}`: **{count}**")
    else:
        lines.append("- none")
    lines.append("")

    lines.append("### Interesting cases")
    if q.get("interesting_cases"):
        lines.append("| Query | Best recall | Best nDCG | Failed modes | Notes |")
        lines.append("|---|---|---|---|---|")
        for item in q["interesting_cases"]:
            failed = ", ".join(f"`{x}`" for x in item.get("failed_modes", [])) or "-"
            notes = ", ".join(f"`{x}`" for x in item.get("notes", [])) or "-"
            lines.append(
                f"| `{item.get('query_id')}` | `{item.get('best_by_recall')}` | "
                f"`{item.get('best_by_ndcg')}` | {failed} | {notes} |"
            )
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Group-level mode recommendations")
    lines.append("")
    group_recs = report.get("group_mode_recommendations") or []
    if group_recs:
        lines.append(
            "| Group | Cases | Best composite | Best recall | Composite | Recall@K | Notes |"
        )
        lines.append("|---|---:|---|---|---:|---:|---|")
        for item in group_recs:
            notes = ", ".join(f"`{x}`" for x in item.get("notes", [])) or "-"
            lines.append(
                f"| `{item.get('group')}` | {item.get('cases_count', 0)} | "
                f"`{item.get('best_mode_by_composite')}` | "
                f"`{item.get('best_mode_by_recall')}` | "
                f"{safe_float(item.get('best_composite')):.3f} | "
                f"{safe_float(item.get(f'best_recall_at_{primary_k}')):.3f} | "
                f"{notes} |"
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
            "Build search quality experiment diagnostics from the latest retrieval eval report. "
            "This script does not run retrieval; it analyzes retrieval_eval_latest.json."
        )
    )
    parser.add_argument("--config-path", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--retrieval-eval-report-path", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_ts = utc_now_ts()

    config = load_yaml(args.config_path)
    if config.get("schema_version") != "search_quality_experiments_v1":
        raise ValueError(f"Unsupported schema_version: {config.get('schema_version')!r}")

    paths = config.get("paths") or {}
    analysis = config.get("analysis") or {}

    retrieval_eval_path = args.retrieval_eval_report_path or Path(
        paths.get("retrieval_eval_report_path", "artifacts/reports/evaluation/retrieval_eval_latest.json")
    )
    output_dir = args.output_dir or Path(paths.get("output_dir", DEFAULT_OUTPUT_DIR))

    retrieval_eval = load_json(retrieval_eval_path)
    if retrieval_eval.get("schema_version") != "retrieval_eval_v1":
        raise ValueError(
            f"Input report must be retrieval_eval_v1, got {retrieval_eval.get('schema_version')!r}"
        )

    primary_k = safe_int(
        analysis.get("primary_k"),
        safe_int((retrieval_eval.get("config") or {}).get("primary_k"), 10),
    )
    modes = [str(x) for x in analysis.get("modes") or (retrieval_eval.get("config") or {}).get("modes") or []]
    if not modes:
        modes = sorted((retrieval_eval.get("mode_summary") or {}).keys())

    quality_weights = analysis.get("quality_composite_weights") or {
        "recall": 0.4,
        "ndcg": 0.4,
        "mrr": 0.2,
    }

    comparison_pairs = analysis.get("comparison_pairs") or [
        {"left": "hybrid", "right": "lexical"},
        {"left": "hybrid", "right": "dense"},
        {"left": "hybrid_ranked", "right": "hybrid"},
        {"left": "dense", "right": "lexical"},
    ]

    mode_table = build_mode_table(
        retrieval_eval=retrieval_eval,
        modes=modes,
        primary_k=primary_k,
        quality_weights=quality_weights,
    )
    rankings = rank_modes(mode_table, primary_k)
    pareto_frontier = build_pareto_frontier(mode_table)
    pairwise_summary = build_pairwise_summary(
        mode_table=mode_table,
        pairs=comparison_pairs,
        primary_k=primary_k,
    )
    query_signal_summary = build_query_signal_summary(retrieval_eval)
    group_mode_recommendations = build_group_mode_recommendations(
        retrieval_eval=retrieval_eval,
        primary_k=primary_k,
    )
    recommendations = build_recommendations(
        rankings=rankings,
        pareto_frontier=pareto_frontier,
        query_signal_summary=query_signal_summary,
        primary_k=primary_k,
    )

    runtime = retrieval_eval.get("runtime") or {}
    summary = retrieval_eval.get("summary") or {}

    report = {
        "schema_version": "search_quality_experiments_v1",
        "report_name": "search_quality_experiments",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "inputs": {
            "config_path": normalize_path(args.config_path),
            "retrieval_eval_report_path": normalize_path(retrieval_eval_path),
        },
        "config": {
            "primary_k": primary_k,
            "modes": modes,
            "quality_composite_weights": quality_weights,
            "comparison_pairs": comparison_pairs,
        },
        "input_retrieval_eval": {
            "schema_version": retrieval_eval.get("schema_version"),
            "run_ts": retrieval_eval.get("run_ts"),
            "backend_mode": runtime.get("backend_mode"),
            "build_id": runtime.get("build_id"),
            "corpus_doc_count": runtime.get("corpus_doc_count"),
            "embedding_model_name": runtime.get("embedding_model_name"),
            "enabled_cases_count": summary.get("enabled_cases_count"),
            "executed_cases_count": summary.get("executed_cases_count"),
        },
        "mode_table": mode_table,
        "rankings": rankings,
        "pareto_frontier": pareto_frontier,
        "pairwise_summary": pairwise_summary,
        "query_signal_summary": query_signal_summary,
        "group_mode_recommendations": group_mode_recommendations,
        "recommendations": recommendations,
    }

    latest_json = output_dir / "search_quality_experiments_latest.json"
    latest_md = output_dir / "search_quality_experiments_latest.md"
    hist_json = output_dir / "history" / f"search_quality_experiments_{run_ts}.json"
    hist_md = output_dir / "history" / f"search_quality_experiments_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(hist_json, report)
    dump_text(hist_md, build_markdown(report))

    print(f"[OK] schema_version={report['schema_version']}")
    print(f"[OK] input_retrieval_eval_schema={report['input_retrieval_eval']['schema_version']}")
    print(f"[OK] build_id={report['input_retrieval_eval']['build_id']}")
    print(f"[OK] corpus_doc_count={report['input_retrieval_eval']['corpus_doc_count']}")
    print(f"[OK] modes_count={len(mode_table)}")
    print(f"[OK] pareto_frontier_count={len(pareto_frontier)}")
    print(f"[OK] group_mode_recommendations_count={len(group_mode_recommendations)}")
    print(f"[OK] recommendations_count={len(recommendations)}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {hist_json}")
    print(f"[OK] history Markdown: {hist_md}")


if __name__ == "__main__":
    main()
