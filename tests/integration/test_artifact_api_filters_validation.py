from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_artifact_api_filters_validation_strict(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["ML_RADAR_SEARCH_BACKEND"] = "db"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.validation.check_artifact_api_filters",
            "--strict",
            "--reports-dir",
            str(tmp_path),
        ],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr

    latest_json = tmp_path / "artifact_api_filters_check_latest.json"
    latest_md = tmp_path / "artifact_api_filters_check_latest.md"

    assert latest_json.exists()
    assert latest_md.exists()

    report = json.loads(latest_json.read_text(encoding="utf-8"))

    assert report["report_name"] == "artifact_api_filters_check"
    assert report["verdict"]["ok"] is True
    assert report["verdict"]["required_failed_count"] == 0
    assert report["summary"]["runtime_backend_mode"] == "db"
    assert report["checks"]["artifacts_provider_github_rows_match"] is True
    assert report["checks"]["document_artifacts_rows_match"] is True
