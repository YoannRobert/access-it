"""Unit tests of the list of the riders, its filters and the choices of each filter."""

import pandas as pd
import pytest

from access_it.analytics.labels import UNKNOWN_CATEGORY, UNKNOWN_CLUB
from access_it.analytics.rider_list import (
    RIDER_LIST_COLUMNS, build_rider_list, filter_riders, get_filter_choices
)
from access_it.common.regions import BRETAGNE, PAYS_DE_LA_LOIRE
from access_it.common.seasons import FIRST_SEASON
from access_it.etl.extract.constants import FOREIGN_CLUB_ID, INDIVIDUAL_CLUB_ID

YEAR = FIRST_SEASON
NOT_COVERED_REGION = "NORMANDIE"
REFERENCE_DATE = f"{YEAR}-07-01"

REGIONAL_COMMITTEES = pd.DataFrame({
    "regional_committee_id": ["52", "53", "28", INDIVIDUAL_CLUB_ID[:2], FOREIGN_CLUB_ID[:2]],
    "name": [PAYS_DE_LA_LOIRE, BRETAGNE, NOT_COVERED_REGION, "Individuel", "Etranger"],
})
DEPARTEMENTAL_COMMITTEES = pd.DataFrame({
    "departemental_committee_id": ["5244", "5285", "5356", "2814", "9899", "9999"],
    "regional_committee_id": ["52", "52", "53", "28", "98", "99"],
    "departement_code": ["44", "85", "56", "14", "99", "99"],
})
DEPARTEMENTS = pd.DataFrame({
    "departement_code": ["44", "85", "56", "14", "99"],
    "departement_name": ["NAME_44", "NAME_85", "NAME_56", "NAME_14", "Autre"],
})
CLUBS = pd.DataFrame({
    "club_id": [
        "5244001", "5244002", "5285001", "5244800", "5356001", "2814001",
        INDIVIDUAL_CLUB_ID, FOREIGN_CLUB_ID,
    ],
    "name": [
        "CLUB_44A", "CLUB_44B", "CLUB_85", "Individuel 44", "CLUB_56", "CLUB_14",
        "Individuel", "Etranger",
    ],
    "departemental_committee_id": ["5244", "5244", "5285", "5244", "5356", "2814", "9899", "9999"],
})
# l and m share the last name of a; c has an accent, b is in lower case
RIDERS = pd.DataFrame({
    "rider_id": list("abcdefghijklm"),
    "last_name": [
        "NAME_A", "name_b", "NÂME_C", "NAME_D", "NAME_E", "NAME_F", "NAME_G", "NAME_H",
        "NAME_I", "NAME_J", "NAME_K", "NAME_A", "NAME_A",
    ],
    "first_name": [
        "FIRST_A", "FIRST_B", "FIRST_C", "FIRST_D", "FIRST_E", "FIRST_F", "FIRST_G", "FIRST_H",
        "FIRST_I", "FIRST_J", "FIRST_K", "Ffirst", "Éfirst",
    ],
})
# r2 is run on the reference date, r0 before the first season
RACES = pd.DataFrame({
    "race_id": ["r0", "r1", "r2"],
    "season": [YEAR - 1, YEAR, YEAR],
    "race_date": [f"{YEAR - 1}-06-01", f"{YEAR}-06-01", REFERENCE_DATE],
})
# i only runs on the reference date, j never runs, k only runs before the first season
RANKINGS = pd.DataFrame({
    "race_id": ["r1"] * 10 + ["r2", "r2", "r0"],
    "rider_id": [*"abcdefghlm", "a", "i", "k"],
    "finish_rank": [*range(1, 11), 1, 2, 1],
})
# The periods of a starting on the reference date are ignored; b has no
# category, g an unknown one
RIDER_CATEGORIES = pd.DataFrame({
    "rider_id": [*"aacdefghiklm"],
    "start_date": [f"{YEAR}-01-01", REFERENCE_DATE, *[f"{YEAR}-01-01"] * 10],
    "rider_category": [2, 1, 3, 4, 4, 4, None, 4, 4, 4, 4, 4],
})
# g has no club
AFFILIATIONS = pd.DataFrame({
    "rider_id": [*"aabcdefhiklm"],
    "start_date": [f"{YEAR}-01-01", REFERENCE_DATE, *[f"{YEAR}-01-01"] * 10],
    "club_id": [
        "5244001", "5285001", "5285001", "5356001", "2814001", INDIVIDUAL_CLUB_ID,
        FOREIGN_CLUB_ID, "5244800", "5244001", "5244001", "5244002", "5244002",
    ],
})


def rider_list(**kwargs) -> pd.DataFrame:
    """List of the riders of the test tables, with the default arguments."""
    arguments = {
        "races": RACES, "rankings": RANKINGS, "riders": RIDERS, "clubs": CLUBS,
        "affiliations": AFFILIATIONS, "rider_categories": RIDER_CATEGORIES,
        "departements": DEPARTEMENTS, "departemental_committees": DEPARTEMENTAL_COMMITTEES,
        "regional_committees": REGIONAL_COMMITTEES, "reference_date": REFERENCE_DATE,
    } | kwargs
    return build_rider_list(**arguments)


