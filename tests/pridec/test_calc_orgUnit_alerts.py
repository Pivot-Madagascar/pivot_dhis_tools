"""
Tests for calc_orgUnit_alerts and its input-validation guards.

Package layout (src-layout):
    src/pivot_dhis_tools/get_dataElements.py
    src/pivot_dhis_tools/pridec/calc_orgUnit_alerts.py

Requires the package to be importable, e.g. via `pip install -e .` from the
repo root, or a pytest `pythonpath = ["src"]` setting in pyproject.toml/pytest.ini.
"""
import copy
import os
from datetime import date

import pandas as pd
import pytest
from dotenv import load_dotenv

# module level so the skipif on the live test sees the .env values
load_dotenv()

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


def to_analytics_df(records: list) -> pd.DataFrame:
    """Convert records to the dx/ou/pe/value shape that get_dataElements returns."""
    df = pd.DataFrame(records)
    return df.rename(columns={"orgUnit": "ou", "period": "pe", "dataElement": "dx"})[
        ["dx", "ou", "pe", "value"]
    ]


@pytest.fixture
def fake_fetch(monkeypatch):
    """Replace get_dataElements with a fake that records its kwargs.

    Returns the list of captured calls. Forecast queries get the default forecast
    records, historic queries the default historic records.
    """
    calls = []

    def fake_get_dataElements(**kwargs):
        calls.append(kwargs)
        if "forecast" in kwargs["dx_query"]:
            return to_analytics_df(default_forecast_records())
        return to_analytics_df(default_historic_records())

    monkeypatch.setattr(com_mod, "get_dataElements", fake_get_dataElements)
    return calls


@pytest.fixture
def no_fetch(monkeypatch):
    """Fail the test if get_dataElements is called at all."""
    def boom(**kwargs):
        raise AssertionError(f"get_dataElements should not be called, got {kwargs}")

    monkeypatch.setattr(com_mod, "get_dataElements", boom)


# =============================================================================
# Guard: must supply token/user+pwd if either dataset needs to be fetched
# =============================================================================
def test_requires_token_or_credentials_when_no_local_data():
    kwargs = {**BASE_KWARGS}
    kwargs.pop("token")
    with pytest.raises(ValueError, match="Authentication required"):
        calc_orgUnit_alerts(**kwargs, forecast_json=None, historic_json=None)


def test_does_not_require_credentials_when_both_datasets_provided_locally(no_fetch):
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
def test_fetches_from_dhis2_when_no_local_data_provided(fake_fetch):
    result = calc_orgUnit_alerts(**BASE_KWARGS, forecast_json=None, historic_json=None)
    assert result["dataValues"][0]["value"] == 1
    assert len(fake_fetch) == 2


def test_fetch_queries_sent_to_dhis2(fake_fetch):
    calc_orgUnit_alerts(**BASE_KWARGS, forecast_json=None, historic_json=None)
    forecast_call, historic_call = fake_fetch

    expected_ou = f"ou:LEVEL-{BASE_KWARGS['ou_level']};{BASE_KWARGS['parent_ou']}"

    assert forecast_call["dhis_url"] == BASE_KWARGS["dhis_url"]
    assert forecast_call["dx_query"] == f"dx:pridec_forecast_{DISEASE_CODE}Avg"
    assert forecast_call["ou_query"] == expected_ou
    assert forecast_call["pe_query"] == "pe:" + ";".join(CURRENT_PERIODS)
    assert forecast_call["dx_id_scheme"] == "CODE"

    assert historic_call["dx_query"] == f"dx:pridec_historic_{DISEASE_CODE}"
    assert historic_call["ou_query"] == expected_ou
    assert set(historic_call["pe_query"].removeprefix("pe:").split(";")) == set(HIST_PERIODS)
    assert historic_call["dx_id_scheme"] == "CODE"


def test_token_forwarded_to_get_dataElements(fake_fetch):
    calc_orgUnit_alerts(**BASE_KWARGS, forecast_json=None, historic_json=None)
    for call in fake_fetch:
        assert call["token"] == BASE_KWARGS["token"]


def test_user_pwd_forwarded_to_get_dataElements(fake_fetch):
    kwargs = {**BASE_KWARGS}
    kwargs.pop("token")
    result = calc_orgUnit_alerts(**kwargs, user="u", pwd="p",
                                 forecast_json=None, historic_json=None)
    assert result["dataValues"][0]["value"] == 1
    assert len(fake_fetch) == 2
    for call in fake_fetch:
        assert call["user"] == "u"
        assert call["pwd"] == "p"
        assert call["token"] is None


