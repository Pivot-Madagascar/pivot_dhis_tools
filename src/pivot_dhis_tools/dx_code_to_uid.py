import requests

from .api_helpers import _raise_for_status, _api_auth

import logging
logger = logging.getLogger(__name__)

def dx_code_to_uid(dhis_url: str,
                   codes: list[str],
                   user: str | None = None,
                   pwd: str | None = None,
                   token: str | None = None) -> dict[str, str]:
    """Look up the UIDs of dataElement and indicator codes.

    Queries both ``/api/dataElements`` and ``/api/indicators``, since an
    analytics `dx` dimension can hold either. If a code exists in both, the
    indicator's UID is kept.

    Args:
        dhis_url: Base URL of the DHIS2 instance (with or without a trailing slash).
        codes: dataElement and/or indicator codes to look up.
        user: DHIS2 username. Required with `pwd` if `token` is not provided.
        pwd: DHIS2 password. Required with `user` if `token` is not provided.
        token: DHIS2 personal access token. Takes precedence over `user`/`pwd`.

    Returns:
        A ``{code: uid}`` dict. Codes with no match are left out and logged
        as a warning, so the dict can be smaller than `codes` or empty.

    Raises:
        ValueError: If credentials are missing.
        requests.HTTPError: If either lookup returns an error status.
        requests.ConnectionError: If the server cannot be reached.
        requests.Timeout: If a lookup takes longer than 600 seconds.
    """
    headers, auth = _api_auth(user=user, pwd=pwd, token=token)

    base_url = dhis_url.rstrip('/')
    code_to_uid = {}

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
        _raise_for_status(resp, f"look up {endpoint} codes")
        for item in resp.json().get(endpoint, []):
            if item.get("code"):
                code_to_uid[item["code"]] = item["id"]

    missing = set(codes) - code_to_uid.keys()
    if missing:
        logger.warning("No dataElement/indicator UID found for code(s): %s", sorted(missing))

    return code_to_uid
