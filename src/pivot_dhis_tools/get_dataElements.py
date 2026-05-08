import requests
from requests.auth import HTTPBasicAuth
import pandas as pd

import logging
logger = logging.getLogger(__name__)

def get_dataElements(dhis_url: str,
                     dx_query: str, 
                     ou_query:str, 
                     pe_query: str, 
                     user:str | None = None, 
                     pwd:str | None = None, 
                     token: str | None = None,  
                     co_query: str | None=None, 
                     includeNumDen: bool = False):
    """
    GET dataValues for query of dataElement, orgunits, and periods

    Args:
        dhis_url: URL of the DHIS2 instance.
        dx_query: id of dataElement or Indicator to download. can supply multiple if seperated by ;. Must starts with `dx:`
        ou_query: list of orgUnit ids to download. 
                    Can also be a DHIS2 call to a certain level such as ["ou:LEVEL-z7UyvgYEMRa;VtP4BdCeXIo"]
                     Must start with `ou:`
        pe_query:  list of periods in YYYYMM to download, seperated by ;. Must start with `pe:`
        user: Username for the DHIS2 instance. Required if `token` is not provided.
        pwd: Password for the DHIS2 instance. Required if `token` is not provided.
        token: Personal access token for the DHIS2 instance. Can be provided
            instead of `user` and `pwd`.
        co_query: list of category options to download, seperated by;. Must start with `co:`. Optional.
        includeNumDen : whether to download the numerator and denominator of indicators. Default = False

    Returns:
        pandas Data.Frame of data with columns 
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


    response = requests.get(api_url, params=params, headers=headers, auth=auth, timeout = 600)

    logger.debug("Response Reason: %s", response.reason)
    response.raise_for_status() 

    data_df = json_to_dataframe(response.json())

    return data_df

def json_to_dataframe(data):
    headers = [h["name"] for h in data["headers"]]  
    df = pd.DataFrame(data["rows"], columns=headers)
    return df