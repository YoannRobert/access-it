"""Unit tests of the recognition of the Access races of a startlist page."""

import pandas as pd
import pytest

from access_it.etl.extract.upcoming_startlists import UpcomingStartlistPage
from access_it.etl.transform.clubs import ClubLookup
from access_it.etl.transform.upcoming_entries import (
    ENTRIES_COLUMNS, AccessStartlist, build_upcoming_entries, find_access_startlists,
    find_club_column, find_departement_code, find_name_columns, is_access_startlist_heading,
    is_cancelled_race_description, is_men_or_mixed_heading, is_women_race_title
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


@pytest.mark.parametrize("description, expected", [
    ("COURSE ANNULÉE. La Lescouëtaise, course cycliste organisée à Lescouët-Gouarec", True),
    ("Les courses annulees ne seront pas reportées", True),
    ("Courses annulée à cause des fortes chaleurs", True),
    ("Course annulées par arrêté préfectoral", True),
    ("Les épreuves prévues pour les écoles de vélo sont annulées", False),
    ("Engagés des courses cyclistes organisées à Vallet (44)", False),
    ("Annulation de l'épreuve à cause des fortes chaleurs", False),
    ("Course reportée au 20 juillet", False),
])
def test_cancelled_race_description(description, expected):
    assert is_cancelled_race_description(description) is expected


@pytest.mark.parametrize("title, expected", [
    ("Ste Sève 29 mars 2026 les engagées de courses cyclistes", True),
    ("Classic Féminine 21 juin 2026 ENGAGÉES", True),
    ("Course 3 mai 2026 l'engagée", True),
    ("Vallet 22 novembre 2026 engagés", False),
    ("Route féminine 31 mai 2026 les engagés et engagées", False),
    ("Ploumagoar 12 avril 2026 les engagé de courses cyclistes", False),
    ("Bretagne Ladies Tour 29-31 mai 2026 les partantes", False),
])
def test_women_race_title(title, expected):
    assert is_women_race_title(title) is expected


@pytest.mark.parametrize("heading, expected", [
    ("HOMMES ACCESS", True),
    ("ACCESS 1.2 HOMMES", True),
    ("Access masculins", True),
    ("ACCESS GARÇONS", True),
    ("Course mixte", True),
    ("ACCESS 3.4 ET FEMMES", True),
    ("ACCESS 3/4 SAUF FEMMES", True),
    ("ACCESS", False),
    ("FEMMES ACCESS", False),
    ("NOTRE-DAME ACCESS", False),
    ("ACCESS DEPART 15 H 30", False),
])
def test_men_or_mixed_heading(heading, expected):
    assert is_men_or_mixed_heading(heading) is expected


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


# ------------------------------------------------------------- build_upcoming_entries

LAST_NAMES = [
    "ALPHA", "BRAVO", "CHARLIE", "DELTA", "ECHO", "FOXTROT",
    "GOLF", "HOTEL", "INDIA", "JULIETT", "KILO", "LIMA",
]
REFERENCE_CLUBS = pd.DataFrame({
    "club_id": ["5244001", "5244800"],
    "name": ["VC NANTAIS", "Individuel 44"],
    "departemental_committee_id": ["5244", "5244"],
    "min_year": 2025,
    "max_year": 2026,
    "alternative_names": "",
})
RIDERS = pd.DataFrame({
    "rider_id": [f"r{i}" for i in range(len(LAST_NAMES))],
    "uci_id": [f"100000000{i:02d}" for i in range(len(LAST_NAMES))],
    "last_name": LAST_NAMES,
    "first_name": "Jean",
})
AFFILIATIONS = pd.DataFrame({
    "rider_id": RIDERS["rider_id"],
    "start_date": pd.to_datetime(["2025-01-01"] * len(LAST_NAMES)),
    "club_id": ["5244800"] + ["5244001"] * (len(LAST_NAMES) - 1),
})
DEPARTEMENTAL_COMMITTEES = pd.DataFrame({
    "departemental_committee_id": ["5244", "5253", "4335", "4250"],
    "name": ["CD 44", "CD 53", "CD 35", "CD 50"],
    "regional_committee_id": ["52", "52", "43", "42"],
    "departement_code": ["44", "53", "35", "50"],
})
REGIONAL_COMMITTEES = pd.DataFrame({
    "regional_committee_id": ["42", "43", "52"],
    "name": ["NORMANDIE", "BRETAGNE", "PAYS DE LA LOIRE"],
})


def startlist_page_html(
        description: str,
        tables: dict[str, list[list[str]]],
        title: str = "Vallet 22 novembre 2026 engagés"
    ) -> str:
    """HTML of a startlist page with the given description, tables by heading and title."""
    tables_html = "".join(
        f"<h3>{heading}</h3><table>"
        + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
        + "</table>"
        for heading, rows in tables.items()
    )
    return (
        f"<h1>{title}</h1>"
        f'<div class="date">18/11/2026</div><div class="description">{description}</div>'
        '<div id="article"><div class="simpleText"><div class="structured_text_semantique_text">'
        f'<div class="code_html">{tables_html}</div></div></div></div>'
    )


def page(page_id: str, html: str) -> UpcomingStartlistPage:
    """Upcoming startlist page with the given HTML."""
    return UpcomingStartlistPage(
        page_id, "2026-11-18", "2026-11-22", f"Vallet {page_id}", f"https://x/{page_id}.html", html
    )


def build(pages: list[UpcomingStartlistPage]) -> pd.DataFrame:
    """Entries of the pages with the reference tables of the tests."""
    return build_upcoming_entries(
        pages, REFERENCE_CLUBS, RIDERS, AFFILIATIONS, DEPARTEMENTS,
        DEPARTEMENTAL_COMMITTEES, REGIONAL_COMMITTEES,
    )


def rows(count: int) -> list[list[str]]:
    """Rows of the first `count` riders (the first one with an empty club cell)."""
    return [
        [name, "Jean", "" if i == 0 else "VC NANTAIS"]
        for i, name in enumerate(LAST_NAMES[:count])
    ]


def test_entries_of_the_identified_riders():
    tables = {
        "U17": rows(12),
        "ACCESS 3.4": rows(11) + [["INCONNU", "Paul", "VC NANTAIS"], ["ALPHA", "Jean", ""]],
    }
    entries = build([page("38949", startlist_page_html("A Vallet (44)", tables))])
    assert list(entries.columns) == ENTRIES_COLUMNS
    assert entries["race_date"].dtype == "datetime64[ns]"
    assert entries["rider_id"].tolist() == [f"r{i}" for i in range(11)]
    first = entries.iloc[0]
    assert (first["race_id"], first["race_date"], first["page_id"]) == (
        "vpc-38949-2", pd.Timestamp("2026-11-22"), "38949"
    )
    assert (first["page_title"], first["startlist_heading"]) == ("Vallet 38949", "ACCESS 3.4")


def test_race_below_the_minimum_of_identified_riders_is_left_out():
    tables = {"ACCESS": rows(9) + [["INCONNU", "Paul", "VC NANTAIS"]] * 3}
    assert build([page("1", startlist_page_html("A Vallet (44)", tables))]).empty


@pytest.mark.parametrize("description, kept", [
    ("A Laval (53)", True),
    ("A Granville (50)", False),
    ("A Vallet", True),
])
def test_pages_outside_the_covered_regions_are_left_out(description, kept):
    entries = build([page("1", startlist_page_html(description, {"ACCESS": rows(12)}))])
    assert (not entries.empty) is kept


def test_cancelled_race_page_is_skipped(caplog):
    caplog.set_level("INFO")
    entries = build([
        page("1", startlist_page_html("COURSE ANNULÉE. A Vallet (44)", {"ACCESS": rows(12)})),
        page("2", startlist_page_html("A Vallet (44)", {"ACCESS": rows(12)})),
    ])
    assert entries["page_id"].unique().tolist() == ["2"]
    assert "Startlist page 1 skipped (cancelled race)" in caplog.text


def test_cancelled_race_page_outside_the_covered_regions_is_not_logged(caplog):
    caplog.set_level("INFO")
    html = startlist_page_html("COURSE ANNULÉE. A Granville (50)", {"ACCESS": rows(12)})
    assert build([page("1", html)]).empty
    assert "cancelled race" not in caplog.text


WOMEN_TITLE = "Ste Sève 29 mars 2026 les engagées de courses cyclistes"


def test_women_race_page_is_skipped(caplog):
    caplog.set_level("INFO")
    women_html = startlist_page_html("A Vallet (44)", {"ACCESS": rows(12)}, title=WOMEN_TITLE)
    men_html = startlist_page_html("A Vallet (44)", {"ACCESS": rows(12)})
    entries = build([page("1", women_html), page("2", men_html)])
    assert entries["page_id"].unique().tolist() == ["2"]
    assert "Startlist page 1 skipped (women's race)" in caplog.text


def test_women_race_page_keeps_its_men_tables(caplog):
    caplog.set_level("INFO")
    tables = {"FEMMES ACCESS": rows(12), "ACCESS": rows(12), "HOMMES ACCESS": rows(12)}
    html = startlist_page_html("A Vallet (44)", tables, title=WOMEN_TITLE)
    entries = build([page("1", html)])
    assert entries["race_id"].unique().tolist() == ["vpc-1-3"]
    assert (
        "Startlist page 1: women's race title, only the men's or mixed tables kept"
        in caplog.text
    )


def test_unreadable_page_is_skipped(caplog):
    entries = build([
        page("1", "<html><body></body></html>"),
        page("2", startlist_page_html("A Vallet (44)", {"ACCESS": rows(10)})),
    ])
    assert entries["page_id"].unique().tolist() == ["2"]
    assert "Startlist page 1 skipped" in caplog.text


def test_each_page_read_is_logged(caplog):
    caplog.set_level("INFO")
    build([page("1", "<html><body></body></html>")])
    assert "Reading startlist page 1: Vallet 1" in caplog.text


def test_no_entries():
    entries = build([])
    assert list(entries.columns) == ENTRIES_COLUMNS
    assert entries.empty
