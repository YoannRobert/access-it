"""Unit tests of the OpenSkill ratings of the riders on the eve of each race."""

import pandas as pd
import pytest

from access_it.features.entries import select_forecast_entries
from access_it.features.ratings import (
    COLUMNS, check_rating_arguments, rate_entries_on_race_eve, rate_riders_on_race_eve
)

FIRST_RACE_DATE = "2023-04-01"


@pytest.fixture
def ratings_of(make_tables):
    """Ratings from FIRST_RACE_DATE to the season 2026 (unless given in kwargs)."""
    def compute(results: list[tuple], **kwargs) -> pd.DataFrame:
        races, rankings = make_tables(results)
        kwargs = {"last_season": 2026, "first_race_date": FIRST_RACE_DATE, **kwargs}
        return rate_riders_on_race_eve(races, rankings, **kwargs)
    return compute


def rating_of(ratings: pd.DataFrame, race_id: str, rider_id: str) -> tuple[float, float]:
    """Rating (mu, sigma) of a rider on the eve of a race."""
    row = ratings[(ratings["race_id"] == race_id) & (ratings["rider_id"] == rider_id)]
    return row["mu"].iloc[0], row["sigma"].iloc[0]


def test_output_of_the_races_forecast_with_default_ratings_of_new_riders(ratings_of):
    ratings = ratings_of(
        [
            ("r1", "2023-03-01", "c", 1), ("r1", "2023-03-01", "d", 2),
            ("r3", "2023-05-01", "b", 1), ("r3", "2023-05-01", "a", 2),
            ("r2", "2023-04-15", "a", 1), ("r2", "2023-04-15", "b", 2),
        ],
        sigma=5.0
    )
    assert ratings.columns.tolist() == COLUMNS
    assert ratings[["race_id", "rider_id"]].values.tolist() == [
        ["r2", "a"], ["r2", "b"], ["r3", "a"], ["r3", "b"]
    ]
    assert ratings.index.tolist() == [0, 1, 2, 3]
    assert ratings["race_date"].dtype == "datetime64[ns]"
    assert rating_of(ratings, "r2", "a") == (25.0, 5.0)


def test_ratings_read_on_the_eve_of_the_races_of_the_day(ratings_of):
    ratings = ratings_of([
        ("r1", "2023-05-01", "a", 1), ("r1", "2023-05-01", "b", 2),
        ("r2", "2023-05-01", "a", 1), ("r2", "2023-05-01", "c", 2),
    ])
    assert rating_of(ratings, "r2", "a") == rating_of(ratings, "r1", "a")
    assert rating_of(ratings, "r2", "a")[0] == 25.0


def test_winner_mu_rises_and_last_rider_mu_falls(ratings_of):
    ratings = ratings_of([
        ("r1", "2023-05-01", "a", 1), ("r1", "2023-05-01", "b", 2),
        ("r2", "2023-05-02", "a", 1), ("r2", "2023-05-02", "b", 2),
    ])
    assert rating_of(ratings, "r2", "a")[0] > 25.0
    assert rating_of(ratings, "r2", "b")[0] < 25.0


def test_tied_riders_of_equal_ratings_keep_equal_ratings(ratings_of):
    ratings = ratings_of([
        ("r1", "2023-05-01", "a", 1), ("r1", "2023-05-01", "b", 1),
        ("r1", "2023-05-01", "c", 3),
        ("r2", "2023-05-02", "a", 1), ("r2", "2023-05-02", "b", 2),
    ])
    assert rating_of(ratings, "r2", "a") == pytest.approx(rating_of(ratings, "r2", "b"))


def test_race_with_a_single_ranked_rider_does_not_update_his_rating(ratings_of):
    ratings = ratings_of([
        ("r1", "2023-05-01", "a", 1),
        ("r2", "2023-05-02", "a", 1), ("r2", "2023-05-02", "b", 2),
    ])
    assert rating_of(ratings, "r2", "a") == (25.0, 25 / 3)


def test_races_before_the_first_race_date_update_the_ratings(ratings_of):
    ratings = ratings_of([
        ("r1", "2023-03-01", "a", 1), ("r1", "2023-03-01", "b", 2),
        ("r2", "2023-05-01", "a", 1), ("r2", "2023-05-01", "b", 2),
    ])
    assert rating_of(ratings, "r2", "a")[0] > 25.0


