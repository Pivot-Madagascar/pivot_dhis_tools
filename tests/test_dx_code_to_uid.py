"""
Tests for dx_code_to_uid.py::dx_code_to_uid.

HTTP calls are mocked. The live test is read-only and runs only when
TEST_URL / TEST_TOKEN are set.
"""
import importlib
import json
import os

import pytest
import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

from pivot_dhis_tools import dx_code_to_uid

# the package __init__ re-exports the function under the module's name, so fetch the module itself
mod = importlib.import_module("pivot_dhis_tools.dx_code_to_uid")

# module level so the skipif on the live test sees the .env values
load_dotenv()

URL = "https://dhis.example.org"


def _response(body, status=200, url=URL):
    resp = requests.Response()
    resp.status_code = status
    resp._content = json.dumps(body).encode()
    resp.url = url
    return resp


@pytest.fixture
def fake_api(monkeypatch):
    """Patch requests.get. Set `.bodies` / `.status` (keyed by endpoint) to control
    responses; every call is recorded in `.calls`."""

    class Api:
        bodies = {
            "dataElements": {"dataElements": [{"id": "deUid00001", "code": "de_code"}]},
            "indicators": {"indicators": [{"id": "inUid00001", "code": "ind_code"}]},
        }
        status = {}
        calls = []

    api = Api()

    def fake_get(url, **kwargs):
        api.calls.append({"url": url, **kwargs})
        endpoint = "indicators" if "/api/indicators" in url else "dataElements"
        return _response(api.bodies[endpoint], api.status.get(endpoint, 200), url)

    monkeypatch.setattr(mod.requests, "get", fake_get)
    return api


def test_maps_dataElement_and_indicator_codes(fake_api):
    assert dx_code_to_uid(URL, ["de_code", "ind_code"], token="t") == {
        "de_code": "deUid00001",
        "ind_code": "inUid00001",
    }


def test_queries_both_endpoints_with_code_filter(fake_api):
    dx_code_to_uid(URL + "/", ["a", "b"], token="t")
    assert [c["url"] for c in fake_api.calls] == [
        f"{URL}/api/dataElements.json",
        f"{URL}/api/indicators.json",
    ]
    for call in fake_api.calls:
        assert call["params"] == {"filter": "code:in:[a,b]", "fields": "id,code", "paging": "false"}
        assert call["timeout"] == 600


def test_indicator_wins_when_code_exists_in_both(fake_api):
    fake_api.bodies = {
        "dataElements": {"dataElements": [{"id": "deUid00001", "code": "shared"}]},
        "indicators": {"indicators": [{"id": "inUid00001", "code": "shared"}]},
    }
    assert dx_code_to_uid(URL, ["shared"], token="t") == {"shared": "inUid00001"}


def test_missing_codes_are_left_out_and_warned(fake_api, caplog):
    fake_api.bodies = {**fake_api.bodies, "indicators": {"indicators": []}}
    with caplog.at_level("WARNING"):
        out = dx_code_to_uid(URL, ["de_code", "nope"], token="t")
    assert out == {"de_code": "deUid00001"}
    assert "nope" in caplog.text


def test_items_without_code_are_ignored(fake_api):
    fake_api.bodies = {"dataElements": {"dataElements": [{"id": "x"}]}, "indicators": {}}
    assert dx_code_to_uid(URL, ["a"], token="t") == {}


def test_token_auth(fake_api):
    dx_code_to_uid(URL, ["a"], token="abc")
    for call in fake_api.calls:
        assert call["headers"] == {"Authorization": "ApiToken abc"}
        assert call["auth"] is None


def test_basic_auth(fake_api):
    dx_code_to_uid(URL, ["a"], user="u", pwd="p")
    for call in fake_api.calls:
        assert isinstance(call["auth"], HTTPBasicAuth)


@pytest.mark.parametrize("kwargs", [{}, {"user": "u"}, {"pwd": "p"}])
def test_missing_credentials_raises_before_request(fake_api, kwargs):
    with pytest.raises(ValueError, match="Authentication required"):
        dx_code_to_uid(URL, ["a"], **kwargs)
    assert fake_api.calls == []


@pytest.mark.parametrize("endpoint", ["dataElements", "indicators"])
def test_http_error_logs_and_raises(fake_api, caplog, endpoint):
    fake_api.status = {endpoint: 401}
    with caplog.at_level("ERROR"), pytest.raises(requests.HTTPError):
        dx_code_to_uid(URL, ["a"], token="t")
    assert f"Failed to look up {endpoint} codes: HTTP 401" in caplog.text


# ---- live ----

@pytest.mark.live
@pytest.mark.skipif(not (os.getenv("TEST_URL") and os.getenv("TEST_TOKEN")),
                    reason="TEST_URL / TEST_TOKEN not set")
def test_live_lookup():
    """Read-only: looks up a known PRIDE-C code and a made-up one on TEST_URL."""
    out = dx_code_to_uid(os.getenv("TEST_URL"),
                         ["pridec_climate_temperatureMean", "pridec_climate_fakeVariable"],
                         token=os.getenv("TEST_TOKEN"))
    assert list(out) == ["pridec_climate_temperatureMean"]
    assert len(out["pridec_climate_temperatureMean"]) == 11  # DHIS2 UIDs are 11 characters
