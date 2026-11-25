"""
Tests for pridec/fetch_pridec_disease.py::fetch_disease.

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

import pivot_dhis_tools.pridec.fetch_pridec_disease as mod

# module level so the skipif on the live test sees the .env values
load_dotenv()

URL = "https://dhis.example.org"
CODE = "pridec_historic_CSBMalaria"

# analytics headers deliberately not in dx/ou/pe/value order to check the name lookup
ANALYTICS_HEADERS = [{"name": "pe"}, {"name": "dx"}, {"name": "value"}, {"name": "ou"}]


def _response(body, status=200, url=URL):
    resp = requests.Response()
    resp.status_code = status
    resp._content = json.dumps(body).encode()
    resp.url = url
    return resp


class FixedDate(dt.date):
    @classmethod
    def today(cls):
        return cls(2026, 11, 25)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setattr(mod, "date", FixedDate)


@pytest.fixture
def fake_api(monkeypatch):
    """Patch requests.get. Set `.de_body` / `.analytics` / `.status` to control
    responses; every call is recorded in `.calls`."""

    class Api:
        de_body = {"dataElements": [{"id": "deMal00001", "code": CODE, "displayName": "Malaria"}]}
        analytics = {
            "headers": ANALYTICS_HEADERS,
            "rows": [
                ["202510", "deMal00001", "42", "ouA"],
                ["202509", "deMal00001", "0", "ouB"],
            ],
        }
        status = {}  # "dataElements" or "analytics" -> status code
        calls = []

    api = Api()

    def fake_get(url, headers=None, auth=None, timeout=None, **kwargs):
        api.calls.append({"url": url, "headers": headers, "auth": auth, "timeout": timeout})
        if "/api/dataElements" in url:
            return _response(api.de_body, api.status.get("dataElements", 200), url)
        return _response(api.analytics, api.status.get("analytics", 200), url)

    monkeypatch.setattr(mod.requests, "get", fake_get)
    return api


def _query(call):
    return parse_qs(urlparse(call["url"]).query)


def _periods(call):
    return _query(call)["dimension"][2].removeprefix("pe:").split(";")


# ---- output ----

def test_returns_flattened_values(fake_api):
    assert mod.fetch_disease(URL, 5, "parentOU01", CODE, token="abc") == [
        {"orgUnit": "ouA", "period": "202510", "dataElement": CODE, "value": 42.0},
        {"orgUnit": "ouB", "period": "202509", "dataElement": CODE, "value": 0.0},
    ]


def test_values_are_floats(fake_api):
    result = mod.fetch_disease(URL, 5, "parentOU01", CODE, token="abc")
    assert all(isinstance(r["value"], float) for r in result)


@pytest.mark.parametrize("body", [{"headers": ANALYTICS_HEADERS, "rows": []}, {}])
def test_no_rows_returns_empty_list(fake_api, body):
    fake_api.analytics = body
    assert mod.fetch_disease(URL, 5, "parentOU01", CODE, token="abc") == []


def test_data_element_is_the_requested_code(fake_api):
    # the output uses the code passed in, even if the matched element's code differs
    fake_api.de_body = {"dataElements": [{"id": "deMal00001", "code": CODE + "_v2"}]}
    result = mod.fetch_disease(URL, 5, "parentOU01", CODE, token="abc")
    assert {r["dataElement"] for r in result} == {CODE}


# ---- requests sent ----

def test_lookup_then_single_analytics_call(fake_api):
    mod.fetch_disease(URL, 5, "parentOU01", CODE, token="abc")
    assert len(fake_api.calls) == 2

    lookup = _query(fake_api.calls[0])
    assert fake_api.calls[0]["url"].startswith(f"{URL}/api/dataElements?")
    assert lookup["filter"] == [f"code:eq:{CODE}"]
    assert lookup["paging"] == ["false"]

    dims = _query(fake_api.calls[1])["dimension"]
    assert fake_api.calls[1]["url"].startswith(f"{URL}/api/analytics.json?")
    assert dims[0] == "dx:deMal00001"
    assert dims[1] == "ou:LEVEL-5;parentOU01"


def test_first_match_used_when_several_elements_match(fake_api):
    fake_api.de_body = {"dataElements": [
        {"id": "deFirst001", "code": CODE},
        {"id": "deSecond01", "code": CODE + "_lag"},
    ]}
    mod.fetch_disease(URL, 5, "parentOU01", CODE, token="abc")
    assert _query(fake_api.calls[1])["dimension"][0] == "dx:deFirst001"


def test_period_range_defaults_to_six_years_ending_last_month(fake_api):
    mod.fetch_disease(URL, 5, "parentOU01", CODE, token="abc")
    periods = _periods(fake_api.calls[1])
    assert len(periods) == 72
    assert (periods[0], periods[-1]) == ("202011", "202610")  # current month excluded


def test_past_years_controls_period_range(fake_api):
    mod.fetch_disease(URL, 5, "parentOU01", CODE, token="abc", past_years=2)
    periods = _periods(fake_api.calls[1])
    assert len(periods) == 24
    assert (periods[0], periods[-1]) == ("202411", "202610")


def test_trailing_slash_in_url_is_dropped(fake_api):
    mod.fetch_disease(URL + "/", 5, "parentOU01", CODE, token="abc")
    assert fake_api.calls[0]["url"].startswith(f"{URL}/api/dataElements?")
    assert fake_api.calls[1]["url"].startswith(f"{URL}/api/analytics.json?")


def test_default_timeout_on_every_request(fake_api):
    mod.fetch_disease(URL, 5, "parentOU01", CODE, token="abc")
    assert [c["timeout"] for c in fake_api.calls] == [300, 300]


def test_custom_timeout_on_every_request(fake_api):
    mod.fetch_disease(URL, 5, "parentOU01", CODE, token="abc", timeout=5)
    assert [c["timeout"] for c in fake_api.calls] == [5, 5]


# ---- authentication ----

def test_token_sent_on_every_request(fake_api):
    mod.fetch_disease(URL, 5, "parentOU01", CODE, token="abc")
    for call in fake_api.calls:
        assert call["headers"] == {"Authorization": "ApiToken abc"}
        assert call["auth"] is None


def test_basic_auth_sent_on_every_request(fake_api):
    mod.fetch_disease(URL, 5, "parentOU01", CODE, user="u", pwd="p")
    for call in fake_api.calls:
        assert isinstance(call["auth"], HTTPBasicAuth)
        assert (call["auth"].username, call["auth"].password) == ("u", "p")


@pytest.mark.parametrize("kwargs", [{}, {"user": "u"}, {"pwd": "p"}])
def test_missing_credentials_raises_before_any_request(fake_api, kwargs):
    with pytest.raises(ValueError, match="Authentication required"):
        mod.fetch_disease(URL, 5, "parentOU01", CODE, **kwargs)
    assert fake_api.calls == []


# ---- errors ----

def test_unknown_disease_code_raises(fake_api):
    fake_api.de_body = {"dataElements": []}
    with pytest.raises(ValueError, match=f"No dataElements found with code {CODE}"):
        mod.fetch_disease(URL, 5, "parentOU01", CODE, token="abc")
    assert len(fake_api.calls) == 1  # no analytics call


@pytest.mark.parametrize("which", ["dataElements", "analytics"])
def test_http_error_raises(fake_api, which):
    fake_api.status = {which: 409}
    with pytest.raises(requests.HTTPError):
        mod.fetch_disease(URL, 5, "parentOU01", CODE, token="abc")


def test_timeout_propagates(monkeypatch):
    def slow(*args, **kwargs):
        raise requests.Timeout("too slow")
    monkeypatch.setattr(mod.requests, "get", slow)
    with pytest.raises(requests.Timeout):
        mod.fetch_disease(URL, 5, "parentOU01", CODE, token="abc", timeout=1)


# ---- live ----

@pytest.mark.live
@pytest.mark.skipif(not all(os.getenv(v) for v in ("TEST_URL", "TEST_TOKEN")),
                    reason="TEST_URL / TEST_TOKEN not set")
def test_live_fetch_disease(monkeypatch):
    """Read-only: fetches 1 year of CSB malaria data from TEST_URL."""
    monkeypatch.setattr(mod, "date", dt.date)  # undo the fixed date
    result = mod.fetch_disease(os.getenv("TEST_URL"), 5, 'VtP4BdCeXIo', CODE,
                               token=os.getenv("TEST_TOKEN"), past_years=1)
    assert isinstance(result, list)
    for row in result:
        assert set(row) == {"orgUnit", "period", "dataElement", "value"}
        assert row["dataElement"] == CODE
