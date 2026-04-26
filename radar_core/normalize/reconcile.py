from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import re
from typing import Iterable, Optional, Any

from radar_core.contracts.canonical_document import CanonicalDocument, SourceLink
from radar_core.contracts.document import NormalizedDocument
from radar_core.utils.ids import stable_hash


CURRENT_YEAR_UTC = datetime.utcnow().year
MAX_REASONABLE_FUTURE_YEAR = CURRENT_YEAR_UTC + 1

SOURCE_PRIORITY_DEFAULT = {
    "openalex": 100,
    "crossref": 95,
    "arxiv": 80,
    "semantic_scholar": 70,
}

SOURCE_PRIORITY_COMMENT = {
    "arxiv": 100,
    "openalex": 80,
}

SOURCE_PRIORITY_BIBLIO = {
    "crossref": 100,
    "openalex": 95,
    "semantic_scholar": 80,
    "arxiv": 60,
}

SOURCE_PRIORITY_VENUE = {
    "openalex": 100,
    "crossref": 95,
    "semantic_scholar": 80,
    "arxiv": 60,
}

SOURCE_PRIORITY_LICENSE = {
    "openalex": 100,
    "crossref": 90,
    "semantic_scholar": 70,
    "arxiv": 60,
}

SOURCE_PRIORITY_ARTIFACTS = {
    "arxiv": 80,
    "openalex": 60,
    "semantic_scholar": 50,
    "crossref": 40,
}

def normalize_title_for_key(title: str) -> str:
    value = (title or "").strip().lower()
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"[^\w\s]", "", value)
    return value.strip()

def looks_like_series_title(value: str | None) -> bool:
    if not value:
        return False

    text = value.strip().lower()
    patterns = [
        "lecture notes in",
        "springer series",
        "advances in intelligent systems",
        "communications in computer and information science",
    ]
    return any(p in text for p in patterns)

def normalize_venue_fields(
    publication_type: str | None,
    venue: str | None,
    journal: str | None,
    conference: str | None,
) -> tuple[str | None, str | None, str | None]:
    pub = (publication_type or "").strip().lower()

    # book-chapter / proceedings-like records:
    # keep container in venue, but avoid pretending it is a journal
    if pub == "book-chapter":
        if journal and looks_like_series_title(journal):
            journal = None
        if conference and looks_like_series_title(conference):
            conference = None

    # if conference record has no conference field but venue looks fine, reuse venue
    if pub == "conference" and not conference and venue:
        conference = venue

    return venue, journal, conference

def normalize_license_value(value: str | None) -> str | None:
    if not value:
        return None

    text = str(value).strip().lower()
    if not text:
        return None

    text = text.replace("_", "-").replace(" ", "-")

    known_map = {
        "cc-by": "cc-by",
        "cc-by-4.0": "cc-by",
        "cc-by-sa": "cc-by-sa",
        "cc-by-sa-4.0": "cc-by-sa",
        "cc-by-nc": "cc-by-nc",
        "cc-by-nc-4.0": "cc-by-nc",
        "cc-by-nc-sa": "cc-by-nc-sa",
        "cc-by-nc-sa-4.0": "cc-by-nc-sa",
        "cc-by-nc-nd": "cc-by-nc-nd",
        "cc-by-nc-nd-4.0": "cc-by-nc-nd",
        "cc0": "cc0",
        "cc0-1.0": "cc0",
    }

    if text in known_map:
        return known_map[text]

    if "creativecommons.org/licenses/by/" in text:
        return "cc-by"
    if "creativecommons.org/licenses/by-sa/" in text:
        return "cc-by-sa"
    if "creativecommons.org/licenses/by-nc/" in text:
        return "cc-by-nc"
    if "creativecommons.org/licenses/by-nc-sa/" in text:
        return "cc-by-nc-sa"
    if "creativecommons.org/licenses/by-nc-nd/" in text:
        return "cc-by-nc-nd"
    if "creativecommons.org/publicdomain/zero/" in text:
        return "cc0"

    if "elsevier.com/tdm" in text:
        return "publisher-tdm-policy"
    if "springer.com/tdm" in text or "springernature.com" in text:
        return "publisher-tdm-policy"
    if "ieeexplore.ieee.org" in text and "license" in text:
        return "publisher-license-page"
    if "acm.org/publications/policies/copyright_policy" in text:
        return "publisher-copyright-policy"

    return text

def choose_best_license(documents: list[NormalizedDocument]) -> str | None:
    candidates: list[tuple[int, int, str]] = []

    for doc in documents:
        raw_value = getattr(doc, "license", None)
        norm_value = normalize_license_value(raw_value)
        if not norm_value:
            continue

        priority = SOURCE_PRIORITY_LICENSE.get(doc.source or "", 0)

        # Предпочитаем настоящие license labels над policy URLs
        quality = 0
        if norm_value.startswith("cc-") or norm_value == "cc0":
            quality = 100
        elif norm_value == "publisher-tdm-policy":
            quality = 30
        elif norm_value == "publisher-license-page":
            quality = 20
        elif norm_value == "publisher-copyright-policy":
            quality = 10

        candidates.append((quality, priority, norm_value))

    if not candidates:
        return None

    candidates.sort(reverse=True)
    return candidates[0][2]

