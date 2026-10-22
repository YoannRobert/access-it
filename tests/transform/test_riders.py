"""Unit tests of the rider functions of the transform step."""

import hashlib

import pandas as pd

from access_it.etl.extract.constants import INDIVIDUAL_CLUB_ID
from access_it.etl.transform.riders import (
    RED_LIST, add_riders_to_database, assign_rider_ids, define_rider_id,
    identify_club_of_riders
)

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


# ---------------------------------------------------------------- assign_rider_ids

OTHER_VALID_UCI_ID = "10012345757"  # 100123457 % 97 == 57


def results(*rows: tuple) -> pd.DataFrame:
    """Results from (uci_id, last_name, first_name, club_id) tuples."""
    return pd.DataFrame(
        [
            {"race_id": f"r{k}", "finish_rank": k, "uci_id": uci_id, "last_name": last_name,
             "first_name": first_name, "club_id": club_id}
            for k, (uci_id, last_name, first_name, club_id) in enumerate(rows, start=1)
        ]
    )


def assigned(data: pd.DataFrame) -> pd.DataFrame:
    """Results with their rider ID, the rider table being built from the same results."""
    return assign_rider_ids(data, add_riders_to_database(data))


def test_valid_uci_id_gives_its_rider_whatever_the_names(capsys):
    data = results((VALID_UCI_ID, "DUPONT", "Jean", "A"), (VALID_UCI_ID, "", "", "A"))
    out = assigned(data)
    assert list(out["rider_id"]) == [define_rider_id(VALID_UCI_ID, "", "")] * 2
    assert "dropped" not in capsys.readouterr().out


def test_red_list_rider_is_not_mixed_up_with_a_homonym_having_a_uci_id():
    data = results((VALID_UCI_ID, "DUPONT", "Jean", "A"), (RED_LIST, "DUPONT", "Jean", "B"))
    out = assigned(data)
    assert list(out["rider_id"]) == [
        define_rider_id(VALID_UCI_ID, "DUPONT", "Jean"),
        define_rider_id(RED_LIST, "DUPONT", "Jean"),
    ]


def test_missing_uci_id_among_homonyms_gives_the_rider_without_uci_id():
    data = results(
        (VALID_UCI_ID, "DUPONT", "Jean", "A"),
        (OTHER_VALID_UCI_ID, "DUPONT", "Jean", "B"),
        ("", "DUPONT", "Jean", "C"),
    )
    out = assigned(data)
    assert out["rider_id"].iloc[2] == define_rider_id("", "DUPONT", "Jean")
    assert out["rider_id"].nunique() == 3


def test_missing_uci_id_of_a_red_list_rider_gives_the_red_list_rider():
    data = results((RED_LIST, "DUPONT", "Jean", "A"), ("", "DUPONT", "Jean", "A"))
    out = assigned(data)
    assert list(out["rider_id"]) == [define_rider_id(RED_LIST, "DUPONT", "Jean")] * 2


def test_individual_licensee_with_an_invalid_uci_id_is_kept():
    data = results(("12345", "DUPONT", "Jean", INDIVIDUAL_CLUB_ID))
    out = assigned(data)
    assert list(out["rider_id"]) == [define_rider_id("12345", "DUPONT", "Jean")]


def test_results_without_rider_are_dropped_and_reported(capsys):
    data = results(
        ("10012345600", "DUPONT", "Jean", "A"),  # wrong check digits
        ("", "", "Jean", "A"),
        (None, None, None, "A"),
        (VALID_UCI_ID, "MARTIN", "Paul", "A"),
    )
    out = assigned(data)
    assert list(out["race_id"]) == ["r4"]
    output = capsys.readouterr().out
    assert "Warning: 3 result row(s) dropped, rider not identified:" in output
    assert "invalid UCI ID, to fix in correct_wrong_uci_ids: 1" in output
    assert "race_id=r1, finish_rank=1, uci_id='10012345600'" in output
    assert "missing names: 2" in output


def test_every_assigned_rider_is_in_the_rider_table():
    data = results(
        (VALID_UCI_ID, "DUPONT", "Jean", "A"),
        (RED_LIST, "DUPONT", "Jean", "A"),
        ("", "DUPONT", "Jean", "A"),
        ("", "MARTIN", "Paul", INDIVIDUAL_CLUB_ID),
        ("", "MARTIN", "Paul", "A"),
    )
    rider_db = add_riders_to_database(data)
    out = assign_rider_ids(data, rider_db)
    assert len(out) == len(data)
    assert set(out["rider_id"]) <= set(rider_db["rider_id"])
