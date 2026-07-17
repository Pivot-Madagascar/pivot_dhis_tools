import requests
from requests.auth import HTTPBasicAuth
import pandas as pd
import re

import logging
logger = logging.getLogger(__name__)

def dx_code_to_uid(dhis_url: str, 
                              codes: list[str], 
                              user:str | None = None, 
                     pwd:str | None = None, 
                     token: str | None = None,  ) -> dict:
    """
    Look up a list of dataElement/indicator CODEs and return a {code: uid} mapping.
    Queries both /api/dataElements and /api/indicators since `dx` can contain either.
    """
    if not token and not (user and pwd):
        raise ValueError("Authentication required: provide either a token or both user and pwd")

    # Authentication setup
    headers = {'Authorization': f'ApiToken {token}'} if token else {}
    auth = None if token else HTTPBasicAuth(user, pwd)

    base_url = dhis_url.rstrip('/')
    code_to_uid = {}

    # dataSets are also valid dx items (for reporting rates), but reporting rate items
    # use the `<dataset>.REPORTING_RATE` syntax rather than a bare code, so they're
    # skipped here and passed through untouched by the caller.
    for endpoint in ("dataElements", "indicators"):
        resp = requests.get(
            f"{base_url}/api/{endpoint}.json",
            params={
                "filter": f"code:in:[{','.join(codes)}]",
                "fields": "id,code",
                "paging": "false",
            },
            headers=headers,
            auth=auth,
            timeout=600,
        )
        resp.raise_for_status()
        for item in resp.json().get(endpoint, []):
            if item.get("code"):
                code_to_uid[item["code"]] = item["id"]

    missing = set(codes) - code_to_uid.keys()
    if missing:
        logger.warning("No dataElement/indicator UID found for code(s): %s", sorted(missing))

    return code_to_uid