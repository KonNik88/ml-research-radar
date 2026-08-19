from __future__ import annotations

import json
from pathlib import Path

from scripts.update import check_refresh_definition_of_done as dod
from scripts.update import run_refresh_operational_flow as flow


def _args(*items: str):
    return flow.normalize_args(flow.build_parser().parse_args(list(items)))


def _ok_runner(calls: list[str]):
    def run(step: flow.StepSpec, _: int) -> dict[str, object]:
        calls.append(step.name)
        return {
            "name": step.name,
            "phase": step.phase,
            "returncode": 0,
            "duration_seconds": 0.01,
            "stdout_tail": "",
            "stderr_tail": "",
            "ok": True,
        }

    return run


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _promotion_state(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    canonical_dir = tmp_path / "data/analytics/reconciled"
    update_dir = tmp_path / "artifacts/reports/update"
    validation_dir = tmp_path / "artifacts/reports/validation"
    candidate_path = canonical_dir / "candidate.jsonl"
    candidate_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_path.write_text('{"canonical_id":"paper-a"}\n', encoding="utf-8")

    readiness_path = validation_dir / "refresh_promotion_readiness_latest.json"
    _write_json(
        readiness_path,
        {
            "summary": {"candidate_path": str(candidate_path)},
            "verdict": {
                "ok": True,
                "promotion_ready": True,
                "required_failed_count": 0,
            },
        },
    )
    _write_json(
        update_dir / "run_refresh_controlled_promotion_latest.json",
        {
            "mode": "dry_run",
            "summary": {"candidate_path": str(candidate_path)},
            "verdict": {
                "ok": True,
                "safe_to_execute": True,
                "controlled_promotion_complete": False,
                "canonical_latest_mutated": False,
            },
        },
    )
    return canonical_dir, update_dir, validation_dir, candidate_path


def test_public_phase_contract_is_stable() -> None:
    assert flow.PUBLIC_PHASES == (
        "preflight",
        "candidate",
        "promote",
        "core-derived",
        "postgres",
        "discovery-derived",
        "full",
    )


def test_bounded_tail_respects_zero_and_positive_limits() -> None:
    assert flow.bounded_tail("abcdef", 0) == ""
    assert flow.bounded_tail("abcdef", 3) == "def"


def test_preflight_builds_alignment_inputs_before_strict_contract() -> None:
    args = _args("--phase", "preflight", "--execute")
    steps = flow.build_phase_plan(args)

    assert [step.name for step in steps] == [
        "build_alignment_merged_snapshots",
        "check_refresh_preflight_contract",
    ]
    assert "--execute" in steps[0].command
    assert "--strict" in steps[0].command
    assert "--require-merged-inputs" in steps[1].command
    assert "--require-refresh-cycle-report" in steps[1].command


def test_preflight_plan_does_not_mark_alignment_builder_for_execute() -> None:
    args = _args("--phase", "preflight")
    steps = flow.build_phase_plan(args)

    assert "--execute" not in steps[0].command


def test_candidate_phase_uses_lower_level_rehearsal_and_never_promotes() -> None:
    args = _args("--phase", "candidate", "--execute")
    steps = flow.build_phase_plan(args)
    commands = [" ".join(step.command) for step in steps]

    assert [step.name for step in steps] == [
        "run_candidate_rehearsal",
        "check_refresh_alignment_coverage",
        "check_refresh_source_coverage",
        "check_refresh_promotion_readiness",
    ]
    assert "--candidate-rehearsal" in steps[0].command
    assert "--strict" in steps[0].command
    assert "--execute" in steps[0].command
    assert not any("promote_canonical_candidate" in command for command in commands)
    assert not any("run_refresh_controlled_promotion" in command for command in commands)


def test_refresh_input_overrides_are_forwarded_to_rehearsal() -> None:
    args = _args(
        "--phase",
        "candidate",
        "--execute",
        "--arxiv-input",
        "arxiv.jsonl",
        "--acl-input",
        "acl.jsonl",
        "--merge-report",
        "openalex_alignment=openalex.json",
    )
    command = flow.build_phase_plan(args)[0].command

    assert "--arxiv-input" in command
    assert "arxiv.jsonl" in command
    assert "--acl-input" in command
    assert "acl.jsonl" in command
    assert "openalex_alignment=openalex.json" in command


def test_promote_phase_owns_only_controlled_promotion() -> None:
    dry_args = _args("--phase", "promote")
    execute_args = _args("--phase", "promote", "--execute")
    dry_step = flow.build_phase_plan(dry_args)[0]
    execute_step = flow.build_phase_plan(execute_args)[0]

    assert "scripts.update.run_refresh_controlled_promotion" in dry_step.command
    assert "scripts.update.promote_canonical_candidate" not in dry_step.command
    assert "--execute" not in dry_step.command
    assert "--execute" in execute_step.command
    assert "--strict" in execute_step.command


def test_promote_without_execute_runs_real_controlled_dry_run() -> None:
    calls: list[str] = []
    args = _args("--phase", "promote")

    report = flow.build_report(args, runner=_ok_runner(calls))

    assert calls == ["dry_run_controlled_promotion"]
    assert report["mode"] == "promotion_dry_run"
    assert report["verdict"]["ok"] is True
    assert report["verdict"]["phase_complete"] is True
    assert report["mutation_policy"]["canonical_mutation_allowed"] is False


def test_promote_execute_requires_a_fresh_matching_dry_run(tmp_path: Path) -> None:
    canonical_dir, update_dir, validation_dir, candidate_path = _promotion_state(tmp_path)
    calls: list[str] = []
    args = _args(
        "--phase",
        "promote",
        "--execute",
        "--canonical-dir",
        str(canonical_dir),
        "--update-dir",
        str(update_dir),
        "--validation-dir",
        str(validation_dir),
        "--candidate-path",
        str(candidate_path),
    )

    report = flow.build_report(args, runner=_ok_runner(calls))

    assert calls == ["execute_controlled_promotion"]
    assert report["verdict"]["ok"] is True
    assert report["verdict"]["phase_complete"] is True
    assert all(item["ok"] for item in report["execution_prechecks"])
    assert report["mutation_policy"]["canonical_mutation_allowed"] is True


def test_promote_execute_blocks_missing_dry_run(tmp_path: Path) -> None:
    validation_dir = tmp_path / "artifacts/reports/validation"
    update_dir = tmp_path / "artifacts/reports/update"
    calls: list[str] = []
    args = _args(
        "--phase",
        "promote",
        "--execute",
        "--update-dir",
        str(update_dir),
        "--validation-dir",
        str(validation_dir),
    )

    report = flow.build_report(args, runner=_ok_runner(calls))

    assert calls == []
    assert report["verdict"]["ok"] is False
    assert report["verdict"]["required_failed_count"] > 0
    assert any(
        "controlled_promotion_dry_run_report_exists" in name
        for name in report["verdict"]["required_failed_checks"]
    )


def test_full_execute_is_fail_closed_in_v0_1() -> None:
    calls: list[str] = []
    args = _args("--phase", "full", "--execute")

    report = flow.build_report(args, runner=_ok_runner(calls))

    assert calls == []
    assert report["verdict"]["ok"] is False
    assert report["mutation_policy"]["full_execute_allowed"] is False
    assert report["verdict"]["required_failed_checks"] == [
        "precheck::full_execute_blocked_in_v0_1"
    ]


def test_full_plan_contains_all_phases_without_execution() -> None:
    calls: list[str] = []
    args = _args("--phase", "full")

    report = flow.build_report(args, runner=_ok_runner(calls))

    assert calls == []
    assert report["verdict"]["ok"] is True
    assert report["verdict"]["plan_only"] is True
    assert report["verdict"]["phase_complete"] is False
    assert {step["phase"] for step in report["planned_steps"]} == set(
        flow.PHASE_ORDER
    )


def test_core_derived_order_ends_in_strict_dod() -> None:
    args = _args(
        "--phase",
        "core-derived",
        "--execute",
        "--canonical-dir",
        "custom-canonical",
    )
    steps = flow.build_phase_plan(args)

    assert [step.name for step in steps] == [
        "build_retrieval_indexes",
        "run_retrieval_checks",
        "run_postpass_audit",
        "build_known_issues_snapshot",
        "check_core_definition_of_done",
    ]
    assert "--require-known-issues" in steps[-1].command
    assert "--strict" in steps[-1].command
    expected_canonical_path = str(
        Path("custom-canonical") / "canonical_documents.jsonl"
    )
    assert expected_canonical_path in steps[-1].command


def test_postgres_checks_availability_before_replace_and_after_export() -> None:
    args = _args("--phase", "postgres", "--execute")
    steps = flow.build_phase_plan(args)

    assert [step.name for step in steps] == [
        "postgres_pre_export_smoke",
        "export_postgres_replace",
        "postgres_post_export_smoke",
        "check_postgres_definition_of_done",
    ]
    assert "--replace" in steps[1].command
    assert steps[1].mutation_domain == flow.MUTATION_POSTGRES


def test_discovery_phase_rebuilds_ranking_before_detail_and_similar() -> None:
    args = _args(
        "--phase",
        "discovery-derived",
        "--execute",
        "--canonical-dir",
        "custom-canonical",
    )
    steps = flow.build_phase_plan(args)
    names = [step.name for step in steps]

    assert names.index("build_paper_features") < names.index("build_ranking_sample")
    assert names.index("build_ranking_sample") < names.index("build_paper_detail")
    assert names.index("build_paper_detail") < names.index("build_similar_papers")
    detail_step = steps[names.index("build_paper_detail")]
    assert "--from-latest-ranking-rank" in detail_step.command
    assert "1" in detail_step.command
    expected_canonical_path = str(
        Path("custom-canonical") / "canonical_documents.jsonl"
    )
    assert expected_canonical_path in detail_step.command
    similar_step = steps[names.index("build_similar_papers")]
    assert expected_canonical_path in similar_step.command


def test_discovery_phase_rebuilds_reports_before_final_required_dod() -> None:
    args = _args("--phase", "discovery-derived", "--execute")
    steps = flow.build_phase_plan(args)
    names = [step.name for step in steps]
    final_command = steps[-1].command

    assert names[-1] == "check_discovery_definition_of_done"
    assert names.index("check_similar_papers") < len(names) - 1
    assert names.index("check_discovery_api") < len(names) - 1
    assert names.index("check_streamlit_discovery_ui") < len(names) - 1
    for flag in (
        "--require-known-issues",
        "--require-paper-features",
        "--require-similar-papers",
        "--require-topic-clusters",
        "--require-topic-projection",
        "--require-discovery-api",
        "--require-streamlit-discovery-ui",
        "--strict",
    ):
        assert flag in final_command


def test_plan_mode_does_not_invoke_runner_for_non_promote_phase() -> None:
    calls: list[str] = []
    args = _args("--phase", "candidate")

    report = flow.build_report(args, runner=_ok_runner(calls))

    assert calls == []
    assert report["mode"] == "plan"
    assert report["execution_summary"]["executed_count"] == 0


def test_execution_stops_on_first_failed_step() -> None:
    calls: list[str] = []

    def failing_runner(step: flow.StepSpec, _: int) -> dict[str, object]:
        calls.append(step.name)
        return {
            "name": step.name,
            "phase": step.phase,
            "returncode": 1,
            "duration_seconds": 0.01,
            "stdout_tail": "",
            "stderr_tail": "failed",
            "ok": False,
        }

    args = _args("--phase", "core-derived", "--execute")
    report = flow.build_report(args, runner=failing_runner)

    assert calls == ["build_retrieval_indexes"]
    assert report["execution_summary"]["stopped_early_due_to_failure"] is True
    assert report["execution_summary"]["failed_step_names"] == [
        "build_retrieval_indexes"
    ]
    assert report["verdict"]["ok"] is False


def test_reports_write_latest_and_history(tmp_path: Path) -> None:
    args = _args("--phase", "full", "--reports-dir", str(tmp_path))
    report = flow.build_report(args)

    paths = flow.write_reports(report, tmp_path)

    assert all(path.exists() for path in paths)
    latest = json.loads(paths[0].read_text(encoding="utf-8"))
    assert latest["schema_version"] == flow.SCHEMA_VERSION
    assert latest["phase"] == "full"
    assert "failed_step_names" in latest["execution_summary"]


def test_history_paths_are_unique_for_back_to_back_reports(tmp_path: Path) -> None:
    args = _args("--phase", "full", "--reports-dir", str(tmp_path))

    first_paths = flow.write_reports(flow.build_report(args), tmp_path)
    second_paths = flow.write_reports(flow.build_report(args), tmp_path)

    assert first_paths[2] != second_paths[2]
    assert first_paths[3] != second_paths[3]
    assert first_paths[2].exists()
    assert second_paths[2].exists()


def test_definition_of_done_parser_supports_strict_mode() -> None:
    args = dod.build_parser().parse_args(["--strict"])

    assert args.strict is True


def test_legacy_pipeline_parser_supports_strict_composition() -> None:
    from scripts.update import run_refresh_pipeline_v1 as pipeline

    args = pipeline.build_parser().parse_args(["--candidate-rehearsal", "--strict"])

    assert args.strict is True
