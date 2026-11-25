"""
Tests for clear_analytics.py::clear_analytics.

HTTP calls are mocked. There is no live test: clearing analytics tables is
not a dry-run operation, so it is not run against TEST_URL.
"""
import importlib

import pytest
import requests
from requests.auth import HTTPBasicAuth

from pivot_dhis_tools import clear_analytics

# the package __init__ re-exports the function under the module's name, so fetch the module itself
mod = importlib.import_module("pivot_dhis_tools.clear_analytics")

URL = "https://dhis.example.org"


def _response(status_code=200, body=b'{"httpStatus": "OK"}'):
    resp = requests.Response()
    resp.status_code = status_code
    resp._content = body
    resp.url = f"{URL}/api/maintenance/analyticsTablesClear"
    return resp


@pytest.fixture
def captured(monkeypatch):
    """Replace requests.post with a fake returning 200; return the list of captured calls."""
    calls = []

    def fake_post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return _response()

    monkeypatch.setattr(mod.requests, "post", fake_post)
    return calls


def test_posts_to_clear_endpoint_and_returns_response(captured):
    resp = clear_analytics(URL + "/", token="abc")
    assert captured[0]["url"] == f"{URL}/api/maintenance/analyticsTablesClear"
    assert resp.status_code == 200


def test_token_auth(captured):
    clear_analytics(URL, token="abc")
    assert captured[0]["headers"] == {"Authorization": "ApiToken abc"}
    assert captured[0]["auth"] is None


def test_basic_auth(captured):
    clear_analytics(URL, user="u", pwd="p")
    assert captured[0]["headers"] == {}
    assert isinstance(captured[0]["auth"], HTTPBasicAuth)


@pytest.mark.parametrize("kwargs", [{}, {"user": "u"}, {"pwd": "p"}, {"token": ""}])
def test_missing_credentials_raises_before_request(captured, kwargs):
    with pytest.raises(ValueError, match="Authentication required"):
        clear_analytics(URL, **kwargs)
    assert captured == []


def test_empty_success_body_does_not_raise(monkeypatch):
    monkeypatch.setattr(mod.requests, "post", lambda *a, **k: _response(204, b""))
    assert clear_analytics(URL, token="abc").status_code == 204


def test_http_error_logs_and_raises(monkeypatch, caplog):
    monkeypatch.setattr(mod.requests, "post",
                        lambda *a, **k: _response(403, b'{"message": "no maintenance authority"}'))
    with caplog.at_level("ERROR"), pytest.raises(requests.HTTPError):
        clear_analytics(URL, token="abc")
    assert "Failed to clear analytics tables: HTTP 403" in caplog.text
    assert "no maintenance authority" in caplog.text
