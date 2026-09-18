import pandas as pd
from datetime import datetime
from access_it.etl.extract.cache import (
    REGCOM_PARQUET_FILE, DEPCOM_PARQUET_FILE, CLUBS_PARQUET_FILE
)
from access_it.etl.extract.client import make_client
from access_it.etl.extract.races import (
    extract_organization_pages_from_search_url,
    extract_former_organization_pages_from_existing_ones,
    extract_former_organization_pages_using_bruteforce
)
from access_it.etl.extract.clubs import get_committees, get_clubs

with make_client() as client:
    this_year = datetime.now().year
    cst_club_dat = {
        "min_year": this_year,
        "max_year": this_year,
        "alternative_names": ""
    }
    for dept in [
        44, 49, 53, 85, 72,  # Pays de La Loire
        22, 29, 35, 56,  # Bretagne
    ]:
        extract_organization_pages_from_search_url(client=client, dept=dept)
    extract_former_organization_pages_from_existing_ones(client=client)
    extract_former_organization_pages_using_bruteforce(client=client)

    reg_committees, dep_committees = get_committees(client)
    clubs = get_clubs(client, departemental_committees=dep_committees)
    reg_committees = [{"id": cr_id} | cr_data for cr_id, cr_data in reg_committees.items()]
    dep_committees = [{"id": cd_id} | cd_data for cd_id, cd_data in dep_committees.items()]
    clubs = [{"club_id": cl_id} | cl_data | cst_club_dat for cl_id, cl_data in clubs.items()]
    pd.DataFrame(reg_committees).to_parquet(REGCOM_PARQUET_FILE, index=False)
    pd.DataFrame(dep_committees).to_parquet(DEPCOM_PARQUET_FILE, index=False)
    pd.DataFrame(clubs).to_parquet(CLUBS_PARQUET_FILE, index=False)
