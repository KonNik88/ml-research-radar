from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from radar_core.retrieval.similarity import DEFAULT_CANONICAL_PATH, load_canonical_map


DEFAULT_CLUSTER_LATEST = Path("artifacts/clusters/abstract/latest.json")
DEFAULT_REPORTS_DIR = Path("artifacts/reports/analytics")


def load_json(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def iter_jsonl(path: str | Path):
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def shorten(text: str, max_len: int = 160) -> str:
    text = " ".join((text or "").split()).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# Cluster inspect: {report['cluster_id']}")
    lines.append("")
    lines.append("## Summary")
    for k, v in report["summary"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")
    lines.append("## Top categories")
    for term, count in report["top_categories"]:
        lines.append(f"- {term}: {count}")
    lines.append("")
    lines.append("## Top tags")
    for term, count in report["top_tags"]:
        lines.append(f"- {term}: {count}")
    lines.append("")
    lines.append("## Top years")
    for year, count in report["top_years"]:
        lines.append(f"- {year}: {count}")
    lines.append("")
    lines.append("## Closest to center")
    for item in report["closest_examples"]:
        lines.append(
            f"- dist={item['distance_to_center']:.4f} | year={item['year']} | title={item['title']}"
        )
    lines.append("")
    lines.append("## Farthest from center")
    for item in report["farthest_examples"]:
        lines.append(
            f"- dist={item['distance_to_center']:.4f} | year={item['year']} | title={item['title']}"
        )
    lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect one abstract cluster produced by cluster_papers.py"
    )
    parser.add_argument("--cluster-id", type=int, required=True)
    parser.add_argument("--cluster-latest", type=Path, default=DEFAULT_CLUSTER_LATEST)
    parser.add_argument("--canonical-path", type=Path, default=DEFAULT_CANONICAL_PATH)
    parser.add_argument("--top-k", type=int, default=15)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    return parser


def main() -> None:
    args = build_parser().parse_args()

    latest = load_json(args.cluster_latest)
    assignments_path = Path(latest["assignments_path"])
    canonical_map = load_canonical_map(args.canonical_path)

    selected: list[dict[str, Any]] = []
    for row in iter_jsonl(assignments_path):
        if int(row["cluster_id"]) == args.cluster_id:
            selected.append(row)

    if not selected:
        raise RuntimeError(f"No rows found for cluster_id={args.cluster_id}")

    category_counter: Counter[str] = Counter()
    tag_counter: Counter[str] = Counter()
    year_counter: Counter[int] = Counter()

    enriched_rows: list[dict[str, Any]] = []
    for item in selected:
        cid = item["canonical_id"]
        can = canonical_map.get(cid, {})
        year = can.get("year")
        if year is not None:
            try:
                year_counter[int(year)] += 1
            except Exception:
                pass

        for cat in can.get("categories") or []:
            if cat:
                category_counter[str(cat)] += 1

        for tag in can.get("tags") or []:
            if tag:
                tag_counter[str(tag)] += 1

        enriched_rows.append(
            {
                "canonical_id": cid,
                "distance_to_center": float(item["distance_to_center"]),
                "title": shorten(str(can.get("title") or "")),
                "year": can.get("year"),
                "doi": can.get("doi"),
                "arxiv_id": can.get("arxiv_id"),
                "categories": can.get("categories") or [],
            }
        )

    closest_examples = sorted(enriched_rows, key=lambda x: x["distance_to_center"])[: args.top_k]
    farthest_examples = sorted(enriched_rows, key=lambda x: x["distance_to_center"], reverse=True)[: args.top_k]

    report = {
        "cluster_id": args.cluster_id,
        "summary": {
            "algorithm": latest.get("algorithm"),
            "model_name": latest.get("model_name"),
            "text_builder": latest.get("text_builder"),
            "normalize_embeddings": latest.get("normalize_embeddings"),
            "cluster_size": len(selected),
            "n_clusters_total": latest.get("n_clusters"),
            "assignments_path": str(assignments_path).replace("\\", "/"),
        },
        "top_categories": category_counter.most_common(20),
        "top_tags": tag_counter.most_common(20),
        "top_years": year_counter.most_common(20),
        "closest_examples": closest_examples,
        "farthest_examples": farthest_examples,
    }

    latest_json = args.reports_dir / f"cluster_inspect_{args.cluster_id}_latest.json"
    latest_md = args.reports_dir / f"cluster_inspect_{args.cluster_id}_latest.md"

    latest_json.parent.mkdir(parents=True, exist_ok=True)
    latest_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_md.write_text(build_markdown(report), encoding="utf-8")

    print(f"[OK] cluster_id={args.cluster_id}")
    print(f"[OK] cluster_size={len(selected)}")
    print(f"[OK] top_categories={category_counter.most_common(8)}")
    print(f"[OK] top_years={year_counter.most_common(8)}")
    print("[OK] closest_examples:")
    for item in closest_examples[:5]:
        print(f"    dist={item['distance_to_center']:.4f} | year={item['year']} | title={item['title']}")
    print(f"[OK] latest_json={latest_json}")
    print(f"[OK] latest_md={latest_md}")


if __name__ == "__main__":
    main()
