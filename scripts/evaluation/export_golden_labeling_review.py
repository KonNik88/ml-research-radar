from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CANDIDATES_PATH = Path(
    "artifacts/reports/evaluation/golden_labeling_candidates_latest.json"
)
DEFAULT_MANIFEST_PATH = Path("artifacts/retrieval/manifests/latest.json")
DEFAULT_OUTPUT_DIR = Path("artifacts/reports/evaluation")

SCHEMA_VERSION = "golden_labeling_review_v1"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def normalize_path(path_value: str | Path, *, base_dir: Path | None = None) -> Path:
    path = Path(path_value)
    if path.is_absolute() or base_dir is None:
        return path
    return (base_dir / path).resolve()


def candidate_ids_from_report(report: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for query in report.get("queries") or []:
        for candidate in query.get("candidates") or []:
            canonical_id = str(candidate.get("canonical_id") or "").strip()
            if canonical_id:
                ids.add(canonical_id)
    return ids


def load_selected_canonical_rows(
    corpus_path: Path,
    wanted_ids: set[str],
) -> dict[str, dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}

    with corpus_path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSONL in {corpus_path} at line {line_no}: {exc}"
                ) from exc

            canonical_id = str(row.get("canonical_id") or "").strip()
            if canonical_id in wanted_ids:
                selected[canonical_id] = row
                if len(selected) == len(wanted_ids):
                    break

    return selected


def compact_text(value: Any, *, max_chars: int) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    if not text:
        return None
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            result.append(text)
    return result