def row(rider_list_df: pd.DataFrame, rider_id: str) -> pd.Series:
    """Row of a rider in a rider list."""
    return rider_list_df.set_index("rider_id").loc[rider_id]


def test_riders_with_a_result_before_the_reference_date_sorted_by_normalized_names():
    riders = rider_list()
    assert riders.columns.tolist() == RIDER_LIST_COLUMNS
    assert riders["rider_id"].tolist() == [*"mlabcdefgh"]
    assert riders.index.tolist() == list(range(10))


def test_category_and_club_of_the_last_periods_started_before_the_reference_date():
    a = row(rider_list(), "a")
    assert (a["category"], a["club"], a["club_id"]) == ("A2", "CLUB_44A", "5244001")
    assert (a["departement_code"], a["departement_name"]) == ("44", "NAME_44")
    assert a["region"] == PAYS_DE_LA_LOIRE


def test_unknown_category_and_club():
    riders = rider_list()
    assert row(riders, "b")["category"] == UNKNOWN_CATEGORY
    g = row(riders, "g")
    assert (g["category"], g["club"]) == (UNKNOWN_CATEGORY, UNKNOWN_CLUB)
    assert g[["departement_code", "departement_name", "region", "club_id"]].isna().all()


def test_individual_licensee_of_a_committee_keeps_its_departement_and_region():
    h = row(rider_list(), "h")
    assert (h["club"], h["departement_code"], h["region"]) == (
        "Individuel 44", "44", PAYS_DE_LA_LOIRE
    )


@pytest.mark.parametrize("rider_id, club_id", [
    ("e", INDIVIDUAL_CLUB_ID), ("f", FOREIGN_CLUB_ID),
], ids=["individual", "foreign"])
def test_fictitious_committee_has_no_departement_nor_region(rider_id, club_id):
    rider = row(rider_list(), rider_id)
    assert rider["club_id"] == club_id
    assert rider[["departement_code", "departement_name", "region"]].isna().all()


def test_club_of_a_region_not_covered_keeps_its_departement_and_region():
    d = row(rider_list(), "d")
    assert (d["departement_code"], d["region"]) == ("14", NOT_COVERED_REGION)


def test_no_rider_kept_gives_an_empty_list():
    riders = rider_list(reference_date=f"{YEAR}-01-01")
    assert riders.empty
    assert riders.columns.tolist() == RIDER_LIST_COLUMNS


def with_missing(table: pd.DataFrame, column: str, rider_id: str) -> pd.DataFrame:
    """Copy of a table with a missing value in `column` on the first row of a rider."""
    table = table.copy()
    table.loc[table.index[table["rider_id"] == rider_id][0], column] = None
    return table


INVALID_TABLES = [
    ({"reference_date": None}, "Missing reference date"),
    ({"races": RACES.assign(race_date=[None, *RACES["race_date"][1:]])},
     "Missing race dates in the results"),
    ({"rider_categories": with_missing(RIDER_CATEGORIES, "start_date", "c")},
     "Missing start dates in the history"),
    ({"affiliations": with_missing(AFFILIATIONS, "start_date", "c")},
     "Missing start dates in the history"),
]
INVALID_TABLE_IDS = ["reference_date", "race_date", "category_start_date", "club_start_date"]


@pytest.mark.parametrize("kwargs, message", INVALID_TABLES, ids=INVALID_TABLE_IDS)
def test_invalid_tables_raise(kwargs, message):
    with pytest.raises(ValueError, match=message):
        rider_list(**kwargs)


def test_missing_start_date_of_a_rider_not_kept_is_ignored():
    riders = rider_list(
        rider_categories=with_missing(RIDER_CATEGORIES, "start_date", "i"),
        affiliations=with_missing(AFFILIATIONS, "start_date", "i"),
    )
    assert len(riders) == 10


@pytest.mark.parametrize("index", range(len(INVALID_TABLES)), ids=INVALID_TABLE_IDS)
def test_invalid_tables_raise_in_order(index):
    kwargs = {}
    for later_kwargs, _ in INVALID_TABLES[index:]:
        kwargs |= later_kwargs
    with pytest.raises(ValueError, match=INVALID_TABLES[index][1]):
        rider_list(**kwargs)


# Rider list built by hand for the filters: x is of an unknown club, y of a
# region not covered
PDL = PAYS_DE_LA_LOIRE
LIST = pd.DataFrame(
    [
        ("Le Name", "FIRST_1", "A1", "CLUB_44A", "44", "NAME_44", PDL, "5244001", "p"),
        ("LE-NAMÉ", "FIRST_2", "A2", "club_44b", "44", "NAME_44", PDL, "5244002", "q"),
        ("L'Autre", "FIRST_1", "A3", "CLUB_85", "85", "NAME_85", PDL, "5285001", "r"),
        ("NAME_S", "Éfirst", "A4", "CLUB_56", "56", "NAME_56", BRETAGNE, "5356001", "s"),
        ("NAME_X", "FIRST_1", UNKNOWN_CATEGORY, UNKNOWN_CLUB, None, None, None, None, "x"),
        ("le name", "Ffirst", "A4", "CLUB_14", "14", "NAME_14", NOT_COVERED_REGION, "2814001", "y"),
    ],
    columns=RIDER_LIST_COLUMNS,
)


