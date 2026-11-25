import logging

import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)


def _api_auth(
    *,
    user: str | None = None,
    pwd: str | None = None,
    token: str | None = None,
) -> tuple[dict[str, str], HTTPBasicAuth | None]:
    """Build the authentication arguments for a DHIS2 API request.

    Checks that enough credentials were supplied and returns the matching
    `headers` and `auth` values to pass to `requests`. It does not contact
    the server, so wrong credentials only show up on the first request
    (usually as a 401). Use `check_dhis_connection` to verify them up front.

    Args:
        user: DHIS2 username. Required with `pwd` if `token` is not provided.
        pwd: DHIS2 password. Required with `user` if `token` is not provided.
        token: DHIS2 personal access token (e.g. ``d2pat_...``). If given,
            it takes precedence and `user`/`pwd` are ignored.

    Returns:
        A ``(headers, auth)`` tuple to unpack into a request, e.g.
        ``requests.get(url, headers=headers, auth=auth)``:

        - With `token`: ``({"Authorization": "ApiToken <token>"}, None)``
        - With `user`/`pwd`: ``({}, HTTPBasicAuth(user, pwd))``

    Raises:
        ValueError: If neither `token` nor both `user` and `pwd` are provided.
    """
    if token:
        return {"Authorization": f"ApiToken {token}"}, None
    if user and pwd:
        return {}, HTTPBasicAuth(user, pwd)
    raise ValueError(
        "Authentication required: provide either a token or both user and pwd"
    )


def _raise_for_status(response: requests.Response, action: str) -> None:
    """Log the details of a failed DHIS2 response, then raise.

    `raise_for_status` alone reports only the status and URL. The response
    body, where DHIS2 explains what went wrong (import conflicts, validation
    errors), is lost unless it is logged first.

    Args:
        response: The response to check.
        action: What the request was doing, worded to follow "Failed to",
            e.g. ``"import dataElements"``.

    Raises:
        requests.HTTPError: If the response has a 4xx or 5xx status.
    """
    if not response.ok:
        logger.error("Failed to %s: HTTP %s %s", action, response.status_code,
                     response.reason or "")
        logger.error("Response: %s", response.text or "(empty body)")
    response.raise_for_status()


def check_dhis_connection(
    dhis_url: str,
    *,
    user: str | None = None,
    pwd: str | None = None,
    token: str | None = None,
    timeout: float = 10,
) -> dict:
    """Verify that the DHIS2 server is reachable and the credentials are valid.

    Sends a GET to ``/api/me``, which returns the authenticated user's
    profile. Redirects are not followed, so a server that redirects failed
    logins to an HTML login page raises instead of passing silently.

    Args:
        dhis_url: Base URL of the DHIS2 instance (with or without a trailing slash).
        user: DHIS2 username. Required with `pwd` if `token` is not provided.
        pwd: DHIS2 password. Required with `user` if `token` is not provided.
        token: DHIS2 personal access token. Takes precedence over `user`/`pwd`.
        timeout: Seconds to wait for the server before giving up.

    Returns:
        The JSON from ``/api/me`` (the authenticated user's profile) as a dict.

    Raises:
        ValueError: If credentials are missing.
        requests.HTTPError: If the server rejects the credentials (e.g. 401)
            or responds with a redirect.
        requests.ConnectionError: If the server cannot be reached.
        requests.Timeout: If the server does not respond within `timeout`.
    """
    headers, auth = _api_auth(user=user, pwd=pwd, token=token)
    response = requests.get(
        f"{dhis_url.rstrip('/')}/api/me",
        headers=headers,
        auth=auth,
        timeout=timeout,
        allow_redirects=False,
    )
    if response.is_redirect:
        raise requests.HTTPError(
            f"Unexpected redirect ({response.status_code}) to "
            f"{response.headers.get('Location')}; credentials were likely rejected",
            response=response,
        )
    _raise_for_status(response, "connect to DHIS2")
    return response.json()