def test_sigma_grows_with_the_days_without_race_up_to_the_initial_sigma(ratings_of):
    results = [
        ("r1", "2023-03-01", "a", 1), ("r1", "2023-03-01", "b", 2),
        ("r2", "2023-03-02", "a", 1), ("r2", "2023-03-02", "b", 2),
        ("r3", "2023-05-01", "a", 1), ("r3", "2023-05-01", "b", 2),
    ]
    sigma_without_growth = rating_of(ratings_of(results), "r3", "a")[1]
    sigma_small_growth = rating_of(ratings_of(results, sigma_growth_per_day=0.01), "r3", "a")[1]
    sigma_large_growth = rating_of(ratings_of(results, sigma_growth_per_day=10.0), "r3", "a")[1]
    assert sigma_without_growth < sigma_small_growth < 25 / 3
    assert sigma_large_growth == pytest.approx(25 / 3)


def test_larger_beta_gives_a_smaller_update_of_mu(ratings_of):
    results = [
        ("r1", "2023-05-01", "a", 1), ("r1", "2023-05-01", "b", 2),
        ("r2", "2023-05-02", "a", 1), ("r2", "2023-05-02", "b", 2),
    ]
    mu_default_beta = rating_of(ratings_of(results), "r2", "a")[0]
    mu_large_beta = rating_of(ratings_of(results, beta=20.0), "r2", "a")[0]
    assert 25.0 < mu_large_beta < mu_default_beta


@pytest.mark.parametrize("kwargs, message", [
    ({"sigma": 0.0}, "sigma must be greater than 0, not 0.0"),
    ({"beta": -1.0}, "beta must be greater than 0, not -1.0"),
    ({"tau": -0.1}, "tau must not be negative, not -0.1"),
    ({"sigma_growth_per_day": -1.0}, "sigma_growth_per_day must not be negative, not -1.0"),
    ({"last_season": 2022}, "Season 2022 is before the first season 2023"),
    ({"first_race_date": None}, "Missing first race date: None"),
    ({"first_race_date": "2027-04-01"}, "First race date 2027-04-01 is not in the seasons"),
    ({"first_race_date": "2023-06-01"}, "No race to forecast from 2023-06-01 to the season 2026"),
])
def test_invalid_arguments_raise(kwargs, message, ratings_of):
    with pytest.raises(ValueError, match=message):
        ratings_of([("r1", "2023-05-01", "a", 1)], **kwargs)


def test_missing_race_date_raises(make_tables, with_undated_race):
    races, rankings = make_tables([("r1", "2023-05-01", "a", 1)])
    with pytest.raises(ValueError, match="Missing race dates"):
        rate_riders_on_race_eve(with_undated_race(races), rankings, 2026, FIRST_RACE_DATE)


@pytest.mark.parametrize("undated, kwargs, message", [
    (False, {"sigma": 0.0, "beta": 0.0}, "sigma must be greater than 0"),
    (False, {"beta": 0.0, "tau": -1.0}, "beta must be greater than 0"),
    (False, {"tau": -1.0, "sigma_growth_per_day": -1.0}, "tau must not be negative"),
    (False, {"sigma_growth_per_day": -1.0, "last_season": 2022}, "sigma_growth_per_day must not"),
    (True, {"last_season": 2022}, "Season 2022 is before"),
    (True, {"first_race_date": "2023-06-01"}, "Missing race dates"),
])
def test_errors_raise_in_order(undated, kwargs, message, make_tables, with_undated_race):
    races, rankings = make_tables([("r1", "2023-05-01", "a", 1)])
    if undated:
        races = with_undated_race(races)
    kwargs = {"last_season": 2026, "first_race_date": FIRST_RACE_DATE, **kwargs}
    with pytest.raises(ValueError, match=message):
        rate_riders_on_race_eve(races, rankings, **kwargs)


@pytest.mark.parametrize("kwargs, message", [
    ({"sigma": 0.0}, "sigma must be greater than 0, not 0.0"),
    ({"beta": -1.0}, "beta must be greater than 0, not -1.0"),
    ({"tau": -0.1}, "tau must not be negative, not -0.1"),
    ({"sigma_growth_per_day": -1.0}, "sigma_growth_per_day must not be negative, not -1.0"),
    ({"tau": 0.0, "sigma_growth_per_day": 0.0}, None),
])
def test_invalid_rating_arguments_raise(kwargs, message):
    kwargs = {
        "sigma": 25 / 3, "beta": 25 / 6, "tau": 25 / 300, "sigma_growth_per_day": 0.0, **kwargs
    }
    if message is None:
        check_rating_arguments(**kwargs)
    else:
        with pytest.raises(ValueError, match=message):
            check_rating_arguments(**kwargs)


