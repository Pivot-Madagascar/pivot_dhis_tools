import logging
import os
from types import SimpleNamespace
from dotenv import load_dotenv

import pandas as pd
import pytest
import requests

from pivot_dhis_tools.pridec import import_pivot as mod
from pivot_dhis_tools.pridec.import_pivot import import_pivot_csb

# module level so the skipif on the live test sees the .env values
load_dotenv()

logger = logging.getLogger(__name__)

TARGETS = {"pridec_historic_CSBMalaria", "pridec_historic_CSBRespinf", "pridec_historic_CSBDiarrhea"}
MALARIA_DX = "dx:NU6LJrW5OtP"


def _is_malaria(dx_query):
    return dx_query == MALARIA_DX


@pytest.fixture
def mocked(monkeypatch):
    """Patch the network calls in the CSB functions.

    Returns a namespace with `posts` (payload dataValues of each POST) and `calls`
    (kwargs of each get_dataElements call).
    """
    state = SimpleNamespace(posts=[], calls=[])

    def fake_get(dhis_url, token, dx_query, pe_query, ou_query, includeNumDen, co_query=None):
        state.calls.append(dict(dx_query=dx_query, co_query=co_query, includeNumDen=includeNumDen))
        if _is_malaria(dx_query):  # one row per age-group COC, summed per orgUnit/period
            return pd.DataFrame([
                {"dx": "NU6LJrW5OtP", "ou": "A", "pe": "202601", "co": "pS0pmI681Yp", "value": "3"},
                {"dx": "NU6LJrW5OtP", "ou": "A", "pe": "202601", "co": "S0U3TuqucZq", "value": "4"},
                {"dx": "NU6LJrW5OtP", "ou": "B", "pe": "202601", "co": "pS0pmI681Yp", "value": "2"},
            ])
        return pd.DataFrame([
            {"dx": "x", "ou": "A", "pe": "202601", "co": "c1", "value": "2"},
            {"dx": "y", "ou": "A", "pe": "202601", "co": "c2", "value": "5"},
            {"dx": "x", "ou": "B", "pe": "202601", "co": "c1", "value": "1"},
        ])

    def fake_post(dhis_url, payload, token, dryRun):
        state.posts.append(payload["dataValues"])
        return SimpleNamespace(ok=True, status_code=200, text="ok")

    monkeypatch.setattr(mod, "get_dataElements", fake_get)
    monkeypatch.setattr(mod, "post_dataElements", fake_post)
    return state


def test_malaria_fetches_new_endpoint_once(mocked):
    import_pivot_csb(dhis_url="u", dhis_token="t", pivot_token="p", pivot_url="pu")

    malaria_calls = [c for c in mocked.calls if _is_malaria(c["dx_query"])]
    assert malaria_calls == [dict(dx_query=MALARIA_DX, co_query=mod.CSB_PALU_COC, includeNumDen=False)]
    assert not any(c["includeNumDen"] for c in mocked.calls)


def test_posts_summed_values_for_each_element(mocked):
    import_pivot_csb(dhis_url="u", dhis_token="t", pivot_token="p", pivot_url="pu")

    vals = {v[0]["dataElement"]: {r["orgUnit"]: r["value"] for r in v} for v in mocked.posts}
    assert set(vals) == TARGETS
    assert vals["pridec_historic_CSBMalaria"] == {"A": 7, "B": 2}   # 3 + 4 across age-group COCs
    assert vals["pridec_historic_CSBRespinf"] == {"A": 7, "B": 1}
    assert vals["pridec_historic_CSBDiarrhea"] == {"A": 7, "B": 1}


def test_dryRun_false_is_forwarded(mocked, monkeypatch):
    dry_runs = []

    def fake_post(dhis_url, payload, token, dryRun):
        dry_runs.append(dryRun)
        return SimpleNamespace(ok=True, status_code=200, text="ok")

    monkeypatch.setattr(mod, "post_dataElements", fake_post)
    import_pivot_csb(dhis_url="u", dhis_token="t", pivot_token="p", pivot_url="pu", dryRun=False)
    assert dry_runs == [False] * 3


def test_posts_use_pridec_u5_coc(mocked):
    import_pivot_csb(dhis_url="u", dhis_token="t", pivot_token="p", pivot_url="pu")

    assert {r["categoryOptionCombo"] for v in mocked.posts for r in v} == {"pridec_COC_u5"}


def test_missing_value_is_skipped(mocked, monkeypatch):
    def fake_get(dhis_url, token, dx_query, pe_query, ou_query, includeNumDen, co_query=None):
        if _is_malaria(dx_query):
            return pd.DataFrame([
                {"dx": "a", "ou": "A", "pe": "202601", "co": "c", "value": "3"},
                {"dx": "a", "ou": "B", "pe": "202601", "co": "c", "value": ""},  # -> NaN
            ])
        return pd.DataFrame(columns=["dx", "ou", "pe", "co", "value"])

    monkeypatch.setattr(mod, "get_dataElements", fake_get)
    import_pivot_csb(dhis_url="u", dhis_token="t", pivot_token="p", pivot_url="pu")

    malaria = next(v for v in mocked.posts if v and v[0]["dataElement"] == "pridec_historic_CSBMalaria")
    assert {r["orgUnit"] for r in malaria} == {"A"}


