from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlencode

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
from radar_core.ingest.pwc_client import (
    DEFAULT_PWC_API_BASE,
    fetch_pwc_entry,
)


DEFAULT_PWC_API_BASE = "https://paperswithcode.com/api/v1"

REPO_HOST_HINTS = (
    "github.com",
    "gitlab.com",
    "bitbucket.org",
    "codeberg.org",
    "huggingface.co",
)

DATASET_HOST_HINTS = (
    "kaggle.com",
    "huggingface.co/datasets",
    "zenodo.org",
    "figshare.com",
    "data.mendeley.com",
    "datadryad.org",
)

MODEL_HOST_HINTS = (
    "huggingface.co",
    "replicate.com",
    "civitai.com",
)

DOI_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
    "doi:",
)

ARXIV_PREFIXES = (
    "https://arxiv.org/abs/",
    "http://arxiv.org/abs/",
    "https://export.arxiv.org/abs/",
    "http://export.arxiv.org/abs/",
    "arxiv:",
)

URL_RE = re.compile(r"https?://[^\s<>)\]}\"']+")


@dataclass
class PapersWithCodeQuery:
    dois: list[str] = field(default_factory=list)
    arxiv_ids: list[str] = field(default_factory=list)
    timeout: int = 60
    api_base: str = DEFAULT_PWC_API_BASE
    sleep_seconds: float = 0.0
    max_results_per_identifier: int = 5


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_doi(value: Any) -> Optional[str]:
    text = _normalize_text(value)
    if not text:
        return None
    lowered = text.lower().strip()
    for prefix in DOI_PREFIXES:
        if lowered.startswith(prefix):
            lowered = lowered[len(prefix):].strip()
            break
    lowered = lowered.strip().strip("/")
    return lowered or None


def _normalize_arxiv_id(value: Any) -> Optional[str]:
    text = _normalize_text(value)
    if not text:
        return None
    lowered = text.lower().strip()
    for prefix in ARXIV_PREFIXES:
        if lowered.startswith(prefix):
            lowered = lowered[len(prefix):].strip()
            break
    lowered = lowered.strip().strip("/")
    return lowered or None


