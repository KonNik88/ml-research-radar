from __future__ import annotations

import hashlib
import re
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(text: Optional[str]) -> str:
    if not text:
        return ""
    text = text.strip()
    text = WHITESPACE_RE.sub(" ", text)
    return text


def canonicalize_url(url: str) -> str:
    """
    Базовая канонизация URL.
    На старте не пытаемся быть слишком умными.
    """
    parsed = urlparse(url.strip())

    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()

    # Убираем trailing slash, кроме корня
    path = parsed.path.rstrip("/") if parsed.path != "/" else parsed.path

    # Сортируем query params для стабильности
    query_pairs = sorted(parse_qsl(parsed.query, keep_blank_values=True))
    query = urlencode(query_pairs)

    canonical = urlunparse((scheme, netloc, path, "", query, ""))
    return canonical


def stable_hash(value: str, length: int = 32) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return digest[:length]


def build_doc_id(canonical_url: str) -> str:
    return stable_hash(canonical_url, length=32)


def build_content_hash(title: str, abstract: Optional[str]) -> str:
    normalized = f"{normalize_text(title)}\n{normalize_text(abstract)}"
    return stable_hash(normalized, length=32)