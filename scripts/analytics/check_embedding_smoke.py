from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


DEFAULT_EMBEDDINGS_LATEST = Path("artifacts/embeddings/abstract/latest.json")
DEFAULT_CANONICAL_PATH = Path("data/analytics/reconciled/canonical_documents.jsonl")
DEFAULT_REPORTS_DIR = Path("artifacts/reports/analytics")


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


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def load_canonical_map(path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in iter_jsonl(path):
        cid = row.get("canonical_id")
        if cid:
            out[str(cid)] = row
    return out


def cosine_top_k(
    query_vec: np.ndarray,
    matrix: np.ndarray,
    top_k: int,
) -> tuple[np.ndarray, np.ndarray]:
    scores = matrix @ query_vec
    if top_k >= len(scores):
        top_idx = np.argsort(-scores)
    else:
        part = np.argpartition(-scores, top_k)[:top_k]
        top_idx = part[np.argsort(-scores[part])]
    return top_idx, scores[top_idx]


def build_seed_ids(
    ids: list[str],
    canonical_map: dict[str, dict[str, Any]],
    explicit_ids: list[str] | None,
    sample_size: int,
) -> list[str]:
    if explicit_ids:
        valid = [x for x in explicit_ids if x in canonical_map]
        if not valid:
            raise ValueError("None of the provided seed canonical_ids were found in canonical corpus.")
        return valid

    selected: list[str] = []
    for cid in ids:
        row = canonical_map.get(cid)
        if not row:
            continue
        title = str(row.get("title") or "").strip()
        abstract = str(row.get("abstract") or "").strip()
        year = row.get("year")
        if title and abstract and year is not None:
            selected.append(cid)
        if len(selected) >= sample_size:
            break

    if not selected:
        raise RuntimeError("Failed to auto-select seed documents.")
    return selected


def shorten(text: str, max_len: int = 180) -> str:
    text = " ".join((text or "").split()).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def build_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Embedding smoke check")
    lines.append("")
    lines.append(f"- Generated at: {report['generated_at_utc']}")
    lines.append(f"- Run ts: `{report['run_ts']}`")
    lines.append(f"- Embeddings latest: `{report['inputs']['embeddings_latest']}`")
    lines.append(f"- Canonical path: `{report['inputs']['canonical_path']}`")
    lines.append("")
    lines.append("## Embedding artifact summary")
    for k, v in report["artifact_summary"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")
    lines.append("## Consistency checks")
    for k, v in report["checks"].items():
        lines.append(f"- {k}: `{v}`")
    lines.append("")

    for seed in report["seed_results"]:
        lines.append(f"## Seed: {seed['seed_canonical_id']}")
        lines.append(f"- title: {seed['seed_title']}")
        lines.append(f"- year: {seed['seed_year']}")
        lines.append(f"- top_neighbor_count: {seed['top_neighbor_count']}")
        lines.append("")
        lines.append("### Nearest neighbors")
        for item in seed["neighbors"]:
            lines.append(
                f"- score={item['score']:.4f} | canonical_id={item['canonical_id']} | "
                f"year={item['year']} | title={item['title']}"
            )
        lines.append("")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Smoke-check abstract embedding artifacts by inspecting nearest neighbors."
    )
    parser.add_argument("--embeddings-latest", type=Path, default=DEFAULT_EMBEDDINGS_LATEST)
    parser.add_argument("--canonical-path", type=Path, default=DEFAULT_CANONICAL_PATH)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument(
        "--seed-id",
        action="append",
        default=None,
        help="Explicit canonical_id to inspect. Can be passed multiple times.",
    )
    parser.add_argument("--sample-seeds", type=int, default=3)
    parser.add_argument("--top-k", type=int, default=10)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_ts = utc_now_ts()

    latest = load_json(args.embeddings_latest)
    embeddings_path = Path(latest["embeddings_path"])
    ids_path = Path(latest["ids_path"])

    embeddings = np.load(embeddings_path)
    ids_payload = load_json(ids_path)
    ids = ids_payload["ids"]

    canonical_map = load_canonical_map(args.canonical_path)

    checks = {
        "ids_count_matches_embeddings_rows": len(ids) == int(embeddings.shape[0]),
        "embedding_dim_matches_latest": int(embeddings.shape[1]) == int(latest["embedding_dim"]),
        "latest_count_matches_ids_count": int(latest["count"]) == len(ids),
        "all_ids_found_in_canonical": all(cid in canonical_map for cid in ids),
    }

    seed_ids = build_seed_ids(
        ids=ids,
        canonical_map=canonical_map,
        explicit_ids=args.seed_id,
        sample_size=args.sample_seeds,
    )

    id_to_index = {cid: i for i, cid in enumerate(ids)}
    seed_results: list[dict[str, Any]] = []

    for seed_id in seed_ids:
        seed_idx = id_to_index[seed_id]
        seed_vec = embeddings[seed_idx]

        # ask for top_k + 1 because the first hit is usually the seed itself
        top_idx, top_scores = cosine_top_k(seed_vec, embeddings, top_k=args.top_k + 1)

        neighbors: list[dict[str, Any]] = []
        for idx, score in zip(top_idx.tolist(), top_scores.tolist()):
            cid = ids[idx]
            if cid == seed_id:
                continue

            row = canonical_map.get(cid, {})
            neighbors.append(
                {
                    "canonical_id": cid,
                    "score": float(score),
                    "title": shorten(str(row.get("title") or "")),
                    "year": row.get("year"),
                    "doi": row.get("doi"),
                    "categories": row.get("categories") or [],
                }
            )

            if len(neighbors) >= args.top_k:
                break

        seed_row = canonical_map[seed_id]
        seed_results.append(
            {
                "seed_canonical_id": seed_id,
                "seed_title": str(seed_row.get("title") or ""),
                "seed_year": seed_row.get("year"),
                "top_neighbor_count": len(neighbors),
                "neighbors": neighbors,
            }
        )

    report = {
        "report_name": "check_embedding_smoke",
        "generated_at_utc": utc_now_iso(),
        "run_ts": run_ts,
        "inputs": {
            "embeddings_latest": str(args.embeddings_latest).replace("\\", "/"),
            "canonical_path": str(args.canonical_path).replace("\\", "/"),
            "top_k": args.top_k,
            "seed_ids": seed_ids,
        },
        "artifact_summary": {
            "model_name": latest["model_name"],
            "text_builder": latest["text_builder"],
            "normalize_embeddings": latest["normalize_embeddings"],
            "count": latest["count"],
            "embedding_dim": latest["embedding_dim"],
            "embeddings_path": latest["embeddings_path"],
            "ids_path": latest["ids_path"],
        },
        "checks": checks,
        "seed_results": seed_results,
    }

    latest_json = args.reports_dir / "check_embedding_smoke_latest.json"
    latest_md = args.reports_dir / "check_embedding_smoke_latest.md"
    hist_json = args.reports_dir / "history" / f"check_embedding_smoke_{run_ts}.json"
    hist_md = args.reports_dir / "history" / f"check_embedding_smoke_{run_ts}.md"

    dump_json(latest_json, report)
    dump_text(latest_md, build_markdown(report))
    dump_json(hist_json, report)
    dump_text(hist_md, build_markdown(report))

    print(f"[OK] model_name={latest['model_name']}")
    print(f"[OK] normalize_embeddings={latest['normalize_embeddings']}")
    print(f"[OK] count={latest['count']}")
    print(f"[OK] embedding_dim={latest['embedding_dim']}")
    print(f"[OK] seed_ids={seed_ids}")
    for seed in seed_results:
        print(f"[OK] seed={seed['seed_canonical_id']} neighbors={seed['top_neighbor_count']}")
        for item in seed["neighbors"][:5]:
            print(f"    score={item['score']:.4f} | year={item['year']} | title={item['title']}")
    print(f"[OK] latest_json={latest_json}")
    print(f"[OK] latest_md={latest_md}")


if __name__ == "__main__":
    main()