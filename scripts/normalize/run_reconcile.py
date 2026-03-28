from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from radar_core.contracts.document import NormalizedDocument
from radar_core.normalize.reconcile import reconcile_documents


DEFAULT_NORMALIZED_ROOT = Path("data/normalized")
DEFAULT_OUTPUT = Path("data/analytics/reconciled/canonical_documents.jsonl")


def load_normalized_jsonl(path: Path) -> list[NormalizedDocument]:
    docs: list[NormalizedDocument] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            docs.append(NormalizedDocument(**payload))
    return docs


def dump_jsonl(path: Path, rows: list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            if hasattr(row, "model_dump"):
                payload = row.model_dump(mode="json")
            elif hasattr(row, "dict"):
                payload = row.dict()
            else:
                payload = row
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def latest_primary_jsonl(base_dir: Path) -> Path:
    candidates = sorted(
        p
        for p in base_dir.glob("documents.*.jsonl")
        if ".new." not in p.name
        and ".updated." not in p.name
        and ".unchanged." not in p.name
    )
    if not candidates:
        raise FileNotFoundError(f"No primary normalized JSONL files found in: {base_dir}")
    return candidates[-1]


def resolve_input_paths(args: argparse.Namespace) -> list[Path]:
    if args.inputs:
        return [Path(p) for p in args.inputs]

    normalized_root = Path(args.normalized_root)
    sources = args.sources or ["arxiv", "openalex_alignment"]

    resolved: list[Path] = []
    for source in sources:
        source_dir = normalized_root / source
        resolved.append(latest_primary_jsonl(source_dir))
    return resolved


def collect_source_names(doc: Any) -> list[str]:
    values: list[str] = []

    sources = getattr(doc, "sources", None) or []
    for src in sources:
        if isinstance(src, str):
            if src.strip():
                values.append(src.strip())
        elif isinstance(src, dict):
            source_name = (src.get("source") or src.get("raw_source_name") or "").strip()
            if source_name:
                values.append(source_name)
        else:
            source_name = getattr(src, "source", None)
            if source_name and str(source_name).strip():
                values.append(str(source_name).strip())

    if not values:
        raw_source_name = getattr(doc, "raw_source_name", None)
        if raw_source_name and str(raw_source_name).strip():
            values.append(str(raw_source_name).strip())

    return values


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reconcile normalized source documents into canonical corpus."
    )
    parser.add_argument(
        "--inputs",
        nargs="+",
        help=(
            "Explicit normalized JSONL input files. "
            "If omitted, latest primary files are resolved from --normalized-root and --sources."
        ),
    )
    parser.add_argument(
        "--normalized-root",
        default=str(DEFAULT_NORMALIZED_ROOT),
        help="Root directory with normalized source subdirectories.",
    )
    parser.add_argument(
    	"--sources",
    	nargs="+",
    	default=["arxiv", "openalex_alignment", "semantic_scholar_alignment", "crossref_alignment"],
    	help="Source subdirectories to use when --inputs is not provided.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Output path for canonical JSONL.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    input_paths = resolve_input_paths(args)
    all_docs: list[NormalizedDocument] = []

    for path in input_paths:
        docs = load_normalized_jsonl(path)
        all_docs.extend(docs)
        print(f"[OK] loaded: {len(docs)} docs from {path}")

    canonical_docs = reconcile_documents(all_docs)

    output_path = Path(args.output)
    dump_jsonl(output_path, canonical_docs)

    multi_source_docs = 0
    for doc in canonical_docs:
        sources = collect_source_names(doc)
        if len(set(sources)) > 1:
            multi_source_docs += 1

    print(f"[OK] input documents: {len(all_docs)}")
    print(f"[OK] canonical documents: {len(canonical_docs)}")
    print(f"[OK] multi-source canonical docs: {multi_source_docs}")
    print(f"[OK] saved to: {output_path}")


if __name__ == "__main__":
    main()