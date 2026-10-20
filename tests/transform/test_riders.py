"""Unit tests of the rider functions of the transform step."""

import pandas as pd

from access_it.etl.transform.riders import identify_club_of_riders

CLUBS = pd.DataFrame({
    "club_id": ["4976038"],
    "name": ["AC SOTTEVILLAIS"],
    "departemental_committee_id": ["4976"],
    "min_year": [2025],
    "max_year": [2025],
    "alternative_names": ["AC SOTTEVILLE"],
})


def result_row(club: str | None) -> dict:
    return {"last_name": "X", "first_name": "Y", "uci_id": "", "finish_rank": 1, "club": club}


def test_identified_clubs_are_kept_without_report(capsys):
    rows = [result_row("4976038 AC SOTTEVILLAIS"), result_row("AC SOTTEVILLE")]
    data = identify_club_of_riders(rows, CLUBS)
    assert [row["club_id"] for row in data] == ["4976038", "4976038"]
    assert all("club" not in row for row in data)
    assert capsys.readouterr().out == ""


def test_unidentified_clubs_are_dropped_and_reported(capsys):
    rows = [
        result_row("AC SOTTEVILLE"),
        result_row("UNKNOWN CLUB NAME"),
        result_row("UNKNOWN CLUB NAME"),
        result_row("OTHER UNKNOWN CLUB"),
    ]
    data = identify_club_of_riders(rows, CLUBS)
    assert len(data) == 1
    output = capsys.readouterr().out
    assert "Warning: 3 result row(s) dropped, club not identified (2 club text(s)):" in output
    lines = output.splitlines()
    assert lines[1].split() == ["2", "'UNKNOWN", "CLUB", "NAME'"]
    assert lines[2].split() == ["1", "'OTHER", "UNKNOWN", "CLUB'"]
