from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, List, Protocol, TypeVar

from radar_core.contracts.document import NormalizedDocument, RawDocument


class QueryLike(Protocol):
    pass


TQuery = TypeVar("TQuery", bound=QueryLike)
TEntry = TypeVar("TEntry")
TFetchResult = TypeVar("TFetchResult")


class BaseIngestor(ABC, Generic[TQuery, TEntry, TFetchResult]):
    source_name: str
    pipeline_version: str = "0.1.0"

    @abstractmethod
    def fetch_feed(self, query: TQuery) -> TFetchResult:
        raise NotImplementedError

    @abstractmethod
    def iter_entries(self, feed: TFetchResult) -> List[TEntry]:
        raise NotImplementedError

    @abstractmethod
    def parse_entry_to_raw(self, entry: TEntry) -> RawDocument:
        raise NotImplementedError

    @abstractmethod
    def parse_entry_to_normalized(
        self,
        entry: TEntry,
        raw_artifact_path: str | None = None,
    ) -> NormalizedDocument:
        raise NotImplementedError

    def ingest(self, query: TQuery) -> tuple[List[RawDocument], List[NormalizedDocument]]:
        feed = self.fetch_feed(query)
        entries = self.iter_entries(feed)

        raw_docs: List[RawDocument] = []
        normalized_docs: List[NormalizedDocument] = []

        for i, entry in enumerate(entries):
            raw_artifact_path = f"entry_{i:05d}.json"
            raw_docs.append(self.parse_entry_to_raw(entry))
            normalized_docs.append(
                self.parse_entry_to_normalized(
                    entry,
                    raw_artifact_path=raw_artifact_path,
                )
            )

        return raw_docs, normalized_docs