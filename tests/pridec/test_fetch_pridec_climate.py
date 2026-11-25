"""
Tests for pridec/fetch_pridec_climate.py::fetch_climate.

HTTP calls are mocked by patching `requests.get` in the module; the live
test at the bottom is read-only and only runs when TEST_URL / TEST_TOKEN are set.
"""
import datetime as dt
import json
import os
from urllib.parse import parse_qs, urlparse

import pytest
import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

import pivot_dhis_tools.pridec.fetch_pridec_climate as mod

# module level so the skipif on the live test sees the .env values
load_dotenv()

URL = "https://dhis.example.org"

DATA_ELEMENTS = [
    {"id": "deRain0001", "code": "pridec_climate_rain", "displayName": "Rain"},
    {"id": "deTemp0001", "code": "pridec_climate_temp", "displayName": "Temp"},
]

# analytics headers deliberately not in dx/ou/pe/value order to check the name lookup
ANALYTICS_HEADERS = [{"name": "pe"}, {"name": "dx"}, {"name": "value"}, {"name": "ou"}]


def _response(body, status=200, url=URL):
    resp = requests.Response()
    resp.status_code = status
    resp._content = json.dumps(body).encode()
    resp.url = url
    return resp


def _analytics(rows):
    return {"headers": ANALYTICS_HEADERS, "rows": rows}


class FixedDate(dt.date):
    @classmethod
    def today(cls):
        return cls(2026, 11, 25)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(mod, "date", FixedDate)


@pytest.fixture
def fake_api(monkeypatch):
    """Patch requests.get. Set `.de_body` / `.analytics` (uid -> body) / `.status`
    to control responses; every call is recorded in `.calls`."""

    class Api:
        de_body = {"dataElements": DATA_ELEMENTS}
        analytics = {
            "deRain0001": _analytics([
                ["202510", "deRain0001", "12.5", "ouA"],
                ["202510", "deRain0001", "0", "ouB"],
            ]),
            "deTemp0001": _analytics([["202509", "deTemp0001", "24", "ouA"]]),
        }
        status = {}  # "dataElements" or uid -> status code
        calls = []

    api = Api()

    def fake_get(url, headers=None, auth=None, timeout=None, **kwargs):
        api.calls.append({"url": url, "headers": headers, "auth": auth, "timeout": timeout})
        if "/api/dataElements" in url:
            return _response(api.de_body, api.status.get("dataElements", 200), url)
        uid = parse_qs(urlparse(url).query)["dimension"][0].removeprefix("dx:")
        return _response(api.analytics.get(uid, {}), api.status.get(uid, 200), url)

    monkeypatch.setattr(mod.requests, "get", fake_get)
    return api


def _query(call):
    return parse_qs(urlparse(call["url"]).query)


# ---- output ----

def test_returns_flattened_values(fake_api):
    result = mod.fetch_climate(URL, 5, "parentOU01", token="abc")
    assert result == [
        {"orgUnit": "ouA", "period": "202510", "dataElement": "pridec_climate_rain", "value": 12.5},
        {"orgUnit": "ouB", "period": "202510", "dataElement": "pridec_climate_rain", "value": 0.0},
        {"orgUnit": "ouA", "period": "202509", "dataElement": "pridec_climate_temp", "value": 24.0},
    ]


def test_values_are_floats(fake_api):
    result = mod.fetch_climate(URL, 5, "parentOU01", token="abc")
    assert all(isinstance(r["value"], float) for r in result)


def test_no_rows_returns_empty_list(fake_api):
    fake_api.analytics = {"deRain0001": {"headers": ANALYTICS_HEADERS, "rows": []},
                          "deTemp0001": {}}  # no headers/rows keys at all
    assert mod.fetch_climate(URL, 5, "parentOU01", token="abc") == []


# ---- requests sent ----

def test_lookup_then_one_analytics_call_per_element(fake_api):
    mod.fetch_climate(URL, 5, "parentOU01", token="abc")
    assert len(fake_api.calls) == 1 + len(DATA_ELEMENTS)

    lookup = _query(fake_api.calls[0])
    assert fake_api.calls[0]["url"].startswith(f"{URL}/api/dataElements?")
    assert lookup["filter"] == ["code:like:pridec_climate"]
    assert lookup["paging"] == ["false"]

    dx = [_query(c)["dimension"][0] for c in fake_api.calls[1:]]
    assert dx == ["dx:deRain0001", "dx:deTemp0001"]


def test_analytics_orgunit_dimension(fake_api):
    mod.fetch_climate(URL, 4, "parentOU01", token="abc")
    for call in fake_api.calls[1:]:
        assert "ou:LEVEL-4;parentOU01" in _query(call)["dimension"]


