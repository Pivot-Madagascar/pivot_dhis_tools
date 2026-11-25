import requests

from .api_helpers import _raise_for_status, _api_auth

import logging
logger = logging.getLogger(__name__)

def get_dataElement_names(dhis_url: str,
                     pattern: str | None = None,
                     user: str | None = None,
                     pwd: str | None = None,
                     token: str | None = None) -> list[dict]:
    """Fetch the dataElements on a DHIS2 instance whose names match a pattern.

    Args:
        dhis_url: Base URL of the DHIS2 instance (with or without a trailing slash).
        pattern: Text to look for in dataElement names, matched as a
            case-insensitive substring (DHIS2 ``name:ilike`` filter). As in
            SQL ``LIKE``, ``_`` matches any single character and ``%`` any
            run of characters, so ``"pridec_"`` also matches ``"pridec "``.
            If None (default), every dataElement is returned.
        user: DHIS2 username. Required with `pwd` if `token` is not provided.
        pwd: DHIS2 password. Required with `user` if `token` is not provided.
        token: DHIS2 personal access token. Takes precedence over `user`/`pwd`.

    Returns:
        A list of dicts with keys ``id``, ``name`` and, where the
        dataElement has one, ``code``. Empty if nothing matches. To view::

            for el in result:
                print(el["id"], el["name"])

    Raises:
        ValueError: If credentials are missing.
        requests.HTTPError: If DHIS2 returns an error status.
        requests.ConnectionError: If the server cannot be reached.
        requests.Timeout: If the request takes longer than 180 seconds.
    """
    headers, auth = _api_auth(user=user, pwd=pwd, token=token)

    url = f"{dhis_url.rstrip('/')}/api/dataElements.json"

    if pattern is None:
        params = {
        "fields": "id,name,code",
        "paging": "false",
        }
    else:
        params = {
            "fields": "id,name,code",
            "filter": f"name:ilike:{pattern}",
            "paging": "false",
        }

    response = requests.get(url, params=params, headers=headers, auth=auth, timeout = 180)

    _raise_for_status(response, "fetch dataElement names")
    logger.debug("Response Reason: %s", response.reason)

    return response.json().get("dataElements", [])
