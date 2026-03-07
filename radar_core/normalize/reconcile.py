from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from radar_core.contracts.canonical_document import CanonicalDocument, SourceLink
from radar_core.contracts.document import NormalizedDocument
from radar_core.utils.ids import stable_hash


def build_reconciliation_key(doc: NormalizedDocument) -> str:
    """
    Порядок силы ключей:
    1. DOI
    2. source-specific external DOI
    3. normalized title + year
    """
    if doc.doi:
        return f"doi::{doc.doi.lower().strip()}"

    ext_doi = doc.external_ids.get("doi")
    if ext_doi:
        return f"doi::{ext_doi.lower().strip()}"

    title = (doc.title or "").strip().lower()
    year = str(doc.year) if doc.year is not None else "unknown"
    return f"title_year::{title}::{year}"


def build_canonical_id(reconciliation_key: str) -> str:
    return stable_hash(reconciliation_key, length=32)


def choose_best_title(documents: list[NormalizedDocument]) -> str:
    docs = sorted(
        documents,
        key=lambda d: (len(d.title or ""), d.source == "openalex"),
        reverse=True,
    )
    return docs[0].title


def choose_best_abstract(documents: list[NormalizedDocument]) -> str | None:
    docs = [d for d in documents if d.abstract]
    if not docs:
        return None
    docs = sorted(
        docs,
        key=lambda d: (len(d.abstract or ""), d.source == "openalex"),
        reverse=True,
    )
    return docs[0].abstract


def choose_best_published_at(documents: list[NormalizedDocument]):
    candidates = [d.published_at for d in documents if d.published_at is not None]
    if not candidates:
        return None
    return min(candidates)


def choose_best_updated_at(documents: list[NormalizedDocument]):
    candidates = [d.updated_source_at for d in documents if d.updated_source_at is not None]
    if not candidates:
        return None
    return max(candidates)


def choose_best_year(documents: list[NormalizedDocument]):
    candidates = [d.year for d in documents if d.year is not None]
    if not candidates:
        return None
    return min(candidates)


def choose_best_doi(documents: list[NormalizedDocument]) -> str | None:
    for d in documents:
        if d.doi:
            return d.doi
    for d in documents:
        ext_doi = d.external_ids.get("doi")
        if ext_doi:
            return ext_doi
    return None


def choose_best_pdf_url(documents: list[NormalizedDocument]):
    for d in documents:
        if d.pdf_url:
            return d.pdf_url
    return None


def choose_best_primary_category(documents: list[NormalizedDocument]) -> str | None:
    for d in documents:
        if d.primary_category:
            return d.primary_category
    return None


def merge_unique_lists(values: Iterable[list[str]]) -> list[str]:
    seen = set()
    merged: list[str] = []
    for items in values:
        for item in items:
            if not item:
                continue
            key = item.strip()
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(key)
    return merged


def build_source_links(documents: list[NormalizedDocument]) -> list[SourceLink]:
    links: list[SourceLink] = []
    for d in documents:
        links.append(
            SourceLink(
                source=d.source,
                source_id=d.source_id,
                source_record_url=d.source_record_url,
                canonical_url=d.canonical_url,
            )
        )
    return links


def reconcile_documents(documents: list[NormalizedDocument]) -> list[CanonicalDocument]:
    grouped: dict[str, list[NormalizedDocument]] = defaultdict(list)

    for doc in documents:
        key = build_reconciliation_key(doc)
        grouped[key].append(doc)

    canonical_documents: list[CanonicalDocument] = []

    for reconciliation_key, docs in grouped.items():
        canonical_id = build_canonical_id(reconciliation_key)

        title = choose_best_title(docs)
        abstract = choose_best_abstract(docs)
        authors = merge_unique_lists([d.authors for d in docs])
        published_at = choose_best_published_at(docs)
        updated_at = choose_best_updated_at(docs)
        year = choose_best_year(docs)
        doi = choose_best_doi(docs)
        pdf_url = choose_best_pdf_url(docs)
        primary_category = choose_best_primary_category(docs)
        categories = merge_unique_lists([d.categories for d in docs])
        tags = merge_unique_lists([d.tags for d in docs])

        language = None
        for d in docs:
            if d.language:
                language = d.language
                break

        canonical_documents.append(
            CanonicalDocument(
                canonical_id=canonical_id,
                doc_ids=[d.doc_id for d in docs],
                title=title,
                abstract=abstract,
                authors=authors,
                published_at=published_at,
                updated_at=updated_at,
                year=year,
                doi=doi,
                pdf_url=pdf_url,
                primary_category=primary_category,
                categories=categories,
                tags=tags,
                language=language,
                sources=build_source_links(docs),
                source_count=len(docs),
                reconciliation_key=reconciliation_key,
            )
        )

    canonical_documents.sort(key=lambda d: (d.year or 0, d.title.lower()), reverse=True)
    return canonical_documents