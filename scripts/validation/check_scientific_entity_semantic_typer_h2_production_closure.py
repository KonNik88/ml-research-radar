from __future__ import annotations

import argparse

from radar_core.entities.scientific_entity_semantic_typer_h2_production_closure import validate_h2_production_closure


def main() -> None:
    parser = argparse.ArgumentParser(description="Strictly validate the immutable H2 v0.3 production closure.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if any required check fails.")
    args = parser.parse_args()
    checks, summary = validate_h2_production_closure()
    for name, ok, detail in checks:
        print(f"[{'OK' if ok else 'FAIL'}] check={name} detail={detail}")
    for key, value in summary.items():
        print(f"[{'OK' if summary['required_failed_count'] == 0 else 'FAIL'}] {key}={value}")
    if args.strict and summary["required_failed_count"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
