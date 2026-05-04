from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from radar_core.contracts.document import DocumentType, NormalizedDocument


SOURCE_NAME = "acl_anthology"
PIPELINE_VERSION = "acl_anthology_candidate_v1"

DEFAULT_XML_IDS = ["2024.acl"]
DEFAULT_RAW_ROOT = Path("data/raw/acl_anthology")
DEFAULT_NORMALIZED_DIR = Path("data/normalized/acl_anthology")
DEFAULT_REPORT_DIR = Path("artifacts/reports/source_audit")
DEFAULT_BASE_RAW_URL = "https://raw.githubusercontent.com/acl-org/acl-anthology/master/data/xml"
DEFAULT_USER_AGENT = "ML-Research-Radar/ACL-Anthology-Candidate-Ingest-v1"

DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
URL_RE = re.compile(r"https?://[^\s)\]}>'\"]+", re.IGNORECASE)


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def stable_hash(*parts: Any, length: int = 32) -> str:
    text = "\n".join("" if p is None else str(p) for p in parts)
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:length]


def content_hash(payload: dict[str, Any], length: int = 32) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", value).strip()
    return text or None


def element_text(element: ET.Element | None) -> str | None:
    if element is None:
        return None
    return clean_text("".join(element.itertext()))


def child_text(parent: ET.Element | None, tag: str) -> str | None:
    if parent is None:
        return None
    return element_text(parent.find(tag))


def parse_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except Exception:
        return None


