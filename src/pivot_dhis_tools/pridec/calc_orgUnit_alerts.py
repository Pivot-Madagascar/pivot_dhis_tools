
import pandas as pd
from datetime import date
from dateutil.relativedelta import relativedelta

from ..get_dataElements import get_dataElements

import logging
logger = logging.getLogger(__name__)

#note that some things are hardcoded for Ifanadiana currently, particularly orgUnit
def calc_orgUnit_alerts(dhis_url: str, parent_ou: str, ou_level: int, disease_code: str,
                        token: str = None, user: str = None, pwd: str = None,
                        focal_date: date = None, 
                        forecast_json: dict = None,
                        historic_json: dict = None,
                        alert_name: str = None):
    """
    Estimate the numbers of orgUnits on alert, e.g. the number expected to see more cases over the next three months than over the same period for the prior 3 years

    Args:
        dhis_url (str)           url of dhis2 instance
        parent_ou (str)          ou ID of the parent orgUnit
        ou_level (int)        level of orgUnits for which to calculate the alert
        disease_code (str)       code of PRIDE_C disease dataElement to estimate. Is what comes after `pridec_historic_`
        user (str, optional)     username for dhis2 instance
        pwd (str, optional)      password for dhis2 instance
        token (str, optional)    personal access token for dhis2 instance.
                                 Can be provided instead of user and pwd.
        focal_date(date, optional) period for which to calculate CSB alert. If None, defaults to current month
        forecast_json       Locally-provided forecast data, in one of two
                            equivalent shapes:
                            - a dict with a top-level "dataValues" key (matching a raw DHIS2 export),
                                whose value is a list of records, e.g.:
                                    {"dataValues": [{"dataElement": ..., "orgUnit": ..., "period": ...,
                                                    "value": ...}, ...]}
                            - or that same list of records passed directly, without the
                                "dataValues" wrapper.
                            Each record must include the keys "dataElement", "orgUnit", "period",
                            and "value". If not provided, data will be sourced from the DHIS2
                            instance instead. 
        historic_json       Locally-provided historic data, follows forecast_json formatting requirements above. If not provided, data will be sourced from the DHIS2
                            instance instead. 
        alert_name          name of alert dataElement that comes after `pridec_alert_`
    
    Returns:
        JSON object with number of orgUnit on alert. Formatted to post directly to DHIS2
    """

    if forecast_json is None or historic_json is None:
        if not token and not (user and pwd):
            raise ValueError("Must provide either `token` or both `user` and `pwd` to query DHIS2")

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
