"""Unit tests of the category changes of the riders."""

import pandas as pd
import pytest

from access_it.analytics.category_changes import CATEGORY_CHANGE_COLUMNS, compute_category_changes
from access_it.analytics.labels import DEMOTION, FIRST_APPEARANCE, PROMOTION, UNKNOWN_CLUB
from access_it.common.regions import BRETAGNE, PAYS_DE_LA_LOIRE
from access_it.common.seasons import FIRST_SEASON

GAP_SEASON = FIRST_SEASON + 1
SEASON = FIRST_SEASON + 2
NOT_COVERED_REGION = "NORMANDIE"

REGIONAL_COMMITTEES = pd.DataFrame({
    "regional_committee_id": ["52", "53", "54"],
    "name": [PAYS_DE_LA_LOIRE, BRETAGNE, NOT_COVERED_REGION],
})
DEPARTEMENTAL_COMMITTEES = pd.DataFrame({
    "departemental_committee_id": ["5244", "5356", "5414"],
    "regional_committee_id": ["52", "53", "54"],
    "departement_code": ["44", "56", "14"],
})
# 5244800 is the pseudo-club of the individual licensees of the committee 5244
CLUBS = pd.DataFrame({
    "club_id": ["5244001", "5356001", "5244800"],
    "name": ["Club Nantes", "Club Vannes", "Individuel 44"],
    "departemental_committee_id": ["5244", "5356", "5244"],
})
# g is absent from the rider table
RIDERS = pd.DataFrame({
    "rider_id": list("abcdefh"),
    "last_name": [f"NAME_{r}" for r in "abcdefh"],
    "first_name": [f"First_{r}" for r in "abcdefh"],
})
# a moves up during FIRST_SEASON then between two seasons; b moves down
# during the season; c appears in SEASON; d comes back in his category after
# GAP_SEASON without race, e in another one; f moves up then down during the
# season; g appears in SEASON; the whole history of h is unknown
RIDER_CATEGORIES = pd.DataFrame(
    [
        ("a", f"{FIRST_SEASON}-01-01", 4), ("a", f"{FIRST_SEASON}-05-01", 3),
        ("a", f"{SEASON}-01-01", 2),
        ("b", f"{FIRST_SEASON}-01-01", 2), ("b", f"{SEASON}-06-01", 3),
        ("c", f"{FIRST_SEASON}-01-01", None), ("c", f"{SEASON}-01-01", 4),
        ("d", f"{FIRST_SEASON}-01-01", 3), ("d", f"{GAP_SEASON}-01-01", None),
        ("d", f"{SEASON}-01-01", 3),
        ("e", f"{FIRST_SEASON}-01-01", 4), ("e", f"{GAP_SEASON}-01-01", None),
        ("e", f"{SEASON}-01-01", 3),
        ("f", f"{FIRST_SEASON}-01-01", 2), ("f", f"{SEASON}-03-01", 1),
        ("f", f"{SEASON}-09-01", 2),
        ("g", f"{FIRST_SEASON}-01-01", None), ("g", f"{SEASON}-01-01", 4),
        ("h", f"{FIRST_SEASON}-01-01", None),
    ],
    columns=["rider_id", "start_date", "rider_category"]
).astype({"rider_category": "Int8"})
# The club of c is unknown; e is an individual licensee; f moves from
# Bretagne to Pays de la Loire on August 1st of SEASON
AFFILIATIONS = pd.DataFrame(
    [
        ("a", f"{FIRST_SEASON}-01-01", "5244001"),
        ("b", f"{FIRST_SEASON}-01-01", "5356001"),
        ("d", f"{FIRST_SEASON}-01-01", "5244001"),
        ("e", f"{FIRST_SEASON}-01-01", "5244800"),
        ("f", f"{FIRST_SEASON}-01-01", "5356001"), ("f", f"{SEASON}-08-01", "5244001"),
        ("g", f"{FIRST_SEASON}-01-01", "5244001"),
    ],
    columns=["rider_id", "start_date", "club_id"]
)


def category_changes(season=SEASON, region=None, category=None):
    return compute_category_changes(
        RIDER_CATEGORIES, RIDERS, CLUBS, AFFILIATIONS, DEPARTEMENTAL_COMMITTEES,
        REGIONAL_COMMITTEES, season, region, category
    )


def test_changes_of_the_season_sorted_with_the_club_on_the_date_of_the_change():
    changes = category_changes()
    assert changes.columns.tolist() == CATEGORY_CHANGE_COLUMNS
    assert (changes["season"] == SEASON).all()
    assert changes["change_date"].tolist() == [
        pd.Timestamp(f"{SEASON}-01-01"), pd.Timestamp(f"{SEASON}-01-01"),
        pd.Timestamp(f"{SEASON}-01-01"), pd.Timestamp(f"{SEASON}-03-01"),
        pd.Timestamp(f"{SEASON}-06-01"), pd.Timestamp(f"{SEASON}-09-01"),
    ]
    assert changes[["last_name", "change_type", "to_category", "club"]].values.tolist() == [
        ["NAME_a", PROMOTION, "A2", "Club Nantes"],
        ["NAME_e", PROMOTION, "A3", "Individuel 44"],
        ["NAME_c", FIRST_APPEARANCE, "A4", UNKNOWN_CLUB],
        ["NAME_f", PROMOTION, "A1", "Club Vannes"],
        ["NAME_b", DEMOTION, "A3", "Club Vannes"],
        ["NAME_f", DEMOTION, "A2", "Club Nantes"],
    ]


def test_departure_category_is_the_last_known_one_and_missing_for_a_first_appearance():
    from_categories = category_changes().set_index("last_name")["from_category"]
    assert from_categories["NAME_a"] == "A3"
    assert from_categories["NAME_e"] == "A4"
    assert pd.isna(from_categories["NAME_c"])


def test_first_appearances_of_the_first_season_left_out():
    changes = category_changes(season=FIRST_SEASON)
    columns = ["last_name", "change_type", "from_category", "to_category"]
    assert changes[columns].values.tolist() == [["NAME_a", PROMOTION, "A4", "A3"]]


def test_season_without_change_gives_an_empty_table():
    changes = category_changes(season=GAP_SEASON)
    assert changes.empty
    assert changes.columns.tolist() == CATEGORY_CHANGE_COLUMNS


def test_changes_filtered_on_the_club_of_the_region_on_the_date_of_the_change():
    pays_de_la_loire = category_changes(region=PAYS_DE_LA_LOIRE)
    assert pays_de_la_loire[["last_name", "change_type"]].values.tolist() == [
        ["NAME_a", PROMOTION], ["NAME_e", PROMOTION], ["NAME_f", DEMOTION]
    ]
    bretagne = category_changes(region=BRETAGNE)
    assert bretagne[["last_name", "change_type"]].values.tolist() == [
        ["NAME_f", PROMOTION], ["NAME_b", DEMOTION]
    ]


def test_changes_filtered_on_the_category_of_arrival():
    changes = category_changes(category="A2")
    assert changes[["last_name", "change_type"]].values.tolist() == [
        ["NAME_a", PROMOTION], ["NAME_f", DEMOTION]
    ]


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"season": FIRST_SEASON - 1}, "before the first season"),
        ({"region": NOT_COVERED_REGION}, "Region not covered"),
        ({"category": "A5"}, "Unknown category"),
    ]
)
def test_invalid_arguments_raise(kwargs, message):
    with pytest.raises(ValueError, match=message):
        category_changes(**kwargs)
