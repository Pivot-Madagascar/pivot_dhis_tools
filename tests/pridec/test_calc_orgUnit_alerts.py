from pivot_dhis_tools import pridec_calc_orgUnit_alerts
from datetime import date
import pytest
import json

#pridec-202603
token = "d2pat_q1fx2vrgjM29rdCREQXCi7ZNuctbOHMn0796483934"
dhis_url = 'http://localhost:8080/'
parent_ou = 'VtP4BdCeXIo'
ou_level = 5
disease_code = "COMRespinf"
alert_name = "COMRespinfVigilance"
with open("/home/mevans/Dropbox/PIVOT/pride-c/appDev/pridec-docker/output/forecast.json") as f:
    forecast_data = json.load(f)

with open("/home/mevans/Dropbox/PIVOT/pride-c/appDev/pridec-docker/input/disease_data.json") as f:
    historic_data = json.load(f)

output = pridec_calc_orgUnit_alerts(dhis_url =dhis_url,
                                token = token,
                                parent_ou = parent_ou,
                                ou_level = ou_level,
                                disease_code = disease_code,
                                focal_date = date(2024,12,1),
                                alert_name = "test")

pridec_calc_orgUnit_alerts(dhis_url =dhis_url,
                                token = token,
                                parent_ou = parent_ou,
                                ou_level = ou_level,
                                disease_code = disease_code,
                                forecast_data = forecast_data,
                                historic_data=historic_data)

pridec_calc_orgUnit_alerts(dhis_url =dhis_url,
                                token = token,
                                parent_ou = parent_ou,
                                ou_level = 6,
                                disease_code = disease_code,
                                focal_date = date(2024,12,1),
                                historic_data=historic_data)


