"""
Tests for get_dataElement_names.py::get_dataElement_names.

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

from pivot_dhis_tools import get_dataElement_names

# the package __init__ re-exports the function under the module's name, so fetch the module itself
mod = importlib.import_module("pivot_dhis_tools.get_dataElement_names")

# module level so the skipif on the live test sees the .env values
load_dotenv()

URL = "https://dhis.example.org"
ELEMENTS = [
    {"id": "deUid00001", "name": "Malaria cases", "code": "MAL"},
    {"id": "deUid00002", "name": "Malaria deaths"},
]


def _response(body, status=200):
    resp = requests.Response()
    resp.status_code = status
    resp._content = json.dumps(body).encode()
    resp.url = f"{URL}/api/dataElements.json"
    return resp


@pytest.fixture
def captured(monkeypatch):
    """Replace requests.get with a fake returning ELEMENTS; return the list of captured calls."""
    calls = []

    def fake_get(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return _response({"dataElements": ELEMENTS})

    monkeypatch.setattr(mod.requests, "get", fake_get)
    return calls


def test_returns_dataElements(captured):
    assert get_dataElement_names(URL, "malaria", token="t") == ELEMENTS


def test_pattern_sets_ilike_filter(captured):
    get_dataElement_names(URL + "/", "malaria", token="t")
    call = captured[0]
    assert call["url"] == f"{URL}/api/dataElements.json"
    assert call["params"] == {"fields": "id,name,code", "filter": "name:ilike:malaria", "paging": "false"}
    assert call["timeout"] == 180


def test_no_pattern_fetches_everything(captured):
    get_dataElement_names(URL, token="t")
    assert "filter" not in captured[0]["params"]


def test_missing_key_returns_empty_list(monkeypatch):
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _response({}))
    assert get_dataElement_names(URL, token="t") == []


def test_token_auth(captured):
    get_dataElement_names(URL, token="abc")
    assert captured[0]["headers"] == {"Authorization": "ApiToken abc"}
    assert captured[0]["auth"] is None


def test_basic_auth(captured):
    get_dataElement_names(URL, user="u", pwd="p")
    assert isinstance(captured[0]["auth"], HTTPBasicAuth)


@pytest.mark.parametrize("kwargs", [{}, {"user": "u"}, {"pwd": "p"}])
def test_missing_credentials_raises_before_request(captured, kwargs):
    with pytest.raises(ValueError, match="Authentication required"):
        get_dataElement_names(URL, **kwargs)
    assert captured == []


def test_http_error_logs_and_raises(monkeypatch, caplog):
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _response({"message": "denied"}, 401))
    with caplog.at_level("ERROR"), pytest.raises(requests.HTTPError):
        get_dataElement_names(URL, token="t")
    assert "Failed to fetch dataElement names: HTTP 401" in caplog.text


# ---- live ----

@pytest.mark.live
@pytest.mark.skipif(not (os.getenv("TEST_URL") and os.getenv("TEST_TOKEN")),
                    reason="TEST_URL / TEST_TOKEN not set")
def test_live_get_names():
    """Read-only: lists dataElement names on TEST_URL, then searches for one of them."""
    url, token = os.getenv("TEST_URL"), os.getenv("TEST_TOKEN")
    everything = get_dataElement_names(url, token=token)
    assert everything, "no dataElements found"
    assert all({"id", "name"} <= set(el) for el in everything)

    # search case-insensitively for a word from a real name. Plain letters only:
    # DHIS2 treats "_" and "%" in the pattern as LIKE wildcards
    target, word = next((el, w) for el in everything for w in el["name"].split()
                        if w.isalpha() and len(w) >= 5)
    pattern = word.upper()
    matches = get_dataElement_names(url, pattern=pattern, token=token)
    assert target["id"] in {el["id"] for el in matches}
    assert all(pattern.lower() in el["name"].lower() for el in matches)
