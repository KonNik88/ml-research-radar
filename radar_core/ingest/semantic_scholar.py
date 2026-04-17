from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import requests
import time

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


SEMANTIC_SCHOLAR_GRAPH_API_BASE = "https://api.semanticscholar.org/graph/v1"
SEMANTIC_SCHOLAR_PAPER_BATCH_API = f"{SEMANTIC_SCHOLAR_GRAPH_API_BASE}/paper/batch"
SEMANTIC_SCHOLAR_MAX_RETRIES = 5
SEMANTIC_SCHOLAR_DEFAULT_BACKOFF_SECONDS = 5.0
SEMANTIC_SCHOLAR_MIN_REQUEST_INTERVAL_SECONDS = 1.5

DEFAULT_FIELDS = [
    "paperId",
    "externalIds",
    "title",
    "abstract",
    "authors",
    "year",
    "publicationDate",
    "venue",
    "journal",
    "publicationTypes",
    "citationCount",
    "referenceCount",
    "url",
    "openAccessPdf",
    "isOpenAccess",
]


@dataclass
class SemanticScholarQuery:
    paper_ids: list[str]
    fields: list[str] = field(default_factory=lambda: list(DEFAULT_FIELDS))
    api_key: Optional[str] = None
    timeout: int = 60

    def to_params(self) -> dict[str, Any]:
        return {"fields": ",".join(self.fields)}


