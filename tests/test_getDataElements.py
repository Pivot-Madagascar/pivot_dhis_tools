"""
Tests for get_dataElements.py::get_dataElements and json_to_dataframe.

HTTP calls are mocked. The live tests are read-only and run only when
TEST_URL / TEST_TOKEN are set.
"""
import importlib
import json
import os

import pandas as pd
import pytest
import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

from pivot_dhis_tools import get_dataElements

# the package __init__ re-exports the function under the module's name, so fetch the module itself
mod = importlib.import_module("pivot_dhis_tools.get_dataElements")

# module level so the skipif on the live test sees the .env values
load_dotenv()

URL = "https://dhis.example.org"
QUERY = dict(dx_query="dx:deUid00001", ou_query="ou:LEVEL-5;parentOU01", pe_query="pe:202601;202602")

ANALYTICS = {
    "headers": [{"name": "dx"}, {"name": "ou"}, {"name": "pe"}, {"name": "value"}],
    "rows": [
        ["deUid00001", "ouA", "202601", "3"],
        ["deUid00001", "ouB", "202602", "0"],
    ],
}


def _response(body, status=200):
    resp = requests.Response()
    resp.status_code = status
    resp._content = json.dumps(body).encode()
    resp.url = f"{URL}/api/analytics.json"
    return resp


