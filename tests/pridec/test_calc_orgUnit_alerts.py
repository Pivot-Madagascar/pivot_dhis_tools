"""
Tests for calc_orgUnit_alerts and its input-validation guards.

Package layout (src-layout):
    src/pivot_dhis_tools/get_dataElements.py
    src/pivot_dhis_tools/pridec/calc_orgUnit_alerts.py

Requires the package to be importable, e.g. via `pip install -e .` from the
repo root, or a pytest `pythonpath = ["src"]` setting in pyproject.toml/pytest.ini.
"""
import copy
from datetime import date

import pandas as pd
import pytest

from pivot_dhis_tools.pridec.calc_orgUnit_alerts import calc_orgUnit_alerts
import pivot_dhis_tools.pridec.calc_orgUnit_alerts as com_mod  # used to monkeypatch get_dataElements


# ---------------------------------------------------------------------------
# Shared constants matching a focal_date of 2026-03-01
# ---------------------------------------------------------------------------
DISEASE_CODE = "COMRespinf"
ALERT_NAME = "COMRespinfVigilance"
FOCAL_DATE = date(2026, 3, 1)

CURRENT_PERIODS = ["202603", "202604", "202605"]
HIST_PERIODS = [
    "202503", "202403", "202303",
    "202504", "202404", "202304",
    "202505", "202405", "202305",
]

BASE_KWARGS = dict(
    dhis_url="http://localhost:8080/",
    parent_ou="VtP4BdCeXIo",
    ou_level=5,
    disease_code=DISEASE_CODE,
    alert_name=ALERT_NAME,
    focal_date=FOCAL_DATE,
    token="d2pat_fake_token",
)


# ---------------------------------------------------------------------------
# Helpers to build synthetic forecast / historic records
# ---------------------------------------------------------------------------
def make_records(org_values: dict, periods: list, dx: str) -> list:
    """org_values: {orgUnit: value_used_for_every_period}"""
    return [
        {"dataElement": dx, "orgUnit": ou, "period": p, "value": val}
        for ou, val in org_values.items()
        for p in periods
    ]


def wrap(records: list) -> dict:
    """Mimic a raw DHIS2 export shape: {"dataValues": [...]}"""
    return {"dataValues": records}


def default_forecast_records(org_values=None):
    org_values = org_values or {"OU1": 11, "OU2": 5}
    return make_records(org_values, CURRENT_PERIODS, f"pridec_forecast_{DISEASE_CODE}Avg")


def default_historic_records(org_values=None):
    org_values = org_values or {"OU1": 5, "OU2": 10}
    return make_records(org_values, HIST_PERIODS, f"pridec_historic_{DISEASE_CODE}")


# =============================================================================
# Guard: must supply token/user+pwd if either dataset needs to be fetched
# =============================================================================
def test_requires_token_or_credentials_when_no_local_data():
    kwargs = {**BASE_KWARGS}
    kwargs.pop("token")
    with pytest.raises(ValueError, match="Must provide either `token`"):
        calc_orgUnit_alerts(**kwargs, forecast_json=None, historic_json=None)


def test_does_not_require_credentials_when_both_datasets_provided_locally():
    # token popped, but since both local datasets are supplied, no DHIS2 call
    # should be attempted and the credential guard should not fire.
    kwargs = {**BASE_KWARGS}
    kwargs.pop("token")
    result = calc_orgUnit_alerts(
        **kwargs,
        forecast_json=wrap(default_forecast_records()),
        historic_json=wrap(default_historic_records()),
    )
    assert result["dataValues"][0]["dataElement"] == f"pridec_alert_{ALERT_NAME}"


# =============================================================================
# Guard: required columns present after building the DataFrame
# =============================================================================
def test_forecast_data_missing_required_columns_raises():
    bad_records = [{"dataElement": f"pridec_forecast_{DISEASE_CODE}Avg", "orgUnit": "OU1", "period": "202603"}]
    # missing "value" column entirely
    with pytest.raises(ValueError, match="forecast_data is missing required columns"):
        calc_orgUnit_alerts(
            **BASE_KWARGS,
            forecast_json=wrap(bad_records),
            historic_json=wrap(default_historic_records()),
        )


