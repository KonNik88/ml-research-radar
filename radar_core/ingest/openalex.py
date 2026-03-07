from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

import requests

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


OPENALEX_WORKS_API_BASE = "https://api.openalex.org/works"


@dataclass
class OpenAlexQuery:
    search: Optional[str] = None
    filter: Optional[str] = None
    per_page: int = 25
    sort: str = "publication_date:desc"
    mailto: Optional[str] = None
    api_key: Optional[str] = None

    def to_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "per_page": self.per_page,
            "sort": self.sort,
        }

        if self.search:
            params["search"] = self.search
        if self.filter:
            params["filter"] = self.filter
        if self.mailto:
            params["mailto"] = self.mailto
        if self.api_key:
            params["api_key"] = self.api_key

        return params


class OpenAlexIngestor(BaseIngestor[OpenAlexQuery, dict, dict]):
    source_name = "openalex"
    pipeline_version = "0.1.0"

    def fetch_feed(self, query: OpenAlexQuery) -> dict:
        response = requests.get(
            OPENALEX_WORKS_API_BASE,
            params=query.to_params(),
            timeout=60,
        )
        response.raise_for_status()
        return response.json()

    def iter_entries(self, feed: dict) -> list[dict]:
        return list(feed.get("results", []))

    def parse_entry_to_raw(self, entry: dict) -> RawDocument:
        canonical_url = self._extract_canonical_url(entry)
        doc_id = build_doc_id(canonical_url)

        payload = {
            "id": entry.get("id"),
            "doi": entry.get("doi"),
            "display_name": entry.get("display_name"),
            "title": entry.get("title"),
            "publication_year": entry.get("publication_year"),
            "publication_date": entry.get("publication_date"),
            "updated_date": entry.get("updated_date"),
            "language": entry.get("language"),
            "type": entry.get("type"),
            "type_crossref": entry.get("type_crossref"),
            "cited_by_count": entry.get("cited_by_count"),
            "ids": entry.get("ids", {}),
            "authorships": entry.get("authorships", []),
            "primary_location": entry.get("primary_location"),
            "locations": entry.get("locations", []),
            "primary_topic": entry.get("primary_topic"),
            "topics": entry.get("topics", []),
            "keywords": entry.get("keywords", []),
            "abstract_inverted_index": entry.get("abstract_inverted_index"),
            "is_retracted": entry.get("is_retracted"),
            "open_access": entry.get("open_access"),
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
        entry: dict,
        raw_artifact_path: Optional[str] = None,
    ) -> NormalizedDocument:
        canonical_url = self._extract_canonical_url(entry)
        doc_id = build_doc_id(canonical_url)

        title = (entry.get("display_name") or entry.get("title") or "").strip()
        abstract = self._reconstruct_abstract(entry.get("abstract_inverted_index"))

        authors = self._extract_authors(entry)
        published_at = self._parse_date(entry.get("publication_date"))
        updated_source_at = self._parse_dt(entry.get("updated_date"))
        year = entry.get("publication_year")

        doi = entry.get("doi")
        pdf_url = self._extract_pdf_url(entry)
        license_value = self._extract_license(entry)

        primary_topic = entry.get("primary_topic") or {}
        topics = entry.get("topics") or []
        keywords = entry.get("keywords") or []

        primary_category = primary_topic.get("display_name")
        categories = [t.get("display_name") for t in topics if t.get("display_name")]
        keyword_tags = [k.get("display_name") for k in keywords if k.get("display_name")]
        tags = list(dict.fromkeys(categories + keyword_tags))

        content_hash = build_content_hash(title=title, abstract=abstract)

        external_ids: dict[str, str] = {}
        ids_block = entry.get("ids") or {}
        for key in ["openalex", "doi", "pmid", "pmcid", "mag"]:
            value = ids_block.get(key)
            if value:
                external_ids[key] = value

        if entry.get("id"):
            external_ids["openalex_id"] = entry["id"]

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
            updated_source_at=updated_source_at,
            year=year,
            pdf_url=pdf_url,
            doi=doi,
            external_ids=external_ids,
            primary_category=primary_category,
            categories=categories,
            comment=None,
            journal_ref=None,
            license=license_value,
            language=entry.get("language"),
            has_pdf=pdf_url is not None,
            is_withdrawn=bool(entry.get("is_retracted", False)),
            tags=tags,
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

    @staticmethod
    def _extract_canonical_url(entry: dict) -> str:
        ids_block = entry.get("ids") or {}

        candidate = (
            entry.get("doi")
            or ids_block.get("doi")
            or entry.get("id")
            or ids_block.get("openalex")
        )

        if not candidate:
            raise ValueError("OpenAlex entry has no canonical identifier")

        return canonicalize_url(candidate)

    @staticmethod
    def _extract_authors(entry: dict) -> list[str]:
        authorships = entry.get("authorships") or []
        authors: list[str] = []

        for authorship in authorships:
            author = authorship.get("author") or {}
            name = author.get("display_name")
            if name:
                authors.append(name)

        return authors

    @staticmethod
    def _extract_pdf_url(entry: dict) -> Optional[str]:
        primary_location = entry.get("primary_location") or {}
        pdf_url = primary_location.get("pdf_url")
        if pdf_url:
            return pdf_url

        for location in entry.get("locations") or []:
            pdf_url = location.get("pdf_url")
            if pdf_url:
                return pdf_url

        return None

    @staticmethod
    def _extract_license(entry: dict) -> Optional[str]:
        primary_location = entry.get("primary_location") or {}
        if primary_location.get("license"):
            return primary_location.get("license")

        for location in entry.get("locations") or []:
            if location.get("license"):
                return location.get("license")

        return None

    @staticmethod
    def _reconstruct_abstract(abstract_inverted_index: Optional[dict]) -> Optional[str]:
        if not abstract_inverted_index:
            return None

        positions: list[tuple[int, str]] = []
        for token, idxs in abstract_inverted_index.items():
            for idx in idxs:
                positions.append((idx, token))

        if not positions:
            return None

        positions.sort(key=lambda x: x[0])
        return " ".join(token for _, token in positions)

    @staticmethod
    def _parse_date(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        return datetime.fromisoformat(f"{value}T00:00:00+00:00")

    @staticmethod
    def _parse_dt(value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        return datetime.fromisoformat(value.replace("Z", "+00:00"))