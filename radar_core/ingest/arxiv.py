from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode
import time
from email.utils import parsedate_to_datetime
import feedparser
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


ARXIV_API_BASE = "https://export.arxiv.org/api/query"
ARXIV_MIN_REQUEST_INTERVAL_SECONDS = 8.0
ARXIV_MAX_RETRIES = 5
ARXIV_DEFAULT_BACKOFF_SECONDS = 20.0
URL_RE = re.compile(r"https?://[^\s<>()\"']+")

CONFERENCE_HINT_RE = re.compile(
    r"\b("
    r"neurips|nips|iclr|icml|cvpr|iccv|eccv|aaai|ijcai|acl|emnlp|naacl|eacl|coling|"
    r"kdd|www|thewebconf|sigir|uai|aistats|interspeech|acmmm|mm|wacv"
    r")\b",
    flags=re.IGNORECASE,
)

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

    def __init__(self) -> None:
        self._last_request_ts: float | None = None

    def _respect_rate_limit(self) -> None:
        if self._last_request_ts is None:
            return

        elapsed = time.monotonic() - self._last_request_ts
        remaining = ARXIV_MIN_REQUEST_INTERVAL_SECONDS - elapsed
        if remaining > 0:
            time.sleep(remaining)

    @staticmethod
    def _retry_after_seconds(response: requests.Response) -> float | None:
        value = response.headers.get("Retry-After")
        if not value:
            return None

        value = value.strip()
        if not value:
            return None

        # Retry-After: seconds
        try:
            return max(float(value), 0.0)
        except ValueError:
            pass

        # Retry-After: HTTP date
        try:
            dt = parsedate_to_datetime(value)
            now = datetime.now(timezone.utc)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return max((dt - now).total_seconds(), 0.0)
        except Exception:
            return None

    def fetch_feed(self, query: ArxivQuery):
        url = query.to_url()

        headers = {
            "User-Agent": "ML-Research-Radar/0.2.0 (research ingest; local development)"
        }

        last_error: Exception | None = None

        for attempt in range(1, ARXIV_MAX_RETRIES + 1):
            self._respect_rate_limit()

            response = requests.get(url, headers=headers, timeout=60)
            self._last_request_ts = time.monotonic()

            if response.status_code == 429:
                retry_after = self._retry_after_seconds(response)
                sleep_s = retry_after if retry_after is not None else (ARXIV_DEFAULT_BACKOFF_SECONDS * attempt)

                body_preview = response.text[:500].replace("\n", " ")
                print(
                    f"[WARN] arXiv rate limited request "
                    f"(attempt={attempt}/{ARXIV_MAX_RETRIES}, sleep={sleep_s:.1f}s, url={url})"
                )
                print(f"[WARN] response preview: {body_preview}")

                if attempt == ARXIV_MAX_RETRIES:
                    response.raise_for_status()

                time.sleep(sleep_s)
                continue

            try:
                response.raise_for_status()
            except Exception as exc:
                body_preview = response.text[:1000].replace("\n", " ")
                raise RuntimeError(
                    f"arXiv request failed: url={url} status={response.status_code} "
                    f"body_preview={body_preview}"
                ) from exc

            text = response.text
            feed = feedparser.parse(text)

            if not getattr(feed, "entries", None):
                bozo = getattr(feed, "bozo", 0)
                bozo_exc = getattr(feed, "bozo_exception", None)
                preview = text[:1000].replace("\n", " ")

                raise RuntimeError(
                    "arXiv returned no entries. "
                    f"url={url} status={response.status_code} "
                    f"bozo={bozo} bozo_exception={repr(bozo_exc)} "
                    f"body_preview={preview}"
                )

            return feed

        if last_error is not None:
            raise last_error

        raise RuntimeError(f"Failed to fetch arXiv feed after {ARXIV_MAX_RETRIES} attempts: {url}")

    def iter_entries(self, feed) -> list[object]:
        entries = list(getattr(feed, "entries", []) or [])
        return entries

    def parse_entry_to_raw(self, entry) -> RawDocument:
        entry_id = entry.get("id")
        canonical_url = canonicalize_url(entry_id)
        doc_id = build_doc_id(canonical_url)

        arxiv_id = self._extract_arxiv_id(entry_id)
        published_at = self._parse_dt(entry.get("published"))
        updated_at = self._parse_dt(entry.get("updated"))

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
                source_record_id=arxiv_id,
                source_record_url=entry.get("id"),
                source_api_url=None,
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
            created_at=published_at or datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    def parse_entry_to_normalized(
        self,
        entry,
        raw_artifact_path: Optional[str] = None,
    ) -> NormalizedDocument:
        entry_id = entry.get("id")
        canonical_url = canonicalize_url(entry_id)
        doc_id = build_doc_id(canonical_url)

        title = self._normalize_text(entry.get("title")) or ""
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
        source_ids: dict[str, str] = {}

        if doi:
            external_ids["doi"] = doi
        if arxiv_id:
            external_ids["arxiv"] = arxiv_id
            source_ids["arxiv"] = arxiv_id

        concepts: list[str] = []
        keywords: list[str] = []
        tags = list(dict.fromkeys(categories))

        code_links = self._extract_code_links(
            comment=comment,
            abstract=abstract,
            links=entry.get("links", []),
        )
        has_code_link = len(code_links) > 0
        repo_url = self._extract_repo_url(code_links)
        conference_hint = self._extract_conference_hint(comment)

        has_pdf = pdf_url is not None
        is_withdrawn = self._detect_withdrawn(title, abstract, comment)
        is_review = self._detect_review(title, abstract, comment)
        is_survey = self._detect_survey(title, abstract, comment)

        open_access = True
        metadata_completeness_score = self._estimate_metadata_completeness(
            title=title,
            abstract=abstract,
            authors=authors,
            doi=doi,
            publication_date=published_at,
            primary_category=primary_category,
            categories=categories,
            pdf_url=pdf_url,
            code_links=code_links,
            comment=comment,
            journal_ref=journal_ref,
        )

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
            source_ids=source_ids,
            source_api_url=None,
            external_ids=external_ids,

            # stable ids
            doi=doi,
            arxiv_id=arxiv_id,
            openalex_id=None,

            # optional extra ids
            pmid=None,
            pmcid=None,
            semantic_scholar_id=None,
            dblp_id=None,
            mag_id=None,

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
            repo_url=repo_url,
            license=license_url,
            open_access=open_access,

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
            conference=conference_hint,
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
            has_dataset_link=False,
            has_model_link=False,

            # lightweight flags
            has_pdf=has_pdf,
            is_withdrawn=is_withdrawn,

            # optional heuristics
            is_open_access=open_access,
            is_preprint=True,
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

        for link in links or []:
            href = link.get("href")
            if href and ArxivIngestor._looks_like_code_link(href):
                candidates.append(href)

        for text in (comment, abstract):
            if not text:
                continue
            for match in URL_RE.findall(text):
                if ArxivIngestor._looks_like_code_link(match):
                    candidates.append(match.rstrip(".,);]"))

        return list(dict.fromkeys(candidates))

    @staticmethod
    def _extract_repo_url(code_links: list[str]) -> Optional[str]:
        for url in code_links:
            if ArxivIngestor._looks_like_repo_host(url):
                return url
        return code_links[0] if code_links else None

    @staticmethod
    def _looks_like_repo_host(url: str) -> bool:
        lowered = url.lower()
        return any(
            host in lowered
            for host in [
                "github.com",
                "gitlab.com",
                "bitbucket.org",
                "codeberg.org",
                "huggingface.co",
            ]
        )

    @staticmethod
    def _extract_conference_hint(comment: Optional[str]) -> Optional[str]:
        if not comment:
            return None

        match = CONFERENCE_HINT_RE.search(comment)
        if not match:
            return None

        conf = match.group(1).upper()
        mapping = {
            "NIPS": "NeurIPS",
            "NEURIPS": "NeurIPS",
            "ICLR": "ICLR",
            "ICML": "ICML",
            "CVPR": "CVPR",
            "ICCV": "ICCV",
            "ECCV": "ECCV",
            "AAAI": "AAAI",
            "IJCAI": "IJCAI",
            "ACL": "ACL",
            "EMNLP": "EMNLP",
            "NAACL": "NAACL",
            "EACL": "EACL",
            "COLING": "COLING",
            "KDD": "KDD",
            "WWW": "WWW",
            "THEWEBCONF": "TheWebConf",
            "SIGIR": "SIGIR",
            "UAI": "UAI",
            "AISTATS": "AISTATS",
            "INTERSPEECH": "Interspeech",
            "ACMMM": "ACMMM",
            "MM": "MM",
            "WACV": "WACV",
        }
        return mapping.get(conf, conf.title())

    @staticmethod
    def _looks_like_code_link(url: str) -> bool:
        lowered = url.lower()
        return any(
            token in lowered
            for token in [
                "github.com",
                "gitlab.com",
                "bitbucket.org",
                "codeberg.org",
                "huggingface.co",
                "project",
                "implementation",
                "source-code",
                "source_code",
                "code",
                "software",
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

    @staticmethod
    def _detect_review(
        title: Optional[str],
        abstract: Optional[str],
        comment: Optional[str],
    ) -> bool:
        haystack = " ".join(
            part for part in [title or "", abstract or "", comment or ""] if part
        ).lower()
        return "review" in haystack

    @staticmethod
    def _detect_survey(
        title: Optional[str],
        abstract: Optional[str],
        comment: Optional[str],
    ) -> bool:
        haystack = " ".join(
            part for part in [title or "", abstract or "", comment or ""] if part
        ).lower()
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
        code_links: list[str],
        comment: Optional[str],
        journal_ref: Optional[str],
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
            bool(code_links),
            bool(comment),
            bool(journal_ref),
        ]
        score = sum(1 for flag in checks if flag) / len(checks)
        return round(score, 4)