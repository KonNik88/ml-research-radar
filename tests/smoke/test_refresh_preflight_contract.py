from __future__ import annotations

import json
from pathlib import Path

from scripts.validation import check_refresh_preflight_contract as preflight


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _sample_canonical_rows() -> list[dict[str, object]]:
    return [
        {
            "canonical_id": "paper-1",
            "title": "First paper",
            "doi": "10.1000/first",
            "unique_source_count": 2,
        },
        {
            "canonical_id": "paper-2",
            "title": "Second paper",
            "doi": None,
            "unique_source_count": 1,
        },
    ]


def _create_sample_project(tmp_path: Path) -> dict[str, Path]:
    canonical_path = tmp_path / "data/analytics/reconciled/canonical_documents.jsonl"
    candidate_path = (
        tmp_path / "data/analytics/reconciled/canonical_documents.candidate.jsonl"
    )
    normalized_root = tmp_path / "data/normalized"
    update_dir = tmp_path / "artifacts/reports/update"
    validation_dir = tmp_path / "artifacts/reports/validation"

    arxiv_path = normalized_root / "arxiv/documents.20260404T161108Z.jsonl"
    _write_jsonl(canonical_path, _sample_canonical_rows())
    _write_jsonl(
        arxiv_path,
        [
            {"id": "2501.00001", "title": "arxiv one"},
            {"id": "2501.00002", "title": "arxiv two"},
        ],
    )

    manifest_path = tmp_path / "artifacts/retrieval/manifests/latest.json"
    _write_json(
        manifest_path,
        {
            "build_id": "retrieval-build-1",
            "corpus_doc_count": 2,
            "corpus_path": str(canonical_path).replace("\\", "/"),
            "lexical_index_path": "artifacts/retrieval/indexes/lexical.json",
            "dense_embeddings_path": "artifacts/retrieval/indexes/dense.npy",
            "embedding_model_name": "all-MiniLM-L6-v2",
        },
    )

    retrieval_checks_path = validation_dir / "retrieval_checks_latest.json"
    _write_json(
        retrieval_checks_path,
        {
            "report_name": "retrieval_checks",
            "build_id": "retrieval-build-1",
            "corpus_doc_count": 2,
            "query_runs": [{"query": "transformer", "runs": []}],
        },
    )

    postpass_audit_path = validation_dir / "postpass_audit_summary_latest.json"
    _write_json(
        postpass_audit_path,
        {
            "report_name": "postpass_audit",
            "summary": {
                "total_docs": 2,
                "merge_stats": {"multi_source_docs": 1},
            },
        },
    )

    canonical_contract_path = validation_dir / "canonical_contract_latest.json"
    _write_json(
        canonical_contract_path,
        {
            "report_name": "canonical_contract",
            "summary": {
                "rows_count": 2,
                "bad_rows_count": 0,
            },
            "verdict": {
                "ok": True,
                "required_failed_count": 0,
                "required_failed_checks": [],
            },
        },
    )

    known_issues_path = validation_dir / "known_issues_snapshot_latest.json"
    _write_json(
        known_issues_path,
        {
            "report_name": "known_issues_snapshot",
            "summary": {
                "canonical_corpus_doc_count": 2,
                "retrieval_build_id": "retrieval-build-1",
            },
        },
    )

    refresh_cycle_path = update_dir / "run_incremental_refresh_cycle_latest.json"
    _write_json(
        refresh_cycle_path,
        {
            "report_name": "run_incremental_refresh_cycle",
            "readiness_summary": {
                "ready_for_reconcile_candidate": True,
                "has_any_enrichment_hits": True,
                "total_found_rows_across_sources": 3,
            },
            "execution_summary": {
                "all_successful": True,
                "failed_count": 0,
            },
        },
    )

    for source_name in [
        "openalex_alignment",
        "semantic_scholar_alignment",
        "crossref_alignment",
    ]:
        snapshot_path = (
            normalized_root / source_name / "documents.20260404T161108Z.jsonl"
        )
        _write_jsonl(snapshot_path, [{"id": f"{source_name}-1"}])
        _write_json(
            update_dir / f"merge_{source_name}_latest.json",
            {
                "source_name": source_name,
                "output": {
                    "merged_snapshot": str(snapshot_path).replace("\\", "/"),
                },
            },
        )

    docs_path = tmp_path / "docs/refresh_contract_v1.md"
    _write_text(
        docs_path,
        "\n".join(
            [
                "Manual refresh flow",
                "run_refresh_pipeline_v1",
                "run_incremental_reconcile_stage",
                "merged full snapshots",
                "check_refresh_preflight_contract",
                "refresh_preflight_contract_v0.1",
                "Controlled refresh rehearsal",
            ]
        ),
    )

    pipeline_path = tmp_path / "scripts/update/run_refresh_pipeline_v1.py"
    _write_text(
        pipeline_path,
        "\n".join(
            [
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
        ),
    )

    reconcile_stage_path = tmp_path / "scripts/update/run_incremental_reconcile_stage.py"
    _write_text(
        reconcile_stage_path,
        '\n'.join(
            [
                'reconcile_input_mode = "merged_full_inputs"',
                "latest-only reconcile is intentionally forbidden",
                "merge_reports_resolved_ok",
                "safe_to_execute",
            ]
        ),
    )

    promote_path = tmp_path / "scripts/update/promote_canonical_candidate.py"
    _write_text(
        promote_path,
        "\n".join(
            [
                "backup_before_promotion",
                "shutil.copy2(latest_path, backup_path)",
                "shutil.copy2(candidate_path, latest_path)",
            ]
        ),
    )

    return {
        "canonical_path": canonical_path,
        "candidate_path": candidate_path,
        "normalized_root": normalized_root,
        "update_dir": update_dir,
        "manifest_path": manifest_path,
        "retrieval_checks_path": retrieval_checks_path,
        "postpass_audit_path": postpass_audit_path,
        "canonical_contract_path": canonical_contract_path,
        "known_issues_path": known_issues_path,
        "refresh_cycle_path": refresh_cycle_path,
        "refresh_contract_path": docs_path,
        "pipeline_path": pipeline_path,
        "reconcile_stage_path": reconcile_stage_path,
        "promote_path": promote_path,
    }


def _args(paths: dict[str, Path], *extra: str):
    return preflight.build_parser().parse_args(
        [
            "--canonical-path",
            str(paths["canonical_path"]),
            "--candidate-path",
            str(paths["candidate_path"]),
            "--normalized-root",
            str(paths["normalized_root"]),
            "--update-dir",
            str(paths["update_dir"]),
            "--manifest-path",
            str(paths["manifest_path"]),
            "--retrieval-checks-path",
            str(paths["retrieval_checks_path"]),
            "--postpass-audit-path",
            str(paths["postpass_audit_path"]),
            "--canonical-contract-path",
            str(paths["canonical_contract_path"]),
            "--known-issues-path",
            str(paths["known_issues_path"]),
            "--refresh-cycle-report-path",
            str(paths["refresh_cycle_path"]),
            "--refresh-contract-path",
            str(paths["refresh_contract_path"]),
            "--pipeline-script-path",
            str(paths["pipeline_path"]),
            "--reconcile-stage-script-path",
            str(paths["reconcile_stage_path"]),
            "--promote-script-path",
            str(paths["promote_path"]),
            *extra,
        ]
    )


def test_refresh_preflight_passes_with_required_refresh_inputs(tmp_path: Path) -> None:
    paths = _create_sample_project(tmp_path)

    report = preflight.build_report(
        _args(
            paths,
            "--require-known-issues",
            "--require-merged-inputs",
            "--require-refresh-cycle-report",
        )
    )

    assert report["schema_version"] == preflight.SCHEMA_VERSION
    assert report["verdict"]["ok"] is True
    assert report["verdict"]["required_failed_count"] == 0
    assert report["checks"]["merge_reports_all_exist"] is True
    assert report["checks"]["refresh_cycle_ready_for_reconcile_candidate"] is True


def test_refresh_preflight_fails_on_manifest_doc_count_mismatch(
    tmp_path: Path,
) -> None:
    paths = _create_sample_project(tmp_path)
    _write_json(
        paths["manifest_path"],
        {
            "build_id": "retrieval-build-1",
            "corpus_doc_count": 3,
            "corpus_path": str(paths["canonical_path"]).replace("\\", "/"),
            "lexical_index_path": "artifacts/retrieval/indexes/lexical.json",
            "dense_embeddings_path": "artifacts/retrieval/indexes/dense.npy",
        },
    )

    report = preflight.build_report(_args(paths))

    assert report["verdict"]["ok"] is False
    assert "manifest_doc_count_matches_canonical" in report["verdict"][
        "required_failed_checks"
    ]


def test_refresh_preflight_requires_candidate_not_to_overwrite_latest(
    tmp_path: Path,
) -> None:
    paths = _create_sample_project(tmp_path)
    paths["candidate_path"] = paths["canonical_path"]

    report = preflight.build_report(_args(paths))

    assert report["checks"]["candidate_path_differs_from_canonical"] is False
    assert "candidate_path_differs_from_canonical" in report["verdict"][
        "required_failed_checks"
    ]


def test_refresh_preflight_can_gate_missing_merged_inputs(tmp_path: Path) -> None:
    paths = _create_sample_project(tmp_path)
    (paths["update_dir"] / "merge_crossref_alignment_latest.json").unlink()

    report = preflight.build_report(_args(paths, "--require-merged-inputs"))

    assert report["checks"]["merge_reports_all_exist"] is False
    assert "merge_reports_all_exist" in report["verdict"]["required_failed_checks"]
