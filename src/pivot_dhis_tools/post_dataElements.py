import requests
from requests.auth import HTTPBasicAuth

def post_dataElements(dhis_url, payload, user=None, pwd=None, token=None, 
                      dryRun=False, verbose=True):
    """
    POST dataElement values to a dhis2 instance based on the `code` scheme

    Args:
        dhis_url (str)           url of dhis2 isntance
        payload (dict)           JSON payload of climate data to send in POST. 
                                 Each item hould contain `orgUnit`, `period`, `code`, `value.
                                 orgUnits shoudl be identified by their `uid`.
        user (str, optional)     username for dhis2 instance
        pwd (str, optional)      password for dhis2 instance
        token (str, optional)    personal access token for dhis2 instance.
                                 Can be provided instead of user and pwd.
        dryRun (boolean)         True: test a dry run of the POST
                                 False (default): actually post the data 
        verbose (boolean)       True (default): return response message
                                False: return response code
    
    Returns:
        requests.Response: Response object from POST request
    """
    if not token and not (user and pwd):
        raise ValueError("Authentication required: provide either a token or both user and pwd")

    if dryRun:
        print("Conducting a dryRun of POST. Data will not be imported.")

    endpoint = (
        "api/dataValueSets"
        f"?dryRun={'true' if dryRun else 'false'}"
        "&dataElementIdScheme=code"
        "&orgUnitIdScheme=uid"
        "&categoryOptionComboIdScheme=code"
        "&idScheme=code"
        "&importStrategy=CREATE_AND_UPDATE"
    )


    url = f"{dhis_url.rstrip('/')}/{endpoint}"

    # Authentication setup
    headers = {'Authorization': f'ApiToken {token}'} if token else {}
    auth = None if token else HTTPBasicAuth(user, pwd)
    
    #send request
    response = requests.post(url, headers=headers, auth=auth, json=payload)

    # resp.json().get("httpStatus")
    # resp.json().get("status")
    # resp.json().get("message")
    

    if verbose:
        resp_text = response.json().get("response") #for debugging
        print(resp_text)
    
    return response