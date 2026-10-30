import time

import requests
from requests.auth import HTTPBasicAuth

import logging
logger = logging.getLogger(__name__)

def launch_analytics(dhis_url: str,
                     user: str | None = None, 
                     pwd: str | None = None, 
                     token: str | None = None):
    """
    Rebuilds Analytics Tables on a DHIS2 instance and waits for the build to complete

    Args:
        dhis_url: URL of the DHIS2 instance.
        user: Username for the DHIS2 instance. Required if `token` is not provided.
        pwd: Password for the DHIS2 instance. Required if `token` is not provided.
        token: Personal access token for the DHIS2 instance. Can be provided
            instead of `user` and `pwd`.

    Returns:
        requests.Response: Response object from POST request
    """
    if not token and not (user and pwd):
        raise ValueError("Authentication required: provide either a token or both user and pwd")
    
    # Authentication setup
    headers = {'Authorization': f'ApiToken {token}'} if token else {}
    auth = None if token else HTTPBasicAuth(user, pwd)

    analytics_endpoint = "/api/33/resourceTables/analytics"


    url = f"{dhis_url.rstrip('/')}{analytics_endpoint}"
    
    #send request
    response = requests.post(url, headers=headers, auth=auth, timeout=30)
    response.raise_for_status()

    resp_text = response.json().get("response")

    if response.ok:
        analytics_endpoint = response.json().get("response")['relativeNotifierEndpoint']
        status_url = f"{dhis_url.rstrip('/')}{analytics_endpoint}"
        logger.info("Successfully launched export of analytics table. Checking for completion every 30s.")
        logger.info("View status at %s", status_url)
        logger.debug("Response: %s", resp_text)
    else:
        logger.error("Analytics table build failed to start with response: %s", resp_text)
        return response

    # Poll the notifier endpoint until the most recent notification is complete
    deadline = time.monotonic() + 15 * 60
    while time.monotonic() < deadline:
        time.sleep(30)
        status_response = requests.get(status_url, headers=headers, auth=auth, timeout=30)
        status_response.raise_for_status()
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