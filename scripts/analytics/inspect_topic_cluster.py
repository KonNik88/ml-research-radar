from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_LATEST_PATH = Path("artifacts/clusters/topic/latest.json")
DEFAULT_REPORTS_DIR = Path("artifacts/reports/clusters")


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON must be an object: {path}")
    return payload


def iter_jsonl(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"JSONL file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line), line_no
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL: {path} line={line_no}: {exc}") from exc


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def find_cluster(summary: dict[str, Any], cluster_id: int) -> dict[str, Any]:
    for cluster in summary.get("clusters") or []:
        if int(cluster.get("cluster_id")) == int(cluster_id):
            return cluster
    raise KeyError(f"cluster_id={cluster_id} not found in summary")


def find_label_cluster(labels: dict[str, Any], cluster_id: int) -> dict[str, Any]:
    for cluster in labels.get("clusters") or []:
        if int(cluster.get("cluster_id")) == int(cluster_id):
            return cluster
    return {}


def rows_for_cluster(assignments_path: Path, cluster_id: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row, _line_no in iter_jsonl(assignments_path):
        try:
            if int(row.get("cluster_id")) == int(cluster_id):
                rows.append(row)
        except Exception:
            continue
    return rows


def top_rows(rows: list[dict[str, Any]], *, key: str, n: int, reverse: bool = True) -> list[dict[str, Any]]:
    def value(row: dict[str, Any]) -> float:
        try:
            return float(row.get(key) or 0.0)
        except Exception:
            return 0.0

    return sorted(rows, key=value, reverse=reverse)[:n]


def compact_paper_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_id": row.get("canonical_id"),
        "rank_within_cluster": row.get("rank_within_cluster"),
        "title": row.get("title"),
        "year": row.get("year"),
        "distance_to_centroid": row.get("distance_to_centroid"),
        "similarity_to_centroid": row.get("similarity_to_centroid"),
        "radar_score": row.get("radar_score"),
        "implementation_readiness_score": row.get("implementation_readiness_score"),
        "source_families": row.get("source_families") or [],
        "has_code_artifact": row.get("has_code_artifact"),
        "has_dataset_artifact": row.get("has_dataset_artifact"),
        "has_model_artifact": row.get("has_model_artifact"),
        "has_demo_artifact": row.get("has_demo_artifact"),
    }


def build_markdown(report: dict[str, Any]) -> str:
    cluster = report["cluster"]
    labels = report.get("labels") or {}
    rows = report["samples"]

    lines: list[str] = []
    lines.append(f"# Topic cluster inspect: {cluster['cluster_id']}")
    lines.append("")
    lines.append(f"- generated_at_utc: `{report['generated_at_utc']}`")
    lines.append(f"- cluster_build_id: `{report['cluster_build_id']}`")
    lines.append(f"- retrieval_build_id: `{report['retrieval_build_id']}`")
    lines.append(f"- size: `{cluster.get('size')}`")
    lines.append(f"- mean_radar_score: `{cluster.get('mean_radar_score')}`")
    lines.append(f"- mean_implementation_readiness_score: `{cluster.get('mean_implementation_readiness_score')}`")
    lines.append(f"- artifact_ready_count: `{cluster.get('artifact_ready_count')}`")
    lines.append(f"- code_artifact_count: `{cluster.get('code_artifact_count')}`")
    lines.append(f"- github_found_paper_count: `{cluster.get('github_found_paper_count')}`")
    lines.append(f"- hf_found_paper_count: `{cluster.get('hf_found_paper_count')}`")
    lines.append("")
    lines.append("## Label candidates")
    candidates = labels.get("label_candidates") or cluster.get("label_candidates") or []
    for item in candidates:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("## Clean label diagnostics")
    for field in [
        "clean_title_trigrams",
        "clean_title_bigrams",
        "clean_abstract_trigrams",
        "clean_abstract_bigrams",
        "clean_keywords",
        "clean_concepts",
        "clean_categories",
        "clean_title_terms",
    ]:
        values = labels.get(field) or []
        if values:
            lines.append(f"### {field}")
            for term, count in values[:15]:
                lines.append(f"- {term}: {count}")
            lines.append("")
    lines.append("## Raw cluster terms")
    for field in ["top_title_terms", "top_title_bigrams", "top_title_trigrams", "top_abstract_bigrams", "top_abstract_trigrams", "top_categories", "top_concepts", "top_keywords", "top_source_families", "top_years"]:
        values = cluster.get(field) or labels.get(field) or []
        if values:
            lines.append(f"### {field}")
            for item in values[:15]:
                if isinstance(item, list) and len(item) >= 2:
                    lines.append(f"- {item[0]}: {item[1]}")
                else:
                    lines.append(f"- {item}")
            lines.append("")
    for sample_name, sample_rows in rows.items():
        lines.append(f"## {sample_name}")
        lines.append("| rank | year | radar | impl | dist | title | canonical_id |")
        lines.append("|---:|---:|---:|---:|---:|---|---|")
        for row in sample_rows:
            title = str(row.get("title") or "").replace("|", "\\|")[:140]
            lines.append(
                f"| {row.get('rank_within_cluster')} | {row.get('year')} | "
                f"{row.get('radar_score')} | {row.get('implementation_readiness_score')} | "
                f"{row.get('distance_to_centroid')} | {title} | `{row.get('canonical_id')}` |"
            )
        lines.append("")
    return "\\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect one topic cluster from latest topic cluster run.")
    parser.add_argument("--cluster-id", type=int, required=True)
    parser.add_argument("--latest-path", type=Path, default=DEFAULT_LATEST_PATH)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--no-write-report", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    latest = load_json(args.latest_path)

    assignments_path = Path(str(latest["assignments_path"]))
    summary_path = Path(str(latest["summary_path"]))
    labels_path = Path(str(latest["label_candidates_path"]))

    summary = load_json(summary_path)
    labels = load_json(labels_path)

    cluster = find_cluster(summary, args.cluster_id)
    label_cluster = find_label_cluster(labels, args.cluster_id)
    assignment_rows = rows_for_cluster(assignments_path, args.cluster_id)

    closest = [compact_paper_row(row) for row in top_rows(assignment_rows, key="distance_to_centroid", n=args.top_n, reverse=False)]
    farthest = [compact_paper_row(row) for row in top_rows(assignment_rows, key="distance_to_centroid", n=args.top_n, reverse=True)]
    top_radar = [compact_paper_row(row) for row in top_rows(assignment_rows, key="radar_score", n=args.top_n, reverse=True)]
    top_impl = [compact_paper_row(row) for row in top_rows(assignment_rows, key="implementation_readiness_score", n=args.top_n, reverse=True)]

    report = {
        "report_name": "topic_cluster_inspect",
        "generated_at_utc": utc_now_iso(),
        "cluster_build_id": latest.get("cluster_build_id"),
        "retrieval_build_id": latest.get("retrieval_build_id"),
        "cluster_id": args.cluster_id,
        "latest_path": str(args.latest_path).replace("\\\\", "/"),
        "assignments_path": str(assignments_path).replace("\\\\", "/"),
        "summary_path": str(summary_path).replace("\\\\", "/"),
        "label_candidates_path": str(labels_path).replace("\\\\", "/"),
        "cluster": cluster,
        "labels": label_cluster,
        "samples": {
            "closest_to_centroid": closest,
            "farthest_from_centroid": farthest,
            "top_radar_score": top_radar,
            "top_implementation_readiness": top_impl,
        },
        "assignment_rows_count": len(assignment_rows),
    }

    print(f"[OK] cluster_id={args.cluster_id}")
    print(f"[OK] size={cluster.get('size')}")
    print(f"[OK] label_candidates={label_cluster.get('label_candidates') or cluster.get('label_candidates') or []}")
    print(f"[OK] top_title_terms={(cluster.get('top_title_terms') or [])[:10]}")
    print(f"[OK] top_title_trigrams={(cluster.get('top_title_trigrams') or [])[:10]}")
    print(f"[OK] top_abstract_trigrams={(cluster.get('top_abstract_trigrams') or [])[:10]}")
    print(f"[OK] top_abstract_bigrams={(cluster.get('top_abstract_bigrams') or [])[:10]}")
    print(f"[OK] top_categories={(cluster.get('top_categories') or [])[:10]}")
    print(f"[OK] top_concepts={(cluster.get('top_concepts') or [])[:10]}")
    print("[OK] closest representative titles:")
    for row in closest[:5]:
        print(f"  - {row.get('title')} ({row.get('year')}) dist={row.get('distance_to_centroid')}")

    if not args.no_write_report:
        run_ts = utc_now_ts()
        latest_json = args.reports_dir / f"topic_cluster_{args.cluster_id}_inspect_latest.json"
        latest_md = args.reports_dir / f"topic_cluster_{args.cluster_id}_inspect_latest.md"
        hist_json = args.reports_dir / "history" / f"topic_cluster_{args.cluster_id}_inspect_{run_ts}.json"
        hist_md = args.reports_dir / "history" / f"topic_cluster_{args.cluster_id}_inspect_{run_ts}.md"

        dump_json(latest_json, report)
        dump_text(latest_md, build_markdown(report))
        dump_json(hist_json, report)
        dump_text(hist_md, build_markdown(report))
        print(f"[OK] report_json={latest_json}")
        print(f"[OK] report_md={latest_md}")


if __name__ == "__main__":
    main()
