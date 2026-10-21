"""Tests of the reading of club texts and of the identification of clubs."""

import pandas as pd
import pytest

from access_it.etl.transform.clubs import ClubLookup, identify_club, parse_club_text


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
