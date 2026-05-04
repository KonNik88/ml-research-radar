from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_BASELINE_PATH = Path("data/analytics/reconciled/canonical_documents.jsonl")
DEFAULT_OUTPUT_DIR = Path("data/analytics/reconciled")
DEFAULT_REPORT_DIR = Path("artifacts/reports/source_audit")

STABLE_CANONICAL_PATH = Path("data/analytics/reconciled/canonical_documents.jsonl")

ACL_FAMILY_MARKERS = {"acl_anthology"}
ARXIV_FAMILY_MARKERS = {"arxiv", "arxiv_kaggle_snapshot"}
OPENALEX_FAMILY_MARKERS = {"openalex", "openalex_alignment"}
S2_FAMILY_MARKERS = {"semantic_scholar", "semantic_scholar_alignment", "semanticscholar"}
CROSSREF_FAMILY_MARKERS = {"crossref", "crossref_alignment"}

DOI_RE = re.compile(r"10\.\d{4,9}/\S+", re.IGNORECASE)
ARXIV_VERSION_RE = re.compile(r"v\d+$", re.IGNORECASE)
NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL {path} line={line_no}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"JSONL row must be object: {path} line={line_no}")
            yield row


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return list(iter_jsonl(path))


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def stable_hash(*parts: Any, length: int = 32) -> str:
    text = "\n".join("" if p is None else str(p) for p in parts)
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:length]


def json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def canonical_doc_id(doc: dict[str, Any]) -> str | None:
    for key in ("canonical_id", "doc_id", "id"):
        value = doc.get(key)
        if value:
            return str(value)
    return None


