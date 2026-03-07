from __future__ import annotations

import feedparser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlencode

from radar_core.contracts.document import (
    DocumentType,
    NormalizedDocument,
    PipelineStage,
    ProcessingStageRecord,
    RawDocument,
    SourceInfo,
    StageStatus,
)
from radar_core.utils.ids import build_content_hash, build_doc_id, canonicalize_url


ARXIV_API_BASE = "http://export.arxiv.org/api/query"


@dataclass
class ArxivQuery:
    search_query: str = "cat:cs.LG"
    start: int = 0
    max_results: int = 25
    sort_by: str = "submittedDate"
    sort_order: str = "descending"

    def to_url(self) -> str:
        params = {
            "search_query": self.search_query,
            "start": self.start,
            "max_results": self.max_results,
            "sortBy": self.sort_by,
            "sortOrder": self.sort_order,
        }
        return f"{ARXIV_API_BASE}?{urlencode(params)}"


class ArxivIngestor:
    source_name = "arxiv"
    pipeline_version = "0.1.0"

    def fetch_feed(self, query: ArxivQuery):
        url = query.to_url()
        return feedparser.parse(url)

    def parse_entry_to_raw(self, entry) -> RawDocument:
        entry_id = entry.get("id")
        canonical_url = canonicalize_url(entry_id)

        doc_id = build_doc_id(canonical_url)

        payload = {
            "id": entry.get("id"),
            "title": entry.get("title"),
            "summary": entry.get("summary"),
            "published": entry.get("published"),
            "updated": entry.get("updated"),
            "authors": [a.get("name") for a in entry.get("authors", [])],
            "tags": [t.get("term") for t in entry.get("tags", [])],
            "links": entry.get("links", []),
            "arxiv_primary_category": entry.get("arxiv_primary_category", {}),
        }

        return RawDocument(
            doc_id=doc_id,
            canonical_url=canonical_url,
            document_type=DocumentType.PAPER,
            source_info=SourceInfo(
                source=self.source_name,
                source_id=entry.get("id"),
                source_url=entry.get("id"),
            ),
            pipeline_version=self.pipeline_version,
            stages=[
                ProcessingStageRecord(
                    stage=PipelineStage.FOUND,
                    status=StageStatus.SUCCESS,
                    pipeline_version=self.pipeline_version,
                ),
                ProcessingStageRecord(
                    stage=PipelineStage.FETCHED,
                    status=StageStatus.SUCCESS,
                    pipeline_version=self.pipeline_version,
                ),
            ],
            payload=payload,
        )

    def parse_entry_to_normalized(self, entry) -> NormalizedDocument:
        entry_id = entry.get("id")
        canonical_url = canonicalize_url(entry_id)
        doc_id = build_doc_id(canonical_url)

        title = (entry.get("title") or "").strip()
        abstract = (entry.get("summary") or "").strip()

        pdf_url = self._extract_pdf_url(entry)
        authors = [a.get("name") for a in entry.get("authors", [])]
        tags = [t.get("term") for t in entry.get("tags", [])]

        published_at = self._parse_dt(entry.get("published"))
        updated_at = self._parse_dt(entry.get("updated"))

        content_hash = build_content_hash(title=title, abstract=abstract)

        return NormalizedDocument(
            doc_id=doc_id,
            canonical_url=canonical_url,
            content_hash=content_hash,
            source=self.source_name,
            source_id=entry.get("id"),
            title=title,
            abstract=abstract,
            authors=authors,
            published_at=published_at,
            updated_source_at=updated_at,
            pdf_url=pdf_url,
            tags=tags,
            document_type=DocumentType.PAPER,
            pipeline_version=self.pipeline_version,
            stages=[
                ProcessingStageRecord(
                    stage=PipelineStage.FOUND,
                    status=StageStatus.SUCCESS,
                    pipeline_version=self.pipeline_version,
                ),
                ProcessingStageRecord(
                    stage=PipelineStage.FETCHED,
                    status=StageStatus.SUCCESS,
                    pipeline_version=self.pipeline_version,
                ),
                ProcessingStageRecord(
                    stage=PipelineStage.PARSED,
                    status=StageStatus.SUCCESS,
                    pipeline_version=self.pipeline_version,
                ),
            ],
        )

    def ingest(self, query: ArxivQuery) -> tuple[List[RawDocument], List[NormalizedDocument]]:
        feed = self.fetch_feed(query)

        raw_docs: List[RawDocument] = []
        normalized_docs: List[NormalizedDocument] = []

        for entry in feed.entries:
            raw_docs.append(self.parse_entry_to_raw(entry))
            normalized_docs.append(self.parse_entry_to_normalized(entry))

        return raw_docs, normalized_docs

    @staticmethod
    def _extract_pdf_url(entry) -> Optional[str]:
        for link in entry.get("links", []):
            href = link.get("href")
            link_type = link.get("type", "")
            title = link.get("title", "")
            if href and ("pdf" in href or title == "pdf" or link_type == "application/pdf"):
                return href
        return None

    @staticmethod
    def _parse_dt(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        # arXiv обычно отдаёт ISO-like UTC timestamp
        return datetime.fromisoformat(value.replace("Z", "+00:00"))