from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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
    pipeline_version = "0.2.0"

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

        openalex_id = entry.get("id")
        updated_at = self._parse_dt(entry.get("updated_date"))

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
            "referenced_works": entry.get("referenced_works", []),
            "ids": entry.get("ids", {}),
            "authorships": entry.get("authorships", []),
            "primary_location": entry.get("primary_location"),
            "locations": entry.get("locations", []),
            "primary_topic": entry.get("primary_topic"),
            "topics": entry.get("topics", []),
            "keywords": entry.get("keywords", []),
            "concepts": entry.get("concepts", []),
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
                source_id=openalex_id,
                source_url=openalex_id,
                source_record_id=openalex_id,
                source_record_url=openalex_id,
                source_api_url=openalex_id,
                source_updated_at=updated_at,
                raw_source_name=self.source_name,
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
            updated_at=datetime.now(timezone.utc),
        )

    def parse_entry_to_normalized(
        self,
        entry: dict,
        raw_artifact_path: Optional[str] = None,
    ) -> NormalizedDocument:
        canonical_url = self._extract_canonical_url(entry)
        doc_id = build_doc_id(canonical_url)

        openalex_id = entry.get("id")
        title = (entry.get("display_name") or entry.get("title") or "").strip()
        abstract = self._reconstruct_abstract(entry.get("abstract_inverted_index"))

        authors = self._extract_authors(entry)
        published_at = self._parse_date(entry.get("publication_date"))
        updated_source_at = self._parse_dt(entry.get("updated_date"))
        year = entry.get("publication_year")

        doi = self._normalize_text(entry.get("doi"))
        pdf_url = self._extract_pdf_url(entry)
        license_value = self._extract_license(entry)
        landing_page_url = self._extract_landing_page_url(entry)
        repo_url = None  # пока OpenAlex как paper source, repo links отдельно не вытягиваем

        primary_topic = entry.get("primary_topic") or {}
        topics = entry.get("topics") or []
        keywords_raw = entry.get("keywords") or []
        concepts_raw = entry.get("concepts") or []

        primary_category = self._normalize_text(primary_topic.get("display_name"))
        categories = self._extract_display_names(topics)
        keywords = self._extract_display_names(keywords_raw)
        concepts = self._extract_display_names(concepts_raw)
        tags = list(dict.fromkeys(categories + keywords + concepts))

        content_hash = build_content_hash(title=title, abstract=abstract or "")

        ids_block = entry.get("ids") or {}
        external_ids: dict[str, str] = {}
        source_ids: dict[str, str] = {}

        if openalex_id:
            source_ids["openalex"] = openalex_id
            external_ids["openalex"] = openalex_id
            external_ids["openalex_id"] = openalex_id

        if doi:
            external_ids["doi"] = doi

        pmid = self._normalize_text(ids_block.get("pmid"))
        pmcid = self._normalize_text(ids_block.get("pmcid"))
        mag_id = self._normalize_text(ids_block.get("mag"))

        if pmid:
            external_ids["pmid"] = pmid
        if pmcid:
            external_ids["pmcid"] = pmcid
        if mag_id:
            external_ids["mag"] = mag_id

        publication_type = self._normalize_text(entry.get("type") or entry.get("type_crossref"))
        language = self._normalize_text(entry.get("language"))

        venue = self._extract_venue(entry)
        journal = self._extract_journal(entry, publication_type=publication_type)
        conference = self._extract_conference(entry, publication_type=publication_type)
        publisher = self._extract_publisher(entry)

        cited_by_count = entry.get("cited_by_count")
        referenced_ids = self._extract_referenced_ids(entry)
        references_count = len(referenced_ids) if referenced_ids else None

        open_access = self._extract_open_access(entry)
        is_withdrawn = bool(entry.get("is_retracted", False))

        is_review = self._detect_review(title, abstract)
        is_survey = self._detect_survey(title, abstract)

        has_pdf = pdf_url is not None
        has_code_link = False
        code_links: list[str] = []
        dataset_links: list[str] = []
        model_links: list[str] = []

        metadata_completeness_score = self._estimate_metadata_completeness(
            title=title,
            abstract=abstract,
            authors=authors,
            doi=doi,
            publication_date=published_at,
            primary_category=primary_category,
            categories=categories,
            pdf_url=pdf_url,
            cited_by_count=cited_by_count,
            venue=venue,
            references_count=references_count,
        )

        return NormalizedDocument(
            # identity
            doc_id=doc_id,
            canonical_url=canonical_url,
            content_hash=content_hash,
            document_type=DocumentType.PAPER,

            # source identity
            source=self.source_name,
            source_id=openalex_id,
            source_record_id=openalex_id,
            source_record_url=openalex_id,
            source_ids=source_ids,
            source_api_url=openalex_id,
            external_ids=external_ids,

            # stable identifiers
            doi=doi,
            arxiv_id=None,
            openalex_id=openalex_id,
            pmid=pmid,
            pmcid=pmcid,
            semantic_scholar_id=None,
            dblp_id=None,
            mag_id=mag_id,

            # core bibliographic fields
            title=title,
            abstract=abstract,
            authors=authors,
            published_at=published_at,
            publication_date=published_at,
            updated_source_at=updated_source_at,
            year=year,

            # links / accessibility
            landing_page_url=landing_page_url,
            pdf_url=pdf_url,
            repo_url=repo_url,
            license=license_value,
            open_access=open_access,

            # taxonomy / topical metadata
            primary_category=primary_category,
            categories=categories,
            concepts=concepts,
            keywords=keywords,
            tags=tags,

            # publication metadata
            comment=None,
            journal_ref=None,
            venue=venue,
            journal=journal,
            conference=conference,
            publisher=publisher,
            publication_type=publication_type,
            language=language,

            # citation / graph-ready metadata
            cited_by_count=cited_by_count,
            references_count=references_count,
            referenced_ids=referenced_ids,
            referenced_dois=[],
            referenced_arxiv_ids=[],
            citation_graph_available=bool(referenced_ids),

            # code / assets
            has_code_link=has_code_link,
            code_links=code_links,
            dataset_links=dataset_links,
            model_links=model_links,
            has_dataset_link=False,
            has_model_link=False,

            # lightweight flags
            has_pdf=has_pdf,
            is_withdrawn=is_withdrawn,

            # optional heuristics
            is_open_access=open_access,
            is_preprint=self._is_preprint(publication_type),
            is_review=is_review,
            is_survey=is_survey,

            # provenance / bookkeeping
            raw_artifact_path=raw_artifact_path,
            raw_source_name=self.source_name,
            ingested_at=datetime.now(timezone.utc),
            metadata_completeness_score=metadata_completeness_score,

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
    def _normalize_text(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

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
                authors.append(str(name).strip())

        return authors

    @staticmethod
    def _extract_display_names(items: list[dict]) -> list[str]:
        values: list[str] = []
        for item in items or []:
            name = item.get("display_name")
            if name and str(name).strip():
                values.append(str(name).strip())
        return list(dict.fromkeys(values))

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
    def _extract_landing_page_url(entry: dict) -> Optional[str]:
        primary_location = entry.get("primary_location") or {}
        landing_page_url = primary_location.get("landing_page_url")
        if landing_page_url:
            return landing_page_url

        source = primary_location.get("source") or {}
        homepage_url = source.get("homepage_url")
        if homepage_url:
            return homepage_url

        return entry.get("id")

    @staticmethod
    def _extract_license(entry: dict) -> Optional[str]:
        open_access = entry.get("open_access") or {}
        oa_license = open_access.get("license")
        if oa_license:
            return oa_license

        primary_location = entry.get("primary_location") or {}
        if primary_location.get("license"):
            return primary_location.get("license")

        for location in entry.get("locations") or []:
            if location.get("license"):
                return location.get("license")

        return None

    @staticmethod
    def _extract_open_access(entry: dict) -> Optional[bool]:
        open_access = entry.get("open_access") or {}
        if "is_oa" in open_access:
            return bool(open_access.get("is_oa"))

        primary_location = entry.get("primary_location") or {}
        if primary_location.get("pdf_url"):
            return True

        return None

    @staticmethod
    def _extract_venue(entry: dict) -> Optional[str]:
        primary_location = entry.get("primary_location") or {}
        source = primary_location.get("source") or {}
        display_name = source.get("display_name")
        if display_name and str(display_name).strip():
            return str(display_name).strip()
        return None

    @staticmethod
    def _extract_journal(entry: dict, publication_type: Optional[str]) -> Optional[str]:
        venue = OpenAlexIngestor._extract_venue(entry)
        if not venue:
            return None

        pub_type = (publication_type or "").lower()
        if any(token in pub_type for token in ["article", "journal"]):
            return venue
        return None

    @staticmethod
    def _extract_conference(entry: dict, publication_type: Optional[str]) -> Optional[str]:
        venue = OpenAlexIngestor._extract_venue(entry)
        if not venue:
            return None

        pub_type = (publication_type or "").lower()
        if any(token in pub_type for token in ["conference", "proceedings"]):
            return venue
        return None

    @staticmethod
    def _extract_publisher(entry: dict) -> Optional[str]:
        primary_location = entry.get("primary_location") or {}
        source = primary_location.get("source") or {}

        host_org_name = source.get("host_organization_name")
        if host_org_name and str(host_org_name).strip():
            return str(host_org_name).strip()

        host_org = source.get("host_organization")
        if host_org and str(host_org).strip():
            return str(host_org).strip()

        return None

    @staticmethod
    def _extract_referenced_ids(entry: dict) -> list[str]:
        referenced = entry.get("referenced_works") or []
        values = []
        for item in referenced:
            if item and str(item).strip():
                values.append(str(item).strip())
        return list(dict.fromkeys(values))

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

    @staticmethod
    def _is_preprint(publication_type: Optional[str]) -> Optional[bool]:
        if publication_type is None:
            return None
        pub_type = publication_type.lower()
        if "preprint" in pub_type:
            return True
        return False

    @staticmethod
    def _detect_review(title: str, abstract: Optional[str]) -> bool:
        haystack = " ".join([title or "", abstract or ""]).lower()
        return "review" in haystack

    @staticmethod
    def _detect_survey(title: str, abstract: Optional[str]) -> bool:
        haystack = " ".join([title or "", abstract or ""]).lower()
        return "survey" in haystack

    @staticmethod
    def _estimate_metadata_completeness(
        *,
        title: str,
        abstract: Optional[str],
        authors: list[str],
        doi: Optional[str],
        publication_date: Optional[datetime],
        primary_category: Optional[str],
        categories: list[str],
        pdf_url: Optional[str],
        cited_by_count: Optional[int],
        venue: Optional[str],
        references_count: Optional[int],
    ) -> float:
        checks = [
            bool(title),
            bool(abstract),
            bool(authors),
            bool(doi),
            publication_date is not None,
            bool(primary_category),
            bool(categories),
            pdf_url is not None,
            cited_by_count is not None,
            bool(venue),
            references_count is not None,
        ]
        score = sum(1 for flag in checks if flag) / len(checks)
        return round(score, 4)