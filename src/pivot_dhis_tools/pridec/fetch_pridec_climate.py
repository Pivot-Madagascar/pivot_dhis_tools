from datetime import date
from dateutil.relativedelta import relativedelta
import requests
import logging

from ..create_period_range import create_period_range
from ..api_helpers import _api_auth, _raise_for_status

logger = logging.getLogger(__name__)

def fetch_climate(dhis_url: str, ou_level: int, ou_parent: str,
                         user: str = None, pwd: str = None, token: str = None, past_years: int = 10,
                         timeout: float = 300):
    """Fetch monthly historical climate data for every PRIDE-C climate dataElement.

    Looks up all dataElements whose code contains ``pridec_climate``, then
    queries the analytics API once per dataElement for every orgUnit at
    `ou_level` under `ou_parent`. The period range runs from the same month
    `past_years` years ago through last month (the current, incomplete month
    is excluded), i.e. ``past_years * 12`` monthly periods.

    Args:
        dhis_url: Base URL of the DHIS2 instance (with or without a trailing
            slash, e.g. ``"https://dhis.example.org"``).
        ou_level: orgUnit level to return data for (e.g. ``5`` for health
            facilities).
        ou_parent: UID of the parent orgUnit; only its descendants at
            `ou_level` are returned.
        user: DHIS2 username. Required with `pwd` if `token` is not provided.
        pwd: DHIS2 password. Required with `user` if `token` is not provided.
        token: DHIS2 personal access token. Takes precedence over `user`/`pwd`.
        past_years: Number of years of history to download. Default ``10``.
        timeout: Seconds to wait for each request before giving up. Applies
            to every request separately, not the whole fetch. Default ``300``.

    Returns:
        A list of dicts, one per orgUnit/period/dataElement value returned
        by analytics::

            {"orgUnit": "<ou uid>", "period": "YYYYMM",
             "dataElement": "<dataElement code>", "value": <float>}

        `dataElement` holds the dataElement **code**, not its UID, so import
        it with ``dataElementIdScheme=CODE``. Periods with no data are absent
        rather than zero. The list is empty if analytics has no data for any
        element. To write it as a DHIS2 import file::

            json.dump({"dataValues": data_list}, f, indent=2)

    Raises:
        ValueError: If credentials are missing, or if no dataElement code
            contains ``pridec_climate``.
        requests.HTTPError: If the dataElement lookup or any analytics
            request returns an error status (e.g. 401 for bad credentials,
            409 for an invalid orgUnit or period).
        requests.ConnectionError: If the server cannot be reached.
        requests.Timeout: If any request takes longer than `timeout`.
    """

    headers, auth = _api_auth(user=user, pwd=pwd, token=token)
    dhis_url = dhis_url.rstrip("/")

    orgUnits = f"LEVEL-{ou_level};{ou_parent}"

    start_month = date.today().replace(day=1) - relativedelta(years=past_years)
    end_month = date.today().replace(day=1) - relativedelta(days=1)
    periods = create_period_range(start = start_month,
                                  end = end_month)
    
    #--- Identify instance-specific climate dataelement IDs from PRIDE-C -----#

    de_lookup_url = (
        f"{dhis_url}/api/dataElements"
        f"?filter=code:like:pridec_climate"
        f"&fields=id,code,displayName"
        f"&paging=false"
    )

    resp = requests.get(de_lookup_url, headers=headers, auth=auth, timeout=timeout)
    _raise_for_status(resp, "look up pridec_climate dataElements")

    data_elements = resp.json()["dataElements"]

    if not data_elements:
        raise ValueError("No dataElements found with code prefix 'pridec_climate'")

    logger.info("Found %s dataElements with code starting 'pridec_climate'", str(len(data_elements)))

    #---- Fetch from instance and save --------------#

    flattened = []

    for element in data_elements:
        de_uid = element["id"]
        de_code = element["code"]

        analytics_url = (
            f"{dhis_url}/api/analytics.json"
            f"?dimension=dx:{de_uid}"
            f"&dimension=ou:{orgUnits}"
            f"&dimension={periods}"
            f"&includeNumDen=false"
        )

        logger.info("Fetching data for %s...", de_code)

        resp = requests.get(analytics_url, headers=headers, auth=auth, timeout=timeout)
        _raise_for_status(resp, "fetch climate analytics data")

        data = resp.json()

        headers_map = {h['name']: i for i, h in enumerate(data.get("headers", []))}

        for row in data.get("rows", []):
            flattened.append({
                "orgUnit": row[headers_map["ou"]],
                "period": row[headers_map["pe"]],
                "dataElement": de_code,
                "value": float(row[headers_map["value"]])
            })

    

    return flattened
