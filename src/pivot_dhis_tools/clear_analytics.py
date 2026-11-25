import requests

from .api_helpers import _api_auth, _raise_for_status

import logging
logger = logging.getLogger(__name__)

def clear_analytics(dhis_url: str,
                     user: str | None = None,
                     pwd: str | None = None,
                     token: str | None = None) -> requests.Response:
    """Drop all analytics tables on a DHIS2 instance.

    Sends a POST to ``/api/maintenance/analyticsTablesClear``. Analytics
    queries return no data until the tables are rebuilt, e.g. with
    `launch_analytics`.

    Args:
        dhis_url: Base URL of the DHIS2 instance (with or without a trailing slash).
        user: DHIS2 username. Required with `pwd` if `token` is not provided.
        pwd: DHIS2 password. Required with `user` if `token` is not provided.
        token: DHIS2 personal access token. Takes precedence over `user`/`pwd`.

    Returns:
        The `requests.Response` from the POST request.

    Raises:
        ValueError: If credentials are missing.
        requests.HTTPError: If DHIS2 returns an error status (e.g. 401 for
            bad credentials, 403 if the user lacks maintenance authority).
        requests.ConnectionError: If the server cannot be reached.
    """
    headers, auth = _api_auth(user=user, pwd=pwd, token=token)
    clear_cache_endpoint = "/api/maintenance/analyticsTablesClear"
    url = f"{dhis_url.rstrip('/')}{clear_cache_endpoint}"

    #send request
    response = requests.post(url, headers=headers, auth=auth, timeout = 120)
    _raise_for_status(response, "clear analytics tables")

    logger.info("Analytics tables dropped.")
    logger.debug("Response: %s", response.text)

    return response
