import requests
import json
from requests.auth import HTTPBasicAuth
from datetime import datetime
import string
import random

def update_dataStoreKey(dhis_url, user=None, pwd=None, token=None, 
                      dryRun=False, verbose=True):
    """
    POST dataElement values to a dhis2 instance based on the `code` scheme

    Args:
        dhis_url (str)           url of dhis2 isntance
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

    # Authentication setup
    headers = {'Authorization': f'ApiToken {token}'} if token else {}
    auth = None if token else HTTPBasicAuth(user, pwd)

    if dryRun:
        print("Conducting a dryRun. dataStore key will not be updated.")

    #Create key
    rand_str = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
    this_key = {
        "pridec_update": f"{rand_str}_updated_{datetime.now().strftime('%Y-%m-%d')}"
    }
    json_key = json.dumps(this_key)

    endpoint = "/api/33/dataStore/pridec/pridec_update"
    url = f"{dhis_url.rstrip('/')}/{endpoint}"

    resp = requests.put(
        url,
        headers=headers, 
        auth=auth,
        json = json_key
    )

    if verbose:
        resp_text = response.json().get("response") #for debugging
        print(resp_text)

    if resp.ok:
        print(f"Successfully updated dataStore key to {this_key['pridec_update']}")
    else:
        print(f"Failed to update dataStore key with status code {resp.status_code}")
        print("Response:", resp.text)

    return resp