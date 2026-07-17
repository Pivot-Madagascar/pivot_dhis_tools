
import pandas as pd
from datetime import date
from dateutil.relativedelta import relativedelta

from ..get_dataElements import get_dataElements
from ..dx_code_to_uid import dx_code_to_uid

import logging
logger = logging.getLogger(__name__)

#note that some things are hardcoded for Ifanadiana currently, particularly orgUnit
def calc_orgUnit_alerts(dhis_url: str, parent_ou: str, ou_level: int, disease_code: str,
                        token: str = None, user: str = None, pwd: str = None,
                        focal_date: date = None, 
                        forecast_data: dict = None,
                        historic_data: dict = None,
                        alert_name: str = None):
    """
    Estimate the numbers of orgUnits on alert, e.g. the number expected to see more cases over the next three months than over the same period for the prior 3 years

    Args:
        dhis_url (str)           url of dhis2 instance
        parent_ou (str)          ou ID of the parent orgUnit
        ou_level (int)        level of orgUnits for which to calculate the alert
        disease_code (str)       code of PRIDE_C disease dataElement to estimate. Is what comes after pridec_historic_
        user (str, optional)     username for dhis2 instance
        pwd (str, optional)      password for dhis2 instance
        token (str, optional)    personal access token for dhis2 instance.
                                 Can be provided instead of user and pwd.
        focal_date(date, optional) period for which to calculate CSB alert. If None, defaults to current month
        forecast_data       JSON of forecasts that is stored locally. IF not available will source from DHIS2 instance
        historic_data       JSON of historic data that is stored locally. If not available will source from DHIS2 instance
        alert_name          name of alert dataElement that comes after pridec_alert
    
    Returns:
        JSON object with number of orgUnit on alert. Formatted to post directly to DHIS2
    """

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


    if forecast_data is None:
        forecast_uid = list(dx_code_to_uid(dhis_url = dhis_url,
                              codes = [f"pridec_forecast_{disease_code}Avg"],
                      token = token).values())[0]
            
        forecast_data = get_dataElements(dhis_url = dhis_url, dx_query = f"dx:pridec_forecast_{disease_code}Avg",
                                    ou_query= f"ou:LEVEL-{ou_level};{parent_ou}", 
                                    pe_query=f"pe:{';'.join(current_period_yyyymm)}",
                                    token = token,
                                    dx_id_scheme="CODE")
        
        forecast_data = forecast_data.rename(columns={'ou': 'orgUnit',
                                      'pe': 'period',
                                      'dx': 'dataElement'})
        
    else:
        forecast_data = pd.DataFrame(forecast_data["dataValues"])
        forecast_data = forecast_data[forecast_data['dataElement'].isin([f"pridec_forecast_{disease_code}Avg"])]

    forecast_data["value"] = pd.to_numeric(forecast_data["value"], errors="coerce")
    forecast_data = forecast_data[forecast_data['period'].isin(current_period_yyyymm)]

    if forecast_data.empty:
            raise ValueError(f"No forecasts exist for the period query {current_period_yyyymm}. Cannot estimate Alerts.\n"
                             "Please update the focal_date argument of the calc_CSB_alerts function and ensure the forecast exists on the DHIS2 instance.")

    #get data for historical period
    hist_period_yyyymm = []
    for i in historical_period:
        hist_period_yyyymm.append(f"{str(i.year)}{str(i.month).zfill(2)}")

    if historic_data is None:

        historic_data = get_dataElements(dhis_url = dhis_url, dx_query = f"dx:pridec_historic_{disease_code}",
                                ou_query= f"ou:LEVEL-{ou_level};{parent_ou}", 
                                pe_query=f"pe:{';'.join(hist_period_yyyymm)}",
                                token = token,
                                dx_id_scheme="CODE")
        
        historic_data = historic_data.rename(columns={'ou': 'orgUnit',
                                      'pe': 'period',
                                      'dx': 'dataElement'})
    
    else:
        historic_data = pd.DataFrame(historic_data["dataValues"])

    historic_data["value"] = pd.to_numeric(historic_data["value"], errors="coerce")
    historic_data = historic_data[historic_data['period'].isin(hist_period_yyyymm)]
        

    if historic_data.empty:
        raise ValueError(f"Historical data missing for the following dates:\n {hist_period_yyyymm}")
    
    def check_data_element(df, name, disease_code):
        unique_vals = df['dataElement'].unique()
        if len(unique_vals) != 1:
            raise ValueError(f"{name} has multiple dataElement values: {unique_vals}")
        if disease_code not in unique_vals[0]:
            raise ValueError(f"{name} dataElement ({unique_vals[0]}) does not match disease_code ({disease_code})")

    check_data_element(forecast_data, 'forecast_data', disease_code)
    check_data_element(historic_data, 'historic_data', disease_code)

    #compare periods and count CSB with higher forecasts per disease
    hist_mean = historic_data.groupby(["orgUnit"])["value"].mean().reset_index(name="hist_mean")
    # hist_mean = hist_mean.merge(de_key[['dx', 'disease']], on='dx', how='left')
    forecast_mean = forecast_data.groupby(["orgUnit"])["value"].mean().reset_index(name="forecast_mean")
    # forecast_mean = forecast_mean.merge(de_key[['dx', 'disease']], on='dx', how='left')
    comparison = hist_mean.merge(forecast_mean, on=["orgUnit"], how="inner")

    if comparison.empty:
        raise ValueError(f"orgUnits in historic_data are not found in forecast_data. Please verify the two data sources, and the `parent_ou` and `ou_level` arguments")

    count = (comparison['forecast_mean'] > comparison['hist_mean']).sum()
    num_org_alert = pd.DataFrame({
        'dataElement': [f"pridec_alert_{alert_name}"],
        'orgUnit': [parent_ou],
        'period': [this_period],
        'value' : [count]
        })

    alert_json = {"dataValues": num_org_alert[['dataElement', 'orgUnit', 'period', 'value']].to_dict(orient='records')}

    return alert_json
