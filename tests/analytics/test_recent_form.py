"""Unit tests of the recent form of the riders."""

from datetime import date

import pandas as pd
import pytest

from access_it.analytics.recent_form import COLUMNS, compute_recent_form

REFERENCE_DATE = "2026-07-01"


def make_tables(results: list[tuple]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Race and ranking tables from (race_id, race_date, rider_id, finish_rank) tuples."""
    df = pd.DataFrame(results, columns=["race_id", "race_date", "rider_id", "finish_rank"])
    races = df[["race_id", "race_date"]].drop_duplicates()
    return races, df[["race_id", "rider_id", "finish_rank"]]


def form_of(results: list[tuple], rider_ids: list[str], **kwargs) -> pd.DataFrame:
    """Recent form on REFERENCE_DATE (unless given in kwargs), indexed by rider_id."""
    races, rankings = make_tables(results)
    kwargs.setdefault("reference_date", REFERENCE_DATE)
    return compute_recent_form(races, rankings, rider_ids, **kwargs).set_index("rider_id")


def test_window_starts_six_months_before_included():
    form = form_of(
        [("r1", "2025-12-31", "a", 1), ("r2", "2026-01-01", "a", 1), ("r3", "2026-06-30", "a", 30)],
        ["a"]
    )
    assert form.loc["a", ["nb_races_used", "nb_top_n"]].tolist() == [2, 1]
    assert form.loc["a", "top_n_rate"] == 0.5


def test_races_of_the_reference_date_are_excluded():
    form = form_of(
        [("r1", "2026-06-30", "a", 1), ("r2", "2026-07-01", "a", 1)],
        ["a"],
        reference_date=pd.Timestamp("2026-07-01 18:00")
    )
    assert form.loc["a", "nb_races_used"] == 1


def test_only_the_last_races_are_used():
    results = [(f"r{d:02d}", f"2026-06-{d:02d}", "a", 1 if d <= 2 else 50) for d in range(1, 13)]
    form = form_of(results, ["a"])
    assert form.loc["a", ["nb_races_used", "nb_top_n"]].tolist() == [10, 0]


def test_same_day_races_keep_the_best_place_first():
    results = [(f"r{d:02d}", f"2026-06-{d:02d}", "a", 50) for d in range(2, 11)]
    results += [("r00", "2026-06-01", "a", 1), ("r99", "2026-06-01", "a", 50)]
    form = form_of(results, ["a"])
    assert form.loc["a", ["nb_races_used", "nb_top_n"]].tolist() == [10, 1]


def test_tied_riders_all_count():
    form = form_of(
        [("r1", "2026-06-01", "a", 20), ("r1", "2026-06-01", "b", 20), ("r1", "2026-06-01", "c", 21)],
        ["a", "b", "c"]
    )
    assert form["nb_top_n"].tolist() == [1, 1, 0]


def test_rider_without_race_has_a_null_form():
    form = form_of([("r1", "2026-06-01", "a", 1)], ["a", "z"])
    assert form.loc["z", ["nb_races_used", "nb_top_n", "top_n_rate"]].tolist() == [0, 0, 0.0]


def test_foreign_rider_is_kept_and_nobody_moves_up():
    # "f" stands for a foreign rider: the function ignores the clubs, so he
    # is ranked like any rider and "a", behind him, keeps his finish rank.
    form = form_of(
        [("r1", "2026-06-01", "f", 20), ("r1", "2026-06-01", "a", 21)],
        ["f", "a"]
    )
    assert form["nb_top_n"].tolist() == [1, 0]


def test_output_follows_the_order_of_rider_ids():
    races, rankings = make_tables([("r1", "2026-06-01", "a", 1), ("r1", "2026-06-01", "b", 2)])
    form = compute_recent_form(races, rankings, ["b", "z", "a"], REFERENCE_DATE)
    assert form.columns.tolist() == COLUMNS
    assert form["rider_id"].tolist() == ["b", "z", "a"]


@pytest.mark.parametrize(
    "reference_date",
    ["2026-07-01", date(2026, 7, 1), pd.to_datetime(pd.Series(["2026-07-01 12:00"])).iloc[0]],
    ids=["string", "date", "timestamp"]
)
def test_reference_date_as_string_or_date(reference_date):
    results = [("r1", "2026-06-30", "a", 1), ("r2", "2026-07-01", "a", 1)]
    form = form_of(results, ["a"], reference_date=reference_date)
    assert form.loc["a", ["nb_races_used", "nb_top_n"]].tolist() == [1, 1]