@pytest.mark.parametrize("missing", ["forecast", "historic"])
def test_one_local_dataset_still_requires_credentials(missing, no_fetch):
    kwargs = {**BASE_KWARGS}
    kwargs.pop("token")
    local = {
        "forecast_json": wrap(default_forecast_records()),
        "historic_json": wrap(default_historic_records()),
    }
    local[f"{missing}_json"] = None
    with pytest.raises(ValueError, match="Authentication required"):
        calc_orgUnit_alerts(**kwargs, **local)


def test_only_missing_dataset_is_fetched(fake_fetch):
    result = calc_orgUnit_alerts(
        **BASE_KWARGS,
        forecast_json=wrap(default_forecast_records()),
        historic_json=None,
    )
    assert result["dataValues"][0]["value"] == 1
    assert len(fake_fetch) == 1
    assert "historic" in fake_fetch[0]["dx_query"]


def test_empty_dhis2_response_raises(monkeypatch):
    def empty_fetch(**kwargs):
        return pd.DataFrame(columns=["dx", "ou", "pe", "value"])

    monkeypatch.setattr(com_mod, "get_dataElements", empty_fetch)
    with pytest.raises(ValueError, match="No forecasts exist for the period query"):
        calc_orgUnit_alerts(**BASE_KWARGS, forecast_json=None, historic_json=None)


# =============================================================================
# Period / focal_date handling
# =============================================================================
def run_with_periods(focal_date, current_periods, hist_periods, **extra):
    """Run with local data built for the given periods (OU1 on alert, OU2 not)."""
    kwargs = {**BASE_KWARGS, "focal_date": focal_date, **extra}
    if focal_date is None:
        kwargs.pop("focal_date")
    return calc_orgUnit_alerts(
        **kwargs,
        forecast_json=make_records({"OU1": 11, "OU2": 5}, current_periods,
                                   f"pridec_forecast_{DISEASE_CODE}Avg"),
        historic_json=make_records({"OU1": 5, "OU2": 10}, hist_periods,
                                   f"pridec_historic_{DISEASE_CODE}"),
    )


def test_year_rollover_periods():
    # Nov 2026 window runs into Jan 2027; historic window runs into Jan 2024-2026
    current = ["202611", "202612", "202701"]
    hist = ["202511", "202411", "202311",
            "202512", "202412", "202312",
            "202601", "202501", "202401"]
    result = run_with_periods(date(2026, 11, 1), current, hist)
    assert result["dataValues"][0]["period"] == "202611"
    assert result["dataValues"][0]["value"] == 1


def test_year_rollover_queries(monkeypatch):
    calls = []

    def fake(**kwargs):
        calls.append(kwargs)
        return pd.DataFrame(columns=["dx", "ou", "pe", "value"])

    monkeypatch.setattr(com_mod, "get_dataElements", fake)
    with pytest.raises(ValueError):  # empty data; we only care about the query
        calc_orgUnit_alerts(**{**BASE_KWARGS, "focal_date": date(2026, 12, 1)},
                            forecast_json=None, historic_json=None)
    assert calls[0]["pe_query"] == "pe:202612;202701;202702"


def test_mid_month_focal_date_uses_first_of_month():
    result = run_with_periods(date(2026, 3, 17), CURRENT_PERIODS, HIST_PERIODS)
    assert result["dataValues"][0]["period"] == "202603"
    assert result["dataValues"][0]["value"] == 1


def test_focal_date_none_defaults_to_today(monkeypatch):
    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 3, 20)

    monkeypatch.setattr(com_mod, "date", FixedDate)
    result = run_with_periods(None, CURRENT_PERIODS, HIST_PERIODS)
    assert result["dataValues"][0]["period"] == "202603"
    assert result["dataValues"][0]["value"] == 1


# =============================================================================
# Alert calculation details
# =============================================================================
def test_equal_means_are_not_on_alert():
    result = calc_orgUnit_alerts(
        **BASE_KWARGS,
        forecast_json=default_forecast_records({"OU1": 7}),
        historic_json=default_historic_records({"OU1": 7}),
    )
    assert result["dataValues"][0]["value"] == 0


def test_zero_alerts_returns_zero_not_error():
    result = calc_orgUnit_alerts(
        **BASE_KWARGS,
        forecast_json=default_forecast_records({"OU1": 1, "OU2": 2}),
        historic_json=default_historic_records({"OU1": 10, "OU2": 20}),
    )
    assert result["dataValues"] == [{
        "dataElement": f"pridec_alert_{ALERT_NAME}",
        "orgUnit": BASE_KWARGS["parent_ou"],
        "period": "202603",
        "value": 0,
    }]


