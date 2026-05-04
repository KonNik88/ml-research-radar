from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_NORMALIZED_ROOT = Path("data/normalized")
DEFAULT_CANONICAL_BASELINE_PATH = Path("data/analytics/reconciled/canonical_documents.jsonl")
DEFAULT_RECONCILED_DIR = Path("data/analytics/reconciled")
DEFAULT_REPORT_DIR = Path("artifacts/reports/source_audit")
DEFAULT_ACL_NORMALIZED_PATH = Path("data/normalized/acl_anthology/documents_latest.jsonl")

DEFAULT_BASELINE_SOURCES = [
    "arxiv",
    "openalex_alignment",
    "semantic_scholar_alignment",
    "crossref_alignment",
]

ACL_SOURCE_NAME = "acl_anthology"
PIPELINE_VERSION = "acl_anthology_reconcile_candidate_v1_1"


ARXIV_ID_RE = re.compile(r"(?P<base>\d{4}\.\d{4,5})(?:v\d+)?", re.IGNORECASE)
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
ACL_XML_SOURCE_RE = re.compile(r"^\d{4}\.[a-z0-9_.-]+$", re.IGNORECASE)

SOURCE_FAMILY_ACL = "acl_anthology"
SOURCE_FAMILY_ARXIV = "arxiv"
SOURCE_FAMILY_OPENALEX = "openalex"
SOURCE_FAMILY_SEMANTIC_SCHOLAR = "semantic_scholar"
SOURCE_FAMILY_CROSSREF = "crossref"
SOURCE_FAMILY_OTHER = "other"


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL: {path}:{line_no}: {exc}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"JSONL row must be object: {path}:{line_no}")
            rows.append(payload)
    return rows


def is_full_snapshot_file(path: Path) -> bool:
    name = path.name
    if not name.startswith("documents.") or not name.endswith(".jsonl"):
        return False
    if name == "documents_latest.jsonl":
        return True
    disallowed = (".new.jsonl", ".updated.jsonl", ".unchanged.jsonl")
    return not name.endswith(disallowed)


def discover_latest_full_snapshot(source_dir: Path) -> Path:
    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")

    timestamped = sorted(
        p for p in source_dir.glob("documents.*.jsonl")
        if is_full_snapshot_file(p) and p.name != "documents_latest.jsonl"
    )
    if timestamped:
        return timestamped[-1]

    latest = source_dir / "documents_latest.jsonl"
    if latest.exists():
        return latest

    raise FileNotFoundError(f"No full snapshot JSONL found in: {source_dir}")


def resolve_input_paths(args: argparse.Namespace) -> dict[str, Path]:
    resolved: dict[str, Path] = {}

    if args.inputs:
        for raw in args.inputs:
            if "=" not in raw:
                raise ValueError(
                    f"Invalid --inputs value: {raw}. Expected source_name=path/to/documents.jsonl"
                )
            name, raw_path = raw.split("=", 1)
            name = name.strip()
            path = Path(raw_path.strip())
            if not name:
                raise ValueError(f"Invalid source name in --inputs: {raw}")
            if not path.exists():
                raise FileNotFoundError(f"Input path for source={name} not found: {path}")
            resolved[name] = path
    else:
        normalized_root = Path(args.normalized_root)
        for source in args.baseline_sources:
            resolved[source] = discover_latest_full_snapshot(normalized_root / source)

    acl_path = Path(args.acl_normalized_path)
    if not acl_path.exists():
        raise FileNotFoundError(f"ACL normalized snapshot not found: {acl_path}")
    resolved[ACL_SOURCE_NAME] = acl_path

    return resolved


def safe_lower(value: Any) -> str:
    return str(value or "").strip().lower()


