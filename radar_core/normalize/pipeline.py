from __future__ import annotations

from typing import Iterable, List

from radar_core.contracts.document import NormalizedDocument


def deduplicate_documents(documents: Iterable[NormalizedDocument]) -> List[NormalizedDocument]:
    """
    Deduplication within a single ingest run.

    Current policy:
    - one doc_id -> one record
    - if the same doc_id appears multiple times, keep the richer / newer record
    """
    by_doc_id: dict[str, NormalizedDocument] = {}

    for doc in documents:
        existing = by_doc_id.get(doc.doc_id)
        if existing is None:
            by_doc_id[doc.doc_id] = doc
            continue

        existing_score = _document_richness_score(existing)
        new_score = _document_richness_score(doc)

        if new_score > existing_score:
            by_doc_id[doc.doc_id] = doc
        elif new_score == existing_score:
            existing_updated = existing.updated_source_at
            new_updated = doc.updated_source_at

            if existing_updated is None and new_updated is not None:
                by_doc_id[doc.doc_id] = doc
            elif (
                existing_updated is not None
                and new_updated is not None
                and new_updated > existing_updated
            ):
                by_doc_id[doc.doc_id] = doc

    return list(by_doc_id.values())


def split_new_vs_updated(
    documents: Iterable[NormalizedDocument],
    existing_content_hash_by_doc_id: dict[str, str],
) -> tuple[list[NormalizedDocument], list[NormalizedDocument], list[NormalizedDocument]]:
    """
    Returns:
    - new_docs
    - updated_docs
    - unchanged_docs
    """
    new_docs: list[NormalizedDocument] = []
    updated_docs: list[NormalizedDocument] = []
    unchanged_docs: list[NormalizedDocument] = []

    for doc in documents:
        old_hash = existing_content_hash_by_doc_id.get(doc.doc_id)

        if old_hash is None:
            new_docs.append(doc)
        elif old_hash != doc.content_hash:
            updated_docs.append(doc)
        else:
            unchanged_docs.append(doc)

    return new_docs, updated_docs, unchanged_docs


def _document_richness_score(doc: NormalizedDocument) -> int:
    score = 0

    # ===== core content =====
    if doc.title:
        score += 3
    if doc.abstract:
        score += 3
    if doc.authors:
        score += 2

    # ===== stable ids =====
    if doc.doi:
        score += 2
    if doc.arxiv_id:
        score += 2
    if doc.openalex_id:
        score += 2

    # additional external/source ids
    if doc.external_ids:
        score += min(len(doc.external_ids), 3)
    if getattr(doc, "source_ids", None):
        score += min(len(doc.source_ids), 2)

    # ===== dates / provenance =====
    if doc.publication_date is not None:
        score += 1
    if doc.published_at is not None:
        score += 1
    if doc.updated_source_at is not None:
        score += 1

    # ===== taxonomy =====
    if doc.primary_category:
        score += 1
    if doc.categories:
        score += 1
    if doc.concepts:
        score += 1
    if doc.keywords:
        score += 1
    if doc.tags:
        score += 1

    # ===== access / links =====
    if doc.pdf_url is not None:
        score += 1
    if doc.landing_page_url is not None:
        score += 1
    if doc.repo_url is not None:
        score += 1
    if doc.code_links:
        score += 1
    if getattr(doc, "dataset_links", None):
        score += 1
    if getattr(doc, "model_links", None):
        score += 1
    if doc.license:
        score += 1
    if doc.open_access is True:
        score += 1

    # ===== publication metadata =====
    if doc.venue:
        score += 1
    if doc.journal:
        score += 1
    if doc.conference:
        score += 1
    if doc.publisher:
        score += 1
    if doc.publication_type:
        score += 1
    if doc.language:
        score += 1
    if doc.comment:
        score += 1
    if doc.journal_ref:
        score += 1

    # ===== citation / graph-ready =====
    if doc.cited_by_count is not None:
        score += 1
    if doc.references_count is not None:
        score += 1
    if doc.referenced_ids:
        score += 1
    if doc.referenced_dois:
        score += 1
    if doc.referenced_arxiv_ids:
        score += 1
    if doc.citation_graph_available:
        score += 1

    # ===== optional quality hints =====
    if doc.metadata_completeness_score is not None:
        score += 1
    if getattr(doc, "is_open_access", None) is True:
        score += 1
    if getattr(doc, "is_preprint", None) is True:
        score += 1

    return score