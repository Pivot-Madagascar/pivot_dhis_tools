"""
Tests for pridec/calc_CSB_alerts.py::calc_CSB_alerts.

get_dataElements is mocked. The live tests are read-only and run only when
TEST_URL / TEST_TOKEN are set.
"""
import os
from datetime import date

import pandas as pd
import pytest
from dotenv import load_dotenv

import pivot_dhis_tools.pridec.calc_CSB_alerts as mod
from pivot_dhis_tools import pridec_calc_CSB_alerts

# module level so the skipif on the live test sees the .env values
load_dotenv()

URL = "https://dhis.example.org"
FOCAL_DATE = date(2026, 3, 1)

FORECAST_DX = {"palu": "Kho6sN2pCZP", "diar": "IqGEQ8eMi9H", "resp": "xSg8GomKjHJ"}
HIST_DX = {"palu": "fxlyV7TBKHn", "diar": "nlqM0kFSov2", "resp": "PVomHTNt4FR"}


def _frame(values: dict, dx: dict, pe: str) -> pd.DataFrame:
    """values: {disease: {orgUnit: value}} -> analytics-shaped DataFrame (string values)."""
    return pd.DataFrame([
        {"dx": dx[disease], "ou": ou, "pe": pe, "value": str(v)}
        for disease, by_ou in values.items()
        for ou, v in by_ou.items()
    ], columns=["dx", "ou", "pe", "value"])


# palu: ouA on alert (10 > 5), ouB not (1 < 5) -> 1
# diar: neither on alert (1 < 5)                -> 0
# resp: both on alert (9 > 1)                   -> 2
FORECAST = {"palu": {"ouA": 10, "ouB": 1}, "diar": {"ouA": 1, "ouB": 1}, "resp": {"ouA": 9, "ouB": 9}}
HISTORIC = {"palu": {"ouA": 5, "ouB": 5}, "diar": {"ouA": 5, "ouB": 5}, "resp": {"ouA": 1, "ouB": 1}}


@pytest.fixture
def fake_fetch(monkeypatch):
    """Replace get_dataElements; `.forecast` / `.historic` set the returned data,
    `.calls` records the kwargs of each call."""

    class Fetch:
        forecast = _frame(FORECAST, FORECAST_DX, "202603")
        historic = _frame(HISTORIC, HIST_DX, "202503")
        calls = []

    fetch = Fetch()

    def fake_get_dataElements(**kwargs):
        fetch.calls.append(kwargs)
        is_forecast = FORECAST_DX["palu"] in kwargs["dx_query"]
        return (fetch.forecast if is_forecast else fetch.historic).copy()

    monkeypatch.setattr(mod, "get_dataElements", fake_get_dataElements)
    return fetch


def test_counts_csbs_on_alert_per_disease(fake_fetch):
    result = pridec_calc_CSB_alerts(URL, token="t", focal_date=FOCAL_DATE)
    by_de = {r["dataElement"]: r for r in result["dataValues"]}
    assert {de: r["value"] for de, r in by_de.items()} == {
        "pridec_alert_CSBMalariaVigilance": 1,
        "pridec_alert_CSBDiarrheaVigilance": 0,
        "pridec_alert_CSBRespinfVigilance": 2,
    }
    assert {r["orgUnit"] for r in result["dataValues"]} == {"VtP4BdCeXIo"}
    assert {r["period"] for r in result["dataValues"]} == {"202603"}


def test_queries_forecast_window_and_prior_three_years(fake_fetch):
    pridec_calc_CSB_alerts(URL, token="t", focal_date=date(2026, 11, 17))
    forecast_call, hist_call = fake_fetch.calls
    assert forecast_call["pe_query"] == "pe:202611;202612;202701"
    assert set(hist_call["pe_query"].removeprefix("pe:").split(";")) == {
        f"{y}{m}" for y, m in [(2025, "11"), (2024, "11"), (2023, "11"),
                               (2025, "12"), (2024, "12"), (2023, "12"),
                               (2026, "01"), (2025, "01"), (2024, "01")]
    }
    for call in fake_fetch.calls:
        assert call["ou_query"] == "ou:LEVEL-5;VtP4BdCeXIo"
        assert call["dhis_url"] == URL
    assert set(forecast_call["dx_query"].removeprefix("dx:").split(";")) == set(FORECAST_DX.values())
    assert set(hist_call["dx_query"].removeprefix("dx:").split(";")) == set(HIST_DX.values())


def test_focal_date_defaults_to_current_month(fake_fetch, monkeypatch):
    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 3, 20)

    monkeypatch.setattr(mod, "date", FixedDate)
    result = pridec_calc_CSB_alerts(URL, token="t")
    assert {r["period"] for r in result["dataValues"]} == {"202603"}


# ---- authentication ----

def test_token_forwarded(fake_fetch):
    pridec_calc_CSB_alerts(URL, token="abc", focal_date=FOCAL_DATE)
    for call in fake_fetch.calls:
        assert (call["token"], call["user"], call["pwd"]) == ("abc", None, None)


def test_user_pwd_forwarded(fake_fetch):
    pridec_calc_CSB_alerts(URL, user="u", pwd="p", focal_date=FOCAL_DATE)
    for call in fake_fetch.calls:
        assert (call["token"], call["user"], call["pwd"]) == (None, "u", "p")


@pytest.mark.parametrize("kwargs", [{}, {"user": "u"}, {"pwd": "p"}])
def test_missing_credentials_raises_before_fetch(fake_fetch, kwargs):
    with pytest.raises(ValueError, match="Authentication required"):
        pridec_calc_CSB_alerts(URL, focal_date=FOCAL_DATE, **kwargs)
    assert fake_fetch.calls == []


# ---- errors ----

def test_no_forecasts_raises(fake_fetch):
    fake_fetch.forecast = pd.DataFrame(columns=["dx", "ou", "pe", "value"])
    with pytest.raises(ValueError, match="No forecasts exist"):
        pridec_calc_CSB_alerts(URL, token="t", focal_date=FOCAL_DATE)
    assert len(fake_fetch.calls) == 1  # historic data not fetched


def test_no_historic_data_raises(fake_fetch):
    fake_fetch.historic = pd.DataFrame(columns=["dx", "ou", "pe", "value"])
    with pytest.raises(ValueError, match="Historical data missing"):
        pridec_calc_CSB_alerts(URL, token="t", focal_date=FOCAL_DATE)


# ---- live ----

LIVE = pytest.mark.skipif(not (os.getenv("TEST_URL") and os.getenv("TEST_TOKEN")),
                          reason="TEST_URL / TEST_TOKEN not set")


@pytest.mark.live
@LIVE
def test_live_calc_csb_alerts():
    """Read-only: computes CSB alerts for Dec 2024 from TEST_URL data."""
    result = pridec_calc_CSB_alerts(os.getenv("TEST_URL"), token=os.getenv("TEST_TOKEN"),
                                    focal_date=date(2024, 12, 1))
    assert result["dataValues"], "no alerts computed"
    for r in result["dataValues"]:
        assert r["dataElement"].startswith("pridec_alert_CSB")
        assert (r["orgUnit"], r["period"]) == ("VtP4BdCeXIo", "202412")
        assert 0 <= r["value"] <= 21  # 21 CSBs in Ifanadiana


@pytest.mark.live
@LIVE
def test_live_no_forecast_raises():
    """Read-only: a month with no forecasts on TEST_URL raises."""
    with pytest.raises(ValueError, match="No forecasts exist"):
        pridec_calc_CSB_alerts(os.getenv("TEST_URL"), token=os.getenv("TEST_TOKEN"),
                               focal_date=date(2099, 1, 1))
