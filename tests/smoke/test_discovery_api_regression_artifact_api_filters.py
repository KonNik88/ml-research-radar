from __future__ import annotations

from scripts.validation.run_discovery_api_regression import (
    build_parser,
    build_steps,
    dod_flags_for_args,
)


def _step_by_name(steps, name: str):
    for step in steps:
        if step.name == name:
            return step
    raise AssertionError(f"Step not found: {name}")


def test_artifact_api_filters_step_is_opt_in_and_db_backed() -> None:
    args = build_parser().parse_args(
        [
            "--skip-similar-rebuild",
            "--include-artifact-api-filters",
        ]
    )

    steps = build_steps(args)
    step = _step_by_name(steps, "check_artifact_api_filters")

    assert step.env == {"ML_RADAR_SEARCH_BACKEND": "db"}
    assert step.cmd[1:4] == [
        "-m",
        "scripts.validation.check_artifact_api_filters",
        "--strict",
    ]


def test_artifact_api_filters_step_runs_before_dod_and_extends_dod_flags() -> None:
    args = build_parser().parse_args(
        [
            "--skip-similar-rebuild",
            "--include-artifact-api-filters",
            "--include-dod",
        ]
    )

    steps = build_steps(args)
    names = [step.name for step in steps]

    assert names.index("check_artifact_api_filters") < names.index(
        "strict_dod_with_discovery_api"
    )

    dod_step = _step_by_name(steps, "strict_dod_with_discovery_api")
    assert "--require-artifact-api-filters" in dod_step.cmd
    assert "--require-artifact-api-filters" in dod_flags_for_args(args)


def test_dod_flags_do_not_require_artifact_api_filters_by_default() -> None:
    args = build_parser().parse_args(
        [
            "--skip-similar-rebuild",
            "--include-dod",
        ]
    )

    steps = build_steps(args)
    names = [step.name for step in steps]

    assert "check_artifact_api_filters" not in names

    dod_step = _step_by_name(steps, "strict_dod_with_discovery_api")
    assert "--require-artifact-api-filters" not in dod_step.cmd
    assert "--require-artifact-api-filters" not in dod_flags_for_args(args)
