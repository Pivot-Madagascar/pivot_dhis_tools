"""
Tests for pridec/send_email_pridec.py::send_email_pridec.

HTTP calls are mocked. There is no live test: it would send real email to
every member of the PRIDE-C user group.
"""
import json

import pytest
import requests
from requests.auth import HTTPBasicAuth

import pivot_dhis_tools.pridec.send_email_pridec as mod
from pivot_dhis_tools.pridec.send_email_pridec import send_email_pridec

URL = "https://dhis.example.org"
GROUPS = {"userGroups": [{"users": [{"email": "a@example.org"}, {}, {"email": ""},
                                    {"email": "b@example.org"}]}]}


def _response(body, status=200, url=URL):
    resp = requests.Response()
    resp.status_code = status
    resp._content = json.dumps(body).encode()
    resp.url = url
    return resp


@pytest.fixture
def fake_api(monkeypatch):
    """Patch requests.get/post. Set `.groups`, `.get_status`, `.post_status` to control
    responses; calls are recorded in `.gets` / `.posts`."""

    class Api:
        groups = GROUPS
        get_status = 200
        post_status = 200
        gets = []
        posts = []

    api = Api()

    def fake_get(url, **kwargs):
        api.gets.append({"url": url, **kwargs})
        return _response(api.groups, api.get_status, url)

    def fake_post(url, **kwargs):
        api.posts.append({"url": url, **kwargs})
        return _response({"httpStatus": "OK"}, api.post_status, url)

    monkeypatch.setattr(mod.requests, "get", fake_get)
    monkeypatch.setattr(mod.requests, "post", fake_post)
    return api


def test_sends_to_group_members_with_email(fake_api):
    out = send_email_pridec("Subj", "<p>Hi</p>", URL + "/", token="t")
    assert out == {"status": "sent", "recipients": ["a@example.org", "b@example.org"]}

    get = fake_api.gets[0]
    assert get["url"] == f"{URL}/api/33/userGroups"
    assert get["params"] == {"filter": "name:eq:PRIDE-C", "fields": "users[email]"}

    post = fake_api.posts[0]
    assert post["url"] == f"{URL}/api/33/email/notification"
    assert post["data"] == {"recipients": "a@example.org,b@example.org",
                            "subject": "Subj", "message": "<p>Hi</p>"}


def test_token_sent_on_every_request(fake_api):
    send_email_pridec("s", "m", URL, token="abc")
    for call in fake_api.gets + fake_api.posts:
        assert call["headers"] == {"Authorization": "ApiToken abc"}
        assert call["auth"] is None


def test_basic_auth_sent_on_every_request(fake_api):
    send_email_pridec("s", "m", URL, user="u", pwd="p")
    for call in fake_api.gets + fake_api.posts:
        assert isinstance(call["auth"], HTTPBasicAuth)


@pytest.mark.parametrize("kwargs", [{}, {"user": "u"}, {"pwd": "p"}])
def test_missing_credentials_raises_before_request(fake_api, kwargs):
    with pytest.raises(ValueError, match="Authentication required"):
        send_email_pridec("s", "m", URL, **kwargs)
    assert fake_api.gets == [] and fake_api.posts == []


def test_no_group_raises(fake_api):
    fake_api.groups = {"userGroups": []}
    with pytest.raises(ValueError, match="No user group named PRIDE-C"):
        send_email_pridec("s", "m", URL, token="t")
    assert fake_api.posts == []


@pytest.mark.parametrize("users", [[], [{}, {"email": ""}]])
def test_no_emails_raises(fake_api, users):
    fake_api.groups = {"userGroups": [{"users": users}]}
    with pytest.raises(ValueError, match="No email addresses found"):
        send_email_pridec("s", "m", URL, token="t")
    assert fake_api.posts == []


def test_lookup_http_error_logs_and_raises(fake_api, caplog):
    fake_api.get_status = 401
    with caplog.at_level("ERROR"), pytest.raises(requests.HTTPError):
        send_email_pridec("s", "m", URL, token="t")
    assert "Failed to look up PRIDE-C user group emails: HTTP 401" in caplog.text
    assert fake_api.posts == []


def test_send_http_error_logs_and_raises(fake_api, caplog):
    fake_api.post_status = 409
    with caplog.at_level("ERROR"), pytest.raises(requests.HTTPError):
        send_email_pridec("s", "m", URL, token="t")
    assert "Failed to send email: HTTP 409" in caplog.text
