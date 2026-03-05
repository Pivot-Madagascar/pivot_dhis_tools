from datetime import date
from dateutil.relativedelta import relativedelta
import requests
from requests.auth import HTTPBasicAuth
import json
import logging

from ..create_period_range import create_period_range

logger = logging.getLogger(__name__)

def fetch_climate(dhis_url: str, ou_level: int, ou_parent: str,
                         user: str = None, pwd: str = None, token: str = None, past_years: int = 10):
    """
    Fetch historical climate data for all praidec elements during `past_years`

    Args:
        dhis_url (str)          url of dhis instance
        ou_level (int)          numeric value of orgUnit level to extract climate data for
        ou_parent (str)         uid of parent orgUnit containing orgUnits to extract
        user (str, optional)    DHIS username
        pwd (str, optional)     DHIS password
        token (str, optional)   DHIS token
        past_years (int)        how many prior years to download. Default = 10      
        
    Returns:
        list: PRIDE-C climate data. 
            can be put into json for dhis2 using `json.dump({"dataValues": data_list}, f, indent=2)`
    """
     
    if not token and not (user and pwd):
        raise ValueError("Authentication required: provide either a token or both user and pwd")

    # Authentication setup
    headers = {'Authorization': f'ApiToken {token}'} if token else {}
    auth = None if token else HTTPBasicAuth(user, pwd)

    orgUnits = f"LEVEL-{ou_level};{ou_parent}"

    start_month = date.today().replace(day=1) - relativedelta(years=past_years)
    end_month = date.today().replace(day=1) - relativedelta(days=1)
    periods = create_period_range(start = start_month,
                                  end = end_month)
    
    #--- Identify instance-specific climate dataelement IDs from PRIDE-C -----#

    de_lookup_url = (
        f"{dhis_url}/api/dataElements"
        f"?filter=code:like:pridec_climate"
        f"&fields=id,code,displayName"
        f"&paging=false"
    )

    resp = requests.get(de_lookup_url, headers=headers, auth=auth)
    resp.raise_for_status()

    data_elements = resp.json()["dataElements"]

    if not data_elements:
        raise ValueError("No dataElements found with code prefix 'pridec_climate'")

    logger.info("Found %s dataElements with code starting 'pridec_climate'", str(len(data_elements)))

    #---- Fetch from instance and save --------------#

    flattened = []

    for element in data_elements:
        de_uid = element["id"]
        de_code = element["code"]

        analytics_url = (
            f"{dhis_url}api/analytics.json"
            f"?dimension=dx:{de_uid}"
            f"&dimension=ou:{orgUnits}"
            f"&dimension={periods}"
            f"&includeNumDen=false"
        )

        logger.info("Fetching data for %s...", de_code)

        resp = requests.get(analytics_url, headers=headers)
        resp.raise_for_status()

        data = resp.json()

        headers_map = {h['name']: i for i, h in enumerate(data.get("headers", []))}

        for row in data.get("rows", []):
            flattened.append({
                "orgUnit": row[headers_map["ou"]],
                "period": row[headers_map["pe"]],
                "dataElement": de_code,
                "value": float(row[headers_map["value"]])
            })

    

    return flattened
