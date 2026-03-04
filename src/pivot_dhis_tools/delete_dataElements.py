import requests
from requests.auth import HTTPBasicAuth
import pandas as pd
from datetime import datetime

def delete_dataElements(dhis_url, dataElement, delete_month_range, orgUnit_ids, 
                        user=None, pwd=None, token=None, dryRun=False, verbose=True):
    """
    Deletes climate dataElement values from the provided date range and orgUnits

    Args:
        dhis_url (str)              url of dhis2 instance
        dataElement (str)           code of dataElement to delete. Example: 'pridec_climate_AOD'
        delete_month_range (list)   range of months of data to delete in YYYYMM format. Example: ["202201", "202208"]
        orgUnit_ids (list)          list of orgUnit ids to delete data from
        user (str, optional)        username for dhis2 instance
        pwd (str, optional)         password for dhis2 instance
        token (str, optional)       personal access token for dhis2 instance.
                                    Can be provided instead of user and pwd.
        dryRun (boolean)            True: test a dry run of the POST
                                    False: actually post the data
        verbose (boolean)           True (default): return response message
                                    False: return response code
    
    Returns:
        requests.Response: Response object from DELETE request
    """
    if not token and not (user and pwd):
        raise ValueError("Authentication required: provide either a token or both user and pwd")
    
    # Authentication setup
    headers = {'Authorization': f'ApiToken {token}'} if token else {}
    auth = None if token else HTTPBasicAuth(user, pwd)
    
    #create json of full range to delete
    start_date = datetime.strptime(delete_month_range[0], "%Y%m")
    end_date = datetime.strptime(delete_month_range[1], "%Y%m")

    df_periods = pd.DataFrame({'period': pd.date_range(start = start_date, end = end_date, freq = 'MS')})
    df_periods['period'] = df_periods['period'].dt.strftime('%Y%m')
    df_orgUnit = pd.DataFrame({'orgUnit': orgUnit_ids})

    full_range = df_periods.merge(df_orgUnit, how = 'cross')
    full_range['dataElement'] = dataElement
    full_range['value'] = 9999

    delete_json = {"dataValues": full_range.to_dict(orient='records')}

    endpoint = (
        "api/dataValueSets"
        f"?dryRun={'true' if dryRun else 'false'}"
        "&dataElementIdScheme=code"
        "&orgUnitIdScheme=uid"
        "&categoryOptionComboIdScheme=code"
        "&idScheme=code"
        "&importStrategy=DELETE"
        "&force=true"
    )


    url = f"{dhis_url.rstrip('/')}/{endpoint}"
    
    if dryRun is False:
        print("!! You are not in dryRun mode. This will delete data on your instance. !!")
        validate_delete = input("Confirm that you want to continue (yes/no):")
        if validate_delete != "yes":
            print("Exiting process without deleting...")
            return


    #send request
    response = requests.post(url, headers=headers, auth=auth, json=delete_json)

    if verbose:
        resp_text = response.json().get("response") #for debugging
        print(resp_text)
    

    return response