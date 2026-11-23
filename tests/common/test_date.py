"""Characterization tests of the conversion of the FFC race dates."""

import pytest

from access_it.common.date import convert_date, correct_startlist_date, parse_startlist_title


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Samedi 12 avril 2025", "2025-04-12"),
        ("dimanche 01 juin 2025", "2025-06-01"),
        ("  Lundi 03 mars 2025 ", "2025-03-03"),
        ("samedi 16 Août 2025", "2025-08-16"),
        ("Dimanche 21 décembre 2025", "2025-12-21"),
        ("Mercredi 05 février 2025", "2025-02-05"),
    ],
)
def test_convert_date(text, expected):
    assert convert_date(text) == expected


def test_convert_date_without_date():
    assert convert_date(None) is None


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


@pytest.mark.parametrize(
    "title, publication_date, title_date, date",
    [
        ("Trélazé 11 octobre 2026 engagés", "2026-10-06", "2026-10-11", "2026-10-11"),
        ("Le Loroux 1er mars 2026 les engagés", "2026-02-24", "2026-03-01", "2026-03-01"),
        ("St Philbert 4 et 5 octobre 2025 engagés", "2025-09-29", "2025-10-04", "2025-10-04"),
        ("Louisfert 4, 5, 6 avril 2026 engagés", "2026-04-02", "2026-04-04", "2026-04-04"),
        ("Adainville 78 31 mai 2026 engagés", "2026-05-26", "2026-05-31", "2026-05-31"),
        ("Trophée des Champions engagés", "2026-09-28", "2026-09-28", "2026-09-28"),
        ("Le Loroux 1er mars 2025 les engagés", "2026-02-24", "2025-03-01", "2026-03-01"),
        ("Faun Tour 10-13 septembre 2026 partantes", "2026-09-08", "2026-09-08", "2026-09-08"),
    ],
)
def test_race_date_read_in_a_startlist_title(title, publication_date, title_date, date):
    assert parse_startlist_title(title, publication_date)[1:] == (title_date, date)


@pytest.mark.parametrize(
    "title, name",
    [
        ("Trélazé 11 octobre 2026 engagés", "Trélazé"),
        ("Adainville 78 31 mai 2026 engagés", "Adainville 78"),
    ],
)
def test_name_read_in_a_startlist_title(title, name):
    assert parse_startlist_title(title, "2026-05-26")[0] == name
