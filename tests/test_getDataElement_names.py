from pivot_dhis_tools import get_dataElement_names

output = get_dataElement_names(dhis_url = "https://play.im.dhis2.org/stable-2-43-0/",
                               pattern = "malaria",
                      user = "admin",
                      pwd = "district")