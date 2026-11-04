"""Unit tests of the list of the races."""

import pandas as pd
import pytest

from access_it.analytics.race_list import RACE_LIST_COLUMNS, list_races
from access_it.common.regions import BRETAGNE, PAYS_DE_LA_LOIRE
from access_it.common.seasons import FIRST_SEASON

YEAR = FIRST_SEASON
NOT_COVERED_REGION = "NORMANDIE"
START_DATE = f"{YEAR}-03-01"
END_DATE = f"{YEAR + 1}-01-01"

REGIONAL_COMMITTEES = pd.DataFrame({
    "regional_committee_id": ["52", "53"],
    "name": [PAYS_DE_LA_LOIRE, BRETAGNE],
})
DEPARTEMENTAL_COMMITTEES = pd.DataFrame({
    "departemental_committee_id": ["5244", "5285", "5385"],
    "regional_committee_id": ["52", "52", "53"],
    "departement_code": ["44", "85", "56"],
})
# The name of departement 85 is unknown
DEPARTEMENTS = pd.DataFrame({
    "departement_code": ["44", "56"],
    "departement_name": ["Loire-Atlantique", "Morbihan"],
})
# r4 is held in Bretagne, r5 has no ranking (cancelled race), r6 and r7 are
# outside the period; r1, r2, r3, r8 and r9 are kept by default
RACES = pd.DataFrame({
    "race_id": [f"r{i}" for i in range(1, 10)],
    "title": [f"Race {i}" for i in range(1, 10)],
    "categories": ["A1,A2", "A3", "A4", "A2", "A2", "A2", "A2", "A1", "A3"],
    "season": [YEAR, YEAR, YEAR + 1, YEAR, YEAR, YEAR, YEAR + 1, YEAR, YEAR],
    "race_date": [
        f"{YEAR}-03-01", f"{YEAR}-12-31", f"{YEAR + 1}-01-01", f"{YEAR}-06-01",
        f"{YEAR}-06-01", f"{YEAR}-02-28", f"{YEAR + 1}-01-02", f"{YEAR}-06-01", f"{YEAR}-06-01",
    ],
    "departement_code": ["44", "85", "44", "56", "44", "44", "44", "85", "44"],
})
RANKINGS = pd.DataFrame({
    "race_id": ["r1", "r1", "r2", "r3", "r4", "r6", "r7", "r8", "r9"],
    "rider_id": ["a", "b", "a", "c", "d", "a", "b", "c", "d"],
    "finish_rank": [1, 2, 1, 1, 1, 1, 1, 1, 1],
})


def race_list(**kwargs) -> pd.DataFrame:
    """List of the races of the test tables, with the default arguments."""
    arguments = {
        "races": RACES, "rankings": RANKINGS, "departements": DEPARTEMENTS,
        "departemental_committees": DEPARTEMENTAL_COMMITTEES,
        "regional_committees": REGIONAL_COMMITTEES, "start_date": START_DATE,
        "end_date": END_DATE, "region": PAYS_DE_LA_LOIRE,
    } | kwargs
    return list_races(**arguments)


def test_races_of_the_period_from_the_most_recent_with_the_bounds_included():
    races = race_list()
    assert races.columns.tolist() == RACE_LIST_COLUMNS
    assert races["race_id"].tolist() == ["r3", "r2", "r9", "r8", "r1"]
    assert races["race_date"].dtype == "datetime64[ns]"
    assert races.index.tolist() == list(range(5))


def test_unknown_departement_name_is_missing():
    races = race_list().set_index("race_id")
    assert races.loc["r1", "departement_name"] == "Loire-Atlantique"
    assert pd.isna(races.loc["r2", "departement_name"])


def test_races_of_the_requested_departements():
    assert race_list(departement_codes=["85", "85"])["race_id"].tolist() == ["r2", "r8"]


def test_no_requested_departement_means_all_those_of_the_region():
    pd.testing.assert_frame_equal(race_list(), race_list(departement_codes=["85", "44"]))


def test_races_having_at_least_one_requested_category():
    assert race_list(categories=["A4", "A3"])["race_id"].tolist() == ["r3", "r2", "r9"]


def test_no_race_kept_gives_an_empty_list():
    races = race_list(start_date=f"{YEAR}-07-01", end_date=f"{YEAR}-07-31")
    assert races.empty
    assert races.columns.tolist() == RACE_LIST_COLUMNS


INVALID_ARGUMENTS = [
    ({"region": NOT_COVERED_REGION}, "Region not covered"),
    ({"start_date": None}, "Missing start date"),
    ({"end_date": None}, "Missing end date"),
    ({"end_date": f"{YEAR}-02-28"}, "End date .* is before the start date"),
    ({"start_date": f"{FIRST_SEASON - 1}-12-31"}, "before the first season"),
    (
        {"regional_committees": REGIONAL_COMMITTEES[
            REGIONAL_COMMITTEES["name"] != PAYS_DE_LA_LOIRE
        ]},
        "Unknown region"
    ),
    ({"departement_codes": []}, "No departement requested"),
    ({"departement_codes": ["44", "56"]}, r"Departements not in the region: \['56'\]"),
    ({"categories": ["A1", "A3"]}, "Categories not contiguous"),
]
INVALID_ARGUMENT_IDS = [
    "not_covered_region", "start_date", "end_date", "end_before_start", "season",
    "unknown_region", "no_departement", "departement_outside", "categories",
]


@pytest.mark.parametrize("kwargs, message", INVALID_ARGUMENTS, ids=INVALID_ARGUMENT_IDS)
def test_invalid_arguments_raise(kwargs, message):
    with pytest.raises(ValueError, match=message):
        race_list(**kwargs)


@pytest.mark.parametrize("column, value, message", [
    ("race_date", None, "Missing race dates in the results"),
    ("categories", "A1,A3", "Races with non contiguous categories"),
], ids=["race_date", "categories"])
def test_invalid_races_raise(column, value, message):
    races = RACES.copy()
    races.loc[0, column] = value
    with pytest.raises(ValueError, match=message):
        race_list(races=races)


INVALID_RACES = RACES.assign(
    categories=["A1,A3", *RACES["categories"][1:]], race_date=[None, *RACES["race_date"][1:]]
)


@pytest.mark.parametrize("kwargs, message", INVALID_ARGUMENTS, ids=INVALID_ARGUMENT_IDS)
def test_invalid_argument_raises_before_invalid_data(kwargs, message):
    with pytest.raises(ValueError, match=message):
        race_list(races=INVALID_RACES, **kwargs)
