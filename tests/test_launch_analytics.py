"""
Tests for launch_analytics.py::launch_analytics.

HTTP calls and the clock are mocked, so polling runs instantly. There is no
live test: rebuilding analytics tables is not a dry-run operation and can
take many minutes, so it is not run against TEST_URL.
"""
import importlib
import json
from types import SimpleNamespace

import pytest
import requests
from requests.auth import HTTPBasicAuth

from pivot_dhis_tools import launch_analytics

# the package __init__ re-exports the function under the module's name, so fetch the module itself
mod = importlib.import_module("pivot_dhis_tools.launch_analytics")

URL = "https://dhis.example.org"
NOTIFIER = "/api/system/tasks/ANALYTICS_TABLE/job123"
START_BODY = {"response": {"relativeNotifierEndpoint": NOTIFIER}}


def _response(body, status=200, url=URL):
    resp = requests.Response()
    resp.status_code = status
    resp._content = json.dumps(body).encode()
    resp.url = url
    return resp


@pytest.fixture
def fake_clock(monkeypatch):
    """Replace the time module: sleep() advances monotonic() instead of waiting."""
    clock = SimpleNamespace(now=0.0, sleeps=[])

    def sleep(seconds):
        clock.sleeps.append(seconds)
        clock.now += seconds

    monkeypatch.setattr(mod, "time", SimpleNamespace(sleep=sleep, monotonic=lambda: clock.now))
    return clock


@pytest.fixture
def fake_api(monkeypatch, fake_clock):
    """Patch requests.post/get. `.polls` is the list of notifier bodies returned in turn
    (the last one repeats); `.post_status` / `.get_status` set error codes."""

    class Api:
        polls = [[{"message": "Started", "completed": False}],
                 [{"message": "Analytics tables updated", "completed": True}]]
        post_status = 200
        get_status = 200
        posts = []
        gets = []

    api = Api()

    def fake_post(url, **kwargs):
        api.posts.append({"url": url, **kwargs})
        return _response(START_BODY, api.post_status, url)

    def fake_get(url, **kwargs):
        api.gets.append({"url": url, **kwargs})
        body = api.polls[min(len(api.gets), len(api.polls)) - 1]
        return _response(body, api.get_status, url)

    monkeypatch.setattr(mod.requests, "post", fake_post)
    monkeypatch.setattr(mod.requests, "get", fake_get)
    return api


# ---- success ----

def test_returns_start_response_once_completed(fake_api, fake_clock):
    resp = launch_analytics(URL + "/", token="t")
    assert resp.json() == START_BODY
    assert fake_api.posts[0]["url"] == f"{URL}/api/33/resourceTables/analytics"
    assert [g["url"] for g in fake_api.gets] == [f"{URL}{NOTIFIER}"] * 2
    assert fake_clock.sleeps == [30, 30]


def test_empty_notifications_keep_polling(fake_api):
    fake_api.polls = [[], [], [{"message": "done", "completed": True}]]
    launch_analytics(URL, token="t")
    assert len(fake_api.gets) == 3


def test_every_request_has_timeout(fake_api):
    launch_analytics(URL, token="t")
    assert all(c["timeout"] == 30 for c in fake_api.posts + fake_api.gets)


# ---- authentication ----

def test_token_sent_on_every_request(fake_api):
    launch_analytics(URL, token="abc")
    for call in fake_api.posts + fake_api.gets:
        assert call["headers"] == {"Authorization": "ApiToken abc"}
        assert call["auth"] is None


def test_basic_auth_sent_on_every_request(fake_api):
    launch_analytics(URL, user="u", pwd="p")
    for call in fake_api.posts + fake_api.gets:
        assert isinstance(call["auth"], HTTPBasicAuth)


@pytest.mark.parametrize("kwargs", [{}, {"user": "u"}, {"pwd": "p"}])
def test_missing_credentials_raises_before_request(fake_api, kwargs):
    with pytest.raises(ValueError, match="Authentication required"):
        launch_analytics(URL, **kwargs)
    assert fake_api.posts == []


# ---- errors ----

def test_error_notification_raises(fake_api):
    fake_api.polls = [[{"message": "Table exceeds disk", "level": "ERROR", "completed": True}]]
    with pytest.raises(RuntimeError, match="Table exceeds disk"):
        launch_analytics(URL, token="t")


def test_not_completed_after_15_minutes_raises(fake_api, fake_clock):
    fake_api.polls = [[{"message": "still running", "completed": False}]]
    with pytest.raises(TimeoutError, match=NOTIFIER):
        launch_analytics(URL, token="t")
    assert fake_clock.now >= 15 * 60
    assert len(fake_api.gets) == 30  # one poll every 30 s


def test_start_http_error_logs_and_raises(fake_api, caplog):
    fake_api.post_status = 403
    with caplog.at_level("ERROR"), pytest.raises(requests.HTTPError):
        launch_analytics(URL, token="t")
    assert "Failed to start analytics table build: HTTP 403" in caplog.text
    assert fake_api.gets == []


def test_status_http_error_logs_and_raises(fake_api, caplog):
    fake_api.get_status = 500
    with caplog.at_level("ERROR"), pytest.raises(requests.HTTPError):
        launch_analytics(URL, token="t")
    assert "Failed to check analytics table build status: HTTP 500" in caplog.text