def _parse_dt(value: Any) -> Optional[datetime]:
    text = _normalize_text(value)
    if not text:
        return None

    candidates = [text]
    if text.endswith("Z"):
        candidates.append(text.replace("Z", "+00:00"))

    for candidate in candidates:
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def _extract_first_url(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        match = URL_RE.search(value)
        return match.group(0).strip() if match else None
    return None


def _looks_like_repo(url: str) -> bool:
    lowered = url.lower()
    return any(host in lowered for host in REPO_HOST_HINTS)


def _looks_like_dataset(url: str) -> bool:
    lowered = url.lower()
    return any(host in lowered for host in DATASET_HOST_HINTS)


def _looks_like_model(url: str) -> bool:
    lowered = url.lower()
    return any(host in lowered for host in MODEL_HOST_HINTS)


def _dedupe_preserve(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        value = item.strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _extract_authors(entry: dict[str, Any]) -> list[str]:
    authors_raw = (
        entry.get("authors")
        or entry.get("paper_authors")
        or entry.get("author_names")
        or []
    )

    authors: list[str] = []

    if isinstance(authors_raw, list):
        for item in authors_raw:
            if isinstance(item, str):
                name = item.strip()
                if name:
                    authors.append(name)
                continue

            if isinstance(item, dict):
                for key in ("name", "full_name", "author_name", "display_name"):
                    name = _normalize_text(item.get(key))
                    if name:
                        authors.append(name)
                        break

    return _dedupe_preserve(authors)


def _extract_title(entry: dict[str, Any]) -> str:
    for key in ("title", "paper_title", "name"):
        value = _normalize_text(entry.get(key))
        if value:
            return value
    return ""


def _extract_abstract(entry: dict[str, Any]) -> Optional[str]:
    for key in ("abstract", "paper_abstract", "summary", "description"):
        value = _normalize_text(entry.get(key))
        if value:
            return value
    return None


def _extract_year(entry: dict[str, Any], publication_date: Optional[datetime]) -> Optional[int]:
    for key in ("year", "published_year"):
        raw = entry.get(key)
        try:
            if raw is not None:
                value = int(raw)
                if 1900 <= value <= datetime.now(timezone.utc).year + 1:
                    return value
        except (TypeError, ValueError):
            pass
    if publication_date is not None:
        return publication_date.year
    return None


def _extract_publication_date(entry: dict[str, Any]) -> Optional[datetime]:
    for key in ("published", "publication_date", "created_at", "updated_at"):
        dt = _parse_dt(entry.get(key))
        if dt is not None:
            return dt
    return None


def _extract_identifier(entry: dict[str, Any], keys: tuple[str, ...]) -> Optional[str]:
    for key in keys:
        value = _normalize_text(entry.get(key))
        if value:
            return value
    return None


def _extract_doi(entry: dict[str, Any]) -> Optional[str]:
    doi = _extract_identifier(entry, ("doi", "paper_doi"))
    if doi:
        return _normalize_doi(doi)

    ext = entry.get("external_ids") or {}
    if isinstance(ext, dict):
        for key in ("doi", "DOI"):
            if key in ext:
                normalized = _normalize_doi(ext.get(key))
                if normalized:
                    return normalized
    return None


def _extract_arxiv_id(entry: dict[str, Any]) -> Optional[str]:
    for key in ("arxiv_id", "paper_arxiv_id"):
        normalized = _normalize_arxiv_id(entry.get(key))
        if normalized:
            return normalized

    ext = entry.get("external_ids") or {}
    if isinstance(ext, dict):
        for key in ("arxiv", "ArXiv", "arxiv_id"):
            if key in ext:
                normalized = _normalize_arxiv_id(ext.get(key))
                if normalized:
                    return normalized
    return None


def _extract_landing_page_url(entry: dict[str, Any], paper_id: Optional[str], arxiv_id: Optional[str], doi: Optional[str]) -> Optional[str]:
    for key in ("url", "paper_url", "html_url"):
        url = _extract_first_url(entry.get(key))
        if url:
            return url

    if paper_id:
        return f"https://paperswithcode.com/paper/{paper_id}"
    if arxiv_id:
        return f"https://huggingface.co/papers/{arxiv_id}"
    if doi:
        return f"https://doi.org/{doi}"
    return None


def _collect_candidate_urls(entry: dict[str, Any]) -> list[str]:
    urls: list[str] = []

    def add(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, str):
            url = _extract_first_url(value)
            if url:
                urls.append(url)
            return
        if isinstance(value, dict):
            for key in ("url", "repo_url", "repository_url", "github_url", "link"):
                url = _extract_first_url(value.get(key))
                if url:
                    urls.append(url)
            return
        if isinstance(value, list):
            for item in value:
                add(item)

    for key in (
        "url",
        "paper_url",
        "repository",
        "repositories",
        "official",
        "official_repository",
        "implementation",
        "implementations",
        "code",
        "code_links",
        "dataset",
        "datasets",
        "model",
        "models",
        "links",
    ):
        add(entry.get(key))

    return _dedupe_preserve(urls)


def _extract_asset_links(entry: dict[str, Any]) -> tuple[Optional[str], list[str], list[str], list[str]]:
    all_urls = _collect_candidate_urls(entry)

    repo_links = [u for u in all_urls if _looks_like_repo(u)]
    dataset_links = [u for u in all_urls if _looks_like_dataset(u)]
    model_links = [u for u in all_urls if _looks_like_model(u)]

    repo_url = repo_links[0] if repo_links else None
    return repo_url, repo_links, dataset_links, model_links


def _extract_tags(entry: dict[str, Any]) -> list[str]:
    values: list[str] = []

    for key in ("tasks", "datasets", "benchmarks", "methods", "tags"):
        raw = entry.get(key)
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, str):
                    text = item.strip()
                    if text:
                        values.append(text)
                elif isinstance(item, dict):
                    for name_key in ("name", "full_name", "display_name"):
                        text = _normalize_text(item.get(name_key))
                        if text:
                            values.append(text)
                            break

    return _dedupe_preserve(values)


def _extract_page_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        return []

    for key in ("results", "items", "papers", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    if payload:
        return [payload]

    return []


def fetch_pwc_entry(
    *,
    doi: Optional[str],
    arxiv_id: Optional[str],
    timeout: int = 60,
    api_base: str = DEFAULT_PWC_API_BASE,
    max_results_per_identifier: int = 5,
) -> Optional[dict[str, Any]]:
    """
    Conservative adapter:
    tries a small set of likely search query shapes and returns the first
    result that strongly matches DOI or arXiv id.

    This isolates the fetch layer because the public PWC surface has changed over time.
    """
    session = requests.Session()
    base = api_base.rstrip("/")

    candidates: list[tuple[str, dict[str, Any]]] = []

    if doi:
        candidates.extend(
            [
                (f"{base}/papers/", {"doi": doi, "page_size": max_results_per_identifier}),
                (f"{base}/papers/", {"q": doi, "page_size": max_results_per_identifier}),
            ]
        )

    if arxiv_id:
        candidates.extend(
            [
                (f"{base}/papers/", {"arxiv_id": arxiv_id, "page_size": max_results_per_identifier}),
                (f"{base}/papers/", {"q": arxiv_id, "page_size": max_results_per_identifier}),
            ]
        )

    for url, params in candidates:
        try:
            response = session.get(url, params=params, timeout=timeout)
            if response.status_code == 404:
                continue
            response.raise_for_status()
            payload = response.json()
        except Exception:
            continue

        rows = _extract_page_payload(payload)
        if not rows:
            continue

        wanted_doi = _normalize_doi(doi)
        wanted_arxiv = _normalize_arxiv_id(arxiv_id)

        for row in rows:
            row_doi = _extract_doi(row)
            row_arxiv = _extract_arxiv_id(row)

            if wanted_doi and row_doi and wanted_doi == row_doi:
                return row
            if wanted_arxiv and row_arxiv and wanted_arxiv == row_arxiv:
                return row

        # if API shape is weak, still return first candidate only if exactly one row exists
        if len(rows) == 1:
            return rows[0]

    return None


class PapersWithCodeIngestor(BaseIngestor[PapersWithCodeQuery, dict, dict]):
    source_name = "paperswithcode"
    pipeline_version = "0.1.0"

    def fetch_feed(self, query: PapersWithCodeQuery) -> dict[str, Any]:
        items: list[dict[str, Any]] = []

        seen_keys: set[str] = set()

        for doi in query.dois:
            normalized_doi = _normalize_doi(doi)
            if not normalized_doi:
                continue
            key = f"doi::{normalized_doi}"
            if key in seen_keys:
                continue
            seen_keys.add(key)

            entry = fetch_pwc_entry(
                doi=normalized_doi,
                arxiv_id=None,
                timeout=query.timeout,
                api_base=query.api_base,
                max_results_per_identifier=query.max_results_per_identifier,
            )
            if entry:
                items.append(entry)

        for arxiv_id in query.arxiv_ids:
            normalized_arxiv = _normalize_arxiv_id(arxiv_id)
            if not normalized_arxiv:
                continue
            key = f"arxiv::{normalized_arxiv}"
            if key in seen_keys:
                continue
            seen_keys.add(key)

            entry = fetch_pwc_entry(
                doi=None,
                arxiv_id=normalized_arxiv,
                timeout=query.timeout,
                api_base=query.api_base,
                max_results_per_identifier=query.max_results_per_identifier,
            )
            if entry:
                items.append(entry)

        return {"results": items}

    def iter_entries(self, feed: dict[str, Any]) -> list[dict]:
        return list(feed.get("results") or [])

    def parse_entry_to_raw(self, entry: dict) -> RawDocument:
        doi = _extract_doi(entry)
        arxiv_id = _extract_arxiv_id(entry)
        paper_id = _extract_identifier(entry, ("id", "paper_id", "slug"))
        landing_page_url = _extract_landing_page_url(entry, paper_id, arxiv_id, doi)
        canonical_url = canonicalize_url(
            landing_page_url
            or (f"https://huggingface.co/papers/{arxiv_id}" if arxiv_id else f"https://doi.org/{doi}" if doi else "https://paperswithcode.com")
        )
        doc_id = build_doc_id(canonical_url)

        source_id = paper_id or doi or arxiv_id or canonical_url
        updated_source_at = _parse_dt(entry.get("updated_at")) or _parse_dt(entry.get("created_at"))

        payload = {
            "id": entry.get("id"),
            "paper_id": entry.get("paper_id"),
            "slug": entry.get("slug"),
            "title": entry.get("title"),
            "abstract": entry.get("abstract"),
            "doi": doi,
            "arxiv_id": arxiv_id,
            "url": entry.get("url"),
            "paper_url": entry.get("paper_url"),
            "repositories": entry.get("repositories"),
            "implementation": entry.get("implementation"),
            "official_repository": entry.get("official_repository"),
            "datasets": entry.get("datasets"),
            "models": entry.get("models"),
            "tasks": entry.get("tasks"),
            "benchmarks": entry.get("benchmarks"),
            "authors": entry.get("authors"),
            "published": entry.get("published"),
            "created_at": entry.get("created_at"),
            "updated_at": entry.get("updated_at"),
        }

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
                source_api_url=None,
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
            payload=payload,
            updated_at=_utc_now(),
        )

    def parse_entry_to_normalized(
        self,
        entry: dict,
        raw_artifact_path: str | None = None,
    ) -> NormalizedDocument:
        doi = _extract_doi(entry)
        arxiv_id = _extract_arxiv_id(entry)
        paper_id = _extract_identifier(entry, ("id", "paper_id", "slug"))

        title = _extract_title(entry)
        abstract = _extract_abstract(entry)
        authors = _extract_authors(entry)

        publication_date = _extract_publication_date(entry)
        updated_source_at = _parse_dt(entry.get("updated_at")) or _parse_dt(entry.get("created_at"))
        year = _extract_year(entry, publication_date)

        repo_url, code_links, dataset_links, model_links = _extract_asset_links(entry)
        tags = _extract_tags(entry)

        landing_page_url = _extract_landing_page_url(entry, paper_id, arxiv_id, doi)
        canonical_url = canonicalize_url(
            landing_page_url
            or (f"https://huggingface.co/papers/{arxiv_id}" if arxiv_id else f"https://doi.org/{doi}" if doi else "https://paperswithcode.com")
        )
        doc_id = build_doc_id(canonical_url)
        content_hash = build_content_hash(title=title, abstract=abstract or "")

        source_id = paper_id or doi or arxiv_id or canonical_url

        source_ids: dict[str, str] = {}
        external_ids: dict[str, str] = {}

        if paper_id:
            source_ids["paperswithcode"] = paper_id
            external_ids["paperswithcode"] = paper_id

        if doi:
            external_ids["doi"] = doi

        if arxiv_id:
            external_ids["arxiv"] = arxiv_id
            source_ids["arxiv"] = arxiv_id

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
            source_api_url=None,
            external_ids=external_ids,

            doi=doi,
            arxiv_id=arxiv_id,
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
            pdf_url=None,
            repo_url=repo_url,
            license=None,
            open_access=None,

            primary_category=None,
            categories=[],
            concepts=[],
            keywords=[],
            tags=tags,

            comment=None,
            journal_ref=None,
            venue=None,
            journal=None,
            conference=None,
            publisher=None,
            publication_type=None,
            language="en",

            cited_by_count=None,
            references_count=None,
            referenced_ids=[],
            referenced_dois=[],
            referenced_arxiv_ids=[],
            citation_graph_available=False,

            has_code_link=bool(code_links or repo_url),
            code_links=code_links,
            dataset_links=dataset_links,
            model_links=model_links,
            has_dataset_link=bool(dataset_links),
            has_model_link=bool(model_links),

            has_pdf=False,
            is_withdrawn=False,

            is_open_access=None,
            is_preprint=None,
            is_review=False,
            is_survey=False,

            raw_artifact_path=raw_artifact_path,
            raw_source_name=self.source_name,
            ingested_at=_utc_now(),
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