def normalize_doi(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None

    # Handle repeated DOI strings and common prefixes.
    text = text.replace("https://doi.org/", "")
    text = text.replace("http://doi.org/", "")
    text = text.replace("https://dx.doi.org/", "")
    text = text.replace("http://dx.doi.org/", "")
    if text.startswith("doi:"):
        text = text[4:].strip()

    match = DOI_RE.search(text)
    if not match:
        return None

    doi = match.group(0).strip().rstrip(".,;:)/]")
    if not doi.startswith("10."):
        return None
    return doi


def doc_doi(doc: dict[str, Any]) -> str | None:
    doi = normalize_doi(doc.get("doi"))
    if doi:
        return doi
    external_ids = doc.get("external_ids")
    if isinstance(external_ids, dict):
        for key in ("doi", "DOI"):
            doi = normalize_doi(external_ids.get(key))
            if doi:
                return doi
    return None


def normalize_arxiv_base(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("https://arxiv.org/abs/", "")
    text = text.replace("http://arxiv.org/abs/", "")
    text = text.replace("arXiv:", "")
    text = text.replace("arxiv:", "")
    text = text.split()[0].strip().strip("/.,;:)")
    text = ARXIV_VERSION_RE.sub("", text)
    return text or None


def doc_arxiv_bases(doc: dict[str, Any]) -> set[str]:
    out: set[str] = set()

    for key in ("arxiv_id", "arxiv_base_id"):
        value = normalize_arxiv_base(doc.get(key))
        if value:
            out.add(value)

    external_ids = doc.get("external_ids")
    if isinstance(external_ids, dict):
        for key in ("arxiv", "arxiv_id", "arXiv", "arxiv_base_id"):
            value = normalize_arxiv_base(external_ids.get(key))
            if value:
                out.add(value)

    source_ids = doc.get("source_ids")
    if isinstance(source_ids, dict):
        for key, value in source_ids.items():
            if "arxiv" in str(key).lower():
                value = normalize_arxiv_base(value)
                if value:
                    out.add(value)

    return out


def normalize_title(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).lower().strip()
    if not text:
        return None
    text = NON_ALNUM_RE.sub(" ", text)
    text = " ".join(text.split())
    return text or None


def doc_title_year_key(doc: dict[str, Any]) -> tuple[str, int] | None:
    title = normalize_title(doc.get("title"))
    year = doc.get("year") or doc.get("publication_year")
    try:
        year_int = int(year)
    except Exception:
        return None
    if not title:
        return None
    return title, year_int


def collect_source_labels(doc: dict[str, Any]) -> set[str]:
    labels: set[str] = set()

    def add(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, str):
            value = value.strip()
            if value:
                labels.add(value)
            return
        if isinstance(value, dict):
            for key in ("source", "source_name", "name", "raw_source_name"):
                add(value.get(key))
            return
        if isinstance(value, list):
            for item in value:
                add(item)
            return

    for key in (
        "source",
        "raw_source_name",
        "sources",
        "source_names",
        "source_name",
        "source_set",
    ):
        add(doc.get(key))

    source_ids = doc.get("source_ids")
    if isinstance(source_ids, dict):
        for key in source_ids.keys():
            add(key)

    external_ids = doc.get("external_ids")
    if isinstance(external_ids, dict):
        if external_ids.get("acl_anthology_id"):
            add("acl_anthology")
        if external_ids.get("arxiv") or external_ids.get("arxiv_id") or external_ids.get("arXiv"):
            add("arxiv")
        if external_ids.get("openalex") or external_ids.get("openalex_id"):
            add("openalex")
        if external_ids.get("semantic_scholar") or external_ids.get("semantic_scholar_id"):
            add("semantic_scholar")
        if external_ids.get("doi") or external_ids.get("DOI"):
            # DOI is not a source family by itself.
            pass

    provenance = doc.get("provenance")
    if isinstance(provenance, dict):
        add(provenance.get("sources"))
        add(provenance.get("source_names"))
    elif isinstance(provenance, list):
        add(provenance)

    source_records = doc.get("source_records") or doc.get("source_documents")
    if isinstance(source_records, list):
        for record in source_records:
            add(record)

    return labels


def source_families(doc: dict[str, Any]) -> set[str]:
    labels = {label.lower() for label in collect_source_labels(doc)}
    families: set[str] = set()

    for label in labels:
        if label in ACL_FAMILY_MARKERS or label.endswith(".acl") or label.startswith("20") and ".acl" in label:
            families.add("acl_anthology")
        if any(marker in label for marker in ARXIV_FAMILY_MARKERS):
            families.add("arxiv")
        if any(marker in label for marker in OPENALEX_FAMILY_MARKERS):
            families.add("openalex")
        if any(marker in label for marker in S2_FAMILY_MARKERS):
            families.add("semantic_scholar")
        if any(marker in label for marker in CROSSREF_FAMILY_MARKERS):
            families.add("crossref")

    if doc.get("source") == "acl_anthology":
        families.add("acl_anthology")
    if doc.get("arxiv_id"):
        families.add("arxiv")
    if doc.get("openalex_id"):
        families.add("openalex")
    if doc.get("semantic_scholar_id"):
        families.add("semantic_scholar")
    if doc.get("doi") and doc.get("source") == "crossref":
        families.add("crossref")

    return families


def family_set_key(doc: dict[str, Any]) -> str:
    families = sorted(source_families(doc))
    return "+".join(families) if families else "unknown"


def has_acl_family(doc: dict[str, Any]) -> bool:
    return "acl_anthology" in source_families(doc)


def has_arxiv_family(doc: dict[str, Any]) -> bool:
    return "arxiv" in source_families(doc)


def is_acl_family_only(doc: dict[str, Any]) -> bool:
    families = source_families(doc)
    return families == {"acl_anthology"}


def build_indexes(rows: list[dict[str, Any]]) -> dict[str, dict[Any, list[dict[str, Any]]]]:
    by_id: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    by_doi: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    by_arxiv_base: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    by_title_year: dict[Any, list[dict[str, Any]]] = defaultdict(list)

    for row in rows:
        doc_id = canonical_doc_id(row)
        if doc_id:
            by_id[doc_id].append(row)

        doi = doc_doi(row)
        if doi:
            by_doi[doi].append(row)

        for base in doc_arxiv_bases(row):
            by_arxiv_base[base].append(row)

        title_year = doc_title_year_key(row)
        if title_year:
            by_title_year[title_year].append(row)

    return {
        "by_id": by_id,
        "by_doi": by_doi,
        "by_arxiv_base": by_arxiv_base,
        "by_title_year": by_title_year,
    }



def find_baseline_exact_match(
    candidate_doc: dict[str, Any],
    baseline_indexes: dict[str, dict[Any, list[dict[str, Any]]]],
) -> dict[str, Any] | None:
    """Return a safe exact baseline match.

    Only canonical id/doc_id and arXiv base-id are considered exact enough to
    replace/update a baseline row automatically. DOI and title+year are treated
    as soft identity signals and are not used for automatic replacement here.
    """
    doc_id = canonical_doc_id(candidate_doc)
    if doc_id:
        matches = baseline_indexes["by_id"].get(doc_id, [])
        if len(matches) == 1:
            return matches[0]

    for base in sorted(doc_arxiv_bases(candidate_doc)):
        matches = baseline_indexes["by_arxiv_base"].get(base, [])
        if len(matches) == 1:
            return matches[0]

    return None


def find_baseline_soft_match(
    candidate_doc: dict[str, Any],
    baseline_indexes: dict[str, dict[Any, list[dict[str, Any]]]],
) -> tuple[str | None, dict[str, Any] | None]:
    """Return a soft baseline match via DOI or normalized title+year.

    Soft matches are useful for diagnostics and duplicate prevention, but are
    not safe enough for automatic baseline replacement because they can drop
    arXiv provenance/canonical ids if the raw reconcile did not merge them.
    """
    doi = doc_doi(candidate_doc)
    if doi:
        matches = baseline_indexes["by_doi"].get(doi, [])
        if len(matches) == 1:
            return "doi", matches[0]

    title_year = doc_title_year_key(candidate_doc)
    if title_year:
        matches = baseline_indexes["by_title_year"].get(title_year, [])
        if len(matches) == 1:
            return "title_year", matches[0]

    return None, None


def merge_candidate_into_baseline_preserving_identity(
    baseline_doc: dict[str, Any],
    candidate_doc: dict[str, Any],
) -> dict[str, Any]:
    """Use the richer candidate row while preserving stable baseline identity.

    This is only used for exact arXiv/doc-id matches. It keeps the stable
    baseline canonical/doc identifiers and merges external/source ids so arXiv
    provenance cannot be lost during the filtered candidate build.
    """
    merged = dict(candidate_doc)

    for key in ("doc_id", "canonical_id", "id"):
        if baseline_doc.get(key) is not None:
            merged[key] = baseline_doc.get(key)

    for key in ("external_ids", "source_ids"):
        baseline_value = baseline_doc.get(key)
        candidate_value = candidate_doc.get(key)
        if isinstance(baseline_value, dict) or isinstance(candidate_value, dict):
            merged[key] = {
                **(baseline_value if isinstance(baseline_value, dict) else {}),
                **(candidate_value if isinstance(candidate_value, dict) else {}),
            }

    # Preserve baseline arXiv id if candidate did not carry it explicitly.
    if baseline_doc.get("arxiv_id") and not merged.get("arxiv_id"):
        merged["arxiv_id"] = baseline_doc.get("arxiv_id")

    metadata = json_object(baseline_doc.get("metadata"))
    metadata.update(json_object(candidate_doc.get("metadata")))
    metadata.setdefault("filtered_candidate", {})
    if isinstance(metadata["filtered_candidate"], dict):
        metadata["filtered_candidate"].update(
            {
                "stage": "acl_anthology_filtered_candidate_v1_3",
                "baseline_doc_id": canonical_doc_id(baseline_doc),
                "candidate_doc_id_before_identity_preservation": canonical_doc_id(candidate_doc),
                "identity_preserved_from_baseline": True,
                "automatic_update_reason": "exact_doc_id_or_arxiv_base_match_with_acl_provenance",
            }
        )
    merged["metadata"] = metadata

    return merged


def backfill_acl_urls(doc: dict[str, Any]) -> dict[str, Any]:
    """Ensure ACL canonical rows retain stable landing/canonical/source URLs.

    Raw ACL normalized documents usually carry source_record_url/canonical_url,
    but after reconcile some ACL-only canonical rows may keep only
    landing_page_url. For DB/API/audit readiness, backfill missing
    canonical_url and source_record_url from the existing landing URL.
    This is deterministic and does not affect identity resolution.
    """
    out = dict(doc)
    if not has_acl_family(out):
        return out

    landing_url = out.get("landing_page_url") or out.get("canonical_url") or out.get("source_record_url")
    if landing_url:
        if not out.get("landing_page_url"):
            out["landing_page_url"] = landing_url
        if not out.get("canonical_url"):
            out["canonical_url"] = landing_url
        if not out.get("source_record_url"):
            out["source_record_url"] = landing_url

    metadata = json_object(out.get("metadata"))
    metadata.setdefault("acl_anthology_filtered_candidate", {})
    if isinstance(metadata["acl_anthology_filtered_candidate"], dict):
        metadata["acl_anthology_filtered_candidate"].update(
            {
                "url_backfill_applied": bool(landing_url),
                "url_backfill_stage": "acl_anthology_filtered_candidate_v1_3",
            }
        )
    out["metadata"] = metadata
    return out


def dedupe_rows_by_identity(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []

    for row in rows:
        doc_id = canonical_doc_id(row)
        if not doc_id:
            # Generate deterministic fallback only for output stability; also report it.
            doc_id = stable_hash("missing_doc_id", row.get("title"), row.get("year"), row.get("doi"))
            row = dict(row)
            row.setdefault("doc_id", doc_id)
            row.setdefault("metadata", {})
            if isinstance(row["metadata"], dict):
                row["metadata"]["generated_doc_id_during_filtered_candidate"] = True

        if doc_id in seen:
            duplicates.append({"doc_id": doc_id, "title": row.get("title"), "year": row.get("year")})
            continue
        seen.add(doc_id)
        out.append(row)

    return out, duplicates


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    doc_ids = [canonical_doc_id(row) for row in rows if canonical_doc_id(row)]
    arxiv_bases: list[str] = []
    dois: list[str] = []
    title_years: list[tuple[str, int]] = []

    for row in rows:
        arxiv_bases.extend(sorted(doc_arxiv_bases(row)))
        doi = doc_doi(row)
        if doi:
            dois.append(doi)
        title_year = doc_title_year_key(row)
        if title_year:
            title_years.append(title_year)

    doc_id_counts = Counter(doc_ids)
    arxiv_counts = Counter(arxiv_bases)
    doi_counts = Counter(dois)
    title_year_counts = Counter(title_years)
    family_sets = Counter(family_set_key(row) for row in rows)

    return {
        "rows_count": len(rows),
        "doc_ids_count": len(doc_ids),
        "duplicate_doc_id_count": sum(1 for _, count in doc_id_counts.items() if count > 1),
        "duplicate_doc_ids_sample": [key for key, count in doc_id_counts.items() if count > 1][:20],
        "arxiv_base_count": len(set(arxiv_bases)),
        "duplicate_arxiv_base_count": sum(1 for _, count in arxiv_counts.items() if count > 1),
        "duplicate_arxiv_base_sample": [key for key, count in arxiv_counts.items() if count > 1][:20],
        "doi_count": len(dois),
        "duplicate_doi_count": sum(1 for _, count in doi_counts.items() if count > 1),
        "duplicate_doi_sample": [key for key, count in doi_counts.items() if count > 1][:20],
        "duplicate_title_year_count": sum(1 for _, count in title_year_counts.items() if count > 1),
        "duplicate_title_year_sample": [f"{key[1]}::{key[0]}" for key, count in title_year_counts.items() if count > 1][:20],
        "acl_family_docs_count": sum(1 for row in rows if has_acl_family(row)),
        "acl_family_only_docs_count": sum(1 for row in rows if is_acl_family_only(row)),
        "acl_family_with_arxiv_docs_count": sum(1 for row in rows if has_acl_family(row) and has_arxiv_family(row)),
        "arxiv_family_docs_count": sum(1 for row in rows if has_arxiv_family(row)),
        "source_family_sets_top20": dict(family_sets.most_common(20)),
    }


def build_filtered_candidate(
    baseline_rows: list[dict[str, Any]],
    raw_candidate_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    baseline_indexes = build_indexes(baseline_rows)
    baseline_by_doc_id = {canonical_doc_id(row): row for row in baseline_rows if canonical_doc_id(row)}
    baseline_doc_ids = set(baseline_by_doc_id.keys())

    output_by_baseline_doc_id: dict[str, dict[str, Any]] = dict(baseline_by_doc_id)

    updated_baseline_docs_with_acl: list[dict[str, Any]] = []
    added_acl_source_only: list[dict[str, Any]] = []
    excluded_non_acl_added: list[dict[str, Any]] = []
    excluded_acl_potential_baseline_matches: list[dict[str, Any]] = []
    excluded_acl_non_source_only_without_exact_match: list[dict[str, Any]] = []

    for candidate_doc in raw_candidate_rows:
        exact_match = find_baseline_exact_match(candidate_doc, baseline_indexes)
        soft_match_kind, soft_match = find_baseline_soft_match(candidate_doc, baseline_indexes)
        has_acl = has_acl_family(candidate_doc)
        has_arxiv = has_arxiv_family(candidate_doc)

        if exact_match is not None:
            # Candidate represents an existing baseline paper. Only use it when
            # ACL provenance was safely merged into an arXiv/doc-id exact match.
            if has_acl and has_arxiv:
                baseline_id = canonical_doc_id(exact_match)
                if baseline_id:
                    merged = merge_candidate_into_baseline_preserving_identity(exact_match, candidate_doc)
                    merged = backfill_acl_urls(merged)
                    output_by_baseline_doc_id[baseline_id] = merged
                    updated_baseline_docs_with_acl.append(merged)
            continue

        if has_acl:
            # ACL docs that softly match baseline by DOI/title+year are likely
            # duplicates of existing arXiv-backed papers, but raw reconcile did
            # not merge them. Exclude for manual inspection rather than replacing
            # arXiv-backed baseline rows or adding duplicate paper entities.
            if soft_match is not None:
                excluded_acl_potential_baseline_matches.append(
                    {
                        "candidate_doc": candidate_doc,
                        "match_kind": soft_match_kind,
                        "baseline_doc": soft_match,
                    }
                )
                continue

            # ACL-backed source-only papers are allowed as candidate additions,
            # regardless of whether they have ACL-only or ACL+other non-arXiv
            # family evidence. They must not have an exact/soft baseline match.
            if not has_arxiv:
                added_acl_source_only.append(backfill_acl_urls(candidate_doc))
            else:
                # Has ACL and arXiv labels but no exact baseline arXiv/doc-id match:
                # unsafe until inspected.
                excluded_acl_non_source_only_without_exact_match.append(candidate_doc)
            continue

        # No exact baseline match and no ACL evidence: this is one of the old
        # non-ACL side fragments and must not enter the ACL filtered candidate.
        excluded_non_acl_added.append(candidate_doc)

    filtered_rows = list(output_by_baseline_doc_id.values()) + added_acl_source_only
    filtered_rows, duplicate_output_doc_ids = dedupe_rows_by_identity(filtered_rows)

    output_doc_ids = {canonical_doc_id(row) for row in filtered_rows if canonical_doc_id(row)}
    missing_baseline_doc_ids = sorted(str(doc_id) for doc_id in baseline_doc_ids - output_doc_ids)

    def doc_sample(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "doc_id": canonical_doc_id(row),
            "title": row.get("title"),
            "doi": doc_doi(row),
            "source_family_set": family_set_key(row),
            "source_record_url": row.get("source_record_url") or row.get("canonical_url"),
        }

    diagnostics = {
        "updated_baseline_docs_with_acl_count": len(updated_baseline_docs_with_acl),
        "updated_baseline_docs_with_acl_sample": [doc_sample(row) for row in updated_baseline_docs_with_acl[:20]],
        # Backward-compatible key name from v1.1; now it means safe ACL source-only additions.
        "added_acl_family_only_docs_count": len(added_acl_source_only),
        "added_acl_family_only_docs_sample": [doc_sample(row) for row in added_acl_source_only[:20]],
        "added_acl_source_only_docs_count": len(added_acl_source_only),
        "added_acl_source_only_docs_sample": [doc_sample(row) for row in added_acl_source_only[:20]],
        "excluded_non_acl_added_docs_count": len(excluded_non_acl_added),
        "excluded_non_acl_source_family_sets_top20": dict(
            Counter(family_set_key(row) for row in excluded_non_acl_added).most_common(20)
        ),
        "excluded_non_acl_added_docs_sample": [doc_sample(row) for row in excluded_non_acl_added[:20]],
        "excluded_acl_potential_baseline_matches_count": len(excluded_acl_potential_baseline_matches),
        "excluded_acl_potential_baseline_matches_by_kind": dict(
            Counter(str(item.get("match_kind") or "unknown") for item in excluded_acl_potential_baseline_matches).most_common()
        ),
        "excluded_acl_potential_baseline_matches_sample": [
            {
                "match_kind": item.get("match_kind"),
                "candidate": doc_sample(item["candidate_doc"]),
                "baseline": doc_sample(item["baseline_doc"]),
            }
            for item in excluded_acl_potential_baseline_matches[:20]
        ],
        "excluded_acl_non_source_only_without_exact_match_count": len(excluded_acl_non_source_only_without_exact_match),
        "excluded_acl_non_source_only_without_exact_match_sample": [
            doc_sample(row) for row in excluded_acl_non_source_only_without_exact_match[:20]
        ],
        "duplicate_output_doc_ids_removed_count": len(duplicate_output_doc_ids),
        "duplicate_output_doc_ids_removed_sample": duplicate_output_doc_ids[:20],
        "missing_baseline_doc_ids_count": len(missing_baseline_doc_ids),
        "missing_baseline_doc_ids_sample": missing_baseline_doc_ids[:20],
    }

    return filtered_rows, diagnostics

def acl_url_coverage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = 0
    missing_any_url = 0
    missing_landing_page_url = 0
    missing_canonical_url = 0
    missing_source_record_url = 0
    sample: list[dict[str, Any]] = []

    for row in rows:
        if not has_acl_family(row):
            continue
        total += 1
        has_any = bool(row.get("landing_page_url") or row.get("canonical_url") or row.get("source_record_url"))
        if not has_any:
            missing_any_url += 1
            if len(sample) < 10:
                sample.append(doc_sample_basic(row))
        if not row.get("landing_page_url"):
            missing_landing_page_url += 1
        if not row.get("canonical_url"):
            missing_canonical_url += 1
        if not row.get("source_record_url"):
            missing_source_record_url += 1

    return {
        "acl_family_docs_count": total,
        "missing_any_url_count": missing_any_url,
        "missing_landing_page_url_count": missing_landing_page_url,
        "missing_canonical_url_count": missing_canonical_url,
        "missing_source_record_url_count": missing_source_record_url,
        "missing_any_url_sample": sample,
    }


def doc_sample_basic(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "doc_id": canonical_doc_id(row),
        "title": row.get("title"),
        "doi": doc_doi(row),
        "source_family_set": family_set_key(row),
        "landing_page_url": row.get("landing_page_url"),
        "canonical_url": row.get("canonical_url"),
        "source_record_url": row.get("source_record_url"),
    }


def baseline_arxiv_bases(rows: list[dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    for row in rows:
        out.update(doc_arxiv_bases(row))
    return out


def build_markdown_report(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# ACL Anthology filtered candidate report")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at_utc']}`")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Baseline path: `{report['inputs']['baseline_path']}`")
    lines.append(f"- Raw candidate path: `{report['inputs']['candidate_path']}`")
    lines.append(f"- Output path: `{report['outputs']['filtered_candidate_path']}`")
    lines.append(f"- Dry run: `{report['dry_run']}`")
    lines.append("")
    lines.append("## Counts")
    for key in (
        "baseline_rows_count",
        "raw_candidate_rows_count",
        "filtered_candidate_rows_count",
        "filtered_candidate_delta_vs_baseline",
        "updated_baseline_docs_with_acl_count",
        "added_acl_family_only_docs_count",
        "excluded_non_acl_added_docs_count",
        "excluded_acl_potential_baseline_matches_count",
        "excluded_acl_non_source_only_without_exact_match_count",
        "missing_baseline_doc_ids_count",
        "missing_baseline_arxiv_base_count",
        "filtered_duplicate_arxiv_base_count",
        "filtered_duplicate_doi_count",
    ):
        lines.append(f"- {key}: `{report.get(key)}`")
    lines.append("")
    lines.append("## Filtered source family sets")
    for key, value in report.get("filtered_summary", {}).get("source_family_sets_top20", {}).items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    lines.append("## Excluded non-ACL additions")
    for key, value in report.get("excluded_non_acl_source_family_sets_top20", {}).items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    lines.append("## Required checks")
    for key in report.get("required_check_names", []):
        lines.append(f"- {key}: `{report['checks'].get(key)}`")
    lines.append("")
    lines.append(f"- required_failed_count: `{report['required_failed_count']}`")
    lines.append(f"- ok: `{report['ok']}`")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a safe ACL Anthology filtered canonical candidate: stable baseline plus "
            "ACL-only additions and ACL enrichment on matched baseline docs, excluding non-ACL fragments."
        )
    )
    parser.add_argument("--baseline-path", type=Path, default=DEFAULT_BASELINE_PATH)
    parser.add_argument("--candidate-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--dry-run", action="store_true", help="Build report but do not write filtered candidate JSONL.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_ts = utc_now_ts()

    if not args.baseline_path.exists():
        raise FileNotFoundError(f"Baseline canonical file not found: {args.baseline_path}")
    if not args.candidate_path.exists():
        raise FileNotFoundError(f"Raw ACL candidate file not found: {args.candidate_path}")

    output_path = args.output_dir / f"canonical_documents.acl_anthology_filtered_candidate.{run_ts}.jsonl"

    if output_path.resolve() == STABLE_CANONICAL_PATH.resolve():
        raise RuntimeError("Refusing to write filtered candidate to stable canonical_documents.jsonl")

    print(f"[INFO] Loading baseline: {args.baseline_path}")
    baseline_rows = load_jsonl(args.baseline_path)
    print(f"[INFO] Loading raw candidate: {args.candidate_path}")
    raw_candidate_rows = load_jsonl(args.candidate_path)

    filtered_rows, diagnostics = build_filtered_candidate(baseline_rows, raw_candidate_rows)

    baseline_summary = summarize_rows(baseline_rows)
    raw_candidate_summary = summarize_rows(raw_candidate_rows)
    filtered_summary = summarize_rows(filtered_rows)
    filtered_acl_url_coverage = acl_url_coverage(filtered_rows)

    baseline_bases = baseline_arxiv_bases(baseline_rows)
    filtered_bases = baseline_arxiv_bases(filtered_rows)
    missing_baseline_bases = sorted(baseline_bases - filtered_bases)

    checks = {
        "baseline_rows_non_empty": len(baseline_rows) > 0,
        "raw_candidate_rows_non_empty": len(raw_candidate_rows) > 0,
        "filtered_rows_non_empty": len(filtered_rows) > 0,
        "filtered_count_not_below_baseline": len(filtered_rows) >= len(baseline_rows),
        "added_acl_family_only_docs_non_empty": diagnostics["added_acl_family_only_docs_count"] > 0,
        "updated_baseline_docs_with_acl_non_empty": diagnostics["updated_baseline_docs_with_acl_count"] > 0,
        "excluded_non_acl_added_docs_non_empty": diagnostics["excluded_non_acl_added_docs_count"] > 0,
        "no_missing_baseline_doc_ids": diagnostics["missing_baseline_doc_ids_count"] == 0,
        "no_missing_baseline_arxiv_base": len(missing_baseline_bases) == 0,
        "no_duplicate_output_doc_ids_removed": diagnostics["duplicate_output_doc_ids_removed_count"] == 0,
        "filtered_no_duplicate_arxiv_base": filtered_summary["duplicate_arxiv_base_count"] == 0,
        "filtered_acl_urls_present": filtered_acl_url_coverage["missing_any_url_count"] == 0,
        "filtered_acl_canonical_urls_present": filtered_acl_url_coverage["missing_canonical_url_count"] == 0,
        "filtered_acl_source_record_urls_present": filtered_acl_url_coverage["missing_source_record_url_count"] == 0,
        "filtered_acl_docs_count_matches_selected_docs": filtered_summary["acl_family_docs_count"] == diagnostics["updated_baseline_docs_with_acl_count"] + diagnostics["added_acl_source_only_docs_count"],
        "output_path_is_not_stable_canonical": output_path.resolve() != STABLE_CANONICAL_PATH.resolve(),
    }

    required_check_names = [
        "baseline_rows_non_empty",
        "raw_candidate_rows_non_empty",
        "filtered_rows_non_empty",
        "filtered_count_not_below_baseline",
        "added_acl_family_only_docs_non_empty",
        "no_missing_baseline_doc_ids",
        "no_missing_baseline_arxiv_base",
        "no_duplicate_output_doc_ids_removed",
        "filtered_no_duplicate_arxiv_base",
        "filtered_acl_urls_present",
        "filtered_acl_canonical_urls_present",
        "filtered_acl_source_record_urls_present",
        "output_path_is_not_stable_canonical",
    ]

    required_failed_checks = [name for name in required_check_names if not checks.get(name)]

    report = {
        "report_name": "acl_anthology_filtered_candidate",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "dry_run": bool(args.dry_run),
        "inputs": {
            "baseline_path": normalize_path(args.baseline_path),
            "candidate_path": normalize_path(args.candidate_path),
        },
        "outputs": {
            "filtered_candidate_path": None if args.dry_run else normalize_path(output_path),
        },
        "baseline_rows_count": len(baseline_rows),
        "raw_candidate_rows_count": len(raw_candidate_rows),
        "filtered_candidate_rows_count": len(filtered_rows),
        "filtered_candidate_delta_vs_baseline": len(filtered_rows) - len(baseline_rows),
        "raw_candidate_delta_vs_baseline": len(raw_candidate_rows) - len(baseline_rows),
        "baseline_summary": baseline_summary,
        "raw_candidate_summary": raw_candidate_summary,
        "filtered_summary": filtered_summary,
        "filtered_acl_url_coverage": filtered_acl_url_coverage,
        "missing_baseline_arxiv_base_count": len(missing_baseline_bases),
        "missing_baseline_arxiv_base_sample": missing_baseline_bases[:20],
        "filtered_duplicate_arxiv_base_count": filtered_summary["duplicate_arxiv_base_count"],
        "filtered_duplicate_doi_count": filtered_summary["duplicate_doi_count"],
        **diagnostics,
        "checks": checks,
        "required_check_names": required_check_names,
        "required_failed_checks": required_failed_checks,
        "required_failed_count": len(required_failed_checks),
        "ok": len(required_failed_checks) == 0,
    }

    latest_json = args.report_dir / "acl_anthology_filtered_candidate_latest.json"
    latest_md = args.report_dir / "acl_anthology_filtered_candidate_latest.md"
    history_json = args.report_dir / "history" / f"acl_anthology_filtered_candidate_{run_ts}.json"
    history_md = args.report_dir / "history" / f"acl_anthology_filtered_candidate_{run_ts}.md"

    if not args.dry_run:
        print(f"[INFO] Writing filtered candidate: {output_path}")
        write_jsonl(output_path, filtered_rows)

    write_json(latest_json, report)
    write_json(history_json, report)
    write_text(latest_md, build_markdown_report(report))
    write_text(history_md, build_markdown_report(report))

    print(f"[OK] report JSON: {latest_json}")
    print(f"[OK] report MD: {latest_md}")
    print(f"[OK] history JSON: {history_json}")
    print(f"[OK] history MD: {history_md}")
    print(f"[CHECK] baseline_rows_count={len(baseline_rows)}")
    print(f"[CHECK] raw_candidate_rows_count={len(raw_candidate_rows)}")
    print(f"[CHECK] filtered_candidate_rows_count={len(filtered_rows)}")
    print(f"[CHECK] filtered_candidate_delta_vs_baseline={len(filtered_rows) - len(baseline_rows)}")
    print(f"[CHECK] updated_baseline_docs_with_acl_count={diagnostics['updated_baseline_docs_with_acl_count']}")
    print(f"[CHECK] added_acl_family_only_docs_count={diagnostics['added_acl_family_only_docs_count']}")
    print(f"[CHECK] excluded_non_acl_added_docs_count={diagnostics['excluded_non_acl_added_docs_count']}")
    print(f"[CHECK] missing_baseline_arxiv_base_count={len(missing_baseline_bases)}")
    print(f"[CHECK] filtered_duplicate_arxiv_base_count={filtered_summary['duplicate_arxiv_base_count']}")
    print(f"[CHECK] filtered_duplicate_doi_count={filtered_summary['duplicate_doi_count']}")
    print(f"[CHECK] filtered_acl_missing_any_url_count={filtered_acl_url_coverage['missing_any_url_count']}")
    print(f"[CHECK] filtered_acl_missing_canonical_url_count={filtered_acl_url_coverage['missing_canonical_url_count']}")
    print(f"[CHECK] filtered_acl_missing_source_record_url_count={filtered_acl_url_coverage['missing_source_record_url_count']}")
    print(f"[CHECK] required_failed_count={len(required_failed_checks)}")
    print(f"[CHECK] required_failed_checks={required_failed_checks}")
    print(f"[CHECK] ok={report['ok']}")
    if not args.dry_run:
        print(f"[OK] filtered_candidate_path={output_path}")

    if required_failed_checks:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