def source_names(row: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for item in row.get("sources") or []:
        if isinstance(item, dict):
            value = str(item.get("source") or item.get("source_name") or "").strip()
        else:
            value = str(item or "").strip()
        if value and value not in names:
            names.append(value)
    return names


def mode_summary(candidate: dict[str, Any]) -> str:
    parts: list[str] = []
    for mode, payload in (candidate.get("modes") or {}).items():
        rank = payload.get("rank")
        if rank is not None:
            parts.append(f"{mode}:#{rank}")
    return ", ".join(parts)


def build_review_rows(
    candidate_report: dict[str, Any],
    canonical_rows: dict[str, dict[str, Any]],
    *,
    max_candidates_per_query: int,
    abstract_max_chars: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for query in candidate_report.get("queries") or []:
        candidates = list(query.get("candidates") or [])[:max_candidates_per_query]

        for candidate_position, candidate in enumerate(candidates, start=1):
            canonical_id = str(candidate.get("canonical_id") or "").strip()
            canonical = canonical_rows.get(canonical_id) or {}

            rows.append(
                {
                    "query_id": query.get("query_id"),
                    "group": query.get("group"),
                    "query": query.get("query"),
                    "intent": query.get("intent"),
                    "candidate_position": candidate_position,
                    "canonical_id": canonical_id,
                    "title": canonical.get("title") or candidate.get("title"),
                    "year": canonical.get("year") or candidate.get("year"),
                    "best_rank": candidate.get("best_rank"),
                    "modes_count": candidate.get("modes_count"),
                    "modes": mode_summary(candidate),
                    "source_count": canonical.get("source_count")
                    if canonical
                    else candidate.get("source_count"),
                    "unique_source_count": canonical.get("unique_source_count"),
                    "source_names": source_names(canonical),
                    "abstract": compact_text(
                        canonical.get("abstract"),
                        max_chars=abstract_max_chars,
                    ),
                    "authors": string_list(canonical.get("authors")),
                    "primary_category": canonical.get("primary_category"),
                    "categories": string_list(canonical.get("categories")),
                    "concepts": string_list(canonical.get("concepts")),
                    "keywords": string_list(canonical.get("keywords")),
                    "venue": canonical.get("venue"),
                    "journal": canonical.get("journal"),
                    "conference": canonical.get("conference"),
                    "doi": canonical.get("doi"),
                    "arxiv_id": canonical.get("arxiv_id"),
                    "landing_page_url": canonical.get("landing_page_url"),
                    "pdf_url": canonical.get("pdf_url"),
                    "cited_by_count": canonical.get("cited_by_count"),
                    "metadata_completeness_score": canonical.get(
                        "metadata_completeness_score"
                    ),
                    "review_grade": None,
                    "review_note": None,
                    "canonical_found": bool(canonical),
                }
            )

    return rows


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "query_id",
        "group",
        "query",
        "intent",
        "candidate_position",
        "canonical_id",
        "title",
        "year",
        "best_rank",
        "modes_count",
        "modes",
        "source_count",
        "unique_source_count",
        "source_names",
        "abstract",
        "authors",
        "primary_category",
        "categories",
        "concepts",
        "keywords",
        "venue",
        "journal",
        "conference",
        "doi",
        "arxiv_id",
        "landing_page_url",
        "pdf_url",
        "cited_by_count",
        "metadata_completeness_score",
        "review_grade",
        "review_note",
        "canonical_found",
    ]

    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            csv_row = dict(row)
            for key in (
                "source_names",
                "authors",
                "categories",
                "concepts",
                "keywords",
            ):
                csv_row[key] = " | ".join(row.get(key) or [])
            writer.writerow(csv_row)


def md_escape(value: Any) -> str:
    text = str(value or "")
    return text.replace("|", r"\|").replace("\n", " ")


def write_markdown(
    path: Path,
    payload: dict[str, Any],
    rows: list[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("query_id") or "unknown"), []).append(row)

    lines = [
        "# Golden labeling review v1",
        "",
        f"- Generated at: `{payload['generated_at_utc']}`",
        f"- Candidate report: `{payload['inputs']['candidate_report_path']}`",
        f"- Canonical corpus: `{payload['inputs']['corpus_path']}`",
        f"- Queries: **{payload['summary']['query_count']}**",
        f"- Candidate rows: **{payload['summary']['candidate_rows_count']}**",
        f"- Missing canonical rows: **{payload['summary']['missing_canonical_count']}**",
        "",
        "## Review policy",
        "",
        "- `3` — directly and centrally relevant;",
        "- `2` — clearly relevant but narrower, applied, or secondary;",
        "- remove — keyword overlap, wrong task, or insufficient relevance;",
        "- do not label from rank alone; inspect title and abstract;",
        "- use at least 3 defensible positives per enabled query; 5 preferred.",
        "",
    ]

    for query_id, query_rows in grouped.items():
        first = query_rows[0]
        lines.extend(
            [
                f"## `{query_id}`",
                "",
                f"- Group: `{first.get('group')}`",
                f"- Query: `{first.get('query')}`",
                f"- Intent: {first.get('intent') or '-'}",
                "",
            ]
        )

        for row in query_rows:
            lines.extend(
                [
                    f"### {row['candidate_position']}. {row.get('title') or '[missing title]'}",
                    "",
                    f"- Canonical ID: `{row['canonical_id']}`",
                    f"- Year: `{row.get('year')}`",
                    f"- Retrieval: `{row.get('modes') or '-'}`",
                    f"- Sources: `{', '.join(row.get('source_names') or []) or '-'}`",
                    f"- DOI: `{row.get('doi') or '-'}`",
                    f"- arXiv: `{row.get('arxiv_id') or '-'}`",
                    f"- Venue: `{row.get('venue') or row.get('journal') or row.get('conference') or '-'}`",
                    f"- Landing page: {row.get('landing_page_url') or '-'}",
                    f"- PDF: {row.get('pdf_url') or '-'}",
                    "",
                    f"**Abstract:** {row.get('abstract') or '_missing_'}",
                    "",
                    "**Review:** grade = `TODO`; note = `TODO`",
                    "",
                ]
            )

    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Hydrate golden-labeling candidates with canonical metadata for "
            "human relevance review."
        )
    )
    parser.add_argument(
        "--candidates-path",
        default=str(DEFAULT_CANDIDATES_PATH),
    )
    parser.add_argument(
        "--manifest-path",
        default=str(DEFAULT_MANIFEST_PATH),
    )
    parser.add_argument(
        "--corpus-path",
        default=None,
        help="Optional explicit canonical JSONL path. Defaults to manifest corpus_path.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
    )
    parser.add_argument(
        "--max-candidates-per-query",
        type=int,
        default=30,
    )
    parser.add_argument(
        "--abstract-max-chars",
        type=int,
        default=1600,
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail when any candidate canonical_id is missing from the canonical corpus.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    candidates_path = Path(args.candidates_path)
    manifest_path = Path(args.manifest_path)
    output_dir = Path(args.output_dir)

    candidate_report = load_json(candidates_path)
    manifest = load_json(manifest_path)

    if args.corpus_path:
        corpus_path = Path(args.corpus_path)
    else:
        corpus_value = manifest.get("corpus_path")
        if not corpus_value:
            raise ValueError(
                f"Manifest {manifest_path} does not contain corpus_path"
            )
        corpus_path = Path(corpus_value)

    wanted_ids = candidate_ids_from_report(candidate_report)
    canonical_rows = load_selected_canonical_rows(corpus_path, wanted_ids)

    rows = build_review_rows(
        candidate_report,
        canonical_rows,
        max_candidates_per_query=args.max_candidates_per_query,
        abstract_max_chars=args.abstract_max_chars,
    )

    missing_ids = sorted(wanted_ids - set(canonical_rows))
    run_ts = utc_now_ts()

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "inputs": {
            "candidate_report_path": str(candidates_path),
            "manifest_path": str(manifest_path),
            "corpus_path": str(corpus_path),
        },
        "summary": {
            "query_count": len(candidate_report.get("queries") or []),
            "candidate_ids_count": len(wanted_ids),
            "candidate_rows_count": len(rows),
            "canonical_rows_found": len(canonical_rows),
            "missing_canonical_count": len(missing_ids),
            "missing_canonical_ids": missing_ids,
            "max_candidates_per_query": args.max_candidates_per_query,
        },
        "rows": rows,
    }

    latest_json = output_dir / "golden_labeling_review_latest.json"
    latest_md = output_dir / "golden_labeling_review_latest.md"
    latest_csv = output_dir / "golden_labeling_review_latest.csv"

    history_dir = output_dir / "history"
    history_json = history_dir / f"golden_labeling_review_{run_ts}.json"
    history_md = history_dir / f"golden_labeling_review_{run_ts}.md"
    history_csv = history_dir / f"golden_labeling_review_{run_ts}.csv"

    write_json(latest_json, payload)
    write_markdown(latest_md, payload, rows)
    write_csv(latest_csv, rows)

    write_json(history_json, payload)
    write_markdown(history_md, payload, rows)
    write_csv(history_csv, rows)

    print(f"[OK] schema_version={SCHEMA_VERSION}")
    print(f"[OK] query_count={payload['summary']['query_count']}")
    print(f"[OK] candidate_ids_count={payload['summary']['candidate_ids_count']}")
    print(f"[OK] candidate_rows_count={payload['summary']['candidate_rows_count']}")
    print(f"[OK] canonical_rows_found={payload['summary']['canonical_rows_found']}")
    print(f"[OK] missing_canonical_count={payload['summary']['missing_canonical_count']}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] latest CSV: {latest_csv}")

    if args.strict and missing_ids:
        print("[FAIL] Missing canonical IDs:")
        for canonical_id in missing_ids:
            print(f"  - {canonical_id}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
