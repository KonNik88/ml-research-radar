from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("PyYAML is required for golden labeling config loading.") from exc

from scripts.evaluation.run_retrieval_eval import (
    build_runtime,
    compact_result,
    dump_json,
    dump_text,
    normalize_path,
    run_one_search,
)


DEFAULT_CONFIG_PATH = Path("configs/golden_labeling_v1.yaml")
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/evaluation")


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Golden labeling config not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Golden labeling config must be a YAML mapping: {path}")
    return payload


def canonical_id_from_compact(item: dict[str, Any]) -> str:
    return str(item.get("canonical_id") or "").strip()


def result_score_summary(item: dict[str, Any]) -> dict[str, Any]:
    retrieval = item.get("retrieval") if isinstance(item.get("retrieval"), dict) else {}
    ranking = item.get("ranking") if isinstance(item.get("ranking"), dict) else {}

    out: dict[str, Any] = {}

    for key in (
        "score",
        "lexical_score",
        "dense_score",
        "hybrid_score",
    ):
        if retrieval.get(key) is not None:
            out[key] = retrieval.get(key)

    for key in (
        "final_score",
        "retrieval_score",
        "recency_score",
        "source_support_score",
        "metadata_quality_score",
    ):
        if ranking.get(key) is not None:
            out[key] = ranking.get(key)

    return out


