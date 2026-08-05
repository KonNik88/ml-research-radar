from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "refresh_preflight_contract_v0.1"

DEFAULT_CANONICAL_PATH = Path("data/analytics/reconciled/canonical_documents.jsonl")
DEFAULT_CANDIDATE_PATH = Path(
    "data/analytics/reconciled/canonical_documents.candidate_refresh_v1.jsonl"
)
DEFAULT_NORMALIZED_ROOT = Path("data/normalized")
DEFAULT_UPDATE_DIR = Path("artifacts/reports/update")
DEFAULT_REPORTS_DIR = Path("artifacts/reports/update")

DEFAULT_MANIFEST_PATH = Path("artifacts/retrieval/manifests/latest.json")
DEFAULT_RETRIEVAL_CHECKS_PATH = Path(
    "artifacts/reports/validation/retrieval_checks_latest.json"
)
DEFAULT_POSTPASS_AUDIT_PATH = Path(
    "artifacts/reports/validation/postpass_audit_summary_latest.json"
)
DEFAULT_CANONICAL_CONTRACT_PATH = Path(
    "artifacts/reports/validation/canonical_contract_latest.json"
)
DEFAULT_KNOWN_ISSUES_PATH = Path(
    "artifacts/reports/validation/known_issues_snapshot_latest.json"
)
DEFAULT_REFRESH_CYCLE_REPORT_PATH = (
    DEFAULT_UPDATE_DIR / "run_incremental_refresh_cycle_latest.json"
)

DEFAULT_REFRESH_CONTRACT_PATH = Path("docs/refresh_contract_v1.md")
DEFAULT_PIPELINE_SCRIPT_PATH = Path("scripts/update/run_refresh_pipeline_v1.py")
DEFAULT_RECONCILE_STAGE_SCRIPT_PATH = Path(
    "scripts/update/run_incremental_reconcile_stage.py"
)
DEFAULT_PROMOTE_SCRIPT_PATH = Path("scripts/update/promote_canonical_candidate.py")

PRIMARY_JSONL_RE = re.compile(r"^documents\.\d{8}T\d{6}Z\.jsonl$")
DEFAULT_MERGE_REPORTS = {
    "openalex_alignment": DEFAULT_UPDATE_DIR / "merge_openalex_alignment_latest.json",
    "semantic_scholar_alignment": (
        DEFAULT_UPDATE_DIR / "merge_semantic_scholar_alignment_latest.json"
    ),
    "crossref_alignment": DEFAULT_UPDATE_DIR / "merge_crossref_alignment_latest.json",
}


def utc_now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_path(path: Path | str | None) -> str | None:
    if path is None:
        return None
    return str(path).replace("\\", "/")


