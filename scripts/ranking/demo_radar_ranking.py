from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from radar_core.ranking.feature_ranking import (
    ALLOWED_SORT_FIELDS,
    DEFAULT_FEATURES_PATH,
    RankingFilters,
    explain_paper_from_features,
    rank_papers_from_features,
)


DEFAULT_REPORTS_DIR = Path("artifacts/reports/ranking")


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


def csv_value(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def write_results_csv(path: Path, report: dict[str, Any]) -> None:
    ensure_parent(path)

    fieldnames = [
        "rank",
        "canonical_id",
        "title",
        "year",
        "radar_score",
        "implementation_readiness_score",
        "source_confidence_score",
        "citation_signal_score",
        "recency_score",
        "trusted_artifact_links_count",
        "trusted_code_links_count",
        "trusted_dataset_links_count",
        "trusted_model_links_count",
        "trusted_demo_links_count",
        "github_found_repo_count",
        "github_stars_max",
        "github_forks_max",
        "hf_found_count",
        "hf_model_count",
        "hf_dataset_count",
        "hf_space_count",
        "hf_downloads_max",
        "hf_likes_max",
        "citation_count",
        "source_families",
        "artifact_provider_counts",
        "artifact_type_counts",
    ]

    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for rank, row in enumerate(report.get("results") or [], start=1):
            payload = {"rank": rank}
            for field in fieldnames:
                if field == "rank":
                    continue
                payload[field] = csv_value(row.get(field))
            writer.writerow(payload)


def build_explain_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Radar paper explanation")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at_utc']}`")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Features path: `{report['features_path']}`")
    lines.append(f"- Canonical ID: `{report['canonical_id']}`")
    lines.append(f"- Found: `{report['found']}`")
    lines.append("")

    explanation = report.get("explanation")
    if not explanation:
        lines.append("_No paper found for this canonical_id._")
        lines.append("")
        return "\n".join(lines)

    lines.append(f"## {explanation.get('title')}")
    lines.append("")
    lines.append(f"- Year: `{explanation.get('year')}`")
    lines.append(f"- Canonical ID: `{explanation.get('canonical_id')}`")
    lines.append("")

    lines.append("## Scores")
    for key, value in (explanation.get("scores") or {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Radar components")
    for key, value in (explanation.get("radar_components") or {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Implementation components")
    for key, value in (explanation.get("implementation_components") or {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Source confidence components")
    for key, value in (explanation.get("source_confidence_components") or {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Artifact evidence")
    lines.append("```json")
    lines.append(json.dumps(explanation.get("artifact_evidence"), ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")

    lines.append("## GitHub evidence")
    lines.append("```json")
    lines.append(json.dumps(explanation.get("github_evidence"), ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")

    lines.append("## Hugging Face evidence")
    lines.append("```json")
    lines.append(json.dumps(explanation.get("huggingface_evidence"), ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")

    lines.append("## Source evidence")
    lines.append("```json")
    lines.append(json.dumps(explanation.get("source_evidence"), ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def build_ranking_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Radar ranking demo report")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at_utc']}`")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Features path: `{report['features_path']}`")
    lines.append(f"- Sort by: `{report['sort_by']}`")
    lines.append(f"- Descending: `{report['descending']}`")
    lines.append(f"- Top K: `{report['top_k']}`")
    lines.append(f"- Input rows: `{report['input_rows_count']}`")
    lines.append(f"- Filtered rows: `{report['filtered_rows_count']}`")
    lines.append(f"- Returned rows: `{report['returned_rows_count']}`")
    lines.append(f"- Include explanations: `{report.get('include_explanations')}`")
    lines.append(f"- CSV written: `{report.get('csv_written')}`")
    if report.get("latest_csv_path"):
        lines.append(f"- Latest CSV: `{report.get('latest_csv_path')}`")
    lines.append("")

    lines.append("## Filters")
    for key, value in report["filters"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Results")
    if not report["results"]:
        lines.append("_No results._")
        return "\n".join(lines)

    lines.append(
        "| rank | year | radar | impl | src | cite | artifacts | github | hf | title | canonical_id |"
    )
    lines.append("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|")

    for rank, row in enumerate(report["results"], start=1):
        title = str(row.get("title") or "").replace("|", "\\|")
        lines.append(
            "| "
            f"{rank} | "
            f"{row.get('year')} | "
            f"{fmt_score(row.get('radar_score'))} | "
            f"{fmt_score(row.get('implementation_readiness_score'))} | "
            f"{fmt_score(row.get('source_confidence_score'))} | "
            f"{fmt_score(row.get('citation_signal_score'))} | "
            f"{row.get('trusted_artifact_links_count')} | "
            f"{row.get('github_found_repo_count')} | "
            f"{row.get('hf_found_count')} | "
            f"{title} | "
            f"`{row.get('canonical_id')}` |"
        )

    lines.append("")

    if report.get("include_explanations"):
        lines.append("## Score explanations")
        for rank, row in enumerate(report["results"], start=1):
            explanation = row.get("score_explanation") or {}
            lines.append(f"### {rank}. {row.get('title')}")
            lines.append("")
            lines.append(f"- Canonical ID: `{row.get('canonical_id')}`")
            lines.append("")
            lines.append("#### Scores")
            for key, value in (explanation.get("scores") or {}).items():
                lines.append(f"- {key}: `{value}`")
            lines.append("")
            lines.append("#### Radar components")
            for key, value in (explanation.get("radar_components") or {}).items():
                lines.append(f"- {key}: `{value}`")
            lines.append("")
            lines.append("#### Implementation components")
            for key, value in (explanation.get("implementation_components") or {}).items():
                lines.append(f"- {key}: `{value}`")
            lines.append("")
            lines.append("#### Source confidence components")
            for key, value in (explanation.get("source_confidence_components") or {}).items():
                lines.append(f"- {key}: `{value}`")
            lines.append("")

    return "\n".join(lines)


def build_markdown(report: dict[str, Any]) -> str:
    if report.get("mode") == "explain":
        return build_explain_markdown(report)
    return build_ranking_markdown(report)


def print_console_results(report: dict[str, Any]) -> None:
    if report.get("mode") == "explain":
        print(f"[OK] mode=explain")
        print(f"[OK] features_path={report['features_path']}")
        print(f"[OK] canonical_id={report['canonical_id']}")
        print(f"[OK] found={report['found']}")

        explanation = report.get("explanation")
        if explanation:
            scores = explanation.get("scores") or {}
            print("")
            print(f"title={explanation.get('title')}")
            print(f"year={explanation.get('year')}")
            print(f"radar_score={scores.get('radar_score')}")
            print(f"implementation_readiness_score={scores.get('implementation_readiness_score')}")
            print(f"source_confidence_score={scores.get('source_confidence_score')}")
            print(f"citation_signal_score={scores.get('citation_signal_score')}")
        return

    print(f"[OK] mode=ranking")
    print(f"[OK] features_path={report['features_path']}")
    print(f"[OK] sort_by={report['sort_by']}")
    print(f"[OK] descending={report['descending']}")
    print(f"[OK] input_rows_count={report['input_rows_count']}")
    print(f"[OK] filtered_rows_count={report['filtered_rows_count']}")
    print(f"[OK] returned_rows_count={report['returned_rows_count']}")
    print(f"[OK] include_explanations={report.get('include_explanations')}")
    print(f"[OK] csv_written={report.get('csv_written')}")
    if report.get("latest_csv_path"):
        print(f"[OK] latest CSV: {report.get('latest_csv_path')}")

    if not report["results"]:
        print("[WARN] no results")
        return

    print("")
    print("rank | year | radar  | impl   | src    | cite   | art | gh | hf | title")
    print("-" * 120)

    for rank, row in enumerate(report["results"], start=1):
        print(
            f"{rank:>4} | "
            f"{str(row.get('year')):>4} | "
            f"{fmt_score(row.get('radar_score')):>6} | "
            f"{fmt_score(row.get('implementation_readiness_score')):>6} | "
            f"{fmt_score(row.get('source_confidence_score')):>6} | "
            f"{fmt_score(row.get('citation_signal_score')):>6} | "
            f"{str(row.get('trusted_artifact_links_count')):>3} | "
            f"{str(row.get('github_found_repo_count')):>2} | "
            f"{str(row.get('hf_found_count')):>2} | "
            f"{truncate(row.get('title'), 70)}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Demo radar/artifact-aware ranking over paper_features_latest.jsonl."
    )
    parser.add_argument("--features-path", type=Path, default=DEFAULT_FEATURES_PATH)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument(
        "--sort-by",
        choices=sorted(ALLOWED_SORT_FIELDS),
        default="radar_score",
    )
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--ascending", action="store_true")

    parser.add_argument("--query-title", type=str, default=None)
    parser.add_argument("--source-family", type=str, default=None)
    parser.add_argument("--min-year", type=int, default=None)
    parser.add_argument("--max-year", type=int, default=None)

    parser.add_argument("--has-code", action="store_true")
    parser.add_argument("--has-dataset", action="store_true")
    parser.add_argument("--has-model", action="store_true")
    parser.add_argument("--has-demo", action="store_true")
    parser.add_argument("--has-github", action="store_true")
    parser.add_argument("--has-hf", action="store_true")
    parser.add_argument("--has-acl", action="store_true")
    parser.add_argument("--has-doi", action="store_true")

    parser.add_argument(
        "--show-components",
        action="store_true",
        help="Include score explanations/components for returned top-k rows.",
    )
    parser.add_argument(
        "--output-csv",
        action="store_true",
        help="Write latest/history CSV files for ranking results.",
    )
    parser.add_argument(
        "--explain-canonical-id",
        type=str,
        default=None,
        help="Explain one paper by canonical_id instead of running top-k ranking.",
    )

    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    if args.explain_canonical_id:
        report = explain_paper_from_features(
            features_path=args.features_path,
            canonical_id=args.explain_canonical_id,
        )
    else:
        filters = RankingFilters(
            query_title=args.query_title,
            source_family=args.source_family,
            min_year=args.min_year,
            max_year=args.max_year,
            has_code=args.has_code,
            has_dataset=args.has_dataset,
            has_model=args.has_model,
            has_demo=args.has_demo,
            has_github=args.has_github,
            has_hf=args.has_hf,
            has_acl=args.has_acl,
            has_doi=args.has_doi,
        )

        report = rank_papers_from_features(
            features_path=args.features_path,
            filters=filters,
            sort_by=args.sort_by,
            top_k=args.top_k,
            descending=not args.ascending,
            include_explanations=args.show_components,
        )

    report = {
        "report_name": "demo_radar_ranking",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        **report,
    }

    latest_json = args.reports_dir / "demo_radar_ranking_latest.json"
    latest_md = args.reports_dir / "demo_radar_ranking_latest.md"
    history_json = args.reports_dir / "history" / f"demo_radar_ranking_{run_ts}.json"
    history_md = args.reports_dir / "history" / f"demo_radar_ranking_{run_ts}.md"

    latest_csv = args.reports_dir / "demo_radar_ranking_latest.csv"
    history_csv = args.reports_dir / "history" / f"demo_radar_ranking_{run_ts}.csv"

    csv_written = False
    if report.get("mode") == "ranking" and args.output_csv:
        write_results_csv(latest_csv, report)
        write_results_csv(history_csv, report)
        csv_written = True
        report["latest_csv_path"] = normalize_path(latest_csv)
        report["history_csv_path"] = normalize_path(history_csv)
    else:
        report["latest_csv_path"] = None
        report["history_csv_path"] = None

    report["csv_written"] = csv_written

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(history_json, report)
    dump_text(history_md, build_markdown(report))

    print_console_results(report)
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {history_json}")
    print(f"[OK] history Markdown: {history_md}")


if __name__ == "__main__":
    main()