from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CANONICAL_PATH = Path("data/analytics/reconciled/canonical_documents.jsonl")
DEFAULT_REPORTS_DIR = Path("artifacts/reports/validation")
DEFAULT_UPDATE_DIR = Path("artifacts/reports/update")
DEFAULT_NORMALIZED_DIR = Path("data/normalized")

DEFAULT_MERGE_REPORTS = {
    "openalex_alignment": DEFAULT_UPDATE_DIR / "merge_openalex_alignment_latest.json",
    "semantic_scholar_alignment": DEFAULT_UPDATE_DIR / "merge_semantic_scholar_alignment_latest.json",
    "crossref_alignment": DEFAULT_UPDATE_DIR / "merge_crossref_alignment_latest.json",
}


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"JSONL file not found: {path}")
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def discover_latest_full_snapshot(source_dir: Path) -> Path:
    candidates = sorted(
        p for p in source_dir.glob("documents.*.jsonl")
        if p.name.startswith("documents.") and p.name.endswith(".jsonl")
        and not p.name.endswith(".new.jsonl")
        and not p.name.endswith(".updated.jsonl")
        and not p.name.endswith(".unchanged.jsonl")
    )
    if not candidates:
        raise FileNotFoundError(f"No full snapshot found in {source_dir}")
    return candidates[-1]


def resolve_merge_snapshot(report_path: Path) -> Path:
    payload = load_json(report_path)
    raw = payload.get("output", {}).get("merged_snapshot")
    if not raw:
        raise ValueError(f"Merge report missing output.merged_snapshot: {report_path}")
    path = Path(str(raw))
    if not path.exists():
        raise FileNotFoundError(f"Merged snapshot does not exist: {path}")
    return path


