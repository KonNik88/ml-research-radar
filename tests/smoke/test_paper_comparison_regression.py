from __future__ import annotations

import argparse
import time
from pathlib import Path

from scripts.validation.run_paper_comparison_regression import (
    TARGET_TEST_PATHS,
    Step,
    build_report,
    build_steps,
    step_result,
)


def _args(
    tmp_path: Path,
    *,
    include_live_smoke: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        include_live_smoke=include_live_smoke,
        base_url="http://127.0.0.1:8000",
        reports_dir=tmp_path / "reports",
    )


def test_default_regression_steps_are_bounded_and_file_backed(tmp_path):
    steps = build_steps(_args(tmp_path))

    assert [step.name for step in steps] == [
        "pytest_paper_comparison_regression",
        "check_streamlit_discovery_ui",
    ]
    assert all(
        step.env == {"ML_RADAR_SEARCH_BACKEND": "file"}
        for step in steps
    )
    assert "--include-live-smoke" not in " ".join(steps[0].cmd)


def test_live_smoke_step_is_explicit_opt_in(tmp_path):
    steps = build_steps(_args(tmp_path, include_live_smoke=True))

    assert [step.name for step in steps] == [
        "pytest_paper_comparison_regression",
        "check_streamlit_discovery_ui",
        "check_paper_comparison_live_smoke",
    ]
    live_cmd = steps[-1].cmd
    assert "scripts.validation.check_paper_comparison_live_smoke" in live_cmd
    assert "--strict" in live_cmd
    assert "--base-url" in live_cmd
    assert "http://127.0.0.1:8000" in live_cmd


def test_target_test_matrix_covers_core_api_ui_and_live_gate():
    assert set(TARGET_TEST_PATHS) == {
        "tests/smoke/test_paper_comparison.py",
        "tests/integration/test_api_discovery.py",
        "tests/smoke/test_citation_graph_fixture_store.py",
        "tests/integration/test_api_citation_graph_failure_isolation.py",
        "tests/integration/test_api_citation_graph_references.py",
        "tests/smoke/test_comparison_ui_client.py",
        "tests/smoke/test_comparison_ui.py",
        "tests/smoke/test_streamlit_discovery_ui.py",
        "tests/smoke/test_workspace_ui_client.py",
        "tests/smoke/test_paper_comparison_live_smoke.py",
        "tests/smoke/test_paper_comparison_regression.py",
    }
    assert not any("qdrant" in path.lower() for path in TARGET_TEST_PATHS)
    assert not any("_db" in path.lower() for path in TARGET_TEST_PATHS)


def test_live_validator_is_http_only_and_has_no_runtime_store_imports():
    validator_path = Path(
        "scripts/validation/check_paper_comparison_live_smoke.py"
    )
    text = validator_path.read_text(encoding="utf-8")

    assert "from urllib.request import Request, urlopen" in text
    assert '"/discovery/papers/compare"' in text
    assert "from services.api" not in text
    assert "from radar_core" not in text
    assert "psycopg" not in text
    assert "qdrant_client" not in text


def test_docs_describe_the_final_merge_gate_and_preserve_boundaries():
    contract = Path(
        "docs/paper_comparison_workspace_v0.1.md"
    ).read_text(encoding="utf-8")
    api_reference = Path("docs/api_reference.md").read_text(encoding="utf-8")
    combined = f"{contract}\n{api_reference}"
    normalized = " ".join(combined.split())

    for snippet in [
        "Final regression and live-smoke gate",
        "run_paper_comparison_regression",
        "check_paper_comparison_live_smoke",
        "paper_comparison_regression_latest.json",
        "paper_comparison_live_smoke_latest.json",
        "workspace_postgres_required = false",
        "does not require workspace PostgreSQL or Qdrant",
        "does not authorize LLM/RAG",
        "changes to canonical truth",
    ]:
        assert snippet in normalized


def test_green_report_records_static_and_live_merge_gates(tmp_path):
    args = _args(tmp_path, include_live_smoke=True)
    steps = build_steps(args)
    results = [
        step_result(step=step, returncode=0, duration_sec=0.01)
        for step in steps
    ]

    report = build_report(
        args=args,
        run_ts="20260730T120000Z",
        started_at=time.perf_counter(),
        steps=results,
    )

    assert report["schema_version"] == "paper_comparison_regression_runner_v1"
    assert report["summary"]["ok"] is True
    assert report["summary"]["failed_steps_count"] == 0
    assert report["summary"]["target_test_files_count"] == 11
    assert report["verdict"]["targeted_regression_complete"] is True
    assert report["verdict"]["streamlit_static_gate_complete"] is True
    assert report["verdict"]["live_smoke_requested"] is True
    assert report["verdict"]["live_smoke_complete"] is True
    assert report["verdict"]["canonical_truth_mutated"] is False
    assert report["verdict"]["workspace_postgres_required"] is False
    assert report["verdict"]["qdrant_required"] is False


def test_failed_step_produces_fail_closed_report(tmp_path):
    args = _args(tmp_path, include_live_smoke=True)
    pytest_step = Step(
        name="pytest_paper_comparison_regression",
        cmd=["python", "-m", "pytest"],
        env={"ML_RADAR_SEARCH_BACKEND": "file"},
    )
    result = step_result(
        step=pytest_step,
        returncode=1,
        duration_sec=0.01,
    )

    report = build_report(
        args=args,
        run_ts="20260730T120001Z",
        started_at=time.perf_counter(),
        steps=[result],
    )

    assert report["summary"]["ok"] is False
    assert report["summary"]["failed_steps_count"] == 1
    assert report["verdict"]["failed_steps"] == [
        "pytest_paper_comparison_regression"
    ]
    assert report["verdict"]["targeted_regression_complete"] is False
    assert report["verdict"]["streamlit_static_gate_complete"] is False
    assert report["verdict"]["live_smoke_complete"] is False
