from __future__ import annotations

import gzip
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, TextIO

import yaml


JSON_ARRAY_START_RE = re.compile(r"\A\s*\[")
VERSION_SUFFIX_RE = re.compile(r"v(\d+)$", re.IGNORECASE)
URL_RE = re.compile(r"https?://[^\s<>()\"']+")
CONFERENCE_HINT_RE = re.compile(
    r"\b("
    r"neurips|nips|iclr|icml|cvpr|iccv|eccv|aaai|ijcai|acl|emnlp|naacl|eacl|coling|"
    r"kdd|www|thewebconf|sigir|uai|aistats|interspeech|acmmm|mm|wacv"
    r")\b",
    flags=re.IGNORECASE,
)

DEFAULT_TAXONOMY_REL_PATH = Path("configs/taxonomy.yaml")

FALLBACK_CORE_ARXIV_CATEGORIES = [
    "cs.LG",
    "cs.AI",
    "stat.ML",
    "cs.CV",
    "cs.CL",
]

DOI_RE = re.compile(r"10\.\d{4,9}/[^\s,;]+", re.IGNORECASE)


def normalize_doi(value: Any) -> str | None:
    if value is None:
        return None

    text = normalize_text(value)
    if not text:
        return None

    lower = text.lower()
    for prefix in (
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
        "doi:",
    ):
        if lower.startswith(prefix):
            text = text[len(prefix):].strip()
            break

    tokens = [
        token.strip().strip(".,;()[]{}<>").lower().rstrip("/")
        for token in DOI_RE.findall(text)
    ]

    tokens = [
        token.strip().strip(".,;()[]{}<>").lower().rstrip("/")
        for token in DOI_RE.findall(text)
    ]
    tokens = [token for token in tokens if token]

    unique_tokens = list(dict.fromkeys(tokens))
    if unique_tokens:
        return unique_tokens[0]

    return None

def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path(__file__).resolve()).resolve()

    candidates: list[Path] = []
    if current.is_dir():
        candidates.append(current)
    candidates.extend([current.parent, *current.parents])

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if (candidate / "radar_core").exists() or (candidate / "configs").exists():
            return candidate

    return current.parent if current.is_file() else current


