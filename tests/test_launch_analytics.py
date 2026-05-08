import os
from dotenv import load_dotenv

from pivot_dhis_tools import launch_analytics

load_dotenv()

launch_analytics(dhis_url=os.getenv("DHIS_URL"), token=os.getenv("DHIS_TOKEN"))