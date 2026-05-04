from __future__ import annotations

import argparse
import html
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_ACL_PATH = Path("data/normalized/acl_anthology/documents_latest.jsonl")
DEFAULT_CANONICAL_PATH = Path("data/analytics/reconciled/canonical_documents.jsonl")
DEFAULT_REPORT_DIR = Path("artifacts/reports/source_audit")

DOI_RE = re.compile(r"(10\.\d{4,9}/\S+)", re.IGNORECASE)


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"JSONL row must be object at {path}:{line_no}")
            rows.append(value)
    return rows


def first_non_empty(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def normalize_doi(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    text = html.unescape(text)
    text = text.replace("\\u200b", "")
    text = text.replace("https://doi.org/", "")
    text = text.replace("http://doi.org/", "")
    text = text.replace("https://dx.doi.org/", "")
    text = text.replace("http://dx.doi.org/", "")
    text = re.sub(r"^doi\s*:\s*", "", text, flags=re.IGNORECASE)
    text = text.strip().lower()

    # Keep the first DOI if dirty metadata contains repeated DOI tokens.
    match = DOI_RE.search(text)
    if not match:
        return None

    doi = match.group(1).strip().lower()
    doi = doi.rstrip(".,;:)])}>")
    doi = doi.rstrip("/")

    if not doi.startswith("10.") or "/" not in doi:
        return None

    return doi


def normalize_title(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value)
    text = html.unescape(text)
    text = unicodedata.normalize("NFKC", text)
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text or None


def parse_year(value: Any) -> int | None:
    if value is None:
        return None
    try:
        year = int(str(value)[:4])
    except Exception:
        return None
    if 1800 <= year <= 2100:
        return year
    return None


def get_external_ids(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("external_ids")
    return value if isinstance(value, dict) else {}


def get_row_doi(row: dict[str, Any]) -> str | None:
    external_ids = get_external_ids(row)
    return normalize_doi(first_non_empty(row.get("doi"), external_ids.get("doi")))


def get_row_title_year_key(row: dict[str, Any]) -> tuple[str, int] | None:
    title = normalize_title(row.get("title"))
    year = parse_year(first_non_empty(row.get("year"), row.get("publication_year")))
    if title is None or year is None:
        return None
    return title, year


def get_canonical_id(row: dict[str, Any]) -> str:
    return str(
        first_non_empty(
            row.get("canonical_id"),
            row.get("doc_id"),
            row.get("id"),
            stable_display_key(row),
        )
    )


def stable_display_key(row: dict[str, Any]) -> str:
    return "|".join(
        str(first_non_empty(row.get(k), ""))
        for k in ("source", "source_id", "title", "year")
    )


def get_acl_id(row: dict[str, Any]) -> str:
    external_ids = get_external_ids(row)
    return str(
        first_non_empty(
            external_ids.get("acl_anthology_id"),
            row.get("source_id"),
            row.get("source_record_id"),
            row.get("doc_id"),
            stable_display_key(row),
        )
    )


def get_source_names(row: dict[str, Any]) -> list[str]:
    source_ids = row.get("source_ids")
    if isinstance(source_ids, dict) and source_ids:
        return sorted(str(k) for k in source_ids.keys())

    sources = row.get("sources")
    if isinstance(sources, list) and sources:
        return sorted(str(x) for x in sources if x)

    source = row.get("source")
    if source:
        return [str(source)]

    return []


def compact_doc(row: dict[str, Any], *, id_key: str = "doc_id") -> dict[str, Any]:
    external_ids = get_external_ids(row)
    return {
        "doc_id": row.get(id_key) or row.get("doc_id"),
        "canonical_id": row.get("canonical_id"),
        "source_id": row.get("source_id"),
        "source_record_id": row.get("source_record_id"),
        "acl_anthology_id": external_ids.get("acl_anthology_id"),
        "title": row.get("title"),
        "year": row.get("year"),
        "doi": get_row_doi(row),
        "arxiv_id": first_non_empty(row.get("arxiv_id"), external_ids.get("arxiv"), external_ids.get("arxiv_id")),
        "source_names": get_source_names(row),
        "canonical_url": row.get("canonical_url"),
        "source_record_url": row.get("source_record_url"),
    }


def count_duplicates(values: Iterable[Any]) -> tuple[int, list[Any]]:
    values = [v for v in values if v is not None]
    counts = Counter(values)
    duplicates = [k for k, v in counts.items() if v > 1]
    return len(duplicates), duplicates[:30]


def build_index_by_key(
    rows: list[dict[str, Any]],
    key_fn,
) -> dict[Any, list[dict[str, Any]]]:
    index: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = key_fn(row)
        if key is not None:
            index[key].append(row)
    return dict(index)


def unique_ids(rows: Iterable[dict[str, Any]]) -> set[str]:
    return {get_canonical_id(row) for row in rows}


def build_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    checks = report["checks"]
    verdict = report["verdict"]

    lines: list[str] = []
    lines.append("# ACL Anthology canonical impact audit")
    lines.append("")
    lines.append(f"- Generated at: `{report['generated_at_utc']}`")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Strict: `{report['strict']}`")
    lines.append(f"- Candidate only: `{report['candidate_only']}`")
    lines.append("")

    lines.append("## Inputs")
    for key, value in report["inputs"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Summary")
    ordered_keys = [
        "acl_rows_count",
        "canonical_rows_count",
        "acl_doi_count",
        "canonical_doi_count",
        "acl_title_year_count",
        "canonical_title_year_count",
        "matched_by_doi_count",
        "matched_by_title_year_count",
        "matched_by_both_count",
        "matched_by_doi_only_count",
        "matched_by_title_year_only_count",
        "matched_by_any_count",
        "acl_only_count",
        "doi_matched_to_arxiv_canonical_count",
        "title_year_matched_to_arxiv_canonical_count",
        "doi_title_disagreement_count",
        "doi_matches_multiple_canonical_count",
        "title_year_matches_multiple_canonical_count",
    ]
    for key in ordered_keys:
        lines.append(f"- {key}: `{summary.get(key)}`")
    lines.append("")

    lines.append("## Source set distribution for matched canonical docs")
    for key, value in summary.get("matched_canonical_source_set_distribution", {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Checks")
    for key, value in checks.items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    lines.append("## Verdict")
    for key, value in verdict.items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")

    if report.get("samples"):
        lines.append("## Samples")
        for name, sample in report["samples"].items():
            lines.append(f"### {name}")
            lines.append("```json")
            lines.append(json.dumps(sample[:10], ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("")

    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only impact audit for ACL Anthology candidate snapshot against "
            "the current canonical corpus. This script does not modify canonical, "
            "Postgres, retrieval, or artifact layers."
        )
    )
    parser.add_argument("--acl-path", type=Path, default=DEFAULT_ACL_PATH)
    parser.add_argument("--canonical-path", type=Path, default=DEFAULT_CANONICAL_PATH)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--sample-limit", type=int, default=30)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_ts = utc_now_ts()

    load_errors: list[str] = []
    acl_rows: list[dict[str, Any]] = []
    canonical_rows: list[dict[str, Any]] = []

    acl_exists = args.acl_path.exists()
    canonical_exists = args.canonical_path.exists()

    if acl_exists:
        try:
            acl_rows = load_jsonl(args.acl_path)
        except Exception as exc:
            load_errors.append(f"acl_load_error: {exc}")

    if canonical_exists:
        try:
            canonical_rows = load_jsonl(args.canonical_path)
        except Exception as exc:
            load_errors.append(f"canonical_load_error: {exc}")

    acl_by_doi = build_index_by_key(acl_rows, get_row_doi)
    canonical_by_doi = build_index_by_key(canonical_rows, get_row_doi)
    acl_by_title_year = build_index_by_key(acl_rows, get_row_title_year_key)
    canonical_by_title_year = build_index_by_key(canonical_rows, get_row_title_year_key)

    acl_doc_ids = [row.get("doc_id") for row in acl_rows]
    acl_source_ids = [row.get("source_id") for row in acl_rows]
    acl_source_record_ids = [row.get("source_record_id") for row in acl_rows]
    acl_dois = [get_row_doi(row) for row in acl_rows]
    acl_title_year_keys = [get_row_title_year_key(row) for row in acl_rows]

    duplicate_acl_doc_id_count, duplicate_acl_doc_ids = count_duplicates(acl_doc_ids)
    duplicate_acl_source_id_count, duplicate_acl_source_ids = count_duplicates(acl_source_ids)
    duplicate_acl_source_record_id_count, duplicate_acl_source_record_ids = count_duplicates(acl_source_record_ids)
    duplicate_acl_doi_count, duplicate_acl_dois = count_duplicates(acl_dois)
    duplicate_acl_title_year_count, duplicate_acl_title_year = count_duplicates(acl_title_year_keys)

    canonical_duplicate_doi_keys = [doi for doi, rows in canonical_by_doi.items() if len(rows) > 1]
    canonical_duplicate_title_year_keys = [key for key, rows in canonical_by_title_year.items() if len(rows) > 1]

    matched_by_doi: list[dict[str, Any]] = []
    matched_by_title_year: list[dict[str, Any]] = []
    matched_by_both: list[dict[str, Any]] = []
    matched_by_doi_only: list[dict[str, Any]] = []
    matched_by_title_year_only: list[dict[str, Any]] = []
    acl_only: list[dict[str, Any]] = []
    doi_title_disagreements: list[dict[str, Any]] = []
    doi_matches_multiple_canonical: list[dict[str, Any]] = []
    title_year_matches_multiple_canonical: list[dict[str, Any]] = []

    matched_canonical_ids: set[str] = set()
    doi_matched_arxiv_canonical_ids: set[str] = set()
    title_year_matched_arxiv_canonical_ids: set[str] = set()

    for acl_row in acl_rows:
        doi = get_row_doi(acl_row)
        title_year = get_row_title_year_key(acl_row)

        doi_matches = canonical_by_doi.get(doi, []) if doi else []
        title_year_matches = canonical_by_title_year.get(title_year, []) if title_year else []

        doi_ids = unique_ids(doi_matches)
        title_year_ids = unique_ids(title_year_matches)

        if doi_matches:
            matched_by_doi.append(acl_row)
            matched_canonical_ids.update(doi_ids)
            for canonical_row in doi_matches:
                if first_non_empty(canonical_row.get("arxiv_id"), get_external_ids(canonical_row).get("arxiv"), get_external_ids(canonical_row).get("arxiv_id")):
                    doi_matched_arxiv_canonical_ids.add(get_canonical_id(canonical_row))

        if title_year_matches:
            matched_by_title_year.append(acl_row)
            matched_canonical_ids.update(title_year_ids)
            for canonical_row in title_year_matches:
                if first_non_empty(canonical_row.get("arxiv_id"), get_external_ids(canonical_row).get("arxiv"), get_external_ids(canonical_row).get("arxiv_id")):
                    title_year_matched_arxiv_canonical_ids.add(get_canonical_id(canonical_row))

        if len(doi_matches) > 1:
            doi_matches_multiple_canonical.append(
                {
                    "acl": compact_doc(acl_row),
                    "matches": [compact_doc(row) for row in doi_matches[:10]],
                }
            )

        if len(title_year_matches) > 1:
            title_year_matches_multiple_canonical.append(
                {
                    "acl": compact_doc(acl_row),
                    "matches": [compact_doc(row) for row in title_year_matches[:10]],
                }
            )

        if doi_matches and title_year_matches:
            matched_by_both.append(acl_row)
            if doi_ids and title_year_ids and doi_ids.isdisjoint(title_year_ids):
                doi_title_disagreements.append(
                    {
                        "acl": compact_doc(acl_row),
                        "doi_matches": [compact_doc(row) for row in doi_matches[:10]],
                        "title_year_matches": [compact_doc(row) for row in title_year_matches[:10]],
                    }
                )
        elif doi_matches:
            matched_by_doi_only.append(acl_row)
        elif title_year_matches:
            matched_by_title_year_only.append(acl_row)
        else:
            acl_only.append(acl_row)

    matched_by_any_count = len({get_acl_id(row) for row in matched_by_doi + matched_by_title_year})

    matched_canonical_rows = [
        row for row in canonical_rows if get_canonical_id(row) in matched_canonical_ids
    ]
    matched_canonical_source_sets = Counter(
        "+".join(get_source_names(row)) or "unknown"
        for row in matched_canonical_rows
    )

    bad_acl_doi_rows = [row for row in acl_rows if row.get("doi") and get_row_doi(row) is None]

    summary = {
        "acl_rows_count": len(acl_rows),
        "canonical_rows_count": len(canonical_rows),
        "acl_doi_count": len(acl_by_doi),
        "canonical_doi_count": len(canonical_by_doi),
        "acl_title_year_count": len(acl_by_title_year),
        "canonical_title_year_count": len(canonical_by_title_year),
        "acl_bad_doi_count": len(bad_acl_doi_rows),
        "acl_duplicate_doc_id_count": duplicate_acl_doc_id_count,
        "acl_duplicate_source_id_count": duplicate_acl_source_id_count,
        "acl_duplicate_source_record_id_count": duplicate_acl_source_record_id_count,
        "acl_duplicate_doi_count": duplicate_acl_doi_count,
        "acl_duplicate_title_year_count": duplicate_acl_title_year_count,
        "canonical_duplicate_doi_count": len(canonical_duplicate_doi_keys),
        "canonical_duplicate_title_year_count": len(canonical_duplicate_title_year_keys),
        "matched_by_doi_count": len(matched_by_doi),
        "matched_by_title_year_count": len(matched_by_title_year),
        "matched_by_both_count": len(matched_by_both),
        "matched_by_doi_only_count": len(matched_by_doi_only),
        "matched_by_title_year_only_count": len(matched_by_title_year_only),
        "matched_by_any_count": matched_by_any_count,
        "acl_only_count": len(acl_only),
        "acl_only_with_doi_count": sum(1 for row in acl_only if get_row_doi(row)),
        "acl_only_without_doi_count": sum(1 for row in acl_only if not get_row_doi(row)),
        "matched_canonical_unique_count": len(matched_canonical_ids),
        "doi_matched_to_arxiv_canonical_count": len(doi_matched_arxiv_canonical_ids),
        "title_year_matched_to_arxiv_canonical_count": len(title_year_matched_arxiv_canonical_ids),
        "doi_title_disagreement_count": len(doi_title_disagreements),
        "doi_matches_multiple_canonical_count": len(doi_matches_multiple_canonical),
        "title_year_matches_multiple_canonical_count": len(title_year_matches_multiple_canonical),
        "matched_canonical_source_set_distribution": dict(sorted(matched_canonical_source_sets.items())),
    }

    checks = {
        "acl_path_exists": acl_exists,
        "canonical_path_exists": canonical_exists,
        "no_load_errors": len(load_errors) == 0,
        "acl_rows_non_empty": len(acl_rows) > 0,
        "canonical_rows_non_empty": len(canonical_rows) > 0,
        "acl_doc_ids_unique": duplicate_acl_doc_id_count == 0,
        "acl_source_ids_unique": duplicate_acl_source_id_count == 0,
        "acl_source_record_ids_unique": duplicate_acl_source_record_id_count == 0,
        "acl_doi_values_valid": len(bad_acl_doi_rows) == 0,
        "impact_audit_has_overlap_signal": (
            len(matched_by_doi) > 0 or len(matched_by_title_year) > 0 or len(acl_only) > 0
        ),
        # Diagnostic-only safety signals. These are useful to review before reconcile,
        # but source-only docs and duplicate canonical DOI cases may be legitimate.
        "no_acl_duplicate_dois": duplicate_acl_doi_count == 0,
        "no_acl_duplicate_title_year": duplicate_acl_title_year_count == 0,
        "no_doi_title_disagreements": len(doi_title_disagreements) == 0,
        "no_doi_matches_multiple_canonical": len(doi_matches_multiple_canonical) == 0,
        "no_title_year_matches_multiple_canonical": len(title_year_matches_multiple_canonical) == 0,
    }

    required_check_names = [
        "acl_path_exists",
        "canonical_path_exists",
        "no_load_errors",
        "acl_rows_non_empty",
        "canonical_rows_non_empty",
        "acl_doc_ids_unique",
        "acl_source_ids_unique",
        "acl_source_record_ids_unique",
        "acl_doi_values_valid",
        "impact_audit_has_overlap_signal",
    ]

    if args.strict:
        required_check_names.extend(
            [
                "no_acl_duplicate_dois",
                "no_acl_duplicate_title_year",
            ]
        )

    required_failed = [name for name in required_check_names if not checks.get(name, False)]

    verdict = {
        "strict": bool(args.strict),
        "required_check_count": len(required_check_names),
        "required_failed_count": len(required_failed),
        "required_failed_checks": required_failed,
        "candidate_ready_for_reconcile_smoke": (
            len(required_failed) == 0
            and len(doi_title_disagreements) == 0
            and len(doi_matches_multiple_canonical) == 0
        ),
        "ok": len(required_failed) == 0,
    }

    sample_limit = max(0, int(args.sample_limit))
    samples = {
        "acl_only_sample": [compact_doc(row) for row in acl_only[:sample_limit]],
        "matched_by_doi_sample": [compact_doc(row) for row in matched_by_doi[:sample_limit]],
        "matched_by_title_year_only_sample": [compact_doc(row) for row in matched_by_title_year_only[:sample_limit]],
        "doi_title_disagreement_sample": doi_title_disagreements[:sample_limit],
        "doi_matches_multiple_canonical_sample": doi_matches_multiple_canonical[:sample_limit],
        "title_year_matches_multiple_canonical_sample": title_year_matches_multiple_canonical[:sample_limit],
        "duplicate_acl_doc_ids_sample": duplicate_acl_doc_ids,
        "duplicate_acl_source_ids_sample": duplicate_acl_source_ids,
        "duplicate_acl_source_record_ids_sample": duplicate_acl_source_record_ids,
        "duplicate_acl_dois_sample": duplicate_acl_dois,
        "duplicate_acl_title_year_sample": [str(x) for x in duplicate_acl_title_year[:sample_limit]],
        "canonical_duplicate_dois_sample": canonical_duplicate_doi_keys[:sample_limit],
        "canonical_duplicate_title_year_sample": [str(x) for x in canonical_duplicate_title_year_keys[:sample_limit]],
    }

    report = {
        "report_name": "acl_anthology_canonical_impact",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "candidate_only": True,
        "strict": bool(args.strict),
        "inputs": {
            "acl_path": normalize_path(args.acl_path),
            "canonical_path": normalize_path(args.canonical_path),
        },
        "load_errors": load_errors,
        "summary": summary,
        "checks": checks,
        "required_check_names": required_check_names,
        "required_failed_checks": required_failed,
        "required_failed_count": len(required_failed),
        "verdict": verdict,
        "samples": samples,
        "ok": verdict["ok"],
    }

    latest_json = args.report_dir / "acl_anthology_canonical_impact_latest.json"
    latest_md = args.report_dir / "acl_anthology_canonical_impact_latest.md"
    history_json = args.report_dir / "history" / f"acl_anthology_canonical_impact_{run_ts}.json"
    history_md = args.report_dir / "history" / f"acl_anthology_canonical_impact_{run_ts}.md"

    write_json(latest_json, report)
    write_text(latest_md, build_markdown(report))
    write_json(history_json, report)
    write_text(history_md, build_markdown(report))

    print(f"[OK] report JSON: {latest_json}")
    print(f"[OK] report MD: {latest_md}")
    print(f"[OK] history JSON: {history_json}")
    print(f"[OK] history MD: {history_md}")
    print(f"[CHECK] acl_rows_count={summary['acl_rows_count']}")
    print(f"[CHECK] canonical_rows_count={summary['canonical_rows_count']}")
    print(f"[CHECK] matched_by_doi_count={summary['matched_by_doi_count']}")
    print(f"[CHECK] matched_by_title_year_count={summary['matched_by_title_year_count']}")
    print(f"[CHECK] matched_by_any_count={summary['matched_by_any_count']}")
    print(f"[CHECK] acl_only_count={summary['acl_only_count']}")
    print(f"[CHECK] doi_title_disagreement_count={summary['doi_title_disagreement_count']}")
    print(f"[CHECK] doi_matches_multiple_canonical_count={summary['doi_matches_multiple_canonical_count']}")
    print(f"[CHECK] title_year_matches_multiple_canonical_count={summary['title_year_matches_multiple_canonical_count']}")
    print(f"[CHECK] candidate_ready_for_reconcile_smoke={verdict['candidate_ready_for_reconcile_smoke']}")
    print(f"[CHECK] strict={bool(args.strict)}")
    print(f"[CHECK] required_failed_count={len(required_failed)}")
    print(f"[CHECK] required_failed_checks={required_failed}")
    print(f"[CHECK] ok={verdict['ok']}")

    if not verdict["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
