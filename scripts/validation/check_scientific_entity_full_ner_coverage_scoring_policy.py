"""Strictly validate frozen full NER coverage scoring policy preregistration."""
from __future__ import annotations

import argparse
from pathlib import Path

from radar_core.entities.scientific_entity_full_ner_coverage_scoring_policy import validate_scoring_policy


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",type=Path,default=Path("configs/scientific_entity_full_ner_coverage_scoring_policy_v0.1.yaml"))
    parser.add_argument("--strict",action="store_true")
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[2]
    cfg=args.config if args.config.is_absolute() else root/args.config
    result=validate_scoring_policy(cfg,root)
    for check in result.pop("checks"):
        print(f"[{'OK' if check['passed'] else 'FAIL'}] check={check['name']}")
    for key,value in result.items():
        print(f"[OK] {key}={value}")
    if args.strict and result["required_failed_count"]:
        raise SystemExit(1)


if __name__=="__main__":
    main()
