import pandas as pd

from datetime import datetime
from access_it.etl.extract.cache import (
    REGCOM_PARQUET_FILE, DEPCOM_PARQUET_FILE, CLUBS_PARQUET_FILE,
    DEPARTEMENTS_PARQUET_FILE
)
from access_it.etl.extract.client import make_client
from access_it.etl.extract.departements import get_departement_mapping
from access_it.etl.extract.races import (
    extract_organization_pages_from_search_url,
    extract_former_organization_pages_from_existing_ones,
    extract_former_organization_pages_using_bruteforce
)
from access_it.etl.extract.clubs import get_committees, get_clubs


def extract():

    with make_client() as client:
        for dept in [
            44, 49, 53, 85, 72,  # Pays de La Loire
            22, 29, 35, 56,  # Bretagne
        ]:
            extract_organization_pages_from_search_url(client=client, dept=dept)
        extract_former_organization_pages_from_existing_ones(client=client)
        extract_former_organization_pages_using_bruteforce(client=client)

        reg_committees, dep_committees = get_committees(client)
        clubs = get_clubs(client, departemental_committees=dep_committees)
        this_year = datetime.now().year
        clubs["min_year"] = this_year
        clubs["max_year"] = this_year
        clubs["alternative_names"] = ""
        departements = get_departement_mapping(client)
        pd.DataFrame(reg_committees).to_parquet(REGCOM_PARQUET_FILE, index=False)
        pd.DataFrame(dep_committees).to_parquet(DEPCOM_PARQUET_FILE, index=False)
        pd.DataFrame(clubs).to_parquet(CLUBS_PARQUET_FILE, index=False)
        pd.DataFrame(departements).to_parquet(DEPARTEMENTS_PARQUET_FILE, index=False)


if __name__ == "__main__":
    extract()