def paths_match(left: Path | str | None, right: Path | str | None) -> bool:
    left_text = normalize_path(left)
    right_text = normalize_path(right)
    if not left_text or not right_text:
        return False
    if left_text == right_text:
        return True
    return left_text.endswith(f"/{right_text}") or right_text.endswith(f"/{left_text}")


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: Mapping[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def dump_text(path: Path, text: str) -> None:
    ensure_parent(path)
    path.write_text(text, encoding="utf-8")


def load_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise TypeError(f"Expected JSON object in {path}, got {type(payload)!r}")
    return payload


def read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def dig(data: Any, *keys: str, default: Any = None) -> Any:
    cur = data
    for key in keys:
        if not isinstance(cur, Mapping):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def first_present(
    data: Mapping[str, Any] | None,
    paths: list[tuple[str, ...]],
    default: Any = None,
) -> Any:
    if data is None:
        return default
    for path in paths:
        value = dig(data, *path, default=None)
        if value is not None:
            return value
    return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def report_ok(report: Mapping[str, Any] | None) -> bool:
    if report is None:
        return False

    if "ok" in report:
        return bool(report.get("ok"))

    verdict_ok = dig(report, "verdict", "ok", default=None)
    if verdict_ok is not None:
        return bool(verdict_ok)

    dod_passed = dig(report, "verdict", "dod_passed", default=None)
    if dod_passed is not None:
        return bool(dod_passed)

    required_failed_count = first_present(
        report,
        [
            ("required_failed_count",),
            ("verdict", "required_failed_count"),
        ],
        default=None,
    )
    if required_failed_count is not None:
        return safe_int(required_failed_count, default=999999) == 0

    return False


def is_full_snapshot_file(path: Path) -> bool:
    name = path.name
    if PRIMARY_JSONL_RE.match(name):
        return True
    if not name.startswith("documents") or not name.endswith(".jsonl"):
        return False
    disallowed = (".new.jsonl", ".updated.jsonl", ".unchanged.jsonl")
    return not name.endswith(disallowed)


def find_latest_full_snapshot(source_dir: Path) -> Path | None:
    if not source_dir.exists():
        return None

    strict_candidates = sorted(
        p for p in source_dir.glob("documents.*.jsonl") if PRIMARY_JSONL_RE.match(p.name)
    )
    if strict_candidates:
        return strict_candidates[-1]

    fallback_candidates = sorted(
        p for p in source_dir.glob("documents*.jsonl") if is_full_snapshot_file(p)
    )
    if fallback_candidates:
        return fallback_candidates[-1]

    return None


def count_jsonl_rows(path: Path | None, *, sample_limit: int = 10) -> dict[str, Any]:
    if path is None:
        return {
            "path": None,
            "exists": False,
            "rows_count": 0,
            "bad_json_count": 0,
            "sample_ids": [],
        }

    if not path.exists():
        return {
            "path": normalize_path(path),
            "exists": False,
            "rows_count": 0,
            "bad_json_count": 0,
            "sample_ids": [],
        }

    rows_count = 0
    bad_json_count = 0
    sample_ids: list[str] = []

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                bad_json_count += 1
                continue
            rows_count += 1
            if len(sample_ids) < sample_limit and isinstance(payload, Mapping):
                sample_id = (
                    payload.get("canonical_id")
                    or payload.get("doc_id")
                    or payload.get("id")
                    or payload.get("arxiv_id")
                )
                if sample_id:
                    sample_ids.append(str(sample_id))

    return {
        "path": normalize_path(path),
        "exists": True,
        "rows_count": rows_count,
        "bad_json_count": bad_json_count,
        "sample_ids": sample_ids,
    }


def summarize_canonical(path: Path) -> dict[str, Any]:
    summary = count_jsonl_rows(path)
    if not summary["exists"]:
        return {
            **summary,
            "doc_count": 0,
            "multisource_docs": 0,
            "doi_count": 0,
            "max_source_count": 0,
            "missing_canonical_id_count": 0,
            "duplicate_canonical_id_count": 0,
        }

    doc_count = 0
    multisource_docs = 0
    doi_count = 0
    max_source_count = 0
    missing_canonical_id_count = 0
    seen_ids: set[str] = set()
    duplicate_ids: set[str] = set()

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, Mapping):
                continue

            doc_count += 1
            canonical_id = payload.get("canonical_id")
            if not canonical_id:
                missing_canonical_id_count += 1
            else:
                key = str(canonical_id)
                if key in seen_ids:
                    duplicate_ids.add(key)
                seen_ids.add(key)

            source_count = safe_int(
                payload.get("unique_source_count", payload.get("source_count")),
                default=0,
            )
            if source_count > 1:
                multisource_docs += 1
            max_source_count = max(max_source_count, source_count)

            if payload.get("doi"):
                doi_count += 1

    return {
        **summary,
        "doc_count": doc_count,
        "multisource_docs": multisource_docs,
        "doi_count": doi_count,
        "max_source_count": max_source_count,
        "missing_canonical_id_count": missing_canonical_id_count,
        "duplicate_canonical_id_count": len(duplicate_ids),
    }


def summarize_manifest(path: Path) -> dict[str, Any]:
    payload = load_json_if_exists(path)
    if payload is None:
        return {
            "path": normalize_path(path),
            "exists": False,
            "build_id": None,
            "corpus_doc_count": None,
            "corpus_path": None,
            "lexical_index_path": None,
            "dense_embeddings_path": None,
        }

    return {
        "path": normalize_path(path),
        "exists": True,
        "build_id": payload.get("build_id"),
        "corpus_doc_count": payload.get("corpus_doc_count"),
        "corpus_path": payload.get("corpus_path"),
        "lexical_index_path": payload.get("lexical_index_path"),
        "dense_embeddings_path": payload.get("dense_embeddings_path"),
        "embedding_model_name": payload.get("embedding_model_name"),
    }


def resolve_manifest_artifact_path(manifest_path: Path, raw_path: Any) -> Path | None:
    if not raw_path:
        return None
    path = Path(str(raw_path))
    if path.is_absolute():
        return path

    project_relative = Path(str(raw_path))
    if project_relative.exists():
        return project_relative

    manifest_relative = manifest_path.parent / project_relative
    return manifest_relative


