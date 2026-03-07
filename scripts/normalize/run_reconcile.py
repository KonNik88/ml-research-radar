from __future__ import annotations

import json
from pathlib import Path

from radar_core.contracts.document import NormalizedDocument
from radar_core.normalize.reconcile import reconcile_documents


def load_latest_jsonl_for_source(normalized_dir: Path, source: str) -> list[NormalizedDocument]:
    source_dir = normalized_dir / source
    files = sorted(
        [
            p for p in source_dir.glob("documents.*.jsonl")
            if not p.name.endswith(".new.jsonl")
            and not p.name.endswith(".updated.jsonl")
            and not p.name.endswith(".unchanged.jsonl")
        ]
    )

    if not files:
        return []

    latest_file = files[-1]
    docs: list[NormalizedDocument] = []

    with latest_file.open("r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            docs.append(NormalizedDocument(**row))

    return docs


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    normalized_dir = Path("data/normalized")
    analytics_dir = Path("data/analytics/reconciled")

    arxiv_docs = load_latest_jsonl_for_source(normalized_dir, "arxiv")
    openalex_docs = load_latest_jsonl_for_source(normalized_dir, "openalex")

    all_docs = arxiv_docs + openalex_docs
    canonical_docs = reconcile_documents(all_docs)

    output_path = analytics_dir / "canonical_documents.jsonl"
    write_jsonl(
        output_path,
        [doc.model_dump(mode="json") for doc in canonical_docs],
    )

    multi_source_count = sum(1 for d in canonical_docs if d.source_count > 1)

    print(f"[OK] input documents: {len(all_docs)}")
    print(f"[OK] canonical documents: {len(canonical_docs)}")
    print(f"[OK] multi-source canonical docs: {multi_source_count}")
    print(f"[OK] saved to: {output_path}")


if __name__ == "__main__":
    main()