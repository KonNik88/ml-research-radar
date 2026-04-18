from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer

from radar_core.text.build_text import (
    build_embedding_text,
    build_minimal_embedding_text,
)


DEFAULT_CANONICAL_PATH = Path("data/analytics/reconciled/canonical_documents.jsonl")
DEFAULT_OUTPUT_DIR = Path("artifacts/embeddings/abstract")
DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def load_canonical_rows(path: Path) -> list[dict[str, Any]]:
    return list(iter_jsonl(path))


def select_text_builder(mode: str):
    if mode == "minimal":
        return build_minimal_embedding_text
    if mode == "full":
        return build_embedding_text
    raise ValueError(f"Unsupported text builder mode: {mode}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build abstract-level embeddings from canonical documents."
    )
    parser.add_argument("--canonical-path", type=Path, default=DEFAULT_CANONICAL_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model-name", default=DEFAULT_MODEL_NAME)
    parser.add_argument(
        "--text-builder",
        choices=["minimal", "full"],
        default="minimal",
        help="minimal = title+abstract, full = title+abstract+taxonomy metadata",
    )
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument(
        "--normalize-embeddings",
        action="store_true",
        help="L2-normalize embeddings at encode time",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit for quick testing",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    if not args.canonical_path.exists():
        raise FileNotFoundError(f"Canonical corpus not found: {args.canonical_path}")

    rows = load_canonical_rows(args.canonical_path)
    if args.limit is not None:
        rows = rows[: args.limit]

    if not rows:
        raise RuntimeError("No canonical rows loaded")

    text_builder = select_text_builder(args.text_builder)

    ids: list[str] = []
    texts: list[str] = []
    sample_titles: list[str] = []

    for row in rows:
        canonical_id = row.get("canonical_id")
        if not canonical_id:
            continue

        text = text_builder(row)
        if not text:
            continue

        ids.append(canonical_id)
        texts.append(text)

        if len(sample_titles) < 5:
            sample_titles.append(str(row.get("title", "")))

    if not ids:
        raise RuntimeError("No valid rows for embedding generation")

    print(f"[INFO] loaded_docs={len(rows)}")
    print(f"[INFO] texts_for_embedding={len(texts)}")
    print(f"[INFO] model_name={args.model_name}")
    print(f"[INFO] text_builder={args.text_builder}")

    model = SentenceTransformer(args.model_name)

    embeddings = model.encode(
        texts,
        batch_size=args.batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=args.normalize_embeddings,
    )

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    embeddings_path = output_dir / f"embeddings_{run_ts}.npy"
    ids_path = output_dir / f"ids_{run_ts}.json"
    meta_path = output_dir / f"meta_{run_ts}.json"
    latest_path = output_dir / "latest.json"

    np.save(embeddings_path, embeddings)

    ids_payload = {
        "run_ts": run_ts,
        "count": len(ids),
        "ids": ids,
    }
    dump_json(ids_path, ids_payload)

    meta_payload = {
        "run_ts": run_ts,
        "generated_at_utc": utc_now_iso(),
        "canonical_path": str(args.canonical_path).replace("\\", "/"),
        "output_dir": str(output_dir).replace("\\", "/"),
        "model_name": args.model_name,
        "text_builder": args.text_builder,
        "normalize_embeddings": bool(args.normalize_embeddings),
        "count": len(ids),
        "embedding_dim": int(embeddings.shape[1]),
        "embeddings_path": str(embeddings_path).replace("\\", "/"),
        "ids_path": str(ids_path).replace("\\", "/"),
        "sample_titles": sample_titles,
    }
    dump_json(meta_path, meta_payload)

    latest_payload = {
        "run_ts": run_ts,
        "model_name": args.model_name,
        "text_builder": args.text_builder,
        "normalize_embeddings": bool(args.normalize_embeddings),
        "count": len(ids),
        "embedding_dim": int(embeddings.shape[1]),
        "embeddings_path": str(embeddings_path).replace("\\", "/"),
        "ids_path": str(ids_path).replace("\\", "/"),
        "meta_path": str(meta_path).replace("\\", "/"),
    }
    dump_json(latest_path, latest_payload)

    print(f"[OK] count={len(ids)}")
    print(f"[OK] embedding_dim={embeddings.shape[1]}")
    print(f"[OK] embeddings_shape={embeddings.shape}")
    print(f"[OK] embeddings_path={embeddings_path}")
    print(f"[OK] ids_path={ids_path}")
    print(f"[OK] meta_path={meta_path}")
    print(f"[OK] latest_path={latest_path}")


if __name__ == "__main__":
    main()