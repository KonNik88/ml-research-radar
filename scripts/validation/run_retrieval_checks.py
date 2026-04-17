from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from services.api.runtime import get_runtime
from services.api.search_service import run_search
from services.api.settings import get_settings

DEFAULT_QUERIES_CONFIG = Path("configs/validation_queries.yaml")
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/validation")


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Queries config not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        payload = yaml.safe_load(f) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Expected mapping in YAML config: {path}")
    return payload


def flatten_queries(payload: dict[str, Any]) -> list[dict[str, str]]:
    query_groups = payload.get("query_groups") or {}
    if not isinstance(query_groups, dict):
        raise ValueError("validation_queries.yaml must contain mapping key 'query_groups'")

    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for group_name, values in query_groups.items():
        if not isinstance(values, list):
            raise ValueError(f"Group '{group_name}' must be a list of strings")
        for query in values:
            if not isinstance(query, str) or not query.strip():
                continue
            normalized = " ".join(query.split())
            key = (str(group_name), normalized)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "group": str(group_name),
                    "query": normalized,
                }
            )

    if not rows:
        raise RuntimeError("No queries found in validation config")

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
    payload = response.model_dump()
    payload["meta"] = to_plain(payload.get("meta"))
    payload["results"] = [to_plain(item) for item in payload.get("results", [])]
    return payload


def build_runtime(backend_mode: str = "file"):
    os.environ["ML_RADAR_SEARCH_BACKEND"] = backend_mode
    get_settings.cache_clear()
    runtime = get_runtime()
    runtime.load()
    snapshot = runtime.runtime_snapshot()

    if not snapshot["ready"]:
        raise RuntimeError(
            f"Runtime not ready. backend={snapshot['backend_mode']}, "
            f"last_load_error={snapshot.get('last_load_error')}"
        )

    return runtime


def run_one_search(
    runtime: Any,
    *,
    query: str,
    mode: str,
    top_k: int,
    rank: bool,
) -> dict[str, Any]:
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
    payload["effective_mode_label"] = f"{mode}{'_ranked' if rank else ''}"
    payload["timing_ms_wall"] = elapsed_ms
    return payload


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []

    lines.append("# Retrieval validation report")
    lines.append("")
    lines.append(f"- Generated at: {report['generated_at_utc']}")
    lines.append(f"- Backend mode: `{report['backend_mode']}`")
    lines.append(f"- Build id: `{report['build_id']}`")
    lines.append(f"- Corpus doc count: **{report['corpus_doc_count']}**")
    lines.append(f"- Queries count: **{report['queries_count']}**")
    lines.append(f"- Top-k: **{report['top_k']}**")
    lines.append("")

    lines.append("## Query groups")
    for group_name, count in report["group_counts"].items():
        lines.append(f"- {group_name}: {count}")
    lines.append("")

    for query_block in report["query_runs"]:
        lines.append(f"## Query: `{query_block['query']}`")
        lines.append(f"- Group: `{query_block['group']}`")
        lines.append("")

        for run in query_block["runs"]:
            lines.append(f"### Mode: `{run['effective_mode_label']}`")
            lines.append(f"- Returned: {len(run.get('results', []))}")
            lines.append(f"- Wall time ms: {run['timing_ms_wall']}")

            meta = run.get("meta") or {}
            timing = meta.get("timing_ms") or {}
            if timing:
                lines.append(f"- Service timing: `{timing}`")
            lines.append("")

            results = run.get("results", [])
            if not results:
                lines.append("- No results")
                lines.append("")
                continue

            lines.append("| Rank | Title | Year | Source count | Retrieval | Final rank |")
            lines.append("|---|---|---:|---:|---:|---:|")

            for idx, item in enumerate(results, start=1):
                doc = item.get("document") or {}
                retrieval = item.get("retrieval") or {}
                ranking = item.get("ranking") or {}

                title = (doc.get("title") or "").replace("|", "\\|")
                year = doc.get("year")
                source_count = doc.get("source_count", 0)

                retrieval_score = (
                    retrieval.get("hybrid_score")
                    if retrieval.get("hybrid_score") is not None
                    else retrieval.get("lexical_score")
                    if retrieval.get("lexical_score") is not None
                    else retrieval.get("dense_score")
                    if retrieval.get("dense_score") is not None
                    else retrieval.get("score")
                )

                final_score = ranking.get("final_score")

                retrieval_text = "-" if retrieval_score is None else f"{retrieval_score:.4f}"
                final_text = "-" if final_score is None else f"{final_score:.4f}"

                lines.append(
                    f"| {idx} | {title} | {year if year is not None else '-'} | "
                    f"{source_count} | {retrieval_text} | {final_text} |"
                )

            lines.append("")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run practical retrieval validation checks on a curated query set."
    )
    parser.add_argument(
        "--queries-config",
        type=Path,
        default=DEFAULT_QUERIES_CONFIG,
        help="Path to YAML file with validation queries.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory to store latest and historical validation reports.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Number of top results to keep for each query/mode.",
    )
    parser.add_argument(
        "--backend-mode",
        choices=["file", "db"],
        default="file",
        help="Backend mode for validation run. For retrieval validation use file.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    payload = load_yaml(args.queries_config)
    query_rows = flatten_queries(payload)

    runtime = build_runtime(backend_mode=args.backend_mode)
    snapshot = runtime.runtime_snapshot()

    run_ts = utc_now_ts()

    query_runs: list[dict[str, Any]] = []
    group_counts: dict[str, int] = {}

    for row in query_rows:
        group = row["group"]
        query = row["query"]
        group_counts[group] = group_counts.get(group, 0) + 1

        runs = [
            run_one_search(runtime, query=query, mode="lexical", top_k=args.top_k, rank=False),
            run_one_search(runtime, query=query, mode="dense", top_k=args.top_k, rank=False),
            run_one_search(runtime, query=query, mode="hybrid", top_k=args.top_k, rank=False),
            run_one_search(runtime, query=query, mode="hybrid", top_k=args.top_k, rank=True),
        ]

        query_runs.append(
            {
                "group": group,
                "query": query,
                "runs": runs,
            }
        )

    report = {
        "report_name": "retrieval_checks",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "backend_mode": snapshot["backend_mode"],
        "build_id": snapshot["build_id"],
        "corpus_doc_count": snapshot["corpus_doc_count"],
        "embedding_model_name": snapshot["embedding_model_name"],
        "queries_config": str(args.queries_config).replace("\\", "/"),
        "queries_count": len(query_rows),
        "group_counts": group_counts,
        "top_k": args.top_k,
        "query_runs": query_runs,
    }

    output_dir: Path = args.output_dir
    latest_json = output_dir / "retrieval_checks_latest.json"
    latest_md = output_dir / "retrieval_checks_latest.md"
    hist_json = output_dir / "history" / f"retrieval_checks_{run_ts}.json"
    hist_md = output_dir / "history" / f"retrieval_checks_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(hist_json, report)
    dump_text(hist_md, build_markdown(report))

    print(f"[OK] backend_mode={snapshot['backend_mode']}")
    print(f"[OK] build_id={snapshot['build_id']}")
    print(f"[OK] corpus_doc_count={snapshot['corpus_doc_count']}")
    print(f"[OK] queries_count={len(query_rows)}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {hist_json}")
    print(f"[OK] history Markdown: {hist_md}")


if __name__ == "__main__":
    main()