from __future__ import annotations

import argparse
import json
from pathlib import Path


DEFAULT_INPUT = Path("data/analytics/reconciled/canonical_documents.jsonl")


def load_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def main():
    parser = argparse.ArgumentParser(description="Inspect multi-source canonical documents.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--min-sources", type=int, default=2)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    docs = list(load_jsonl(Path(args.input)))
    selected = [d for d in docs if d.get("source_count", 1) >= args.min_sources][: args.limit]

    print(f"selected docs: {len(selected)}")
    for i, d in enumerate(selected, start=1):
        print("\n" + "=" * 100)
        print(f"[{i}] {d.get('title')}")
        print(f"source_count: {d.get('source_count')} | unique_source_count: {d.get('unique_source_count')}")
        print(f"source_ids: {d.get('source_ids')}")
        print(f"doc_ids: {d.get('doc_ids')}")
        print(f"doi: {d.get('doi')}")
        print(f"arxiv_id: {d.get('arxiv_id')}")
        print(f"semantic_scholar_id: {d.get('semantic_scholar_id')}")
        print(f"journal: {d.get('journal')}")
        print(f"venue: {d.get('venue')}")
        print(f"publisher: {d.get('publisher')}")
        print(f"publication_type: {d.get('publication_type')}")
        print(f"cited_by_count: {d.get('cited_by_count')}")
        print(f"references_count: {d.get('references_count')}")
        print(f"is_preprint: {d.get('is_preprint')}")
        print(f"external_ids keys: {sorted((d.get('external_ids') or {}).keys())}")


if __name__ == "__main__":
    main()