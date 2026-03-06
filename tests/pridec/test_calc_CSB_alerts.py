from pivot_dhis_tools import pridec_calc_CSB_alerts
from datetime import date

token = "d2pat_mEjuHqGRi5R3YSWz6HxL1ZFjNQkbWbnW2999294529"
dhis_url = 'http://localhost:8080/'

output = pridec_calc_CSB_alerts(dhis_url =dhis_url,
                                token = token,
                                focal_date = date(2024,12,1))