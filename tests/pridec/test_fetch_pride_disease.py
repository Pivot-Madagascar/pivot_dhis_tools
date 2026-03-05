import os
from dotenv import load_dotenv

from pivot_dhis_tools import pridec_fetch_disease

load_dotenv()

pridec_fetch_disease(dhis_url = os.getenv("DHIS_URL"), ou_level = 5, 
                     ou_parent =  os.getenv("PARENT_OU"),
                     disease_code = "pridec_historic_CSBMalaria",
                     token=os.getenv("DHIS_TOKEN"), past_years = 3)