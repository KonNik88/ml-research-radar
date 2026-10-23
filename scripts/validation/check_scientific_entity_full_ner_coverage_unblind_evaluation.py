"""Strictly validate the immutable 9D full-field NER evaluation."""
from __future__ import annotations

import argparse
from pathlib import Path

from radar_core.entities.scientific_entity_full_ner_coverage_unblind_evaluation import validate_unblind_evaluation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/scientific_entity_full_ner_coverage_unblind_evaluation_v0.1.yaml"))
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    config = args.config if args.config.is_absolute() else root / args.config
    report = validate_unblind_evaluation(config, root)
    for item in report.pop("checks"):
        print(f"[{'OK' if item['passed'] else 'FAIL'}] check={item['name']}")
    for name,value in report.items():
        print(f"[OK] {name}={value}")
    if args.strict and report["required_failed_count"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
