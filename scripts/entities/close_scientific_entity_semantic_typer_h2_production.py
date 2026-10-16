from __future__ import annotations

import argparse

from radar_core.entities.scientific_entity_semantic_typer_h2_production_closure import plan_or_execute_h2_production_closure


def main() -> None:
    parser = argparse.ArgumentParser(description="Close H2 v0.3 as the trusted Scientific Entity production baseline.")
    parser.add_argument("--execute", action="store_true", help="Write the immutable closure record. Without this flag, run read-only PLAN.")
    args = parser.parse_args()
    report = plan_or_execute_h2_production_closure(execute=args.execute)
    for key, value in report.items():
        print(f"[OK] {key}={value}")


if __name__ == "__main__":
    main()