def summarize_source_input(normalized_root: Path, arxiv_input: Path | None) -> dict[str, Any]:
    resolved = arxiv_input if arxiv_input is not None else find_latest_full_snapshot(
        normalized_root / "arxiv"
    )
    rows = count_jsonl_rows(resolved)
    return {
        **rows,
        "resolved_from": "explicit" if arxiv_input is not None else "latest_full_snapshot",
        "full_snapshot_shape": bool(resolved and is_full_snapshot_file(resolved)),
    }


def parse_merge_report_arg(raw: str) -> tuple[str, Path]:
    if "=" not in raw:
        raise ValueError(
            "Invalid --merge-report value. Expected source_name=path/to/report.json"
        )
    source_name, raw_path = raw.split("=", 1)
    source_name = source_name.strip()
    raw_path = raw_path.strip()
    if not source_name or not raw_path:
        raise ValueError(
            "Invalid --merge-report value. Expected source_name=path/to/report.json"
        )
    return source_name, Path(raw_path)


def resolve_merge_report_specs(
    update_dir: Path,
    cli_values: list[str] | None,
) -> dict[str, Path]:
    if cli_values:
        return dict(parse_merge_report_arg(item) for item in cli_values)

    return {
        "openalex_alignment": update_dir / "merge_openalex_alignment_latest.json",
        "semantic_scholar_alignment": (
            update_dir / "merge_semantic_scholar_alignment_latest.json"
        ),
        "crossref_alignment": update_dir / "merge_crossref_alignment_latest.json",
    }


def summarize_merge_reports(
    *,
    update_dir: Path,
    cli_values: list[str] | None,
) -> dict[str, Any]:
    specs = resolve_merge_report_specs(update_dir=update_dir, cli_values=cli_values)
    rows: list[dict[str, Any]] = []

    for source_name, report_path in specs.items():
        payload = load_json_if_exists(report_path)
        merged_snapshot_raw = first_present(
            payload,
            [
                ("output", "merged_snapshot"),
                ("outputs", "merged_snapshot"),
                ("merged_snapshot",),
            ],
            default=None,
        )
        merged_snapshot = Path(str(merged_snapshot_raw)) if merged_snapshot_raw else None
        merged_rows = count_jsonl_rows(merged_snapshot)
        rows.append(
            {
                "source_name": source_name,
                "report_path": normalize_path(report_path),
                "report_exists": payload is not None,
                "report_source_name": payload.get("source_name") if payload else None,
                "merged_snapshot": normalize_path(merged_snapshot),
                "merged_snapshot_declared": merged_snapshot_raw is not None,
                "merged_snapshot_exists": merged_rows["exists"],
                "merged_snapshot_rows_count": merged_rows["rows_count"],
                "merged_snapshot_bad_json_count": merged_rows["bad_json_count"],
                "merged_snapshot_full_shape": bool(
                    merged_snapshot and is_full_snapshot_file(merged_snapshot)
                ),
            }
        )

    return {
        "expected_report_count": len(specs),
        "resolved_report_count": len(rows),
        "reports": rows,
    }


def summarize_report(path: Path) -> dict[str, Any]:
    payload = load_json_if_exists(path)
    return {
        "path": normalize_path(path),
        "exists": payload is not None,
        "ok": report_ok(payload),
        "payload": payload,
    }


def extract_refresh_cycle_values(report: Mapping[str, Any] | None) -> dict[str, Any]:
    return {
        "ready_for_reconcile_candidate": bool(
            dig(report, "readiness_summary", "ready_for_reconcile_candidate", default=False)
        ),
        "has_any_enrichment_hits": bool(
            dig(report, "readiness_summary", "has_any_enrichment_hits", default=False)
        ),
        "all_successful": bool(
            dig(report, "execution_summary", "all_successful", default=False)
        ),
        "failed_count": safe_int(
            dig(report, "execution_summary", "failed_count", default=999999),
            default=999999,
        ),
        "total_found_rows_across_sources": safe_int(
            dig(
                report,
                "readiness_summary",
                "total_found_rows_across_sources",
                default=0,
            ),
            default=0,
        ),
    }


