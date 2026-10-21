"""Unit tests of the parsing of the startlist pages."""

import pytest

from bs4 import BeautifulSoup

from access_it.etl.transform.parse import (
    correct_startlist_date, get_elements_from_results_page,
    parse_startlists_from_organization_page
)


def startlist_page(title: str, publication_date: str) -> str:
    """Minimal startlist page (publication date as 'DD/MM/YYYY')."""
    return (
        f"<html><body><h1>{title}</h1><div class='description'>Access</div>"
        f"<div class='date'>{publication_date}</div><div id='article'></div></body></html>"
    )


@pytest.mark.parametrize(
    "title_date, publication_date, expected",
    [
        ("2025-08-31", "2025-08-27", "2025-08-31"),  # usual case: a few days after publication
        ("2025-08-25", "2025-08-27", "2025-08-25"),  # slightly before publication
        ("2025-03-01", "2026-02-24", "2026-03-01"),  # typo in the year of the title
        ("2026-01-04", "2025-12-29", "2026-01-04"),  # race in January, published in December
        ("2025-01-04", "2025-12-29", "2026-01-04"),  # same, with the year of the publication
        ("2025-06-15", "2025-12-29", "2025-12-29"),  # no plausible year: publication date
        ("2024-02-29", "2025-02-20", "2025-02-20"),  # February 29th, no leap year in the window
    ],
)
def test_correct_startlist_date(title_date, publication_date, expected):
    assert correct_startlist_date(title_date, publication_date) == expected


def test_startlist_with_a_wrong_year_in_the_title():
    page = startlist_page("Le Loroux 1er mars 2025 les engagés de courses cyclistes", "24/02/2026")
    data = parse_startlists_from_organization_page(page)
    assert data["title_date"] == "2025-03-01"
    assert data["date"] == "2026-03-01"


def test_startlist_with_a_correct_title():
    page = startlist_page("La Séguinière 31 août 2025 les engagés", "27/08/2025")
    data = parse_startlists_from_organization_page(page)
    assert data["title_date"] == data["date"] == "2025-08-31"


def test_startlist_over_two_days():
    title = "Landaul La Landaulaise 20 et 21 septembre 2025 les engagés"
    page = startlist_page(title, "15/09/2025")
    data = parse_startlists_from_organization_page(page)
    assert data["date"] == "2025-09-20"


def test_number_before_the_day_is_not_taken_as_the_day():
    title = "Ladies Tour Adainville 78 31 mai 2026 les engagées de course cycliste"
    data = parse_startlists_from_organization_page(startlist_page(title, "26/05/2026"))
    assert data["title_date"] == data["date"] == "2026-05-31"


def test_title_starting_with_the_day():
    page = startlist_page("31 mai 2026 Adainville", "26/05/2026")
    data = parse_startlists_from_organization_page(page)
    assert data["date"] == "2026-05-31"


def test_title_without_day_uses_the_publication_date():
    page = startlist_page("Adainville mai 2026", "26/05/2026")
    data = parse_startlists_from_organization_page(page)
    assert data["date"] == "2026-05-26"


# ---------------------------------------------------------------- result pages

def results_page(*blocks: tuple[str, str]) -> BeautifulSoup:
    """Minimal result page with general information blocks (label, value)."""
    html = "".join(
        "<div class='info-principale'>"
        f"<div class='titreValeur-titre'>{label}</div>"
        f"<div class='titreValeur-valeur'>{value}</div></div>"
        for label, value in blocks
    )
    return BeautifulSoup(html, features="html.parser")


def test_result_page_elements_are_translated():
    bs = results_page(("Saison", "2026"), ("Code épreuve", "1.27.1"))
    assert get_elements_from_results_page(bs) == {"season": 2026, "race_code": "1.27.1"}


def test_unknown_label_is_ignored_and_reported_once(capsys):
    bs = results_page(("Nouveau champ FFC", "x"), ("Code épreuve", "1.27.1"))
    assert get_elements_from_results_page(bs) == {"race_code": "1.27.1"}
    assert get_elements_from_results_page(bs) == {"race_code": "1.27.1"}
    assert capsys.readouterr().out.count("unknown label on a result page") == 1


def test_empty_label_or_value_is_ignored():
    bs = results_page(("", "x"), ("Durée", ""), ("Code épreuve", "1.27.1"))
    assert get_elements_from_results_page(bs) == {"race_code": "1.27.1"}
