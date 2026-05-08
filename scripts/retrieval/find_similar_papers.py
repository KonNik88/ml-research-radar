from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from radar_core.retrieval.similar import (
    DEFAULT_CANONICAL_PATH,
    DEFAULT_DENSE_DIR,
    DEFAULT_FEATURES_PATH,
    DEFAULT_RETRIEVAL_MANIFEST_PATH,
    find_similar_papers,
    normalize_path,
)


DEFAULT_REPORTS_DIR = Path("artifacts/reports/retrieval")
DEFAULT_RANKING_REPORT_PATH = Path("artifacts/reports/ranking/demo_radar_ranking_latest.json")
DEFAULT_DETAIL_REPORT_PATH = Path("artifacts/reports/details/paper_detail_latest.json")


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


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_canonical_id_from_latest_ranking(*, rank: int, ranking_report_path: Path) -> str:
    if rank <= 0:
        raise ValueError("--from-latest-ranking-rank must be > 0")

    report = load_json(ranking_report_path)
    results = report.get("results") or []

    if rank > len(results):
        raise ValueError(
            f"Ranking report has only {len(results)} result(s), cannot resolve rank={rank}"
        )

    canonical_id = results[rank - 1].get("canonical_id")
    if not canonical_id:
        raise ValueError(f"Ranking result rank={rank} has no canonical_id")

    return str(canonical_id)


def resolve_canonical_id_from_latest_detail(*, detail_report_path: Path) -> str:
    report = load_json(detail_report_path)
    canonical_id = report.get("canonical_id") or (report.get("detail") or {}).get("canonical_id")

    if not canonical_id:
        raise ValueError(f"Detail report has no canonical_id: {detail_report_path}")

    return str(canonical_id)


def fmt_score(value: Any) -> str:
    try:
        return f"{float(value):.4f}"
    except Exception:
        return "NA"


def truncate(value: Any, width: int) -> str:
    text = str(value or "")
    if len(text) <= width:
        return text
    return text[: max(0, width - 1)] + "…"


def markdown_escape(value: Any) -> str:
    text = str(value or "")
    return text.replace("|", "\\|")


def hf_artifact_count(row: dict[str, Any]) -> int:
    return int(row.get("hf_model_count") or 0) + int(row.get("hf_dataset_count") or 0) + int(
        row.get("hf_space_count") or 0
    )


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Similar papers report")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at_utc']}`")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Target canonical ID: `{report['target_canonical_id']}`")
    lines.append(f"- Target found: `{report['target_found']}`")
    lines.append(f"- Rank by: `{report['rank_by']}`")
    lines.append(f"- Top K: `{report['top_k']}`")
    lines.append(f"- Input rows: `{report['input_rows_count']}`")
    lines.append(f"- Returned rows: `{report['returned_rows_count']}`")
    lines.append("")

    target = report.get("target") or {}
    lines.append("## Target")
    lines.append("")
    lines.append(f"- Title: `{target.get('title')}`")
    lines.append(f"- Year: `{target.get('year')}`")
    lines.append(f"- Radar score: `{fmt_score(target.get('radar_score'))}`")
    lines.append(
        f"- Implementation readiness: `{fmt_score(target.get('implementation_readiness_score'))}`"
    )
    lines.append(f"- Source families: `{target.get('source_families')}`")
    lines.append("")

    lines.append("## Dense artifacts")
    dense = report.get("dense_artifacts") or {}
    for key, value in dense.items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Results")
    results = report.get("results") or []

    if not results:
        lines.append("_No similar papers found._")
        lines.append("")
        return "\n".join(lines)

    lines.append(
        "| rank | year | sim | adjusted | radar | impl | art | gh | hf_art | title | canonical_id |"
    )
    lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|")

    for rank, row in enumerate(results, start=1):
        lines.append(
            "| "
            f"{rank} | "
            f"{row.get('year')} | "
            f"{fmt_score(row.get('semantic_similarity'))} | "
            f"{fmt_score(row.get('radar_adjusted_similarity'))} | "
            f"{fmt_score(row.get('radar_score'))} | "
            f"{fmt_score(row.get('implementation_readiness_score'))} | "
            f"{row.get('trusted_artifact_links_count')} | "
            f"{row.get('github_found_repo_count')} | "
            f"{hf_artifact_count(row)} | "
            f"{markdown_escape(truncate(row.get('title'), 80))} | "
            f"`{row.get('canonical_id')}` |"
        )

    lines.append("")
    return "\n".join(lines)


