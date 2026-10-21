"""Characterization tests of the conversion of the FFC race dates."""

import pytest

from access_it.common.date import convert_date


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
