import requests
from requests.auth import HTTPBasicAuth

def launch_analytics(dhis_url, user=None, pwd=None, token=None,  verbose=True):
    """
    Launches Analytics Tables on a dhis2 instance

    Args:
        dhis_url (str)           url of dhis2 isntance
        user (str, optional)     ousername for dhis2 instance
        pwd (str, optional)      password for dhis2 instance
        token (str, optional)    personal access token for dhis2 instance.
                                 Can be provided instead of user and pwd.
        verbose (boolean)       True (default): return response message
                                False: return response code
    
    Returns:
        requests.Response: Response object from POST request
    """
    if not token and not (user and pwd):
        raise ValueError("Authentication required: provide either a token or both user and pwd")

    endpoint = "api/33/resourceTables/analytics"


    url = f"{dhis_url.rstrip('/')}/{endpoint}"

    # Authentication setup
    headers = {'Authorization': f'ApiToken {token}'} if token else {}
    auth = None if token else HTTPBasicAuth(user, pwd)
    
    #send request
    response = requests.post(url, headers=headers, auth=auth)

    # resp.json().get("httpStatus")
    # resp.json().get("status")
    # resp.json().get("message")
    # resp_text = response.json().get("response") #for debugging

    if response.ok:
        analytics_endpoint = response.json().get("response")['relativeNotifierEndpoint']
        print(f"Successfully launched export of analytics table.")
        print(f"View status at {dhis_url.rstrip('/')}{analytics_endpoint}")

    if verbose:
        resp_text = response.json().get("response") #for debugging
        print(resp_text)
    
    return response