def test_string_values_are_coerced():
    # DHIS2 exports send values as strings
    forecast = default_forecast_records()
    historic = default_historic_records()
    for r in forecast + historic:
        r["value"] = str(r["value"])
    result = calc_orgUnit_alerts(**BASE_KWARGS, forecast_json=forecast, historic_json=historic)
    assert result["dataValues"][0]["value"] == 1


def test_alert_uses_mean_across_periods():
    # OU1 forecast 2, 2, 20 -> mean 8; historic flat 7 -> on alert (max or first value would differ)
    # OU2 forecast 9, 1, 1 -> mean 3.67; historic flat 4 -> not on alert (first value 9 would alert)
    dx = f"pridec_forecast_{DISEASE_CODE}Avg"
    forecast = [
        {"dataElement": dx, "orgUnit": "OU1", "period": p, "value": v}
        for p, v in zip(CURRENT_PERIODS, [2, 2, 20])
    ] + [
        {"dataElement": dx, "orgUnit": "OU2", "period": p, "value": v}
        for p, v in zip(CURRENT_PERIODS, [9, 1, 1])
    ]
    historic = default_historic_records({"OU1": 7, "OU2": 4})
    result = calc_orgUnit_alerts(**BASE_KWARGS, forecast_json=forecast, historic_json=historic)
    assert result["dataValues"][0]["value"] == 1


def test_rows_outside_window_or_other_dataElements_ignored():
    # Without filtering, the 202606 forecast and the other-disease rows would push OU2 onto alert,
    # and the 202203 historic row would pull OU1's historic mean up so it fell off alert.
    forecast = default_forecast_records() + [
        {"dataElement": f"pridec_forecast_{DISEASE_CODE}Avg", "orgUnit": "OU2",
         "period": "202606", "value": 10_000},
        {"dataElement": "pridec_forecast_OtherAvg", "orgUnit": "OU2",
         "period": "202603", "value": 10_000},
    ]
    historic = default_historic_records() + [
        {"dataElement": f"pridec_historic_{DISEASE_CODE}", "orgUnit": "OU1",
         "period": "202203", "value": 10_000},
        {"dataElement": "pridec_historic_Other", "orgUnit": "OU1",
         "period": "202503", "value": 10_000},
    ]
    result = calc_orgUnit_alerts(**BASE_KWARGS, forecast_json=forecast, historic_json=historic)
    assert result["dataValues"][0]["value"] == 1

# =============================================================================
# Live: TEST instance (read-only; nothing is posted)
# =============================================================================
@pytest.mark.live
@pytest.mark.skipif(not (os.getenv("TEST_URL") and os.getenv("TEST_TOKEN")),
                    reason="TEST_URL / TEST_TOKEN not set")
def test_live_calc_against_test_instance(monkeypatch):
    """Fetches real forecast/historic data from TEST_URL and checks the alert result.

    Also feeds the fetched data back in as local JSON and checks both paths agree,
    so the DHIS2 fetch path and the local-data path are held to the same answer.
    """
    real_get = com_mod.get_dataElements
    fetched = {}

    def spy(**kwargs):
        df = real_get(**kwargs)
        kind = "forecast" if "forecast" in kwargs["dx_query"] else "historic"
        fetched[kind] = df.copy()
        return df

    monkeypatch.setattr(com_mod, "get_dataElements", spy)

    kwargs = {**BASE_KWARGS, "dhis_url": os.getenv("TEST_URL"), "token": os.getenv("TEST_TOKEN")}
    result = calc_orgUnit_alerts(**kwargs, forecast_json=None, historic_json=None)

    assert set(fetched) == {"forecast", "historic"}
    assert not fetched["forecast"].empty and not fetched["historic"].empty

    [dv] = result["dataValues"]
    assert dv["dataElement"] == f"pridec_alert_{ALERT_NAME}"
    assert dv["orgUnit"] == BASE_KWARGS["parent_ou"]
    assert dv["period"] == "202603"
    n_ous = fetched["forecast"]["ou"].nunique()
    assert isinstance(dv["value"], int)
    assert 0 <= dv["value"] <= n_ous

    # same data passed locally must give the same answer
    def to_records(df):
        return df.rename(columns={"ou": "orgUnit", "pe": "period", "dx": "dataElement"})[
            ["dataElement", "orgUnit", "period", "value"]
        ].to_dict(orient="records")

    local_result = calc_orgUnit_alerts(
        **kwargs,
        forecast_json=to_records(fetched["forecast"]),
        historic_json=to_records(fetched["historic"]),
    )
    assert local_result == result
