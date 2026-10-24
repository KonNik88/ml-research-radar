"""Build read-only historical 9D diagnostic review queue (PLAN by default)."""
from __future__ import annotations

import argparse
from pathlib import Path

from radar_core.entities.scientific_entity_v04_root_cause_diagnostics import (
    execute_root_cause_review,
    plan_root_cause_review,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/scientific_entity_v04_root_cause_diagnostics_v0.1.yaml"))
    parser.add_argument("--execute", action="store_true", help="Write NEW review workspace, no model inference")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    config = args.config if args.config.is_absolute() else root / args.config
    report = (execute_root_cause_review if args.execute else plan_root_cause_review)(config, root)
    for name, value in report.items():
        print(f"[OK] {name}={value}")


if __name__ == "__main__":
    main()