class SemanticScholarIngestor(BaseIngestor[SemanticScholarQuery, dict, dict]):
    source_name = "semantic_scholar"
    pipeline_version = "0.3.0"

    def __init__(self) -> None:
        self._last_request_ts: float | None = None

    def _respect_rate_limit(self) -> None:
        if self._last_request_ts is None:
            return

        elapsed = time.monotonic() - self._last_request_ts
        remaining = SEMANTIC_SCHOLAR_MIN_REQUEST_INTERVAL_SECONDS - elapsed
        if remaining > 0:
            time.sleep(remaining)

    @staticmethod
    def _normalize_text(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _normalize_journal_name(value: Any, venue: Optional[str] = None) -> Optional[str]:
        text = SemanticScholarIngestor._normalize_text(value)
        if not text:
            return None

        lowered = text.strip().lower()

        if lowered == "arxiv" and venue and venue.strip().lower() != "arxiv":
            return None

        return text

    @staticmethod
    def _infer_publication_type(
        publication_types_raw: Any,
        venue: Optional[str],
        doi: Optional[str],
        journal: Optional[str],
    ) -> Optional[str]:
        normalized = SemanticScholarIngestor._normalize_publication_type(publication_types_raw)

        venue_l = (venue or "").strip().lower()
        journal_l = (journal or "").strip().lower()
        doi_l = (doi or "").strip().lower()

        conference_markers = [
            "conference",
            "proceedings",
            "symposium",
            "workshop",
            "annual meeting",
            "international conference",
        ]

        if any(marker in venue_l for marker in conference_markers):
            if doi_l.startswith("10.1007/") and "_" in doi_l:
                return "book-chapter"
            return "conference"

        if journal_l and journal_l != "arxiv":
            return normalized or "article"

        return normalized

    @staticmethod
    def _normalize_doi(value: Any) -> Optional[str]:
        text = SemanticScholarIngestor._normalize_text(value)
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
    def _normalize_arxiv_id(value: Any) -> Optional[str]:
        text = SemanticScholarIngestor._normalize_text(value)
        if not text:
            return None

        lowered = text.lower().strip()
        prefixes = (
            "https://arxiv.org/abs/",
            "http://arxiv.org/abs/",
            "https://export.arxiv.org/abs/",
            "http://export.arxiv.org/abs/",
            "arxiv:",
        )
        for prefix in prefixes:
            if lowered.startswith(prefix):
                lowered = lowered[len(prefix):].strip()
                break

        lowered = lowered.strip().strip("/")
        return lowered or None

    @staticmethod
    def _parse_dt(value: Any) -> Optional[datetime]:
        if value is None:
            return None

        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

        text = str(value).strip()
        if not text:
            return None

        if text.endswith("Z"):
            text = text[:-1] + "+00:00"

        try:
            dt = datetime.fromisoformat(text)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    @classmethod
    def _parse_date(cls, value: Any) -> Optional[datetime]:
        return cls._parse_dt(value)

    @staticmethod
    def _extract_authors(entry: dict[str, Any]) -> list[str]:
        authors = entry.get("authors") or []
        names: list[str] = []
        for author in authors:
            name = SemanticScholarIngestor._normalize_text((author or {}).get("name"))
            if name:
                names.append(name)
        return list(dict.fromkeys(names))

    @staticmethod
    def _extract_external_ids(entry: dict[str, Any]) -> dict[str, str]:
        external_ids_raw = entry.get("externalIds") or {}
        external_ids: dict[str, str] = {}

        for key, value in external_ids_raw.items():
            if value is None:
                continue
            text = str(value).strip()
            if not text:
                continue
            external_ids[key] = text

        return external_ids

    @classmethod
    def _extract_doi(cls, entry: dict[str, Any]) -> Optional[str]:
        ext = entry.get("externalIds") or {}
        return cls._normalize_doi(
            ext.get("DOI") or ext.get("doi")
        )

    @classmethod
    def _extract_arxiv_id(cls, entry: dict[str, Any]) -> Optional[str]:
        ext = entry.get("externalIds") or {}
        return cls._normalize_arxiv_id(
            ext.get("ArXiv") or ext.get("Arxiv") or ext.get("arXiv") or ext.get("arxiv")
        )

    @staticmethod
    def _extract_pmid(entry: dict[str, Any]) -> Optional[str]:
        ext = entry.get("externalIds") or {}
        value = ext.get("PubMed") or ext.get("PMID") or ext.get("pmid")
        return SemanticScholarIngestor._normalize_text(value)

    @staticmethod
    def _extract_pmcid(entry: dict[str, Any]) -> Optional[str]:
        ext = entry.get("externalIds") or {}
        value = ext.get("PubMedCentral") or ext.get("PMCID") or ext.get("pmcid")
        return SemanticScholarIngestor._normalize_text(value)

    @staticmethod
    def _extract_open_access_pdf(entry: dict[str, Any]) -> Optional[str]:
        block = entry.get("openAccessPdf") or {}
        return SemanticScholarIngestor._normalize_text(block.get("url"))

    @staticmethod
    def _extract_landing_page_url(entry: dict[str, Any], doi: Optional[str]) -> Optional[str]:
        if doi:
            return f"https://doi.org/{doi}"

        url = SemanticScholarIngestor._normalize_text(entry.get("url"))
        if url:
            return url

        paper_id = SemanticScholarIngestor._normalize_text(entry.get("paperId"))
        if paper_id:
            return f"https://www.semanticscholar.org/paper/{paper_id}"

        return None

    @staticmethod
    def _extract_source_api_url(entry: dict[str, Any]) -> Optional[str]:
        paper_id = SemanticScholarIngestor._normalize_text(entry.get("paperId"))
        if not paper_id:
            return None
        return f"{SEMANTIC_SCHOLAR_GRAPH_API_BASE}/paper/{paper_id}"

    @staticmethod
    def _normalize_publication_type(value: Any) -> Optional[str]:
        if value is None:
            return None

        values: list[str]
        if isinstance(value, list):
            values = [str(v).strip() for v in value if str(v).strip()]
        else:
            values = [str(value).strip()] if str(value).strip() else []

        if not values:
            return None

        normalized = [v.lower().replace("_", "").replace("-", "").replace(" ", "") for v in values]

        priority_map = [
            ("journalarticle", "article"),
            ("article", "article"),
            ("conference", "conference"),
            ("conferencepaper", "conference"),
            ("proceedings", "conference"),
            ("review", "review"),
            ("survey", "review"),
            ("preprint", "preprint"),
            ("bookchapter", "book-chapter"),
            ("chapter", "book-chapter"),
            ("book", "book"),
        ]

        for candidate in normalized:
            for token, mapped in priority_map:
                if candidate == token:
                    return mapped

        return SemanticScholarIngestor._normalize_text(values[0].lower())

    @staticmethod
    def _is_preprint(publication_type: Optional[str]) -> bool:
        if not publication_type:
            return False
        return publication_type.strip().lower() in {"preprint", "working paper"}

    @staticmethod
    def _detect_review(title: Optional[str], abstract: Optional[str], publication_type: Optional[str]) -> bool:
        if publication_type and publication_type.lower() == "review":
            return True
        haystack = " ".join(part for part in [title or "", abstract or ""] if part).lower()
        return "review" in haystack

    @staticmethod
    def _detect_survey(title: Optional[str], abstract: Optional[str]) -> bool:
        haystack = " ".join(part for part in [title or "", abstract or ""] if part).lower()
        return "survey" in haystack

    @staticmethod
    def _sanitize_year(value: Any, publication_date: Optional[datetime] = None) -> Optional[int]:
        if value is not None:
            try:
                year = int(value)
                if 1900 <= year <= datetime.now(timezone.utc).year + 1:
                    return year
            except (TypeError, ValueError):
                pass

        if publication_date is not None:
            return publication_date.year

        return None

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
        cited_by_count: Optional[int],
        references_count: Optional[int],
        pdf_url: Optional[str],
    ) -> float:
        checks = [
            bool(title),
            bool(abstract),
            bool(authors),
            bool(doi),
            publication_date is not None,
            bool(venue),
            bool(journal),
            cited_by_count is not None,
            references_count is not None,
            bool(pdf_url),
        ]
        score = sum(1 for flag in checks if flag) / len(checks)
        return round(score, 4)

    def fetch_feed(self, query: SemanticScholarQuery) -> dict[str, Any]:
        if not query.paper_ids:
            return {"data": []}

        headers = {"Content-Type": "application/json"}
        if query.api_key:
            headers["x-api-key"] = query.api_key

        last_error: Exception | None = None

        for attempt in range(1, SEMANTIC_SCHOLAR_MAX_RETRIES + 1):
            try:
                self._respect_rate_limit()

                response = requests.post(
                    SEMANTIC_SCHOLAR_PAPER_BATCH_API,
                    params=query.to_params(),
                    json={"ids": query.paper_ids},
                    headers=headers,
                    timeout=query.timeout,
                )
                self._last_request_ts = time.monotonic()

            except requests.RequestException as exc:
                last_error = RuntimeError(
                    f"Semantic Scholar request exception: "
                    f"attempt={attempt}/{SEMANTIC_SCHOLAR_MAX_RETRIES} "
                    f"batch_size={len(query.paper_ids)} "
                    f"error={repr(exc)}"
                )
                if attempt == SEMANTIC_SCHOLAR_MAX_RETRIES:
                    raise last_error from exc

                sleep_s = SEMANTIC_SCHOLAR_DEFAULT_BACKOFF_SECONDS * attempt
                print(
                    f"[WARN] Semantic Scholar network error "
                    f"(attempt={attempt}/{SEMANTIC_SCHOLAR_MAX_RETRIES}, "
                    f"sleep={sleep_s:.1f}s, batch_size={len(query.paper_ids)})"
                )
                print(f"[WARN] exception: {repr(exc)}")
                time.sleep(sleep_s)
                continue

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        sleep_s = max(float(retry_after), SEMANTIC_SCHOLAR_DEFAULT_BACKOFF_SECONDS)
                    except ValueError:
                        sleep_s = SEMANTIC_SCHOLAR_DEFAULT_BACKOFF_SECONDS * attempt
                else:
                    sleep_s = SEMANTIC_SCHOLAR_DEFAULT_BACKOFF_SECONDS * attempt

                preview = response.text[:300].replace("\n", " ")
                print(
                    f"[WARN] Semantic Scholar rate limited "
                    f"(attempt={attempt}/{SEMANTIC_SCHOLAR_MAX_RETRIES}, "
                    f"sleep={sleep_s:.1f}s, batch_size={len(query.paper_ids)})"
                )
                print(f"[WARN] response preview: {preview}")

                if attempt == SEMANTIC_SCHOLAR_MAX_RETRIES:
                    response.raise_for_status()

                time.sleep(sleep_s)
                continue

            try:
                response.raise_for_status()
            except Exception as exc:
                preview = response.text[:500].replace("\n", " ")
                last_error = RuntimeError(
                    f"Semantic Scholar request failed: "
                    f"status={response.status_code} "
                    f"batch_size={len(query.paper_ids)} "
                    f"body_preview={preview}"
                )
                if attempt == SEMANTIC_SCHOLAR_MAX_RETRIES:
                    raise last_error from exc

                sleep_s = SEMANTIC_SCHOLAR_DEFAULT_BACKOFF_SECONDS * attempt
                print(
                    f"[WARN] Semantic Scholar HTTP error "
                    f"(attempt={attempt}/{SEMANTIC_SCHOLAR_MAX_RETRIES}, "
                    f"sleep={sleep_s:.1f}s, status={response.status_code}, "
                    f"batch_size={len(query.paper_ids)})"
                )
                time.sleep(sleep_s)
                continue

            payload = response.json()

            if isinstance(payload, list):
                return {"data": payload}
            if isinstance(payload, dict) and "data" in payload:
                return payload

            return {"data": []}

        if last_error is not None:
            raise last_error

        raise RuntimeError("Semantic Scholar fetch failed unexpectedly")

    def iter_entries(self, feed: dict[str, Any]) -> list[dict]:
        data = feed.get("data") or []
        return [entry for entry in data if isinstance(entry, dict) and entry]

    def parse_entry_to_raw(self, entry: dict) -> RawDocument:
        doi = self._extract_doi(entry)
        canonical_url = canonicalize_url(
            self._extract_landing_page_url(entry, doi) or "https://www.semanticscholar.org"
        )
        doc_id = build_doc_id(canonical_url)

        paper_id = self._normalize_text(entry.get("paperId"))
        publication_date = self._parse_date(entry.get("publicationDate"))

        return RawDocument(
            doc_id=doc_id,
            canonical_url=canonical_url,
            document_type=DocumentType.PAPER,
            source_info=SourceInfo(
                source=self.source_name,
                source_id=paper_id,
                source_url=canonical_url,
                source_record_id=paper_id,
                source_record_url=self._normalize_text(entry.get("url")) or canonical_url,
                source_api_url=self._extract_source_api_url(entry),
                source_updated_at=publication_date,
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
            created_at=publication_date or datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    def parse_entry_to_normalized(
        self,
        entry: dict,
        raw_artifact_path: str | None = None,
    ) -> NormalizedDocument:
        paper_id = self._normalize_text(entry.get("paperId"))
        doi = self._extract_doi(entry)
        arxiv_id = self._extract_arxiv_id(entry)
        pmid = self._extract_pmid(entry)
        pmcid = self._extract_pmcid(entry)

        title = self._normalize_text(entry.get("title")) or ""
        abstract = self._normalize_text(entry.get("abstract"))
        authors = self._extract_authors(entry)

        publication_date = self._parse_date(entry.get("publicationDate"))
        year = self._sanitize_year(entry.get("year"), publication_date=publication_date)

        venue = self._normalize_text(entry.get("venue"))
        journal_block = entry.get("journal") or {}
        journal = self._normalize_journal_name(journal_block.get("name"), venue=venue)
        publication_type = self._infer_publication_type(
            entry.get("publicationTypes"),
            venue=venue,
            doi=doi,
            journal=journal,
        )

        landing_page_url = self._extract_landing_page_url(entry, doi)
        pdf_url = self._extract_open_access_pdf(entry)
        open_access = entry.get("isOpenAccess")
        if open_access is not None:
            open_access = bool(open_access)

        canonical_url = canonicalize_url(landing_page_url or "https://www.semanticscholar.org")
        doc_id = build_doc_id(canonical_url)
        content_hash = build_content_hash(title=title, abstract=abstract or "")

        cited_by_count = entry.get("citationCount")
        try:
            cited_by_count = int(cited_by_count) if cited_by_count is not None else None
        except (TypeError, ValueError):
            cited_by_count = None

        references_count = entry.get("referenceCount")
        try:
            references_count = int(references_count) if references_count is not None else None
        except (TypeError, ValueError):
            references_count = None

        source_ids: dict[str, str] = {}
        external_ids: dict[str, str] = {}

        if paper_id:
            source_ids["semantic_scholar"] = paper_id
            external_ids["semantic_scholar"] = paper_id
            external_ids["semantic_scholar_id"] = paper_id

        external_ids_raw = self._extract_external_ids(entry)

        if doi:
            external_ids["doi"] = doi
        if arxiv_id:
            external_ids["arxiv"] = arxiv_id
        if pmid:
            external_ids["pmid"] = pmid
        if pmcid:
            external_ids["pmcid"] = pmcid

        metadata_completeness_score = self._estimate_metadata_completeness(
            title=title,
            abstract=abstract,
            authors=authors,
            doi=doi,
            publication_date=publication_date,
            venue=venue,
            journal=journal,
            cited_by_count=cited_by_count,
            references_count=references_count,
            pdf_url=pdf_url,
        )

        return NormalizedDocument(
            doc_id=doc_id,
            canonical_url=canonical_url,
            content_hash=content_hash,
            document_type=DocumentType.PAPER,

            source=self.source_name,
            source_id=paper_id,
            source_record_id=paper_id,
            source_record_url=self._normalize_text(entry.get("url")) or landing_page_url,
            source_ids=source_ids,
            source_api_url=self._extract_source_api_url(entry),
            external_ids={
                **external_ids_raw,
                **external_ids,
            },

            doi=doi,
            arxiv_id=arxiv_id,
            openalex_id=None,
            pmid=pmid,
            pmcid=pmcid,
            semantic_scholar_id=paper_id,
            dblp_id=self._normalize_text(external_ids_raw.get("DBLP")),
            mag_id=self._normalize_text(external_ids_raw.get("MAG")),

            title=title,
            abstract=abstract,
            authors=authors,
            published_at=publication_date,
            publication_date=publication_date,
            updated_source_at=publication_date,
            year=year,

            landing_page_url=landing_page_url,
            pdf_url=pdf_url,
            repo_url=None,
            license=None,
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
            conference=None,
            publisher=None,
            publication_type=publication_type,
            language="en",

            cited_by_count=cited_by_count,
            references_count=references_count,
            referenced_ids=[],
            referenced_dois=[],
            referenced_arxiv_ids=[],
            citation_graph_available=bool(references_count and references_count > 0),

            has_code_link=False,
            code_links=[],
            dataset_links=[],
            model_links=[],
            has_dataset_link=False,
            has_model_link=False,

            has_pdf=pdf_url is not None,
            is_withdrawn=False,

            is_open_access=open_access,
            is_preprint=self._is_preprint(publication_type),
            is_review=self._detect_review(title, abstract, publication_type),
            is_survey=self._detect_survey(title, abstract),

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