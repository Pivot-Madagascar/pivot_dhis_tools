from pivot_dhis_tools import dx_code_to_uid

import os
from dotenv import load_dotenv


dx_code_to_uid(dhis_url = os.getenv("DHIS_URL"),
                              codes = ["pridec_climate_temperatureMean"],
                      user = "michelle",
                      pwd = os.getenv("DHIS_PASSWORD"))

dx_code_to_uid(dhis_url = os.getenv("DHIS_URL"),
                              codes = ["pridec_climate_fakeVariable"],
                      user = "michelle",
                      pwd = os.getenv("DHIS_PASSWORD"))

out = dx_code_to_uid(dhis_url = os.getenv("DHIS_URL"),
                              codes = ["pridec_climate_temperatureMean"],
                      user = "michelle",
                      pwd = os.getenv("DHIS_PASSWORD"))

out.keys()
out.values()

list(out.keys())[0]
list(out.values())[0]
next(iter(out))
next(iter(out.values()))
list(out.items())[0][0]
