from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from radar_core.contracts.document import NormalizedDocument
from radar_core.normalize.pipeline import deduplicate_documents, split_new_vs_updated
from radar_core.store.jsonl_store import JsonlDocumentStore
from radar_core.store.local_index import LocalDocumentIndex


DEFAULT_BATCHES_DIR = Path("data/normalized/arxiv_incremental_batches")
DEFAULT_STATE_PATH = Path("data/state/local_document_index.json")
DEFAULT_REPORTS_DIR = Path("artifacts/reports")


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Merge normalized arXiv incremental batches into one aggregated primary snapshot."
    )
    parser.add_argument("--batches-dir", default=str(DEFAULT_BATCHES_DIR))
    parser.add_argument("--state-path", default=str(DEFAULT_STATE_PATH))
    parser.add_argument("--reports-dir", default=str(DEFAULT_REPORTS_DIR))
    parser.add_argument(
        "--limit-batches",
        type=int,
        default=None,
        help="Optional limit on number of latest batch files to merge.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()

    batches_dir = Path(args.batches_dir)
    state_path = Path(args.state_path)
    reports_dir = Path(args.reports_dir)

    if not batches_dir.exists():
        raise FileNotFoundError(f"Batches dir not found: {batches_dir}")

    pattern = re.compile(r"^arxiv_normalized_batch\.\d{8}T\d{6}Z\.jsonl$")
    batch_files = sorted([p for p in batches_dir.iterdir() if pattern.match(p.name)])

    if not batch_files:
        raise RuntimeError(f"No normalized batch files found in: {batches_dir}")

    if args.limit_batches is not None:
        batch_files = batch_files[-args.limit_batches :]

    all_docs: list[NormalizedDocument] = []
    raw_input_count = 0

    for path in batch_files:
        rows = load_jsonl(path)
        raw_input_count += len(rows)
        all_docs.extend(NormalizedDocument(**row) for row in rows)

    deduped_docs = deduplicate_documents(all_docs)

    local_index = LocalDocumentIndex(state_path)
    local_index.load()
    existing_hashes = local_index.get_content_hash_map(source="arxiv")

    new_docs, updated_docs, unchanged_docs = split_new_vs_updated(deduped_docs, existing_hashes)

    run_ts = utc_now_ts()
    store = JsonlDocumentStore(base_dir=Path("data"))

    normalized_paths = store.save_normalized_bundle(
        source="arxiv",
        run_ts=run_ts,
        normalized_rows=[doc.model_dump(mode="json") for doc in deduped_docs],
        new_rows=[doc.model_dump(mode="json") for doc in new_docs],
        updated_rows=[doc.model_dump(mode="json") for doc in updated_docs],
        unchanged_rows=[doc.model_dump(mode="json") for doc in unchanged_docs],
    )

    report = {
        "run_ts": run_ts,
        "source": "arxiv",
        "merged_batch_count": len(batch_files),
        "merged_batch_files": [str(p).replace("\\", "/") for p in batch_files],
        "raw_input_count": raw_input_count,
        "normalized_count_after_dedup": len(deduped_docs),
        "new_count": len(new_docs),
        "updated_count": len(updated_docs),
        "unchanged_count": len(unchanged_docs),
        "output_files": {
            key: str(value).replace("\\", "/")
            for key, value in normalized_paths.items()
        },
    }

    dump_json(reports_dir / "arxiv_incremental_merge_latest.json", report)
    dump_json(reports_dir / "history" / f"arxiv_incremental_merge_{run_ts}.json", report)

    print(f"[OK] merged batch files: {len(batch_files)}")
    print(f"[OK] raw input count: {raw_input_count}")
    print(f"[OK] normalized after dedup: {len(deduped_docs)}")
    print(f"[OK] new={len(new_docs)} updated={len(updated_docs)} unchanged={len(unchanged_docs)}")
    print(f"[OK] normalized all file: {normalized_paths['all']}")

if __name__ == "__main__":
    main()