def print_console(report: dict[str, Any]) -> None:
    print(f"[OK] mode={report.get('mode')}")
    print(f"[OK] target_canonical_id={report.get('target_canonical_id')}")
    print(f"[OK] target_found={report.get('target_found')}")
    print(f"[OK] rank_by={report.get('rank_by')}")
    print(f"[OK] top_k={report.get('top_k')}")
    print(f"[OK] input_rows_count={report.get('input_rows_count')}")
    print(f"[OK] returned_rows_count={report.get('returned_rows_count')}")

    dense = report.get("dense_artifacts") or {}
    print(f"[OK] embedding_path={dense.get('embedding_path')}")
    print(f"[OK] ids_path={dense.get('ids_path')}")
    print(f"[OK] meta_path={dense.get('meta_path')}")
    print(f"[OK] embedding_shape={dense.get('embedding_shape')}")

    target = report.get("target") or {}
    print(f"[OK] target_title={target.get('title')}")
    print(f"[OK] target_year={target.get('year')}")

    results = report.get("results") or []
    if not results:
        print("[WARN] no results")
        return

    print("")
    print("rank | year | sim    | adjusted | radar  | impl   | art | gh | hf_art | title")
    print("-" * 132)

    for rank, row in enumerate(results, start=1):
        print(
            f"{rank:>4} | "
            f"{str(row.get('year')):>4} | "
            f"{fmt_score(row.get('semantic_similarity')):>6} | "
            f"{fmt_score(row.get('radar_adjusted_similarity')):>8} | "
            f"{fmt_score(row.get('radar_score')):>6} | "
            f"{fmt_score(row.get('implementation_readiness_score')):>6} | "
            f"{str(row.get('trusted_artifact_links_count')):>3} | "
            f"{str(row.get('github_found_repo_count')):>2} | "
            f"{str(hf_artifact_count(row)):>6} | "
            f"{truncate(row.get('title'), 72)}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Find semantically similar papers using dense retrieval embeddings."
    )

    parser.add_argument("--canonical-id", type=str, default=None)
    parser.add_argument("--from-latest-detail", action="store_true")
    parser.add_argument("--from-latest-ranking-rank", type=int, default=None)

    parser.add_argument("--ranking-report-path", type=Path, default=DEFAULT_RANKING_REPORT_PATH)
    parser.add_argument("--detail-report-path", type=Path, default=DEFAULT_DETAIL_REPORT_PATH)

    parser.add_argument("--dense-dir", type=Path, default=DEFAULT_DENSE_DIR)
    parser.add_argument("--manifest-path", type=Path, default=DEFAULT_RETRIEVAL_MANIFEST_PATH)
    parser.add_argument("--embedding-path", type=Path, default=None)
    parser.add_argument("--ids-path", type=Path, default=None)
    parser.add_argument("--meta-path", type=Path, default=None)
    parser.add_argument("--features-path", type=Path, default=DEFAULT_FEATURES_PATH)
    parser.add_argument("--canonical-path", type=Path, default=DEFAULT_CANONICAL_PATH)

    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument(
        "--rank-by",
        choices=["semantic", "radar_adjusted"],
        default="semantic",
    )
    parser.add_argument("--min-similarity", type=float, default=None)

    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)

    return parser


def resolve_target_canonical_id(args: argparse.Namespace) -> str:
    modes = [
        bool(args.canonical_id),
        bool(args.from_latest_detail),
        bool(args.from_latest_ranking_rank),
    ]

    if sum(1 for x in modes if x) != 1:
        raise SystemExit(
            "Use exactly one of: --canonical-id, --from-latest-detail, --from-latest-ranking-rank."
        )

    if args.canonical_id:
        return str(args.canonical_id)

    if args.from_latest_detail:
        return resolve_canonical_id_from_latest_detail(
            detail_report_path=args.detail_report_path,
        )

    return resolve_canonical_id_from_latest_ranking(
        rank=int(args.from_latest_ranking_rank),
        ranking_report_path=args.ranking_report_path,
    )


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    canonical_id = resolve_target_canonical_id(args)

    similar_report = find_similar_papers(
        canonical_id=canonical_id,
        dense_dir=args.dense_dir,
        manifest_path=args.manifest_path,
        embedding_path=args.embedding_path,
        ids_path=args.ids_path,
        meta_path=args.meta_path,
        features_path=args.features_path,
        canonical_path=args.canonical_path,
        top_k=args.top_k,
        rank_by=args.rank_by,
        min_similarity=args.min_similarity,
    )

    report = {
        "report_name": "similar_papers",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "inputs": {
            "canonical_id": canonical_id,
            "from_latest_detail": bool(args.from_latest_detail),
            "from_latest_ranking_rank": args.from_latest_ranking_rank,
            "ranking_report_path": normalize_path(args.ranking_report_path),
            "detail_report_path": normalize_path(args.detail_report_path),
            "dense_dir": normalize_path(args.dense_dir),
            "manifest_path": normalize_path(args.manifest_path),
            "embedding_path_requested": normalize_path(args.embedding_path),
            "ids_path_requested": normalize_path(args.ids_path),
            "meta_path_requested": normalize_path(args.meta_path),
            "features_path": normalize_path(args.features_path),
            "canonical_path": normalize_path(args.canonical_path),
            "reports_dir": normalize_path(args.reports_dir),
        },
        **similar_report,
    }

    latest_json = args.reports_dir / "similar_papers_latest.json"
    latest_md = args.reports_dir / "similar_papers_latest.md"
    history_json = args.reports_dir / "history" / f"similar_papers_{run_ts}.json"
    history_md = args.reports_dir / "history" / f"similar_papers_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(history_json, report)
    dump_text(history_md, build_markdown(report))

    print_console(report)
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {history_json}")
    print(f"[OK] history Markdown: {history_md}")


if __name__ == "__main__":
    main()