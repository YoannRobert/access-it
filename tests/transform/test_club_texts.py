"""Tests of the reading of club texts and of the identification of clubs."""

import pandas as pd
import pytest

from access_it.etl.extract.clubs import individual_club_id_mask, is_individual_club_id
from access_it.etl.extract.constants import INDIVIDUAL_CLUB_ID
from access_it.etl.transform.clubs import ClubLookup, add_club, identify_club, parse_club_text


@pytest.mark.parametrize(
    "text, expected",
    [
        ("5244001 - VC NANTAIS", ("5244001", "VC NANTAIS")),
        ("5244001 VC NANTAIS", ("5244001", "VC NANTAIS")),
        ("4976038 AC SOTTEVILLE", ("4976038", "AC SOTTEVILLE")),
        ("VC NANTAIS", (None, "VC NANTAIS")),
        ("  VC   NANTAIS ", (None, "VC NANTAIS")),
        ("5244001", ("5244001", "")),
        ("524400 VC", (None, "524400 VC")),  # 6 digits: not a club ID
        (None, (None, None)),
    ],
)
def test_parse_club_text(text, expected):
    assert parse_club_text(text) == expected


# ---------------------------------------------------------------- identify_club

CLUBS = pd.DataFrame({
    "club_id": ["4436087", "5079082", "5244001"],
    "name": ["VC CHATILLONNAIS", "VELO CLUB CHATILLONNAIS", "VC NANTAIS"],
    "departemental_committee_id": ["4436", "5079", "5244"],
    "min_year": 2025,
    "max_year": 2025,
    "alternative_names": ["", "VC CHATILLONNAIS", ""],
})


def test_name_shared_by_several_clubs_gives_an_unknown_club():
    assert identify_club(None, "VC CHATILLONNAIS", ClubLookup(CLUBS)) == (False, None, None)
    assert identify_club(None, "vc  chatillonnais", ClubLookup(CLUBS)) == (False, None, None)


def test_club_id_resolves_a_shared_name():
    lookup = ClubLookup(CLUBS)
    assert identify_club("5079082", "VC CHATILLONNAIS", lookup)[1] == "5079082"
    assert identify_club("4436087", "VC CHATILLONNAIS", lookup)[1] == "4436087"


def test_unique_name_is_identified():
    assert identify_club(None, "VC NANTAIS", ClubLookup(CLUBS)) == (True, "5244001", "VC NANTAIS")


def test_empty_name_gives_an_unknown_club():
    assert identify_club(None, "", ClubLookup(CLUBS)) == (False, None, None)
    assert identify_club(None, "   ", ClubLookup(CLUBS)) == (False, None, None)


def test_name_becomes_ambiguous_when_another_club_gets_it_as_alternative_name():
    clubs = CLUBS.assign(alternative_names=["", "", ""])
    lookup = ClubLookup(clubs)
    assert identify_club(None, "VC NANTAIS", lookup)[1] == "5244001"
    clubs.loc[0, "alternative_names"] = "VC NANTAIS"
    lookup.sync(clubs, "4436087")
    assert identify_club(None, "VC NANTAIS", lookup) == (False, None, None)


# ---------------------------------------------------------------- individual licensees of a committee

COMMITTEES = pd.DataFrame({
    "departemental_committee_id": ["5244", "6097"],
    "name": ["LOIRE-ATLANTIQUE", "GUADELOUPE"],
    "regional_committee_id": ["52", "60"],
    "departement_code": ["44", "971"],
})


def test_individual_license_id_gives_the_pseudo_club_of_its_committee():
    assert identify_club("5244800", "", ClubLookup(CLUBS)) == (True, "5244800", "")
    assert identify_club(None, "Individuel", ClubLookup(CLUBS)) == (
        False, INDIVIDUAL_CLUB_ID, "Individuel"
    )


def test_pseudo_club_of_a_committee_is_named_after_its_departement():
    clubs = add_club(CLUBS, "5244800", "COMITE DEPARTEMENTAL", 2025, COMMITTEES)
    clubs = add_club(clubs, "5244800", "", 2026, COMMITTEES)
    clubs = add_club(clubs, "6098800", "", 2026, COMMITTEES)
    row = clubs[clubs["club_id"] == "5244800"].iloc[0]
    assert (row["name"], row["departemental_committee_id"]) == ("Individuel 44", "5244")
    assert (row["min_year"], row["max_year"], row["alternative_names"]) == (2025, 2026, "")
    assert clubs.loc[clubs["club_id"] == "6098800", "name"].iloc[0] == "Individuel 971"
    assert identify_club("5244800", "", ClubLookup(clubs)) == (True, "5244800", "Individuel 44")


@pytest.mark.parametrize(
    "club_id, expected",
    [
        ("5244800", True), (INDIVIDUAL_CLUB_ID, True), ("5244001", False),
        (None, False), (float("nan"), False),
    ],
)
def test_is_individual_club_id(club_id, expected):
    assert is_individual_club_id(club_id) is expected


@pytest.mark.parametrize("dtype", ["object", "str", "string[pyarrow]", "large_string[pyarrow]"])
def test_individual_club_id_mask_is_a_plain_boolean_series(dtype):
    club_ids = pd.Series(["5244800", "5244001", None], index=[3, 5, 7], dtype=dtype)
    mask = individual_club_id_mask(club_ids)
    assert mask.dtype == bool
    assert mask.tolist() == [True, False, False]
    assert (~mask & (club_ids != "x").fillna(True).astype(bool)).tolist() == [False, True, True]
