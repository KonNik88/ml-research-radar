from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode

import feedparser

from radar_core.contracts.document import (
    DocumentType,
    NormalizedDocument,
    PipelineStage,
    ProcessingStageRecord,
    RawDocument,
    SourceInfo,
    StageStatus,
)
from radar_core.ingest.base import BaseIngestor
from radar_core.utils.ids import build_content_hash, build_doc_id, canonicalize_url


ARXIV_API_BASE = "http://export.arxiv.org/api/query"

URL_RE = re.compile(r"https?://[^\s<>()\"']+")


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


class ArxivIngestor(BaseIngestor[ArxivQuery, object, object]):
    source_name = "arxiv"
    pipeline_version = "0.2.0"

    def fetch_feed(self, query: ArxivQuery):
        url = query.to_url()
        return feedparser.parse(url)

    def iter_entries(self, feed) -> list[object]:
        return list(feed.entries)

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

        title = self._normalize_text(entry.get("title"))
        abstract = self._normalize_text(entry.get("summary"))
        comment = self._normalize_text(entry.get("arxiv_comment"))
        journal_ref = self._normalize_text(entry.get("arxiv_journal_ref"))

        authors = [
            self._normalize_text(a.get("name"))
            for a in entry.get("authors", [])
            if self._normalize_text(a.get("name"))
        ]

        categories = [
            t.get("term")
            for t in entry.get("tags", [])
            if t.get("term")
        ]
        primary_category = self._extract_primary_category(entry)

        pdf_url = self._extract_pdf_url(entry)
        license_url = self._extract_license_url(entry)
        landing_page_url = entry.get("id")

        doi = self._normalize_text(entry.get("arxiv_doi"))
        arxiv_id = self._extract_arxiv_id(entry_id)

        published_at = self._parse_dt(entry.get("published"))
        updated_at = self._parse_dt(entry.get("updated"))

        publication_year = published_at.year if published_at else None
        content_hash = build_content_hash(title=title, abstract=abstract or "")

        external_ids: dict[str, str] = {}
        if doi:
            external_ids["doi"] = doi
        if arxiv_id:
            external_ids["arxiv"] = arxiv_id

        concepts: list[str] = []
        keywords: list[str] = []
        tags = list(dict.fromkeys(categories))

        code_links = self._extract_code_links(
            comment=comment,
            abstract=abstract,
            links=entry.get("links", []),
        )
        has_code_link = len(code_links) > 0

        return NormalizedDocument(
            # identity
            doc_id=doc_id,
            canonical_url=canonical_url,
            content_hash=content_hash,
            document_type=DocumentType.PAPER,

            # source identity
            source=self.source_name,
            source_id=entry_id,
            source_record_id=arxiv_id,
            source_record_url=entry_id,
            external_ids=external_ids,

            # stable ids
            doi=doi,
            arxiv_id=arxiv_id,
            openalex_id=None,

            # core content
            title=title,
            abstract=abstract,
            authors=authors,
            published_at=published_at,
            publication_date=published_at,
            updated_source_at=updated_at,
            year=publication_year,

            # links / accessibility
            landing_page_url=landing_page_url,
            pdf_url=pdf_url,
            repo_url=code_links[0] if code_links else None,
            license=license_url,
            open_access=True,

            # taxonomy / topics
            primary_category=primary_category,
            categories=categories,
            concepts=concepts,
            keywords=keywords,
            tags=tags,

            # publication metadata
            comment=comment,
            journal_ref=journal_ref,
            venue=None,
            journal=None,
            conference=None,
            publisher=None,
            publication_type="preprint",
            language="en",

            # citation / graph-ready
            cited_by_count=None,
            references_count=None,
            referenced_ids=[],
            referenced_dois=[],
            referenced_arxiv_ids=[],
            citation_graph_available=False,

            # code / assets
            has_code_link=has_code_link,
            code_links=code_links,
            dataset_links=[],
            model_links=[],

            # lightweight flags
            has_pdf=pdf_url is not None,
            is_withdrawn=self._detect_withdrawn(title, abstract, comment),

            # provenance / bookkeeping
            raw_artifact_path=raw_artifact_path,
            raw_source_name=self.source_name,
            ingested_at=datetime.now(timezone.utc),
            metadata_completeness_score=None,

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

    @staticmethod
    def _normalize_text(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = " ".join(str(value).split()).strip()
        return cleaned or None

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
            if href and (
                "pdf" in href
                or title == "pdf"
                or link_type == "application/pdf"
            ):
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
    def _extract_arxiv_id(entry_id: Optional[str]) -> Optional[str]:
        if not entry_id:
            return None
        return entry_id.rstrip("/").rsplit("/", 1)[-1]

    @staticmethod
    def _extract_code_links(
        *,
        comment: Optional[str],
        abstract: Optional[str],
        links: list[object],
    ) -> list[str]:
        candidates: list[str] = []

        # direct links in arXiv feed
        for link in links or []:
            href = link.get("href")
            if href and ArxivIngestor._looks_like_code_link(href):
                candidates.append(href)

        # links mentioned in comment / abstract
        for text in (comment, abstract):
            if not text:
                continue
            for match in URL_RE.findall(text):
                if ArxivIngestor._looks_like_code_link(match):
                    candidates.append(match.rstrip(".,);]"))

        # deduplicate preserving order
        return list(dict.fromkeys(candidates))

    @staticmethod
    def _looks_like_code_link(url: str) -> bool:
        lowered = url.lower()
        return any(
            token in lowered
            for token in [
                "github.com",
                "gitlab.com",
                "bitbucket.org",
                "huggingface.co",
                "code",
                "implementation",
            ]
        )

    @staticmethod
    def _parse_dt(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None

        formats = [
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(value, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue

        return None

    @staticmethod
    def _detect_withdrawn(
        title: Optional[str],
        abstract: Optional[str],
        comment: Optional[str],
    ) -> bool:
        haystack = " ".join(
            part for part in [title or "", abstract or "", comment or ""] if part
        ).lower()
        return "withdrawn" in haystack or "retracted" in haystack