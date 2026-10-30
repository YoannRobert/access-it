"""Unit tests of the building blocks shared by the rankings."""

import pandas as pd
import pytest

from access_it.analytics.ranking_tools import (
    compute_places, get_reference_date, rank_scoring_riders, scale_points, select_category,
    select_club
)
from access_it.etl.extract.constants import INDIVIDUAL_CLUB_ID


def test_places_skip_the_next_place_after_tied_riders():
    results = pd.DataFrame({"race_id": ["r1"] * 4 + ["r2"], "finish_rank": [1, 3, 3, 7, 4]})
    assert compute_places(results).tolist() == [1, 2, 2, 4, 1]


def test_points_of_the_scale_and_none_for_an_unknown_category():
    results = pd.DataFrame({"place": [1, 2, 3, 2], "category": ["A1", "A1", "A1", None]})
    assert scale_points(results, (6, 4)).tolist() == [6, 4, 0, 0]


def test_club_shown_skips_the_individual_licences():
    assert select_club(pd.Series([INDIVIDUAL_CLUB_ID, "5244800", "5244001"])) == "5244001"
    assert select_club(pd.Series(["5244800"])) == "5244800"


def test_riders_ranked_by_points_then_places_then_names():
    scoring = pd.DataFrame({
        "race_id": ["r1", "r1", "r2", "r2", "r3"],
        "rider_id": ["a", "b", "b", "c", "c"],
        "club_id": ["X"] * 5,
        "place": [1, 2, 1, 2, 2],
        "category": ["A1"] * 5,
        "points": [6, 4, 6, 4, 4],
    })
    riders = pd.DataFrame(
        {"rider_id": ["a", "b", "c"], "last_name": ["A", "B", "C"], "first_name": "x"}
    )
    clubs = pd.DataFrame({"club_id": ["X"], "name": ["Club X"]})
    ranking = rank_scoring_riders(scoring, riders, clubs, max_place=5)
    assert ranking[["rider_id", "rank", "points", "nb_wins"]].values.tolist() == [
        ["b", 1, 10, 1], ["c", 2, 8, 0], ["a", 3, 6, 1]
    ]


def test_unknown_category_raises():
    with pytest.raises(ValueError, match="Unknown category"):
        select_category(pd.DataFrame(columns=["category"]), "A5")


def test_reference_date_is_the_day_after_the_last_race():
    races = pd.DataFrame({"race_date": ["2026-10-25", "2026-10-26", "2026-03-01"]})
    assert get_reference_date(races) == pd.Timestamp("2026-10-27")


def test_reference_date_of_an_empty_race_table_raises():
    with pytest.raises(ValueError):
        get_reference_date(pd.DataFrame({"race_date": []}))
