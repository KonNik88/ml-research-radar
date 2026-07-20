#!/usr/bin/env python
"""Create a private reconciliation-audit ZIP from reports and a small data slice.

Read-only boundaries:
- does not run reconciliation;
- does not mutate canonical data, Postgres, Qdrant, retrieval, graphs, API, or UI;
- does not call live provider APIs;
- does not include full snapshots, raw payloads, PDFs, full text, embeddings,
  database dumps, .env files, or credentials;
- does not publish anything.

Run from the repository root:

    python scripts/validation/build_reconciliation_audit_package.py

Recommended:

    python scripts/validation/build_reconciliation_audit_package.py \
        --strict-reports --max-papers 18 --semantic-scholar-min 6
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


PACKAGE_SCHEMA_VERSION = "reconciliation_evidence_audit_package_v1"
PACKAGE_VERSION = "v0.1"

DEFAULT_CANONICAL = Path("data/analytics/reconciled/canonical_documents.jsonl")
DEFAULT_NORMALIZED_DIR = Path("data/normalized")
DEFAULT_REPORTS_ROOT = Path("artifacts/reports")
DEFAULT_OUTPUT_ROOT = Path("artifacts/audit/reconciliation_evidence_package_v0.1")

PRIMARY_SNAPSHOT_RE = re.compile(r"^documents\.\d{8}T\d{6}Z\.jsonl$")
DOI_PREFIX_RE = re.compile(
    r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE
)
ARXIV_PREFIX_RE = re.compile(
    r"^(?:https?://arxiv\.org/(?:abs|pdf)/|arxiv:\s*)", re.IGNORECASE
)
OPENALEX_RE = re.compile(r"(?:https?://openalex\.org/)?(W\d+)$", re.IGNORECASE)

SOURCE_FAMILY_TO_DIR = {
    "arxiv": "arxiv",
    "openalex": "openalex_alignment",
    "semantic_scholar": "semantic_scholar_alignment",
    "crossref": "crossref_alignment",
    "acl_anthology": "acl_anthology",
}

SOURCE_ALIASES = {
    "arxiv": "arxiv",
    "openalex": "openalex",
    "openalex_alignment": "openalex",
    "semantic_scholar": "semantic_scholar",
    "semantic_scholar_alignment": "semantic_scholar",
    "semanticscholar": "semantic_scholar",
    "s2": "semantic_scholar",
    "crossref": "crossref",
    "crossref_alignment": "crossref",
    "acl": "acl_anthology",
    "acl_anthology": "acl_anthology",
    "aclanthology": "acl_anthology",
}

MATCH_FIELDS = (
    "doc_id",
    "source_record_id",
    "source_id",
    "source_record_url",
    "canonical_url",
    "landing_page_url",
    "source_api_url",
)

MATCH_PRIORITY = {
    "doc_id": 100,
    "source_record_id": 90,
    "source_id": 80,
    "source_record_url": 70,
    "canonical_url": 60,
    "landing_page_url": 50,
    "source_api_url": 40,
}


@dataclass(frozen=True)
class ReportSpec:
    label: str
    required: bool
    tokens: tuple[str, ...]
    excluded: tuple[str, ...] = ()


REPORT_SPECS = (
    ReportSpec("canonical_contract", True, ("canonical", "contract"), ("provenance",)),
    ReportSpec(
        "canonical_provenance_consistency",
        True,
        ("canonical", "provenance", "consistency"),
    ),
    ReportSpec("postpass_audit_summary", True, ("postpass", "audit", "summary")),
    ReportSpec(
        "source_observation_identity_contract",
        False,
        ("source", "observation", "identity"),
    ),
    # test_db_read.py is currently a console smoke script and does not
    # persist a JSON/MD report. Therefore its report is useful when present
    # but must not block --strict-reports. DB materialization evidence is
    # still captured through export/validation reports and the data slice.
    ReportSpec("db_read", False, ("db", "read"), ("artifact",)),
    ReportSpec("artifact_db_read", False, ("artifact", "db", "read")),
    ReportSpec(
        "dataset_release_readiness", False, ("dataset", "release", "readiness")
    ),
    ReportSpec(
        "public_metadata_release_policy",
        False,
        ("public", "metadata", "release", "policy"),
    ),
    ReportSpec(
        "public_metadata_release_review_evidence",
        False,
        ("public", "metadata", "release", "review", "evidence"),
    ),
    ReportSpec(
        "public_metadata_release_review",
        False,
        ("public", "metadata", "release", "review"),
        ("evidence", "decision"),
    ),
    ReportSpec(
        "public_metadata_release_decision",
        False,
        ("public", "metadata", "release", "decision"),
    ),
    ReportSpec(
        "acl_anthology_canonical_impact", False, ("acl", "canonical", "impact")
    ),
)

CATEGORY_ORDER = (
    "arxiv_only",
    "arxiv_openalex",
    "arxiv_semantic_scholar",
    "arxiv_crossref",
    "multisource_doi",
    "arxiv_id_without_doi",
    "title_year_fallback",
    "acl_only",
    "acl_enriched_existing",
    "doi_conflict_or_incomplete",
)


def utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def norm_path(value: Path | str) -> str:
    return str(value).replace("\\", "/")


def text(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def source_family(value: Any) -> str | None:
    raw = text(value)
    if raw is None:
        return None
    key = raw.lower().replace("-", "_").replace(" ", "_")
    return SOURCE_ALIASES.get(key, key)


def canonical_families(doc: Mapping[str, Any]) -> set[str]:
    result: set[str] = set()
    for item in as_list(doc.get("sources")):
        family = source_family(as_dict(item).get("source"))
        if family:
            result.add(family)
    return result


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_no, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL {path}:{line_no}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"JSONL row is not an object: {path}:{line_no}")
            yield row


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def is_title_year_fallback(doc: Mapping[str, Any]) -> bool:
    key = str(doc.get("reconciliation_key") or "").strip().lower()
    if key.startswith("title_year") or key.startswith("title+year"):
        return True
    return bool(
        not doc.get("doi")
        and not doc.get("arxiv_id")
        and doc.get("title")
        and doc.get("year")
    )


def is_conflict_or_incomplete(doc: Mapping[str, Any]) -> bool:
    key = str(doc.get("reconciliation_key") or "").strip().lower()
    if key.startswith("doi_conflict"):
        return True
    completeness = safe_float(doc.get("metadata_completeness_score"))
    if completeness is not None and completeness < 0.50:
        return True
    missing = sum(
        not bool(doc.get(field))
        for field in ("abstract", "authors", "year", "doi", "arxiv_id")
    )
    return missing >= 3


def predicates() -> dict[str, Callable[[Mapping[str, Any], set[str]], bool]]:
    return {
        "arxiv_only": lambda doc, families: families == {"arxiv"},
        "arxiv_openalex": lambda doc, families: {
            "arxiv",
            "openalex",
        }.issubset(families),
        "arxiv_semantic_scholar": lambda doc, families: {
            "arxiv",
            "semantic_scholar",
        }.issubset(families),
        "arxiv_crossref": lambda doc, families: {
            "arxiv",
            "crossref",
        }.issubset(families),
        "multisource_doi": lambda doc, families: len(families) >= 3
        and bool(doc.get("doi")),
        "arxiv_id_without_doi": lambda doc, families: bool(doc.get("arxiv_id"))
        and not bool(doc.get("doi")),
        "title_year_fallback": lambda doc, families: is_title_year_fallback(doc),
        "acl_only": lambda doc, families: families == {"acl_anthology"},
        "acl_enriched_existing": lambda doc, families: "acl_anthology" in families
        and len(families) >= 2,
        "doi_conflict_or_incomplete": lambda doc, families: is_conflict_or_incomplete(
            doc
        ),
    }


def select_sample(
    canonical_path: Path,
    max_papers: int,
    semantic_scholar_min: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    checks = predicates()
    pools: dict[str, list[dict[str, Any]]] = {name: [] for name in checks}
    s2_pool: list[dict[str, Any]] = []
    fill_pool: list[dict[str, Any]] = []
    corpus_rows = 0

    for doc in iter_jsonl(canonical_path):
        corpus_rows += 1
        families = canonical_families(doc)
        for name, check in checks.items():
            if len(pools[name]) < 100 and check(doc, families):
                pools[name].append(doc)
        if "semantic_scholar" in families and len(s2_pool) < 250:
            s2_pool.append(doc)
        if len(families) >= 2 and len(fill_pool) < 250:
            fill_pool.append(doc)

    selected: dict[str, dict[str, Any]] = {}
    reasons: dict[str, list[str]] = defaultdict(list)

    def add(doc: Mapping[str, Any], reason: str) -> bool:
        canonical_id = text(doc.get("canonical_id"))
        if canonical_id is None:
            return False
        if canonical_id not in selected:
            if len(selected) >= max_papers:
                return False
            selected[canonical_id] = dict(doc)
        if reason not in reasons[canonical_id]:
            reasons[canonical_id].append(reason)
        return True

    for category in CATEGORY_ORDER:
        choice = next(
            (
                row
                for row in pools[category]
                if text(row.get("canonical_id")) not in selected
            ),
            pools[category][0] if pools[category] else None,
        )
        if choice is not None:
            add(choice, category)

    def selected_s2_count() -> int:
        return sum(
            "semantic_scholar" in canonical_families(row)
            for row in selected.values()
        )

    for row in s2_pool:
        if selected_s2_count() >= semantic_scholar_min:
            break
        add(row, "semantic_scholar_evidence_sample")

    target_min = min(max_papers, max(12, semantic_scholar_min))
    for row in fill_pool:
        if len(selected) >= target_min:
            break
        add(row, "multisource_fill")

    rows = list(selected.values())
    summary = {
        "canonical_corpus_path": norm_path(canonical_path),
        "canonical_corpus_rows_seen": corpus_rows,
        "requested_max_papers": max_papers,
        "requested_semantic_scholar_min": semantic_scholar_min,
        "selected_paper_count": len(rows),
        "selected_semantic_scholar_count": selected_s2_count(),
        "category_candidate_counts": {name: len(pool) for name, pool in pools.items()},
        "missing_categories": [name for name, pool in pools.items() if not pool],
        "selected": [
            {
                "canonical_id": row.get("canonical_id"),
                "title": row.get("title"),
                "year": row.get("year"),
                "doi": row.get("doi"),
                "arxiv_id": row.get("arxiv_id"),
                "reconciliation_key": row.get("reconciliation_key"),
                "source_families": sorted(canonical_families(row)),
                "source_count": row.get("source_count"),
                "unique_source_count": row.get("unique_source_count"),
                "metadata_completeness_score": row.get(
                    "metadata_completeness_score"
                ),
                "selection_reasons": reasons[str(row.get("canonical_id"))],
            }
            for row in rows
        ],
    }
    return rows, summary


def latest_snapshot(source_dir: Path) -> tuple[Path | None, str]:
    if not source_dir.is_dir():
        return None, "source_directory_missing"
    timestamped = sorted(
        path
        for path in source_dir.glob("documents.*.jsonl")
        if PRIMARY_SNAPSHOT_RE.match(path.name)
    )
    if timestamped:
        return timestamped[-1], "latest_primary_timestamped_snapshot"
    for name in ("documents_latest.jsonl", "documents.latest.jsonl"):
        candidate = source_dir / name
        if candidate.exists():
            return candidate, "latest_pointer_fallback"
    return None, "no_snapshot_found"


def normalize_match_value(family: str, field: str, value: Any) -> str | None:
    raw = text(value)
    if raw is None:
        return None
    raw = raw.strip()
    if field.endswith("url") or field in {
        "canonical_url",
        "landing_page_url",
        "source_api_url",
    }:
        return raw.rstrip("/").lower()
    if family == "crossref" or "doi.org/" in raw.lower() or raw.lower().startswith(
        ("doi:", "10.")
    ):
        return DOI_PREFIX_RE.sub("", raw).rstrip("/").strip().lower()
    if family == "arxiv":
        return ARXIV_PREFIX_RE.sub("", raw).replace(".pdf", "").strip().lower()
    if family == "openalex":
        match = OPENALEX_RE.search(raw)
        return match.group(1).upper() if match else raw.upper()
    if family == "semantic_scholar":
        return raw.lower()
    if family == "acl_anthology":
        if "aclanthology.org/" in raw.lower():
            raw = raw.rstrip("/").rsplit("/", 1)[-1]
        return raw.lower()
    return raw


@dataclass(frozen=True)
class WantedLink:
    ref_id: str
    canonical_id: str
    family: str
    link: dict[str, Any]
    doc_ids: tuple[str, ...]


@dataclass(frozen=True)
class Match:
    score: int
    basis: str
    family: str
    row: dict[str, Any]
    snapshot: Path


def build_wanted_links(
    selected_docs: Sequence[Mapping[str, Any]],
) -> tuple[list[WantedLink], dict[tuple[str, str, str], list[str]]]:
    links: list[WantedLink] = []
    index: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for doc in selected_docs:
        canonical_id = text(doc.get("canonical_id"))
        if canonical_id is None:
            continue
        doc_ids = tuple(
            str(item) for item in as_list(doc.get("doc_ids")) if text(item)
        )
        for position, raw_link in enumerate(as_list(doc.get("sources"))):
            link = as_dict(raw_link)
            family = source_family(link.get("source"))
            if family not in SOURCE_FAMILY_TO_DIR:
                continue
            ref_id = f"{canonical_id}:{position}:{family}"
            links.append(WantedLink(ref_id, canonical_id, family, link, doc_ids))
            for field in MATCH_FIELDS:
                value = normalize_match_value(family, field, link.get(field))
                if value is not None:
                    index[(family, field, value)].append(ref_id)
            for doc_id in doc_ids:
                value = normalize_match_value(family, "doc_id", doc_id)
                if value is not None:
                    index[(family, "doc_id", value)].append(ref_id)
    return links, index


def resolve_source_rows(
    selected_docs: Sequence[Mapping[str, Any]],
    normalized_dir: Path,
) -> tuple[
    dict[str, list[dict[str, Any]]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any],
]:
    wanted_links, wanted_index = build_wanted_links(selected_docs)
    matches: dict[str, list[Match]] = defaultdict(list)
    snapshots: dict[str, dict[str, Any]] = {}

    for family, directory_name in SOURCE_FAMILY_TO_DIR.items():
        source_dir = normalized_dir / directory_name
        snapshot, basis = latest_snapshot(source_dir)
        snapshots[family] = {
            "source_directory": norm_path(source_dir),
            "snapshot_path": norm_path(snapshot) if snapshot else None,
            "selection_basis": basis,
            "rows_scanned": 0,
        }
        if snapshot is None:
            continue
        scanned = 0
        for row in iter_jsonl(snapshot):
            scanned += 1
            seen: set[tuple[str, str]] = set()
            for field in MATCH_FIELDS:
                value = normalize_match_value(family, field, row.get(field))
                if value is None:
                    continue
                for ref_id in wanted_index.get((family, field, value), []):
                    marker = (ref_id, field)
                    if marker in seen:
                        continue
                    seen.add(marker)
                    matches[ref_id].append(
                        Match(MATCH_PRIORITY[field], field, family, dict(row), snapshot)
                    )
        snapshots[family]["rows_scanned"] = scanned

    link_rows: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    per_family: dict[str, dict[tuple[str, str, str], dict[str, Any]]] = {
        family: {} for family in SOURCE_FAMILY_TO_DIR
    }
    combined: dict[tuple[str, str, str], dict[str, Any]] = {}

    for wanted in wanted_links:
        candidates = sorted(
            matches.get(wanted.ref_id, []),
            key=lambda item: (
                -item.score,
                str(item.row.get("doc_id") or ""),
                str(item.row.get("source_record_id") or ""),
            ),
        )
        best = candidates[0] if candidates else None
        link_row = {
            "canonical_id": wanted.canonical_id,
            "source_family": wanted.family,
            "source_link": wanted.link,
            "matched": best is not None,
            "resolved_doc_id": best.row.get("doc_id") if best else None,
            "match_basis": best.basis if best else None,
            "match_score": best.score if best else None,
            "candidate_match_count": len(candidates),
            "snapshot_path": (
                norm_path(best.snapshot)
                if best
                else snapshots.get(wanted.family, {}).get("snapshot_path")
            ),
        }
        link_rows.append(link_row)
        if best is None:
            unmatched.append(link_row)
            continue

        key = (
            wanted.family,
            str(best.row.get("doc_id") or ""),
            str(best.row.get("source_record_id") or ""),
        )
        per_family[wanted.family][key] = best.row
        record = combined.setdefault(
            key,
            {
                **best.row,
                "_audit_source_family": wanted.family,
                "_audit_snapshot_path": norm_path(best.snapshot),
                "_audit_canonical_ids": [],
                "_audit_match_bases": [],
            },
        )
        if wanted.canonical_id not in record["_audit_canonical_ids"]:
            record["_audit_canonical_ids"].append(wanted.canonical_id)
        if best.basis not in record["_audit_match_bases"]:
            record["_audit_match_bases"].append(best.basis)

    exact_rows = {family: list(rows.values()) for family, rows in per_family.items()}
    combined_rows = list(combined.values())
    diagnostics = {
        "wanted_canonical_source_link_count": len(wanted_links),
        "matched_canonical_source_link_count": len(wanted_links) - len(unmatched),
        "unmatched_canonical_source_link_count": len(unmatched),
        "matched_source_document_count": len(combined_rows),
        "matched_source_document_counts_by_family": {
            family: len(rows) for family, rows in exact_rows.items()
        },
        "snapshots": snapshots,
    }
    return exact_rows, combined_rows, link_rows, unmatched, diagnostics


def report_match(path: Path, spec: ReportSpec, require_latest: bool) -> bool:
    name = path.name.lower()
    if path.suffix.lower() not in {".json", ".md"}:
        return False
    if "history" in {part.lower() for part in path.parts}:
        return False
    if require_latest and "latest" not in name:
        return False
    return all(token in name for token in spec.tokens) and not any(
        token in name for token in spec.excluded
    )


def report_candidates(reports_root: Path, spec: ReportSpec) -> list[Path]:
    if not reports_root.is_dir():
        return []
    files = [path for path in reports_root.rglob("*") if path.is_file()]
    candidates = [path for path in files if report_match(path, spec, True)]
    if not candidates:
        candidates = [path for path in files if report_match(path, spec, False)]
    return sorted(
        candidates,
        key=lambda path: (
            path.suffix.lower() != ".json",
            -path.stat().st_mtime,
            norm_path(path),
        ),
    )


def collect_reports(
    project_root: Path, reports_root: Path, staging: Path
) -> dict[str, Any]:
    found: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    copied: set[Path] = set()

    for spec in REPORT_SPECS:
        candidates = report_candidates(reports_root, spec)
        if not candidates:
            missing.append({"label": spec.label, "required": spec.required})
            continue
        primary = candidates[0]
        group_files = [primary]
        pair = primary.with_suffix(".md" if primary.suffix.lower() == ".json" else ".json")
        if pair.exists():
            group_files.append(pair)
        package_paths: list[str] = []
        for source in group_files:
            if source.resolve() in copied:
                continue
            copied.add(source.resolve())
            try:
                relative = source.relative_to(project_root)
            except ValueError:
                relative = Path(source.name)
            destination = staging / "reports" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            package_paths.append(norm_path(destination.relative_to(staging)))
        found.append(
            {
                "label": spec.label,
                "required": spec.required,
                "primary_source_path": norm_path(primary),
                "candidate_count": len(candidates),
                "copied_files": package_paths,
            }
        )

    return {
        "reports_root": norm_path(reports_root),
        "found": found,
        "missing": missing,
        "required_missing": [row["label"] for row in missing if row["required"]],
    }


def collect_inventories(project_root: Path, staging: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for name in (
        "reconciliation_inventory.txt",
        "source_materialization_inventory.txt",
    ):
        source = project_root / name
        if not source.exists():
            continue
        destination = staging / "inventories" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        result.append(
            {
                "source_path": norm_path(source),
                "package_path": norm_path(destination.relative_to(staging)),
            }
        )
    return result


def file_inventory(staging: Path, excluded: set[str] | None = None) -> list[dict[str, Any]]:
    excluded = excluded or set()
    result: list[dict[str, Any]] = []
    for path in sorted(item for item in staging.rglob("*") if item.is_file()):
        relative = path.relative_to(staging)
        if relative.name in excluded:
            continue
        result.append(
            {
                "path": norm_path(relative),
                "size_bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    return result


def write_checksums(staging: Path) -> None:
    target = staging / "checksums.txt"
    lines = []
    for path in sorted(item for item in staging.rglob("*") if item.is_file()):
        if path == target:
            continue
        lines.append(f"{sha256(path)}  {norm_path(path.relative_to(staging))}")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def create_zip(staging: Path, zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        zip_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for path in sorted(item for item in staging.rglob("*") if item.is_file()):
            archive.write(
                path,
                arcname=norm_path(Path(staging.name) / path.relative_to(staging)),
            )


def build_readme(
    selection: Mapping[str, Any],
    source_diag: Mapping[str, Any],
    reports: Mapping[str, Any],
) -> str:
    return "\n".join(
        [
            "# ML Research Radar — Reconciliation Evidence Audit Package v0.1",
            "",
            "Status: `internal_review_only`",
            "",
            "This is a small read-only evidence bundle for reviewing canonical reconciliation and provenance.",
            "It is not canonical truth, not a reconcile input, not a public dataset release, and not publication approval.",
            "",
            "## Included",
            "",
            "- selected latest validation/release/DB reports when present;",
            "- a representative canonical sample;",
            "- matched normalized source observations from latest primary snapshots;",
            "- canonical-source link resolution diagnostics;",
            "- optional grep inventories;",
            "- manifest and SHA256 checksums.",
            "",
            "## Excluded",
            "",
            "- full canonical corpus and full normalized snapshots;",
            "- raw provider payloads, PDFs, full text, embeddings, DB dumps, graph outputs;",
            "- `.env`, credentials, and API keys.",
            "",
            "## Safety note",
            "",
            "Semantic Scholar-derived rows, when included, are private diagnostic evidence only and are not cleared for public redistribution.",
            "",
            "## Summary",
            "",
            f"- selected papers: `{selection.get('selected_paper_count')}`",
            f"- selected S2 papers: `{selection.get('selected_semantic_scholar_count')}`",
            f"- matched source links: `{source_diag.get('matched_canonical_source_link_count')}`",
            f"- unmatched source links: `{source_diag.get('unmatched_canonical_source_link_count')}`",
            f"- matched source documents: `{source_diag.get('matched_source_document_count')}`",
            f"- report groups found: `{len(reports.get('found', []))}`",
            f"- required report groups missing: `{reports.get('required_missing', [])}`",
            "",
            "Review `manifest.json` first.",
            "",
        ]
    )


def resolve_project_root(explicit: Path | None) -> Path:
    if explicit is not None:
        root = explicit.resolve()
        if not root.is_dir():
            raise NotADirectoryError(root)
        return root
    candidates = [Path.cwd().resolve()]
    script = Path(__file__).resolve()
    if len(script.parents) >= 3:
        candidates.append(script.parents[2])
    for candidate in candidates:
        if (candidate / DEFAULT_CANONICAL).exists():
            return candidate
    raise FileNotFoundError(
        "Could not detect repository root. Run from the repository root or pass --project-root."
    )


def under_root(root: Path, explicit: Path | None, default: Path) -> Path:
    path = explicit or default
    return path if path.is_absolute() else root / path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a private reports + reconciliation data-slice ZIP."
    )
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--canonical-path", type=Path)
    parser.add_argument("--normalized-dir", type=Path)
    parser.add_argument("--reports-root", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--max-papers", type=int, default=18)
    parser.add_argument("--semantic-scholar-min", type=int, default=6)
    parser.add_argument("--strict-reports", action="store_true")
    parser.add_argument("--keep-staging", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 10 <= args.max_papers <= 50:
        raise ValueError("--max-papers must be between 10 and 50")
    if not 0 <= args.semantic_scholar_min <= args.max_papers:
        raise ValueError("--semantic-scholar-min must be between 0 and --max-papers")

    root = resolve_project_root(args.project_root)
    canonical = under_root(root, args.canonical_path, DEFAULT_CANONICAL)
    normalized = under_root(root, args.normalized_dir, DEFAULT_NORMALIZED_DIR)
    reports_root = under_root(root, args.reports_root, DEFAULT_REPORTS_ROOT)
    output_root = under_root(root, args.output_dir, DEFAULT_OUTPUT_ROOT)

    if not canonical.exists():
        raise FileNotFoundError(f"Canonical corpus not found: {canonical}")
    if not normalized.is_dir():
        raise NotADirectoryError(f"Normalized directory not found: {normalized}")

    run_ts = utc_ts()
    package_name = f"reconciliation_evidence_audit_{PACKAGE_VERSION}_{run_ts}"
    staging = output_root / package_name
    zip_path = output_root / f"{package_name}.zip"

    if staging.exists():
        if not args.force:
            raise FileExistsError(staging)
        shutil.rmtree(staging)
    if zip_path.exists():
        if not args.force:
            raise FileExistsError(zip_path)
        zip_path.unlink()
    staging.mkdir(parents=True)
    data_dir = staging / "data_slice"

    selected_docs, selection = select_sample(
        canonical,
        max_papers=args.max_papers,
        semantic_scholar_min=args.semantic_scholar_min,
    )
    write_jsonl(data_dir / "canonical_documents.sample.jsonl", selected_docs)
    write_json(
        data_dir / "sample_selection.json",
        {
            "schema_version": "reconciliation_audit_sample_selection_v1",
            "generated_at_utc": utc_iso(),
            **selection,
        },
    )

    per_family, combined_rows, link_rows, unmatched, source_diag = resolve_source_rows(
        selected_docs, normalized
    )
    filenames = {
        "arxiv": "arxiv.sample.jsonl",
        "openalex": "openalex_alignment.sample.jsonl",
        "semantic_scholar": "semantic_scholar_alignment.sample.jsonl",
        "crossref": "crossref_alignment.sample.jsonl",
        "acl_anthology": "acl_anthology.sample.jsonl",
    }
    for family, filename in filenames.items():
        write_jsonl(data_dir / filename, per_family.get(family, []))
    write_jsonl(data_dir / "source_documents.sample.jsonl", combined_rows)
    write_jsonl(data_dir / "canonical_source_links.sample.jsonl", link_rows)
    write_jsonl(data_dir / "unmatched_canonical_source_links.jsonl", unmatched)

    reports = collect_reports(root, reports_root, staging)
    inventories = collect_inventories(root, staging)
    if args.strict_reports and reports["required_missing"]:
        raise RuntimeError(
            "Required reports missing: " + ", ".join(reports["required_missing"])
        )

    (staging / "README.md").write_text(
        build_readme(selection, source_diag, reports), encoding="utf-8"
    )
    manifest = {
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "package_version": PACKAGE_VERSION,
        "package_name": package_name,
        "generated_at_utc": utc_iso(),
        "status": "internal_review_only",
        "publication_ready": False,
        "manual_review_required": True,
        "canonical_truth": False,
        "may_be_used_as_reconcile_input": False,
        "inputs": {
            "project_root": norm_path(root),
            "canonical_path": norm_path(canonical),
            "normalized_dir": norm_path(normalized),
            "reports_root": norm_path(reports_root),
        },
        "selection": selection,
        "source_evidence": source_diag,
        "reports": reports,
        "inventories": inventories,
        "safety": {
            "read_only_inputs": True,
            "run_reconciliation": False,
            "mutate_canonical_documents": False,
            "mutate_postgres": False,
            "mutate_qdrant": False,
            "mutate_retrieval_artifacts": False,
            "mutate_graph_outputs": False,
            "call_live_provider_apis": False,
            "publish_dataset": False,
            "include_full_canonical_corpus": False,
            "include_full_normalized_snapshots": False,
            "include_raw_provider_payloads": False,
            "include_pdfs": False,
            "include_full_text": False,
            "include_embeddings": False,
            "include_database_dump": False,
            "include_secrets": False,
            "semantic_scholar_rows_private_diagnostic_only": True,
        },
        "package_files_before_manifest_and_checksums": file_inventory(
            staging, {"manifest.json", "checksums.txt"}
        ),
    }
    write_json(staging / "manifest.json", manifest)
    write_checksums(staging)
    create_zip(staging, zip_path)

    result = {
        "ok": True,
        "zip_path": norm_path(zip_path),
        "zip_size_bytes": zip_path.stat().st_size,
        "zip_sha256": sha256(zip_path),
        "selected_papers": selection["selected_paper_count"],
        "matched_source_documents": source_diag["matched_source_document_count"],
        "unmatched_source_links": source_diag[
            "unmatched_canonical_source_link_count"
        ],
        "reports_found": len(reports["found"]),
        "required_reports_missing": reports["required_missing"],
        "staging_dir": norm_path(staging) if args.keep_staging else None,
    }

    if not args.keep_staging:
        shutil.rmtree(staging)

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[ERROR] {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