def test_historic_data_missing_required_columns_raises():
    bad_records = [{"dataElement": f"pridec_historic_{DISEASE_CODE}", "orgUnit": "OU1", "period": "202503"}]
    with pytest.raises(ValueError, match="historic_data is missing required columns"):
        calc_orgUnit_alerts(
            **BASE_KWARGS,
            forecast_json=wrap(default_forecast_records()),
            historic_json=wrap(bad_records),
        )


# =============================================================================
# Guard: "dataValues" unwrapping vs. accepting raw JSON as-is
# =============================================================================
def test_forecast_data_unwraps_dataValues_key():
    result = calc_orgUnit_alerts(
        **BASE_KWARGS,
        forecast_json=wrap(default_forecast_records()),
        historic_json=wrap(default_historic_records()),
    )
    assert result["dataValues"][0]["value"] == 1


def test_forecast_data_accepts_raw_list_without_wrapper():
    result = calc_orgUnit_alerts(
        **BASE_KWARGS,
        forecast_json=default_forecast_records(),       # raw list, no "dataValues" wrapper
        historic_json=default_historic_records(),        # raw list, no "dataValues" wrapper
    )
    assert result["dataValues"][0]["value"] == 1


# =============================================================================
# Guard: disease_code / dataElement not found in provided data
# =============================================================================
def test_forecast_disease_code_not_found_raises():
    wrong_records = make_records({"OU1": 11}, CURRENT_PERIODS, "pridec_forecast_OtherDiseaseAvg")
    with pytest.raises(ValueError, match=f"pridec_forecast_{DISEASE_CODE}Avg not found"):
        calc_orgUnit_alerts(
            **BASE_KWARGS,
            forecast_json=wrap(wrong_records),
            historic_json=wrap(default_historic_records()),
        )


def test_historic_disease_code_not_found_raises():
    wrong_records = make_records({"OU1": 5}, HIST_PERIODS, "pridec_historic_OtherDisease")
    with pytest.raises(ValueError, match=f"pridec_historic_{DISEASE_CODE} not found"):
        calc_orgUnit_alerts(
            **BASE_KWARGS,
            forecast_json=wrap(default_forecast_records()),
            historic_json=wrap(wrong_records),
        )


# =============================================================================
# Guard: non-numeric / missing values
# =============================================================================
def test_non_numeric_forecast_value_raises():
    records = default_forecast_records()
    records[0]["value"] = "not-a-number"
    with pytest.raises(ValueError, match="Non-numeric or missing values found in forecast data"):
        calc_orgUnit_alerts(
            **BASE_KWARGS,
            forecast_json=wrap(records),
            historic_json=wrap(default_historic_records()),
        )


def test_non_numeric_historic_value_raises():
    records = default_historic_records()
    records[0]["value"] = None
    with pytest.raises(ValueError, match="Non-numeric or missing values found in historic data"):
        calc_orgUnit_alerts(
            **BASE_KWARGS,
            forecast_json=wrap(default_forecast_records()),
            historic_json=wrap(records),
        )


# =============================================================================
# Guard: no rows left after filtering to the expected period window
# =============================================================================
def test_no_forecast_data_for_requested_period_raises():
    records = make_records({"OU1": 11}, ["202101"], f"pridec_forecast_{DISEASE_CODE}Avg")
    with pytest.raises(ValueError, match="No forecasts exist for the period query"):
        calc_orgUnit_alerts(
            **BASE_KWARGS,
            forecast_json=wrap(records),
            historic_json=wrap(default_historic_records()),
        )


def test_no_historic_data_for_requested_period_raises():
    records = make_records({"OU1": 5}, ["202101"], f"pridec_historic_{DISEASE_CODE}")
    with pytest.raises(ValueError, match="Historical data missing for the following dates"):
        calc_orgUnit_alerts(
            **BASE_KWARGS,
            forecast_json=wrap(default_forecast_records()),
            historic_json=wrap(records),
        )


