from __future__ import annotations

from copy import deepcopy

import scripts.validation.check_runtime_service_contract as contract_validator
from services.api.runtime_services import build_runtime_service_status


def test_runtime_service_contract_fixture_matrix_is_green() -> None:
    report = contract_validator.build_report(
        check_api=False,
        api_base_url="http://127.0.0.1:8000",
        timeout_seconds=1,
    )

    assert report["ok"] is True
    assert report["required_failed_count"] == 0
    assert report["extracted_values"]["scenario_count"] == 6

    scenario_reports = {
        row["name"]: row for row in report["extracted_values"]["scenario_reports"]
    }
    assert scenario_reports["file_ready_dense_qdrant_unavailable"]["ok"] is True
    assert scenario_reports["db_ready_core_optional_unsupported"]["ok"] is True
    assert (
        scenario_reports["unsupported_backend_blocks_health"]["summary"][
            "overall_status"
        ]
        == "unavailable"
    )


def test_runtime_service_contract_validator_detects_count_drift() -> None:
    scenario = contract_validator.runtime_service_scenarios()[0]
    status = build_runtime_service_status(
        snapshot=scenario.snapshot,
        settings=contract_validator._settings(**scenario.settings_overrides),
    )
    mutated = deepcopy(status)
    mutated["counts"]["required_available_count"] = -1

    checks = contract_validator.validate_service_status(
        status=mutated,
        scenario=scenario,
    )

    assert checks["service_counts_match"] is False
    assert checks["scenario_overall_status_ok"] is True


def test_runtime_service_contract_validator_detects_service_status_drift() -> None:
    scenario = contract_validator.runtime_service_scenarios()[2]
    status = build_runtime_service_status(
        snapshot=scenario.snapshot,
        settings=contract_validator._settings(**scenario.settings_overrides),
    )
    mutated = deepcopy(status)
    mutated["services"]["search_dense"]["status"] = "available"
    mutated["services"]["search_dense"]["available"] = True

    checks = contract_validator.validate_service_status(
        status=mutated,
        scenario=scenario,
    )

    assert checks["scenario_search_dense_status_ok"] is False
    assert checks["scenario_search_dense_available_ok"] is False
