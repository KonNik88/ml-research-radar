from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class IngestRunManifest:
    run_ts: str
    source: str
    mode: str
    query: dict[str, Any]

    raw_count: int
    normalized_count_before_dedup: int
    normalized_count_after_dedup: int

    new_count: int
    updated_count: int
    unchanged_count: int

    state_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)