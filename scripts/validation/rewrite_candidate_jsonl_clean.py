from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def parse_objects_from_broken_jsonl(path: Path) -> list[dict[str, Any]]:
    """
    Reads a file that should have contained one JSON object per line,
    but may contain malformed lines with multiple concatenated JSON fragments.
    Uses JSONDecoder.raw_decode to recover objects sequentially.
    """
    text = path.read_text(encoding="utf-8")
    decoder = json.JSONDecoder()

    idx = 0
    n = len(text)
    rows: list[dict[str, Any]] = []

    while idx < n:
        while idx < n and text[idx].isspace():
            idx += 1
        if idx >= n:
            break

        obj, end = decoder.raw_decode(text, idx)
        if not isinstance(obj, dict):
            raise ValueError(f"Expected dict JSON object at position {idx}, got {type(obj)}")
        rows.append(obj)
        idx = end

    return rows


def dump_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rewrite a broken candidate reconcile output into clean JSONL."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main() -> None:
    args = build_parser().parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Input file not found: {args.input}")

    rows = parse_objects_from_broken_jsonl(args.input)
    dump_jsonl(args.output, rows)

    print(f"[OK] recovered objects: {len(rows)}")
    print(f"[OK] clean output: {args.output}")


if __name__ == "__main__":
    main()