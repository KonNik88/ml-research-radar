from __future__ import annotations

from pathlib import Path

from scripts.validation.check_ranking_evaluation_freshness import (
    build_freshness_report,
)


def _evaluation_report(*, build_id: str = "build-a") -> dict:
    return {
        "schema_version": "ranking_evaluation_v1",
        "report_name": "ranking_evaluation",
        "runtime": {
            "ready": True,
            "backend_mode": "file",
            "build_id": build_id,
            "corpus_doc_count": 60954,
            "embedding_model_name": (
                "sentence-transformers/all-MiniLM-L6-v2"
            ),
        },
        "summary": {
            "runs_count": 612,
            "error_count": 0,
            "determinism_failure_count": 0,
        },
        "decision": {
            "recommended_outcome": "reject_heuristic_reranking",
            "automatic_public_change_allowed": False,
        },
    }


def _retrieval_manifest(*, build_id: str = "build-a") -> dict:
    return {
        "build_id": build_id,
        "corpus_doc_count": 60954,
        "embedding_model_name": (
            "sentence-transformers/all-MiniLM-L6-v2"
        ),
        "corpus_fingerprint": "fingerprint",
    }


def test_freshness_report_passes_when_build_identity_matches() -> None:
    report = build_freshness_report(
        evaluation_report=_evaluation_report(),
        retrieval_manifest=_retrieval_manifest(),
        report_path=Path("ranking.json"),
        retrieval_manifest_path=Path("latest.json"),
    )

    assert report["ok"] is True
    assert report["required_failed_count"] == 0
    assert report["required_failed_checks"] == []
    assert (
        report["checks"][
            "build_id_matches_current_retrieval_manifest"
        ]
        is True
    )


def test_freshness_report_fails_on_stale_build_id() -> None:
    report = build_freshness_report(
        evaluation_report=_evaluation_report(build_id="old-build"),
        retrieval_manifest=_retrieval_manifest(build_id="new-build"),
        report_path=Path("ranking.json"),
        retrieval_manifest_path=Path("latest.json"),
    )

    assert report["ok"] is False
    assert (
        "build_id_matches_current_retrieval_manifest"
        in report["required_failed_checks"]
    )


def test_freshness_report_fails_on_doc_count_mismatch() -> None:
    manifest = _retrieval_manifest()
    manifest["corpus_doc_count"] = 70000

    report = build_freshness_report(
        evaluation_report=_evaluation_report(),
        retrieval_manifest=manifest,
        report_path=Path("ranking.json"),
        retrieval_manifest_path=Path("latest.json"),
    )

    assert report["ok"] is False
    assert (
        "corpus_doc_count_matches_current_retrieval_manifest"
        in report["required_failed_checks"]
    )


def test_freshness_report_fails_on_model_mismatch() -> None:
    manifest = _retrieval_manifest()
    manifest["embedding_model_name"] = "different-model"

    report = build_freshness_report(
        evaluation_report=_evaluation_report(),
        retrieval_manifest=manifest,
        report_path=Path("ranking.json"),
        retrieval_manifest_path=Path("latest.json"),
    )

    assert report["ok"] is False
    assert (
        "embedding_model_matches_current_retrieval_manifest"
        in report["required_failed_checks"]
    )
