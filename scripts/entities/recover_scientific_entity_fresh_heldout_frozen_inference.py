from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from radar_core.contracts.scientific_entity_fresh_heldout_frozen_inference import (
    ScientificEntityFreshHeldoutFrozenInferenceError,
    load_scientific_entity_fresh_heldout_frozen_inference_config,
)
from radar_core.entities.scientific_entity_fresh_heldout_frozen_inference import (
    DEFAULT_CANONICAL,
    DEFAULT_CONFIG,
    PROJECT_ROOT,
    plan_or_execute_frozen_inference,
)

REPORT_NAME = "scientific_entity_fresh_heldout_frozen_inference_recovery_v02"

# These facts were printed by the successful original one-shot execution
# before a faulty smoke test deleted its local output directory.
ORIGINAL_RAW_MENTION_COUNT = 1257
ORIGINAL_EXTRACTOR_FINGERPRINT = (
    "e43009f1127a445ddfd01352b47825391c2d12a2059ed53b9d35f7e5b12d8f13"
)
ORIGINAL_RUNTIME_DEVICE_NAME = "NVIDIA GeForce RTX 2070 SUPER"
ORIGINAL_INFERENCE_DURATION_SECONDS = 10.334789
ORIGINAL_PEAK_CUDA_MEMORY_BYTES = 418029568

RECOVERY_AUDIT_ROOT = (
    PROJECT_ROOT
    / "data"
    / "entities"
    / "scientific_entity_fresh_heldout_frozen_inference_recovery"
    / "v0.2"
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _audit_dir(build_id: str) -> Path:
    return RECOVERY_AUDIT_ROOT / build_id


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Exceptional recovery for the already-executed frozen v0.2c fresh-heldout raw "
            "inference after accidental local artifact deletion by a faulty smoke test. "
            "PLAN does not run the model. EXECUTE records recovery provenance and requires "
            "the rematerialized run to match the previously observed raw count and extractor fingerprint."
        )
    )
    parser.add_argument("--sample-dir", type=Path, required=True)
    parser.add_argument("--reference-dir", type=Path, required=True)
    parser.add_argument("--development-package-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--model-cache-dir", type=Path, default=None)
    parser.add_argument("--allow-model-download", action="store_true")
    parser.add_argument("--execute", action="store_true")
    return parser


