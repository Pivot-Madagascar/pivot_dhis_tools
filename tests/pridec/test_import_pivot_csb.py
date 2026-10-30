from types import SimpleNamespace

import pandas as pd
import pytest

from pivot_dhis_tools.pridec import import_pivot as mod
from pivot_dhis_tools.pridec.import_pivot import import_pivot_csb

TARGETS = {"pridec_historic_CSBMalaria", "pridec_historic_CSBRespinf", "pridec_historic_CSBDiarrhea"}


@pytest.fixture
def mocked(monkeypatch):
    """Patch the network calls in import_pivot_csb; return the list of captured posts."""
    posts = []

    def fake_get(dhis_url, token, dx_query, pe_query, ou_query, includeNumDen, co_query=None):
        if includeNumDen:  # malaria: one fetch per age group, summed across fetches
            n = {"dx:wuwA8DT9h7c": "3", "dx:PVu7GgpuJNV": "4"}[dx_query]
            return pd.DataFrame([{"dx": dx_query[3:], "ou": "A", "pe": "202601",
                                  "value": "0.5", "numerator": n}])
        return pd.DataFrame([
            {"dx": "x", "ou": "A", "pe": "202601", "co": "c1", "value": "2"},
            {"dx": "y", "ou": "A", "pe": "202601", "co": "c2", "value": "5"},
            {"dx": "x", "ou": "B", "pe": "202601", "co": "c1", "value": "1"},
        ])

    def fake_post(dhis_url, payload, token, dryRun):
        posts.append(payload["dataValues"])
        return SimpleNamespace(ok=True, status_code=200, text="ok")

    monkeypatch.setattr(mod, "get_dataElements", fake_get)
    monkeypatch.setattr(mod, "post_dataElements", fake_post)
    return posts


def test_posts_summed_values_for_each_element(mocked):
    import_pivot_csb(dhis_url="u", dhis_token="t", pivot_token="p", pivot_url="pu")

    vals = {v[0]["dataElement"]: {r["orgUnit"]: r["value"] for r in v} for v in mocked}
    assert set(vals) == TARGETS
    assert vals["pridec_historic_CSBMalaria"] == {"A": 7}   # 3 + 4 numerators
    assert vals["pridec_historic_CSBRespinf"] == {"A": 7, "B": 1}
    assert vals["pridec_historic_CSBDiarrhea"] == {"A": 7, "B": 1}


def test_nan_numerator_is_skipped(mocked, monkeypatch):
    def fake_get(dhis_url, token, dx_query, pe_query, ou_query, includeNumDen, co_query=None):
        if includeNumDen:
            return pd.DataFrame([
                {"dx": "a", "ou": "A", "pe": "202601", "value": "0.5", "numerator": "3"},
                {"dx": "a", "ou": "B", "pe": "202601", "value": "0.5", "numerator": ""},  # -> NaN
            ])
        return pd.DataFrame(columns=["dx", "ou", "pe", "co", "value"])

    monkeypatch.setattr(mod, "get_dataElements", fake_get)
    import_pivot_csb(dhis_url="u", dhis_token="t", pivot_token="p", pivot_url="pu")

    malaria = next(v for v in mocked if v and v[0]["dataElement"] == "pridec_historic_CSBMalaria")
    assert {r["orgUnit"] for r in malaria} == {"A"}


def test_skips_are_logged(mocked, monkeypatch, caplog):
    def fake_get(dhis_url, token, dx_query, pe_query, ou_query, includeNumDen, co_query=None):
        if includeNumDen:
            return pd.DataFrame([{"dx": "a", "ou": "A", "pe": "202601", "value": "0.5", "numerator": ""}])
        return pd.DataFrame([{"dx": "x", "ou": "A", "pe": "202601", "co": "c", "value": "9999"}])

    monkeypatch.setattr(mod, "get_dataElements", fake_get)
    monkeypatch.setattr("builtins.input", lambda _p: "n")
    with caplog.at_level("WARNING"):
        import_pivot_csb(dhis_url="u", dhis_token="t", pivot_token="p", pivot_url="pu")

    msgs = [r.getMessage() for r in caplog.records]
    assert any("pridec_historic_CSBMalaria: 2 source rows" in m for m in msgs)  # NaN dropped, one per fetch
    assert any("Skipping import of pridec_historic_CSBMalaria: no values left" in m for m in msgs)
    assert any("Skipping import of pridec_historic_CSBRespinf: failed the value check" in m for m in msgs)
