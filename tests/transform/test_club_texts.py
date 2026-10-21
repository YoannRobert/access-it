"""Characterization tests of the reading of club texts."""

import pytest

from access_it.etl.transform.clubs import parse_club_text


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
