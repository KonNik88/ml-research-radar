from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from radar_core.details.paper_detail import (
    DEFAULT_PAPER_FEATURES_CONFIG_PATH,
    DEFAULT_RANKING_REPORT_PATH,
    build_paper_detail_from_config,
    normalize_path,
    resolve_canonical_id_from_latest_ranking,
)


DEFAULT_REPORTS_DIR = Path("artifacts/reports/details")


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


def truncate(value: Any, width: int) -> str:
    text = str(value or "")
    if len(text) <= width:
        return text
    return text[: max(0, width - 1)] + "…"


def fmt_score(value: Any) -> str:
    try:
        return f"{float(value):.4f}"
    except Exception:
        return "NA"


def markdown_escape(value: Any) -> str:
    text = str(value or "")
    return text.replace("|", "\\|")


def build_markdown(report: dict[str, Any]) -> str:
    detail = report.get("detail") or {}

    lines: list[str] = []
    lines.append("# Paper detail report")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at_utc']}`")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Canonical ID: `{report['canonical_id']}`")
    lines.append(f"- Found: `{detail.get('found')}`")
    lines.append(f"- Canonical found: `{detail.get('canonical_found')}`")
    lines.append(f"- Features found: `{detail.get('features_found')}`")
    lines.append("")

    if not detail.get("found"):
        lines.append("_Paper not found in canonical corpus._")
        lines.append("")
        return "\n".join(lines)

    lines.append(f"## {detail.get('title')}")
    lines.append("")
    lines.append(f"- Year: `{detail.get('year')}`")
    lines.append(f"- Venue: `{detail.get('venue')}`")
    lines.append(f"- Publisher: `{detail.get('publisher')}`")
    lines.append(f"- Document type: `{detail.get('document_type')}`")
    lines.append(f"- Publication type: `{detail.get('publication_type')}`")
    lines.append("")

    authors = detail.get("authors") or []
    if authors:
        lines.append("## Authors")
        lines.append("")
        lines.append(", ".join(str(author) for author in authors[:30]))
        if len(authors) > 30:
            lines.append(f"… and {len(authors) - 30} more")
        lines.append("")

    abstract = detail.get("abstract")
    if abstract:
        lines.append("## Abstract")
        lines.append("")
        lines.append(str(abstract))
        lines.append("")

    lines.append("## Scores")
    scores = detail.get("scores") or {}
    for key in (
        "radar_score",
        "implementation_readiness_score",
        "source_confidence_score",
        "citation_signal_score",
        "recency_score",
    ):
        lines.append(f"- {key}: `{fmt_score(scores.get(key))}`")
    lines.append("")

    lines.append("## Identifiers")
    identifiers = detail.get("identifiers") or {}
    if identifiers:
        for key, value in identifiers.items():
            lines.append(f"- {key}: `{value}`")
    else:
        lines.append("_No identifiers._")
    lines.append("")

    lines.append("## Links")
    links = detail.get("links") or {}
    if links:
        for key, value in links.items():
            lines.append(f"- {key}: `{value}`")
    else:
        lines.append("_No links._")
    lines.append("")

    lines.append("## Source evidence")
    source_evidence = detail.get("source_evidence") or {}
    lines.append("```json")
    lines.append(json.dumps(source_evidence, ensure_ascii=False, indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")

    lines.append("## Feature summary")
    features = detail.get("features") or {}
    important_feature_keys = [
        "source_count",
        "source_families",
        "has_arxiv",
        "has_acl",
        "has_doi",
        "has_code_artifact",
        "has_dataset_artifact",
        "has_model_artifact",
        "has_demo_artifact",
        "trusted_artifact_links_count",
        "github_found_repo_count",
        "github_stars_max",
        "github_forks_max",
        "hf_found_count",
        "hf_model_count",
        "hf_dataset_count",
        "hf_space_count",
        "citation_count",
    ]
    for key in important_feature_keys:
        if key in features:
            lines.append(f"- {key}: `{features.get(key)}`")
    lines.append("")

    lines.append("## Artifacts")
    artifact_summary = detail.get("artifact_summary") or {}
    lines.append(f"- Artifact link rows: `{artifact_summary.get('artifact_links_rows_count')}`")
    lines.append(f"- Artifact detail rows: `{artifact_summary.get('artifact_detail_rows_count')}`")
    lines.append(f"- GitHub metadata attached: `{artifact_summary.get('github_metadata_rows_attached')}`")
    lines.append(
        f"- Hugging Face metadata attached: `{artifact_summary.get('huggingface_metadata_rows_attached')}`"
    )
    lines.append("")

    artifacts = detail.get("artifacts") or []
    if not artifacts:
        lines.append("_No artifacts._")
        lines.append("")
    else:
        lines.append(
            "| # | relation | provider | type | name | confidence | evidence | url |"
        )
        lines.append("|---:|---|---|---|---|---:|---:|---|")

        for idx, artifact in enumerate(artifacts, start=1):
            lines.append(
                "| "
                f"{idx} | "
                f"{markdown_escape(artifact.get('relation_type'))} | "
                f"{markdown_escape(artifact.get('provider'))} | "
                f"{markdown_escape(artifact.get('artifact_type'))} | "
                f"{markdown_escape(truncate(artifact.get('name'), 70))} | "
                f"{fmt_score(artifact.get('confidence_max'))} | "
                f"{artifact.get('evidence_count')} | "
                f"{markdown_escape(artifact.get('url'))} |"
            )
        lines.append("")

    lines.append("## Score components")
    score_components = scores.get("score_components") or {}
    lines.append("```json")
    lines.append(json.dumps(score_components, ensure_ascii=False, indent=2, sort_keys=True))
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a paper detail/card report for one canonical_id."
    )

    parser.add_argument("--canonical-id", type=str, default=None)
    parser.add_argument(
        "--from-latest-ranking-rank",
        type=int,
        default=None,
        help="Resolve canonical_id from artifacts/reports/ranking/demo_radar_ranking_latest.json by 1-based rank.",
    )
    parser.add_argument(
        "--ranking-report-path",
        type=Path,
        default=DEFAULT_RANKING_REPORT_PATH,
    )

    parser.add_argument(
        "--paper-features-config",
        type=Path,
        default=DEFAULT_PAPER_FEATURES_CONFIG_PATH,
    )
    parser.add_argument("--canonical-path", type=Path, default=None)
    parser.add_argument("--features-path", type=Path, default=None)
    parser.add_argument("--artifact-entities-path", type=Path, default=None)
    parser.add_argument("--artifact-links-path", type=Path, default=None)
    parser.add_argument("--github-metadata-path", type=Path, default=None)
    parser.add_argument("--huggingface-metadata-path", type=Path, default=None)

    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    if args.canonical_id and args.from_latest_ranking_rank:
        raise SystemExit("Use either --canonical-id or --from-latest-ranking-rank, not both.")

    if args.from_latest_ranking_rank:
        canonical_id = resolve_canonical_id_from_latest_ranking(
            rank=args.from_latest_ranking_rank,
            ranking_report_path=args.ranking_report_path,
        )
    elif args.canonical_id:
        canonical_id = args.canonical_id
    else:
        raise SystemExit("Provide --canonical-id or --from-latest-ranking-rank.")

    detail, resolved_paths = build_paper_detail_from_config(
        canonical_id=canonical_id,
        config_path=args.paper_features_config,
        canonical_path=args.canonical_path,
        features_path=args.features_path,
        artifact_entities_path=args.artifact_entities_path,
        artifact_links_path=args.artifact_links_path,
        github_metadata_path=args.github_metadata_path,
        huggingface_metadata_path=args.huggingface_metadata_path,
    )

    report = {
        "report_name": "paper_detail",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "canonical_id": canonical_id,
        "inputs": {
            **resolved_paths,
            "ranking_report_path": normalize_path(args.ranking_report_path),
            "reports_dir": normalize_path(args.reports_dir),
            "from_latest_ranking_rank": args.from_latest_ranking_rank,
        },
        "detail": detail,
        "summary": {
            "found": detail.get("found"),
            "canonical_found": detail.get("canonical_found"),
            "features_found": detail.get("features_found"),
            "title": detail.get("title"),
            "year": detail.get("year"),
            "artifact_detail_rows_count": (detail.get("artifact_summary") or {}).get(
                "artifact_detail_rows_count"
            ),
            "github_metadata_rows_attached": (detail.get("artifact_summary") or {}).get(
                "github_metadata_rows_attached"
            ),
            "huggingface_metadata_rows_attached": (detail.get("artifact_summary") or {}).get(
                "huggingface_metadata_rows_attached"
            ),
        },
    }

    latest_json = args.reports_dir / "paper_detail_latest.json"
    latest_md = args.reports_dir / "paper_detail_latest.md"
    history_json = args.reports_dir / "history" / f"paper_detail_{run_ts}.json"
    history_md = args.reports_dir / "history" / f"paper_detail_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(history_json, report)
    dump_text(history_md, build_markdown(report))

    print(f"[OK] canonical_id={canonical_id}")
    print(f"[OK] found={detail.get('found')}")
    print(f"[OK] canonical_found={detail.get('canonical_found')}")
    print(f"[OK] features_found={detail.get('features_found')}")
    print(f"[OK] title={detail.get('title')}")
    print(f"[OK] year={detail.get('year')}")
    print(
        f"[OK] artifact_detail_rows_count={(detail.get('artifact_summary') or {}).get('artifact_detail_rows_count')}"
    )
    print(
        f"[OK] github_metadata_rows_attached={(detail.get('artifact_summary') or {}).get('github_metadata_rows_attached')}"
    )
    print(
        f"[OK] huggingface_metadata_rows_attached={(detail.get('artifact_summary') or {}).get('huggingface_metadata_rows_attached')}"
    )
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {history_json}")
    print(f"[OK] history Markdown: {history_md}")


if __name__ == "__main__":
    main()