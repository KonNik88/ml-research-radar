from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Iterable, Optional

from radar_core.contracts.canonical_document import CanonicalDocument, SourceLink
from radar_core.contracts.document import NormalizedDocument
from radar_core.utils.ids import stable_hash


def build_reconciliation_key(doc: NormalizedDocument) -> str:
    """
    Priority of reconciliation keys:
    1. DOI
    2. external DOI
    3. arXiv id
    4. normalized title + year
    """
    if doc.doi:
        return f"doi::{doc.doi.lower().strip()}"

    ext_doi = doc.external_ids.get("doi")
    if ext_doi:
        return f"doi::{ext_doi.lower().strip()}"

    if doc.arxiv_id:
        return f"arxiv::{doc.arxiv_id.lower().strip()}"

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


def choose_first_nonempty_string(
    documents: list[NormalizedDocument],
    attr_name: str,
) -> str | None:
    for doc in documents:
        value = getattr(doc, attr_name, None)
        if isinstance(value, str):
            value = value.strip()
            if value:
                return value
        elif value is not None:
            return str(value)
    return None


def choose_best_published_at(documents: list[NormalizedDocument]) -> Optional[datetime]:
    candidates = [d.published_at for d in documents if d.published_at is not None]
    if not candidates:
        return None
    return min(candidates)


def choose_best_publication_date(documents: list[NormalizedDocument]) -> Optional[datetime]:
    candidates = [d.publication_date for d in documents if d.publication_date is not None]
    if not candidates:
        return None
    return min(candidates)


def choose_best_updated_at(documents: list[NormalizedDocument]) -> Optional[datetime]:
    candidates = [d.updated_source_at for d in documents if d.updated_source_at is not None]
    if not candidates:
        return None
    return max(candidates)


def choose_best_year(documents: list[NormalizedDocument]) -> int | None:
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


def choose_best_arxiv_id(documents: list[NormalizedDocument]) -> str | None:
    for d in documents:
        if d.arxiv_id:
            return d.arxiv_id
    ext = choose_external_id(documents, "arxiv")
    return ext


def choose_best_openalex_id(documents: list[NormalizedDocument]) -> str | None:
    for d in documents:
        if d.openalex_id:
            return d.openalex_id
    ext = choose_external_id(documents, "openalex")
    return ext


def choose_best_pdf_url(documents: list[NormalizedDocument]):
    for d in documents:
        if d.pdf_url:
            return d.pdf_url
    return None


def choose_best_landing_page_url(documents: list[NormalizedDocument]):
    for d in documents:
        if d.landing_page_url:
            return d.landing_page_url
    return None


def choose_best_repo_url(documents: list[NormalizedDocument]):
    for d in documents:
        if d.repo_url:
            return d.repo_url
    return None


def choose_best_primary_category(documents: list[NormalizedDocument]) -> str | None:
    for d in documents:
        if d.primary_category:
            return d.primary_category
    return None


def choose_any_bool(
    documents: list[NormalizedDocument],
    attr_name: str,
) -> bool | None:
    for doc in documents:
        value = getattr(doc, attr_name, None)
        if value is True:
            return True
    for doc in documents:
        value = getattr(doc, attr_name, None)
        if value is False:
            return False
    return None


def choose_max_int(
    documents: list[NormalizedDocument],
    attr_name: str,
) -> int | None:
    candidates = [
        getattr(doc, attr_name)
        for doc in documents
        if getattr(doc, attr_name) is not None
    ]
    if not candidates:
        return None
    return max(candidates)


def choose_external_id(documents: list[NormalizedDocument], key: str) -> str | None:
    for doc in documents:
        value = doc.external_ids.get(key)
        if value:
            return value
    return None


