import requests
from requests.auth import HTTPBasicAuth
import pandas as pd

import logging
logger = logging.getLogger(__name__)

def get_dataElements(dhis_url, dx_query, ou_query, pe_query, 
                     user=None, pwd=None, token=None, co_query=None, includeNumDen=False):
    """
    GET dataValues for query of dataElement, orgunits, and periods

    Args:
        dhis_url (str)              url of dhis2 instance
        pivot_token (string)        personal access token for DHIS instance
        dx_query (string)           id of dataElement or Indicator to download. can supply multiple if seperated by ;. Must starts with `dx:`
        ou_query (string)           list of orgUnit ids to download. Can also be a DHIS2 call to a certain level such as ["ou:LEVEL-z7UyvgYEMRa;VtP4BdCeXIo"]
                                    Must start with `ou:`
        pe_query (string)           list of periods in YYYYMM to download, seperated by ;. Must start with `pe:`
        user (str, optional)        username for dhis2 instance
        pwd (str, optional)         password for dhis2 instance
        token (str, optional)       personal access token for dhis2 instance.
        co_query (string)           list of category options to download, seperated by;. Must start with `co:`. Default = None
        includeNumDen (boolean)     whether to download the numerator and denominator of indicators. Default = False
    Returns:
        pandas Data.Frame of data with columns ...
    """
    if not token and not (user and pwd):
        raise ValueError("Authentication required: provide either a token or both user and pwd")

    # Authentication setup
    headers = {'Authorization': f'ApiToken {token}'} if token else {}
    auth = None if token else HTTPBasicAuth(user, pwd)

    params = {
        "dimension": [q for q in [dx_query, ou_query, pe_query, co_query] if q is not None],
        "includeNumDen": includeNumDen
    }

    api_url = f"{dhis_url.rstrip('/')}/api/analytics.json?"


    response = requests.get(api_url, params=params, headers=headers, auth=auth)

    logger.debug("Response: %s", response.text)
    response.raise_for_status() 

    data_df = json_to_dataframe(response.json())

    return data_df

def json_to_dataframe(data):
    headers = [h["name"] for h in data["headers"]]  
    df = pd.DataFrame(data["rows"], columns=headers)
    return df