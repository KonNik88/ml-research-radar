from __future__ import annotations

import json
from pathlib import Path

from scripts.update import build_refresh_alignment_merged_snapshots as builder


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _canonical_row() -> dict[str, object]:
    return {
        "canonical_id": "paper-openalex",
        "title": "OpenAlex covered paper",
        "doi": "10.1000/openalex-covered",
        "arxiv_id": "2401.00001v1",
        "openalex_id": "https://openalex.org/W1",
        "source_ids": {
            "arxiv": "2401.00001v1",
            "openalex": "https://openalex.org/W1",
        },
        "sources": [
            {"source": "arxiv", "source_record_id": "2401.00001v1"},
            {
                "source": "openalex_alignment",
                "source_record_id": "https://openalex.org/W1",
            },
        ],
        "unique_source_count": 2,
    }


def _args(root: Path, *extra: str):
    return builder.build_parser().parse_args(
        [
            "--canonical-path",
            str(root / "data/analytics/reconciled/canonical_documents.jsonl"),
            "--normalized-root",
            str(root / "data/normalized"),
            "--reports-dir",
            str(root / "artifacts/reports"),
            "--update-dir",
            str(root / "artifacts/reports/update"),
            "--source",
            "openalex_alignment",
            *extra,
        ]
    )


def test_builder_preserves_baseline_alignment_coverage_and_writes_merge_report(
    tmp_path: Path,
) -> None:
    canonical_path = tmp_path / "data/analytics/reconciled/canonical_documents.jsonl"
    source_dir = tmp_path / "data/normalized/openalex_alignment"
    reports_dir = tmp_path / "artifacts/reports"
    update_dir = reports_dir / "update"

    base_path = source_dir / "documents.20260101T000000Z.jsonl"
    incremental_path = source_dir / "documents.20260201T000000Z.jsonl"

    _write_jsonl(canonical_path, [_canonical_row()])
    _write_jsonl(
        base_path,
        [
            {
                "doc_id": "openalex-W1",
                "source": "openalex_alignment",
                "doi": "10.1000/openalex-covered",
                "arxiv_id": "2401.00001v1",
                "openalex_id": "https://openalex.org/W1",
                "source_ids": {"openalex": "https://openalex.org/W1"},
                "title": "OpenAlex covered paper",
            }
        ],
    )
    _write_jsonl(
        incremental_path,
        [
            {
                "doc_id": "openalex-W2",
                "source": "openalex_alignment",
                "doi": "10.1000/new",
                "openalex_id": "https://openalex.org/W2",
                "source_ids": {"openalex": "https://openalex.org/W2"},
                "title": "New OpenAlex paper",
            }
        ],
    )
    _write_json(
        reports_dir / "openalex_alignment_ingest_latest.json",
        {"artifacts": {"normalized_jsonl": str(incremental_path)}},
    )

    report = builder.build_report(_args(tmp_path, "--execute"))

    assert report["verdict"]["ok"] is True
    source_result = report["source_results"][0]
    assert source_result["coverage_safe"] is True
    assert source_result["base_selection"]["selected"]["path"].endswith(
        "documents.20260101T000000Z.jsonl"
    )

    output_path = Path(source_result["output"]["path"])
    assert output_path.exists()
    assert len(_read_jsonl(output_path)) == 2

    latest_merge_report = update_dir / "merge_openalex_alignment_latest.json"
    assert latest_merge_report.exists()
    merge_report = json.loads(latest_merge_report.read_text(encoding="utf-8"))
    assert merge_report["output"]["merged_snapshot"] == source_result["output"]["path"]
    assert merge_report["stats"]["baseline_source_docs_missing_count"] == 0


def test_builder_does_not_write_merge_report_without_safe_base_coverage(
    tmp_path: Path,
) -> None:
    canonical_path = tmp_path / "data/analytics/reconciled/canonical_documents.jsonl"
    source_dir = tmp_path / "data/normalized/openalex_alignment"
    reports_dir = tmp_path / "artifacts/reports"
    update_dir = reports_dir / "update"
    incremental_path = source_dir / "documents.20260201T000000Z.jsonl"

    _write_jsonl(canonical_path, [_canonical_row()])
    _write_jsonl(
        incremental_path,
        [
            {
                "doc_id": "openalex-W2",
                "source": "openalex_alignment",
                "doi": "10.1000/new",
                "openalex_id": "https://openalex.org/W2",
            }
        ],
    )
    _write_json(
        reports_dir / "openalex_alignment_ingest_latest.json",
        {"artifacts": {"normalized_jsonl": str(incremental_path)}},
    )

    report = builder.build_report(_args(tmp_path, "--execute"))

    assert report["verdict"]["ok"] is False
    assert report["source_results"][0]["output"]["written"] is False
    assert not (update_dir / "merge_openalex_alignment_latest.json").exists()