def merge_unique_strings(values: Iterable[Iterable[object]]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []

    for items in values:
        for item in items:
            if item is None:
                continue
            value = str(item).strip()
            if not value:
                continue
            norm = value.lower()
            if norm in seen:
                continue
            seen.add(norm)
            merged.append(value)

    return merged


def merge_source_ids(documents: list[NormalizedDocument]) -> dict[str, str]:
    source_ids: dict[str, str] = {}

    for doc in documents:
        # richer per-source ids first
        for key, value in (doc.source_ids or {}).items():
            if value and key not in source_ids:
                source_ids[key] = value

        # source slot
        if doc.source and doc.source_id and doc.source not in source_ids:
            source_ids[doc.source] = doc.source_id

        # stable ids
        if doc.arxiv_id and "arxiv" not in source_ids:
            source_ids["arxiv"] = doc.arxiv_id

        if doc.openalex_id and "openalex" not in source_ids:
            source_ids["openalex"] = doc.openalex_id

        # fallback from external ids
        for key, value in doc.external_ids.items():
            if value and key not in source_ids:
                source_ids[key] = value

    return source_ids


def merge_external_ids(documents: list[NormalizedDocument]) -> dict[str, str]:
    external_ids: dict[str, str] = {}
    for doc in documents:
        for key, value in (doc.external_ids or {}).items():
            if value and key not in external_ids:
                external_ids[key] = value
    return external_ids


def build_source_links(documents: list[NormalizedDocument]) -> list[SourceLink]:
    links: list[SourceLink] = []

    for d in documents:
        links.append(
            SourceLink(
                source=d.source,
                source_id=d.source_id,
                source_record_id=d.source_record_id,
                source_record_url=d.source_record_url,
                canonical_url=d.canonical_url,
                fetched_at=d.ingested_at,
                source_updated_at=d.updated_source_at,
                source_api_url=d.source_api_url,
                raw_source_name=d.raw_source_name,
                run_ts=None,
            )
        )

    return links


def compute_metadata_completeness_score(documents: list[NormalizedDocument]) -> float | None:
    """
    Simple heuristic score on merged record completeness.
    Returned in [0, 1].
    """
    if not documents:
        return None

    title = choose_best_title(documents)
    abstract = choose_best_abstract(documents)
    authors = merge_unique_strings([d.authors for d in documents])
    doi = choose_best_doi(documents)
    publication_date = choose_best_publication_date(documents)
    primary_category = choose_best_primary_category(documents)
    categories = merge_unique_strings([d.categories for d in documents])
    pdf_url = choose_best_pdf_url(documents)
    venue = choose_first_nonempty_string(documents, "venue")
    cited_by_count = choose_max_int(documents, "cited_by_count")
    references_count = choose_max_int(documents, "references_count")
    has_code_link = any(d.has_code_link for d in documents)

    checks = [
        bool(title),
        bool(abstract),
        bool(authors),
        bool(doi),
        publication_date is not None,
        bool(primary_category),
        bool(categories),
        pdf_url is not None,
        bool(venue),
        cited_by_count is not None,
        references_count is not None,
        has_code_link,
    ]
    score = sum(1 for flag in checks if flag) / len(checks)
    return round(score, 4)


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

        authors = merge_unique_strings([d.authors for d in docs])

        published_at = choose_best_published_at(docs)
        publication_date = choose_best_publication_date(docs)
        updated_at = choose_best_updated_at(docs)
        year = choose_best_year(docs)

        doi = choose_best_doi(docs)
        arxiv_id = choose_best_arxiv_id(docs)
        openalex_id = choose_best_openalex_id(docs)
        source_ids = merge_source_ids(docs)
        external_ids = merge_external_ids(docs)

        pmid = choose_first_nonempty_string(docs, "pmid")
        pmcid = choose_first_nonempty_string(docs, "pmcid")
        semantic_scholar_id = choose_first_nonempty_string(docs, "semantic_scholar_id")
        dblp_id = choose_first_nonempty_string(docs, "dblp_id")
        mag_id = choose_first_nonempty_string(docs, "mag_id")

        landing_page_url = choose_best_landing_page_url(docs)
        pdf_url = choose_best_pdf_url(docs)
        repo_url = choose_best_repo_url(docs)

        license_value = choose_first_nonempty_string(docs, "license")
        open_access = choose_any_bool(docs, "open_access")

        primary_category = choose_best_primary_category(docs)
        categories = merge_unique_strings([d.categories for d in docs])
        concepts = merge_unique_strings([d.concepts for d in docs])
        keywords = merge_unique_strings([d.keywords for d in docs])
        tags = merge_unique_strings([d.tags for d in docs])

        comment = choose_first_nonempty_string(docs, "comment")
        journal_ref = choose_first_nonempty_string(docs, "journal_ref")
        venue = choose_first_nonempty_string(docs, "venue")
        journal = choose_first_nonempty_string(docs, "journal")
        conference = choose_first_nonempty_string(docs, "conference")
        publisher = choose_first_nonempty_string(docs, "publisher")
        publication_type = choose_first_nonempty_string(docs, "publication_type")
        language = choose_first_nonempty_string(docs, "language")

        cited_by_count = choose_max_int(docs, "cited_by_count")
        references_count = choose_max_int(docs, "references_count")
        referenced_ids = merge_unique_strings([d.referenced_ids for d in docs])
        referenced_dois = merge_unique_strings([d.referenced_dois for d in docs])
        referenced_arxiv_ids = merge_unique_strings([d.referenced_arxiv_ids for d in docs])
        citation_graph_available = any(d.citation_graph_available for d in docs)

        has_code_link = any(d.has_code_link for d in docs)
        code_links = merge_unique_strings([d.code_links for d in docs])
        dataset_links = merge_unique_strings([d.dataset_links for d in docs])
        model_links = merge_unique_strings([d.model_links for d in docs])

        has_dataset_link = any(bool(getattr(d, "has_dataset_link", False)) for d in docs) or bool(dataset_links)
        has_model_link = any(bool(getattr(d, "has_model_link", False)) for d in docs) or bool(model_links)

        unique_source_count = len({d.source for d in docs if d.source})

        is_open_access = choose_any_bool(docs, "is_open_access")
        is_preprint = choose_any_bool(docs, "is_preprint")
        is_review = any(bool(getattr(d, "is_review", False)) for d in docs)
        is_survey = any(bool(getattr(d, "is_survey", False)) for d in docs)
        is_withdrawn = any(bool(d.is_withdrawn) for d in docs)

        metadata_completeness_score = compute_metadata_completeness_score(docs)

        canonical_documents.append(
            CanonicalDocument(
                canonical_id=canonical_id,
                doc_ids=[d.doc_id for d in docs],
                doi=doi,
                arxiv_id=arxiv_id,
                openalex_id=openalex_id,
                source_ids=source_ids,
                external_ids=external_ids,
                pmid=pmid,
                pmcid=pmcid,
                semantic_scholar_id=semantic_scholar_id,
                dblp_id=dblp_id,
                mag_id=mag_id,
                title=title,
                abstract=abstract,
                authors=authors,
                published_at=published_at,
                publication_date=publication_date,
                updated_at=updated_at,
                year=year,
                landing_page_url=landing_page_url,
                pdf_url=pdf_url,
                repo_url=repo_url,
                license=license_value,
                open_access=open_access,
                primary_category=primary_category,
                categories=categories,
                concepts=concepts,
                keywords=keywords,
                tags=tags,
                comment=comment,
                journal_ref=journal_ref,
                venue=venue,
                journal=journal,
                conference=conference,
                publisher=publisher,
                publication_type=publication_type,
                language=language,
                cited_by_count=cited_by_count,
                references_count=references_count,
                referenced_ids=referenced_ids,
                referenced_dois=referenced_dois,
                referenced_arxiv_ids=referenced_arxiv_ids,
                citation_graph_available=citation_graph_available,
                has_code_link=has_code_link,
                code_links=code_links,
                dataset_links=dataset_links,
                model_links=model_links,
                has_dataset_link=has_dataset_link,
                has_model_link=has_model_link,
                sources=build_source_links(docs),
                source_count=len(docs),
                unique_source_count=unique_source_count,
                metadata_completeness_score=metadata_completeness_score,
                is_open_access=is_open_access,
                is_preprint=is_preprint,
                is_review=is_review,
                is_survey=is_survey,
                is_withdrawn=is_withdrawn,
                reconciliation_key=reconciliation_key,
            )
        )

    canonical_documents.sort(
        key=lambda d: (
            d.year or 0,
            d.cited_by_count or 0,
            d.title.lower(),
        ),
        reverse=True,
    )
    return canonical_documents