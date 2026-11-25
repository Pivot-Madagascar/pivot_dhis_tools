import requests

from .api_helpers import _raise_for_status, _api_auth
import pandas as pd

from.dx_code_to_uid import dx_code_to_uid

import logging
logger = logging.getLogger(__name__)

def get_dataElements(dhis_url: str,
                     dx_query: str,
                     ou_query: str,
                     pe_query: str,
                     user: str | None = None,
                     pwd: str | None = None,
                     token: str | None = None,
                     co_query: str | None = None,
                     includeNumDen: bool = False,
                     dx_id_scheme: str | None = None) -> pd.DataFrame:
    """Fetch analytics values for a set of dataElements/indicators, orgUnits and periods.

    Sends one GET to ``/api/analytics.json`` with the given dimensions.

    Args:
        dhis_url: Base URL of the DHIS2 instance (with or without a trailing slash).
        dx_query: dataElements or indicators to fetch, starting with ``dx:``
            and separated by ``;``, e.g. ``"dx:fbfJHSPpUQD;cYeuwXTCPkU"``.
            Give UIDs, or codes if `dx_id_scheme` is ``"CODE"``.
        ou_query: orgUnits to fetch, starting with ``ou:`` and separated by
            ``;``. Can use DHIS2 keywords, e.g.
            ``"ou:LEVEL-5;VtP4BdCeXIo"`` for every level 5 orgUnit under
            ``VtP4BdCeXIo``.
        pe_query: Periods to fetch, starting with ``pe:`` and separated by
            ``;``, e.g. ``"pe:202401;202402"``. See `create_period_range`.
        user: DHIS2 username. Required with `pwd` if `token` is not provided.
        pwd: DHIS2 password. Required with `user` if `token` is not provided.
        token: DHIS2 personal access token. Takes precedence over `user`/`pwd`.
        co_query: Category option combos to split by, starting with ``co:``
            and separated by ``;``. Optional; if given, the result has a
            ``co`` column.
        includeNumDen: Whether to also return the numerator and denominator
            of indicators. Default False.
        dx_id_scheme: Set to ``"CODE"`` to give codes instead of UIDs in
            `dx_query`. The codes are looked up with `dx_code_to_uid` and the
            ``dx`` column of the result is mapped back to codes. A code with
            no match is sent to DHIS2 unchanged (and logged as a warning),
            which usually makes DHIS2 reject the query. Any other value,
            including the default None, uses UIDs.

    Returns:
        A `pandas.DataFrame` with one row per value and a column per
        dimension returned by DHIS2: usually ``dx``, ``ou``, ``pe`` (and
        ``co`` if `co_query` is given), and ``value``. Values are strings,
        as DHIS2 returns them. Empty (with those columns) if there is no data.

    Raises:
        ValueError: If credentials are missing.
        requests.HTTPError: If the analytics request, or the code lookup when
            `dx_id_scheme` is ``"CODE"``, returns an error status (e.g. 409
            for an unknown dataElement, orgUnit or period).
        requests.ConnectionError: If the server cannot be reached.
        requests.Timeout: If the request takes longer than 600 seconds.
    """
    headers, auth = _api_auth(user=user, pwd=pwd, token=token)

    # look up dx from code
    uid_to_code = {}
    if dx_id_scheme == "CODE":
        codes = dx_query.removeprefix("dx:").split(";")

        code_to_uid = dx_code_to_uid(
            dhis_url,
            codes,
            user=user,
            pwd=pwd,
            token=token,
        )
        # Keep original order; fall back to the raw code if no match was found
        resolved_dx_query = "dx:" + ";".join(code_to_uid.get(c, c) for c in codes)
        #for reverse-mapping afterwards
        uid_to_code = {v: k for k, v in code_to_uid.items()}
    else:
        resolved_dx_query = dx_query

    params = {
        "dimension": [q for q in [resolved_dx_query, ou_query, pe_query, co_query] if q is not None],
        "includeNumDen": includeNumDen
    }

    api_url = f"{dhis_url.rstrip('/')}/api/analytics.json"


    response = requests.get(api_url, params=params, headers=headers, auth=auth, timeout = 600)

    logger.debug("Response Reason: %s", response.reason)
    _raise_for_status(response, "fetch analytics data")

    data_df = json_to_dataframe(response.json())

    # map dx column back from UID to the original codes
    if uid_to_code and "dx" in data_df.columns:
        data_df["dx"] = data_df["dx"].replace(uid_to_code)

    return data_df

def json_to_dataframe(data: dict) -> pd.DataFrame:
    """Convert a DHIS2 analytics JSON response to a DataFrame.

    Args:
        data: Parsed analytics response with ``headers`` (a list of dicts
            with a ``name`` key) and ``rows`` (a list of lists).

    Returns:
        A `pandas.DataFrame` with one column per header, named by the
        header's ``name``, and one row per entry in ``rows``.

    Raises:
        KeyError: If `data` has no ``headers`` or ``rows`` key.
    """
    headers = [h["name"] for h in data["headers"]]
    df = pd.DataFrame(data["rows"], columns=headers)
    return df
