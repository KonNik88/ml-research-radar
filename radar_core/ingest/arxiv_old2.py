from __future__ import annotations

import feedparser
from dataclasses import dataclass
from datetime import datetime
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
            "arxiv_comment": entry.get("arxiv_comment"),
            "arxiv_journal_ref": entry.get("arxiv_journal_ref"),
            "arxiv_doi": entry.get("arxiv_doi"),
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

    def parse_entry_to_normalized(
        self,
        entry,
        raw_artifact_path: Optional[str] = None,
    ) -> NormalizedDocument:
        entry_id = entry.get("id")
        canonical_url = canonicalize_url(entry_id)
        doc_id = build_doc_id(canonical_url)

        title = (entry.get("title") or "").strip()
        abstract = (entry.get("summary") or "").strip()

        authors = [a.get("name") for a in entry.get("authors", [])]
        categories = [t.get("term") for t in entry.get("tags", []) if t.get("term")]
        primary_category = self._extract_primary_category(entry)

        pdf_url = self._extract_pdf_url(entry)
        doi = entry.get("arxiv_doi")
        comment = entry.get("arxiv_comment")
        journal_ref = entry.get("arxiv_journal_ref")
        license_url = self._extract_license_url(entry)

        published_at = self._parse_dt(entry.get("published"))
        updated_at = self._parse_dt(entry.get("updated"))
        year = published_at.year if published_at else None

        content_hash = build_content_hash(title=title, abstract=abstract)

        external_ids = {}
        if doi:
            external_ids["doi"] = doi
        if entry_id:
            external_ids["arxiv"] = entry_id.rsplit("/", 1)[-1]

        return NormalizedDocument(
            doc_id=doc_id,
            canonical_url=canonical_url,
            content_hash=content_hash,
            document_type=DocumentType.PAPER,
            source=self.source_name,
            source_id=entry.get("id"),
            source_record_url=entry.get("id"),
            title=title,
            abstract=abstract,
            authors=authors,
            published_at=published_at,
            updated_source_at=updated_at,
            year=year,
            pdf_url=pdf_url,
            doi=doi,
            external_ids=external_ids,
            primary_category=primary_category,
            categories=categories,
            comment=comment,
            journal_ref=journal_ref,
            license=license_url,
            language="en",
            has_pdf=pdf_url is not None,
            is_withdrawn=self._detect_withdrawn(title, abstract, comment),
            tags=categories,
            raw_artifact_path=raw_artifact_path,
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

        for i, entry in enumerate(feed.entries):
            raw_artifact_path = f"entry_{i:05d}.json"
            raw_docs.append(self.parse_entry_to_raw(entry))
            normalized_docs.append(
                self.parse_entry_to_normalized(
                    entry,
                    raw_artifact_path=raw_artifact_path,
                )
            )

        return raw_docs, normalized_docs

    @staticmethod
    def _extract_primary_category(entry) -> Optional[str]:
        primary = entry.get("arxiv_primary_category")
        if isinstance(primary, dict):
            return primary.get("term")
        return None

    @staticmethod
    def _extract_pdf_url(entry) -> Optional[str]:
        for link in entry.get("links", []):
            href = link.get("href")
            title = link.get("title", "")
            link_type = link.get("type", "")
            if href and ("pdf" in href or title == "pdf" or link_type == "application/pdf"):
                return href
        return None

    @staticmethod
    def _extract_license_url(entry) -> Optional[str]:
        for link in entry.get("links", []):
            href = link.get("href")
            rel = link.get("rel", "")
            if href and "license" in rel.lower():
                return href
        return None

    @staticmethod
    def _detect_withdrawn(title: Optional[str], abstract: Optional[str], comment: Optional[str]) -> bool:
        haystack = " ".join(
            [part for part in [title or "", abstract or "", comment or ""] if part]
        ).lower()
        return "withdrawn" in haystack

    @staticmethod
    def _parse_dt(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        return datetime.fromisoformat(value.replace("Z", "+00:00"))