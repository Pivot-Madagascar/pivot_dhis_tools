import requests
from requests.auth import HTTPBasicAuth

import logging

logger = logging.getLogger(__name__)

def post_dataElements(dhis_url: str,
                      payload: dict,
                      user:str | None = None, 
                      pwd:str | None = None, 
                      token: str | None = None, 
                      dryRun: bool = True):
    """
    POST dataElement values to a dhis2 instance based on the `code` scheme

    Args:
        dhis_url: URL of the DHIS2 instance.
        payload: JSON payload of dataElement values to send. Each item should contain `orgUnit`, `period`, `code`, `value`.
                                 orgUnits should be identified by their `uid`.
        user: Username for the DHIS2 instance. Required if `token` is not provided.
        pwd: Password for the DHIS2 instance. Required if `token` is not provided.
        token: Personal access token for the DHIS2 instance. Can be provided
            instead of `user` and `pwd`.
        dryRun: If True, performs a dry run without actually posting data.
            If False, executes the POST request.
    
    Returns:
        requests.Response: Response object from POST request
    """
    if not token and not (user and pwd):
        logger.error("Authentication required: provide either a token or both user and pwd")
        raise SystemExit(1)

    if dryRun:
        logger.info("Conducting a dryRun of POST. Data will not be imported.")

    endpoint = (
        "/api/dataValueSets"
        f"?dryRun={'true' if dryRun else 'false'}"
        "&dataElementIdScheme=code"
        "&orgUnitIdScheme=uid"
        "&categoryOptionComboIdScheme=code"
        "&idScheme=code"
        "&importStrategy=CREATE_AND_UPDATE"
    )


    url = f"{dhis_url.rstrip('/')}{endpoint}"

    # Authentication setup
    headers = {'Authorization': f'ApiToken {token}'} if token else {}
    auth = None if token else HTTPBasicAuth(user, pwd)
    
    #send request
    response = requests.post(url, headers=headers, auth=auth, json=payload)
    response.raise_for_status()

    # resp.json().get("httpStatus")
    # resp.json().get("status")
    # resp.json().get("message")
    

    if response.ok:
        logger.info("dataElements imported")
        logger.debug("Response: %s", response.text)
    else:
        logger.error("Failed to import dataElements")
        logger.error("Response: %s", response.text)
    
    return response