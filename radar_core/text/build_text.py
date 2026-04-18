from __future__ import annotations

from typing import Any


def normalize_text(value: Any) -> str:
    """
    Normalize text safely for downstream embedding use.

    - Converts None to empty string
    - Casts non-strings to string
    - Collapses repeated whitespace
    - Strips leading/trailing spaces
    """
    if value is None:
        return ""
    text = " ".join(str(value).split()).strip()
    return text


def _normalize_list(values: Any) -> list[str]:
    """
    Normalize a list-like field into a clean list of strings.

    Supports:
    - None
    - list[str]
    - single scalar value
    """
    if values is None:
        return []

    if isinstance(values, list):
        out = [normalize_text(v) for v in values]
        return [x for x in out if x]

    value = normalize_text(values)
    return [value] if value else []


def join_nonempty(parts: list[str], sep: str = "\n") -> str:
    """
    Join only non-empty text parts.
    """
    cleaned = [normalize_text(p) for p in parts]
    cleaned = [p for p in cleaned if p]
    return sep.join(cleaned)


def build_embedding_text(doc: dict[str, Any]) -> str:
    """
    Build the primary text representation for abstract-level embeddings.

    Current strategy:
    1. title
    2. abstract
    3. categories / tags / concepts / keywords (only if present)

    Important:
    - This is an ML-layer representation builder.
    - It must not mutate canonical/source data.
    - If abstract is missing, fallback is title only.
    """
    title = normalize_text(doc.get("title"))
    abstract = normalize_text(doc.get("abstract"))

    categories = _normalize_list(doc.get("categories"))
    tags = _normalize_list(doc.get("tags"))
    concepts = _normalize_list(doc.get("concepts"))
    keywords = _normalize_list(doc.get("keywords"))

    # fallback for rare records without abstract
    if not abstract:
        return title

    taxonomy_block = join_nonempty(
        [
            "Categories: " + ", ".join(categories) if categories else "",
            "Tags: " + ", ".join(tags) if tags else "",
            "Concepts: " + ", ".join(concepts[:15]) if concepts else "",
            "Keywords: " + ", ".join(keywords[:15]) if keywords else "",
        ],
        sep="\n",
    )

    return join_nonempty(
        [
            title,
            abstract,
            taxonomy_block,
        ],
        sep="\n\n",
    )


def build_minimal_embedding_text(doc: dict[str, Any]) -> str:
    """
    Minimal version for quick experiments:
    title + abstract
    """
    title = normalize_text(doc.get("title"))
    abstract = normalize_text(doc.get("abstract"))

    if not abstract:
        return title

    return join_nonempty([title, abstract], sep="\n\n")