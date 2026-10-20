"""Unit tests of the rider functions of the transform step."""

import hashlib

import pandas as pd

from access_it.etl.transform.riders import define_rider_id, identify_club_of_riders

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


# ---------------------------------------------------------------- define_rider_id

VALID_UCI_ID = "10012345656"  # 100123456 % 97 == 56


def names_based_id(uci_id: str, last_name: str, first_name: str) -> str:
    """Former formula, still used for riders without a valid UCI ID."""
    key = f"{uci_id}|{last_name}|{first_name}".encode()
    return hashlib.blake2b(key, digest_size=8).hexdigest()


def test_rider_id_with_valid_uci_id_does_not_depend_on_names():
    rider_id = define_rider_id(VALID_UCI_ID, "MARTIN", "Jean")
    assert define_rider_id(VALID_UCI_ID, "Jean", "MARTIN") == rider_id
    assert define_rider_id(VALID_UCI_ID, "MARTIN-DUPONT", "Jean-Luc") == rider_id
    assert define_rider_id(f" {VALID_UCI_ID} ", "MARTIN", "Jean") == rider_id


def test_rider_ids_with_different_valid_uci_ids_differ():
    other_uci_id = "10012345757"  # 100123457 % 97 == 57
    assert define_rider_id(VALID_UCI_ID, "X", "Y") != define_rider_id(other_uci_id, "X", "Y")


def test_rider_id_without_valid_uci_id_is_unchanged():
    assert define_rider_id("", "Martin", "Élodie") == names_based_id("", "martin", "elodie")
    assert define_rider_id(None, "Martin", "Élodie") == names_based_id("", "martin", "elodie")
    assert define_rider_id("Liste Rouge", "MARTIN", "J.") == names_based_id(
        "Liste Rouge", "martin", "j."
    )
    assert define_rider_id("10012345699", "MARTIN", "Jean") == names_based_id(
        "10012345699", "martin", "jean"
    )
