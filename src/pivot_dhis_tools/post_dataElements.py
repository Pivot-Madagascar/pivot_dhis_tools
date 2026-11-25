import requests

from .api_helpers import _api_auth, _raise_for_status

import logging

logger = logging.getLogger(__name__)

def post_dataElements(dhis_url: str,
                      payload: dict,
                      user: str | None = None,
                      pwd: str | None = None,
                      token: str | None = None,
                      dryRun: bool = True,
                      dx_id_scheme: str = "code") -> requests.Response:
    """Import dataValues into a DHIS2 instance.

    POSTs `payload` to ``/api/dataValueSets`` with
    ``importStrategy=CREATE_AND_UPDATE``, so existing values are overwritten.

    Args:
        dhis_url: Base URL of the DHIS2 instance (with or without a trailing slash).
        payload: Data to import, in DHIS2 dataValueSet form::

                {"dataValues": [{"dataElement": ..., "orgUnit": ...,
                                 "period": "YYYYMM", "value": ...,
                                 "categoryOptionCombo": ...}, ...]}

            `orgUnit` must be a UID. `dataElement` and `categoryOptionCombo`
            follow `dx_id_scheme`. `categoryOptionCombo` is optional.
        user: DHIS2 username. Required with `pwd` if `token` is not provided.
        pwd: DHIS2 password. Required with `user` if `token` is not provided.
        token: DHIS2 personal access token. Takes precedence over `user`/`pwd`.
        dryRun: If True (default), DHIS2 validates the import without saving
            anything. Set to False to actually import the data.
        dx_id_scheme: How `dataElement` and `categoryOptionCombo` are
            identified in `payload`, e.g. ``"code"`` (default) or ``"uid"``.

    Returns:
        The `requests.Response` from the POST request. Its JSON body is the
        DHIS2 import summary. A 200 status can still contain conflicts or
        ignored values, so check ``importCount`` and ``conflicts`` there.

    Raises:
        ValueError: If credentials are missing.
        requests.HTTPError: If DHIS2 returns an error status (e.g. 409 when
            the whole import is rejected). The response body is logged first.
        requests.ConnectionError: If the server cannot be reached.
    """

    headers, auth = _api_auth(user=user, pwd=pwd, token=token)

    if dryRun:
        logger.info("Conducting a dryRun of POST. Data will not be imported.")

    endpoint = (
        "/api/dataValueSets"
        f"?dryRun={'true' if dryRun else 'false'}"
        f"&dataElementIdScheme={dx_id_scheme}"
        "&orgUnitIdScheme=uid"
        f"&categoryOptionComboIdScheme={dx_id_scheme}"
        "&idScheme=code"
        "&importStrategy=CREATE_AND_UPDATE"
    )


    url = f"{dhis_url.rstrip('/')}{endpoint}"


    #send request
    response = requests.post(url, headers=headers, auth=auth, json=payload)

    _raise_for_status(response, "import dataElements")

    logger.info("dataElements imported")
    logger.debug("Response: %s", response.text)

    return response
