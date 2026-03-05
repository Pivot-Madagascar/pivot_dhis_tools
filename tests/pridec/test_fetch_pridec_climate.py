import os
from dotenv import load_dotenv

from pivot_dhis_tools import pridec_fetch_climate

load_dotenv()

pridec_fetch_climate(dhis_url = os.getenv("DHIS_URL"), ou_level = 5, 
                     ou_parent =  os.getenv("PARENT_OU"),
                     token=os.getenv("DHIS_TOKEN"), past_years = 2)