def build_indexes(rows: list[dict[str, Any]]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    by_source_record_id: dict[str, list[dict[str, Any]]] = {}
    by_source_id: dict[str, list[dict[str, Any]]] = {}
    by_doc_id: dict[str, list[dict[str, Any]]] = {}
    by_arxiv_id: dict[str, list[dict[str, Any]]] = {}

    for row in rows:
        source_record_id = row.get("source_record_id")
        source_id = row.get("source_id")
        doc_id = row.get("doc_id")
        arxiv_id = row.get("arxiv_id")

        if source_record_id:
            by_source_record_id.setdefault(str(source_record_id), []).append(row)
        if source_id:
            by_source_id.setdefault(str(source_id), []).append(row)
        if doc_id:
            by_doc_id.setdefault(str(doc_id), []).append(row)
        if arxiv_id:
            by_arxiv_id.setdefault(str(arxiv_id), []).append(row)

        external_ids = row.get("external_ids") or {}
        if isinstance(external_ids, dict):
            for key in ("arxiv", "ArXiv", "arxiv_base"):
                val = external_ids.get(key)
                if val:
                    by_arxiv_id.setdefault(str(val), []).append(row)

    return {
        "by_source_record_id": by_source_record_id,
        "by_source_id": by_source_id,
        "by_doc_id": by_doc_id,
        "by_arxiv_id": by_arxiv_id,
    }


def find_matches(
    indexes: dict[str, dict[str, list[dict[str, Any]]]],
    source_entry: dict[str, Any] | None,
    canonical_row: dict[str, Any],
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []

    if source_entry:
        for field_name, index_name in (
            ("source_record_id", "by_source_record_id"),
            ("source_id", "by_source_id"),
        ):
            val = source_entry.get(field_name)
            if val:
                matches.extend(indexes[index_name].get(str(val), []))

    for doc_id in canonical_row.get("doc_ids") or []:
        matches.extend(indexes["by_doc_id"].get(str(doc_id), []))

    arxiv_id = canonical_row.get("arxiv_id")
    if arxiv_id:
        matches.extend(indexes["by_arxiv_id"].get(str(arxiv_id), []))

    # dedupe by (source, source_record_id, doc_id)
    unique = {}
    for row in matches:
        key = (
            row.get("source"),
            row.get("source_record_id"),
            row.get("doc_id"),
        )
        unique[key] = row

    return list(unique.values())


def summarize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": row.get("source"),
        "doc_id": row.get("doc_id"),
        "source_id": row.get("source_id"),
        "source_record_id": row.get("source_record_id"),
        "arxiv_id": row.get("arxiv_id"),
        "doi": row.get("doi"),
        "title": row.get("title"),
    }


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Debug selected canonical docs")
    lines.append("")
    lines.append(f"- Generated at: {report['generated_at_utc']}")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append("")

    for item in report["documents"]:
        lines.append(f"## canonical_id `{item['canonical_id']}`")
        lines.append(f"- found: `{item['found']}`")
        if not item["found"]:
            lines.append("")
            continue

        c = item["canonical_summary"]
        lines.append(f"- title: `{c['title']}`")
        lines.append(f"- reconciliation_key: `{c['reconciliation_key']}`")
        lines.append(f"- source_count: `{c['source_count']}`")
        lines.append(f"- unique_source_count: `{c['unique_source_count']}`")
        lines.append(f"- doc_ids: `{c['doc_ids']}`")
        lines.append(f"- source_ids_keys: `{c['source_ids_keys']}`")
        lines.append(f"- provenance_sources: `{c['provenance_sources']}`")
        lines.append(f"- arxiv_id: `{c['arxiv_id']}`")
        lines.append(f"- doi: `{c['doi']}`")
        lines.append("")

        lines.append("### Canonical sources entries")
        for s in item["canonical_sources"]:
            lines.append(
                f"- source=`{s.get('source')}` | source_record_id=`{s.get('source_record_id')}` | source_id=`{s.get('source_id')}`"
            )
        lines.append("")

        lines.append("### Candidate normalized matches")
        for src_name, matches in item["matched_normalized_rows"].items():
            lines.append(f"- `{src_name}`: {len(matches)} match(es)")
            for m in matches[:10]:
                lines.append(
                    f"  - source=`{m['source']}` | source_record_id=`{m['source_record_id']}` | doc_id=`{m['doc_id']}` | arxiv_id=`{m['arxiv_id']}` | doi=`{m['doi']}`"
                )
        lines.append("")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Debug selected canonical docs against normalized source snapshots.")
    parser.add_argument("--canonical-path", type=Path, default=DEFAULT_CANONICAL_PATH)
    parser.add_argument("--normalized-dir", type=Path, default=DEFAULT_NORMALIZED_DIR)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--canonical-id", action="append", required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    canonical_rows = load_jsonl(args.canonical_path)
    canonical_by_id = {row.get("canonical_id"): row for row in canonical_rows}

    arxiv_snapshot = discover_latest_full_snapshot(args.normalized_dir / "arxiv")
    openalex_snapshot = resolve_merge_snapshot(DEFAULT_MERGE_REPORTS["openalex_alignment"])
    semantic_snapshot = resolve_merge_snapshot(DEFAULT_MERGE_REPORTS["semantic_scholar_alignment"])
    crossref_snapshot = resolve_merge_snapshot(DEFAULT_MERGE_REPORTS["crossref_alignment"])

    snapshots = {
        "arxiv": arxiv_snapshot,
        "openalex": openalex_snapshot,
        "semantic_scholar": semantic_snapshot,
        "crossref": crossref_snapshot,
    }

    indexes = {
        name: build_indexes(load_jsonl(path))
        for name, path in snapshots.items()
    }

    documents: list[dict[str, Any]] = []

    for canonical_id in args.canonical_id:
        row = canonical_by_id.get(canonical_id)
        if row is None:
            documents.append(
                {
                    "canonical_id": canonical_id,
                    "found": False,
                }
            )
            continue

        sources = row.get("sources") or []
        if not isinstance(sources, list):
            sources = []

        provenance_sources = sorted(
            {
                s.get("source")
                for s in sources
                if isinstance(s, dict) and s.get("source")
            }
        )

        canonical_summary = {
            "title": row.get("title"),
            "reconciliation_key": row.get("reconciliation_key"),
            "source_count": row.get("source_count"),
            "unique_source_count": row.get("unique_source_count"),
            "doc_ids": row.get("doc_ids"),
            "source_ids_keys": sorted((row.get("source_ids") or {}).keys()),
            "provenance_sources": provenance_sources,
            "arxiv_id": row.get("arxiv_id"),
            "doi": row.get("doi"),
        }

        matched_normalized_rows: dict[str, list[dict[str, Any]]] = {}
        for source_name, idx in indexes.items():
            source_entry = None
            for s in sources:
                if isinstance(s, dict) and s.get("source") == source_name:
                    source_entry = s
                    break
            matches = find_matches(idx, source_entry, row)
            matched_normalized_rows[source_name] = [summarize_row(m) for m in matches]

        documents.append(
            {
                "canonical_id": canonical_id,
                "found": True,
                "canonical_summary": canonical_summary,
                "canonical_sources": sources,
                "matched_normalized_rows": matched_normalized_rows,
            }
        )

    report = {
        "report_name": "debug_selected_canonical_docs",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "canonical_path": normalize_path(args.canonical_path),
        "snapshots": {k: normalize_path(v) for k, v in snapshots.items()},
        "documents": documents,
    }

    latest_json = args.reports_dir / "debug_selected_canonical_docs_latest.json"
    latest_md = args.reports_dir / "debug_selected_canonical_docs_latest.md"
    hist_json = args.reports_dir / "history" / f"debug_selected_canonical_docs_{run_ts}.json"
    hist_md = args.reports_dir / "history" / f"debug_selected_canonical_docs_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(hist_json, report)
    dump_text(hist_md, build_markdown(report))

    print(f"[OK] canonical_path={normalize_path(args.canonical_path)}")
    for item in documents:
        print(f"[OK] canonical_id={item['canonical_id']} found={item['found']}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {hist_json}")
    print(f"[OK] history Markdown: {hist_md}")


if __name__ == "__main__":
    main()