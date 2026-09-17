from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from radar_core.entities.scientific_entity_semantic_typer_h2_frozen_policy import (  # noqa: E402
    validate_h2_frozen_policy,
)


DEFAULT_CONFIG = ROOT / "configs" / "scientific_entity_semantic_typer_h2_frozen_policy_v0.3.yaml"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Scientific Entity Semantic Typer v0.3 H2 frozen policy package.")
    parser.add_argument("--revision-analysis-dir", type=Path, required=True)
    parser.add_argument("--evaluation-dir", type=Path, required=True)
    parser.add_argument("--prediction-dir", type=Path, required=True)
    parser.add_argument("--frozen-policy-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    checks, summary = validate_h2_frozen_policy(
        project_root=ROOT,
        config_path=args.config,
        revision_analysis_dir=args.revision_analysis_dir,
        evaluation_dir=args.evaluation_dir,
        prediction_dir=args.prediction_dir,
        frozen_policy_dir=args.frozen_policy_dir,
    )
    for key in (
        "report",
        "validation_scope",
        "freeze_id",
        "candidate_id",
        "margin_threshold",
        "policy_frozen",
        "total_checks",
        "required_failed_count",
        "next_slice",
    ):
        if key in summary:
            print(f"[OK] {key}={summary[key]}")
    if args.strict and summary.get("required_failed_count", 0):
        for name, ok, detail in checks:
            if not ok:
                print(f"[FAIL] {name}: {detail}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
