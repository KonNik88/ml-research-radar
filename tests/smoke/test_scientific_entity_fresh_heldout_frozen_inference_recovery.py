from __future__ import annotations

from pathlib import Path

from scripts.entities import recover_scientific_entity_fresh_heldout_frozen_inference as recovery


def test_recovery_constants_preserve_observed_original_run_facts() -> None:
    assert recovery.ORIGINAL_RAW_MENTION_COUNT == 1257
    assert recovery.ORIGINAL_EXTRACTOR_FINGERPRINT == (
        "e43009f1127a445ddfd01352b47825391c2d12a2059ed53b9d35f7e5b12d8f13"
    )
    assert recovery.ORIGINAL_RUNTIME_DEVICE_NAME == "NVIDIA GeForce RTX 2070 SUPER"
    assert recovery.ORIGINAL_PEAK_CUDA_MEMORY_BYTES == 418029568


def test_recovery_plan_is_non_inference(monkeypatch, tmp_path: Path) -> None:
    sample = tmp_path / "sample"
    reference = tmp_path / "reference"
    dev = tmp_path / "dev"
    sample.mkdir()
    reference.mkdir()
    dev.mkdir()

    calls = []

    def fake_plan_or_execute(**kwargs):
        calls.append(kwargs["execute"])
        return {
            "candidate_id": "scientific-entity-semantic-prompt-raw-floor-extension-v0.2c",
            "runtime_config_sha256": "b9b544194183e1cdf60a4632735acb6fe24788829bd1c75941293c5cd4360da6",
            "sample_id": "scientific-entity-fresh-heldout-sample-v0.2-20260901T130232963026Z",
            "review_id": "scientific-entity-fresh-heldout-review-v0.2-20260901T130232963026Z",
            "reference_mention_count": 944,
            "build_id": "scientific-entity-gliner-small-v2.5-fresh-v0.2c-20260901T130232963026Z",
        }

    monkeypatch.setattr(recovery, "plan_or_execute_frozen_inference", fake_plan_or_execute)
    monkeypatch.setattr(
        recovery,
        "load_scientific_entity_fresh_heldout_frozen_inference_config",
        lambda path: type(
            "Cfg",
            (),
            {
                "execution": type(
                    "Execution",
                    (),
                    {
                        "raw_output_root": Path("tmp-output-that-does-not-exist"),
                        "build_id": "scientific-entity-gliner-small-v2.5-fresh-v0.2c-20260901T130232963026Z",
                    },
                )()
            },
        )(),
    )
    monkeypatch.setattr(recovery, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(recovery, "RECOVERY_AUDIT_ROOT", tmp_path / "audit")

    report = recovery.recover_deleted_artifact(
        sample_dir=sample,
        reference_dir=reference,
        development_package_dir=dev,
        config_path=tmp_path / "config.yaml",
        canonical_path=tmp_path / "canonical.jsonl",
        execute=False,
    )

    assert calls == [False]
    assert report["plan_runs_model_inference"] is False
    assert report["recovery_model_inference_executed"] is False
    assert report["next_slice"] == "execute_documented_artifact_recovery_once"
