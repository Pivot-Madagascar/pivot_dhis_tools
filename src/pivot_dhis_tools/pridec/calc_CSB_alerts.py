
import pandas as pd
from datetime import date
from dateutil.relativedelta import relativedelta

from ..get_dataElements import get_dataElements

import logging
logger = logging.getLogger(__name__)

#note that some things are hardcoded for Ifanadiana currently, particularly orgUnit
def calc_CSB_alerts(dhis_url: str, token: str = None, user: str = None, pwd: str = None,
                    focal_date: date = None):
    """
    Estimate the numbers of CSB on alert for each disease, e.g. the number expected to see more cases over the next three months than over the same period for the prior 3 years

    Args:
        dhis_url (str)           url of dhis2 isntance
        user (str, optional)     username for dhis2 instance
        pwd (str, optional)      password for dhis2 instance
        token (str, optional)    personal access token for dhis2 instance.
                                 Can be provided instead of user and pwd.
        focal_date(date, optional) period for which to calculate CSB alert. If None, defaults to current month
    
    Returns:
        JSON object with number of CSB on alert per disease. Formatted to post directly to DHIS2
    """

    de_key = pd.DataFrame({
        'dx': ["fxlyV7TBKHn", "nlqM0kFSov2", "PVomHTNt4FR",
                "Kho6sN2pCZP", "IqGEQ8eMi9H", "xSg8GomKjHJ"],
        'ind_name': ["hist_palu", "hist_diar", "hist_resp",
                    "forecast_palu", "forecast_diar", "forecast_resp"],
        'disease':  ["palu", "diar", "resp", "palu", "diar", "resp"]
    })

    def get_historical_periods(dates, years_prior=3):
        out = []
        
        for d in dates:
            for i in range(1, years_prior + 1):
                out.append(d.replace(year=d.year - i))
        
        return out
    
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
    current_period_yyyymm  = f"pe:{';'.join(current_period_yyyymm)}"

    forecast_data = get_dataElements(dhis_url = dhis_url, dx_query = f"dx:{';'.join(de_key['dx'][3:6])}",
                                ou_query= "ou:LEVEL-5;VtP4BdCeXIo", pe_query=current_period_yyyymm,
                                token = token)
    if forecast_data.empty:
        raise ValueError(f"No forecasts exist for the period query {current_period_yyyymm}. Cannot estimate 'CSB en Vigilance'.\nPlease update the focal_date argument of the calc_CSB_alerts function and ensure the forecast exists on the DHIS2 instance.")

    forecast_data["value"] = pd.to_numeric(forecast_data["value"], errors="coerce")

    #get data for historical period
    hist_period_yyyymm = []
    for i in historical_period:
        hist_period_yyyymm.append(f"{str(i.year)}{str(i.month).zfill(2)}")
    hist_period_yyyymm  = f"pe:{';'.join(hist_period_yyyymm)}"

    hist_data = get_dataElements(dhis_url = dhis_url, dx_query = f"dx:{';'.join(de_key['dx'][0:3])}",
                                ou_query= "ou:LEVEL-5;VtP4BdCeXIo", pe_query=hist_period_yyyymm,
                                token = token)
    hist_data["value"] = pd.to_numeric(hist_data["value"], errors="coerce")
    if hist_data.empty:
        raise ValueError(f"Historical data missing for the following dates:\n {hist_period_yyyymm}")

    #compare periods and count CSB with higher forecasts per disease
    hist_mean = hist_data.groupby(["ou", "dx"])["value"].mean().reset_index(name="hist_mean")
    hist_mean = hist_mean.merge(de_key[['dx', 'disease']], on='dx', how='left')
    forecast_mean = forecast_data.groupby(["ou", "dx"])["value"].mean().reset_index(name="forecast_mean")
    forecast_mean = forecast_mean.merge(de_key[['dx', 'disease']], on='dx', how='left')
    comparison = hist_mean.merge(forecast_mean, on=["ou", "disease"], how="inner")
    num_csb_alert = comparison.groupby("disease").apply(
        lambda df: (df["forecast_mean"] > df["hist_mean"]).sum()
        ).reset_index(name="value")

    #reformat as JSON to send
    num_csb_alert['dataElement'] = num_csb_alert['disease'].map({
        "palu": "pridec_alert_CSBMalariaVigilance",
        "diar": "pridec_alert_CSBDiarrheaVigilance",
        "resp": "pridec_alert_CSBRespinfVigilance"
    })

    num_csb_alert['orgUnit'] = "VtP4BdCeXIo"
    num_csb_alert['period'] = this_period

    alert_json = {"dataValues": num_csb_alert[['dataElement', 'orgUnit', 'period', 'value']].to_dict(orient='records')}

    return alert_json