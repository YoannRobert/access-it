"""Unit tests of the recognition of the Access races of a startlist page."""

import pandas as pd
import pytest

from access_it.etl.transform.clubs import ClubLookup
from access_it.etl.transform.upcoming_entries import (
    AccessStartlist, find_access_startlists, find_club_column, find_departement_code,
    find_name_columns, is_access_startlist_heading
)

CLUBS = ClubLookup(pd.DataFrame({
    "club_id": ["5244001", "5244002", "4335001", "4344800"],
    "name": ["VC NANTAIS", "UC REZEENNE", "CC LIFFRE", "Individuel 44"],
    "departemental_committee_id": ["5244", "5244", "4335", "4344"],
    "min_year": 2025,
    "max_year": 2026,
    "alternative_names": "",
}))

DEPARTEMENTS = pd.DataFrame({
    "departement_code": ["35", "44", "49", "50", "53", "72"],
    "departement_name": [
        "Ille-et-Vilaine", "Loire-Atlantique", "Maine-et-Loire", "Manche", "Mayenne", "Sarthe",
    ],
})


@pytest.mark.parametrize("heading, expected", [
    ("ACCESS 1.2", True),
    ("Acces 3-4", True),
    ("A3-A4", True),
    ("Course A 2", True),
    ("OPEN ACCESS", False),
    ("ELITE ET ACCESS", False),
    ("Élite Access", False),
    ("ACCESS DAMES", False),
    ("U17", False),
])
def test_access_startlist_heading(heading, expected):
    assert is_access_startlist_heading(heading) is expected


@pytest.mark.parametrize("description, expected", [
    ("Courses organisées à Vallet en Loire-Atlantique (44) le 3 mai", "44"),
    ("Courses organisées à Laval (53) puis à Vallet (44)", None),
    ("Courses organisées à Château-Gontier en Mayenne le 3 mai", "53"),
    ("Courses organisées dans le Maine et Loire le 3 mai", "49"),
    ("Courses organisées à Granville (99) dans la Manche", "50"),
    ("Courses organisées à Vallet le 3 mai pour la manche du challenge", None),
    ("Courses en Mayenne puis dans la Sarthe", None),
])
def test_departement_code(description, expected):
    assert find_departement_code(description, DEPARTEMENTS) == expected


def table(**columns: list) -> pd.DataFrame:
    """Startlist table with the given columns."""
    return pd.DataFrame(columns)


def test_club_column_is_the_best_identified_one():
    t = table(
        col0=["DUPONT Jean", "MARTIN Paul", "DURAND Luc"],
        col1=["VC NANTAIS", "UC REZEENNE", "CLUB INCONNU"],
        col2=["Access 1", "Access 2", "Access 3"],
    )
    assert find_club_column(t, CLUBS) == "col1"


def test_individual_cells_are_left_out_of_the_club_rate():
    t = table(
        col0=["DUPONT Jean", "MARTIN Paul", "DURAND Luc"],
        col1=["Individuel", "Individuel", "VC NANTAIS"],
    )
    assert find_club_column(t, CLUBS) == "col1"


def test_club_column_below_the_threshold_is_not_found():
    t = table(
        col0=["DUPONT Jean", "MARTIN Paul", "DURAND Luc"],
        col1=["VC NANTAIS", "CLUB INCONNU", "AUTRE CLUB"],
    )
    assert find_club_column(t, CLUBS) is None


def test_leftmost_club_column_wins_a_tie():
    t = table(
        col0=["DUPONT Jean", "MARTIN Paul"],
        col1=["VC NANTAIS", "CC LIFFRE"],
        col2=["VC NANTAIS", "CC LIFFRE"],
    )
    assert find_club_column(t, CLUBS) == "col1"


@pytest.mark.parametrize("second_column, expected", [
    (["Jean", "Paul-Henri", "Anne Marie"], ["col0", "col1"]),
    (["H", "H", "F"], ["col0"]),
    (["FRA", "FRA", "BEL"], ["col0"]),
    (["France", "France", "France"], ["col0"]),
    (["Access", "Access", "Access"], ["col0"]),
    (["12", "13", "14"], ["col0"]),
])
def test_name_columns(second_column, expected):
    t = table(col0=["DUPONT", "MARTIN", "DURAND"], col1=second_column, col2=["VC NANTAIS"] * 3)
    assert find_name_columns(t, "col2") == expected


def test_club_as_second_column_gives_a_single_name_column():
    t = table(col0=["DUPONT Jean", "MARTIN Paul"], col1=["Vc Nantais", "Cc Liffre"])
    assert find_name_columns(t, "col1") == ["col0"]


def test_access_startlists_of_a_page():
    rows = [
        {"col0": "DUPONT", "col1": "Jean", "col2": "VC NANTAIS"},
        {"col0": "MARTIN", "col1": "Paul", "col2": "CC LIFFRE"},
    ]
    startlists = {
        "U17": rows,
        "ACCESS 1.2": rows,
        "OPEN": rows,
        "ACCESS 3.4": [{"col0": "DUPONT Jean", "col1": "CLUB INCONNU"}],
        "A4": [],
        "ACCESS 4": rows[:1],
    }
    result = find_access_startlists(startlists, CLUBS)
    assert [(a.rank, a.heading, a.name_columns, a.club_column) for a in result] == [
        (2, "ACCESS 1.2", ("col0", "col1"), "col2"),
        (6, "ACCESS 4", ("col0", "col1"), "col2"),
    ]
    assert isinstance(result[0], AccessStartlist)
    pd.testing.assert_frame_equal(result[0].table, pd.DataFrame(rows))
