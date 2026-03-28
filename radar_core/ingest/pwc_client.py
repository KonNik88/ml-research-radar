from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Optional

import requests


DEFAULT_PWC_API_BASE = "https://paperswithcode.com/api/v1"


@dataclass
class PWCRequestTrace:
    query_type: str
    query_value: str
    url: str
    params: dict[str, Any]
    status_code: Optional[int]
    ok: bool
    response_preview: str
    error: Optional[str] = None


def _safe_preview(text: str, limit: int = 1200) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "...<truncated>"


def _normalize_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_doi(value: Any) -> Optional[str]:
    text = _normalize_text(value)
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


def normalize_arxiv_id(value: Any) -> Optional[str]:
    text = _normalize_text(value)
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


def _extract_payload_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        return []

    for key in ("results", "items", "papers", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    if payload and any(k in payload for k in ("id", "paper_id", "title", "url", "abstract")):
        return [payload]

    return []


def _extract_doi_from_entry(entry: dict[str, Any]) -> Optional[str]:
    for key in ("doi", "paper_doi"):
        value = normalize_doi(entry.get(key))
        if value:
            return value

    ext = entry.get("external_ids") or {}
    if isinstance(ext, dict):
        for key in ("doi", "DOI"):
            value = normalize_doi(ext.get(key))
            if value:
                return value

    return None


def _extract_arxiv_from_entry(entry: dict[str, Any]) -> Optional[str]:
    for key in ("arxiv_id", "paper_arxiv_id"):
        value = normalize_arxiv_id(entry.get(key))
        if value:
            return value

    ext = entry.get("external_ids") or {}
    if isinstance(ext, dict):
        for key in ("arxiv", "ArXiv", "arxiv_id"):
            value = normalize_arxiv_id(ext.get(key))
            if value:
                return value

    return None


def _build_candidate_requests(
    *,
    api_base: str,
    doi: Optional[str],
    arxiv_id: Optional[str],
    title: Optional[str] = None,
    max_results_per_identifier: int = 5,
) -> list[tuple[str, str, dict[str, Any]]]:
    """
    Возвращает список попыток в формате:
    (query_type, url, params)
    """
    base = api_base.rstrip("/")
    requests_to_try: list[tuple[str, str, dict[str, Any]]] = []

    if doi:
        requests_to_try.extend(
            [
                ("doi", f"{base}/papers/", {"doi": doi, "page_size": max_results_per_identifier}),
                ("doi", f"{base}/papers/", {"q": doi, "page_size": max_results_per_identifier}),
            ]
        )

    if arxiv_id:
        requests_to_try.extend(
            [
                ("arxiv", f"{base}/papers/", {"arxiv_id": arxiv_id, "page_size": max_results_per_identifier}),
                ("arxiv", f"{base}/papers/", {"q": arxiv_id, "page_size": max_results_per_identifier}),
            ]
        )

    if title:
        requests_to_try.append(
            ("title", f"{base}/papers/", {"q": title, "page_size": max_results_per_identifier})
        )

    return requests_to_try


def _looks_like_html_response(text: str) -> bool:
    lowered = (text or "").lstrip().lower()
    return lowered.startswith("<!doctype html") or lowered.startswith("<html")


def fetch_pwc_entry(
    *,
    doi: Optional[str],
    arxiv_id: Optional[str],
    title: Optional[str] = None,
    timeout: int = 60,
    api_base: str = DEFAULT_PWC_API_BASE,
    max_results_per_identifier: int = 5,
    debug: bool = False,
    traces: Optional[list[PWCRequestTrace]] = None,
    sleep_seconds: float = 0.0,
) -> Optional[dict[str, Any]]:
    """
    Консервативный resolver:
    - сначала DOI
    - потом arXiv id
    - потом title fallback
    - возвращает первую сильную запись

    Важно:
    если endpoint возвращает HTML вместо JSON, это считается невалидным API-ответом.
    """
    normalized_doi = normalize_doi(doi)
    normalized_arxiv = normalize_arxiv_id(arxiv_id)
    title = _normalize_text(title)

    session = requests.Session()
    candidate_requests = _build_candidate_requests(
        api_base=api_base,
        doi=normalized_doi,
        arxiv_id=normalized_arxiv,
        title=title,
        max_results_per_identifier=max_results_per_identifier,
    )

    for query_type, url, params in candidate_requests:
        status_code: Optional[int] = None
        preview = ""
        error: Optional[str] = None

        try:
            response = session.get(url, params=params, timeout=timeout)
            status_code = response.status_code
            preview = _safe_preview(response.text)

            content_type = response.headers.get("Content-Type", "")

            if _looks_like_html_response(response.text) or "text/html" in content_type.lower():
                error = "html_response_instead_of_json"
                if debug and traces is not None:
                    traces.append(
                        PWCRequestTrace(
                            query_type=query_type,
                            query_value=str(params.get("doi") or params.get("arxiv_id") or params.get("q") or ""),
                            url=url,
                            params=params,
                            status_code=status_code,
                            ok=False,
                            response_preview=preview,
                            error=error,
                        )
                    )
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)
                continue

            if response.status_code == 404:
                if debug and traces is not None:
                    traces.append(
                        PWCRequestTrace(
                            query_type=query_type,
                            query_value=str(params.get("doi") or params.get("arxiv_id") or params.get("q") or ""),
                            url=url,
                            params=params,
                            status_code=status_code,
                            ok=False,
                            response_preview=preview,
                            error="not_found",
                        )
                    )
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)
                continue

            response.raise_for_status()

            try:
                payload = response.json()
            except Exception as e:
                error = f"json_decode_error: {repr(e)}"
                if debug and traces is not None:
                    traces.append(
                        PWCRequestTrace(
                            query_type=query_type,
                            query_value=str(params.get("doi") or params.get("arxiv_id") or params.get("q") or ""),
                            url=url,
                            params=params,
                            status_code=status_code,
                            ok=False,
                            response_preview=preview,
                            error=error,
                        )
                    )
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)
                continue

            rows = _extract_payload_rows(payload)

            if debug and traces is not None:
                traces.append(
                    PWCRequestTrace(
                        query_type=query_type,
                        query_value=str(params.get("doi") or params.get("arxiv_id") or params.get("q") or ""),
                        url=url,
                        params=params,
                        status_code=status_code,
                        ok=True,
                        response_preview=_safe_preview(json.dumps(payload, ensure_ascii=False)),
                        error=None,
                    )
                )

            if not rows:
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)
                continue

            for row in rows:
                row_doi = _extract_doi_from_entry(row)
                row_arxiv = _extract_arxiv_from_entry(row)

                if normalized_doi and row_doi and normalized_doi == row_doi:
                    return row
                if normalized_arxiv and row_arxiv and normalized_arxiv == row_arxiv:
                    return row

            if len(rows) == 1:
                return rows[0]

        except requests.RequestException as e:
            error = repr(e)
            if debug and traces is not None:
                traces.append(
                    PWCRequestTrace(
                        query_type=query_type,
                        query_value=str(params.get("doi") or params.get("arxiv_id") or params.get("q") or ""),
                        url=url,
                        params=params,
                        status_code=status_code,
                        ok=False,
                        response_preview=preview,
                        error=error,
                    )
                )
        except Exception as e:
            error = repr(e)
            if debug and traces is not None:
                traces.append(
                    PWCRequestTrace(
                        query_type=query_type,
                        query_value=str(params.get("doi") or params.get("arxiv_id") or params.get("q") or ""),
                        url=url,
                        params=params,
                        status_code=status_code,
                        ok=False,
                        response_preview=preview,
                        error=error,
                    )
                )

        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    return None