def kept(**kwargs) -> list[str]:
    """rider_id of the riders of LIST kept by the filters."""
    return filter_riders(LIST, **kwargs)["rider_id"].tolist()


def test_no_filter_keeps_every_rider_in_order():
    filtered = filter_riders(LIST)
    assert filtered["rider_id"].tolist() == [*"pqrsxy"]
    assert filtered.columns.tolist() == RIDER_LIST_COLUMNS


@pytest.mark.parametrize("last_name, expected", [
    ("name", [*"pqsxy"]),
    ("  LE   NAME ", [*"pqy"]),
    ("le-name", [*"pqy"]),
    ("lé nâme", [*"pqy"]),
    ("l autre", ["r"]),
    ("l'autre", ["r"]),
    ("", [*"pqrsxy"]),
    (" - ", [*"pqrsxy"]),
    ("nobody", []),
], ids=[
    "part", "case_and_spaces", "hyphen", "accents", "apostrophe_in_name", "apostrophe_in_text",
    "empty", "empty_once_normalized", "none_found",
])
def test_last_name_filter_on_normalized_names(last_name, expected):
    assert kept(last_name=last_name) == expected


def test_first_name_filter_keeps_equal_values():
    assert kept(first_name="FIRST_1") == [*"prx"]


@pytest.mark.parametrize("regions, expected", [
    (None, [*"pqrsxy"]),
    ([], [*"pqrsxy"]),
    ([BRETAGNE], ["s"]),
    ([PAYS_DE_LA_LOIRE, BRETAGNE], [*"pqrs"]),
], ids=["none", "empty", "one", "two"])
def test_region_filter(regions, expected):
    assert kept(regions=regions) == expected


def test_departement_and_club_filters_keep_only_covered_regions():
    assert kept(departement_code="44") == [*"pq"]
    assert kept(departement_code="14") == []
    assert kept(club_id="5285001") == ["r"]
    assert kept(club_id="2814001") == []


def test_filters_combine():
    assert kept(last_name="name", first_name="FIRST_1", departement_code="44") == ["p"]


def test_inconsistent_filters_give_an_empty_list():
    filtered = filter_riders(LIST, regions=[BRETAGNE], departement_code="44")
    assert filtered.empty
    assert filtered.columns.tolist() == RIDER_LIST_COLUMNS


@pytest.mark.parametrize("function", [filter_riders, get_filter_choices],
                         ids=["filter", "choices"])
def test_region_not_covered_raises(function):
    with pytest.raises(ValueError, match="Region not covered"):
        function(LIST, regions=[PAYS_DE_LA_LOIRE, NOT_COVERED_REGION])


def test_choices_without_filter_are_limited_to_covered_regions_and_sorted():
    choices = get_filter_choices(LIST)
    assert choices.first_names == ("Éfirst", "Ffirst", "FIRST_1", "FIRST_2")
    assert choices.regions == (BRETAGNE, PAYS_DE_LA_LOIRE)
    assert choices.departements.columns.tolist() == ["departement_code", "departement_name"]
    assert choices.departements["departement_code"].tolist() == ["44", "56", "85"]
    assert choices.departements.index.tolist() == [0, 1, 2]
    assert choices.clubs.columns.tolist() == ["club_id", "club"]
    assert choices.clubs["club_id"].tolist() == ["5244001", "5244002", "5356001", "5285001"]


def test_choices_of_a_filter_ignore_its_own_value():
    choices = get_filter_choices(LIST, regions=[BRETAGNE])
    assert choices.regions == (BRETAGNE, PAYS_DE_LA_LOIRE)
    assert choices.first_names == ("Éfirst",)
    assert choices.departements["departement_code"].tolist() == ["56"]
    assert choices.clubs["club_id"].tolist() == ["5356001"]


def test_choices_follow_the_other_filters():
    choices = get_filter_choices(LIST, departement_code="44", club_id="5244002")
    assert choices.first_names == ("FIRST_2",)
    assert choices.regions == (PAYS_DE_LA_LOIRE,)
    assert choices.departements["departement_code"].tolist() == ["44"]
    assert choices.clubs["club_id"].tolist() == ["5244001", "5244002"]


def test_choices_of_the_first_names_keep_unknown_clubs_and_regions_not_covered():
    choices = get_filter_choices(LIST, last_name="name_x")
    assert choices.first_names == ("FIRST_1",)
    assert choices.regions == ()
    assert choices.departements.empty
    assert choices.clubs.empty
