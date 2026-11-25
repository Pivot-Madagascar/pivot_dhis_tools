
import pandas as pd
from datetime import date
from dateutil.relativedelta import relativedelta

from ..get_dataElements import get_dataElements
from ..api_helpers import _api_auth

import logging
logger = logging.getLogger(__name__)

#note that some things are hardcoded for Ifanadiana currently, particularly orgUnit
def calc_orgUnit_alerts(dhis_url: str, parent_ou: str, ou_level: int, disease_code: str,
                        token: str | None = None, user: str | None = None, pwd: str | None = None,
                        focal_date: date | None = None,
                        forecast_json: dict | list | None = None,
                        historic_json: dict | list | None = None,
                        alert_name: str | None = None) -> dict:
    """Count the orgUnits on alert for one PRIDE-C disease.

    An orgUnit at `ou_level` under `parent_ou` is on alert when its mean
    ``pridec_forecast_<disease_code>Avg`` over the three months starting at
    `focal_date` is higher than its mean ``pridec_historic_<disease_code>``
    over the same three months in the prior three years. Equal means are
    not on alert. orgUnits missing from either dataset are left out of the
    count and logged as a warning.

    Each dataset is read from `forecast_json` / `historic_json` if given,
    otherwise fetched from DHIS2 with `get_dataElements`. Credentials are
    only needed when at least one dataset is fetched.

    Args:
        dhis_url: Base URL of the DHIS2 instance (with or without a trailing slash).
        parent_ou: UID of the parent orgUnit. The result is posted to it.
        ou_level: orgUnit level to compare (e.g. ``5`` for CSBs).
        disease_code: Disease part of the PRIDE-C dataElement codes, i.e.
            what follows ``pridec_historic_`` (e.g. ``"COMRespinf"``).
        token: DHIS2 personal access token. Takes precedence over `user`/`pwd`.
        user: DHIS2 username. Required with `pwd` if `token` is not provided
            and a dataset has to be fetched.
        pwd: DHIS2 password. Required with `user` if `token` is not provided
            and a dataset has to be fetched.
        focal_date: Any day in the first month of the forecast window. If
            None (default), the current month is used.
        forecast_json: Forecast data to use instead of fetching it, either a
            raw DHIS2 export ``{"dataValues": [record, ...]}`` or the list of
            records itself. Each record needs ``dataElement`` (code),
            ``orgUnit``, ``period`` (``YYYYMM``) and ``value``. Records for
            other dataElements or periods are ignored. Not modified.
        historic_json: Historic data to use instead of fetching it, in the
            same form as `forecast_json`.
        alert_name: What follows ``pridec_alert_`` in the output dataElement
            code. Defaults to `disease_code`.

    Returns:
        A dict ready to POST with `post_dataElements`, holding one record::

            {"dataValues": [{"dataElement": "pridec_alert_<alert_name>",
                             "orgUnit": parent_ou, "period": "YYYYMM",
                             "value": <number of orgUnits on alert>}]}

        where ``period`` is the month of `focal_date`.

    Raises:
        ValueError: If credentials are needed but missing; if local data is
            missing a required key, has no records for the disease, or has
            non-numeric or missing values; if there is no forecast or no
            historic data for the window; or if no orgUnit has both.
        requests.HTTPError: If fetching from DHIS2 returns an error status.
        requests.ConnectionError: If the server cannot be reached.
    """

    if forecast_json is None or historic_json is None:
        _api_auth(user=user, pwd=pwd, token=token)

    def get_historical_periods(dates, years_prior=3):
        out = []
        
        for d in dates:
            for i in range(1, years_prior + 1):
                out.append(d.replace(year=d.year - i))
        
        return out
    
    if alert_name is None:
        alert_name = disease_code
    
    if focal_date is None:
        first_this_month = date.today().replace(day=1)
    else:
        first_this_month = focal_date.replace(day=1)
    
    this_period = f"{str(first_this_month.year)}{str(first_this_month.month).zfill(2)}"
    current_period = [first_this_month,
                    first_this_month + relativedelta(months=1),
                    first_this_month + relativedelta(months=2)
                    ]
    historical_period = get_historical_periods(dates = current_period)

    #get forecasts for current period
    current_period_yyyymm = []
    for i in current_period:
        current_period_yyyymm.append(f"{str(i.year)}{str(i.month).zfill(2)}")


    if forecast_json is None: #get data from instance
        forecast_data = get_dataElements(dhis_url = dhis_url, dx_query = f"dx:pridec_forecast_{disease_code}Avg",
                                    ou_query= f"ou:LEVEL-{ou_level};{parent_ou}", 
                                    pe_query=f"pe:{';'.join(current_period_yyyymm)}",
                                    token = token,
                                    user=user,
                                    pwd = pwd,
                                    dx_id_scheme="CODE")
        
        forecast_data = forecast_data.rename(columns={'ou': 'orgUnit',
                                      'pe': 'period',
                                      'dx': 'dataElement'})
    #use locally provided data    
    else:
        #flexibility for direct export from DHIS2, which uses "dataValues"
        if isinstance(forecast_json, dict) and "dataValues" in forecast_json:
            forecast_data = pd.DataFrame(forecast_json["dataValues"])
        else:    
            forecast_data = pd.DataFrame(forecast_json)
        
        #check for columns and format
        required_cols = {"dataElement", "orgUnit", "period", "value"}
        missing_cols = required_cols - set(forecast_data.columns)
        if missing_cols:
            raise ValueError(f"forecast_data is missing required columns: {missing_cols}")
        forecast_data = forecast_data[forecast_data['dataElement'].isin([f"pridec_forecast_{disease_code}Avg"])]
        if forecast_data.empty:
            raise ValueError(f"pridec_forecast_{disease_code}Avg not found in provided forecast json. Ensure you have specified the proper `disease_code`.")

    forecast_data["value"] = pd.to_numeric(forecast_data["value"], errors="coerce")
    if forecast_data["value"].isna().any():
        raise ValueError(f"Non-numeric or missing values found in forecast data for {disease_code}: "
                        f"{forecast_data[forecast_data['value'].isna()]}")
    
    forecast_data = forecast_data[forecast_data['period'].isin(current_period_yyyymm)]
    if forecast_data.empty:
            raise ValueError(f"No forecasts exist for the period query {current_period_yyyymm}. Cannot estimate Alerts.\n"
                             "Please update the focal_date argument of the calc_orgUnit_alerts function and ensure the date range exists in forecast data.")

    #get data for historical period
    hist_period_yyyymm = []
    for i in historical_period:
        hist_period_yyyymm.append(f"{str(i.year)}{str(i.month).zfill(2)}")

    if historic_json is None:

        historic_data = get_dataElements(dhis_url = dhis_url, dx_query = f"dx:pridec_historic_{disease_code}",
                                ou_query= f"ou:LEVEL-{ou_level};{parent_ou}", 
                                pe_query=f"pe:{';'.join(hist_period_yyyymm)}",
                                token = token,
                                user = user,
                                pwd = pwd,
                                dx_id_scheme="CODE")
        
        historic_data = historic_data.rename(columns={'ou': 'orgUnit',
                                      'pe': 'period',
                                      'dx': 'dataElement'})
    
    else:
        if isinstance(historic_json, dict) and "dataValues" in historic_json:
            historic_data = pd.DataFrame(historic_json["dataValues"])
        else:
            historic_data = pd.DataFrame(historic_json)
        required_cols = {"dataElement", "orgUnit", "period", "value"}
        missing_cols = required_cols - set(historic_data.columns)
        if missing_cols:
            raise ValueError(f"historic_data is missing required columns: {missing_cols}")
        historic_data = historic_data[historic_data['dataElement'].isin([f"pridec_historic_{disease_code}"])]
        if historic_data.empty:
            raise ValueError(f"pridec_historic_{disease_code} not found in provided historic data. Ensure you have specified the proper `disease_code`.")

    historic_data["value"] = pd.to_numeric(historic_data["value"], errors="coerce")
    if historic_data["value"].isna().any():
        raise ValueError(f"Non-numeric or missing values found in historic data for {disease_code}: "
                        f"{historic_data[historic_data['value'].isna()]}")
    
    historic_data = historic_data[historic_data['period'].isin(hist_period_yyyymm)]
    if historic_data.empty:
        raise ValueError(f"Historical data missing for the following dates:\n {hist_period_yyyymm}")

    #compare periods and count CSB with higher forecasts per disease
    hist_mean = historic_data.groupby(["orgUnit"])["value"].mean().reset_index(name="hist_mean")
    forecast_mean = forecast_data.groupby(["orgUnit"])["value"].mean().reset_index(name="forecast_mean")

    missing_from_forecast = set(hist_mean["orgUnit"]) - set(forecast_mean["orgUnit"])
    missing_from_historic = set(forecast_mean["orgUnit"]) - set(hist_mean["orgUnit"])
    if missing_from_forecast or missing_from_historic:
        logger.warning(f"orgUnits dropped from comparison for alert — missing forecast: {missing_from_forecast}, "
                        f"missing historic: {missing_from_historic}")

    comparison = hist_mean.merge(forecast_mean, on=["orgUnit"], how="inner")

    if comparison.empty:
        raise ValueError(f"orgUnits in historic data are not found in forecast data. Please verify the two data sources, and the `parent_ou` and `ou_level` arguments")

    count = (comparison['forecast_mean'] > comparison['hist_mean']).sum()
    num_org_alert = pd.DataFrame({
        'dataElement': [f"pridec_alert_{alert_name}"],
        'orgUnit': [parent_ou],
        'period': [this_period],
        'value' : [count]
        })

    alert_json = {"dataValues": num_org_alert[['dataElement', 'orgUnit', 'period', 'value']].to_dict(orient='records')}

    return alert_json
