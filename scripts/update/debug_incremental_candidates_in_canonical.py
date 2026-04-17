from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


CANDIDATES = [
    {
        "doi": "10.1016/j.ins.2026.123407",
        "arxiv_id": "2603.25501v1",
        "title": "An Experimental Comparison of the Most Popular Approaches to Fake News Detection",
    },
    {
        "doi": "10.1016/j.physd.2026.135189",
        "arxiv_id": "2603.25597v1",
        "title": "Spatiotemporal System Forecasting with Irregular Time Steps via Masked Autoencoder",
    },
    {
        "doi": "10.1109/iceccme64568.2025.11277514",
        "arxiv_id": "2603.26135v1",
        "title": "TinyML for Acoustic Anomaly Detection in IoT Sensor Networks",
    },
    {
        "doi": "10.1145/3772318.3791018",
        "arxiv_id": "2603.26173v1",
        "title": "ComVi: Context-Aware Optimized Comment Display in Video Playback",
    },
    {
        "doi": "10.1145/3772363.3798382",
        "arxiv_id": "2603.26099v1",
        "title": "\"Oops! ChatGPT is Temporarily Unavailable!\": A Diary Study on Knowledge Workers' Experiences of LLM Withdrawal",
    },
    {
        "doi": "10.1145/3773077.3806144",
        "arxiv_id": "2603.27376v1",
        "title": "Where Does AI Leave a Footprint? Children's Reasoning About AI's Environmental Costs",
    },
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def norm(s: Any) -> str:
    if s is None:
        return ""
    return str(s).strip().lower()


def extract_sources(row: dict[str, Any]) -> list[str]:
    values = []
    for src in row.get("sources", []) or []:
        if isinstance(src, dict):
            v = src.get("source") or src.get("raw_source_name")
            if v:
                values.append(str(v))
        elif isinstance(src, str):
            values.append(src)
    return sorted(set(values))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canonical-path", required=True, type=Path)
    args = parser.parse_args()

    rows = load_jsonl(args.canonical_path)

    for cand in CANDIDATES:
        cand_doi = norm(cand["doi"])
        cand_arxiv = norm(cand["arxiv_id"])
        cand_title = norm(cand["title"])

        doi_hits = []
        arxiv_hits = []
        title_hits = []

        for row in rows:
            row_doi = norm(row.get("doi"))
            row_arxiv = norm(row.get("arxiv_id"))
            row_title = norm(row.get("title"))

            if row_doi == cand_doi:
                doi_hits.append(row)

            if row_arxiv == cand_arxiv:
                arxiv_hits.append(row)

            if cand_title and cand_title in row_title:
                title_hits.append(row)

        print("=" * 100)
        print(f"DOI       : {cand['doi']}")
        print(f"ARXIV ID  : {cand['arxiv_id']}")
        print(f"TITLE     : {cand['title']}")
        print(f"doi_hits={len(doi_hits)} | arxiv_hits={len(arxiv_hits)} | title_hits={len(title_hits)}")

        def show(label: str, hits: list[dict[str, Any]]) -> None:
            for i, row in enumerate(hits[:3], start=1):
                print(f"[{label} #{i}] canonical_id={row.get('canonical_id')}")
                print(f"  title={row.get('title')}")
                print(f"  doi={row.get('doi')}")
                print(f"  arxiv_id={row.get('arxiv_id')}")
                print(f"  source_count={row.get('source_count')}")
                print(f"  sources={extract_sources(row)}")

        show("DOI", doi_hits)
        show("ARXIV", arxiv_hits)
        show("TITLE", title_hits)


if __name__ == "__main__":
    main()