def flatten_queries(config: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    seen: set[str] = set()

    for item in config.get("queries") or []:
        if not isinstance(item, dict):
            continue
        if not item.get("enabled", True):
            continue

        query_id = str(item.get("query_id") or "").strip()
        query = str(item.get("query") or "").strip()

        if not query_id or not query:
            continue
        if query_id in seen:
            raise ValueError(f"Duplicate query_id in golden labeling config: {query_id}")
        seen.add(query_id)

        rows.append(
            {
                "query_id": query_id,
                "group": str(item.get("group") or "ungrouped"),
                "query": query,
                "intent": item.get("intent"),
                "expected_terms": item.get("expected_terms") or {},
            }
        )

    if not rows:
        raise RuntimeError("No enabled queries found in golden labeling config")

    return rows


def build_template_row(query: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    expected_terms = query.get("expected_terms") or {}

    return {
        "query_id": query["query_id"],
        "enabled": False,
        "group": query.get("group") or "ungrouped",
        "query": query["query"],
        "intent": query.get("intent"),
        "expected": {
            "canonical_ids": [],
            "strict_canonical_relevance": True,
            "title_substrings": expected_terms.get("title_substrings") or [],
            "must_have_any_terms": expected_terms.get("must_have_any_terms") or [],
        },
        "graded_relevance": [
            {
                "canonical_id": candidate["canonical_id"],
                "grade": None,
                "note": "TODO: set grade 3/2/1 or remove this candidate",
            }
            for candidate in candidates[:10]
        ],
    }


def sort_candidates(candidates: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = list(candidates.values())
    rows.sort(
        key=lambda x: (
            int(x.get("best_rank") or 10**9),
            -int(x.get("modes_count") or 0),
            str(x.get("title") or ""),
        )
    )
    return rows


def run_query(
    *,
    runtime: Any,
    query: dict[str, Any],
    modes: list[str],
    top_k: int,
    max_candidates: int,
) -> dict[str, Any]:
    candidate_map: dict[str, dict[str, Any]] = {}
    mode_runs: list[dict[str, Any]] = []

    for mode in modes:
        try:
            payload = run_one_search(
                runtime,
                query=query["query"],
                mode_label=mode,
                top_k=top_k,
            )
            raw_results = payload.get("results") or []
            compact_results = [compact_result(item) for item in raw_results]

            mode_runs.append(
                {
                    "mode": mode,
                    "effective_mode": payload.get("effective_mode"),
                    "rank": payload.get("rank"),
                    "results_count": len(compact_results),
                    "timing_ms_wall": payload.get("timing_ms_wall"),
                    "error": None,
                }
            )

            for rank, item in enumerate(compact_results, start=1):
                canonical_id = canonical_id_from_compact(item)
                if not canonical_id:
                    continue

                row = candidate_map.setdefault(
                    canonical_id,
                    {
                        "canonical_id": canonical_id,
                        "title": item.get("title"),
                        "year": item.get("year"),
                        "source_count": item.get("source_count"),
                        "best_rank": rank,
                        "modes_count": 0,
                        "modes": {},
                    },
                )

                row["best_rank"] = min(int(row.get("best_rank") or rank), rank)
                row["modes"][mode] = {
                    "rank": rank,
                    "scores": result_score_summary(item),
                }
                row["modes_count"] = len(row["modes"])

        except Exception as exc:
            mode_runs.append(
                {
                    "mode": mode,
                    "effective_mode": None,
                    "rank": None,
                    "results_count": 0,
                    "timing_ms_wall": None,
                    "error": repr(exc),
                }
            )

    candidates = sort_candidates(candidate_map)
    candidates = candidates[:max_candidates]

    return {
        "query_id": query["query_id"],
        "group": query.get("group"),
        "query": query["query"],
        "intent": query.get("intent"),
        "expected_terms": query.get("expected_terms") or {},
        "modes": mode_runs,
        "candidates_count": len(candidates),
        "candidates": candidates,
        "jsonl_template": build_template_row(query, candidates),
    }


def json_dumps_inline(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []

    lines.append("# Golden labeling candidates v1")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at_utc']}`")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Backend mode: `{report['runtime'].get('backend_mode')}`")
    lines.append(f"- Build id: `{report['runtime'].get('build_id')}`")
    lines.append(f"- Corpus doc count: `{report['runtime'].get('corpus_doc_count')}`")
    lines.append(f"- Enabled queries: **{report['summary']['enabled_queries_count']}**")
    lines.append(f"- Modes: `{', '.join(report['config']['modes'])}`")
    lines.append(f"- Top-k per mode: **{report['config']['top_k']}**")
    lines.append("")

    lines.append("## How to use this report")
    lines.append("")
    lines.append("For each query, inspect the candidate table and choose canonical IDs that are truly relevant.")
    lines.append("")
    lines.append("Suggested grading:")
    lines.append("")
    lines.append("- `3` = direct/highly relevant")
    lines.append("- `2` = relevant but broader or secondary")
    lines.append("- `1` = weakly relevant")
    lines.append("- remove candidate = not relevant")
    lines.append("")
    lines.append("After manual review, copy the edited JSONL template into `data/eval/retrieval/golden_queries.jsonl` and set `enabled=true`.")
    lines.append("")

    for query_block in report.get("queries", []):
        lines.append(f"## `{query_block['query_id']}`")
        lines.append("")
        lines.append(f"- Group: `{query_block.get('group')}`")
        lines.append(f"- Query: `{query_block.get('query')}`")
        lines.append(f"- Intent: {query_block.get('intent') or '-'}")
        lines.append(f"- Candidates: **{query_block.get('candidates_count')}**")
        lines.append("")

        lines.append("### Mode runs")
        lines.append("")
        lines.append("| Mode | Effective | Rank | Results | Wall ms | Error |")
        lines.append("|---|---|---:|---:|---:|---|")
        for mode_run in query_block.get("modes", []):
            lines.append(
                f"| `{mode_run.get('mode')}` | `{mode_run.get('effective_mode')}` | "
                f"{mode_run.get('rank')} | {mode_run.get('results_count')} | "
                f"{mode_run.get('timing_ms_wall')} | {mode_run.get('error') or '-'} |"
            )
        lines.append("")

        lines.append("### Candidate pool")
        lines.append("")
        lines.append("| # | canonical_id | Title | Year | Best rank | Modes |")
        lines.append("|---:|---|---|---:|---:|---|")

        for idx, candidate in enumerate(query_block.get("candidates", []), start=1):
            title = str(candidate.get("title") or "").replace("|", "\\|")
            modes = []
            for mode, mode_payload in (candidate.get("modes") or {}).items():
                modes.append(f"{mode}:#{mode_payload.get('rank')}")
            lines.append(
                f"| {idx} | `{candidate.get('canonical_id')}` | {title} | "
                f"{candidate.get('year') if candidate.get('year') is not None else '-'} | "
                f"{candidate.get('best_rank')} | {', '.join(modes)} |"
            )
        lines.append("")

        lines.append("### JSONL template")
        lines.append("")
        lines.append("```json")
        lines.append(json_dumps_inline(query_block.get("jsonl_template") or {}))
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export candidate papers for manual golden query labeling."
    )
    parser.add_argument("--config-path", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--backend-mode", choices=["file"], default=None)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = load_yaml(args.config_path)

    if config.get("schema_version") != "golden_labeling_v1":
        raise ValueError(f"Unsupported schema_version: {config.get('schema_version')!r}")

    defaults = config.get("defaults") or {}
    paths = config.get("paths") or {}

    backend_mode = args.backend_mode or defaults.get("backend_mode") or "file"
    modes = [str(x) for x in defaults.get("modes") or ["lexical", "dense", "hybrid", "hybrid_ranked"]]
    top_k = int(defaults.get("top_k") or 20)
    max_candidates = int(defaults.get("max_candidates_per_query") or 30)
    output_dir = args.output_dir or Path(paths.get("output_dir", DEFAULT_OUTPUT_DIR))

    queries = flatten_queries(config)

    runtime = build_runtime(backend_mode)
    snapshot = runtime.runtime_snapshot()

    run_ts = utc_now_ts()

    query_reports = [
        run_query(
            runtime=runtime,
            query=query,
            modes=modes,
            top_k=top_k,
            max_candidates=max_candidates,
        )
        for query in queries
    ]

    report = {
        "schema_version": "golden_labeling_v1",
        "report_name": "golden_labeling_candidates",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "inputs": {
            "config_path": normalize_path(args.config_path),
        },
        "config": {
            "backend_mode": backend_mode,
            "modes": modes,
            "top_k": top_k,
            "max_candidates_per_query": max_candidates,
        },
        "runtime": {
            "backend_mode": snapshot.get("backend_mode"),
            "ready": snapshot.get("ready"),
            "build_id": snapshot.get("build_id"),
            "corpus_doc_count": snapshot.get("corpus_doc_count"),
            "embedding_model_name": snapshot.get("embedding_model_name"),
        },
        "summary": {
            "enabled_queries_count": len(queries),
            "queries_with_candidates_count": sum(1 for row in query_reports if row.get("candidates_count", 0) > 0),
            "total_candidates_count": sum(int(row.get("candidates_count") or 0) for row in query_reports),
            "modes_count": len(modes),
            "mode_error_count": sum(
                1
                for row in query_reports
                for mode in row.get("modes", [])
                if mode.get("error")
            ),
        },
        "queries": query_reports,
    }

    latest_json = output_dir / "golden_labeling_candidates_latest.json"
    latest_md = output_dir / "golden_labeling_candidates_latest.md"
    hist_json = output_dir / "history" / f"golden_labeling_candidates_{run_ts}.json"
    hist_md = output_dir / "history" / f"golden_labeling_candidates_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(hist_json, report)
    dump_text(hist_md, build_markdown(report))

    print(f"[OK] schema_version={report['schema_version']}")
    print(f"[OK] backend_mode={snapshot.get('backend_mode')}")
    print(f"[OK] build_id={snapshot.get('build_id')}")
    print(f"[OK] corpus_doc_count={snapshot.get('corpus_doc_count')}")
    print(f"[OK] enabled_queries_count={len(queries)}")
    print(f"[OK] total_candidates_count={report['summary']['total_candidates_count']}")
    print(f"[OK] mode_error_count={report['summary']['mode_error_count']}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {hist_json}")
    print(f"[OK] history Markdown: {hist_md}")


if __name__ == "__main__":
    main()