def test_period_range_defaults_to_ten_years_ending_last_month(fake_api):
    mod.fetch_climate(URL, 5, "parentOU01", token="abc")
    pe = _query(fake_api.calls[1])["dimension"][2]
    periods = pe.removeprefix("pe:").split(";")
    assert len(periods) == 120
    assert periods[0] == "201611"
    assert periods[-1] == "202610"  # current month (2026-11) excluded


def test_past_years_controls_period_range(fake_api):
    mod.fetch_climate(URL, 5, "parentOU01", token="abc", past_years=2)
    periods = _query(fake_api.calls[1])["dimension"][2].removeprefix("pe:").split(";")
    assert len(periods) == 24
    assert (periods[0], periods[-1]) == ("202411", "202610")


def test_trailing_slash_in_url_is_dropped(fake_api):
    mod.fetch_climate(URL + "/", 5, "parentOU01", token="abc")
    assert fake_api.calls[0]["url"].startswith(f"{URL}/api/dataElements?")
    assert fake_api.calls[1]["url"].startswith(f"{URL}/api/analytics.json?")
    assert not any("//api" in c["url"] for c in fake_api.calls)


def test_default_timeout_on_every_request(fake_api):
    mod.fetch_climate(URL, 5, "parentOU01", token="abc")
    assert [c["timeout"] for c in fake_api.calls] == [300] * len(fake_api.calls)


def test_custom_timeout_on_every_request(fake_api):
    mod.fetch_climate(URL, 5, "parentOU01", token="abc", timeout=5)
    assert [c["timeout"] for c in fake_api.calls] == [5] * len(fake_api.calls)


# ---- authentication ----

def test_token_sent_on_every_request(fake_api):
    mod.fetch_climate(URL, 5, "parentOU01", token="abc")
    for call in fake_api.calls:
        assert call["headers"] == {"Authorization": "ApiToken abc"}
        assert call["auth"] is None


def test_basic_auth_sent_on_every_request(fake_api):
    mod.fetch_climate(URL, 5, "parentOU01", user="u", pwd="p")
    for call in fake_api.calls:
        assert isinstance(call["auth"], HTTPBasicAuth)
        assert (call["auth"].username, call["auth"].password) == ("u", "p")


@pytest.mark.parametrize("kwargs", [{}, {"user": "u"}, {"pwd": "p"}])
def test_missing_credentials_raises_before_any_request(fake_api, kwargs):
    with pytest.raises(ValueError, match="Authentication required"):
        mod.fetch_climate(URL, 5, "parentOU01", **kwargs)
    assert fake_api.calls == []


# ---- errors ----

def test_no_climate_data_elements_raises(fake_api):
    fake_api.de_body = {"dataElements": []}
    with pytest.raises(ValueError, match="No dataElements found"):
        mod.fetch_climate(URL, 5, "parentOU01", token="abc")
    assert len(fake_api.calls) == 1  # no analytics calls


def test_lookup_http_error_raises(fake_api):
    fake_api.status = {"dataElements": 401}
    with pytest.raises(requests.HTTPError):
        mod.fetch_climate(URL, 5, "parentOU01", token="abc")


def test_analytics_http_error_raises(fake_api):
    fake_api.status = {"deTemp0001": 409}
    with pytest.raises(requests.HTTPError):
        mod.fetch_climate(URL, 5, "parentOU01", token="abc")


def test_timeout_propagates(monkeypatch):
    def slow(*args, **kwargs):
        raise requests.Timeout("too slow")
    monkeypatch.setattr(mod.requests, "get", slow)
    with pytest.raises(requests.Timeout):
        mod.fetch_climate(URL, 5, "parentOU01", token="abc", timeout=1)


# ---- live ----

@pytest.mark.live
@pytest.mark.skipif(not all(os.getenv(v) for v in ("TEST_URL", "TEST_TOKEN")),
                    reason="TEST_URL / TEST_TOKEN not set")
def test_live_fetch_climate(monkeypatch):
    """Read-only: fetches 1 year of climate data from TEST_URL."""
    monkeypatch.setattr(mod, "date", dt.date)  # undo the fixed date
    result = mod.fetch_climate(os.getenv("TEST_URL"), 5, 'VtP4BdCeXIo',
                               token=os.getenv("TEST_TOKEN"), past_years=1)
    assert isinstance(result, list)
    assert result, "no climate data returned"
    for row in result:
        assert set(row) == {"orgUnit", "period", "dataElement", "value"}
        assert row["dataElement"].startswith("pridec_climate")
