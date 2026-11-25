import os

import pytest
import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

import pivot_dhis_tools.api_helpers as mod

# module level so the skipif on the live test sees the .env values
load_dotenv()


def _response(status=200, body=b'{"username": "tester"}', headers=None):
    resp = requests.Response()
    resp.status_code = status
    resp._content = body
    resp.headers.update(headers or {})
    resp.url = "https://dhis.example.org/api/me"
    return resp


# ---- _api_auth ----

def test_token_auth():
    headers, auth = mod._api_auth(token="abc")
    assert headers == {"Authorization": "ApiToken abc"}
    assert auth is None


def test_basic_auth():
    headers, auth = mod._api_auth(user="u", pwd="p")
    assert headers == {}
    assert isinstance(auth, HTTPBasicAuth)
    assert (auth.username, auth.password) == ("u", "p")


def test_token_takes_precedence():
    headers, auth = mod._api_auth(user="u", pwd="p", token="abc")
    assert headers == {"Authorization": "ApiToken abc"}
    assert auth is None


@pytest.mark.parametrize("kwargs", [
    {},
    {"user": "u"},
    {"pwd": "p"},
    {"token": ""},
    {"user": "", "pwd": ""},
])
def test_missing_credentials_raise(kwargs):
    with pytest.raises(ValueError, match="Authentication required"):
        mod._api_auth(**kwargs)


def test_positional_args_rejected():
    with pytest.raises(TypeError):
        mod._api_auth("u", "p")


# ---- check_dhis_connection ----

@pytest.fixture
def captured(monkeypatch):
    """Replace requests.get with a fake returning 200; return the list of captured calls."""
    calls = []

    def fake_get(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return _response()

    monkeypatch.setattr(mod.requests, "get", fake_get)
    return calls


def test_check_dhis_connection_success(captured):
    result = mod.check_dhis_connection("https://dhis.example.org", token="abc")
    assert result == {"username": "tester"}
    call = captured[0]
    assert call["url"] == "https://dhis.example.org/api/me"
    assert call["headers"] == {"Authorization": "ApiToken abc"}
    assert call["auth"] is None
    assert call["allow_redirects"] is False
    assert call["timeout"] == 10


def test_check_dhis_connection_strips_trailing_slash(captured):
    mod.check_dhis_connection("https://dhis.example.org/", user="u", pwd="p")
    assert captured[0]["url"] == "https://dhis.example.org/api/me"
    assert isinstance(captured[0]["auth"], HTTPBasicAuth)


def test_check_dhis_connection_missing_credentials_makes_no_request(captured):
    with pytest.raises(ValueError):
        mod.check_dhis_connection("https://dhis.example.org")
    assert captured == []


def test_check_dhis_connection_bad_credentials(monkeypatch):
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: _response(401, b""))
    with pytest.raises(requests.HTTPError):
        mod.check_dhis_connection("https://dhis.example.org", token="bad")


def test_check_dhis_connection_redirect_raises(monkeypatch):
    redirect = _response(302, b"", headers={"Location": "https://dhis.example.org/dhis-web-login/"})
    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: redirect)
    with pytest.raises(requests.HTTPError, match="redirect"):
        mod.check_dhis_connection("https://dhis.example.org", token="abc")


def test_check_dhis_connection_unreachable(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("no route")

    monkeypatch.setattr(mod.requests, "get", boom)
    with pytest.raises(requests.ConnectionError):
        mod.check_dhis_connection("https://dhis.example.org", token="abc")


@pytest.mark.live
@pytest.mark.skipif(not (os.getenv("TEST_URL") and os.getenv("TEST_TOKEN")),
                    reason="TEST_URL / TEST_TOKEN not set")
def test_live_check_dhis_connection():
    """Calls /api/me on TEST_URL with TEST_TOKEN (read-only)."""
    me = mod.check_dhis_connection(os.getenv("TEST_URL"), token=os.getenv("TEST_TOKEN"))
    assert "id" in me
