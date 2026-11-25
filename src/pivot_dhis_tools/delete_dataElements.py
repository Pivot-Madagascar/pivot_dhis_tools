import requests

from .api_helpers import _raise_for_status, _api_auth
import pandas as pd
from datetime import datetime

def delete_dataElements(dhis_url: str,
                        dataElement: str,
                        delete_month_range: list[str],
                        orgUnit_ids: list[str],
                        user: str | None = None,
                        pwd: str | None = None,
                        token: str | None = None,
                        dryRun: bool = False,
                        verbose: bool = True) -> requests.Response | None:
    """Delete the values of one dataElement for a range of months and orgUnits.

    Builds one placeholder value for every month in `delete_month_range` and
    every orgUnit in `orgUnit_ids`, then POSTs them to ``/api/dataValueSets``
    with ``importStrategy=DELETE`` and ``force=true``.

    Unless `dryRun` is True, you are asked on the terminal to type ``yes``
    before anything is deleted; any other answer returns without sending
    the request.

    Args:
        dhis_url: Base URL of the DHIS2 instance (with or without a trailing slash).
        dataElement: Code (not UID) of the dataElement to delete, e.g.
            ``"pridec_climate_AOD"``.
        delete_month_range: First and last month to delete, inclusive, in
            ``YYYYMM`` format, e.g. ``["202201", "202208"]``.
        orgUnit_ids: UIDs of the orgUnits to delete data from.
        user: DHIS2 username. Required with `pwd` if `token` is not provided.
        pwd: DHIS2 password. Required with `user` if `token` is not provided.
        token: DHIS2 personal access token. Takes precedence over `user`/`pwd`.
        dryRun: If True, DHIS2 validates the deletion without saving it and
            no confirmation is asked. Default False.
        verbose: If True (default), print the ``response`` part of the
            DHIS2 import summary.

    Returns:
        The `requests.Response` from the POST request, or None if the
        deletion was not confirmed at the prompt.

    Raises:
        ValueError: If credentials are missing, or if a month in
            `delete_month_range` is not in ``YYYYMM`` format.
        requests.HTTPError: If DHIS2 returns an error status.
        requests.ConnectionError: If the server cannot be reached.
    """
    headers, auth = _api_auth(user=user, pwd=pwd, token=token)

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
    response = requests.post(url, headers=headers, auth=auth, json=delete_json, timeout = 1200)
    _raise_for_status(response, "delete dataValues")

    if verbose:
        resp_text = response.json().get("response") #for debugging
        print(resp_text)


    return response