def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result

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

    ext_arxiv = doc.external_ids.get("arxiv")
    if ext_arxiv:
        return f"arxiv::{ext_arxiv.lower().strip()}"

    title = normalize_title_for_key(doc.title or "")
    year = str(doc.year) if doc.year is not None else "unknown"
    return f"title_year::{title}::{year}"


def build_canonical_id(reconciliation_key: str) -> str:
    return stable_hash(reconciliation_key, length=32)

def choose_best_publication_type(documents: list[NormalizedDocument]) -> str | None:
    """
    Conservative publication_type merge.

    Rules:
    - prefer a non-preprint publication type if any source provides it;
    - otherwise fall back to normal priority-based selection.
    """
    non_preprint_docs = [
        d for d in documents
        if getattr(d, "publication_type", None)
        and not bool(getattr(d, "is_preprint", False))
    ]
    if non_preprint_docs:
        return choose_preferred_string(
            non_preprint_docs,
            "publication_type",
            source_priority=SOURCE_PRIORITY_BIBLIO,
            prefer_longer=False,
        )

    return choose_preferred_string(
        documents,
        "publication_type",
        source_priority=SOURCE_PRIORITY_BIBLIO,
        prefer_longer=False,
    )

def choose_canonical_open_access(
    documents: list[NormalizedDocument],
) -> bool | None:
    """
    Manifestation-level OA:
    True if any source clearly indicates an open-access manifestation exists.
    This includes arXiv and OA publisher/API signals.
    """
    explicit_true = [
        d for d in documents
        if getattr(d, "open_access", None) is True
    ]
    if explicit_true:
        return True

    explicit_false = [
        d for d in documents
        if getattr(d, "open_access", None) is False
    ]
    if explicit_false:
        return False

    return None

def choose_canonical_is_open_access(
    documents: list[NormalizedDocument],
) -> bool | None:
    """
    Strict bibliographic OA signal.

    True  -> confirmed by non-arXiv source
    False -> confirmed closed by non-arXiv source and no non-arXiv OA signal
    None  -> only arXiv/open manifestation evidence exists, but no bibliographic confirmation
    """
    non_arxiv_docs = [d for d in documents if (d.source or "") != "arxiv"]

    non_arxiv_true = [
        d for d in non_arxiv_docs
        if getattr(d, "is_open_access", None) is True
        or getattr(d, "open_access", None) is True
    ]
    if non_arxiv_true:
        return True

    non_arxiv_false = [
        d for d in non_arxiv_docs
        if getattr(d, "is_open_access", None) is False
        or getattr(d, "open_access", None) is False
    ]
    if non_arxiv_false:
        return False

    # only arXiv/open-manifestation evidence exists -> unknown for bibliographic OA
    return None

def choose_canonical_is_preprint(
    documents: list[NormalizedDocument],
    publication_type: str | None,
) -> bool | None:
    """
    Canonical preprint flag should not be an unconditional OR across sources.

    If any source clearly represents a journal/article/proceedings publication,
    canonical paper is not treated as purely preprint anymore.
    """
    has_explicit_non_preprint = any(
        getattr(d, "publication_type", None) and not bool(getattr(d, "is_preprint", False))
        for d in documents
    )
    if has_explicit_non_preprint:
        return False

    explicit_flags = [
        getattr(d, "is_preprint", None)
        for d in documents
        if getattr(d, "is_preprint", None) is not None
    ]
    if explicit_flags:
        return any(bool(v) for v in explicit_flags)

    if publication_type:
        text = str(publication_type).strip().lower()
        if text in {"preprint", "working paper"}:
            return True
        if text in {"article", "journal-article", "journal article", "conference", "proceedings", "book-chapter"}:
            return False

    return None


def choose_best_title(documents: list[NormalizedDocument]) -> str:
    docs = sorted(
        documents,
        key=lambda d: (len(d.title or ""), d.source == "openalex"),
        reverse=True,
    )
    return docs[0].title

def sort_documents_by_priority(
    documents: list[NormalizedDocument],
    source_priority: dict[str, int],
) -> list[NormalizedDocument]:
    return sorted(
        documents,
        key=lambda d: source_priority.get(d.source or "", 0),
        reverse=True,
    )

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


def choose_preferred_string(
    documents: list[NormalizedDocument],
    attr_name: str,
    *,
    source_priority: dict[str, int] | None = None,
    prefer_longer: bool = False,
) -> str | None:
    source_priority = source_priority or SOURCE_PRIORITY_DEFAULT
    candidates: list[tuple[int, int, str]] = []

    for doc in documents:
        value = getattr(doc, attr_name, None)
        if isinstance(value, str):
            value = value.strip()
            if not value:
                continue
        elif value is None:
            continue
        else:
            value = str(value).strip()
            if not value:
                continue

        priority = source_priority.get(doc.source or "", 0)
        length_score = len(value) if prefer_longer else 0
        candidates.append((priority, length_score, value))

    if not candidates:
        return None

    candidates.sort(reverse=True)
    return candidates[0][2]


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
    candidates = []
    for d in documents:
        value = d.updated_source_at
        if value is None:
            continue
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        candidates.append(value)

    if not candidates:
        return None
    return max(candidates)


