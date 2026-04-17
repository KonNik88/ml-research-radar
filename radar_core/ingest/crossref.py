from __future__ import annotations

from dataclasses import dataclass, field
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


CROSSREF_WORKS_API_BASE = "https://api.crossref.org/works"


@dataclass
class CrossrefQuery:
    dois: list[str]
    mailto: Optional[str] = None
    timeout: int = 60
    rows: int = 100

    def to_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "MLResearchRadar/0.1 (mailto:unknown@example.com)",
        }
        if self.mailto:
            headers["User-Agent"] = f"MLResearchRadar/0.1 (mailto:{self.mailto})"
        return headers


class CrossrefIngestor(BaseIngestor[CrossrefQuery, dict, dict]):
    source_name = "crossref"
    pipeline_version = "0.1.0"

    @staticmethod
    def _normalize_text(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _normalize_doi(value: Any) -> Optional[str]:
        text = CrossrefIngestor._normalize_text(value)
        if not text:
            return None

        lowered = text.lower().strip()
        prefixes = (
            "https://doi.org/",
            "http://doi.org/",
            "https://dx.doi.org/",
            "http://dx.doi.org/",
            "doi:",
        )
        for prefix in prefixes:
            if lowered.startswith(prefix):
                lowered = lowered[len(prefix):].strip()
                break

        lowered = lowered.strip().strip("/")
        return lowered or None

    @staticmethod
    def _extract_title(entry: dict[str, Any]) -> str:
        title_list = entry.get("title") or []
        if isinstance(title_list, list) and title_list:
            title = str(title_list[0]).strip()
            if title:
                return title
        fallback = entry.get("container-title") or []
        if isinstance(fallback, list) and fallback:
            return str(fallback[0]).strip()
        return ""

    @staticmethod
    def _extract_abstract(entry: dict[str, Any]) -> Optional[str]:
        abstract = entry.get("abstract")
        if not abstract:
            return None

        text = str(abstract).strip()

        # very light cleanup of JATS-like tags without extra deps
        replacements = [
            ("<jats:p>", " "),
            ("</jats:p>", " "),
            ("<p>", " "),
            ("</p>", " "),
            ("<jats:title>", " "),
            ("</jats:title>", " "),
            ("\n", " "),
        ]
        for old, new in replacements:
            text = text.replace(old, new)

        import re
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text or None

    @staticmethod
    def _extract_authors(entry: dict[str, Any]) -> list[str]:
        authors_raw = entry.get("author") or []
        authors: list[str] = []

        for author in authors_raw:
            if not isinstance(author, dict):
                continue
            given = str(author.get("given", "")).strip()
            family = str(author.get("family", "")).strip()
            name = " ".join(part for part in [given, family] if part).strip()

            if not name:
                literal = str(author.get("name", "")).strip()
                if literal:
                    name = literal

            if name:
                authors.append(name)

        return list(dict.fromkeys(authors))

    @staticmethod
    def _extract_date_parts(block: Any) -> Optional[datetime]:
        """
        Crossref date fields look like:
        {"date-parts": [[2024, 3, 1]]}
        """
        if not isinstance(block, dict):
            return None

        parts = block.get("date-parts")
        if not isinstance(parts, list) or not parts:
            return None
        first = parts[0]
        if not isinstance(first, list) or not first:
            return None

        try:
            year = int(first[0])
            month = int(first[1]) if len(first) >= 2 else 1
            day = int(first[2]) if len(first) >= 3 else 1
            return datetime(year, month, day, tzinfo=timezone.utc)
        except Exception:
            return None

    @classmethod
    def _extract_best_publication_date(cls, entry: dict[str, Any]) -> Optional[datetime]:
        for key in ("published-print", "published-online", "published", "issued", "created", "deposited"):
            dt = cls._extract_date_parts(entry.get(key))
            if dt is not None:
                return dt
        return None

    @classmethod
    def _extract_updated_source_at(cls, entry: dict[str, Any]) -> Optional[datetime]:
        for key in ("deposited", "indexed", "created", "issued"):
            dt = cls._extract_date_parts(entry.get(key))
            if dt is not None:
                return dt
        return None

    @staticmethod
    def _extract_container_title(entry: dict[str, Any]) -> Optional[str]:
        values = entry.get("container-title") or []
        if isinstance(values, list) and values:
            text = str(values[0]).strip()
            return text or None
        return None

    @staticmethod
    def _normalize_publication_type(value: Any) -> Optional[str]:
        text = CrossrefIngestor._normalize_text(value)
        if not text:
            return None

        normalized = text.lower().strip()

        mapping = {
            "journal-article": "article",
            "article": "article",
            "proceedings-article": "conference",
            "proceedings": "conference",
            "posted-content": "preprint",
            "report": "report",
            "book-chapter": "book-chapter",
            "book-part": "book-chapter",
            "monograph": "book",
            "book": "book",
            "reference-entry": "reference-entry",
            "dissertation": "thesis",
        }
        return mapping.get(normalized, normalized)

    @staticmethod
    def _infer_venue_journal_conference(
        container_title: Optional[str],
        publication_type: Optional[str],
    ) -> tuple[Optional[str], Optional[str], Optional[str]]:
        if not container_title:
            return None, None, None

        pub_type = (publication_type or "").lower()

        venue = container_title
        journal = None
        conference = None

        if pub_type in {"article"}:
            journal = container_title
        elif pub_type in {"conference", "proceedings"}:
            conference = container_title

        return venue, journal, conference

    @staticmethod
    def _extract_language(entry: dict[str, Any]) -> Optional[str]:
        language = entry.get("language")
        if language is None:
            return None
        text = str(language).strip()
        return text or None

    @staticmethod
    def _extract_publisher(entry: dict[str, Any]) -> Optional[str]:
        return CrossrefIngestor._normalize_text(entry.get("publisher"))

    @staticmethod
    def _extract_license(entry: dict[str, Any]) -> Optional[str]:
        licenses = entry.get("license") or []
        if not isinstance(licenses, list) or not licenses:
            return None

        first = licenses[0]
        if not isinstance(first, dict):
            return None

        # prefer URL if present, otherwise delay-start or content-version is too noisy
        url = first.get("URL")
        if url:
            return str(url).strip()

        return None

    @staticmethod
    def _extract_landing_page_url(entry: dict[str, Any], doi: Optional[str]) -> Optional[str]:
        if doi:
            return f"https://doi.org/{doi}"

        url = entry.get("URL")
        if url:
            return str(url).strip()

        return None

    @staticmethod
    def _extract_pdf_url(entry: dict[str, Any]) -> Optional[str]:
        links = entry.get("link") or []
        if not isinstance(links, list):
            return None

        for link in links:
            if not isinstance(link, dict):
                continue
            content_type = str(link.get("content-type", "")).lower()
            intended = str(link.get("intended-application", "")).lower()
            url = link.get("URL")
            if not url:
                continue

            if content_type == "application/pdf" or intended == "text-mining":
                return str(url).strip()

        return None

    @staticmethod
    def _extract_open_access(
            entry: dict[str, Any],
            pdf_url: Optional[str],
            license_value: Optional[str],
    ) -> Optional[bool]:
        if pdf_url:
            return True
        return None

    @staticmethod
    def _extract_referenced_dois(entry: dict[str, Any]) -> list[str]:
        refs = entry.get("reference") or []
        dois: list[str] = []

        for ref in refs:
            if not isinstance(ref, dict):
                continue
            doi = ref.get("DOI") or ref.get("doi")
            normalized = CrossrefIngestor._normalize_doi(doi)
            if normalized:
                dois.append(normalized)

        return list(dict.fromkeys(dois))

    @staticmethod
    def _extract_references_count(entry: dict[str, Any], referenced_dois: list[str]) -> Optional[int]:
        count = entry.get("reference-count")
        try:
            if count is not None:
                return int(count)
        except (TypeError, ValueError):
            pass

        if referenced_dois:
            return len(referenced_dois)

        return None

    @staticmethod
    def _is_preprint(publication_type: Optional[str], subtype_text: Optional[str] = None) -> Optional[bool]:
        pub = (publication_type or "").lower()
        subtype = (subtype_text or "").lower()

        if pub == "preprint":
            return True
        if "preprint" in subtype:
            return True
        if pub in {"article", "conference", "book-chapter", "book", "report", "thesis"}:
            return False
        return None

    @staticmethod
    def _detect_review(title: Optional[str], abstract: Optional[str], publication_type: Optional[str]) -> bool:
        if (publication_type or "").lower() == "review":
            return True
        haystack = " ".join(part for part in [title or "", abstract or ""] if part).lower()
        return "review" in haystack

    @staticmethod
    def _detect_survey(title: Optional[str], abstract: Optional[str]) -> bool:
        haystack = " ".join(part for part in [title or "", abstract or ""] if part).lower()
        return "survey" in haystack

    @staticmethod
    def _estimate_metadata_completeness(
        *,
        title: str,
        abstract: Optional[str],
        authors: list[str],
        doi: Optional[str],
        publication_date: Optional[datetime],
        venue: Optional[str],
        journal: Optional[str],
        publisher: Optional[str],
        references_count: Optional[int],
        pdf_url: Optional[str],
        license_value: Optional[str],
    ) -> float:
        checks = [
            bool(title),
            bool(abstract),
            bool(authors),
            bool(doi),
            publication_date is not None,
            bool(venue),
            bool(journal),
            bool(publisher),
            references_count is not None,
            bool(pdf_url),
            bool(license_value),
        ]
        score = sum(1 for flag in checks if flag) / len(checks)
        return round(score, 4)

    def fetch_feed(self, query: CrossrefQuery) -> dict[str, Any]:
        if not query.dois:
            return {"message": {"items": []}}

        headers = query.to_headers()
        items: list[dict[str, Any]] = []

        for doi in query.dois:
            normalized = self._normalize_doi(doi)
            if not normalized:
                continue

            url = f"{CROSSREF_WORKS_API_BASE}/{normalized}"
            response = requests.get(url, headers=headers, timeout=query.timeout)
            if response.status_code == 404:
                continue
            response.raise_for_status()

            payload = response.json()
            message = payload.get("message") or {}
            if isinstance(message, dict) and message:
                items.append(message)

        return {"message": {"items": items}}

    def iter_entries(self, feed: dict[str, Any]) -> list[dict]:
        return list((feed.get("message") or {}).get("items") or [])

    def parse_entry_to_raw(self, entry: dict) -> RawDocument:
        doi = self._normalize_doi(entry.get("DOI"))
        landing_page_url = self._extract_landing_page_url(entry, doi)
        canonical_url = canonicalize_url(landing_page_url or f"https://doi.org/{doi}" if doi else "https://api.crossref.org")
        doc_id = build_doc_id(canonical_url)

        updated_source_at = self._extract_updated_source_at(entry)

        source_id = doi or self._normalize_text(entry.get("URL")) or canonical_url

        return RawDocument(
            doc_id=doc_id,
            canonical_url=canonical_url,
            document_type=DocumentType.PAPER,
            source_info=SourceInfo(
                source=self.source_name,
                source_id=source_id,
                source_url=landing_page_url or canonical_url,
                source_record_id=source_id,
                source_record_url=landing_page_url or canonical_url,
                source_api_url=f"{CROSSREF_WORKS_API_BASE}/{doi}" if doi else None,
                source_updated_at=updated_source_at,
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
            payload=entry,
            created_at=updated_source_at or datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    def parse_entry_to_normalized(
        self,
        entry: dict,
        raw_artifact_path: str | None = None,
    ) -> NormalizedDocument:
        doi = self._normalize_doi(entry.get("DOI"))
        title = self._extract_title(entry)
        abstract = self._extract_abstract(entry)
        authors = self._extract_authors(entry)

        publication_date = self._extract_best_publication_date(entry)
        updated_source_at = self._extract_updated_source_at(entry)
        year = publication_date.year if publication_date is not None else None

        container_title = self._extract_container_title(entry)
        publication_type = self._normalize_publication_type(entry.get("type"))
        venue, journal, conference = self._infer_venue_journal_conference(container_title, publication_type)

        publisher = self._extract_publisher(entry)
        language = self._extract_language(entry)
        license_value = self._extract_license(entry)

        landing_page_url = self._extract_landing_page_url(entry, doi)
        pdf_url = self._extract_pdf_url(entry)
        open_access = self._extract_open_access(entry, pdf_url, license_value)

        referenced_dois = self._extract_referenced_dois(entry)
        references_count = self._extract_references_count(entry, referenced_dois)

        canonical_url = canonicalize_url(landing_page_url or (f"https://doi.org/{doi}" if doi else "https://api.crossref.org"))
        doc_id = build_doc_id(canonical_url)
        content_hash = build_content_hash(title=title, abstract=abstract or "")

        source_id = doi or self._normalize_text(entry.get("URL")) or canonical_url

        source_ids: dict[str, str] = {}
        external_ids: dict[str, str] = {}

        if doi:
            source_ids["crossref"] = doi
            external_ids["doi"] = doi
            external_ids["crossref"] = doi

        subtype_text = self._normalize_text(entry.get("subtype"))
        is_preprint = self._is_preprint(publication_type, subtype_text)
        is_review = self._detect_review(title, abstract, publication_type)
        is_survey = self._detect_survey(title, abstract)

        metadata_completeness_score = self._estimate_metadata_completeness(
            title=title,
            abstract=abstract,
            authors=authors,
            doi=doi,
            publication_date=publication_date,
            venue=venue,
            journal=journal,
            publisher=publisher,
            references_count=references_count,
            pdf_url=pdf_url,
            license_value=license_value,
        )

        return NormalizedDocument(
            doc_id=doc_id,
            canonical_url=canonical_url,
            content_hash=content_hash,
            document_type=DocumentType.PAPER,

            source=self.source_name,
            source_id=source_id,
            source_record_id=source_id,
            source_record_url=landing_page_url or canonical_url,
            source_ids=source_ids,
            source_api_url=f"{CROSSREF_WORKS_API_BASE}/{doi}" if doi else None,
            external_ids=external_ids,

            doi=doi,
            arxiv_id=None,
            openalex_id=None,
            pmid=None,
            pmcid=None,
            semantic_scholar_id=None,
            dblp_id=None,
            mag_id=None,

            title=title,
            abstract=abstract,
            authors=authors,
            published_at=publication_date,
            publication_date=publication_date,
            updated_source_at=updated_source_at,
            year=year,

            landing_page_url=landing_page_url,
            pdf_url=pdf_url,
            repo_url=None,
            license=license_value,
            open_access=open_access,

            primary_category=None,
            categories=[],
            concepts=[],
            keywords=[],
            tags=[],

            comment=None,
            journal_ref=None,
            venue=venue,
            journal=journal,
            conference=conference,
            publisher=publisher,
            publication_type=publication_type,
            language=language,

            cited_by_count=None,
            references_count=references_count,
            referenced_ids=[],
            referenced_dois=referenced_dois,
            referenced_arxiv_ids=[],
            citation_graph_available=bool(referenced_dois),

            has_code_link=False,
            code_links=[],
            dataset_links=[],
            model_links=[],
            has_dataset_link=False,
            has_model_link=False,

            has_pdf=pdf_url is not None,
            is_withdrawn=False,

            is_open_access=open_access,
            is_preprint=is_preprint,
            is_review=is_review,
            is_survey=is_survey,

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