# =============================================================================
# Guard/behavior: orgUnit mismatch between forecast and historic data
# =============================================================================
def test_orgUnits_missing_from_one_side_logs_warning_but_still_runs(caplog):
    forecast_records = make_records({"OU1": 11}, CURRENT_PERIODS, f"pridec_forecast_{DISEASE_CODE}Avg")
    historic_records = make_records({"OU1": 5, "OU2": 20}, HIST_PERIODS, f"pridec_historic_{DISEASE_CODE}")

    with caplog.at_level("WARNING"):
        result = calc_orgUnit_alerts(
            **BASE_KWARGS,
            forecast_json=wrap(forecast_records),
            historic_json=wrap(historic_records),
        )

    assert "OU2" in caplog.text
    assert "dropped from comparison" in caplog.text
    # OU2 has no forecast data, so only OU1 is compared -> alert count 1
    assert result["dataValues"][0]["value"] == 1


def test_no_overlapping_orgUnits_raises():
    forecast_records = make_records({"OU1": 11}, CURRENT_PERIODS, f"pridec_forecast_{DISEASE_CODE}Avg")
    historic_records = make_records({"OU2": 5}, HIST_PERIODS, f"pridec_historic_{DISEASE_CODE}")

    with pytest.raises(ValueError, match="orgUnits in historic data are not found in forecast data"):
        calc_orgUnit_alerts(
            **BASE_KWARGS,
            forecast_json=wrap(forecast_records),
            historic_json=wrap(historic_records),
        )


# =============================================================================
# Core behavior: correct alert count and output shape
# =============================================================================
@pytest.mark.parametrize("wrap_data", [True, False], ids=["wrapped_dataValues", "raw_list"])
def test_successful_alert_calculation(wrap_data):
    # OU1: forecast mean (11) > historic mean (5)  -> on alert
    # OU2: forecast mean (5)  < historic mean (10)  -> not on alert
    forecast_records = default_forecast_records({"OU1": 11, "OU2": 5})
    historic_records = default_historic_records({"OU1": 5, "OU2": 10})

    forecast_input = wrap(forecast_records) if wrap_data else forecast_records
    historic_input = wrap(historic_records) if wrap_data else historic_records

    result = calc_orgUnit_alerts(
        **BASE_KWARGS,
        forecast_json=forecast_input,
        historic_json=historic_input,
    )

    assert result == {
        "dataValues": [
            {
                "dataElement": f"pridec_alert_{ALERT_NAME}",
                "orgUnit": BASE_KWARGS["parent_ou"],
                "period": "202603",
                "value": 1,
            }
        ]
    }


def test_alert_name_defaults_to_disease_code_when_not_supplied():
    kwargs = {**BASE_KWARGS}
    kwargs.pop("alert_name")
    result = calc_orgUnit_alerts(
        **kwargs,
        forecast_json=wrap(default_forecast_records()),
        historic_json=wrap(default_historic_records()),
    )
    assert result["dataValues"][0]["dataElement"] == f"pridec_alert_{DISEASE_CODE}"


def test_original_input_data_not_mutated():
    # Guards against accidental in-place mutation of caller-supplied dicts.
    forecast_input = wrap(default_forecast_records())
    historic_input = wrap(default_historic_records())
    forecast_copy = copy.deepcopy(forecast_input)
    historic_copy = copy.deepcopy(historic_input)

    calc_orgUnit_alerts(
        **BASE_KWARGS,
        forecast_json=forecast_input,
        historic_json=historic_input,
    )

    assert forecast_input == forecast_copy
    assert historic_input == historic_copy


# =============================================================================
# DHIS2 fetch path (forecast_data / historic_data = None)
# =============================================================================
def test_fetches_from_dhis2_when_no_local_data_provided(monkeypatch):
    def fake_get_dataElements(dhis_url, dx_query, ou_query, pe_query, token, dx_id_scheme):
        if "forecast" in dx_query:
            df = pd.DataFrame(default_forecast_records())
        else:
            df = pd.DataFrame(default_historic_records())
        return df.rename(columns={"orgUnit": "ou", "period": "pe", "dataElement": "dx"})[
            ["dx", "ou", "pe", "value"]
        ]

    monkeypatch.setattr(com_mod, "get_dataElements", fake_get_dataElements)

    result = calc_orgUnit_alerts(**BASE_KWARGS, forecast_json=None, historic_json=None)
    assert result["dataValues"][0]["value"] == 1