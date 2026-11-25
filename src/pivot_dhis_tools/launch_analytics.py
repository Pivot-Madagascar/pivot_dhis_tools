import time

import requests

from .api_helpers import _api_auth, _raise_for_status

import logging
logger = logging.getLogger(__name__)

def launch_analytics(dhis_url: str,
                     user: str | None = None,
                     pwd: str | None = None,
                     token: str | None = None) -> requests.Response:
    """Rebuild the analytics tables on a DHIS2 instance and wait for the build to finish.

    Starts the build with a POST to ``/api/33/resourceTables/analytics``,
    then checks the job's notifier endpoint every 30 seconds for up to 15
    minutes.

    Args:
        dhis_url: Base URL of the DHIS2 instance (with or without a trailing slash).
        user: DHIS2 username. Required with `pwd` if `token` is not provided.
        pwd: DHIS2 password. Required with `user` if `token` is not provided.
        token: DHIS2 personal access token. Takes precedence over `user`/`pwd`.

    Returns:
        The `requests.Response` from the POST that started the build,
        returned once the build has completed.

    Raises:
        ValueError: If credentials are missing.
        requests.HTTPError: If starting the build or checking its status
            returns an error status.
        requests.ConnectionError: If the server cannot be reached.
        requests.Timeout: If any single request takes longer than 30 seconds.
        RuntimeError: If DHIS2 reports an ERROR-level notification for the build.
        TimeoutError: If the build has not completed after 15 minutes. The
            build may still be running on the server.
    """
    headers, auth = _api_auth(user=user, pwd=pwd, token=token)

    analytics_endpoint = "/api/33/resourceTables/analytics"


    url = f"{dhis_url.rstrip('/')}{analytics_endpoint}"

    #send request
    response = requests.post(url, headers=headers, auth=auth, timeout=30)
    _raise_for_status(response, "start analytics table build")

    resp_text = response.json().get("response")
    status_url = f"{dhis_url.rstrip('/')}{resp_text['relativeNotifierEndpoint']}"
    logger.info("Successfully launched export of analytics table. Checking for completion every 30s.")
    logger.info("View status at %s", status_url)
    logger.debug("Response: %s", resp_text)

    # Poll the notifier endpoint until the most recent notification is complete
    deadline = time.monotonic() + 15 * 60
    while time.monotonic() < deadline:
        time.sleep(30)
        status_response = requests.get(status_url, headers=headers, auth=auth, timeout=30)
        _raise_for_status(status_response, "check analytics table build status")
        notifications = status_response.json()

        # notifications are listed newest first
        if notifications:
            errors = [n for n in notifications if n.get("level") == "ERROR"]
            if errors:
                logger.error("Analytics table build failed: %s", errors[0].get("message"))
                raise RuntimeError(f"Analytics table build failed: {errors[0].get('message')}")

            logger.debug("Latest status: %s", notifications[0].get("message"))
            if notifications[0].get("completed"):
                logger.info("Analytics table build completed: %s", notifications[0].get("message"))
                return response

    msg = f"Analytics table not built after 15 minutes. Investigate status endpoint {status_url}"
    logger.error(msg)
    raise TimeoutError(msg)