def test_skips_are_logged(mocked, monkeypatch, caplog):
    def fake_get(dhis_url, token, dx_query, pe_query, ou_query, includeNumDen, co_query=None):
        if _is_malaria(dx_query):
            return pd.DataFrame([
                {"dx": "a", "ou": "A", "pe": "202601", "co": "c1", "value": ""},
                {"dx": "a", "ou": "A", "pe": "202601", "co": "c2", "value": ""},
            ])
        return pd.DataFrame([{"dx": "x", "ou": "A", "pe": "202601", "co": "c", "value": "9999"}])

    monkeypatch.setattr(mod, "get_dataElements", fake_get)
    monkeypatch.setattr("builtins.input", lambda _p: "n")
    with caplog.at_level("WARNING"):
        import_pivot_csb(dhis_url="u", dhis_token="t", pivot_token="p", pivot_url="pu")

    msgs = [r.getMessage() for r in caplog.records]
    assert any("pridec_historic_CSBMalaria: 2 source rows" in m for m in msgs)
    assert any("Skipping import of pridec_historic_CSBMalaria: no values left" in m for m in msgs)
    assert any("Skipping import of pridec_historic_CSBRespinf: failed the value check" in m for m in msgs)


def test_rejected_post_is_logged_and_others_still_post(mocked, monkeypatch, caplog):
    def fake_post(dhis_url, payload, token, dryRun):
        if payload["dataValues"][0]["dataElement"] == "pridec_historic_CSBMalaria":
            raise requests.HTTPError("409 Conflict")
        mocked.posts.append(payload["dataValues"])
        return SimpleNamespace(ok=True, status_code=200, text="ok")

    monkeypatch.setattr(mod, "post_dataElements", fake_post)
    with caplog.at_level("ERROR"):
        import_pivot_csb(dhis_url="u", dhis_token="t", pivot_token="p", pivot_url="pu")

    assert {v[0]["dataElement"] for v in mocked.posts} == TARGETS - {"pridec_historic_CSBMalaria"}
    assert "Failed to import pridec_historic_CSBMalaria" in caplog.text


# ---------------- live ----------------

LIVE_ENV = ["TEST_URL", "TEST_TOKEN"]


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

    import_pivot_csb(dhis_url=os.getenv("TEST_URL"),
                     dhis_token=os.getenv("TEST_TOKEN"),
                     pivot_url=os.getenv("TEST_URL"),
                     pivot_token=os.getenv("TEST_TOKEN"),
                     dryRun=True,
                     prior_months=2)

    # elements skipped by a failed value check are data-dependent, so log rather than fail
    for p in prompts:
        logger.warning("live data failed the value check: %s", p)

    assert responses, "no dataElement was posted (all skipped or none fetched)"

    for payload, resp in responses:
        values = payload["dataValues"]
        assert {v["dataElement"] for v in values} <= TARGETS
        assert {v["categoryOptionCombo"] for v in values} == {"pridec_COC_u5"}
        assert resp.status_code == 200

        body = resp.json()
        logger.info("dryRun response: %s", body)
        # newer DHIS2 versions nest the summary under "response"
        summary = body.get("response", body)
        counts = summary["importCount"]

        # conflicts / rejected indexes are how DHIS2 reports unknown orgUnits, elements or combos
        assert not summary.get("conflicts"), summary.get("conflicts")
        assert not summary.get("rejectedIndexes"), summary.get("rejectedIndexes")

        # every value is accounted for. "ignored" is not an error by itself, so log it
        assert sum(counts[k] for k in ("imported", "updated", "ignored")) == len(values)
        logger.info("%s: %s", values[0]["dataElement"], counts)


# ---------------- fetch_pivot_csb_etlhub ----------------

def _fetch():
    return mod.fetch_pivot_csb_etlhub(pivot_token="p", pivot_url="pu")


def test_etlhub_returns_one_item_per_element_without_posting(mocked):
    out = _fetch()

    assert mocked.posts == []  # nothing posted
    assert [i["dataElement"] for i in out] == list(mod.CSB_ELEMENTS)
    vals = {i["dataElement"]: {r["orgUnit"]: r["value"] for r in i["fetched_data"]} for i in out}
    assert vals["pridec_historic_CSBMalaria"] == {"A": 7, "B": 2}
    assert vals["pridec_historic_CSBRespinf"] == {"A": 7, "B": 1}
    assert vals["pridec_historic_CSBDiarrhea"] == {"A": 7, "B": 1}


def test_etlhub_output_is_json_serialisable(mocked):
    import json
    json.dumps(_fetch())


def test_etlhub_passing_check_is_not_flagged(mocked):
    for item in _fetch():
        assert item["summary"]["flagged"] is False
        assert item["summary"]["error"] is None
        assert item["summary"]["text"].startswith("numNA: 0")


def test_etlhub_failed_and_empty_checks_are_flagged(mocked, monkeypatch):
    def fake_get(dhis_url, token, dx_query, pe_query, ou_query, includeNumDen, co_query=None):
        if _is_malaria(dx_query):  # only a missing value, so empty after dropping it
            return pd.DataFrame([{"dx": "a", "ou": "A", "pe": "202601", "co": "c", "value": ""}])
        return pd.DataFrame([{"dx": "x", "ou": "A", "pe": "202601", "co": "c", "value": "9999"}])

    monkeypatch.setattr(mod, "get_dataElements", fake_get)
    monkeypatch.setattr("builtins.input", lambda _p: pytest.fail("etlhub must not prompt"))
    summaries = {i["dataElement"]: i["summary"] for i in _fetch()}

    assert summaries["pridec_historic_CSBMalaria"]["flagged"] is True
    assert "data is empty" in summaries["pridec_historic_CSBMalaria"]["error"]
    assert summaries["pridec_historic_CSBMalaria"]["text"].endswith("number of values: 0")
    for target in ("pridec_historic_CSBRespinf", "pridec_historic_CSBDiarrhea"):
        assert summaries[target]["flagged"] is True
        assert summaries[target]["text"].startswith("numNA: 0")
        assert "maximum value: 9999" in summaries[target]["text"]
        assert "exceed case threshold of 500" in summaries[target]["error"]
