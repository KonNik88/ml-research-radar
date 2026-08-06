from __future__ import annotations

from pathlib import Path

from scripts.update import run_refresh_pipeline_v1 as pipeline


def _args(*items: str):
    return pipeline.build_parser().parse_args(list(items))


def test_refresh_preflight_is_first_pipeline_step() -> None:
    assert pipeline.STEP_ORDER[0] == "refresh_preflight"
    assert pipeline.STEP_ORDER.index("refresh_preflight") < pipeline.STEP_ORDER.index(
        "reconcile_candidate"
    )
    assert pipeline.STEP_ORDER.index("candidate_provenance_audit") < (
        pipeline.STEP_ORDER.index("candidate_delta_review")
    )
    assert pipeline.STEP_ORDER.index("candidate_delta_review") < pipeline.STEP_ORDER.index(
        "promote_candidate"
    )


def test_execute_pipeline_preflight_cmd_uses_full_gate_by_default() -> None:
    args = _args("--execute")
    cmd = pipeline.build_refresh_preflight_cmd(
        args,
        Path("data/analytics/reconciled/canonical_documents.pipeline_candidate.test.jsonl"),
    )

    assert cmd[:3] == [
        pipeline.sys.executable,
        "-m",
        "scripts.validation.check_refresh_preflight_contract",
    ]
    assert "--strict" in cmd
    assert "--require-known-issues" in cmd
    assert "--require-merged-inputs" in cmd
    assert "--require-refresh-cycle-report" in cmd
    assert "--candidate-path" in cmd
    assert "--check-db" in cmd


def test_candidate_only_pipeline_preflight_does_not_require_db() -> None:
    args = _args("--execute", "--stop-after", "candidate_delta_review")
    cmd = pipeline.build_refresh_preflight_cmd(
        args,
        Path("data/analytics/reconciled/canonical_documents.pipeline_candidate.test.jsonl"),
    )

    assert "--check-db" not in cmd


def test_stop_after_preflight_excludes_downstream_steps() -> None:
    args = _args("--execute", "--stop-after", "refresh_preflight")

    preflight_enabled, _ = pipeline.step_enabled("refresh_preflight", args)
    reconcile_enabled, reconcile_reason = pipeline.step_enabled("reconcile_candidate", args)

    assert preflight_enabled is True
    assert reconcile_enabled is False
    assert reconcile_reason == "Excluded because stop-after=refresh_preflight"


def test_explicit_skip_preflight_keeps_downstream_debug_path_available() -> None:
    args = _args("--execute", "--skip-refresh-preflight")

    preflight_enabled, preflight_reason = pipeline.step_enabled("refresh_preflight", args)
    reconcile_enabled, _ = pipeline.step_enabled("reconcile_candidate", args)

    assert preflight_enabled is False
    assert preflight_reason == "Refresh preflight skipped by --skip-refresh-preflight"
    assert reconcile_enabled is True
