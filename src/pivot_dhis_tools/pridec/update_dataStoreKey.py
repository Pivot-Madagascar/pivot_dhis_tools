import requests
from datetime import datetime
import string
import random

import logging
logger = logging.getLogger(__name__)

from ..api_helpers import _api_auth, _raise_for_status

def update_dataStoreKey(dhis_url: str, user: str | None = None, pwd: str | None = None,
                        token: str | None = None, dryRun: bool = False,
                        timeout: float = 30) -> requests.Response | None:
    """Update the ``pridec/pridec_update`` dataStore key on a DHIS2 instance.

    Sets the key to ``{"pridec_update": "<random>_updated_<YYYY-MM-DD>"}``
    with a PUT, so anything watching the key can tell that new data has
    been posted. The key must already exist; DHIS2 rejects a PUT to a
    missing key.

    Args:
        dhis_url: Base URL of the DHIS2 instance (with or without a trailing slash).
        user: DHIS2 username. Required with `pwd` if `token` is not provided.
        pwd: DHIS2 password. Required with `user` if `token` is not provided.
        token: DHIS2 personal access token. Takes precedence over `user`/`pwd`.
        dryRun: If True, log the new value without contacting the server.
            Default False.
        timeout: Seconds to wait for the server. Default 30.

    Returns:
        The `requests.Response` from the PUT request, or None if `dryRun`
        is True.

    Raises:
        ValueError: If credentials are missing (checked even when `dryRun`
            is True).
        requests.HTTPError: If DHIS2 rejects the update (e.g. 404 if the
            key does not exist, 403 without write access).
        requests.ConnectionError: If the server cannot be reached.
        requests.Timeout: If the server does not respond within `timeout`.
    """

    headers, auth = _api_auth(user=user, pwd=pwd, token=token)

    #Create key
    rand_str = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
    this_key = {
        "pridec_update": f"{rand_str}_updated_{datetime.now().strftime('%Y-%m-%d')}"
    }

    if dryRun:
        logger.info("Conducting a dryRun. dataStore key would be updated to %s",
                    this_key['pridec_update'])
        return None

    endpoint = "/api/33/dataStore/pridec/pridec_update"
    url = f"{dhis_url.rstrip('/')}{endpoint}"

    resp = requests.put(
        url,
        headers=headers,
        auth=auth,
        json=this_key,
        timeout=timeout,
    )
    _raise_for_status(resp, "update dataStore key")

    logger.info("Successfully updated dataStore key to %s", this_key['pridec_update'])
    logger.debug("Response: %s", resp.text)

    return resp
