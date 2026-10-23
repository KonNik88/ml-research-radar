"""Strict immutable full-field NER reference validator."""
from __future__ import annotations
import argparse
from pathlib import Path
from radar_core.entities.scientific_entity_full_ner_coverage_reference import validate_frozen_reference


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",type=Path,default=Path("configs/scientific_entity_full_ner_coverage_reference_v0.1.yaml"))
    parser.add_argument("--strict",action="store_true")
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[2]
    config=args.config if args.config.is_absolute() else root/args.config
    result=validate_frozen_reference(config,root)
    for check in result.pop("checks"):
        print(f"[{'OK' if check['passed'] else 'FAIL'}] check={check['name']}")
    for k,v in result.items():
        print(f"[{'OK' if result['required_failed_count']==0 else 'FAIL'}] {k}={v}")
    if args.strict and result["required_failed_count"]:
        raise SystemExit(1)

if __name__=="__main__":
    main()