def run_db_smoke() -> dict[str, Any]:
    cmd = [sys.executable, "-m", "scripts.export.test_db_read"]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    stdout = result.stdout or ""
    stderr = result.stderr or ""

    ping_match = re.search(r"Ping:\s*(True|False)", stdout)
    total_docs_match = re.search(r"Total docs:\s*(\d+)", stdout)

    return {
        "cmd": " ".join(cmd),
        "returncode": result.returncode,
        "ping": (ping_match.group(1) == "True") if ping_match else None,
        "total_docs": int(total_docs_match.group(1)) if total_docs_match else None,
        "stdout_tail": stdout[-4000:],
        "stderr_tail": stderr[-4000:],
        "ok": result.returncode == 0 and ping_match is not None,
    }


def build_static_summaries(args: argparse.Namespace) -> dict[str, Any]:
    refresh_contract_text = read_text_if_exists(args.refresh_contract_path)
    pipeline_text = read_text_if_exists(args.pipeline_script_path)
    reconcile_stage_text = read_text_if_exists(args.reconcile_stage_script_path)
    promote_text = read_text_if_exists(args.promote_script_path)

    required_contract_snippets = [
        "Manual refresh flow",
        "run_refresh_pipeline_v1",
        "run_incremental_reconcile_stage",
        "merged full snapshots",
        "check_refresh_preflight_contract",
        "refresh_preflight_contract_v0.1",
        "Controlled refresh rehearsal",
    ]
    required_pipeline_snippets = [
        "refresh_preflight",
        "scripts.validation.check_refresh_preflight_contract",
        "--candidate-rehearsal",
        "REHEARSAL_STOP_STEP",
        "canonical_documents.rehearsal_candidate",
        "--skip-refresh-preflight",
        "--require-refresh-cycle-report",
        "scripts.update.run_incremental_reconcile_stage",
        "scripts.update.promote_canonical_candidate",
        "scripts.export.export_postgres_v1",
        "scripts.retrieval.build_indexes",
        "scripts.validation.build_known_issues_snapshot",
        "scripts.update.check_refresh_definition_of_done",
    ]
    required_reconcile_snippets = [
        'reconcile_input_mode = "merged_full_inputs"',
        "latest-only reconcile is intentionally forbidden",
        "merge_reports_resolved_ok",
        "safe_to_execute",
    ]
    required_promote_snippets = [
        "backup_before_promotion",
        "shutil.copy2(latest_path, backup_path)",
        "shutil.copy2(candidate_path, latest_path)",
    ]

    return {
        "refresh_contract_exists": args.refresh_contract_path.exists(),
        "pipeline_script_exists": args.pipeline_script_path.exists(),
        "reconcile_stage_script_exists": args.reconcile_stage_script_path.exists(),
        "promote_script_exists": args.promote_script_path.exists(),
        "missing_refresh_contract_snippets": [
            item for item in required_contract_snippets if item not in refresh_contract_text
        ],
        "missing_pipeline_snippets": [
            item for item in required_pipeline_snippets if item not in pipeline_text
        ],
        "missing_reconcile_stage_snippets": [
            item for item in required_reconcile_snippets if item not in reconcile_stage_text
        ],
        "missing_promote_snippets": [
            item for item in required_promote_snippets if item not in promote_text
        ],
    }


