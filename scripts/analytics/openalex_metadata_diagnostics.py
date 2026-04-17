from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import urlparse


REPORTS_DIR = Path("artifacts/reports")
NORMALIZED_DIR = Path("data/normalized/openalex")
RAW_DIR = Path("data/raw/openalex")

URL_RE = re.compile(r"https?://[^\s<>)\]}\"']+")

REPOSITORY_VENUE_HINTS = (
    "zenodo",
    "repository",
    "escholarship",
    "open collections",
    "arxiv",
    "figshare",
    "ssrn",
    "hal ",
    "hal-",
    "biorxiv",
    "medrxiv",
    "osf",
)

REPO_HOSTS = (
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

PAPER_LIKE_TYPES = {
    "article",
    "preprint",
}

NON_PAPER_LIKE_TYPES = {
    "dataset",
    "dissertation",
    "report",
    "other",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def dump_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def find_latest_normalized_file() -> Path:
    candidates = []
    for path in NORMALIZED_DIR.glob("documents.*.jsonl"):
        name = path.name
        if ".new." in name or ".updated." in name or ".unchanged." in name:
            continue
        candidates.append(path)

    candidates = sorted(candidates)
    if not candidates:
        raise FileNotFoundError(
            f"No primary normalized OpenAlex files found in {NORMALIZED_DIR}"
        )
    return candidates[-1]


def find_latest_raw_file() -> Optional[Path]:
    run_dirs = sorted([p for p in RAW_DIR.iterdir() if p.is_dir()])
    if not run_dirs:
        return None

    latest_run = run_dirs[-1]
    candidate = latest_run / "documents.raw.jsonl"
    if candidate.exists():
        return candidate
    return None


def looks_like_repository_venue(name: Optional[str]) -> bool:
    if not name:
        return False
    lowered = name.lower()
    return any(token in lowered for token in REPOSITORY_VENUE_HINTS)


def safe_lower(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def collect_urls_from_text(text: Optional[str]) -> list[str]:
    if not text:
        return []
    return URL_RE.findall(str(text))


def collect_urls_from_record(doc: dict[str, Any]) -> list[str]:
    urls: list[str] = []

    def add(value: Any) -> None:
        if value and str(value).strip():
            urls.append(str(value).strip())

    for key in [
        "canonical_url",
        "landing_page_url",
        "pdf_url",
        "repo_url",
    ]:
        add(doc.get(key))

    for key in ["title", "abstract", "comment", "journal_ref", "venue", "publisher"]:
        urls.extend(collect_urls_from_text(doc.get(key)))

    for field in ["code_links", "dataset_links", "model_links"]:
        for item in doc.get(field) or []:
            add(item)

    unique: list[str] = []
    seen: set[str] = set()
    for url in urls:
        norm = url.strip()
        if not norm or norm in seen:
            continue
        seen.add(norm)
        unique.append(norm)

    return unique


def host_of(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""


def is_repo_url(url: str) -> bool:
    host = host_of(url)
    return any(token in host for token in REPO_HOSTS)


def is_dataset_url(url: str) -> bool:
    lowered = url.lower()
    return any(token in lowered for token in DATASET_HOST_HINTS)


def is_model_url(url: str) -> bool:
    lowered = url.lower()
    return any(token in lowered for token in MODEL_HOST_HINTS)


def top_counter(counter: Counter, n: int = 15) -> list[dict[str, Any]]:
    return [{"value": key, "count": value} for key, value in counter.most_common(n)]


def pct(x: int, n: int) -> float:
    if n == 0:
        return 0.0
    return round(100.0 * x / n, 2)


def summarize_publication_types(records: list[dict[str, Any]]) -> Counter:
    c = Counter()
    for r in records:
        c[safe_lower(r.get("publication_type")) or "missing"] += 1
    return c


def summarize_venues(records: list[dict[str, Any]]) -> Counter:
    c = Counter()
    for r in records:
        venue = (r.get("venue") or "").strip()
        c[venue or "missing"] += 1
    return c


def summarize_publishers(records: list[dict[str, Any]]) -> Counter:
    c = Counter()
    for r in records:
        publisher = (r.get("publisher") or "").strip()
        c[publisher or "missing"] += 1
    return c


def build_diagnostics(records: list[dict[str, Any]], normalized_path: Path, raw_path: Optional[Path]) -> dict[str, Any]:
    total = len(records)

    publication_types = summarize_publication_types(records)
    venues = summarize_venues(records)
    publishers = summarize_publishers(records)

    repository_like_count = 0
    has_references_count = 0
    has_referenced_ids_count = 0
    has_citations_count = 0
    has_repo_url_count = 0
    has_code_links_count = 0
    has_dataset_links_count = 0
    has_model_links_count = 0
    has_any_text_url_count = 0
    has_any_repo_like_url_count = 0
    has_any_dataset_like_url_count = 0
    has_any_model_like_url_count = 0
    has_pdf_count = 0
    is_preprint_count = 0
    future_year_count = 0
    paper_like_count = 0
    non_paper_like_count = 0

    current_year = datetime.now(timezone.utc).year + 1

    repo_hosts = Counter()
    dataset_hosts = Counter()
    model_hosts = Counter()
    all_hosts = Counter()

    publication_type_by_repository_flag = defaultdict(Counter)

    example_repository_like: list[dict[str, Any]] = []
    example_with_repo_links: list[dict[str, Any]] = []
    example_with_references: list[dict[str, Any]] = []

    for r in records:
        venue = r.get("venue")
        publication_type = safe_lower(r.get("publication_type")) or "missing"

        if publication_type in PAPER_LIKE_TYPES:
            paper_like_count += 1

        if publication_type in NON_PAPER_LIKE_TYPES:
            non_paper_like_count += 1

        is_repository_like = looks_like_repository_venue(venue)
        if is_repository_like:
            repository_like_count += 1

        publication_type_by_repository_flag["repository_like" if is_repository_like else "non_repository_like"][
            publication_type
        ] += 1

        references_count = r.get("references_count")
        referenced_ids = r.get("referenced_ids") or []
        cited_by_count = r.get("cited_by_count")

        if references_count not in (None, 0):
            has_references_count += 1
        if referenced_ids:
            has_referenced_ids_count += 1
        if cited_by_count not in (None, 0):
            has_citations_count += 1

        if r.get("repo_url"):
            has_repo_url_count += 1
        if r.get("code_links"):
            has_code_links_count += 1
        if r.get("dataset_links"):
            has_dataset_links_count += 1
        if r.get("model_links"):
            has_model_links_count += 1
        if r.get("pdf_url"):
            has_pdf_count += 1
        if r.get("is_preprint") is True:
            is_preprint_count += 1

        year = r.get("year")
        if isinstance(year, int) and year > current_year:
            future_year_count += 1

        urls = collect_urls_from_record(r)
        if urls:
            has_any_text_url_count += 1

        repo_like_here = False
        dataset_like_here = False
        model_like_here = False

        for url in urls:
            h = host_of(url)
            if h:
                all_hosts[h] += 1

            if is_repo_url(url):
                repo_like_here = True
                if h:
                    repo_hosts[h] += 1
            if is_dataset_url(url):
                dataset_like_here = True
                if h:
                    dataset_hosts[h] += 1
            if is_model_url(url):
                model_like_here = True
                if h:
                    model_hosts[h] += 1

        if repo_like_here:
            has_any_repo_like_url_count += 1
        if dataset_like_here:
            has_any_dataset_like_url_count += 1
        if model_like_here:
            has_any_model_like_url_count += 1

        if is_repository_like and len(example_repository_like) < 10:
            example_repository_like.append(
                {
                    "doc_id": r.get("doc_id"),
                    "title": r.get("title"),
                    "publication_type": r.get("publication_type"),
                    "venue": r.get("venue"),
                    "publisher": r.get("publisher"),
                    "doi": r.get("doi"),
                }
            )

        if (r.get("repo_url") or r.get("code_links")) and len(example_with_repo_links) < 10:
            example_with_repo_links.append(
                {
                    "doc_id": r.get("doc_id"),
                    "title": r.get("title"),
                    "repo_url": r.get("repo_url"),
                    "code_links": r.get("code_links"),
                    "venue": r.get("venue"),
                    "publication_type": r.get("publication_type"),
                }
            )

        if (references_count not in (None, 0) or referenced_ids) and len(example_with_references) < 10:
            example_with_references.append(
                {
                    "doc_id": r.get("doc_id"),
                    "title": r.get("title"),
                    "references_count": references_count,
                    "referenced_ids_count": len(referenced_ids),
                    "venue": r.get("venue"),
                    "publication_type": r.get("publication_type"),
                }
            )

    report = {
        "report_name": "openalex_metadata_diagnostics",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input": {
            "normalized_file": str(normalized_path),
            "raw_file": str(raw_path) if raw_path else None,
            "total_records": total,
        },
        "coverage": {
            "repository_like_venue_count": repository_like_count,
            "repository_like_venue_pct": pct(repository_like_count, total),
            "has_references_count_count": has_references_count,
            "has_references_count_pct": pct(has_references_count, total),
            "has_referenced_ids_count": has_referenced_ids_count,
            "has_referenced_ids_pct": pct(has_referenced_ids_count, total),
            "has_cited_by_count_nonzero_count": has_citations_count,
            "has_cited_by_count_nonzero_pct": pct(has_citations_count, total),
            "has_repo_url_count": has_repo_url_count,
            "has_repo_url_pct": pct(has_repo_url_count, total),
            "has_code_links_count": has_code_links_count,
            "has_code_links_pct": pct(has_code_links_count, total),
            "has_dataset_links_count": has_dataset_links_count,
            "has_dataset_links_pct": pct(has_dataset_links_count, total),
            "has_model_links_count": has_model_links_count,
            "has_model_links_pct": pct(has_model_links_count, total),
            "has_any_url_in_record_count": has_any_text_url_count,
            "has_any_url_in_record_pct": pct(has_any_text_url_count, total),
            "has_any_repo_like_url_count": has_any_repo_like_url_count,
            "has_any_repo_like_url_pct": pct(has_any_repo_like_url_count, total),
            "has_any_dataset_like_url_count": has_any_dataset_like_url_count,
            "has_any_dataset_like_url_pct": pct(has_any_dataset_like_url_count, total),
            "has_any_model_like_url_count": has_any_model_like_url_count,
            "has_any_model_like_url_pct": pct(has_any_model_like_url_count, total),
            "has_pdf_count": has_pdf_count,
            "has_pdf_pct": pct(has_pdf_count, total),
            "is_preprint_count": is_preprint_count,
            "is_preprint_pct": pct(is_preprint_count, total),
            "future_year_count": future_year_count,
            "future_year_pct": pct(future_year_count, total),
            "paper_like_count": paper_like_count,
            "paper_like_pct": pct(paper_like_count, total),
            "non_paper_like_count": non_paper_like_count,
            "non_paper_like_pct": pct(non_paper_like_count, total)
        },
        "publication_type_distribution": {
            "top": top_counter(publication_types, n=20),
        },
        "venue_distribution": {
            "top": top_counter(venues, n=20),
        },
        "publisher_distribution": {
            "top": top_counter(publishers, n=20),
        },
        "host_distribution": {
            "top_all_hosts": top_counter(all_hosts, n=20),
            "top_repo_hosts": top_counter(repo_hosts, n=20),
            "top_dataset_hosts": top_counter(dataset_hosts, n=20),
            "top_model_hosts": top_counter(model_hosts, n=20),
        },
        "publication_type_by_repository_flag": {
            key: top_counter(counter, n=20)
            for key, counter in publication_type_by_repository_flag.items()
        },
        "examples": {
            "repository_like_records": example_repository_like,
            "records_with_repo_links": example_with_repo_links,
            "records_with_references": example_with_references,
        },
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    inp = report["input"]
    cov = report["coverage"]

    def bullet_cov(label: str, count_key: str, pct_key: str) -> str:
        return f"- {label}: {cov[count_key]} ({cov[pct_key]}%)"

    lines: list[str] = []
    lines.append("# OpenAlex metadata diagnostics")
    lines.append("")
    lines.append(f"- Generated at: {report['generated_at_utc']}")
    lines.append(f"- Normalized file: `{inp['normalized_file']}`")
    lines.append(f"- Raw file: `{inp['raw_file']}`")
    lines.append(f"- Total records: {inp['total_records']}")
    lines.append("")
    lines.append("## Coverage")
    lines.append(bullet_cov("Repository-like venue", "repository_like_venue_count", "repository_like_venue_pct"))
    lines.append(bullet_cov("Has references_count", "has_references_count_count", "has_references_count_pct"))
    lines.append(bullet_cov("Has referenced_ids", "has_referenced_ids_count", "has_referenced_ids_pct"))
    lines.append(bullet_cov("Has cited_by_count > 0", "has_cited_by_count_nonzero_count", "has_cited_by_count_nonzero_pct"))
    lines.append(bullet_cov("Has repo_url", "has_repo_url_count", "has_repo_url_pct"))
    lines.append(bullet_cov("Has code_links", "has_code_links_count", "has_code_links_pct"))
    lines.append(bullet_cov("Has dataset_links", "has_dataset_links_count", "has_dataset_links_pct"))
    lines.append(bullet_cov("Has model_links", "has_model_links_count", "has_model_links_pct"))
    lines.append(bullet_cov("Has any URL in record", "has_any_url_in_record_count", "has_any_url_in_record_pct"))
    lines.append(bullet_cov("Has any repo-like URL", "has_any_repo_like_url_count", "has_any_repo_like_url_pct"))
    lines.append(bullet_cov("Has any dataset-like URL", "has_any_dataset_like_url_count", "has_any_dataset_like_url_pct"))
    lines.append(bullet_cov("Has any model-like URL", "has_any_model_like_url_count", "has_any_model_like_url_pct"))
    lines.append(bullet_cov("Has PDF", "has_pdf_count", "has_pdf_pct"))
    lines.append(bullet_cov("Is preprint", "is_preprint_count", "is_preprint_pct"))
    lines.append(bullet_cov("Future year", "future_year_count", "future_year_pct"))
    lines.append(bullet_cov("Paper-like type", "paper_like_count", "paper_like_pct"))
    lines.append(bullet_cov("Non-paper-like type", "non_paper_like_count", "non_paper_like_pct"))
    lines.append("")

    for section_key, title in [
        ("publication_type_distribution", "Publication type distribution"),
        ("venue_distribution", "Venue distribution"),
        ("publisher_distribution", "Publisher distribution"),
    ]:
        lines.append(f"## {title}")
        for row in report[section_key]["top"]:
            lines.append(f"- {row['value']}: {row['count']}")
        lines.append("")

    lines.append("## Host distribution")
    for subkey, title in [
        ("top_all_hosts", "All hosts"),
        ("top_repo_hosts", "Repo-like hosts"),
        ("top_dataset_hosts", "Dataset-like hosts"),
        ("top_model_hosts", "Model-like hosts"),
    ]:
        lines.append(f"### {title}")
        for row in report["host_distribution"][subkey]:
            lines.append(f"- {row['value']}: {row['count']}")
        lines.append("")

    lines.append("## Publication type by repository flag")
    for key, rows in report["publication_type_by_repository_flag"].items():
        lines.append(f"### {key}")
        for row in rows:
            lines.append(f"- {row['value']}: {row['count']}")
        lines.append("")

    lines.append("## Examples")
    for ex_key, title in [
        ("repository_like_records", "Repository-like records"),
        ("records_with_repo_links", "Records with repo links"),
        ("records_with_references", "Records with references"),
    ]:
        lines.append(f"### {title}")
        examples = report["examples"][ex_key]
        if not examples:
            lines.append("- none")
        else:
            for item in examples:
                title_value = item.get("title") or "<no title>"
                doc_id = item.get("doc_id") or "<no doc_id>"
                lines.append(f"- {title_value} | doc_id={doc_id} | {json.dumps(item, ensure_ascii=False)}")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    normalized_path = find_latest_normalized_file()
    raw_path = find_latest_raw_file()

    records = load_jsonl(normalized_path)
    report = build_diagnostics(records, normalized_path=normalized_path, raw_path=raw_path)

    json_path = REPORTS_DIR / "openalex_metadata_diagnostics_latest.json"
    md_path = REPORTS_DIR / "openalex_metadata_diagnostics_latest.md"

    dump_json(json_path, report)
    dump_text(md_path, render_markdown(report))

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    hist_json = REPORTS_DIR / "history" / f"openalex_metadata_diagnostics_{ts}.json"
    hist_md = REPORTS_DIR / "history" / f"openalex_metadata_diagnostics_{ts}.md"

    dump_json(hist_json, report)
    dump_text(hist_md, render_markdown(report))

    print(f"[OK] loaded docs: {len(records)}")
    print(f"[OK] JSON report: {json_path}")
    print(f"[OK] Markdown report: {md_path}")
    print(f"[OK] snapshot JSON: {hist_json}")
    print(f"[OK] snapshot MD: {hist_md}")


if __name__ == "__main__":
    main()