def choose_best_year(documents: list[NormalizedDocument]) -> int | None:
    candidates = [
        d.year for d in documents
        if d.year is not None and 1900 <= d.year <= MAX_REASONABLE_FUTURE_YEAR
    ]
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
    docs_with_repo = [d for d in documents if d.repo_url]
    if not docs_with_repo:
        return None

    docs_with_repo.sort(
        key=lambda d: (
            SOURCE_PRIORITY_ARTIFACTS.get(d.source or "", 0),
            len(str(d.repo_url or "")),
        ),
        reverse=True,
    )
    return docs_with_repo[0].repo_url


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
        for key, value in (doc.source_ids or {}).items():
            if value and key not in source_ids:
                source_ids[key] = value

        if doc.source and doc.source_id and doc.source not in source_ids:
            source_ids[doc.source] = doc.source_id

        if doc.arxiv_id and "arxiv" not in source_ids:
            source_ids["arxiv"] = doc.arxiv_id

        if doc.openalex_id and "openalex" not in source_ids:
            source_ids["openalex"] = doc.openalex_id

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
    venue = choose_preferred_string(documents, "venue", source_priority=SOURCE_PRIORITY_VENUE,)
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
        docs_biblio = sort_documents_by_priority(docs, SOURCE_PRIORITY_BIBLIO)
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

        license_value = choose_best_license(docs)
        open_access = choose_canonical_open_access(docs)

        primary_category = choose_best_primary_category(docs)
        categories = merge_unique_strings([d.categories for d in docs])
        concepts = merge_unique_strings([d.concepts for d in docs])
        keywords = merge_unique_strings([d.keywords for d in docs])
        tags = merge_unique_strings([d.tags for d in docs])

        comment = choose_preferred_string(
            docs,
            "comment",
            source_priority=SOURCE_PRIORITY_COMMENT,
            prefer_longer=True,
        )
        journal_ref = choose_preferred_string(
            docs,
            "journal_ref",
            source_priority=SOURCE_PRIORITY_COMMENT,
            prefer_longer=True,
        )

        publication_type = choose_best_publication_type(docs)

        venue = choose_preferred_string(
            docs,
            "venue",
            source_priority=SOURCE_PRIORITY_VENUE,
            prefer_longer=False,
        )
        journal = choose_preferred_string(
            docs,
            "journal",
            source_priority=SOURCE_PRIORITY_VENUE,
            prefer_longer=False,
        )
        conference = choose_preferred_string(
            docs,
            "conference",
            source_priority=SOURCE_PRIORITY_VENUE,
            prefer_longer=False,
        )
        venue, journal, conference = normalize_venue_fields(
            publication_type,
            venue,
            journal,
            conference,
        )
        publisher = choose_preferred_string(
            docs,
            "publisher",
            source_priority=SOURCE_PRIORITY_BIBLIO,
            prefer_longer=False,
        )
        language = choose_preferred_string(
            docs,
            "language",
            source_priority=SOURCE_PRIORITY_DEFAULT,
            prefer_longer=False,
        )

        cited_by_count = choose_max_int(docs, "cited_by_count")
        references_count = choose_max_int(docs, "references_count")
        referenced_ids = merge_unique_strings([d.referenced_ids for d in docs_biblio])
        referenced_dois = merge_unique_strings([d.referenced_dois for d in docs_biblio])
        referenced_arxiv_ids = merge_unique_strings([d.referenced_arxiv_ids for d in docs_biblio])
        citation_graph_available = any(d.citation_graph_available for d in docs)

        code_links = merge_unique_strings([d.code_links for d in docs])
        dataset_links = merge_unique_strings([d.dataset_links for d in docs])
        model_links = merge_unique_strings([d.model_links for d in docs])

        has_code_link = (
            any(bool(getattr(d, "has_code_link", False)) for d in docs)
            or bool(code_links)
            or any(bool(getattr(d, "repo_url", None)) for d in docs)
        )
        has_dataset_link = (
            any(bool(getattr(d, "has_dataset_link", False)) for d in docs)
            or bool(dataset_links)
        )
        has_model_link = (
            any(bool(getattr(d, "has_model_link", False)) for d in docs)
            or bool(model_links)
        )

        unique_source_count = len({d.source for d in docs if d.source})

        is_open_access = choose_canonical_is_open_access(docs)
        is_preprint = choose_canonical_is_preprint(docs, publication_type)
        is_review = any(bool(getattr(d, "is_review", False)) for d in docs)
        is_survey = any(bool(getattr(d, "is_survey", False)) for d in docs)
        is_withdrawn = any(bool(getattr(d, "is_withdrawn", False)) for d in docs)

        metadata_completeness_score = compute_metadata_completeness_score(docs)

        canonical_documents.append(
            CanonicalDocument(
                canonical_id=canonical_id,
                doc_ids = dedupe_preserve_order([d.doc_id for d in docs if getattr(d, "doc_id", None)]),
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