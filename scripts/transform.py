import pandas as pd

from access_it.etl.extract.cache import (
    RACES_PARQUET_FILE, RIDER_X_RACE_DATA_PARQUET_FILE, RIDERS_PARQUET_FILE,
    CLUBS_PARQUET_FILE, CLUB_X_RIDER_PARQUET_FILE, RANKINGS_PARQUET_FILE,
    DEPARTEMENTS_PARQUET_FILE
)
from access_it.etl.transform.clubs import add_legacy_clubs
from access_it.etl.transform.riders import (
    add_riders_to_database, split_race_data_into_rider_data,
    identify_club_of_riders, create_affiliation_clubs_riders
)
from access_it.etl.transform.rider_x_race_data import (
    fill_missing_club_and_uci_ids, fill_missing_uci_ids_deep_mode,
    add_missing_individual_labels, add_missing_foreign_labels,
    correct_wrong_uci_ids, create_ranking_table
)
from access_it.etl.transform.clubs import add_clubs_found_in_race_html_files
from access_it.etl.transform.races import get_race_data, create_race_table


# Reading Parquet files obtained in the extract step of the ETL
departements = pd.read_parquet(DEPARTEMENTS_PARQUET_FILE)
clubs = pd.read_parquet(CLUBS_PARQUET_FILE)

# Enriching club database
clubs = add_legacy_clubs(df_clubs=clubs)
clubs = add_clubs_found_in_race_html_files(clubs)

# Getting race data
races_data = get_race_data()  # includes rankings
races = create_race_table(races_data, departements)  # fewer columns

# Creating intermediate data: rider x race
# ---- flattening rankings: one line per ranking element
rider_x_race_data = split_race_data_into_rider_data(races_data)
# ---- multiple corrections
rider_x_race_data = correct_wrong_uci_ids(rider_x_race_data)
rider_x_race_data = add_missing_individual_labels(rider_x_race_data)
rider_x_race_data = add_missing_foreign_labels(rider_x_race_data)
# ---- identifying the club of the riders
rider_x_race_data = identify_club_of_riders(rider_x_race_data, clubs)
# ---- filling missing data
rider_x_race_data = pd.DataFrame(rider_x_race_data)
rider_x_race_data = fill_missing_club_and_uci_ids(rider_x_race_data)
rider_x_race_data = fill_missing_uci_ids_deep_mode(rider_x_race_data)

# Creating rider database
rider_db = add_riders_to_database(rider_x_race_data=rider_x_race_data)

# Creating ranking database
rankings = create_ranking_table(rider_x_race_data, rider_db)

# Creating the club-rider affiliation database
aff_club_rider = create_affiliation_clubs_riders(rider_x_race_data, races, rider_db)

# Saving all data to Parquet files
pd.DataFrame(clubs).to_parquet(CLUBS_PARQUET_FILE, index=False)
pd.DataFrame(races).to_parquet(RACES_PARQUET_FILE, index=False)
pd.DataFrame(rider_x_race_data).to_parquet(RIDER_X_RACE_DATA_PARQUET_FILE, index=False)
pd.DataFrame(rider_db).to_parquet(RIDERS_PARQUET_FILE, index=False)
pd.DataFrame(rankings).to_parquet(RANKINGS_PARQUET_FILE, index=False)
pd.DataFrame(aff_club_rider).to_parquet(CLUB_X_RIDER_PARQUET_FILE, index=False)
