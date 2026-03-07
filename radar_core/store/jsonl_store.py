from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


class JsonlDocumentStore:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir

    @staticmethod
    def ensure_dir(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def write_json(path: Path, payload: dict) -> None:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
        with path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def raw_run_dir(self, source: str, run_ts: str) -> Path:
        return self.base_dir / "raw" / source / run_ts

    def normalized_dir(self, source: str) -> Path:
        return self.base_dir / "normalized" / source

    def state_dir(self) -> Path:
        return self.base_dir / "state"

    def prepare_run_dirs(self, source: str, run_ts: str) -> tuple[Path, Path, Path]:
        raw_dir = self.raw_run_dir(source, run_ts)
        normalized_dir = self.normalized_dir(source)
        state_dir = self.state_dir()

        self.ensure_dir(raw_dir)
        self.ensure_dir(normalized_dir)
        self.ensure_dir(state_dir)

        return raw_dir, normalized_dir, state_dir

    def save_raw_documents(self, source: str, run_ts: str, rows: list[dict]) -> Path:
        raw_dir = self.raw_run_dir(source, run_ts)
        self.ensure_dir(raw_dir)
        path = raw_dir / "documents.raw.jsonl"
        self.write_jsonl(path, rows)
        return path

    def save_manifest(self, source: str, run_ts: str, manifest: dict) -> Path:
        raw_dir = self.raw_run_dir(source, run_ts)
        self.ensure_dir(raw_dir)
        path = raw_dir / "manifest.json"
        self.write_json(path, manifest)
        return path

    def save_normalized_bundle(
        self,
        source: str,
        run_ts: str,
        normalized_rows: list[dict],
        new_rows: list[dict],
        updated_rows: list[dict],
        unchanged_rows: list[dict],
    ) -> dict[str, Path]:
        normalized_dir = self.normalized_dir(source)
        self.ensure_dir(normalized_dir)

        paths = {
            "all": normalized_dir / f"documents.{run_ts}.jsonl",
            "new": normalized_dir / f"documents.{run_ts}.new.jsonl",
            "updated": normalized_dir / f"documents.{run_ts}.updated.jsonl",
            "unchanged": normalized_dir / f"documents.{run_ts}.unchanged.jsonl",
        }

        self.write_jsonl(paths["all"], normalized_rows)
        self.write_jsonl(paths["new"], new_rows)
        self.write_jsonl(paths["updated"], updated_rows)
        self.write_jsonl(paths["unchanged"], unchanged_rows)

        return paths