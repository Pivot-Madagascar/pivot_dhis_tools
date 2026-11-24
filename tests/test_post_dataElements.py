import importlib
import os
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

from pivot_dhis_tools import post_dataElements

# the package __init__ re-exports the function under the module's name, so fetch the module itself
mod = importlib.import_module("pivot_dhis_tools.post_dataElements")

# module level so the skipif on the live test sees the .env values
load_dotenv()

example_payload = {
    "dataValues": [
        {
            "orgUnit": "D9UWDj19ljP",
            "period": "202105",
            "value": 61,
            "dataElement": "pridec_forecast_CSBMalariaLowCI",
            "categoryOptionCombo": "pridec_COC_u5"
        },
        {
            "orgUnit": "DDR2w1c1GyE",
            "period": "202105",
            "value": 31,
            "dataElement": "pridec_forecast_CSBMalariaLowCI",
            "categoryOptionCombo": "pridec_COC_u5"
        },
        {
            "orgUnit": "EE6WwIMgQ0F",
            "period": "202105",
            "value": 50,
            "dataElement": "pridec_forecast_CSBMalariaLowCI",
            "categoryOptionCombo": "pridec_COC_u5"
        },
        {
            "orgUnit": "FGM6Ric1YnC",
            "period": "202105",
            "value": 49,
            "dataElement": "pridec_forecast_CSBMalariaLowCI",
            "categoryOptionCombo": "pridec_COC_u5"
        }
    ]
}


def _response(status_code=200, body=b'{"status": "OK"}'):
    resp = requests.Response()
    resp.status_code = status_code
    resp._content = body
    resp.url = "https://dhis.example.org/api/dataValueSets"
    return resp


@pytest.fixture
def captured(monkeypatch):
    """Replace requests.post with a fake; return the list of captured calls."""
    calls = []

    def fake_post(url, headers=None, auth=None, json=None):
        calls.append({"url": url, "headers": headers, "auth": auth, "json": json})
        return _response()

    monkeypatch.setattr(mod.requests, "post", fake_post)
    return calls


def _params(url):
    """Query string of a captured URL as {name: value}."""
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


@pytest.mark.parametrize("auth", [
    {},
    {"user": "admin"},
    {"pwd": "district"},
    {"token": ""},
])
def test_missing_auth_raises_before_request(captured, auth):
    with pytest.raises(ValueError, match="Authentication required"):
        post_dataElements(dhis_url="https://dhis.example.org", payload=example_payload, **auth)
    assert captured == []


def test_token_auth_sets_header(captured):
    post_dataElements(dhis_url="https://dhis.example.org", payload=example_payload, token="abc123")
    call = captured[0]
    assert call["headers"] == {"Authorization": "ApiToken abc123"}
    assert call["auth"] is None


def test_basic_auth(captured):
    post_dataElements(dhis_url="https://dhis.example.org", payload=example_payload,
                      user="admin", pwd="district")
    call = captured[0]
    assert call["headers"] == {}
    assert isinstance(call["auth"], HTTPBasicAuth)
    assert (call["auth"].username, call["auth"].password) == ("admin", "district")


def test_default_url_and_params(captured):
    post_dataElements(dhis_url="https://dhis.example.org/", payload=example_payload, token="t")
    url = captured[0]["url"]
    # trailing slash on dhis_url is not doubled
    assert url.startswith("https://dhis.example.org/api/dataValueSets?")
    assert _params(url) == {
        "dryRun": "true",
        "dataElementIdScheme": "code",
        "orgUnitIdScheme": "uid",
        "categoryOptionComboIdScheme": "code",
        "idScheme": "code",
        "importStrategy": "CREATE_AND_UPDATE",
    }


def test_dx_id_scheme_sets_dataElement_and_coc_schemes(captured):
    post_dataElements(dhis_url="https://dhis.example.org", payload=example_payload, token="t",
                      dx_id_scheme="uid")
    params = _params(captured[0]["url"])
    assert params["dataElementIdScheme"] == "uid"
    assert params["categoryOptionComboIdScheme"] == "uid"
    # orgUnits are always identified by uid
    assert params["orgUnitIdScheme"] == "uid"


def test_dryRun_false(captured):
    post_dataElements(dhis_url="https://dhis.example.org", payload=example_payload, token="t",
                      dryRun=False)
    assert _params(captured[0]["url"])["dryRun"] == "false"


def test_payload_sent_as_json_and_response_returned(captured):
    resp = post_dataElements(dhis_url="https://dhis.example.org", payload=example_payload, token="t")
    assert captured[0]["json"] == example_payload
    assert resp.status_code == 200
    assert resp.json() == {"status": "OK"}


def test_http_error_raises(monkeypatch):
    monkeypatch.setattr(mod.requests, "post", lambda *a, **k: _response(409, b'{"status": "ERROR"}'))
    with pytest.raises(requests.HTTPError):
        post_dataElements(dhis_url="https://dhis.example.org", payload=example_payload, token="t")


def test_http_error_logs_response_body(monkeypatch, caplog):
    body = b'{"status": "ERROR", "message": "conflict on dataElement X"}'
    monkeypatch.setattr(mod.requests, "post", lambda *a, **k: _response(409, body))
    with caplog.at_level("ERROR", logger=mod.__name__), pytest.raises(requests.HTTPError):
        post_dataElements(dhis_url="https://dhis.example.org", payload=example_payload, token="t")
    assert "HTTP 409" in caplog.text
    assert "conflict on dataElement X" in caplog.text


def test_http_error_empty_body_is_flagged(monkeypatch, caplog):
    monkeypatch.setattr(mod.requests, "post", lambda *a, **k: _response(401, b""))
    with caplog.at_level("ERROR", logger=mod.__name__), pytest.raises(requests.HTTPError):
        post_dataElements(dhis_url="https://dhis.example.org", payload=example_payload, token="t")
    assert "HTTP 401" in caplog.text
    assert "(empty body)" in caplog.text


@pytest.mark.live
@pytest.mark.skipif(not (os.getenv("TEST_URL") and os.getenv("TEST_TOKEN")),
                    reason="TEST_URL / TEST_TOKEN not set")
def test_live_dry_run():
    """POSTs the example payload to TEST_URL with dryRun=True (nothing is saved)."""
    resp = post_dataElements(dhis_url=os.getenv("TEST_URL"), payload=example_payload,
                             token=os.getenv("TEST_TOKEN"), dryRun=True)
    assert resp.status_code == 200
    assert resp.json().get("status") in {"OK", "SUCCESS", "WARNING"}
