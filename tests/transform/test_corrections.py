"""Checks of the hard-coded corrections of the result pages."""

from collections import Counter

import pytest

from access_it.etl.transform.rider_x_race_data import (
    FOREIGN_LABEL_CORRECTIONS, INDIVIDUAL_LABEL_CORRECTIONS, UCI_ID_CORRECTIONS
)

CORRECTIONS = {
    "UCI_ID_CORRECTIONS": UCI_ID_CORRECTIONS,
    "INDIVIDUAL_LABEL_CORRECTIONS": INDIVIDUAL_LABEL_CORRECTIONS,
    "FOREIGN_LABEL_CORRECTIONS": FOREIGN_LABEL_CORRECTIONS,
}


@pytest.mark.parametrize("name", CORRECTIONS)
def test_each_result_is_corrected_once(name):
    keys = Counter((race_id, finish_rank) for race_id, finish_rank, *_ in CORRECTIONS[name])
    duplicates = [key for key, count in keys.items() if count > 1]
    assert duplicates == [], f"results corrected twice in {name}: {duplicates}"


def test_no_result_is_both_individual_and_foreign():
    both = set(INDIVIDUAL_LABEL_CORRECTIONS) & set(FOREIGN_LABEL_CORRECTIONS)
    assert both == set(), f"results in both label corrections: {sorted(both)}"
