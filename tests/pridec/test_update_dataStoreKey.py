import importlib
import os
import re

import pytest
import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

from pivot_dhis_tools import pridec_update_key

mod = importlib.import_module("pivot_dhis_tools.pridec.update_dataStoreKey")

# module level so the skipif on the live test sees the .env values
load_dotenv()


def _response(status_code=200, body=b'{"httpStatus": "OK"}'):
    resp = requests.Response()
    resp.status_code = status_code
    resp._content = body
    resp.url = "https://dhis.example.org/api/33/dataStore/pridec/pridec_update"
    return resp


@pytest.fixture
def captured(monkeypatch):
    """Replace requests.put with a fake; return the list of captured calls."""
    calls = []

    def fake_put(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return _response()

    monkeypatch.setattr(mod.requests, "put", fake_put)
    return calls


@pytest.mark.parametrize("kwargs", [{}, {"user": "u"}, {"pwd": "p"}, {"token": ""}])
def test_missing_auth_raises_before_request(captured, kwargs):
    with pytest.raises(ValueError, match="Authentication required"):
        pridec_update_key(dhis_url="https://dhis.example.org", **kwargs)
    assert captured == []


def test_missing_auth_raises_even_in_dryRun(captured):
    with pytest.raises(ValueError, match="Authentication required"):
        pridec_update_key(dhis_url="https://dhis.example.org", dryRun=True)


def test_basic_auth(captured):
    pridec_update_key(dhis_url="https://dhis.example.org", user="u", pwd="p")
    assert captured[0]["headers"] == {}
    assert isinstance(captured[0]["auth"], HTTPBasicAuth)


def test_custom_timeout(captured):
    pridec_update_key(dhis_url="https://dhis.example.org", token="t", timeout=5)
    assert captured[0]["timeout"] == 5


def test_dryRun_sends_nothing(captured):
    assert pridec_update_key(dhis_url="https://dhis.example.org", token="t", dryRun=True) is None
    assert captured == []


def test_put_sends_key_as_json_object(captured):
    resp = pridec_update_key(dhis_url="https://dhis.example.org/", token="t")
    call = captured[0]
    assert call["url"] == "https://dhis.example.org/api/33/dataStore/pridec/pridec_update"
    assert call["headers"] == {"Authorization": "ApiToken t"}
    # a dict, not a pre-encoded JSON string, so DHIS2 stores an object
    assert isinstance(call["json"], dict)
    assert re.fullmatch(r"[A-Za-z0-9]{6}_updated_\d{4}-\d{2}-\d{2}", call["json"]["pridec_update"])
    assert call["timeout"] == 30
    assert resp.status_code == 200


def test_http_error_logs_and_raises(monkeypatch, caplog):
    monkeypatch.setattr(mod.requests, "put",
                        lambda *a, **k: _response(403, b'{"message": "no write access"}'))
    with caplog.at_level("ERROR"), pytest.raises(requests.HTTPError):
        pridec_update_key(dhis_url="https://dhis.example.org", token="t")
    assert "Failed to update dataStore key: HTTP 403" in caplog.text
    assert "no write access" in caplog.text