@pytest.fixture
def captured(monkeypatch):
    """Replace requests.get with a fake returning ANALYTICS; return the list of captured calls."""
    calls = []

    def fake_get(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return _response(ANALYTICS)

    monkeypatch.setattr(mod.requests, "get", fake_get)
    return calls


# ---- output ----

def test_returns_dataframe_of_rows(captured):
    df = get_dataElements(URL, **QUERY, token="t")
    expected = pd.DataFrame(ANALYTICS["rows"], columns=["dx", "ou", "pe", "value"])
    pd.testing.assert_frame_equal(df, expected)


def test_no_rows_gives_empty_frame_with_columns(monkeypatch):
    monkeypatch.setattr(mod.requests, "get",
                        lambda *a, **k: _response({"headers": ANALYTICS["headers"], "rows": []}))
    df = get_dataElements(URL, **QUERY, token="t")
    assert df.empty
    assert list(df.columns) == ["dx", "ou", "pe", "value"]


# ---- request ----

def test_url_and_dimensions(captured):
    get_dataElements(URL + "/", **QUERY, token="t")
    call = captured[0]
    assert call["url"] == f"{URL}/api/analytics.json"
    assert call["params"] == {
        "dimension": [QUERY["dx_query"], QUERY["ou_query"], QUERY["pe_query"]],
        "includeNumDen": False,
    }
    assert call["timeout"] == 600


def test_co_query_and_includeNumDen(captured):
    get_dataElements(URL, **QUERY, token="t", co_query="co:coc1;coc2", includeNumDen=True)
    params = captured[0]["params"]
    assert params["dimension"][-1] == "co:coc1;coc2"
    assert params["includeNumDen"] is True


# ---- CODE id scheme ----

@pytest.fixture
def code_lookup(monkeypatch):
    """Replace dx_code_to_uid with a fake; return the list of captured calls."""
    calls = []

    def fake_lookup(dhis_url, codes, user=None, pwd=None, token=None):
        calls.append({"dhis_url": dhis_url, "codes": codes, "user": user, "pwd": pwd, "token": token})
        return {"code_a": "deUid00001", "code_b": "deUid00002"}

    monkeypatch.setattr(mod, "dx_code_to_uid", fake_lookup)
    return calls


def test_code_scheme_resolves_codes_and_maps_dx_back(captured, code_lookup):
    df = get_dataElements(URL, **{**QUERY, "dx_query": "dx:code_a;code_b"}, token="t",
                          dx_id_scheme="CODE")
    assert code_lookup[0]["codes"] == ["code_a", "code_b"]
    assert captured[0]["params"]["dimension"][0] == "dx:deUid00001;deUid00002"
    assert set(df["dx"]) == {"code_a"}


def test_code_scheme_keeps_unmatched_code(captured, code_lookup):
    get_dataElements(URL, **{**QUERY, "dx_query": "dx:code_b;unknown"}, token="t",
                     dx_id_scheme="CODE")
    assert captured[0]["params"]["dimension"][0] == "dx:deUid00002;unknown"


def test_code_scheme_forwards_credentials(captured, code_lookup):
    get_dataElements(URL, **{**QUERY, "dx_query": "dx:code_a"}, user="u", pwd="p",
                     dx_id_scheme="CODE")
    assert code_lookup[0] == {"dhis_url": URL, "codes": ["code_a"], "user": "u", "pwd": "p", "token": None}


def test_default_scheme_skips_code_lookup(captured, monkeypatch):
    monkeypatch.setattr(mod, "dx_code_to_uid", lambda *a, **k: pytest.fail("lookup should not run"))
    get_dataElements(URL, **QUERY, token="t")


# ---- authentication ----

def test_token_auth(captured):
    get_dataElements(URL, **QUERY, token="abc")
    assert captured[0]["headers"] == {"Authorization": "ApiToken abc"}
    assert captured[0]["auth"] is None


def test_basic_auth(captured):
    get_dataElements(URL, **QUERY, user="u", pwd="p")
    assert isinstance(captured[0]["auth"], HTTPBasicAuth)


@pytest.mark.parametrize("kwargs", [{}, {"user": "u"}, {"pwd": "p"}])
def test_missing_credentials_raises_before_request(captured, kwargs):
    with pytest.raises(ValueError, match="Authentication required"):
        get_dataElements(URL, **QUERY, **kwargs)
    assert captured == []


# ---- errors ----

def test_http_error_logs_and_raises(monkeypatch, caplog):
    monkeypatch.setattr(mod.requests, "get",
                        lambda *a, **k: _response({"message": "Dimension dx is present in query without any valid dimension options"}, 409))
    with caplog.at_level("ERROR"), pytest.raises(requests.HTTPError):
        get_dataElements(URL, **QUERY, token="t")
    assert "Failed to fetch analytics data: HTTP 409" in caplog.text
    assert "without any valid dimension options" in caplog.text


# ---- json_to_dataframe ----

def test_json_to_dataframe_uses_header_order():
    data = {"headers": [{"name": "pe"}, {"name": "value"}], "rows": [["202601", "1"]]}
    df = mod.json_to_dataframe(data)
    assert list(df.columns) == ["pe", "value"]
    assert df.iloc[0].tolist() == ["202601", "1"]


def test_json_to_dataframe_missing_rows_raises():
    with pytest.raises(KeyError):
        mod.json_to_dataframe({"headers": []})


# ---- live ----

LIVE = pytest.mark.skipif(not (os.getenv("TEST_URL") and os.getenv("TEST_TOKEN")),
                          reason="TEST_URL / TEST_TOKEN not set")


@pytest.mark.live
@LIVE
def test_live_uid_query():
    """Read-only: fetches one dataElement by UID from TEST_URL."""
    df = get_dataElements(os.getenv("TEST_URL"), dx_query="dx:dA9FwHe5k4U", ou_query="ou:VtP4BdCeXIo",
                          pe_query="pe:202201", token=os.getenv("TEST_TOKEN"))
    assert {"dx", "ou", "pe", "value"} <= set(df.columns)
    assert set(df["dx"]) <= {"dA9FwHe5k4U"}


@pytest.mark.live
@LIVE
def test_live_code_query():
    """Read-only: fetches one dataElement by code from TEST_URL; dx comes back as the code."""
    code = "pridec_historic_COMMalaria"
    df = get_dataElements(os.getenv("TEST_URL"), dx_query=f"dx:{code}", ou_query="ou:VtP4BdCeXIo",
                          pe_query="pe:202201", token=os.getenv("TEST_TOKEN"), dx_id_scheme="CODE")
    assert {"dx", "ou", "pe", "value"} <= set(df.columns)
    assert set(df["dx"]) <= {code}
