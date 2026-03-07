from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class LocalIndexRecord:
    doc_id: str
    content_hash: str
    source: str
    last_seen_run_ts: str
    updated_at: str


class LocalDocumentIndex:
    """
    Простой локальный state store.
    Хранит минимальный индекс документов:
    doc_id -> content_hash/source/last_seen_run_ts/updated_at
    """

    def __init__(self, path: Path):
        self.path = path
        self.records: Dict[str, LocalIndexRecord] = {}

    def load(self) -> None:
        if not self.path.exists():
            self.records = {}
            return

        payload = json.loads(self.path.read_text(encoding="utf-8"))
        raw_records = payload.get("records", {})

        self.records = {
            doc_id: LocalIndexRecord(**record)
            for doc_id, record in raw_records.items()
        }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "version": "0.1.0",
            "updated_at": utc_now_iso(),
            "records": {
                doc_id: asdict(record)
                for doc_id, record in self.records.items()
            },
        }

        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_content_hash_map(self, source: Optional[str] = None) -> dict[str, str]:
        if source is None:
            return {doc_id: rec.content_hash for doc_id, rec in self.records.items()}

        return {
            doc_id: rec.content_hash
            for doc_id, rec in self.records.items()
            if rec.source == source
        }

    def upsert(self, doc_id: str, content_hash: str, source: str, run_ts: str) -> None:
        now = utc_now_iso()
        existing = self.records.get(doc_id)

        if existing is None:
            self.records[doc_id] = LocalIndexRecord(
                doc_id=doc_id,
                content_hash=content_hash,
                source=source,
                last_seen_run_ts=run_ts,
                updated_at=now,
            )
            return

        existing.content_hash = content_hash
        existing.source = source
        existing.last_seen_run_ts = run_ts
        existing.updated_at = now

    def bulk_upsert_documents(self, documents, run_ts: str) -> None:
        for doc in documents:
            self.upsert(
                doc_id=doc.doc_id,
                content_hash=doc.content_hash,
                source=doc.source,
                run_ts=run_ts,
            )