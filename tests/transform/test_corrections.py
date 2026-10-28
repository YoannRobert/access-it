"""Checks of the hard-coded corrections of the result pages."""

from collections import Counter

import pytest

from access_it.etl.transform.rider_x_race_data import (
    CLUB_CORRECTIONS, FOREIGN_LABEL_CORRECTIONS, INDIVIDUAL_LABEL_CORRECTIONS,
    UCI_ID_CORRECTIONS, correct_wrong_clubs
)

CORRECTIONS = {
    "UCI_ID_CORRECTIONS": UCI_ID_CORRECTIONS,
    "INDIVIDUAL_LABEL_CORRECTIONS": INDIVIDUAL_LABEL_CORRECTIONS,
    "FOREIGN_LABEL_CORRECTIONS": FOREIGN_LABEL_CORRECTIONS,
    "CLUB_CORRECTIONS": CLUB_CORRECTIONS,
}


@pytest.mark.parametrize("name", CORRECTIONS)
def test_each_result_is_corrected_once(name):
    keys = Counter((race_id, finish_rank) for race_id, finish_rank, *_ in CORRECTIONS[name])
    duplicates = [key for key, count in keys.items() if count > 1]
    assert duplicates == [], f"results corrected twice in {name}: {duplicates}"


def test_no_result_is_both_individual_and_foreign():
    both = set(INDIVIDUAL_LABEL_CORRECTIONS) & set(FOREIGN_LABEL_CORRECTIONS)
    assert both == set(), f"results in both label corrections: {sorted(both)}"


def test_club_correction_replaces_the_club_whatever_its_value():
    race_id, finish_rank, club = CLUB_CORRECTIONS[0]
    data = [
        {"race_id": race_id, "finish_rank": finish_rank, "club": "Individuel"},
        {"race_id": race_id, "finish_rank": finish_rank + 1, "club": "Individuel"},
    ]
    assert [d["club"] for d in correct_wrong_clubs(data)] == [club, "Individuel"]
