from __future__ import annotations

from scripts.validation.run_discovery_api_regression import build_parser, build_steps


def step_names(argv: list[str]) -> list[str]:
    args = build_parser().parse_args(["--skip-similar-rebuild", *argv])
    return [step.name for step in build_steps(args)]


def test_profile_sweep_flag_adds_evaluation_and_validator_steps():
    names = step_names(["--include-qdrant-profile-sweep"])

    assert "run_qdrant_search_profile_sweep" in names
    assert "check_qdrant_search_profile_sweep" in names
    assert names.index("run_qdrant_search_profile_sweep") < names.index(
        "check_qdrant_search_profile_sweep"
    )


def test_profile_sweep_is_not_part_of_default_regression():
    names = step_names([])

    assert "run_qdrant_search_profile_sweep" not in names
    assert "check_qdrant_search_profile_sweep" not in names


def test_serving_poc_and_profile_sweep_can_be_requested_together():
    names = step_names(
        ["--include-qdrant-serving-poc", "--include-qdrant-profile-sweep"]
    )

    assert "check_qdrant_collection" in names
    assert "compare_qdrant_file_dense" in names
    assert "check_qdrant_file_dense_comparison" in names
    assert "run_qdrant_search_profile_sweep" in names
    assert "check_qdrant_search_profile_sweep" in names

def test_serving_performance_flag_adds_evaluation_and_validator_steps():
    names = step_names(
        ["--include-qdrant-serving-performance"]
    )

    assert "run_qdrant_serving_performance" in names
    assert "check_qdrant_serving_performance" in names

    assert names.index(
        "run_qdrant_serving_performance"
    ) < names.index(
        "check_qdrant_serving_performance"
    )


def test_serving_performance_is_not_part_of_default_regression():
    names = step_names([])

    assert "run_qdrant_serving_performance" not in names
    assert "check_qdrant_serving_performance" not in names


def test_qdrant_evidence_steps_can_be_requested_together():
    names = step_names(
        [
            "--include-qdrant-serving-poc",
            "--include-qdrant-profile-sweep",
            "--include-qdrant-serving-performance",
            "--include-qdrant-hybrid-evaluation",
        ]
    )

    assert "check_qdrant_collection" in names
    assert "compare_qdrant_file_dense" in names
    assert "check_qdrant_file_dense_comparison" in names

    assert "run_qdrant_search_profile_sweep" in names
    assert "check_qdrant_search_profile_sweep" in names

    assert "run_qdrant_serving_performance" in names
    assert "check_qdrant_serving_performance" in names

    assert "run_qdrant_hybrid_evaluation" in names
    assert "check_qdrant_hybrid_evaluation" in names

    assert names.index(
        "run_qdrant_hybrid_evaluation"
    ) < names.index(
        "check_qdrant_hybrid_evaluation"
    )

def test_hybrid_evaluation_uses_strict_validator_and_file_backend():
    args = build_parser().parse_args(
        [
            "--skip-similar-rebuild",
            "--include-qdrant-hybrid-evaluation",
        ]
    )

    steps = {
        step.name: step
        for step in build_steps(args)
    }

    run_step = steps[
        "run_qdrant_hybrid_evaluation"
    ]
    check_step = steps[
        "check_qdrant_hybrid_evaluation"
    ]

    assert run_step.cmd[-1] == (
        "scripts.evaluation."
        "run_qdrant_hybrid_evaluation"
    )

    assert check_step.cmd[-2:] == [
        (
            "scripts.validation."
            "check_qdrant_hybrid_evaluation"
        ),
        "--strict",
    ]

    assert run_step.env == {
        "ML_RADAR_SEARCH_BACKEND": "file",
    }
    assert check_step.env == {
        "ML_RADAR_SEARCH_BACKEND": "file",
    }

def test_serving_performance_uses_full_preset_and_strict_validator():
    args = build_parser().parse_args(
        [
            "--skip-similar-rebuild",
            "--include-qdrant-serving-performance",
        ]
    )
    steps = {
        step.name: step
        for step in build_steps(args)
    }

    run_step = steps["run_qdrant_serving_performance"]
    check_step = steps["check_qdrant_serving_performance"]

    assert run_step.cmd[-2:] == ["--preset", "full"]
    assert check_step.cmd[-1] == "--strict"

def test_hybrid_evaluation_is_composed_after_existing_qdrant_evidence():
    names = step_names(
        [
            "--include-qdrant-profile-sweep",
            "--include-qdrant-serving-performance",
            "--include-qdrant-hybrid-evaluation",
        ]
    )

    assert names.index(
        "check_qdrant_search_profile_sweep"
    ) < names.index(
        "run_qdrant_serving_performance"
    )

    assert names.index(
        "check_qdrant_serving_performance"
    ) < names.index(
        "run_qdrant_hybrid_evaluation"
    )

    assert names.index(
        "run_qdrant_hybrid_evaluation"
    ) < names.index(
        "check_qdrant_hybrid_evaluation"
    )