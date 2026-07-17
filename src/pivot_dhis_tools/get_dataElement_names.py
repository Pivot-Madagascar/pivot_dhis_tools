import requests
from requests.auth import HTTPBasicAuth
import pandas as pd

import logging
logger = logging.getLogger(__name__)

def get_dataElement_names(dhis_url: str,
                     pattern: str | None = None,
                     user:str | None = None, 
                     pwd:str | None = None, 
                     token: str | None = None):
    """
    Fetch all dataElements from a DHIS2 instance whose names match a pattern.

    Args:
        dhis_url:  Base URL of the DHIS2 instance
        pattern:   Pattern to match against dataElement names using case-insensitive substring match. Default gets all names
        user: Username for the DHIS2 instance. Required if `token` is not provided.
        pwd: Password for the DHIS2 instance. Required if `token` is not provided.
        token: Personal access token for the DHIS2 instance. Can be provided
            instead of `user` and `pwd`.

    Returns:
        List of matching dataElement dicts with 'id' and 'name'.

        View all elements via:
            for el in result:
                print(el["id"], el["name"])

        Can apply regex search to name afterwards as well
    """
     
    if not token and not (user and pwd):
        raise ValueError("Authentication required: provide either a token or both user and pwd")

    # Authentication setup
    headers = {'Authorization': f'ApiToken {token}'} if token else {}
    auth = None if token else HTTPBasicAuth(user, pwd)

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
    
    response.raise_for_status() 
    logger.debug("Response Reason: %s", response.reason)

    return response.json().get("dataElements", [])