import logging
import os
from types import SimpleNamespace
from dotenv import load_dotenv

import pandas as pd
import pytest

from pivot_dhis_tools.pridec import import_pivot as mod
from pivot_dhis_tools.pridec.import_pivot import import_pivot_com

# module level so the skipif on the live test sees the .env values
load_dotenv()

logger = logging.getLogger(__name__)

TOTAL_DX = "dx:lq38tLcfEi7"
TARGETS = {"pridec_historic_COMMalaria", "pridec_historic_COMRespinf", "pridec_historic_COMDiarrhea"}


def _rows(dx, ou, value, pe="202601"):
    return {"dx": dx, "ou": ou, "pe": pe, "value": value}


@pytest.fixture
def pivot_data():
    """Fake Pivot responses keyed by dx_query, for two orgUnits (A, B) in one period."""
    return {
        # both orgUnits reported consultations
        TOTAL_DX: [_rows("lq38tLcfEi7", "A", "10"), _rows("lq38tLcfEi7", "B", "12")],
        # malaria: only A has a value, so B should be filled with 0
        "dx:vduU8d1GZbW": [_rows("vduU8d1GZbW", "A", "5")],
        # respinf: two source dx that must be summed
        "dx:hJ5pa6wO4nJ;CmDXCmmywrj": [
            _rows("hJ5pa6wO4nJ", "A", "2"), _rows("CmDXCmmywrj", "A", "3"),
            _rows("hJ5pa6wO4nJ", "B", "1"),
        ],
        "dx:DjsQEzPDAoN;f4hrhsiz49l": [_rows("DjsQEzPDAoN", "A", "4")],
    }


@pytest.fixture
def mocked(monkeypatch, pivot_data):
    """Patch the network calls in import_pivot_com; return the list of captured posts."""
    posts = []

    def fake_get(dhis_url, token, dx_query, pe_query, ou_query, includeNumDen):
        return pd.DataFrame(pivot_data[dx_query])

    def fake_post(dhis_url, payload, token, dryRun):
        posts.append({"dhis_url": dhis_url, "token": token, "dryRun": dryRun,
                      "values": payload["dataValues"]})
        return SimpleNamespace(ok=True, status_code=200, text="ok")

    monkeypatch.setattr(mod, "get_dataElements", fake_get)
    monkeypatch.setattr(mod, "post_dataElements", fake_post)
    return posts


def _run():
    import_pivot_com(dhis_url="https://dhis.test", dhis_token="dhis-tok",
                     pivot_token="pivot-tok", pivot_url="https://pivot.test")


def _values_by_target(posts):
    return {p["values"][0]["dataElement"]: {v["orgUnit"]: v["value"] for v in p["values"]}
            for p in posts}


def test_posts_each_element_with_summed_and_zero_filled_values(mocked):
    _run()

    assert len(mocked) == 3
    vals = _values_by_target(mocked)
    assert set(vals) == TARGETS
    assert vals["pridec_historic_COMMalaria"] == {"A": 5, "B": 0}  # B missing -> 0
    assert vals["pridec_historic_COMRespinf"] == {"A": 5, "B": 1}  # 2 + 3 summed
    assert vals["pridec_historic_COMDiarrhea"] == {"A": 4, "B": 0}


def test_post_uses_dhis_credentials_and_defaults_to_dry_run(mocked):
    _run()

    assert all(p["dhis_url"] == "https://dhis.test" for p in mocked)
    assert all(p["token"] == "dhis-tok" for p in mocked)
    assert all(p["dryRun"] is True for p in mocked)


def test_failed_check_declined_skips_post(mocked, monkeypatch, pivot_data):
    pivot_data["dx:vduU8d1GZbW"] = [_rows("vduU8d1GZbW", "A", "500")]  # over threshold of 200
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")

    _run()

    assert set(_values_by_target(mocked)) == TARGETS - {"pridec_historic_COMMalaria"}


def test_failed_check_approved_still_posts(mocked, monkeypatch, pivot_data):
    pivot_data["dx:vduU8d1GZbW"] = [_rows("vduU8d1GZbW", "A", "500")]
    monkeypatch.setattr("builtins.input", lambda _prompt: "y")

    _run()

    assert _values_by_target(mocked)["pridec_historic_COMMalaria"]["A"] == 500
    assert len(mocked) == 3


def test_failed_check_without_terminal_skips_post(mocked, monkeypatch, pivot_data):
    pivot_data["dx:vduU8d1GZbW"] = [_rows("vduU8d1GZbW", "A", "500")]

    def no_tty(_prompt):
        raise EOFError

    monkeypatch.setattr("builtins.input", no_tty)

    _run()

    assert "pridec_historic_COMMalaria" not in _values_by_target(mocked)


def test_passing_check_never_prompts(mocked, monkeypatch):
    def fail(_prompt):
        raise AssertionError("input() should not be called when the check passes")

    monkeypatch.setattr("builtins.input", fail)

    _run()

    assert len(mocked) == 3


LIVE_ENV = ["TEST_URL", "TEST_TOKEN", "PIVOT_URL", "PIVOT_TOKEN"]


@pytest.mark.live
@pytest.mark.skipif(any(not os.getenv(v) for v in LIVE_ENV), reason="live env vars not set")
def test_live_dry_run(monkeypatch):
    """Reads real Pivot data and POSTs it to TEST_URL with dryRun=True (nothing is saved)."""
    real_post = mod.post_dataElements
    responses = []
    prompts = []

    def spy(**kwargs):
        assert kwargs["dryRun"] is True  # never allow a real write from this test
        resp = real_post(**kwargs)
        responses.append((kwargs["payload"], resp))
        return resp

    def decline(prompt):
        # pytest captures stdin, so input() would raise OSError; decline instead
        prompts.append(prompt)
        return "n"

    monkeypatch.setattr(mod, "post_dataElements", spy)
    monkeypatch.setattr("builtins.input", decline)

    import_pivot_com(dhis_url=os.getenv("TEST_URL"),
                     dhis_token=os.getenv("TEST_TOKEN"),
                     pivot_url=os.getenv("PIVOT_URL"),
                     pivot_token=os.getenv("PIVOT_TOKEN"),
                     dryRun=True,
                     prior_months=2)

    # elements skipped by a failed value check are data-dependent, so log rather than fail
    for p in prompts:
        logger.warning("live data failed the value check: %s", p)

    assert responses, "no dataElement was posted (all skipped or none fetched)"

    for payload, resp in responses:
        values = payload["dataValues"]
        assert {v["dataElement"] for v in values} <= TARGETS
        assert resp.status_code == 200

        body = resp.json()
        logger.info("dryRun response: %s", body)
        # newer DHIS2 versions nest the summary under "response"
        summary = body.get("response", body)
        counts = summary["importCount"]

        # conflicts / rejected indexes are how DHIS2 reports unknown orgUnits, elements or combos
        assert not summary.get("conflicts"), summary.get("conflicts")
        assert not summary.get("rejectedIndexes"), summary.get("rejectedIndexes")

        # every value is accounted for. "ignored" is not an error by itself (the live
        # data returned ignored values with no conflicts), so log it instead of failing
        assert sum(counts[k] for k in ("imported", "updated", "ignored")) == len(values)
        logger.info("%s: %s", values[0]["dataElement"], counts)
