from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class RelevanceJudgment:
    query_id: str
    canonical_id: str
    relevance: int


@dataclass
class EvalQuery:
    query_id: str
    text: str


def load_eval_queries(path: Path) -> list[EvalQuery]:
    queries: list[EvalQuery] = []

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            queries.append(EvalQuery(**row))

    return queries


def load_qrels(path: Path) -> list[RelevanceJudgment]:
    qrels: list[RelevanceJudgment] = []

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            qrels.append(RelevanceJudgment(**row))

    return qrels


def build_qrels_map(qrels: Iterable[RelevanceJudgment]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}

    for q in qrels:
        out.setdefault(q.query_id, {})[q.canonical_id] = q.relevance

    return out


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def save_eval_queries(path: Path, queries: Iterable[EvalQuery]) -> None:
    write_jsonl(path, (asdict(q) for q in queries))


def save_qrels(path: Path, qrels: Iterable[RelevanceJudgment]) -> None:
    write_jsonl(path, (asdict(q) for q in qrels))