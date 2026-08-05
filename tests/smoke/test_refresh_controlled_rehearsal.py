from __future__ import annotations

from pathlib import Path

import pytest

from scripts.update import run_refresh_pipeline_v1 as pipeline


def _args(*items: str):
    args = pipeline.build_parser().parse_args(list(items))
    pipeline.apply_rehearsal_defaults(args)
    return args


def test_candidate_rehearsal_defaults_to_candidate_audit_stop() -> None:
    args = _args("--candidate-rehearsal")

    assert args.stop_after == "candidate_provenance_audit"


def test_candidate_rehearsal_uses_rehearsal_candidate_prefix() -> None:
    args = _args("--candidate-rehearsal")

    candidate_path = pipeline.resolve_candidate_path(args, "20260804T120000Z")

    assert candidate_path == Path(
        "data/analytics/reconciled/"
        "canonical_documents.rehearsal_candidate.20260804T120000Z.jsonl"
    )


def test_candidate_rehearsal_execute_plan_stops_before_promotion() -> None:
    args = _args("--candidate-rehearsal", "--execute")

    enabled_steps = [
        step_name
        for step_name in pipeline.STEP_ORDER
        if pipeline.step_enabled(step_name, args)[0]
    ]

    assert enabled_steps == [
        "refresh_preflight",
        "reconcile_candidate",
        "candidate_provenance_audit",
    ]
    assert "promote_candidate" not in enabled_steps
    assert "export_postgres" not in enabled_steps
    assert "rebuild_retrieval" not in enabled_steps
    assert "dod_check" not in enabled_steps


def test_candidate_rehearsal_rejects_downstream_flags() -> None:
    with pytest.raises(SystemExit):
        _args("--candidate-rehearsal", "--require-artifacts")

    with pytest.raises(SystemExit):
        _args("--candidate-rehearsal", "--require-streamlit-discovery-ui")


def test_candidate_rehearsal_rejects_skip_preflight() -> None:
    with pytest.raises(SystemExit):
        _args("--candidate-rehearsal", "--skip-refresh-preflight")


def test_candidate_rehearsal_rejects_stop_after_promotion() -> None:
    with pytest.raises(SystemExit):
        _args("--candidate-rehearsal", "--stop-after", "promote_candidate")