def recover_deleted_artifact(
    *,
    sample_dir: Path,
    reference_dir: Path,
    development_package_dir: Path,
    config_path: Path,
    canonical_path: Path,
    model_cache_dir: Path | None = None,
    allow_model_download: bool = False,
    execute: bool = False,
) -> dict:
    contract = load_scientific_entity_fresh_heldout_frozen_inference_config(
        config_path.resolve()
    )
    output_dir = (
        PROJECT_ROOT
        / contract.execution.raw_output_root
        / contract.execution.build_id
    ).resolve()
    audit_dir = _audit_dir(contract.execution.build_id)

    # Re-run the ordinary non-inference PLAN so frozen runtime/reference lineage
    # must still validate before recovery can even be considered.
    preflight = plan_or_execute_frozen_inference(
        project_root=PROJECT_ROOT,
        config_path=config_path,
        sample_dir=sample_dir,
        reference_dir=reference_dir,
        development_package_dir=development_package_dir,
        canonical_path=canonical_path,
        model_cache_dir=model_cache_dir,
        allow_model_download=allow_model_download,
        execute=False,
    )

    if output_dir.exists():
        raise FileExistsError(
            f"Raw artifact already exists; recovery is neither required nor allowed: {output_dir}"
        )

    prior_authorization = audit_dir / "recovery_authorization.json"
    prior_result = audit_dir / "recovery_result.json"
    if execute and (prior_authorization.exists() or prior_result.exists()):
        raise FileExistsError(
            f"Recovery audit already exists; a second recovery attempt is forbidden: {audit_dir}"
        )

    report = {
        "report": REPORT_NAME,
        "mode": "execute" if execute else "plan",
        "phase_complete": False,
        "recovery_reason": "faulty_smoke_test_deleted_successful_one_shot_raw_artifact",
        "original_one_shot_execution_observed": True,
        "original_artifact_available": False,
        "byte_identity_with_deleted_artifact_verifiable": False,
        "candidate_id": preflight["candidate_id"],
        "runtime_config_sha256": preflight["runtime_config_sha256"],
        "sample_id": preflight["sample_id"],
        "review_id": preflight["review_id"],
        "reference_mention_count": preflight["reference_mention_count"],
        "build_id": preflight["build_id"],
        "output_dir": str(output_dir).replace("\\", "/"),
        "original_raw_mention_count": ORIGINAL_RAW_MENTION_COUNT,
        "original_extractor_fingerprint": ORIGINAL_EXTRACTOR_FINGERPRINT,
        "original_runtime_device_name": ORIGINAL_RUNTIME_DEVICE_NAME,
        "original_inference_duration_seconds": ORIGINAL_INFERENCE_DURATION_SECONDS,
        "original_peak_cuda_memory_bytes": ORIGINAL_PEAK_CUDA_MEMORY_BYTES,
        "plan_runs_model_inference": False,
        "recovery_model_inference_executed": False,
        "policy_applied": False,
        "evaluation_executed": False,
        "acceptance_decision_made": False,
        "next_slice": "execute_documented_artifact_recovery_once",
    }
    if not execute:
        return report

    authorization = {
        "schema_version": "scientific_entity_fresh_heldout_frozen_inference_recovery_v0.2",
        "status": "authorized_before_recovery_rerun",
        "created_at_utc": _utc_now(),
        "reason": report["recovery_reason"],
        "original_one_shot_execution_observed": True,
        "byte_identity_with_deleted_artifact_verifiable": False,
        "candidate_id": report["candidate_id"],
        "runtime_config_sha256": report["runtime_config_sha256"],
        "sample_id": report["sample_id"],
        "review_id": report["review_id"],
        "reference_mention_count": report["reference_mention_count"],
        "build_id": report["build_id"],
        "expected_original_raw_mention_count": ORIGINAL_RAW_MENTION_COUNT,
        "expected_original_extractor_fingerprint": ORIGINAL_EXTRACTOR_FINGERPRINT,
        "safety": {
            "prompt_changes": False,
            "threshold_changes": False,
            "model_changes": False,
            "sampling_changes": False,
            "policy_application": False,
            "evaluation": False,
            "acceptance_decision": False,
        },
    }
    _write_json(prior_authorization, authorization)

    recovered = plan_or_execute_frozen_inference(
        project_root=PROJECT_ROOT,
        config_path=config_path,
        sample_dir=sample_dir,
        reference_dir=reference_dir,
        development_package_dir=development_package_dir,
        canonical_path=canonical_path,
        model_cache_dir=model_cache_dir,
        allow_model_download=allow_model_download,
        execute=True,
    )

    raw_count_match = recovered.get("raw_mention_count") == ORIGINAL_RAW_MENTION_COUNT
    fingerprint_match = (
        recovered.get("extractor_fingerprint") == ORIGINAL_EXTRACTOR_FINGERPRINT
    )
    recovery_match_passed = raw_count_match and fingerprint_match

    result = {
        "schema_version": "scientific_entity_fresh_heldout_frozen_inference_recovery_v0.2",
        "status": (
            "recovered_and_observed_facts_match"
            if recovery_match_passed
            else "recovered_but_observed_facts_do_not_match"
        ),
        "completed_at_utc": _utc_now(),
        "reason": report["recovery_reason"],
        "byte_identity_with_deleted_artifact_verifiable": False,
        "build_id": recovered.get("build_id"),
        "runtime_config_sha256": recovered.get("runtime_config_sha256"),
        "raw_mention_count": recovered.get("raw_mention_count"),
        "expected_original_raw_mention_count": ORIGINAL_RAW_MENTION_COUNT,
        "raw_mention_count_match": raw_count_match,
        "extractor_fingerprint": recovered.get("extractor_fingerprint"),
        "expected_original_extractor_fingerprint": ORIGINAL_EXTRACTOR_FINGERPRINT,
        "extractor_fingerprint_match": fingerprint_match,
        "model_artifact_verified": recovered.get("model_artifact_verified"),
        "backbone_config_verified": recovered.get("backbone_config_verified"),
        "runtime_device_name": recovered.get("runtime_device_name"),
        "inference_duration_seconds": recovered.get("inference_duration_seconds"),
        "peak_cuda_memory_bytes": recovered.get("peak_cuda_memory_bytes"),
        "policy_applied": False,
        "evaluation_executed": False,
        "acceptance_decision_made": False,
        "recovery_match_passed": recovery_match_passed,
    }
    _write_json(prior_result, result)

    report.update(
        {
            "phase_complete": recovery_match_passed,
            "recovery_model_inference_executed": True,
            "recovered_raw_mention_count": recovered.get("raw_mention_count"),
            "recovered_extractor_fingerprint": recovered.get("extractor_fingerprint"),
            "raw_mention_count_match": raw_count_match,
            "extractor_fingerprint_match": fingerprint_match,
            "recovery_match_passed": recovery_match_passed,
            "recovery_audit_dir": str(audit_dir).replace("\\", "/"),
            "next_slice": (
                "validate_recovered_frozen_v02c_raw_inference"
                if recovery_match_passed
                else "stop_and_investigate_recovery_mismatch"
            ),
        }
    )

    if not recovery_match_passed:
        raise ScientificEntityFreshHeldoutFrozenInferenceError(
            "Recovered raw artifact does not match the previously observed "
            "raw mention count and extractor fingerprint; stop before policy/evaluation."
        )
    return report


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = recover_deleted_artifact(
            sample_dir=args.sample_dir,
            reference_dir=args.reference_dir,
            development_package_dir=args.development_package_dir,
            config_path=args.config,
            canonical_path=args.canonical,
            model_cache_dir=args.model_cache_dir,
            allow_model_download=args.allow_model_download,
            execute=args.execute,
        )
    except (
        FileNotFoundError,
        FileExistsError,
        OSError,
        ValueError,
        ScientificEntityFreshHeldoutFrozenInferenceError,
    ) as exc:
        print(f"[FAILED] report={REPORT_NAME}")
        print(f"[FAILED] {type(exc).__name__}: {exc}")
        return 2

    for key in (
        "report",
        "mode",
        "phase_complete",
        "recovery_reason",
        "original_one_shot_execution_observed",
        "original_artifact_available",
        "byte_identity_with_deleted_artifact_verifiable",
        "candidate_id",
        "runtime_config_sha256",
        "sample_id",
        "review_id",
        "reference_mention_count",
        "build_id",
        "output_dir",
        "original_raw_mention_count",
        "original_extractor_fingerprint",
        "plan_runs_model_inference",
        "recovery_model_inference_executed",
        "recovered_raw_mention_count",
        "recovered_extractor_fingerprint",
        "raw_mention_count_match",
        "extractor_fingerprint_match",
        "recovery_match_passed",
        "policy_applied",
        "evaluation_executed",
        "acceptance_decision_made",
        "recovery_audit_dir",
        "next_slice",
    ):
        if key in report:
            print(f"[OK] {key}={report.get(key)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