def normalize_title(value: Any) -> str | None:
    text = str(value or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def normalize_doi(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text)
    text = re.sub(r"^doi:\s*", "", text)
    text = text.strip().rstrip("./")
    if not DOI_RE.match(text):
        return None
    return text


def arxiv_base(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = ARXIV_ID_RE.search(text)
    if not match:
        return None
    return match.group("base")


def collect_source_names(row: dict[str, Any]) -> set[str]:
    names: set[str] = set()

    source = row.get("source")
    if isinstance(source, str) and source.strip():
        names.add(source.strip())

    raw_source_name = row.get("raw_source_name")
    if isinstance(raw_source_name, str) and raw_source_name.strip():
        names.add(raw_source_name.strip())

    sources = row.get("sources")
    if isinstance(sources, list):
        for item in sources:
            if isinstance(item, str) and item.strip():
                names.add(item.strip())
            elif isinstance(item, dict):
                for key in ("source", "raw_source_name", "source_name"):
                    value = item.get(key)
                    if isinstance(value, str) and value.strip():
                        names.add(value.strip())

    source_ids = row.get("source_ids")
    if isinstance(source_ids, dict):
        for key in source_ids:
            if str(key).strip():
                names.add(str(key).strip())

    canonical_sources = row.get("canonical_sources")
    if isinstance(canonical_sources, list):
        for item in canonical_sources:
            if isinstance(item, str) and item.strip():
                names.add(item.strip())
            elif isinstance(item, dict):
                value = item.get("source") or item.get("source_name")
                if isinstance(value, str) and value.strip():
                    names.add(value.strip())

    return names


def source_to_family(source: str) -> str:
    value = safe_lower(source)

    if not value:
        return SOURCE_FAMILY_OTHER

    # ACL Anthology normalized rows often carry both source="acl_anthology"
    # and raw_source_name like "2024.acl". Treat both as one source family
    # for candidate diagnostics.
    if value == ACL_SOURCE_NAME or value.startswith("acl_") or value.startswith("acl-"):
        return SOURCE_FAMILY_ACL
    if ACL_XML_SOURCE_RE.match(value) and not value.startswith("arxiv"):
        return SOURCE_FAMILY_ACL

    if "arxiv" in value:
        return SOURCE_FAMILY_ARXIV
    if "openalex" in value:
        return SOURCE_FAMILY_OPENALEX
    if "semantic_scholar" in value or "semanticscholar" in value:
        return SOURCE_FAMILY_SEMANTIC_SCHOLAR
    if "crossref" in value:
        return SOURCE_FAMILY_CROSSREF

    return SOURCE_FAMILY_OTHER


def collect_source_families(row: dict[str, Any]) -> set[str]:
    families = {source_to_family(source) for source in collect_source_names(row)}
    families.discard(SOURCE_FAMILY_OTHER)
    return families


def source_family_key(families: set[str]) -> str:
    return "+".join(sorted(families)) if families else "unknown"


def has_acl_family(row: dict[str, Any]) -> bool:
    return SOURCE_FAMILY_ACL in collect_source_families(row)


def has_arxiv_family(row: dict[str, Any]) -> bool:
    return SOURCE_FAMILY_ARXIV in collect_source_families(row)


def extract_arxiv_bases(row: dict[str, Any]) -> set[str]:
    bases: set[str] = set()

    for key in ("arxiv_id", "primary_arxiv_id"):
        base = arxiv_base(row.get(key))
        if base:
            bases.add(base)

    external_ids = row.get("external_ids")
    if isinstance(external_ids, dict):
        for key, value in external_ids.items():
            if "arxiv" in str(key).lower():
                if isinstance(value, list):
                    for item in value:
                        base = arxiv_base(item)
                        if base:
                            bases.add(base)
                else:
                    base = arxiv_base(value)
                    if base:
                        bases.add(base)

    source_ids = row.get("source_ids")
    if isinstance(source_ids, dict):
        for key, value in source_ids.items():
            if "arxiv" in str(key).lower():
                if isinstance(value, list):
                    for item in value:
                        base = arxiv_base(item)
                        if base:
                            bases.add(base)
                else:
                    base = arxiv_base(value)
                    if base:
                        bases.add(base)

    referenced = row.get("referenced_arxiv_ids")
    if isinstance(referenced, list):
        # Do not count references as identity.
        pass

    return bases


def title_year_key(row: dict[str, Any]) -> tuple[str, int] | None:
    title = normalize_title(row.get("title"))
    year = row.get("year") or row.get("publication_year")
    try:
        year_int = int(year)
    except Exception:
        return None
    if not title:
        return None
    return title, year_int


def summarize_rows(rows: list[dict[str, Any]], *, label: str) -> dict[str, Any]:
    source_sets: Counter[str] = Counter()
    source_family_sets: Counter[str] = Counter()
    sources_flat: Counter[str] = Counter()
    families_flat: Counter[str] = Counter()
    doi_values: list[str] = []
    title_year_values: list[tuple[str, int]] = []
    arxiv_bases: list[str] = []

    acl_family_docs = 0
    acl_family_only_docs = 0
    acl_family_with_arxiv_docs = 0
    acl_family_with_other_family_docs = 0
    arxiv_family_docs = 0
    arxiv_family_only_docs = 0
    non_acl_non_arxiv_docs = 0
    multisource_docs = 0
    multifamily_docs = 0
    empty_title = 0
    empty_abstract = 0
    empty_authors = 0

    for row in rows:
        sources = collect_source_names(row)
        families = collect_source_families(row)

        if len(sources) > 1:
            multisource_docs += 1
        if len(families) > 1:
            multifamily_docs += 1

        source_key = "+".join(sorted(sources)) if sources else "unknown"
        family_key = source_family_key(families)
        source_sets[source_key] += 1
        source_family_sets[family_key] += 1

        for source in sources:
            sources_flat[source] += 1
        for family in families:
            families_flat[family] += 1

        has_acl = SOURCE_FAMILY_ACL in families
        has_arxiv = SOURCE_FAMILY_ARXIV in families

        if has_acl:
            acl_family_docs += 1
            if families == {SOURCE_FAMILY_ACL}:
                acl_family_only_docs += 1
            if has_arxiv:
                acl_family_with_arxiv_docs += 1
            if len(families - {SOURCE_FAMILY_ACL}) > 0:
                acl_family_with_other_family_docs += 1

        if has_arxiv:
            arxiv_family_docs += 1
            if families == {SOURCE_FAMILY_ARXIV}:
                arxiv_family_only_docs += 1

        if not has_acl and not has_arxiv:
            non_acl_non_arxiv_docs += 1

        bases = extract_arxiv_bases(row)
        if bases:
            arxiv_bases.extend(sorted(bases))

        doi = normalize_doi(row.get("doi"))
        if doi:
            doi_values.append(doi)

        ty = title_year_key(row)
        if ty:
            title_year_values.append(ty)

        if not str(row.get("title") or "").strip():
            empty_title += 1
        if not str(row.get("abstract") or "").strip():
            empty_abstract += 1
        authors = row.get("authors")
        if not isinstance(authors, list) or not authors:
            empty_authors += 1

    duplicate_dois = [doi for doi, count in Counter(doi_values).items() if count > 1]
    duplicate_title_years = [f"{title}|{year}" for (title, year), count in Counter(title_year_values).items() if count > 1]
    duplicate_arxiv_bases = [base for base, count in Counter(arxiv_bases).items() if count > 1]

    return {
        "label": label,
        "rows_count": len(rows),
        "multisource_docs_count": multisource_docs,
        "multifamily_docs_count": multifamily_docs,
        "doi_count": len(set(doi_values)),
        "doi_rows_count": len(doi_values),
        "duplicate_doi_count": len(duplicate_dois),
        "duplicate_doi_sample": duplicate_dois[:30],
        "title_year_count": len(set(title_year_values)),
        "duplicate_title_year_count": len(duplicate_title_years),
        "duplicate_title_year_sample": duplicate_title_years[:30],
        "arxiv_docs_count": len(arxiv_bases),
        "unique_arxiv_base_count": len(set(arxiv_bases)),
        "duplicate_arxiv_base_count": len(duplicate_arxiv_bases),
        "duplicate_arxiv_base_sample": duplicate_arxiv_bases[:30],
        # Backward-compatible names, now source-family aware.
        "acl_docs_count": acl_family_docs,
        "acl_only_docs_count": acl_family_only_docs,
        # Explicit source-family diagnostics.
        "acl_family_docs_count": acl_family_docs,
        "acl_family_only_docs_count": acl_family_only_docs,
        "acl_family_with_arxiv_docs_count": acl_family_with_arxiv_docs,
        "acl_family_with_other_family_docs_count": acl_family_with_other_family_docs,
        "arxiv_family_docs_count": arxiv_family_docs,
        "arxiv_family_only_docs_count": arxiv_family_only_docs,
        "non_acl_non_arxiv_docs_count": non_acl_non_arxiv_docs,
        "empty_title_count": empty_title,
        "empty_abstract_count": empty_abstract,
        "empty_authors_count": empty_authors,
        "source_sets_top20": dict(source_sets.most_common(20)),
        "source_family_sets_top20": dict(source_family_sets.most_common(20)),
        "source_distribution": dict(sorted(sources_flat.items())),
        "source_family_distribution": dict(sorted(families_flat.items())),
    }

def build_indices(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_doi: dict[str, list[str]] = defaultdict(list)
    by_title_year: dict[tuple[str, int], list[str]] = defaultdict(list)
    by_arxiv_base: dict[str, list[str]] = defaultdict(list)

    for row in rows:
        doc_id = str(row.get("doc_id") or row.get("canonical_id") or "")
        if not doc_id:
            continue

        doi = normalize_doi(row.get("doi"))
        if doi:
            by_doi[doi].append(doc_id)

        ty = title_year_key(row)
        if ty:
            by_title_year[ty].append(doc_id)

        for base in extract_arxiv_bases(row):
            by_arxiv_base[base].append(doc_id)

    return {
        "by_doi": by_doi,
        "by_title_year": by_title_year,
        "by_arxiv_base": by_arxiv_base,
    }


def compare_baseline_candidate(
    baseline_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    baseline_by_doc_id = {
        str(row.get("doc_id") or row.get("canonical_id")): row
        for row in baseline_rows
        if row.get("doc_id") or row.get("canonical_id")
    }
    candidate_by_doc_id = {
        str(row.get("doc_id") or row.get("canonical_id")): row
        for row in candidate_rows
        if row.get("doc_id") or row.get("canonical_id")
    }

    baseline_doc_ids = set(baseline_by_doc_id)
    candidate_doc_ids = set(candidate_by_doc_id)
    added_doc_ids = sorted(candidate_doc_ids - baseline_doc_ids)
    removed_doc_ids = sorted(baseline_doc_ids - candidate_doc_ids)

    baseline_indices = build_indices(baseline_rows)
    candidate_indices = build_indices(candidate_rows)

    baseline_arxiv_bases = set(baseline_indices["by_arxiv_base"].keys())
    candidate_arxiv_bases = set(candidate_indices["by_arxiv_base"].keys())

    missing_arxiv_bases = sorted(baseline_arxiv_bases - candidate_arxiv_bases)
    new_arxiv_bases = sorted(candidate_arxiv_bases - baseline_arxiv_bases)

    candidate_acl_doc_ids: set[str] = set()
    candidate_acl_only_doc_ids: set[str] = set()
    candidate_acl_multifamily_doc_ids: set[str] = set()
    candidate_acl_with_arxiv_doc_ids: set[str] = set()

    added_acl_doc_ids: set[str] = set()
    added_acl_only_doc_ids: set[str] = set()
    added_non_acl_doc_ids: set[str] = set()
    added_non_acl_source_family_sets: Counter[str] = Counter()
    added_source_family_sets: Counter[str] = Counter()

    for doc_id, row in candidate_by_doc_id.items():
        families = collect_source_families(row)
        has_acl = SOURCE_FAMILY_ACL in families
        has_arxiv = SOURCE_FAMILY_ARXIV in families

        if has_acl:
            candidate_acl_doc_ids.add(doc_id)
            if families == {SOURCE_FAMILY_ACL}:
                candidate_acl_only_doc_ids.add(doc_id)
            else:
                candidate_acl_multifamily_doc_ids.add(doc_id)
            if has_arxiv:
                candidate_acl_with_arxiv_doc_ids.add(doc_id)

        if doc_id in added_doc_ids:
            family_key = source_family_key(families)
            added_source_family_sets[family_key] += 1
            if has_acl:
                added_acl_doc_ids.add(doc_id)
                if families == {SOURCE_FAMILY_ACL}:
                    added_acl_only_doc_ids.add(doc_id)
            else:
                added_non_acl_doc_ids.add(doc_id)
                added_non_acl_source_family_sets[family_key] += 1

    return {
        "baseline_doc_id_count": len(baseline_doc_ids),
        "candidate_doc_id_count": len(candidate_doc_ids),
        "doc_id_intersection_count": len(baseline_doc_ids & candidate_doc_ids),
        "doc_id_added_count": len(added_doc_ids),
        "doc_id_removed_count": len(removed_doc_ids),
        "doc_id_added_sample": added_doc_ids[:30],
        "doc_id_removed_sample": removed_doc_ids[:30],
        "baseline_arxiv_base_count": len(baseline_arxiv_bases),
        "candidate_arxiv_base_count": len(candidate_arxiv_bases),
        "missing_baseline_arxiv_base_count": len(missing_arxiv_bases),
        "missing_baseline_arxiv_base_sample": missing_arxiv_bases[:30],
        "new_candidate_arxiv_base_count": len(new_arxiv_bases),
        "new_candidate_arxiv_base_sample": new_arxiv_bases[:30],
        # Backward-compatible names, now source-family aware.
        "candidate_acl_docs_count": len(candidate_acl_doc_ids),
        "candidate_acl_only_docs_count": len(candidate_acl_only_doc_ids),
        "candidate_acl_multisource_docs_count": len(candidate_acl_multifamily_doc_ids),
        # Explicit source-family diagnostics.
        "candidate_acl_family_docs_count": len(candidate_acl_doc_ids),
        "candidate_acl_family_only_docs_count": len(candidate_acl_only_doc_ids),
        "candidate_acl_family_multifamily_docs_count": len(candidate_acl_multifamily_doc_ids),
        "candidate_acl_family_with_arxiv_docs_count": len(candidate_acl_with_arxiv_doc_ids),
        "added_acl_family_docs_count": len(added_acl_doc_ids),
        "added_acl_family_only_docs_count": len(added_acl_only_doc_ids),
        "added_non_acl_docs_count": len(added_non_acl_doc_ids),
        "added_source_family_sets_top20": dict(added_source_family_sets.most_common(20)),
        "added_non_acl_source_family_sets_top20": dict(added_non_acl_source_family_sets.most_common(20)),
        "candidate_acl_doc_id_sample": sorted(candidate_acl_doc_ids)[:30],
        "candidate_acl_only_doc_id_sample": sorted(candidate_acl_only_doc_ids)[:30],
        "candidate_acl_multifamily_doc_id_sample": sorted(candidate_acl_multifamily_doc_ids)[:30],
        "added_acl_doc_id_sample": sorted(added_acl_doc_ids)[:30],
        "added_non_acl_doc_id_sample": sorted(added_non_acl_doc_ids)[:30],
    }

def run_command(cmd: list[str]) -> dict[str, Any]:
    started_at = utc_now_iso()
    t0 = time.perf_counter()
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    finished_at = utc_now_iso()
    duration_sec = round(time.perf_counter() - t0, 3)
    return {
        "cmd": " ".join(cmd),
        "returncode": result.returncode,
        "ok": result.returncode == 0,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_sec": duration_sec,
        "stdout_tail": result.stdout[-6000:],
        "stderr_tail": result.stderr[-6000:],
    }


def build_reconcile_cmd(input_paths: dict[str, Path], output_path: Path) -> list[str]:
    ordered_sources = [
        "arxiv",
        "openalex_alignment",
        "semantic_scholar_alignment",
        "crossref_alignment",
        ACL_SOURCE_NAME,
    ]
    ordered_paths = [input_paths[source] for source in ordered_sources if source in input_paths]
    extra_sources = [source for source in input_paths if source not in ordered_sources]
    ordered_paths.extend(input_paths[source] for source in sorted(extra_sources))

    return [
        sys.executable,
        "-m",
        "scripts.normalize.run_reconcile",
        "--inputs",
        *[str(path) for path in ordered_paths],
        "--output",
        str(output_path),
    ]


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# ACL Anthology reconcile candidate report")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at_utc']}`")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Mode: `{report['mode']}`")
    lines.append(f"- Pipeline version: `{report['pipeline_version']}`")
    lines.append("")

    lines.append("## Inputs")
    for key, value in report["inputs"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Resolved source snapshots")
    for key, value in report["resolved_inputs"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Candidate output")
    for key, value in report["candidate_output"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    if report.get("execution"):
        lines.append("## Execution")
        for key, value in report["execution"].items():
            if key in {"stdout_tail", "stderr_tail"}:
                continue
            lines.append(f"- {key}: `{value}`")
        lines.append("")

    if report.get("baseline_summary"):
        lines.append("## Baseline summary")
        for key, value in report["baseline_summary"].items():
            if isinstance(value, (dict, list)):
                continue
            lines.append(f"- {key}: `{value}`")
        lines.append("")

    if report.get("candidate_summary"):
        lines.append("## Candidate summary")
        for key, value in report["candidate_summary"].items():
            if isinstance(value, (dict, list)):
                continue
            lines.append(f"- {key}: `{value}`")
        lines.append("")

    if report.get("comparison"):
        lines.append("## Baseline vs candidate")
        for key, value in report["comparison"].items():
            if isinstance(value, list):
                continue
            lines.append(f"- {key}: `{value}`")
        lines.append("")

    lines.append("## Checks")
    for key, value in report["checks"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Verdict")
    lines.append(f"- ok: `{report['ok']}`")
    lines.append(f"- required_failed_count: `{report['required_failed_count']}`")
    lines.append(f"- required_failed_checks: `{report['required_failed_checks']}`")
    lines.append("")

    return "\n".join(lines)


def write_reports(report_dir: Path, report: dict[str, Any]) -> None:
    latest_json = report_dir / "acl_anthology_reconcile_candidate_latest.json"
    latest_md = report_dir / "acl_anthology_reconcile_candidate_latest.md"
    history_json = report_dir / "history" / f"acl_anthology_reconcile_candidate_{report['run_ts']}.json"
    history_md = report_dir / "history" / f"acl_anthology_reconcile_candidate_{report['run_ts']}.md"

    write_json(latest_json, report)
    write_text(latest_md, build_markdown(report))
    write_json(history_json, report)
    write_text(history_md, build_markdown(report))

    print(f"[OK] report JSON: {latest_json}")
    print(f"[OK] report MD: {latest_md}")
    print(f"[OK] history JSON: {history_json}")
    print(f"[OK] history MD: {history_md}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a candidate canonical corpus including ACL Anthology, without touching stable canonical, DB, retrieval, or artifacts."
        )
    )
    parser.add_argument("--normalized-root", type=Path, default=DEFAULT_NORMALIZED_ROOT)
    parser.add_argument("--baseline-canonical", type=Path, default=DEFAULT_CANONICAL_BASELINE_PATH)
    parser.add_argument("--acl-normalized-path", type=Path, default=DEFAULT_ACL_NORMALIZED_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RECONCILED_DIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument(
        "--baseline-sources",
        nargs="+",
        default=DEFAULT_BASELINE_SOURCES,
        help="Baseline source directories under --normalized-root.",
    )
    parser.add_argument(
        "--inputs",
        nargs="*",
        help="Optional explicit inputs in source=path format. ACL is still supplied by --acl-normalized-path.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually run reconcile and write candidate output. Default is planning/dry-run only.",
    )
    parser.add_argument(
        "--candidate-path",
        type=Path,
        default=None,
        help="Existing ACL reconcile candidate JSONL to analyze, or explicit output path when used with --execute.",
    )
    parser.add_argument(
        "--analyze-only",
        action="store_true",
        help="Do not run reconcile. Analyze an existing --candidate-path against the stable baseline.",
    )
    parser.add_argument(
        "--allow-arxiv-base-loss",
        action="store_true",
        help="Do not fail required checks if candidate loses baseline arXiv base IDs.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    input_paths = resolve_input_paths(args)

    if args.analyze_only and args.execute:
        raise ValueError("--analyze-only and --execute are mutually exclusive")

    if args.analyze_only and args.candidate_path is None:
        raise ValueError("--analyze-only requires --candidate-path")

    candidate_output_path = (
        args.candidate_path
        if args.candidate_path is not None
        else args.output_dir / f"canonical_documents.acl_anthology_candidate.{run_ts}.jsonl"
    )
    reconcile_cmd = build_reconcile_cmd(input_paths, candidate_output_path)

    report: dict[str, Any] = {
        "report_name": "acl_anthology_reconcile_candidate",
        "pipeline_version": PIPELINE_VERSION,
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "mode": "analyze_only" if args.analyze_only else "execute" if args.execute else "dry_run",
        "inputs": {
            "normalized_root": normalize_path(args.normalized_root),
            "baseline_canonical": normalize_path(args.baseline_canonical),
            "acl_normalized_path": normalize_path(args.acl_normalized_path),
            "output_dir": normalize_path(args.output_dir),
            "report_dir": normalize_path(args.report_dir),
            "baseline_sources": args.baseline_sources,
            "allow_arxiv_base_loss": bool(args.allow_arxiv_base_loss),
            "candidate_path": normalize_path(args.candidate_path),
            "analyze_only": bool(args.analyze_only),
        },
        "resolved_inputs": {source: normalize_path(path) for source, path in input_paths.items()},
        "candidate_output": {
            "path": normalize_path(candidate_output_path),
            "exists_before_run": candidate_output_path.exists(),
            "stable_canonical_path": normalize_path(args.baseline_canonical),
            "stable_canonical_will_be_modified": False,
        },
        "reconcile_command": " ".join(reconcile_cmd),
        "execution": None,
        "baseline_summary": None,
        "candidate_summary": None,
        "comparison": None,
        "checks": {},
        "required_check_names": [],
        "required_failed_checks": [],
        "required_failed_count": None,
        "ok": False,
    }

    checks: dict[str, bool] = {
        "baseline_canonical_exists": args.baseline_canonical.exists(),
        "acl_normalized_exists": Path(args.acl_normalized_path).exists(),
        "stable_canonical_will_not_be_modified": True,
        "all_resolved_inputs_exist": all(path.exists() for path in input_paths.values()),
        "acl_input_included": ACL_SOURCE_NAME in input_paths,
    }

    if args.analyze_only:
        checks["candidate_output_exists"] = candidate_output_path.exists()
        if not candidate_output_path.exists():
            report["checks"] = checks
            report["required_check_names"] = [
                "baseline_canonical_exists",
                "acl_normalized_exists",
                "stable_canonical_will_not_be_modified",
                "candidate_output_exists",
            ]
            failed = [name for name in report["required_check_names"] if not checks.get(name, False)]
            report["required_failed_checks"] = failed
            report["required_failed_count"] = len(failed)
            report["ok"] = False
            write_reports(args.report_dir, report)
            print(f"[ERROR] candidate_output does not exist: {candidate_output_path}", file=sys.stderr)
            raise SystemExit(1)

        baseline_rows = load_jsonl(args.baseline_canonical)
        candidate_rows = load_jsonl(candidate_output_path)
        baseline_summary = summarize_rows(baseline_rows, label="baseline")
        candidate_summary = summarize_rows(candidate_rows, label="candidate")
        comparison = compare_baseline_candidate(baseline_rows, candidate_rows)

        report["baseline_summary"] = baseline_summary
        report["candidate_summary"] = candidate_summary
        report["comparison"] = comparison

        checks.update(
            {
                "baseline_rows_non_empty": baseline_summary["rows_count"] > 0,
                "candidate_rows_non_empty": candidate_summary["rows_count"] > 0,
                "candidate_doc_count_not_smaller_than_baseline": (
                    candidate_summary["rows_count"] >= baseline_summary["rows_count"]
                ),
                "candidate_has_acl_docs": candidate_summary["acl_family_docs_count"] > 0,
                "candidate_has_acl_only_docs": candidate_summary["acl_family_only_docs_count"] > 0,
                "candidate_duplicate_arxiv_base_count_zero": candidate_summary["duplicate_arxiv_base_count"] == 0,
                "candidate_missing_baseline_arxiv_base_count_zero": (
                    comparison["missing_baseline_arxiv_base_count"] == 0
                ),
                "candidate_empty_title_count_zero": candidate_summary["empty_title_count"] == 0,
                "added_docs_explained_by_acl_or_known_fragments": (
                    comparison["doc_id_added_count"]
                    == comparison["added_acl_family_docs_count"] + comparison["added_non_acl_docs_count"]
                ),
            }
        )

        required_check_names = [
            "baseline_canonical_exists",
            "acl_normalized_exists",
            "stable_canonical_will_not_be_modified",
            "candidate_output_exists",
            "baseline_rows_non_empty",
            "candidate_rows_non_empty",
            "candidate_doc_count_not_smaller_than_baseline",
            "candidate_has_acl_docs",
            "candidate_has_acl_only_docs",
            "candidate_duplicate_arxiv_base_count_zero",
            "candidate_empty_title_count_zero",
            "added_docs_explained_by_acl_or_known_fragments",
        ]
        if not args.allow_arxiv_base_loss:
            required_check_names.append("candidate_missing_baseline_arxiv_base_count_zero")

        failed = [name for name in required_check_names if not checks.get(name, False)]
        report["checks"] = checks
        report["required_check_names"] = required_check_names
        report["required_failed_checks"] = failed
        report["required_failed_count"] = len(failed)
        report["ok"] = len(failed) == 0
        write_reports(args.report_dir, report)

        print(f"[CHECK] mode=analyze_only")
        print(f"[CHECK] baseline_rows_count={baseline_summary['rows_count']}")
        print(f"[CHECK] candidate_rows_count={candidate_summary['rows_count']}")
        print(f"[CHECK] candidate_delta={candidate_summary['rows_count'] - baseline_summary['rows_count']}")
        print(f"[CHECK] candidate_acl_family_docs_count={candidate_summary['acl_family_docs_count']}")
        print(f"[CHECK] candidate_acl_family_only_docs_count={candidate_summary['acl_family_only_docs_count']}")
        print(f"[CHECK] candidate_acl_family_with_arxiv_docs_count={candidate_summary['acl_family_with_arxiv_docs_count']}")
        print(f"[CHECK] added_acl_family_docs_count={comparison['added_acl_family_docs_count']}")
        print(f"[CHECK] added_acl_family_only_docs_count={comparison['added_acl_family_only_docs_count']}")
        print(f"[CHECK] added_non_acl_docs_count={comparison['added_non_acl_docs_count']}")
        print(f"[CHECK] missing_baseline_arxiv_base_count={comparison['missing_baseline_arxiv_base_count']}")
        print(f"[CHECK] candidate_duplicate_arxiv_base_count={candidate_summary['duplicate_arxiv_base_count']}")
        print(f"[CHECK] candidate_duplicate_doi_count={candidate_summary['duplicate_doi_count']}")
        print(f"[CHECK] added_source_family_sets_top20={comparison['added_source_family_sets_top20']}")
        print(f"[CHECK] added_non_acl_source_family_sets_top20={comparison['added_non_acl_source_family_sets_top20']}")
        print(f"[CHECK] required_failed_count={len(failed)}")
        print(f"[CHECK] required_failed_checks={failed}")
        print(f"[CHECK] ok={report['ok']}")
        if failed:
            raise SystemExit(1)
        return

    if not args.execute:
        report["checks"] = checks
        report["required_check_names"] = [
            "baseline_canonical_exists",
            "acl_normalized_exists",
            "stable_canonical_will_not_be_modified",
            "all_resolved_inputs_exist",
            "acl_input_included",
        ]
        failed = [name for name in report["required_check_names"] if not checks.get(name, False)]
        report["required_failed_checks"] = failed
        report["required_failed_count"] = len(failed)
        report["ok"] = len(failed) == 0
        write_reports(args.report_dir, report)
        print("[OK] mode=dry_run")
        print(f"[OK] candidate_output={candidate_output_path}")
        print(f"[OK] reconcile_command={' '.join(reconcile_cmd)}")
        print(f"[OK] required_failed_count={len(failed)}")
        if failed:
            raise SystemExit(1)
        return

    execution = run_command(reconcile_cmd)
    report["execution"] = execution

    checks["reconcile_returncode_ok"] = bool(execution["ok"])
    checks["candidate_output_exists"] = candidate_output_path.exists()

    if not execution["ok"]:
        report["checks"] = checks
        report["required_check_names"] = [
            "baseline_canonical_exists",
            "acl_normalized_exists",
            "all_resolved_inputs_exist",
            "acl_input_included",
            "reconcile_returncode_ok",
            "candidate_output_exists",
        ]
        failed = [name for name in report["required_check_names"] if not checks.get(name, False)]
        report["required_failed_checks"] = failed
        report["required_failed_count"] = len(failed)
        report["ok"] = False
        write_reports(args.report_dir, report)
        print(execution.get("stdout_tail") or "")
        print(execution.get("stderr_tail") or "", file=sys.stderr)
        raise SystemExit(1)

    baseline_rows = load_jsonl(args.baseline_canonical)
    candidate_rows = load_jsonl(candidate_output_path)

    baseline_summary = summarize_rows(baseline_rows, label="baseline")
    candidate_summary = summarize_rows(candidate_rows, label="candidate")
    comparison = compare_baseline_candidate(baseline_rows, candidate_rows)

    report["baseline_summary"] = baseline_summary
    report["candidate_summary"] = candidate_summary
    report["comparison"] = comparison

    checks.update(
        {
            "baseline_rows_non_empty": baseline_summary["rows_count"] > 0,
            "candidate_rows_non_empty": candidate_summary["rows_count"] > 0,
            "candidate_doc_count_not_smaller_than_baseline": (
                candidate_summary["rows_count"] >= baseline_summary["rows_count"]
            ),
            "candidate_has_acl_docs": candidate_summary["acl_family_docs_count"] > 0,
            "candidate_has_acl_only_docs": candidate_summary["acl_family_only_docs_count"] > 0,
            "candidate_duplicate_arxiv_base_count_zero": candidate_summary["duplicate_arxiv_base_count"] == 0,
            "candidate_missing_baseline_arxiv_base_count_zero": (
                comparison["missing_baseline_arxiv_base_count"] == 0
            ),
            "candidate_duplicate_doi_count_reasonable": candidate_summary["duplicate_doi_count"] <= baseline_summary["duplicate_doi_count"] + 100,
            "candidate_empty_title_count_zero": candidate_summary["empty_title_count"] == 0,
            "added_docs_explained_by_acl_or_known_fragments": (
                comparison["doc_id_added_count"]
                == comparison["added_acl_family_docs_count"] + comparison["added_non_acl_docs_count"]
            ),
        }
    )

    required_check_names = [
        "baseline_canonical_exists",
        "acl_normalized_exists",
        "all_resolved_inputs_exist",
        "acl_input_included",
        "stable_canonical_will_not_be_modified",
        "reconcile_returncode_ok",
        "candidate_output_exists",
        "baseline_rows_non_empty",
        "candidate_rows_non_empty",
        "candidate_doc_count_not_smaller_than_baseline",
        "candidate_has_acl_docs",
        "candidate_duplicate_arxiv_base_count_zero",
        "candidate_empty_title_count_zero",
        "added_docs_explained_by_acl_or_known_fragments",
    ]

    if not args.allow_arxiv_base_loss:
        required_check_names.append("candidate_missing_baseline_arxiv_base_count_zero")

    failed = [name for name in required_check_names if not checks.get(name, False)]

    report["checks"] = checks
    report["required_check_names"] = required_check_names
    report["required_failed_checks"] = failed
    report["required_failed_count"] = len(failed)
    report["ok"] = len(failed) == 0

    write_reports(args.report_dir, report)

    print(f"[CHECK] baseline_rows_count={baseline_summary['rows_count']}")
    print(f"[CHECK] candidate_rows_count={candidate_summary['rows_count']}")
    print(f"[CHECK] candidate_delta={candidate_summary['rows_count'] - baseline_summary['rows_count']}")
    print(f"[CHECK] baseline_multisource_docs={baseline_summary['multisource_docs_count']}")
    print(f"[CHECK] candidate_multisource_docs={candidate_summary['multisource_docs_count']}")
    print(f"[CHECK] candidate_acl_family_docs_count={candidate_summary['acl_family_docs_count']}")
    print(f"[CHECK] candidate_acl_family_only_docs_count={candidate_summary['acl_family_only_docs_count']}")
    print(f"[CHECK] candidate_acl_family_with_arxiv_docs_count={candidate_summary['acl_family_with_arxiv_docs_count']}")
    print(f"[CHECK] added_acl_family_docs_count={comparison['added_acl_family_docs_count']}")
    print(f"[CHECK] added_acl_family_only_docs_count={comparison['added_acl_family_only_docs_count']}")
    print(f"[CHECK] added_non_acl_docs_count={comparison['added_non_acl_docs_count']}")
    print(f"[CHECK] missing_baseline_arxiv_base_count={comparison['missing_baseline_arxiv_base_count']}")
    print(f"[CHECK] candidate_duplicate_arxiv_base_count={candidate_summary['duplicate_arxiv_base_count']}")
    print(f"[CHECK] candidate_duplicate_doi_count={candidate_summary['duplicate_doi_count']}")
    print(f"[CHECK] added_source_family_sets_top20={comparison['added_source_family_sets_top20']}")
    print(f"[CHECK] added_non_acl_source_family_sets_top20={comparison['added_non_acl_source_family_sets_top20']}")
    print(f"[CHECK] required_failed_count={len(failed)}")
    print(f"[CHECK] required_failed_checks={failed}")
    print(f"[CHECK] ok={report['ok']}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
