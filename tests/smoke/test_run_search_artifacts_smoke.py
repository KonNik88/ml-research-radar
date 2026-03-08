from __future__ import annotations

import subprocess
import sys


def _run_search(mode: str, query: str) -> str:
    cmd = [
        sys.executable,
        "-m",
        "scripts.retrieval.run_search",
        "--mode",
        mode,
        "--query",
        query,
        "--top-k",
        "3",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return result.stdout


def test_run_search_lexical_from_artifacts_smoke() -> None:
    output = _run_search("lexical", "graph neural networks")
    assert "[OK] lexical results" in output
    assert "title:" in output


def test_run_search_dense_from_artifacts_smoke() -> None:
    output = _run_search("dense", "graph neural networks")
    assert "[OK] dense results" in output
    assert "title:" in output


def test_run_search_hybrid_from_artifacts_smoke() -> None:
    output = _run_search("hybrid", "graph neural networks")
    assert "[OK] hybrid results" in output
    assert "title:" in output
    assert "hybrid=" in output