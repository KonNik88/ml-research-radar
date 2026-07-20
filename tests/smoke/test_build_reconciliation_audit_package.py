from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

from scripts.validation import build_reconciliation_audit_package as audit_package


FIXED_TS = "20260720T120000Z"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _source_row(source: str, index: int) -> dict:
    if source == "arxiv":
        source_record_id = f"2401.{index:05d}"
        canonical_url = f"https://arxiv.org/abs/{source_record_id}"
        return {
            "source": "arxiv",
            "doc_id": f"arxiv-doc-{index}",
            "source_id": source_record_id,
            "source_record_id": source_record_id,
            "source_record_url": canonical_url,
            "canonical_url": canonical_url,
            "title": f"Synthetic paper {index}",
            "year": 2024,
        }

    source_record_id = f"s2-paper-{index:02d}"
    canonical_url = f"https://www.semanticscholar.org/paper/{source_record_id}"
    return {
        "source": "semantic_scholar",
        "doc_id": f"s2-doc-{index}",
        "source_id": source_record_id,
        "source_record_id": source_record_id,
        "source_record_url": canonical_url,
        "canonical_url": canonical_url,
        "title": f"Synthetic paper {index}",
        "year": 2024,
    }


def _make_project(tmp_path: Path, *, omit_required_report: bool = False) -> Path:
    root = tmp_path / "repo"
    canonical_rows: list[dict] = []
    arxiv_rows: list[dict] = []
    s2_rows: list[dict] = []

    for index in range(10):
        arxiv = _source_row("arxiv", index)
        s2 = _source_row("semantic_scholar", index)
        arxiv_rows.append(arxiv)
        s2_rows.append(s2)

        canonical_rows.append(
            {
                "canonical_id": f"paper-{index:02d}",
                "reconciliation_key": f"doi::10.1234/example.{index}",
                "title": f"Synthetic paper {index}",
                "year": 2024,
                "doi": f"10.1234/example.{index}",
                "arxiv_id": arxiv["source_record_id"],
                "source_count": 2,
                "unique_source_count": 2,
                "metadata_completeness_score": 0.8,
                "doc_ids": [arxiv["doc_id"], s2["doc_id"]],
                "sources": [
                    {
                        key: arxiv.get(key)
                        for key in (
                            "source",
                            "doc_id",
                            "source_id",
                            "source_record_id",
                            "source_record_url",
                            "canonical_url",
                        )
                    },
                    {
                        key: s2.get(key)
                        for key in (
                            "source",
                            "doc_id",
                            "source_id",
                            "source_record_id",
                            "source_record_url",
                            "canonical_url",
                        )
                    },
                ],
            }
        )

    canonical_path = (
        root / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"
    )
    _write_jsonl(canonical_path, canonical_rows)
    _write_jsonl(
        root
        / "data"
        / "normalized"
        / "arxiv"
        / "documents.20260720T110000Z.jsonl",
        arxiv_rows,
    )
    _write_jsonl(
        root
        / "data"
        / "normalized"
        / "semantic_scholar_alignment"
        / "documents.20260720T110000Z.jsonl",
        s2_rows,
    )

    reports = root / "artifacts" / "reports" / "validation"
    _write_json(reports / "canonical_contract_latest.json", {"ok": True})
    _write_json(
        reports / "canonical_provenance_consistency_latest.json",
        {"ok": True},
    )
    if not omit_required_report:
        _write_json(reports / "postpass_audit_summary_latest.json", {"ok": True})

    return root


def test_builds_private_bounded_zip_without_optional_db_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _make_project(tmp_path)
    output_dir = root / "artifacts" / "audit-test"
    canonical_path = (
        root / "data" / "analytics" / "reconciled" / "canonical_documents.jsonl"
    )
    canonical_before = canonical_path.read_bytes()

    monkeypatch.setattr(audit_package, "utc_ts", lambda: FIXED_TS)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_reconciliation_audit_package.py",
            "--project-root",
            str(root),
            "--output-dir",
            str(output_dir),
            "--strict-reports",
            "--max-papers",
            "10",
            "--semantic-scholar-min",
            "6",
        ],
    )

    assert audit_package.main() == 0

    zip_path = (
        output_dir
        / f"reconciliation_evidence_audit_v0.1_{FIXED_TS}.zip"
    )
    assert zip_path.is_file()
    assert canonical_path.read_bytes() == canonical_before

    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
        prefix = f"reconciliation_evidence_audit_v0.1_{FIXED_TS}/"
        manifest = json.loads(archive.read(prefix + "manifest.json"))
        source_links = archive.read(
            prefix + "data_slice/canonical_source_links.sample.jsonl"
        ).decode("utf-8").splitlines()

        assert prefix + "data_slice/canonical_documents.sample.jsonl" in names
        assert prefix + "data_slice/arxiv.sample.jsonl" in names
        assert prefix + "data_slice/semantic_scholar_alignment.sample.jsonl" in names
        assert prefix + "data_slice/source_documents.sample.jsonl" in names
        assert prefix + "data_slice/unmatched_canonical_source_links.jsonl" in names
        assert prefix + "checksums.txt" in names

        assert not any(
            name.endswith("documents.20260720T110000Z.jsonl")
            for name in names
        )
        assert manifest["status"] == "internal_review_only"
        assert manifest["canonical_truth"] is False
        assert manifest["may_be_used_as_reconcile_input"] is False
        assert manifest["publication_ready"] is False
        assert manifest["safety"]["mutate_postgres"] is False
        assert (
            manifest["safety"][
                "semantic_scholar_rows_private_diagnostic_only"
            ]
            is True
        )
        assert manifest["selection"]["selected_paper_count"] == 10
        assert (
            manifest["source_evidence"][
                "unmatched_canonical_source_link_count"
            ]
            == 0
        )
        assert len(source_links) == 20

        missing = {
            item["label"]: item["required"]
            for item in manifest["reports"]["missing"]
        }
        assert missing["db_read"] is False


def test_strict_mode_fails_when_required_report_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _make_project(tmp_path, omit_required_report=True)

    monkeypatch.setattr(audit_package, "utc_ts", lambda: FIXED_TS)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_reconciliation_audit_package.py",
            "--project-root",
            str(root),
            "--output-dir",
            str(root / "artifacts" / "audit-test"),
            "--strict-reports",
            "--max-papers",
            "10",
            "--semantic-scholar-min",
            "6",
        ],
    )

    with pytest.raises(RuntimeError, match="postpass_audit_summary"):
        audit_package.main()


def test_invalid_sample_arguments_fail_before_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _make_project(tmp_path)
    output_dir = root / "artifacts" / "audit-test"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_reconciliation_audit_package.py",
            "--project-root",
            str(root),
            "--output-dir",
            str(output_dir),
            "--max-papers",
            "9",
        ],
    )

    with pytest.raises(ValueError, match="between 10 and 50"):
        audit_package.main()

    assert not output_dir.exists()