def build_required_check_names(args: argparse.Namespace) -> list[str]:
    required = [
        "canonical_exists",
        "canonical_non_empty",
        "canonical_jsonl_valid",
        "canonical_ids_present",
        "canonical_ids_unique",
        "candidate_path_differs_from_canonical",
        "candidate_parent_exists",
        "arxiv_input_exists",
        "arxiv_input_non_empty",
        "arxiv_input_jsonl_valid",
        "arxiv_input_is_full_snapshot",
        "manifest_exists",
        "manifest_build_id_present",
        "manifest_doc_count_matches_canonical",
        "manifest_corpus_path_matches_canonical",
        "manifest_index_paths_present",
        "retrieval_checks_exists",
        "retrieval_checks_ok",
        "retrieval_checks_doc_count_matches_canonical",
        "retrieval_checks_build_id_matches_manifest",
        "postpass_audit_exists",
        "postpass_doc_count_matches_canonical",
        "canonical_contract_exists",
        "canonical_contract_ok",
        "canonical_contract_rows_match_canonical",
        "refresh_contract_doc_exists",
        "refresh_contract_preflight_markers_present",
        "pipeline_script_exists",
        "pipeline_refresh_steps_present",
        "reconcile_stage_script_exists",
        "reconcile_stage_uses_merged_full_inputs",
        "promote_script_exists",
        "promote_script_keeps_backup",
    ]

    if args.require_known_issues:
        required.extend(
            [
                "known_issues_exists",
                "known_issues_doc_count_matches_canonical",
                "known_issues_build_id_matches_manifest",
            ]
        )

    if args.require_merged_inputs:
        required.extend(
            [
                "merge_reports_expected_count",
                "merge_reports_all_exist",
                "merge_reports_all_declare_snapshots",
                "merge_snapshots_all_exist",
                "merge_snapshots_all_non_empty",
                "merge_snapshots_jsonl_valid",
                "merge_snapshots_full_shape",
            ]
        )

    if args.require_refresh_cycle_report:
        required.extend(
            [
                "refresh_cycle_report_exists",
                "refresh_cycle_ready_for_reconcile_candidate",
                "refresh_cycle_execution_successful",
                "refresh_cycle_has_enrichment_hits",
            ]
        )

    if args.check_db:
        required.extend(
            [
                "db_smoke_ok",
                "db_ping_true",
                "db_doc_count_matches_canonical",
            ]
        )

    return required


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    run_ts = utc_now_ts()

    canonical = summarize_canonical(args.canonical_path)
    arxiv_input = summarize_source_input(args.normalized_root, args.arxiv_input)
    manifest = summarize_manifest(args.manifest_path)

    retrieval_checks = summarize_report(args.retrieval_checks_path)
    postpass_audit = summarize_report(args.postpass_audit_path)
    canonical_contract = summarize_report(args.canonical_contract_path)
    known_issues = summarize_report(args.known_issues_path)
    refresh_cycle = summarize_report(args.refresh_cycle_report_path)

    merge_reports = summarize_merge_reports(
        update_dir=args.update_dir,
        cli_values=args.merge_report,
    )
    static = build_static_summaries(args)

    retrieval_payload = retrieval_checks["payload"]
    postpass_payload = postpass_audit["payload"]
    canonical_contract_payload = canonical_contract["payload"]
    known_issues_payload = known_issues["payload"]
    refresh_cycle_payload = refresh_cycle["payload"]

    manifest_doc_count = safe_int(manifest["corpus_doc_count"], default=-1)
    manifest_build_id = manifest["build_id"]
    manifest_corpus_path = normalize_path(manifest["corpus_path"])
    canonical_path_text = normalize_path(args.canonical_path)

    retrieval_checks_doc_count = safe_int(
        first_present(
            retrieval_payload,
            [
                ("corpus_doc_count",),
                ("summary", "corpus_doc_count"),
                ("extracted_values", "corpus_doc_count"),
            ],
            default=-1,
        ),
        default=-1,
    )
    retrieval_checks_build_id = first_present(
        retrieval_payload,
        [
            ("build_id",),
            ("summary", "build_id"),
            ("extracted_values", "build_id"),
        ],
        default=None,
    )

    postpass_doc_count = safe_int(
        first_present(
            postpass_payload,
            [
                ("total_docs",),
                ("summary", "total_docs"),
                ("corpus_summary", "total_docs"),
                ("audit_summary", "total_docs"),
            ],
            default=-1,
        ),
        default=-1,
    )

    canonical_contract_rows_count = safe_int(
        first_present(
            canonical_contract_payload,
            [
                ("summary", "rows_count"),
                ("extracted_values", "canonical_contract_rows_count"),
            ],
            default=-1,
        ),
        default=-1,
    )

    known_issues_doc_count = safe_int(
        first_present(
            known_issues_payload,
            [
                ("canonical_corpus_doc_count",),
                ("summary", "canonical_corpus_doc_count"),
                ("current_state", "canonical_corpus_doc_count"),
                ("snapshot", "canonical_corpus_doc_count"),
                ("operational_truth", "canonical_corpus_doc_count"),
            ],
            default=-1,
        ),
        default=-1,
    )
    known_issues_build_id = first_present(
        known_issues_payload,
        [
            ("retrieval_build_id",),
            ("summary", "retrieval_build_id"),
            ("current_state", "retrieval_build_id"),
            ("snapshot", "retrieval_build_id"),
            ("operational_truth", "retrieval_build_id"),
            ("retrieval_findings", "build_id"),
        ],
        default=None,
    )

    refresh_cycle_values = extract_refresh_cycle_values(refresh_cycle_payload)
    db_smoke = run_db_smoke() if args.check_db else None

    index_paths = [
        resolve_manifest_artifact_path(args.manifest_path, manifest["lexical_index_path"]),
        resolve_manifest_artifact_path(args.manifest_path, manifest["dense_embeddings_path"]),
    ]

    merge_rows = merge_reports["reports"]

    checks = {
        "canonical_exists": canonical["exists"],
        "canonical_non_empty": canonical["doc_count"] > 0,
        "canonical_jsonl_valid": canonical["bad_json_count"] == 0,
        "canonical_ids_present": canonical["missing_canonical_id_count"] == 0,
        "canonical_ids_unique": canonical["duplicate_canonical_id_count"] == 0,
        "candidate_path_differs_from_canonical": (
            normalize_path(args.candidate_path) != normalize_path(args.canonical_path)
        ),
        "candidate_parent_exists": args.candidate_path.parent.exists(),
        "arxiv_input_exists": arxiv_input["exists"],
        "arxiv_input_non_empty": safe_int(arxiv_input["rows_count"]) > 0,
        "arxiv_input_jsonl_valid": arxiv_input["bad_json_count"] == 0,
        "arxiv_input_is_full_snapshot": arxiv_input["full_snapshot_shape"],
        "manifest_exists": manifest["exists"],
        "manifest_build_id_present": bool(manifest_build_id),
        "manifest_doc_count_matches_canonical": (
            manifest_doc_count == canonical["doc_count"]
        ),
        "manifest_corpus_path_matches_canonical": (
            paths_match(manifest_corpus_path, canonical_path_text)
        ),
        "manifest_index_paths_present": all(path is not None for path in index_paths),
        "manifest_index_files_exist": all(
            path is not None and path.exists() for path in index_paths
        ),
        "retrieval_checks_exists": retrieval_checks["exists"],
        "retrieval_checks_ok": bool(
            retrieval_checks["ok"]
            or (
                retrieval_checks["exists"]
                and retrieval_checks_doc_count > 0
                and retrieval_checks_build_id
            )
        ),
        "retrieval_checks_doc_count_matches_canonical": (
            retrieval_checks_doc_count == canonical["doc_count"]
        ),
        "retrieval_checks_build_id_matches_manifest": (
            retrieval_checks_build_id == manifest_build_id
        ),
        "postpass_audit_exists": postpass_audit["exists"],
        "postpass_doc_count_matches_canonical": (
            postpass_doc_count == canonical["doc_count"]
        ),
        "canonical_contract_exists": canonical_contract["exists"],
        "canonical_contract_ok": canonical_contract["ok"],
        "canonical_contract_rows_match_canonical": (
            canonical_contract_rows_count == canonical["doc_count"]
        ),
        "known_issues_exists": known_issues["exists"],
        "known_issues_doc_count_matches_canonical": (
            known_issues_doc_count == canonical["doc_count"]
        ),
        "known_issues_build_id_matches_manifest": (
            known_issues_build_id == manifest_build_id
        ),
        "merge_reports_expected_count": (
            merge_reports["expected_report_count"] == 3
            and merge_reports["resolved_report_count"] == 3
        ),
        "merge_reports_all_exist": all(row["report_exists"] for row in merge_rows),
        "merge_reports_all_declare_snapshots": all(
            row["merged_snapshot_declared"] for row in merge_rows
        ),
        "merge_snapshots_all_exist": all(
            row["merged_snapshot_exists"] for row in merge_rows
        ),
        "merge_snapshots_all_non_empty": all(
            safe_int(row["merged_snapshot_rows_count"]) > 0 for row in merge_rows
        ),
        "merge_snapshots_jsonl_valid": all(
            safe_int(row["merged_snapshot_bad_json_count"]) == 0 for row in merge_rows
        ),
        "merge_snapshots_full_shape": all(
            row["merged_snapshot_full_shape"] for row in merge_rows
        ),
        "refresh_cycle_report_exists": refresh_cycle["exists"],
        "refresh_cycle_ready_for_reconcile_candidate": refresh_cycle_values[
            "ready_for_reconcile_candidate"
        ],
        "refresh_cycle_execution_successful": (
            refresh_cycle_values["all_successful"]
            and refresh_cycle_values["failed_count"] == 0
        ),
        "refresh_cycle_has_enrichment_hits": refresh_cycle_values[
            "has_any_enrichment_hits"
        ],
        "refresh_contract_doc_exists": static["refresh_contract_exists"],
        "refresh_contract_preflight_markers_present": not static[
            "missing_refresh_contract_snippets"
        ],
        "pipeline_script_exists": static["pipeline_script_exists"],
        "pipeline_refresh_steps_present": not static["missing_pipeline_snippets"],
        "reconcile_stage_script_exists": static["reconcile_stage_script_exists"],
        "reconcile_stage_uses_merged_full_inputs": not static[
            "missing_reconcile_stage_snippets"
        ],
        "promote_script_exists": static["promote_script_exists"],
        "promote_script_keeps_backup": not static["missing_promote_snippets"],
        "db_smoke_ok": bool(db_smoke and db_smoke["ok"]),
        "db_ping_true": bool(db_smoke and db_smoke["ping"] is True),
        "db_doc_count_matches_canonical": bool(
            db_smoke and db_smoke.get("total_docs") == canonical["doc_count"]
        ),
    }

    required_check_names = build_required_check_names(args)
    required_failed_checks = [
        name for name in required_check_names if not checks.get(name, False)
    ]

    report = {
        "schema_version": SCHEMA_VERSION,
        "report_name": "check_refresh_preflight_contract",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "inputs": {
            "canonical_path": normalize_path(args.canonical_path),
            "candidate_path": normalize_path(args.candidate_path),
            "normalized_root": normalize_path(args.normalized_root),
            "arxiv_input": normalize_path(args.arxiv_input),
            "update_dir": normalize_path(args.update_dir),
            "manifest_path": normalize_path(args.manifest_path),
            "retrieval_checks_path": normalize_path(args.retrieval_checks_path),
            "postpass_audit_path": normalize_path(args.postpass_audit_path),
            "canonical_contract_path": normalize_path(args.canonical_contract_path),
            "known_issues_path": normalize_path(args.known_issues_path),
            "refresh_cycle_report_path": normalize_path(args.refresh_cycle_report_path),
            "merge_reports": args.merge_report or [],
            "check_db": bool(args.check_db),
            "require_known_issues": bool(args.require_known_issues),
            "require_merged_inputs": bool(args.require_merged_inputs),
            "require_refresh_cycle_report": bool(args.require_refresh_cycle_report),
        },
        "canonical_summary": canonical,
        "arxiv_input_summary": arxiv_input,
        "retrieval_manifest": manifest,
        "report_summaries": {
            "retrieval_checks": {
                "path": retrieval_checks["path"],
                "exists": retrieval_checks["exists"],
                "ok": retrieval_checks["ok"],
                "doc_count": retrieval_checks_doc_count,
                "build_id": retrieval_checks_build_id,
            },
            "postpass_audit": {
                "path": postpass_audit["path"],
                "exists": postpass_audit["exists"],
                "ok": postpass_audit["ok"],
                "doc_count": postpass_doc_count,
            },
            "canonical_contract": {
                "path": canonical_contract["path"],
                "exists": canonical_contract["exists"],
                "ok": canonical_contract["ok"],
                "rows_count": canonical_contract_rows_count,
            },
            "known_issues": {
                "path": known_issues["path"],
                "exists": known_issues["exists"],
                "ok": known_issues["ok"],
                "doc_count": known_issues_doc_count,
                "build_id": known_issues_build_id,
            },
            "refresh_cycle": {
                "path": refresh_cycle["path"],
                "exists": refresh_cycle["exists"],
                **refresh_cycle_values,
            },
        },
        "merge_reports": merge_reports,
        "static_contract": static,
        "db_smoke": db_smoke,
        "checks": checks,
        "verdict": {
            "ok": len(required_failed_checks) == 0,
            "required_check_count": len(required_check_names),
            "required_failed_count": len(required_failed_checks),
            "required_failed_checks": required_failed_checks,
            "required_check_names": required_check_names,
        },
    }

    return report


