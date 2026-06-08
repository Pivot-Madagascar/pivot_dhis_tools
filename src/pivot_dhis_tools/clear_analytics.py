import requests
from requests.auth import HTTPBasicAuth

import logging
logger = logging.getLogger(__name__)

def clear_analytics(dhis_url: str,
                     user: str | None = None, 
                     pwd: str | None = None, 
                     token: str | None = None):
    """
    Clears Analytics table cache

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

    clear_cache_endpoint = "/api/maintenance/analyticsTablesClear"

    url = f"{dhis_url.rstrip('/')}{clear_cache_endpoint}"

        #send request
    response = requests.post(url, headers=headers, auth=auth)
    response.raise_for_status()

    resp_text = response.json().get("response")
    if response.ok:
        logger.info("Analytics tables dropped.")
        logger.debug("Response: %s", resp_text)
    else: 
        logger.error("Error clearing analytics tables with response: %s", resp_text)

    return response