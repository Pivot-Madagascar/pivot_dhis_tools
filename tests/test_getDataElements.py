from pivot_dhis_tools import get_dataElements

import os
from dotenv import load_dotenv


get_dataElements(dhis_url = os.getenv("TEST_URL"),
                              dx_query = "dx:dA9FwHe5k4U",
                              ou_query = "ou:VtP4BdCeXIo",
                              pe_query = "pe:202201",
                     token = os.getenv("TEST_TOKEN"))

get_dataElements(dhis_url = os.getenv("DHIS_URL"),
                              dx_query = "dx:pridec_historic_COMMalaria",
                              ou_query = "ou:VtP4BdCeXIo",
                              pe_query = "pe:202201",
                      user = "michelle",
                      pwd = os.getenv("DHIS_PASSWORD"),
                      dx_id_scheme = "CODE")