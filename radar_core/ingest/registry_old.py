from __future__ import annotations

from typing import Dict, Type

from radar_core.ingest.arxiv import ArxivIngestor
from radar_core.ingest.base import BaseIngestor


INGESTOR_REGISTRY: Dict[str, Type[BaseIngestor]] = {
    "arxiv": ArxivIngestor,
}


def get_ingestor(source: str) -> BaseIngestor:
    try:
        ingestor_cls = INGESTOR_REGISTRY[source]
    except KeyError as exc:
        available = ", ".join(sorted(INGESTOR_REGISTRY))
        raise ValueError(
            f"Unknown source '{source}'. Available sources: {available}"
        ) from exc

    return ingestor_cls()