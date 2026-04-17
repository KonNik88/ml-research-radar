from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from radar_core.config import load_sources_config
from radar_core.ingest.arxiv import ArxivIngestor, ArxivQuery
from radar_core.normalize.pipeline import deduplicate_documents


DEFAULT_STATE_PATH = Path("data/state/arxiv_incremental_state.json")
DEFAULT_REPORTS_DIR = Path("artifacts/reports")
DEFAULT_BATCHES_DIR = Path("data/normalized/arxiv_incremental_batches")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ts_slug(dt: datetime | None = None) -> str:
    dt = dt or utc_now()
    return dt.strftime("%Y%m%dT%H%M%SZ")


def iso_now() -> str:
    return utc_now().isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def dump_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_parent(path)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_query_text(value: str) -> str:
    return " ".join((value or "").strip().split())


def load_profile_arxiv_config(profile_name: str) -> dict[str, Any]:
    cfg = load_sources_config()
    profiles = cfg.get("profiles", {})

    if profile_name not in profiles:
        raise ValueError(f"Profile not found in configs/sources.yaml: {profile_name}")

    arxiv_cfg = profiles[profile_name].get("arxiv")
    if not arxiv_cfg:
        raise ValueError(f"Profile '{profile_name}' does not define arxiv config")

    return arxiv_cfg


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch one arXiv slice and persist it as an incremental batch."
    )
    parser.add_argument("--profile", default="medium_scale")
    parser.add_argument("--state-path", default=str(DEFAULT_STATE_PATH))
    parser.add_argument("--reports-dir", default=str(DEFAULT_REPORTS_DIR))
    parser.add_argument("--batches-dir", default=str(DEFAULT_BATCHES_DIR))

    parser.add_argument("--search-query", default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--start", type=int, default=None)

    parser.add_argument(
        "--advance-state-on-success",
        action="store_true",
        help="Advance next_start in state after successful fetch.",
    )
    parser.add_argument(
        "--initialize-state",
        action="store_true",
        help="Create/refresh state from profile and exit without network call.",
    )
    parser.add_argument(
        "--cooldown-minutes-on-rate-limit",
        type=int,
        default=60,
        help="Cooldown to write into state after 429 / rate exceeded.",
    )
    parser.add_argument(
        "--cooldown-minutes-on-timeout",
        type=int,
        default=30,
        help="Cooldown to write into state after timeout / 503.",
    )
    parser.add_argument(
        "--cooldown-minutes-on-network-error",
        type=int,
        default=20,
        help="Cooldown to write into state after DNS / connection failures.",
    )
    parser.add_argument(
        "--ignore-cooldown",
        action="store_true",
        help="Run even if cooldown_until is still in the future.",
    )
    return parser


def default_state_from_profile(profile_name: str, arxiv_cfg: dict[str, Any]) -> dict[str, Any]:
    search_query = normalize_query_text(arxiv_cfg.get("search_query", ""))
    batch_size = int(arxiv_cfg.get("batch_size") or arxiv_cfg.get("max_results") or 25)

    return {
        "profile": profile_name,
        "search_query": search_query,
        "batch_size": batch_size,
        "next_start": 0,
        "successful_batches": 0,
        "successful_docs_total": 0,
        "last_success_at": None,
        "last_attempt_at": None,
        "last_status": "initialized",
        "last_error": None,
        "cooldown_until": None,
        "sort_by": arxiv_cfg.get("sort_by", "submittedDate"),
        "sort_order": arxiv_cfg.get("sort_order", "descending"),
    }


def resolve_state(args: argparse.Namespace, arxiv_cfg: dict[str, Any], state_path: Path) -> dict[str, Any]:
    state = load_json(state_path)

    if args.initialize_state or not state:
        state = default_state_from_profile(args.profile, arxiv_cfg)

    if args.search_query is not None:
        state["search_query"] = normalize_query_text(args.search_query)

    if args.batch_size is not None:
        state["batch_size"] = int(args.batch_size)

    if args.start is not None:
        state["next_start"] = int(args.start)

    return state


def save_state(state_path: Path, state: dict[str, Any]) -> None:
    dump_json(state_path, state)


def cooldown_active(state: dict[str, Any]) -> bool:
    raw = state.get("cooldown_until")
    if not raw:
        return False

    try:
        dt = datetime.fromisoformat(raw)
    except Exception:
        return False

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt > utc_now()


def set_cooldown(state: dict[str, Any], minutes: int) -> None:
    until = utc_now() + timedelta(minutes=minutes)
    state["cooldown_until"] = until.isoformat()


def classify_error(exc: Exception) -> str:
    text = repr(exc).lower()

    if "429" in text or "rate exceeded" in text:
        return "rate_limited"

    if "503" in text or "service unavailable" in text:
        return "service_unavailable"

    if "timeout" in text or "read timed out" in text:
        return "timeout"

    if "nameresolutionerror" in text or "failed to resolve" in text or "getaddrinfo failed" in text:
        return "network_error"

    if "connectionerror" in text or "maxretryerror" in text:
        return "network_error"

    return "fatal_error"


def main() -> None:
    args = build_parser().parse_args()

    state_path = Path(args.state_path)
    reports_dir = Path(args.reports_dir)
    batches_dir = Path(args.batches_dir)

    arxiv_cfg = load_profile_arxiv_config(args.profile)
    state = resolve_state(args, arxiv_cfg, state_path)

    if args.initialize_state:
        save_state(state_path, state)
        print(f"[OK] incremental state initialized: {state_path}")
        print(f"[OK] profile={args.profile}")
        print(f"[OK] next_start={state['next_start']}")
        print(f"[OK] batch_size={state['batch_size']}")
        return

    if cooldown_active(state) and not args.ignore_cooldown:
        print(f"[SKIP] cooldown active until {state['cooldown_until']}")
        return

    run_ts = ts_slug()
    state["last_attempt_at"] = iso_now()

    search_query = normalize_query_text(state["search_query"])
    batch_size = int(state["batch_size"])
    start = int(state["next_start"])
    sort_by = state.get("sort_by", "submittedDate")
    sort_order = state.get("sort_order", "descending")

    query = ArxivQuery(
        search_query=search_query,
        start=start,
        max_results=batch_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    ingestor = ArxivIngestor()

    try:
        raw_docs, normalized_docs = ingestor.ingest(query=query)
        deduped_docs = deduplicate_documents(normalized_docs)

        raw_rows = [doc.model_dump(mode="json") for doc in raw_docs]
        norm_rows = [doc.model_dump(mode="json") for doc in deduped_docs]

        batch_raw_path = batches_dir / f"arxiv_raw_batch.{run_ts}.jsonl"
        batch_norm_path = batches_dir / f"arxiv_normalized_batch.{run_ts}.jsonl"
        batch_meta_path = batches_dir / f"arxiv_batch_meta.{run_ts}.json"

        dump_jsonl(batch_raw_path, raw_rows)
        dump_jsonl(batch_norm_path, norm_rows)

        batch_meta = {
            "run_ts": run_ts,
            "profile": args.profile,
            "query": {
                "search_query": search_query,
                "start": start,
                "max_results": batch_size,
                "sort_by": sort_by,
                "sort_order": sort_order,
            },
            "raw_count": len(raw_rows),
            "normalized_count_before_dedup": len(normalized_docs),
            "normalized_count_after_dedup": len(norm_rows),
            "raw_batch_path": str(batch_raw_path).replace("\\", "/"),
            "normalized_batch_path": str(batch_norm_path).replace("\\", "/"),
            "status": "success",
            "generated_at": iso_now(),
        }
        dump_json(batch_meta_path, batch_meta)

        state["last_status"] = "success"
        state["last_error"] = None
        state["cooldown_until"] = None
        state["last_success_at"] = iso_now()
        state["successful_batches"] = int(state.get("successful_batches", 0)) + 1
        state["successful_docs_total"] = int(state.get("successful_docs_total", 0)) + len(norm_rows)

        if args.advance_state_on_success:
            state["next_start"] = start + len(raw_rows)

        save_state(state_path, state)

        latest_report = {
            "run_ts": run_ts,
            "status": "success",
            "profile": args.profile,
            "state_path": str(state_path).replace("\\", "/"),
            "raw_count": len(raw_rows),
            "normalized_count_after_dedup": len(norm_rows),
            "next_start_after_run": state["next_start"],
            "batch_meta_path": str(batch_meta_path).replace("\\", "/"),
        }
        dump_json(reports_dir / "arxiv_incremental_latest.json", latest_report)
        dump_json(reports_dir / "history" / f"arxiv_incremental_{run_ts}.json", latest_report)

        print(f"[OK] incremental arXiv fetch succeeded")
        print(f"[OK] start={start} batch_size={batch_size}")
        print(f"[OK] raw_count={len(raw_rows)} normalized_after_dedup={len(norm_rows)}")
        print(f"[OK] next_start={state['next_start']}")
        print(f"[OK] raw batch: {batch_raw_path}")
        print(f"[OK] normalized batch: {batch_norm_path}")
        print(f"[OK] state: {state_path}")

    except Exception as exc:
        status = classify_error(exc)
        state["last_status"] = status
        state["last_error"] = repr(exc)

        if status == "rate_limited":
            set_cooldown(state, args.cooldown_minutes_on_rate_limit)
        elif status in {"timeout", "service_unavailable"}:
            set_cooldown(state, args.cooldown_minutes_on_timeout)
        elif status == "network_error":
            set_cooldown(state, args.cooldown_minutes_on_network_error)

        save_state(state_path, state)

        error_report = {
            "run_ts": run_ts,
            "status": status,
            "profile": args.profile,
            "state_path": str(state_path).replace("\\", "/"),
            "query": {
                "search_query": search_query,
                "start": start,
                "max_results": batch_size,
                "sort_by": sort_by,
                "sort_order": sort_order,
            },
            "error": repr(exc),
            "cooldown_until": state.get("cooldown_until"),
        }
        dump_json(reports_dir / "arxiv_incremental_latest.json", error_report)
        dump_json(reports_dir / "history" / f"arxiv_incremental_{run_ts}.json", error_report)

        print(f"[WARN] incremental arXiv fetch failed with status={status}")
        print(f"[WARN] error={repr(exc)}")
        if state.get("cooldown_until"):
            print(f"[WARN] cooldown_until={state['cooldown_until']}")


if __name__ == "__main__":
    main()