def test_entries_of_past_races_give_the_ratings_of_the_ranked_riders(make_tables):
    races, rankings = make_tables([
        ("r1", "2023-03-01", "a", 1), ("r1", "2023-03-01", "b", 2),
        ("r2", "2023-04-15", "b", 1), ("r2", "2023-04-15", "a", 2), ("r2", "2023-04-15", "c", 3),
        ("r3", "2023-05-01", "c", 1), ("r3", "2023-05-01", "a", 2),
    ])
    entries = select_forecast_entries(races, rankings, 2026, FIRST_RACE_DATE)
    pd.testing.assert_frame_equal(
        rate_entries_on_race_eve(races, rankings, entries)[COLUMNS],
        rate_riders_on_race_eve(races, rankings, 2026, FIRST_RACE_DATE),
    )


def test_entry_of_a_coming_race_gets_the_rating_on_its_eve(make_tables, make_entries):
    races, rankings = make_tables([("r1", "2023-05-01", "a", 1), ("r1", "2023-05-01", "b", 2)])
    ratings = rate_entries_on_race_eve(
        races, rankings, make_entries([("f1", "2023-06-01", "a"), ("f1", "2023-06-01", "z")])
    )
    assert rating_of(ratings, "f1", "a")[0] > 25.0
    assert rating_of(ratings, "f1", "z") == (25.0, 25 / 3)


def test_output_keeps_the_columns_of_the_entries(make_tables, make_entries):
    races, rankings = make_tables([("r1", "2023-05-01", "a", 1), ("r1", "2023-05-01", "b", 2)])
    entries = make_entries([
        ("f2", "2023-06-01", "b"), ("f1", "2023-06-01", "b"), ("f1", "2023-06-01", "a"),
    ]).assign(category="A1")
    ratings = rate_entries_on_race_eve(races, rankings, entries)
    assert ratings.columns.tolist() == [
        "race_id", "race_date", "rider_id", "category", "mu", "sigma"
    ]
    assert ratings[["race_id", "rider_id"]].values.tolist() == [
        ["f1", "a"], ["f1", "b"], ["f2", "b"]
    ]
    assert ratings.index.tolist() == [0, 1, 2]
    assert ratings["race_date"].dtype == "datetime64[ns]"


def test_entry_without_result_does_not_count_as_a_last_race(make_tables, make_entries):
    races, rankings = make_tables([
        ("r1", "2023-03-01", "a", 1), ("r1", "2023-03-01", "b", 2),
        ("r2", "2023-05-01", "a", 1), ("r2", "2023-05-01", "b", 2),
    ])
    entries = make_entries([("r2", "2023-05-01", "a"), ("r2", "2023-05-01", "b")])
    with_unranked_entry = pd.concat(
        [entries, make_entries([("f1", "2023-04-01", "a")])], ignore_index=True
    )
    sigma_without = rating_of(
        rate_entries_on_race_eve(races, rankings, entries, sigma_growth_per_day=0.01), "r2", "a"
    )[1]
    sigma_with = rating_of(
        rate_entries_on_race_eve(races, rankings, with_unranked_entry, sigma_growth_per_day=0.01),
        "r2", "a"
    )[1]
    assert sigma_with == sigma_without


def test_race_dates_checked_up_to_the_season_of_the_last_entry(
        make_tables, make_entries, with_undated_race
    ):
    races, rankings = make_tables([("r1", "2023-05-01", "a", 1), ("r1", "2023-05-01", "b", 2)])
    entries = make_entries([("f1", "2023-06-01", "a")])
    with pytest.raises(ValueError, match="Missing race dates in the results"):
        rate_entries_on_race_eve(with_undated_race(races), rankings, entries)
    undated_2025 = pd.DataFrame({"race_id": ["r0"], "race_date": [None], "season": [2025]})
    rate_entries_on_race_eve(pd.concat([races, undated_2025], ignore_index=True), rankings, entries)


@pytest.mark.parametrize("rows, undated, kwargs, message", [
    ([], False, {"sigma": 0.0}, "sigma must be greater than 0"),
    ([], True, {}, "No entries"),
    (
        [("f1", "2023-06-01", "a"), ("f1", "2023-06-01", "a")], True, {},
        "Riders entered twice in a race",
    ),
])
def test_entry_errors_raise_in_order(
        rows, undated, kwargs, message, make_tables, make_entries, with_undated_race
    ):
    races, rankings = make_tables([("r1", "2023-05-01", "a", 1)])
    if undated:
        races = with_undated_race(races)
    with pytest.raises(ValueError, match=message):
        rate_entries_on_race_eve(races, rankings, make_entries(rows), **kwargs)
