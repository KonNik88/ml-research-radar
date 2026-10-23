"""Preregister full NER coverage scoring rules before unblind; PLAN by default."""
from __future__ import annotations

import argparse
from pathlib import Path

from radar_core.entities.scientific_entity_full_ner_coverage_scoring_policy import (
    plan_scoring_policy,execute_scoring_policy,
)


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",type=Path,default=Path("configs/scientific_entity_full_ner_coverage_scoring_policy_v0.1.yaml"))
    parser.add_argument("--execute",action="store_true",help="One-shot immutable scoring preregistration; NO unblind")
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[2]
    cfg=args.config if args.config.is_absolute() else root/args.config
    result=(execute_scoring_policy if args.execute else plan_scoring_policy)(cfg,root)
    for key,value in result.items():
        print(f"[OK] {key}={value}")


if __name__=="__main__":
    main()
