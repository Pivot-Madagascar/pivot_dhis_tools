import os
from dotenv import load_dotenv

from pivot_dhis_tools import post_dataElements

load_dotenv()

example_payload = {
    "dataValues": [
        {
            "orgUnit": "D9UWDj19ljP",
            "period": "202105",
            "value": 61,
            "dataElement": "pridec_forecast_CSBMalariaLowCI",
            "categoryOptionCombo": "pridec_COC_u5"
        },
        {
            "orgUnit": "DDR2w1c1GyE",
            "period": "202105",
            "value": 31,
            "dataElement": "pridec_forecast_CSBMalariaLowCI",
            "categoryOptionCombo": "pridec_COC_u5"
        },
        {
            "orgUnit": "EE6WwIMgQ0F",
            "period": "202105",
            "value": 50,
            "dataElement": "pridec_forecast_CSBMalariaLowCI",
            "categoryOptionCombo": "pridec_COC_u5"
        },
        {
            "orgUnit": "FGM6Ric1YnC",
            "period": "202105",
            "value": 49,
            "dataElement": "pridec_forecast_CSBMalariaLowCI",
            "categoryOptionCombo": "pridec_COC_u5"
        }
    ]
}

resp = post_dataElements(dhis_url = os.getenv("DHIS_URL"), payload = example_payload,
                   token=os.getenv("DHIS_TOKEN"), 
                      dryRun=True)

print(resp.text)