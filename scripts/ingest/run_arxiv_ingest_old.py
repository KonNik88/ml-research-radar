from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from radar_core.ingest.arxiv import ArxivIngestor, ArxivQuery


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    run_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    raw_dir = Path("data/raw/arxiv") / run_ts
    normalized_dir = Path("data/normalized/arxiv")

    ensure_dir(raw_dir)
    ensure_dir(normalized_dir)

    query = ArxivQuery(
        search_query="cat:cs.LG OR cat:cs.AI OR cat:cs.CL",
        start=0,
        max_results=30,
        sort_by="submittedDate",
        sort_order="descending",
    )

    ingestor = ArxivIngestor()
    raw_docs, normalized_docs = ingestor.ingest(query=query)

    manifest = {
        "run_ts": run_ts,
        "source": "arxiv",
        "query": query.__dict__,
        "raw_count": len(raw_docs),
        "normalized_count": len(normalized_docs),
    }
    write_json(raw_dir / "manifest.json", manifest)

    raw_rows = [doc.model_dump(mode="json") for doc in raw_docs]
    normalized_rows = [doc.model_dump(mode="json") for doc in normalized_docs]

    write_jsonl(raw_dir / "documents.raw.jsonl", raw_rows)
    write_jsonl(normalized_dir / f"documents.{run_ts}.jsonl", normalized_rows)

    print(f"[OK] arXiv ingest finished: {len(normalized_docs)} documents")
    print(f"[OK] raw saved to: {raw_dir}")
    print(f"[OK] normalized saved to: {normalized_dir}")


if __name__ == "__main__":
    main()