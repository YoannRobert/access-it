import pandas as pd
from access_it.etl.extract.cache import REGCOM_PARQUET_FILE, DEPCOM_PARQUET_FILE, CLUBS_PARQUET_FILE
from access_it.etl.extract.client import make_client
from access_it.etl.extract.listing import get_organisation_list
from access_it.etl.extract.races import extract_unlisted_organizations
from access_it.etl.extract.clubs import get_committees, get_clubs

with make_client() as client:
    for dept in [
        44, 49, 53, 85, 72, # Pays de La Loire
        22, 29, 35, 56,  # Bretagne
    ]:
        get_organisation_list(client=client, dept=dept)
    extract_unlisted_organizations(client=client)

    reg_committees, dep_committees = get_committees(client)
    clubs = get_clubs(client, departemental_committees=dep_committees)
    reg_committees = [{"id": cr_id} | cr_data for cr_id, cr_data in reg_committees.items()]
    dep_committees = [{"id": cd_id} | cd_data for cd_id, cd_data in dep_committees.items()]
    clubs = [{"id": cl_id} | cl_data for cl_id, cl_data in clubs.items()]
    pd.DataFrame(reg_committees).to_parquet(REGCOM_PARQUET_FILE)
    pd.DataFrame(dep_committees).to_parquet(DEPCOM_PARQUET_FILE)
    pd.DataFrame(clubs).to_parquet(CLUBS_PARQUET_FILE)