def build_markdown(report: Mapping[str, Any]) -> str:
    verdict = report["verdict"]
    lines = [
        "# Refresh preflight contract report",
        "",
        f"- Generated at: {report['generated_at_utc']}",
        f"- Schema version: `{report['schema_version']}`",
        f"- OK: `{verdict['ok']}`",
        f"- Required failed count: `{verdict['required_failed_count']}`",
        "",
        "## Inputs",
    ]

    for key, value in report["inputs"].items():
        lines.append(f"- {key}: `{value}`")

    lines.extend(["", "## Core Counts"])
    canonical = report["canonical_summary"]
    manifest = report["retrieval_manifest"]
    lines.append(f"- canonical_doc_count: `{canonical['doc_count']}`")
    lines.append(f"- manifest_doc_count: `{manifest['corpus_doc_count']}`")
    lines.append(f"- manifest_build_id: `{manifest['build_id']}`")

    lines.extend(["", "## Checks"])
    for key, value in report["checks"].items():
        lines.append(f"- {key}: `{value}`")

    if verdict["required_failed_checks"]:
        lines.extend(["", "## Required Failures"])
        for key in verdict["required_failed_checks"]:
            lines.append(f"- `{key}`")

    lines.append("")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only refresh preflight contract validator for ML Research Radar."
        )
    )
    parser.add_argument("--canonical-path", type=Path, default=DEFAULT_CANONICAL_PATH)
    parser.add_argument("--candidate-path", type=Path, default=DEFAULT_CANDIDATE_PATH)
    parser.add_argument("--normalized-root", type=Path, default=DEFAULT_NORMALIZED_ROOT)
    parser.add_argument("--arxiv-input", type=Path, default=None)
    parser.add_argument("--update-dir", type=Path, default=DEFAULT_UPDATE_DIR)
    parser.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument(
        "--retrieval-checks-path",
        type=Path,
        default=DEFAULT_RETRIEVAL_CHECKS_PATH,
    )
    parser.add_argument(
        "--postpass-audit-path",
        type=Path,
        default=DEFAULT_POSTPASS_AUDIT_PATH,
    )
    parser.add_argument(
        "--canonical-contract-path",
        type=Path,
        default=DEFAULT_CANONICAL_CONTRACT_PATH,
    )
    parser.add_argument("--known-issues-path", type=Path, default=DEFAULT_KNOWN_ISSUES_PATH)
    parser.add_argument(
        "--refresh-cycle-report-path",
        type=Path,
        default=DEFAULT_REFRESH_CYCLE_REPORT_PATH,
    )
    parser.add_argument(
        "--merge-report",
        action="append",
        default=None,
        help=(
            "Merged source report in source_name=path/to/report.json format. "
            "Defaults to latest OpenAlex/Semantic Scholar/Crossref merge reports."
        ),
    )
    parser.add_argument(
        "--refresh-contract-path",
        type=Path,
        default=DEFAULT_REFRESH_CONTRACT_PATH,
    )
    parser.add_argument(
        "--pipeline-script-path",
        type=Path,
        default=DEFAULT_PIPELINE_SCRIPT_PATH,
    )
    parser.add_argument(
        "--reconcile-stage-script-path",
        type=Path,
        default=DEFAULT_RECONCILE_STAGE_SCRIPT_PATH,
    )
    parser.add_argument(
        "--promote-script-path",
        type=Path,
        default=DEFAULT_PROMOTE_SCRIPT_PATH,
    )
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--check-db", action="store_true")
    parser.add_argument("--require-known-issues", action="store_true")
    parser.add_argument("--require-merged-inputs", action="store_true")
    parser.add_argument("--require-refresh-cycle-report", action="store_true")
    parser.add_argument("--strict", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    report = build_report(args)
    run_ts = report["run_ts"]

    latest_json = args.reports_dir / "refresh_preflight_contract_latest.json"
    latest_md = args.reports_dir / "refresh_preflight_contract_latest.md"
    hist_json = (
        args.reports_dir / "history" / f"refresh_preflight_contract_{run_ts}.json"
    )
    hist_md = (
        args.reports_dir / "history" / f"refresh_preflight_contract_{run_ts}.md"
    )

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(hist_json, report)
    dump_text(hist_md, build_markdown(report))

    for key, value in report["checks"].items():
        status = "OK" if value else "FAIL"
        print(f"[{status}] {key}={value}")

    verdict = report["verdict"]
    print(f"[OK] ok={verdict['ok']}")
    print(f"[OK] required_failed_count={verdict['required_failed_count']}")
    print(f"[OK] required_failed_checks={verdict['required_failed_checks']}")
    print(f"[OK] latest JSON: {latest_json}")
    print(f"[OK] latest Markdown: {latest_md}")
    print(f"[OK] history JSON: {hist_json}")
    print(f"[OK] history Markdown: {hist_md}")

    if args.strict and not verdict["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