def normalize_doi(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    text = text.replace("https://doi.org/", "").replace("http://doi.org/", "")
    text = text.replace("https://dx.doi.org/", "").replace("http://dx.doi.org/", "")
    if text.lower().startswith("doi:"):
        text = text[4:]

    # Some dirty source fields contain repeated DOI tokens or prose after the DOI.
    text = text.strip().split()[0]
    text = text.strip().strip(".,;)")
    text = text.rstrip("/")
    text = text.lower()

    if not DOI_RE.match(text):
        return None
    return text


def parse_publication_date(year: int | None, month: str | None) -> datetime | None:
    if year is None:
        return None

    month_map = {
        "january": 1,
        "jan": 1,
        "february": 2,
        "feb": 2,
        "march": 3,
        "mar": 3,
        "april": 4,
        "apr": 4,
        "may": 5,
        "june": 6,
        "jun": 6,
        "july": 7,
        "jul": 7,
        "august": 8,
        "aug": 8,
        "september": 9,
        "sep": 9,
        "sept": 9,
        "october": 10,
        "oct": 10,
        "november": 11,
        "nov": 11,
        "december": 12,
        "dec": 12,
    }

    month_num = 1
    if month:
        first = re.split(r"[,;/\s]+", month.strip().lower())[0]
        month_num = month_map.get(first, 1)

    try:
        return datetime(year, month_num, 1, tzinfo=timezone.utc)
    except Exception:
        return None


def normalized_acl_url(anthology_id: str) -> str:
    return f"https://aclanthology.org/{anthology_id}/"


def normalized_acl_pdf_url(anthology_id: str) -> str:
    return f"https://aclanthology.org/{anthology_id}.pdf"


def raw_xml_url(base_raw_url: str, xml_id: str) -> str:
    return f"{base_raw_url.rstrip('/')}/{xml_id}.xml"


def download_text(url: str, timeout_sec: float, user_agent: str) -> str:
    request = Request(
        url,
        headers={
            "Accept": "application/xml,text/xml,text/plain,*/*",
            "User-Agent": user_agent,
        },
        method="GET",
    )
    with urlopen(request, timeout=timeout_sec) as response:  # noqa: S310 - controlled source URL
        raw = response.read()
    return raw.decode("utf-8")


def read_or_fetch_xml(
    *,
    xml_id: str,
    raw_dir: Path,
    offline_xml_dir: Path | None,
    base_raw_url: str,
    timeout_sec: float,
    user_agent: str,
    force_download: bool,
    sleep_sec: float,
) -> tuple[Path, str, str]:
    """Return (raw_path, source_url_or_path, xml_text)."""
    raw_path = raw_dir / f"{xml_id}.xml"

    if offline_xml_dir is not None:
        offline_path = offline_xml_dir / f"{xml_id}.xml"
        if not offline_path.exists():
            raise FileNotFoundError(f"Offline ACL XML not found: {offline_path}")
        xml_text = offline_path.read_text(encoding="utf-8")
        ensure_parent(raw_path)
        raw_path.write_text(xml_text, encoding="utf-8")
        return raw_path, normalize_path(offline_path) or str(offline_path), xml_text

    if raw_path.exists() and not force_download:
        return raw_path, normalize_path(raw_path) or str(raw_path), raw_path.read_text(encoding="utf-8")

    url = raw_xml_url(base_raw_url, xml_id)
    xml_text = download_text(url, timeout_sec=timeout_sec, user_agent=user_agent)
    ensure_parent(raw_path)
    raw_path.write_text(xml_text, encoding="utf-8")

    if sleep_sec > 0:
        time.sleep(sleep_sec)

    return raw_path, url, xml_text


def parse_author(author_el: ET.Element) -> str | None:
    first = child_text(author_el, "first")
    last = child_text(author_el, "last")
    name = child_text(author_el, "name")

    if first or last:
        return clean_text(" ".join(part for part in [first, last] if part))

    if name:
        return name

    return element_text(author_el)


def parse_urls_from_text(*texts: str | None) -> list[str]:
    urls: set[str] = set()
    for text in texts:
        if not text:
            continue
        for match in URL_RE.finditer(text):
            url = match.group(0).rstrip(".,;:)]}")
            if url:
                urls.add(url)
    return sorted(urls)


def classify_asset_urls(urls: list[str]) -> tuple[list[str], list[str], list[str]]:
    code: set[str] = set()
    datasets: set[str] = set()
    models: set[str] = set()

    for url in urls:
        low = url.lower()
        if "github.com" in low or "gitlab.com" in low or "bitbucket.org" in low or "codeberg.org" in low:
            code.add(url)
        elif "huggingface.co/datasets/" in low or "kaggle.com/datasets" in low:
            datasets.add(url)
        elif "huggingface.co/" in low:
            models.add(url)

    return sorted(code), sorted(datasets), sorted(models)


def parse_volume_meta(volume: ET.Element, collection_id: str) -> dict[str, Any]:
    meta = volume.find("meta")
    volume_id = str(volume.attrib.get("id") or "").strip()

    year = parse_int(child_text(meta, "year"))
    month = child_text(meta, "month")
    booktitle = child_text(meta, "booktitle")
    venue = child_text(meta, "venue")
    publisher = child_text(meta, "publisher") or "Association for Computational Linguistics"
    address = child_text(meta, "address")
    volume_url = child_text(meta, "url")
    volume_doi = normalize_doi(child_text(meta, "doi"))

    return {
        "collection_id": collection_id,
        "volume_id": volume_id,
        "volume_anthology_id": volume_url,
        "booktitle": booktitle,
        "year": year,
        "month": month,
        "venue": venue,
        "publisher": publisher,
        "address": address,
        "volume_doi": volume_doi,
    }


def paper_to_normalized_document(
    *,
    paper: ET.Element,
    volume_meta: dict[str, Any],
    xml_id: str,
    raw_path: Path,
    source_url: str,
    ingested_at: datetime,
) -> dict[str, Any] | None:
    title = child_text(paper, "title")
    if not title:
        return None

    anthology_id = child_text(paper, "url")
    if not anthology_id:
        paper_id = str(paper.attrib.get("id") or "").strip()
        volume_anthology_id = volume_meta.get("volume_anthology_id")
        if volume_anthology_id and paper_id:
            anthology_id = f"{volume_anthology_id}.{paper_id}"

    anthology_id = clean_text(anthology_id)
    if not anthology_id:
        return None

    doi = normalize_doi(child_text(paper, "doi"))
    abstract = child_text(paper, "abstract")
    pages = child_text(paper, "pages")
    bibkey = child_text(paper, "bibkey")

    authors = [parse_author(author_el) for author_el in paper.findall("author")]
    authors = [author for author in authors if author]

    year = volume_meta.get("year")
    month = volume_meta.get("month")
    publication_date = parse_publication_date(year, month)

    urls = parse_urls_from_text(abstract)
    code_links, dataset_links, model_links = classify_asset_urls(urls)

    canonical_url = normalized_acl_url(anthology_id)
    pdf_url = normalized_acl_pdf_url(anthology_id)

    source_ids = {SOURCE_NAME: anthology_id}
    external_ids = {"acl_anthology_id": anthology_id}
    if doi:
        external_ids["doi"] = doi
    if bibkey:
        external_ids["acl_bibkey"] = bibkey

    metadata_for_hash = {
        "source": SOURCE_NAME,
        "anthology_id": anthology_id,
        "doi": doi,
        "title": title,
        "abstract": abstract,
        "authors": authors,
        "year": year,
        "booktitle": volume_meta.get("booktitle"),
    }

    doc_id = stable_hash(SOURCE_NAME, anthology_id)
    chash = content_hash(metadata_for_hash)

    concepts: list[str] = []
    keywords: list[str] = []
    tags = ["acl_anthology"]
    if volume_meta.get("venue"):
        tags.append(str(volume_meta["venue"]).lower())

    comment_parts = []
    if pages:
        comment_parts.append(f"pages: {pages}")
    if bibkey:
        comment_parts.append(f"bibkey: {bibkey}")

    doc = NormalizedDocument(
        doc_id=doc_id,
        canonical_url=canonical_url,
        content_hash=chash,
        document_type=DocumentType.PAPER,
        source=SOURCE_NAME,
        source_id=anthology_id,
        source_record_id=anthology_id,
        source_record_url=canonical_url,
        source_ids=source_ids,
        source_api_url=source_url if source_url.startswith("http") else None,
        external_ids=external_ids,
        doi=doi,
        title=title,
        abstract=abstract,
        authors=authors,
        published_at=publication_date,
        publication_date=publication_date,
        year=year,
        landing_page_url=canonical_url,
        pdf_url=pdf_url,
        open_access=True,
        concepts=concepts,
        keywords=keywords,
        tags=tags,
        comment="; ".join(comment_parts) if comment_parts else None,
        venue=volume_meta.get("venue"),
        conference=volume_meta.get("booktitle"),
        publisher=volume_meta.get("publisher"),
        publication_type="conference-paper",
        language="en",
        code_links=code_links,
        dataset_links=dataset_links,
        model_links=model_links,
        has_code_link=bool(code_links),
        has_dataset_link=bool(dataset_links),
        has_model_link=bool(model_links),
        has_pdf=True,
        is_open_access=True,
        is_preprint=False,
        raw_artifact_path=normalize_path(raw_path),
        raw_source_name=xml_id,
        ingested_at=ingested_at,
        metadata_completeness_score=metadata_completeness_score(
            title=title,
            abstract=abstract,
            authors=authors,
            doi=doi,
            year=year,
            venue=volume_meta.get("venue"),
            pdf_url=pdf_url,
        ),
        pipeline_version=PIPELINE_VERSION,
    )

    return doc.model_dump(mode="json")


def metadata_completeness_score(
    *,
    title: str | None,
    abstract: str | None,
    authors: list[str],
    doi: str | None,
    year: int | None,
    venue: str | None,
    pdf_url: str | None,
) -> float:
    checks = [
        bool(title),
        bool(abstract),
        bool(authors),
        bool(doi),
        year is not None,
        bool(venue),
        bool(pdf_url),
    ]
    return round(sum(1 for ok in checks if ok) / len(checks), 4)


def parse_acl_xml(
    *,
    xml_text: str,
    xml_id: str,
    raw_path: Path,
    source_url: str,
    ingested_at: datetime,
    limit_docs: int | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"Failed to parse ACL XML {xml_id}: {exc}") from exc

    collection_id = root.attrib.get("id") or xml_id
    docs: list[dict[str, Any]] = []
    skipped_without_title = 0
    skipped_without_id = 0
    by_volume: Counter[str] = Counter()

    for volume in root.findall("volume"):
        volume_meta = parse_volume_meta(volume, collection_id=str(collection_id))
        volume_key = str(volume_meta.get("volume_anthology_id") or volume_meta.get("volume_id") or "unknown")

        for paper in volume.findall("paper"):
            if limit_docs is not None and len(docs) >= limit_docs:
                break

            title = child_text(paper, "title")
            anthology_id = child_text(paper, "url")
            if not title:
                skipped_without_title += 1
                continue
            if not anthology_id:
                skipped_without_id += 1

            doc = paper_to_normalized_document(
                paper=paper,
                volume_meta=volume_meta,
                xml_id=xml_id,
                raw_path=raw_path,
                source_url=source_url,
                ingested_at=ingested_at,
            )
            if doc is None:
                skipped_without_id += 1
                continue
            docs.append(doc)
            by_volume[volume_key] += 1

        if limit_docs is not None and len(docs) >= limit_docs:
            break

    parse_report = {
        "xml_id": xml_id,
        "collection_id": collection_id,
        "raw_path": normalize_path(raw_path),
        "source_url": source_url,
        "documents_count": len(docs),
        "skipped_without_title": skipped_without_title,
        "skipped_without_id": skipped_without_id,
        "by_volume": dict(sorted(by_volume.items())),
    }
    return docs, parse_report


def build_report(
    *,
    run_ts: str,
    args: argparse.Namespace,
    raw_dir: Path,
    normalized_path: Path,
    latest_path: Path,
    docs: list[dict[str, Any]],
    xml_reports: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    by_year = Counter(str(doc.get("year") or "missing") for doc in docs)
    by_venue = Counter(str(doc.get("venue") or "missing") for doc in docs)
    by_publication_type = Counter(str(doc.get("publication_type") or "missing") for doc in docs)

    doc_ids = [str(doc.get("doc_id") or "") for doc in docs if doc.get("doc_id")]
    source_ids = [str(doc.get("source_id") or "") for doc in docs if doc.get("source_id")]
    dois = [str(doc.get("doi") or "") for doc in docs if doc.get("doi")]

    duplicate_doc_ids = sorted([key for key, count in Counter(doc_ids).items() if count > 1])
    duplicate_source_ids = sorted([key for key, count in Counter(source_ids).items() if count > 1])
    duplicate_dois = sorted([key for key, count in Counter(dois).items() if count > 1])

    abstract_count = sum(1 for doc in docs if doc.get("abstract"))
    doi_count = sum(1 for doc in docs if doc.get("doi"))
    author_count_non_empty = sum(1 for doc in docs if doc.get("authors"))
    code_link_docs = sum(1 for doc in docs if doc.get("has_code_link"))
    dataset_link_docs = sum(1 for doc in docs if doc.get("has_dataset_link"))
    model_link_docs = sum(1 for doc in docs if doc.get("has_model_link"))

    return {
        "report_name": "acl_anthology_ingest",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "source": SOURCE_NAME,
        "pipeline_version": PIPELINE_VERSION,
        "candidate_only": True,
        "xml_ids": args.xml_ids,
        "limit_docs": args.limit_docs,
        "base_raw_url": args.base_raw_url,
        "offline_xml_dir": normalize_path(args.offline_xml_dir),
        "raw_dir": normalize_path(raw_dir),
        "normalized_path": normalize_path(normalized_path),
        "latest_path": normalize_path(latest_path),
        "documents_count": len(docs),
        "xml_files_count": len(xml_reports),
        "xml_reports": xml_reports,
        "errors": errors,
        "error_count": len(errors),
        "abstract_count": abstract_count,
        "abstract_coverage": round(abstract_count / len(docs), 4) if docs else 0.0,
        "doi_count": doi_count,
        "doi_coverage": round(doi_count / len(docs), 4) if docs else 0.0,
        "author_count_non_empty": author_count_non_empty,
        "author_coverage": round(author_count_non_empty / len(docs), 4) if docs else 0.0,
        "code_link_docs": code_link_docs,
        "dataset_link_docs": dataset_link_docs,
        "model_link_docs": model_link_docs,
        "duplicate_doc_id_count": len(duplicate_doc_ids),
        "duplicate_doc_ids_sample": duplicate_doc_ids[:20],
        "duplicate_source_id_count": len(duplicate_source_ids),
        "duplicate_source_ids_sample": duplicate_source_ids[:20],
        "duplicate_doi_count": len(duplicate_dois),
        "duplicate_dois_sample": duplicate_dois[:20],
        "by_year": dict(sorted(by_year.items())),
        "by_venue": dict(sorted(by_venue.items())),
        "by_publication_type": dict(sorted(by_publication_type.items())),
        "ok": bool(docs) and not errors and not duplicate_doc_ids and not duplicate_source_ids,
    }


def build_markdown_report(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# ACL Anthology candidate ingest report")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at_utc']}`")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Candidate only: `{report['candidate_only']}`")
    lines.append(f"- XML ids: `{', '.join(report['xml_ids'])}`")
    lines.append(f"- Documents: `{report['documents_count']}`")
    lines.append(f"- Output: `{report['normalized_path']}`")
    lines.append("")
    lines.append("## Coverage")
    lines.append(f"- abstract_count: `{report['abstract_count']}` / `{report['documents_count']}`")
    lines.append(f"- abstract_coverage: `{report['abstract_coverage']}`")
    lines.append(f"- doi_count: `{report['doi_count']}` / `{report['documents_count']}`")
    lines.append(f"- doi_coverage: `{report['doi_coverage']}`")
    lines.append(f"- author_coverage: `{report['author_coverage']}`")
    lines.append(f"- code_link_docs: `{report['code_link_docs']}`")
    lines.append(f"- dataset_link_docs: `{report['dataset_link_docs']}`")
    lines.append(f"- model_link_docs: `{report['model_link_docs']}`")
    lines.append("")
    lines.append("## Integrity")
    lines.append(f"- duplicate_doc_id_count: `{report['duplicate_doc_id_count']}`")
    lines.append(f"- duplicate_source_id_count: `{report['duplicate_source_id_count']}`")
    lines.append(f"- duplicate_doi_count: `{report['duplicate_doi_count']}`")
    lines.append(f"- error_count: `{report['error_count']}`")
    lines.append(f"- ok: `{report['ok']}`")
    lines.append("")
    lines.append("## By year")
    for key, value in report.get("by_year", {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    lines.append("## By venue")
    for key, value in report.get("by_venue", {}).items():
        lines.append(f"- {key}: `{value}`")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Candidate-only ACL Anthology ingest. Fetches/parses ACL XML metadata and writes "
            "NormalizedDocument-compatible JSONL without touching canonical corpus or Postgres."
        )
    )
    parser.add_argument("--xml-ids", nargs="+", default=DEFAULT_XML_IDS, help="ACL XML ids without .xml suffix.")
    parser.add_argument("--limit-docs", type=int, default=None, help="Optional maximum docs across all XML files.")
    parser.add_argument("--base-raw-url", default=DEFAULT_BASE_RAW_URL)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--normalized-dir", type=Path, default=DEFAULT_NORMALIZED_DIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--offline-xml-dir", type=Path, default=None, help="Optional local directory with <xml_id>.xml files.")
    parser.add_argument("--timeout-sec", type=float, default=60.0)
    parser.add_argument("--sleep-sec", type=float, default=0.2)
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument("--user-agent", default=DEFAULT_USER_AGENT)
    parser.add_argument("--allow-partial", action="store_true", help="Write output even if some XML files fail.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_ts = utc_now_ts()
    ingested_at = utc_now()

    raw_dir = args.raw_root / run_ts
    normalized_path = args.normalized_dir / f"documents.{run_ts}.jsonl"
    latest_path = args.normalized_dir / "documents_latest.jsonl"

    docs: list[dict[str, Any]] = []
    xml_reports: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    print(f"[INFO] source={SOURCE_NAME}")
    print(f"[INFO] candidate_only=True")
    print(f"[INFO] xml_ids={args.xml_ids}")
    print(f"[INFO] raw_dir={raw_dir}")
    print(f"[INFO] normalized_path={normalized_path}")

    for xml_id in args.xml_ids:
        try:
            print(f"[INFO] loading XML {xml_id}")
            raw_path, source_url, xml_text = read_or_fetch_xml(
                xml_id=xml_id,
                raw_dir=raw_dir,
                offline_xml_dir=args.offline_xml_dir,
                base_raw_url=args.base_raw_url,
                timeout_sec=args.timeout_sec,
                user_agent=args.user_agent,
                force_download=args.force_download,
                sleep_sec=args.sleep_sec,
            )
            remaining_limit = None
            if args.limit_docs is not None:
                remaining_limit = max(args.limit_docs - len(docs), 0)

            parsed_docs, parse_report = parse_acl_xml(
                xml_text=xml_text,
                xml_id=xml_id,
                raw_path=raw_path,
                source_url=source_url,
                ingested_at=ingested_at,
                limit_docs=remaining_limit,
            )
            docs.extend(parsed_docs)
            xml_reports.append(parse_report)
            print(f"[INFO] parsed {len(parsed_docs)} docs from {xml_id}")

            if args.limit_docs is not None and len(docs) >= args.limit_docs:
                print(f"[INFO] limit_docs reached: {args.limit_docs}")
                break

        except (HTTPError, URLError, OSError, ValueError) as exc:
            error = {
                "xml_id": xml_id,
                "error": repr(exc),
                "error_type": type(exc).__name__,
            }
            errors.append(error)
            print(f"[ERROR] failed XML {xml_id}: {exc}")
            if not args.allow_partial:
                break

    if errors and not args.allow_partial:
        report = build_report(
            run_ts=run_ts,
            args=args,
            raw_dir=raw_dir,
            normalized_path=normalized_path,
            latest_path=latest_path,
            docs=docs,
            xml_reports=xml_reports,
            errors=errors,
        )
        report["ok"] = False
        write_json(args.report_dir / "acl_anthology_ingest_latest.json", report)
        write_text(args.report_dir / "acl_anthology_ingest_latest.md", build_markdown_report(report))
        write_json(args.report_dir / "history" / f"acl_anthology_ingest_{run_ts}.json", report)
        write_text(args.report_dir / "history" / f"acl_anthology_ingest_{run_ts}.md", build_markdown_report(report))
        raise SystemExit(1)

    write_jsonl(normalized_path, docs)
    shutil.copyfile(normalized_path, latest_path)

    report = build_report(
        run_ts=run_ts,
        args=args,
        raw_dir=raw_dir,
        normalized_path=normalized_path,
        latest_path=latest_path,
        docs=docs,
        xml_reports=xml_reports,
        errors=errors,
    )

    latest_json = args.report_dir / "acl_anthology_ingest_latest.json"
    latest_md = args.report_dir / "acl_anthology_ingest_latest.md"
    history_json = args.report_dir / "history" / f"acl_anthology_ingest_{run_ts}.json"
    history_md = args.report_dir / "history" / f"acl_anthology_ingest_{run_ts}.md"

    write_json(latest_json, report)
    write_text(latest_md, build_markdown_report(report))
    write_json(history_json, report)
    write_text(history_md, build_markdown_report(report))

    print(f"[OK] documents_count={len(docs)}")
    print(f"[OK] normalized_path={normalized_path}")
    print(f"[OK] latest_path={latest_path}")
    print(f"[OK] report JSON: {latest_json}")
    print(f"[OK] report MD: {latest_md}")
    print(f"[OK] ok={report['ok']}")

    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