def resolve_project_path(path_like: str | Path) -> Path:
    path = Path(path_like)
    if path.is_absolute():
        return path
    return find_project_root() / path


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        value = (value or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def load_taxonomy_payload(
    taxonomy_path: str | Path = DEFAULT_TAXONOMY_REL_PATH,
) -> dict[str, Any]:
    path = resolve_project_path(taxonomy_path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return payload.get("taxonomy", {}) or {}


def load_arxiv_taxonomy_categories(
    taxonomy_path: str | Path = DEFAULT_TAXONOMY_REL_PATH,
    *,
    mode: str = "expanded",
) -> list[str]:
    taxonomy = load_taxonomy_payload(taxonomy_path)

    core_categories = (
        taxonomy.get("core_categories", {}).get("arxiv", [])
        or FALLBACK_CORE_ARXIV_CATEGORIES
    )
    core_categories = dedupe_preserve_order([str(x) for x in core_categories])

    if mode == "core":
        return core_categories

    if mode != "expanded":
        raise ValueError(f"Unsupported taxonomy category mode: {mode}")

    expanded = list(core_categories)
    topic_groups = taxonomy.get("topic_groups", {}) or {}

    for group_cfg in topic_groups.values():
        expanded.extend(group_cfg.get("arxiv_categories", []) or [])

    return dedupe_preserve_order([str(x) for x in expanded])


PROJECT_ROOT = find_project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# Import project contracts lazily so the utility can still be imported for pure format inspection.
try:
    from radar_core.contracts.document import (
        DocumentType,
        NormalizedDocument,
        PipelineStage,
        ProcessingStageRecord,
        RawDocument,
        SourceInfo,
        StageStatus,
    )
    from radar_core.utils.ids import build_content_hash, build_doc_id, canonicalize_url
except Exception:  # pragma: no cover - useful for standalone inspection only
    DocumentType = None
    NormalizedDocument = None
    PipelineStage = None
    ProcessingStageRecord = None
    RawDocument = None
    SourceInfo = None
    StageStatus = None
    build_content_hash = None
    build_doc_id = None
    canonicalize_url = None


@dataclass
class SnapshotFormatInfo:
    path: Path
    compression: str
    format_name: str
    first_non_ws: str | None
    sample_line_count: int


@dataclass
class RowMappingResult:
    raw_document: Any
    normalized_document: Any
    arxiv_id_base: str | None
    arxiv_id_versioned: str | None
    primary_category: str | None
    categories: list[str]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ts_slug(dt: datetime | None = None) -> str:
    dt = dt or utc_now()
    return dt.strftime("%Y%m%dT%H%M%SZ")


def _open_text(path: Path) -> TextIO:
    if path.suffix.lower() == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return path.open("r", encoding="utf-8")


def detect_snapshot_format(path: str | Path, sample_bytes: int = 65536) -> SnapshotFormatInfo:
    path = Path(path)
    opener = gzip.open if path.suffix.lower() == ".gz" else open
    compression = "gzip" if path.suffix.lower() == ".gz" else "none"

    with opener(path, "rt", encoding="utf-8") as f:
        sample = f.read(sample_bytes)

    stripped = sample.lstrip()
    first_non_ws = stripped[:1] or None

    if not stripped:
        format_name = "empty"
    elif JSON_ARRAY_START_RE.match(stripped):
        format_name = "json_array"
    else:
        format_name = "ndjson"

    sample_line_count = len([line for line in sample.splitlines() if line.strip()])

    return SnapshotFormatInfo(
        path=path,
        compression=compression,
        format_name=format_name,
        first_non_ws=first_non_ws,
        sample_line_count=sample_line_count,
    )


def iter_snapshot_rows(
    path: str | Path,
    *,
    format_name: str | None = None,
) -> Iterator[tuple[int, dict[str, Any]]]:
    path = Path(path)
    format_name = format_name or detect_snapshot_format(path).format_name

    if format_name == "ndjson":
        with _open_text(path) as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                yield line_no, json.loads(line)
        return

    if format_name == "json_array":
        try:
            import ijson  # type: ignore
        except Exception:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                raise ValueError(f"Expected JSON array in {path}")
            for idx, row in enumerate(payload, start=1):
                if isinstance(row, dict):
                    yield idx, row
            return

        open_handle = gzip.open(path, "rb") if path.suffix.lower() == ".gz" else path.open("rb")
        with open_handle as f:
            for idx, row in enumerate(ijson.items(f, "item"), start=1):
                if isinstance(row, dict):
                    yield idx, row
        return

    raise ValueError(f"Unsupported or unknown snapshot format: {format_name}")


def normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split()).strip()
    return text or None


def parse_categories(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = [normalize_text(v) for v in value]
        return [x for x in items if x]
    text = normalize_text(value)
    if not text:
        return []
    return [token for token in text.split() if token]


def parse_authors(value: Any, authors_parsed: Any = None) -> list[str]:
    if isinstance(value, list):
        out = [normalize_text(v) for v in value]
        return [x for x in out if x]

    text = normalize_text(value)
    if text:
        parts = [part.strip() for part in text.split(",") if part.strip()]
        if parts:
            return parts

    if isinstance(authors_parsed, list):
        out: list[str] = []
        for item in authors_parsed:
            if not isinstance(item, list) or not item:
                continue
            if len(item) >= 2:
                family = normalize_text(item[0]) or ""
                given = normalize_text(item[1]) or ""
                full = " ".join(part for part in [given, family] if part).strip()
                if full:
                    out.append(full)
        return out

    return []


def parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None

    text = normalize_text(value)
    if not text:
        return None

    text = text.replace("Z", "+00:00")

    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def parse_versions(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
    return []


def choose_versioned_arxiv_id(base_id: str | None, versions: list[dict[str, Any]]) -> str | None:
    base_id = normalize_text(base_id)
    if not base_id:
        return None

    best_label = None
    best_n = -1

    for item in versions:
        version = normalize_text(item.get("version"))
        if not version:
            continue
        match = VERSION_SUFFIX_RE.search(version)
        if not match:
            continue
        n = int(match.group(1))
        if n > best_n:
            best_label = version
            best_n = n

    if best_label:
        return f"{base_id}{best_label}"
    return base_id


def first_version_created_at(versions: list[dict[str, Any]]) -> datetime | None:
    candidates: list[tuple[int, datetime]] = []

    for item in versions:
        version = normalize_text(item.get("version"))
        created = parse_datetime(item.get("created"))
        if not version or created is None:
            continue

        match = VERSION_SUFFIX_RE.search(version)
        n = int(match.group(1)) if match else 999999
        candidates.append((n, created))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def last_version_created_at(versions: list[dict[str, Any]]) -> datetime | None:
    candidates: list[tuple[int, datetime]] = []

    for item in versions:
        version = normalize_text(item.get("version"))
        created = parse_datetime(item.get("created"))
        if not version or created is None:
            continue

        match = VERSION_SUFFIX_RE.search(version)
        n = int(match.group(1)) if match else -1
        candidates.append((n, created))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def _detect_withdrawn(title: str | None, abstract: str | None, comment: str | None) -> bool:
    haystack = " ".join(part for part in [title, abstract, comment] if part).lower()
    return any(token in haystack for token in ["withdrawn", "retracted"])


def _detect_review(title: str | None, abstract: str | None, comment: str | None) -> bool:
    haystack = " ".join(part for part in [title, abstract, comment] if part).lower()
    return " review " in f" {haystack} " or haystack.startswith("review of")


def _detect_survey(title: str | None, abstract: str | None, comment: str | None) -> bool:
    haystack = " ".join(part for part in [title, abstract, comment] if part).lower()
    return " survey " in f" {haystack} " or haystack.startswith("survey of")


def _extract_code_links(*texts: str | None) -> list[str]:
    out: list[str] = []
    for text in texts:
        if not text:
            continue
        for match in URL_RE.findall(text):
            if any(host in match.lower() for host in ["github.com", "gitlab.com", "bitbucket.org", "huggingface.co"]):
                out.append(match.rstrip(".,);]"))
    return list(dict.fromkeys(out))


def _extract_conference_hint(comment: str | None) -> str | None:
    if not comment:
        return None
    match = CONFERENCE_HINT_RE.search(comment)
    if not match:
        return None
    token = match.group(1).upper()
    mapping = {"NIPS": "NeurIPS", "NEURIPS": "NeurIPS", "THEWEBCONF": "WWW", "MM": "ACMMM"}
    return mapping.get(token, token)


def estimate_metadata_completeness(
    *,
    title: str | None,
    abstract: str | None,
    authors: list[str],
    doi: str | None,
    publication_date: datetime | None,
    primary_category: str | None,
    categories: list[str],
    pdf_url: str | None,
    code_links: list[str],
    comment: str | None,
    journal_ref: str | None,
) -> float:
    weights = {
        "title": 0.18,
        "abstract": 0.18,
        "authors": 0.12,
        "doi": 0.08,
        "publication_date": 0.10,
        "primary_category": 0.08,
        "categories": 0.08,
        "pdf_url": 0.08,
        "code_links": 0.04,
        "comment": 0.03,
        "journal_ref": 0.03,
    }

    score = 0.0
    score += weights["title"] if title else 0.0
    score += weights["abstract"] if abstract else 0.0
    score += weights["authors"] if authors else 0.0
    score += weights["doi"] if doi else 0.0
    score += weights["publication_date"] if publication_date else 0.0
    score += weights["primary_category"] if primary_category else 0.0
    score += weights["categories"] if categories else 0.0
    score += weights["pdf_url"] if pdf_url else 0.0
    score += weights["code_links"] if code_links else 0.0
    score += weights["comment"] if comment else 0.0
    score += weights["journal_ref"] if journal_ref else 0.0

    return round(min(score, 1.0), 4)


def row_matches_categories(categories: list[str], wanted: set[str] | None) -> bool:
    if not wanted:
        return True
    return bool(set(categories) & wanted)


def require_project_contracts() -> None:
    missing = []
    for name, value in {
        "DocumentType": DocumentType,
        "NormalizedDocument": NormalizedDocument,
        "PipelineStage": PipelineStage,
        "ProcessingStageRecord": ProcessingStageRecord,
        "RawDocument": RawDocument,
        "SourceInfo": SourceInfo,
        "StageStatus": StageStatus,
        "build_content_hash": build_content_hash,
        "build_doc_id": build_doc_id,
        "canonicalize_url": canonicalize_url,
    }.items():
        if value is None:
            missing.append(name)

    if missing:
        raise RuntimeError(
            "Project contracts are unavailable. Missing imports: " + ", ".join(missing)
        )


def map_kaggle_row_to_documents(
    row: dict[str, Any],
    *,
    raw_artifact_path: str | None,
    pipeline_version: str = "0.3.0",
    raw_source_name: str = "arxiv_kaggle_snapshot",
) -> RowMappingResult:
    require_project_contracts()

    title = normalize_text(row.get("title")) or ""
    abstract = normalize_text(row.get("abstract"))
    comment = normalize_text(row.get("comments"))
    journal_ref = normalize_text(row.get("journal-ref") or row.get("journal_ref"))
    doi = normalize_doi(row.get("doi"))
    license_value = normalize_text(row.get("license"))

    categories = parse_categories(row.get("categories"))
    primary_category = categories[0] if categories else None

    authors = parse_authors(row.get("authors"), row.get("authors_parsed"))
    versions = parse_versions(row.get("versions"))

    arxiv_id_base = normalize_text(row.get("id"))
    arxiv_id_versioned = choose_versioned_arxiv_id(arxiv_id_base, versions)

    published_at = first_version_created_at(versions) or parse_datetime(row.get("update_date"))
    updated_source_at = (
        parse_datetime(row.get("update_date"))
        or last_version_created_at(versions)
        or published_at
    )
    year = published_at.year if published_at else None

    chosen_id = arxiv_id_versioned or arxiv_id_base
    landing_page_url = f"http://arxiv.org/abs/{chosen_id}" if chosen_id else None
    pdf_url = f"https://arxiv.org/pdf/{chosen_id}" if chosen_id else None

    canonical_url = canonicalize_url(landing_page_url)
    doc_id = build_doc_id(canonical_url)
    content_hash = build_content_hash(title=title, abstract=abstract or "")

    code_links = _extract_code_links(comment, abstract)
    repo_url = code_links[0] if code_links else None

    metadata_completeness_score = estimate_metadata_completeness(
        title=title,
        abstract=abstract,
        authors=authors,
        doi=doi,
        publication_date=published_at,
        primary_category=primary_category,
        categories=categories,
        pdf_url=pdf_url,
        code_links=code_links,
        comment=comment,
        journal_ref=journal_ref,
    )

    external_ids: dict[str, str] = {}
    if doi:
        external_ids["doi"] = doi
    if arxiv_id_versioned:
        external_ids["arxiv"] = arxiv_id_versioned
    if arxiv_id_base and arxiv_id_base != arxiv_id_versioned:
        external_ids["arxiv_base"] = arxiv_id_base

    source_ids: dict[str, str] = {}
    if arxiv_id_versioned:
        source_ids["arxiv"] = arxiv_id_versioned

    found_stage = ProcessingStageRecord(
        stage=PipelineStage.FOUND,
        status=StageStatus.SUCCESS,
        pipeline_version=pipeline_version,
    )
    fetched_stage = ProcessingStageRecord(
        stage=PipelineStage.FETCHED,
        status=StageStatus.SUCCESS,
        pipeline_version=pipeline_version,
    )
    parsed_stage = ProcessingStageRecord(
        stage=PipelineStage.PARSED,
        status=StageStatus.SUCCESS,
        pipeline_version=pipeline_version,
    )

    raw_document = RawDocument(
        doc_id=doc_id,
        canonical_url=canonical_url,
        content_hash=content_hash,
        document_type=DocumentType.PAPER,
        source_info=SourceInfo(
            source="arxiv",
            source_id=landing_page_url,
            source_url=landing_page_url,
            source_record_id=chosen_id,
            source_record_url=landing_page_url,
            source_api_url=None,
            source_updated_at=updated_source_at,
            raw_source_name=raw_source_name,
        ),
        pipeline_version=pipeline_version,
        stages=[found_stage, fetched_stage],
        payload=row,
        created_at=published_at or utc_now(),
        updated_at=utc_now(),
    )

    normalized_document = NormalizedDocument(
        doc_id=doc_id,
        canonical_url=canonical_url,
        content_hash=content_hash,
        document_type=DocumentType.PAPER,
        source="arxiv",
        source_id=landing_page_url,
        source_record_id=chosen_id,
        source_record_url=landing_page_url,
        source_ids=source_ids,
        source_api_url=None,
        external_ids=external_ids,
        doi=doi,
        arxiv_id=chosen_id,
        openalex_id=None,
        pmid=None,
        pmcid=None,
        semantic_scholar_id=None,
        dblp_id=None,
        mag_id=None,
        title=title,
        abstract=abstract,
        authors=authors,
        published_at=published_at,
        publication_date=published_at,
        updated_source_at=updated_source_at,
        year=year,
        landing_page_url=landing_page_url,
        pdf_url=pdf_url,
        repo_url=repo_url,
        license=license_value,
        open_access=True,
        primary_category=primary_category,
        categories=categories,
        concepts=[],
        keywords=[],
        tags=list(dict.fromkeys(categories)),
        comment=comment,
        journal_ref=journal_ref,
        venue=None,
        journal=None,
        conference=_extract_conference_hint(comment),
        publisher=None,
        publication_type="preprint",
        language="en",
        cited_by_count=None,
        references_count=None,
        referenced_ids=[],
        referenced_dois=[],
        referenced_arxiv_ids=[],
        citation_graph_available=False,
        has_code_link=bool(code_links),
        code_links=code_links,
        dataset_links=[],
        model_links=[],
        has_dataset_link=False,
        has_model_link=False,
        has_pdf=pdf_url is not None,
        is_withdrawn=_detect_withdrawn(title, abstract, comment),
        is_open_access=True,
        is_preprint=True,
        is_review=_detect_review(title, abstract, comment),
        is_survey=_detect_survey(title, abstract, comment),
        raw_artifact_path=raw_artifact_path,
        raw_source_name=raw_source_name,
        ingested_at=utc_now(),
        metadata_completeness_score=metadata_completeness_score,
        pipeline_version=pipeline_version,
        stages=[found_stage, fetched_stage, parsed_stage],
        created_at=utc_now(),
        updated_at=utc_now(),
    )

    return RowMappingResult(
        raw_document=raw_document,
        normalized_document=normalized_document,
        arxiv_id_base=arxiv_id_base,
        arxiv_id_versioned=arxiv_id_versioned,
        primary_category=primary_category,
        categories=categories,
    )


def summarize_rows(
    rows: Iterable[dict[str, Any]],
    *,
    max_rows: int | None = None,
) -> dict[str, Any]:
    total = 0
    with_abstract = 0
    with_doi = 0
    category_counts: dict[str, int] = {}
    year_counts: dict[int, int] = {}
    sample_ids: list[str] = []

    for row in rows:
        if max_rows is not None and total >= max_rows:
            break

        total += 1

        abstract = normalize_text(row.get("abstract"))
        doi = normalize_doi(row.get("doi"))
        cats = parse_categories(row.get("categories"))
        versions = parse_versions(row.get("versions"))
        published = first_version_created_at(versions) or parse_datetime(row.get("update_date"))

        if abstract:
            with_abstract += 1
        if doi:
            with_doi += 1

        for cat in cats:
            category_counts[cat] = category_counts.get(cat, 0) + 1

        if published is not None:
            year_counts[published.year] = year_counts.get(published.year, 0) + 1

        if len(sample_ids) < 10:
            rid = normalize_text(row.get("id"))
            if rid:
                sample_ids.append(rid)

    top_categories = sorted(category_counts.items(), key=lambda x: (-x[1], x[0]))[:20]
    top_years = sorted(year_counts.items(), key=lambda x: (-x[1], -x[0]))[:20]

    return {
        "total_rows_seen": total,
        "with_abstract": with_abstract,
        "with_doi": with_doi,
        "abstract_coverage": round(with_abstract / max(total, 1), 4),
        "doi_coverage": round(with_doi / max(total, 1), 4),
        "top_categories": top_categories,
        "top_years": top_years,
        "sample_ids": sample_ids,
    }