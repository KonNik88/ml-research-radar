from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.api.db import PostgresConfig, PostgresDocumentStore
from radar_core.retrieval.artifacts import read_latest_manifest


DEFAULT_REPORTS_DIR = Path("artifacts/reports")
DEFAULT_UPDATE_DIR = DEFAULT_REPORTS_DIR / "update"
DEFAULT_OUTPUT_DIR = DEFAULT_UPDATE_DIR
DEFAULT_CANONICAL_PATH = Path("data/analytics/reconciled/canonical_documents.jsonl")


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required JSON file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def count_jsonl_rows(path: Path) -> int:
    if not path.exists():
        raise FileNotFoundError(f"JSONL file not found: {path}")

    count = 0
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
    return count


def summarize_canonical(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Canonical corpus not found: {path}")

    doc_count = 0
    multisource_docs = 0
    doi_count = 0
    max_source_count = 0
    sample_ids: list[str] = []

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            payload = json.loads(line)
            doc_count += 1

            source_count = int(payload.get("source_count", 0) or 0)
            if source_count > 1:
                multisource_docs += 1
            max_source_count = max(max_source_count, source_count)

            if payload.get("doi"):
                doi_count += 1

            if len(sample_ids) < 10 and payload.get("canonical_id"):
                sample_ids.append(payload["canonical_id"])

    return {
        "path": str(path).replace("\\", "/"),
        "doc_count": doc_count,
        "multisource_docs": multisource_docs,
        "doi_count": doi_count,
        "max_source_count": max_source_count,
        "sample_canonical_ids": sample_ids,
    }


def summarize_manifest(artifacts_root: Path) -> dict[str, Any]:
    manifest = read_latest_manifest(root_dir=artifacts_root)
    return {
        "path": str((artifacts_root / "manifests" / "latest.json")).replace("\\", "/"),
        "build_id": manifest.build_id,
        "created_at": manifest.created_at,
        "corpus_path": manifest.corpus_path.replace("\\", "/"),
        "corpus_doc_count": manifest.corpus_doc_count,
        "corpus_fingerprint": manifest.corpus_fingerprint,
        "embedding_model_name": manifest.embedding_model_name,
        "lexical_index_path": manifest.lexical_index_path.replace("\\", "/"),
        "dense_embeddings_path": manifest.dense_embeddings_path.replace("\\", "/"),
        "text_fields": manifest.text_fields,
    }


def summarize_update_reports(update_dir: Path) -> dict[str, Any]:
    plan_path = update_dir / "plan_incremental_refresh_latest.json"
    doi_extract_path = update_dir / "extract_incremental_doi_candidates_latest.json"
    refresh_cycle_path = update_dir / "run_incremental_refresh_cycle_latest.json"
    reconcile_stage_path = update_dir / "run_incremental_reconcile_stage_latest.json"
    doi_candidates_path = update_dir / "doi_candidates_latest.jsonl"

    plan = load_json(plan_path)
    doi_extract = load_json(doi_extract_path)
    refresh_cycle = load_json(refresh_cycle_path)
    reconcile_stage = load_json(reconcile_stage_path)

    doi_candidates_count = count_jsonl_rows(doi_candidates_path) if doi_candidates_path.exists() else 0

    return {
        "plan_incremental_refresh": {
            "path": str(plan_path).replace("\\", "/"),
            "run_ts": plan.get("run_ts"),
            "canonical_doc_count": ((plan.get("canonical_summary") or {}).get("doc_count")),
            "retrieval_doc_count": ((plan.get("retrieval_summary") or {}).get("corpus_doc_count")),
            "arxiv_primary_doc_count": ((plan.get("arxiv_primary_snapshot") or {}).get("doc_count")),
            "doi_coverage": ((plan.get("arxiv_primary_snapshot") or {}).get("doi_coverage")),
        },
        "extract_incremental_doi_candidates": {
            "path": str(doi_extract_path).replace("\\", "/"),
            "run_ts": doi_extract.get("run_ts"),
            "new_docs_total": ((doi_extract.get("counts") or {}).get("new_docs_total")),
            "updated_docs_total": ((doi_extract.get("counts") or {}).get("updated_docs_total")),
            "unique_doi_candidates": ((doi_extract.get("counts") or {}).get("unique_doi_candidates")),
        },
        "run_incremental_refresh_cycle": {
            "path": str(refresh_cycle_path).replace("\\", "/"),
            "run_ts": refresh_cycle.get("run_ts"),
            "mode": refresh_cycle.get("mode"),
            "ready_for_reconcile_candidate": ((refresh_cycle.get("readiness_summary") or {}).get("ready_for_reconcile_candidate")),
            "has_any_enrichment_hits": ((refresh_cycle.get("readiness_summary") or {}).get("has_any_enrichment_hits")),
            "executed_count": ((refresh_cycle.get("execution_summary") or {}).get("executed_count")),
            "failed_count": ((refresh_cycle.get("execution_summary") or {}).get("failed_count")),
        },
        "run_incremental_reconcile_stage": {
            "path": str(reconcile_stage_path).replace("\\", "/"),
            "run_ts": reconcile_stage.get("run_ts"),
            "mode": reconcile_stage.get("mode"),
            "ready_for_reconcile_candidate": ((reconcile_stage.get("readiness") or {}).get("ready_for_reconcile_candidate")),
            "selective_execution_ok": ((reconcile_stage.get("readiness") or {}).get("selective_execution_ok")),
        },
        "doi_candidates_file": {
            "path": str(doi_candidates_path).replace("\\", "/"),
            "count": doi_candidates_count,
        },
    }


def fetch_scalar(cur: Any, query: str) -> int:
    cur.execute(query)
    row = cur.fetchone()

    if row is None:
        return 0

    if isinstance(row, dict):
        if not row:
            return 0
        return int(next(iter(row.values())) or 0)

    try:
        return int(row[0] or 0)
    except Exception:
        try:
            return int(next(iter(row)) or 0)
        except Exception as exc:
            raise TypeError(f"Unsupported scalar row format: {type(row)!r}, row={row!r}") from exc


def summarize_postgres(
    host: str,
    port: int,
    dbname: str,
    user: str,
    password: str,
) -> dict[str, Any]:
    store = PostgresDocumentStore(
        PostgresConfig(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password,
        )
    )

    ping_ok = store.ping()
    summary: dict[str, Any] = {
        "connected": ping_ok,
        "host": host,
        "port": port,
        "dbname": dbname,
        "user": user,
    }

    if not ping_ok:
        summary["error"] = "Postgres ping failed"
        return summary

    with store.connection() as conn:
        with conn.cursor() as cur:
            summary.update(
                {
                    "canonical_documents": fetch_scalar(cur, "SELECT COUNT(*) FROM canonical_documents"),
                    "source_documents": fetch_scalar(cur, "SELECT COUNT(*) FROM source_documents"),
                    "canonical_source_links": fetch_scalar(cur, "SELECT COUNT(*) FROM canonical_source_links"),
                    "document_references": fetch_scalar(cur, "SELECT COUNT(*) FROM document_references"),
                    "export_runs": fetch_scalar(cur, "SELECT COUNT(*) FROM export_runs"),
                }
            )

    return summary

    with store._connect() as conn:  # noqa: SLF001 - acceptable for internal diagnostics script
        with conn.cursor() as cur:
            summary.update(
                {
                    "canonical_documents": fetch_scalar(cur, "SELECT COUNT(*) FROM canonical_documents"),
                    "source_documents": fetch_scalar(cur, "SELECT COUNT(*) FROM source_documents"),
                    "canonical_source_links": fetch_scalar(cur, "SELECT COUNT(*) FROM canonical_source_links"),
                    "document_references": fetch_scalar(cur, "SELECT COUNT(*) FROM document_references"),
                    "export_runs": fetch_scalar(cur, "SELECT COUNT(*) FROM export_runs"),
                }
            )

    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture current refresh baseline before running a real refresh cycle."
    )
    parser.add_argument(
        "--canonical-path",
        type=Path,
        default=DEFAULT_CANONICAL_PATH,
        help="Path to canonical JSONL corpus.",
    )
    parser.add_argument(
        "--artifacts-root",
        type=Path,
        default=Path("artifacts/retrieval"),
        help="Retrieval artifacts root directory.",
    )
    parser.add_argument(
        "--update-dir",
        type=Path,
        default=DEFAULT_UPDATE_DIR,
        help="Directory with latest update reports.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory to write baseline reports.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=15432)
    parser.add_argument("--dbname", default="ml_radar")
    parser.add_argument("--user", default="ml_radar")
    parser.add_argument("--password", default="ml_radar_dev")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    canonical_summary = summarize_canonical(args.canonical_path)
    retrieval_summary = summarize_manifest(args.artifacts_root)
    update_reports_summary = summarize_update_reports(args.update_dir)
    postgres_summary = summarize_postgres(
        host=args.host,
        port=args.port,
        dbname=args.dbname,
        user=args.user,
        password=args.password,
    )

    report = {
        "report_name": "refresh_baseline",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "canonical_summary": canonical_summary,
        "retrieval_summary": retrieval_summary,
        "postgres_summary": postgres_summary,
        "update_reports_summary": update_reports_summary,
        "consistency_checks": {
            "canonical_vs_retrieval_doc_count_match": (
                canonical_summary["doc_count"] == retrieval_summary["corpus_doc_count"]
            ),
            "doi_candidates_count": update_reports_summary["doi_candidates_file"]["count"],
        },
    }

    output_dir: Path = args.output_dir
    latest_json = output_dir / "refresh_baseline_latest.json"
    hist_json = output_dir / "history" / f"refresh_baseline_{run_ts}.json"

    dump_json(latest_json, report)
    dump_json(hist_json, report)

    print(f"[OK] canonical_doc_count={canonical_summary['doc_count']}")
    print(f"[OK] multisource_docs={canonical_summary['multisource_docs']}")
    print(f"[OK] retrieval_doc_count={retrieval_summary['corpus_doc_count']}")
    print(f"[OK] doi_candidates_count={update_reports_summary['doi_candidates_file']['count']}")
    print(f"[OK] postgres_connected={postgres_summary['connected']}")
    if postgres_summary["connected"]:
        print(f"[OK] postgres_canonical_documents={postgres_summary['canonical_documents']}")
        print(f"[OK] postgres_source_documents={postgres_summary['source_documents']}")
    print(
        "[OK] canonical_vs_retrieval_doc_count_match="
        f"{report['consistency_checks']['canonical_vs_retrieval_doc_count_match']}"
    )
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] history JSON: {hist_json}")


if __name__ == "__main__":
    main()