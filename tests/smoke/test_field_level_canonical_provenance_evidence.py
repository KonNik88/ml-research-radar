from __future__ import annotations

import hashlib
import json
from pathlib import Path

from radar_core.contracts.document import NormalizedDocument
from radar_core.normalize.reconcile import reconcile_documents
from scripts.validation.build_field_level_canonical_provenance_evidence import (
    build_package,
)
from scripts.validation.check_field_level_canonical_provenance_evidence import (
    build_report,
)



def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _source_docs() -> list[NormalizedDocument]:
    return [
        NormalizedDocument(
            doc_id="shared-doc",
            canonical_url="https://arxiv.org/abs/2401.00001v1",
            content_hash="a",
            source="arxiv",
            source_id="2401.00001v1",
            source_record_id="2401.00001v1",
            source_record_url="https://arxiv.org/abs/2401.00001v1",
            doi="10.1234/example",
            arxiv_id="2401.00001v1",
            title="Example paper",
            abstract="short",
            authors=["Alice"],
            year=2024,
            pipeline_version="test",
        ),
        NormalizedDocument(
            doc_id="shared-doc",
            canonical_url="https://openalex.org/W1",
            content_hash="b",
            source="openalex",
            source_id="https://openalex.org/W1",
            source_record_id="https://openalex.org/W1",
            source_record_url="https://openalex.org/W1",
            doi="10.1234/example",
            openalex_id="https://openalex.org/W1",
            title="Example paper extended",
            abstract="a longer abstract",
            authors=["Alice", "Bob"],
            year=2024,
            pipeline_version="test",
        ),
    ]


def _make_audit_package(tmp_path: Path) -> Path:
    root = tmp_path / "audit"
    docs = _source_docs()
    canonical = reconcile_documents(docs)[0]
    source_rows = []
    links = []
    for doc in docs:
        row = doc.model_dump(mode="json")
        row["_audit_canonical_ids"] = [canonical.canonical_id]
        source_rows.append(row)
        links.append(
            {
                "canonical_id": canonical.canonical_id,
                "source_family": doc.source,
                "source_link": next(
                    source.model_dump(mode="json")
                    for source in canonical.sources
                    if source.source == doc.source
                ),
                "matched": True,
                "resolved_doc_id": doc.doc_id,
                "match_basis": "source_record_id",
                "match_score": 90,
                "candidate_match_count": 1,
            }
        )
    _write_json(root / "manifest.json", {"package_name": "synthetic-audit"})
    _write_jsonl(
        root / "data_slice" / "canonical_documents.sample.jsonl",
        [canonical.model_dump(mode="json")],
    )
    _write_jsonl(root / "data_slice" / "source_documents.sample.jsonl", source_rows)
    _write_jsonl(root / "data_slice" / "canonical_source_links.sample.jsonl", links)
    _write_jsonl(root / "data_slice" / "unmatched_canonical_source_links.jsonl", [])
    return root

def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _rewrite_checksums(root: Path) -> None:
    filenames = [
        "field_evidence.jsonl",
        "paper_summary.jsonl",
        "data_quality_summary.json",
        "manifest.json",
        "README.md",
    ]
    lines = []
    for filename in filenames:
        digest = hashlib.sha256((root / filename).read_bytes()).hexdigest()
        lines.append(f"{digest}  {filename}")
    (root / "checksums.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _package(tmp_path: Path) -> Path:
    audit = _make_audit_package(tmp_path)
    result = build_package(
        audit_path=audit,
        output_root=tmp_path / "output",
        run_ts="20260724T130000Z",
        strict=True,
    )
    return Path(result["run_dir"])


def test_validator_accepts_valid_package(tmp_path: Path) -> None:
    root = _package(tmp_path)
    report = build_report(package_root=root)

    assert report["verdict"]["ok"] is True
    assert report["summary"]["checks_count"] >= 32
    assert report["summary"]["paper_count"] == 1
    assert report["summary"]["field_record_count"] == 61
    assert report["summary"]["required_failed_count"] == 0


def test_validator_detects_missing_field_record(tmp_path: Path) -> None:
    root = _package(tmp_path)
    path = root / "field_evidence.jsonl"
    rows = _read_jsonl(path)
    _write_jsonl(path, rows[:-1])
    _rewrite_checksums(root)

    report = build_report(package_root=root)
    assert report["verdict"]["ok"] is False
    assert report["checks"]["all_papers_cover_all_contract_fields"] is False


def test_validator_detects_duplicate_record_id(tmp_path: Path) -> None:
    root = _package(tmp_path)
    path = root / "field_evidence.jsonl"
    rows = _read_jsonl(path)
    rows[1]["record_id"] = rows[0]["record_id"]
    _write_jsonl(path, rows)
    _rewrite_checksums(root)

    report = build_report(package_root=root)
    assert report["checks"]["no_duplicate_record_ids"] is False
    assert report["checks"]["all_record_ids_deterministic"] is False


def test_validator_detects_wrong_strategy(tmp_path: Path) -> None:
    root = _package(tmp_path)
    path = root / "field_evidence.jsonl"
    rows = _read_jsonl(path)
    rows[0]["strategy_kind"] = "runtime_default"
    _write_jsonl(path, rows)
    _rewrite_checksums(root)

    report = build_report(package_root=root)
    assert report["checks"]["all_field_strategies_match_contract"] is False


def test_validator_detects_foreign_observation_id(tmp_path: Path) -> None:
    root = _package(tmp_path)
    path = root / "field_evidence.jsonl"
    rows = _read_jsonl(path)
    target = next(row for row in rows if row["field_name"] == "title")
    target["selected_source_observation_ids"].append("foreign-observation")
    _write_jsonl(path, rows)
    _rewrite_checksums(root)

    report = build_report(package_root=root)
    assert report["checks"]["all_observation_ids_are_contributing"] is False


def test_validator_detects_value_mismatch(tmp_path: Path) -> None:
    root = _package(tmp_path)
    path = root / "field_evidence.jsonl"
    rows = _read_jsonl(path)
    target = next(row for row in rows if row["field_name"] == "title")
    target["recomputed_value"] = "tampered"
    _write_jsonl(path, rows)
    _rewrite_checksums(root)

    report = build_report(package_root=root)
    assert report["checks"]["all_source_reconstructable_values_match"] is False
    assert report["summary"]["value_mismatch_count"] == 1


def test_validator_detects_checksum_tampering(tmp_path: Path) -> None:
    root = _package(tmp_path)
    with (root / "README.md").open("a", encoding="utf-8") as handle:
        handle.write("tampered\n")

    report = build_report(package_root=root)
    assert report["checks"]["all_checksums_match"] is False
    assert report["summary"]["checksum_mismatch_count"] == 1


def test_validator_detects_invalid_runtime_default_semantics(tmp_path: Path) -> None:
    root = _package(tmp_path)
    path = root / "field_evidence.jsonl"
    rows = _read_jsonl(path)
    target = next(row for row in rows if row["field_name"] == "created_at")
    target["comparison_status"] = "match"
    target["selected_source_observation_ids"] = ["foreign-observation"]
    _write_jsonl(path, rows)
    _rewrite_checksums(root)

    report = build_report(package_root=root)
    assert report["checks"]["runtime_default_semantics_valid"] is False


def test_validator_detects_manifest_count_drift(tmp_path: Path) -> None:
    root = _package(tmp_path)
    path = root / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["counts"]["field_evidence_record_count"] = 999
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _rewrite_checksums(root)

    report = build_report(package_root=root)
    assert report["checks"]["manifest_field_record_count_matches"] is False
