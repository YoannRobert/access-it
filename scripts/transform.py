"""Transform step: build the tables to load from the cached pages.

Reads the cached result and startlist pages and the Parquet files of the
extract step, and writes one Parquet file per table (clubs, races, riders,
rankings, affiliations, rider_categories) to the cache.

Usage, from the repository root: python scripts/transform.py
"""

import pandas as pd

from access_it.common.log import setup_logging
from access_it.etl.extract.cache import (
    RACES_PARQUET_FILE, RIDERS_PARQUET_FILE, RIDER_CATEGORIES_PARQUET_FILE,
    CLUBS_PARQUET_FILE, AFFILIATIONS_PARQUET_FILE, RANKINGS_PARQUET_FILE,
    DEPARTEMENTS_PARQUET_FILE, DEPCOM_PARQUET_FILE, REGCOM_PARQUET_FILE,
    NATIONAL_RESULTS_DIR
)
from access_it.etl.transform.clubs import add_legacy_clubs
from access_it.etl.transform.riders import (
    add_riders_to_database, assign_rider_ids, split_race_data_into_rider_data,
    identify_club_of_riders, create_affiliation_clubs_riders
)
from access_it.etl.transform.rider_x_race_data import (
    fill_missing_club_and_uci_ids, fill_missing_uci_ids_deep_mode,
    add_missing_individual_labels, add_missing_foreign_labels, correct_wrong_clubs,
    correct_wrong_uci_ids, create_ranking_table, correct_swapped_names
)
from access_it.etl.transform.clubs import add_clubs_found_in_race_html_files
from access_it.etl.transform.races import get_results_data, create_race_table
from access_it.etl.transform.startlists import identify_riders_categories_on_startlists
from access_it.etl.transform.categories import create_category_table
from access_it.etl.transform.individuals import assign_individual_committees


def transform():

    # Reading Parquet files obtained in the extract step of the ETL
    """Run the transform step."""
    departements = pd.read_parquet(DEPARTEMENTS_PARQUET_FILE)
    departemental_committees = pd.read_parquet(DEPCOM_PARQUET_FILE)
    regional_committees = pd.read_parquet(REGCOM_PARQUET_FILE)
    clubs = pd.read_parquet(CLUBS_PARQUET_FILE)

    # Enriching club database
    clubs = add_legacy_clubs(
        df_clubs=clubs,
        departemental_committees=departemental_committees
    )
    clubs = add_clubs_found_in_race_html_files(
        clubs,
        departemental_committees=departemental_committees
    )

    # Getting race data
    races_data = get_results_data()  # includes rankings
    races = create_race_table(races_data, departements)  # fewer columns

    # Creating intermediate data: rider x race
    # ---- flattening rankings: one line per ranking element
    rider_x_race_data = split_race_data_into_rider_data(races_data)
    # ---- multiple corrections
    rider_x_race_data = correct_wrong_uci_ids(rider_x_race_data)
    rider_x_race_data = correct_swapped_names(rider_x_race_data)
    rider_x_race_data = add_missing_individual_labels(rider_x_race_data)
    rider_x_race_data = add_missing_foreign_labels(rider_x_race_data)
    rider_x_race_data = correct_wrong_clubs(rider_x_race_data)
    # ---- identifying the club of the riders
    rider_x_race_data = identify_club_of_riders(rider_x_race_data, clubs)
    # ---- filling missing data
    rider_x_race_data = pd.DataFrame(rider_x_race_data)
    rider_x_race_data = fill_missing_club_and_uci_ids(rider_x_race_data)
    rider_x_race_data = fill_missing_uci_ids_deep_mode(rider_x_race_data)

    # Creating rider database
    rider_db = add_riders_to_database(rider_x_race_data=rider_x_race_data)
    rider_x_race_data = assign_rider_ids(rider_x_race_data, rider_db)

    # Finding the committee of the individual licensees of unknown committee
    # (the result pages of the other regions are only read here)
    national_races_data = get_results_data(results_dir=NATIONAL_RESULTS_DIR)
    rider_x_race_data, clubs = assign_individual_committees(
        rider_x_race_data=rider_x_race_data,
        races=races,
        national_races_data=national_races_data,
        clubs=clubs,
        departements=departements,
        departemental_committees=departemental_committees
    )

    # Creating ranking database
    rankings = create_ranking_table(rider_x_race_data)

    # Creating the club-rider affiliation database
    aff_club_rider = create_affiliation_clubs_riders(rider_x_race_data, races)

    # Creating the category database
    categories_from_startlists = identify_riders_categories_on_startlists(
        clubs=clubs,
        riders=rider_db,
        affiliations=aff_club_rider,
        departemental_committees=departemental_committees,
        regional_committees=regional_committees
    )
    rider_categories = create_category_table(
        races=races,
        rankings=rankings,
        categories_from_startlists=categories_from_startlists
    )

    # Saving all data to Parquet files
    pd.DataFrame(clubs).to_parquet(CLUBS_PARQUET_FILE, index=False)
    pd.DataFrame(races).to_parquet(RACES_PARQUET_FILE, index=False)
    pd.DataFrame(rider_db).to_parquet(RIDERS_PARQUET_FILE, index=False)
    pd.DataFrame(rankings).to_parquet(RANKINGS_PARQUET_FILE, index=False)
    pd.DataFrame(aff_club_rider).to_parquet(AFFILIATIONS_PARQUET_FILE, index=False)
    pd.DataFrame(rider_categories).to_parquet(RIDER_CATEGORIES_PARQUET_FILE, index=False)


if __name__ == "__main__":
    setup_logging()
    transform()
