"""9D immutable full NER unblind + evaluation (PLAN by default)."""
from __future__ import annotations

import argparse
from pathlib import Path

from radar_core.entities.scientific_entity_full_ner_coverage_unblind_evaluation import (
    execute_unblind_evaluation, plan_unblind_evaluation,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/scientific_entity_full_ner_coverage_unblind_evaluation_v0.1.yaml"))
    parser.add_argument("--execute", action="store_true", help="ONE TIME: read existing trusted predictions and produce immutable evaluation; no inference")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    config = args.config if args.config.is_absolute() else root / args.config
    report = (execute_unblind_evaluation if args.execute else plan_unblind_evaluation)(config, root)
    for name, value in report.items():
        print(f"[OK] {name}={value}")


if __name__ == "__main__":
    main()
