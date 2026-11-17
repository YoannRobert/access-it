"""Unit tests of the baseline of the forecast: riders ranked by their recent form."""

import pandas as pd
import pytest

from access_it.features.baseline import COLUMNS, rank_by_recent_form

FIRST_RACE_DATE = "2023-04-01"


def make_tables(results: list[tuple]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Race and ranking tables from (race_id, race_date, rider_id, finish_rank) tuples."""
    df = pd.DataFrame(results, columns=["race_id", "race_date", "rider_id", "finish_rank"])
    races = df[["race_id", "race_date"]].drop_duplicates().assign(
        season=lambda d: pd.to_datetime(d["race_date"]).dt.year
    )
    return races, df[["race_id", "rider_id", "finish_rank"]]


def forecast_of(results: list[tuple], **kwargs) -> pd.DataFrame:
    """Baseline from FIRST_RACE_DATE to the season 2026 (unless given in kwargs)."""
    races, rankings = make_tables(results)
    kwargs = {"last_season": 2026, "first_race_date": FIRST_RACE_DATE, **kwargs}
    return rank_by_recent_form(races, rankings, **kwargs)


def with_undated_race(races: pd.DataFrame) -> pd.DataFrame:
    """Race table with a race of 2023 without date added."""
    undated = pd.DataFrame({"race_id": ["r0"], "race_date": [None], "season": [2023]})
    return pd.concat([races, undated], ignore_index=True)


def ranked_riders(forecast: pd.DataFrame, race_id: str) -> list[str]:
    """Riders of a race, from the first predicted rank to the last one."""
    return forecast.loc[forecast["race_id"] == race_id, "rider_id"].tolist()


def test_races_forecast_from_the_first_race_date_to_the_last_season():
    forecast = forecast_of(
        [
            ("r1", "2023-03-31", "a", 1), ("r2", "2023-04-01", "a", 1),
            ("r3", "2025-10-01", "a", 1), ("r4", "2026-04-01", "a", 1),
        ],
        last_season=2025
    )
    assert forecast["race_id"].tolist() == ["r2", "r3"]


def test_start_list_is_made_of_the_ranked_riders():
    forecast = forecast_of([
        ("r1", "2023-03-01", "a", 1), ("r1", "2023-03-01", "b", 2),
        ("r2", "2023-05-01", "b", 1), ("r2", "2023-05-01", "c", 2),
    ])
    assert ranked_riders(forecast, "r2") == ["b", "c"]


def test_recent_form_is_computed_on_the_eve_of_the_race():
    forecast = forecast_of([
        ("r1", "2023-05-01", "a", 30), ("r2", "2023-05-01", "a", 1),
        ("r3", "2023-05-02", "a", 1),
    ])
    assert forecast.loc[forecast["race_id"] == "r1", "nb_races_used"].tolist() == [0]
    assert forecast.loc[forecast["race_id"] == "r3", "nb_races_used"].tolist() == [2]


def test_riders_ranked_by_share_of_top_n():
    forecast = forecast_of([
        ("r1", "2023-03-01", "a", 30), ("r1", "2023-03-01", "b", 1),
        ("r2", "2023-05-01", "a", 1), ("r2", "2023-05-01", "b", 2),
    ])
    assert ranked_riders(forecast, "r2") == ["b", "a"]


def test_tie_broken_by_the_best_places_one_after_the_other():
    forecast = forecast_of([
        ("r1", "2023-03-01", "a", 12), ("r1", "2023-03-01", "b", 8),
        ("r2", "2023-03-02", "a", 8), ("r2", "2023-03-02", "b", 12),
        ("r3", "2023-03-03", "a", 23), ("r3", "2023-03-03", "b", 21),
        ("r4", "2023-05-01", "a", 1), ("r4", "2023-05-01", "b", 2),
    ])
    assert ranked_riders(forecast, "r4") == ["b", "a"]


def test_missing_place_is_worse_than_any_place():
    forecast = forecast_of([
        ("r1", "2023-03-01", "a", 50), ("r1", "2023-03-01", "b", 50),
        ("r2", "2023-03-02", "b", 90),
        ("r3", "2023-05-01", "a", 1), ("r3", "2023-05-01", "b", 2),
    ])
    assert ranked_riders(forecast, "r3") == ["b", "a"]


def test_last_tie_broken_by_rider_id_with_a_unique_rank():
    forecast = forecast_of([
        ("r1", "2023-03-01", "b", 5), ("r1", "2023-03-01", "a", 5),
        ("r2", "2023-05-01", "b", 1), ("r2", "2023-05-01", "a", 2),
    ])
    assert ranked_riders(forecast, "r2") == ["a", "b"]
    assert forecast["predicted_rank"].tolist() == [1, 2]


def test_race_without_recent_form_is_kept_and_ranked_by_rider_id():
    forecast = forecast_of([("r1", "2023-05-01", "b", 1), ("r1", "2023-05-01", "a", 2)])
    assert ranked_riders(forecast, "r1") == ["a", "b"]
    assert forecast["nb_races_used"].tolist() == [0, 0]


def test_output_columns_order_and_index():
    forecast = forecast_of([
        ("r2", "2023-05-01", "a", 2), ("r2", "2023-05-01", "b", 1),
        ("r1", "2023-05-01", "a", 1), ("r3", "2023-04-15", "c", 1),
    ])
    assert forecast.columns.tolist() == COLUMNS
    assert forecast[["race_id", "predicted_rank"]].values.tolist() == [
        ["r3", 1], ["r1", 1], ["r2", 1], ["r2", 2]
    ]
    assert forecast.index.tolist() == [0, 1, 2, 3]
    assert forecast["race_date"].dtype == "datetime64[ns]"
    assert forecast["finish_rank"].tolist() == [1, 1, 2, 1]


@pytest.mark.parametrize("kwargs, message", [
    ({"top_n": 21}, "top_n must be between 1 and 20, not 21"),
    ({"last_races": 0}, "last_races must be at least 1, not 0"),
    ({"window_months": 0}, "window_months must be at least 1, not 0"),
    ({"last_season": 2022}, "Season 2022 is before the first season 2023"),
    ({"first_race_date": None}, "Missing first race date: None"),
    ({"first_race_date": "2022-12-31"}, "First race date 2022-12-31 is not in the seasons"),
    ({"first_race_date": "2027-04-01"}, "First race date 2027-04-01 is not in the seasons"),
    ({"first_race_date": "2023-06-01"}, "No race to forecast from 2023-06-01 to the season 2026"),
])
def test_invalid_arguments_raise(kwargs, message):
    with pytest.raises(ValueError, match=message):
        forecast_of([("r1", "2023-05-01", "a", 1)], **kwargs)


def test_missing_race_date_raises():
    races, rankings = make_tables([("r1", "2023-05-01", "a", 1)])
    with pytest.raises(ValueError, match="Missing race dates"):
        rank_by_recent_form(with_undated_race(races), rankings, 2026, FIRST_RACE_DATE)


@pytest.mark.parametrize("undated, kwargs, message", [
    (False, {"top_n": 21, "last_season": 2022}, "top_n must be between 1 and 20"),
    (False, {"last_season": 2022, "first_race_date": None}, "Season 2022 is before"),
    (True, {"first_race_date": None}, "Missing first race date"),
    (True, {"first_race_date": "2027-04-01"}, "First race date 2027-04-01 is not in"),
    (True, {"first_race_date": "2023-06-01"}, "Missing race dates"),
])
def test_errors_raise_in_order(undated, kwargs, message):
    races, rankings = make_tables([("r1", "2023-05-01", "a", 1)])
    if undated:
        races = with_undated_race(races)
    kwargs = {"last_season": 2026, "first_race_date": FIRST_RACE_DATE, **kwargs}
    with pytest.raises(ValueError, match=message):
        rank_by_recent_form(races, rankings, **kwargs)
