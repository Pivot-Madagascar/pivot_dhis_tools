"""
Tests for delete_dataElements.py::delete_dataElements.

HTTP calls are mocked. The live test only sends a dryRun deletion to TEST_URL
(DHIS2 validates it but deletes nothing) and runs only when TEST_URL /
TEST_TOKEN are set.
"""
import importlib
import os
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

from pivot_dhis_tools import delete_dataElements

# the package __init__ re-exports the function under the module's name, so fetch the module itself
mod = importlib.import_module("pivot_dhis_tools.delete_dataElements")

# module level so the skipif on the live test sees the .env values
load_dotenv()

URL = "https://dhis.example.org"
ARGS = dict(dataElement="pridec_climate_AOD", delete_month_range=["202511", "202601"],
            orgUnit_ids=["ouA", "ouB"])


def _response(status_code=200, body=b'{"status": "OK", "response": {"importCount": {}}}'):
    resp = requests.Response()
    resp.status_code = status_code
    resp._content = body
    resp.url = f"{URL}/api/dataValueSets"
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


@pytest.fixture
def no_prompt(monkeypatch):
    """Fail the test if the confirmation prompt is shown."""
    monkeypatch.setattr("builtins.input", lambda _p: pytest.fail("input() should not be called"))


def _params(url):
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


# ---- payload and request ----

def test_payload_covers_every_month_and_orgUnit(captured, no_prompt):
    delete_dataElements(URL, **ARGS, token="t", dryRun=True)
    values = captured[0]["json"]["dataValues"]
    assert {(v["period"], v["orgUnit"]) for v in values} == {
        (pe, ou) for pe in ("202511", "202512", "202601") for ou in ("ouA", "ouB")
    }
    assert {v["dataElement"] for v in values} == {"pridec_climate_AOD"}


def test_url_and_params(captured, no_prompt):
    delete_dataElements(URL + "/", **ARGS, token="t", dryRun=True)
    url = captured[0]["url"]
    assert url.startswith(f"{URL}/api/dataValueSets?")
    assert _params(url) == {
        "dryRun": "true",
        "dataElementIdScheme": "code",
        "orgUnitIdScheme": "uid",
        "categoryOptionComboIdScheme": "code",
        "idScheme": "code",
        "importStrategy": "DELETE",
        "force": "true",
    }


def test_single_month_range(captured, no_prompt):
    delete_dataElements(URL, **{**ARGS, "delete_month_range": ["202601", "202601"]},
                        token="t", dryRun=True)
    assert {v["period"] for v in captured[0]["json"]["dataValues"]} == {"202601"}


def test_returns_response_and_prints_summary_when_verbose(captured, no_prompt, capsys):
    resp = delete_dataElements(URL, **ARGS, token="t", dryRun=True)
    assert resp.status_code == 200
    assert "importCount" in capsys.readouterr().out


def test_not_verbose_prints_nothing(captured, no_prompt, capsys):
    delete_dataElements(URL, **ARGS, token="t", dryRun=True, verbose=False)
    assert capsys.readouterr().out == ""


# ---- confirmation prompt ----

def test_real_delete_requires_yes(captured, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _p: "yes")
    delete_dataElements(URL, **ARGS, token="t")
    assert _params(captured[0]["url"])["dryRun"] == "false"


@pytest.mark.parametrize("answer", ["no", "y", "YES", ""])
def test_real_delete_without_yes_sends_nothing(captured, monkeypatch, answer):
    monkeypatch.setattr("builtins.input", lambda _p: answer)
    assert delete_dataElements(URL, **ARGS, token="t") is None
    assert captured == []


# ---- authentication ----

def test_token_auth(captured, no_prompt):
    delete_dataElements(URL, **ARGS, token="abc", dryRun=True)
    assert captured[0]["headers"] == {"Authorization": "ApiToken abc"}
    assert captured[0]["auth"] is None


def test_basic_auth(captured, no_prompt):
    delete_dataElements(URL, **ARGS, user="u", pwd="p", dryRun=True)
    assert isinstance(captured[0]["auth"], HTTPBasicAuth)


@pytest.mark.parametrize("kwargs", [{}, {"user": "u"}, {"pwd": "p"}])
def test_missing_credentials_raises_before_prompt_or_request(captured, no_prompt, kwargs):
    with pytest.raises(ValueError, match="Authentication required"):
        delete_dataElements(URL, **ARGS, **kwargs)
    assert captured == []


# ---- errors ----

def test_bad_month_format_raises(captured, no_prompt):
    with pytest.raises(ValueError):
        delete_dataElements(URL, **{**ARGS, "delete_month_range": ["2025-11", "202601"]},
                            token="t", dryRun=True)
    assert captured == []


def test_http_error_logs_and_raises(monkeypatch, no_prompt, caplog):
    monkeypatch.setattr(mod.requests, "post",
                        lambda *a, **k: _response(409, b'{"message": "unknown dataElement"}'))
    with caplog.at_level("ERROR"), pytest.raises(requests.HTTPError):
        delete_dataElements(URL, **ARGS, token="t", dryRun=True)
    assert "Failed to delete dataValues: HTTP 409" in caplog.text
    assert "unknown dataElement" in caplog.text


# ---- live ----

@pytest.mark.live
@pytest.mark.skipif(not (os.getenv("TEST_URL") and os.getenv("TEST_TOKEN")),
                    reason="TEST_URL / TEST_TOKEN not set")
def test_live_dry_run(no_prompt):
    """Sends a dryRun deletion to TEST_URL (DHIS2 validates it; nothing is deleted)."""
    resp = delete_dataElements(os.getenv("TEST_URL"), dataElement="pridec_climate_temperatureMean",
                               delete_month_range=["202201", "202201"], orgUnit_ids=["VtP4BdCeXIo"],
                               token=os.getenv("TEST_TOKEN"), dryRun=True, verbose=False)
    assert resp.status_code == 200
