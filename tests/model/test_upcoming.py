"""Unit tests of the probabilities of the riders entered in upcoming races to reach each target."""

import logging

import numpy as np
import pandas as pd
import pytest

from access_it.features.entries import select_forecast_entries
from access_it.features.examples import FEATURES, build_race_eve_features
from access_it.model.forecasts import (
    PROBABILITY_COLUMNS, RANK_COLUMNS, forecast_place_probabilities
)
from access_it.model.upcoming import forecast_upcoming_entries

RESULT_DATES = [f"2024-{month:02d}-01" for month in range(3, 8)]
RIDER_IDS = [f"rider{j:02d}" for j in range(20)]


def make_results(dates: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One race per date, the same 20 riders ranked in an order drawn with a fixed seed."""
    rng = np.random.default_rng(0)
    races = pd.DataFrame({
        "race_id": [f"r{i}" for i in range(len(dates))],
        "race_date": dates,
        "season": [int(race_date[:4]) for race_date in dates],
    })
    rankings = pd.concat([
        pd.DataFrame({
            "race_id": race_id,
            "rider_id": RIDER_IDS,
            "finish_rank": rng.permutation(len(RIDER_IDS)) + 1,
        })
        for race_id in races["race_id"]
    ], ignore_index=True)
    return races, rankings


def make_upcoming(dates: list[str]) -> pd.DataFrame:
    """One upcoming race per date, entered by the first 15 riders, with a page column."""
    return pd.DataFrame([
        (f"vpc-{i}-1", pd.Timestamp(race_date), rider_id, str(i))
        for i, race_date in enumerate(dates)
        for rider_id in RIDER_IDS[:15]
    ], columns=["race_id", "race_date", "rider_id", "page_id"])


OUTPUT_COLUMNS = [
    "race_id", "race_date", "rider_id", "page_id", *FEATURES, *PROBABILITY_COLUMNS, *RANK_COLUMNS
]


def test_output_is_the_chain_of_the_features_and_the_forecast():
    races, rankings = make_results(RESULT_DATES)
    entries = make_upcoming(["2024-09-01", "2024-09-08"])
    past_entries = select_forecast_entries(races, rankings, 2024, "2023-09-01")
    expected = forecast_place_probabilities(
        build_race_eve_features(races, rankings, past_entries),
        build_race_eve_features(races, rankings, entries),
    )
    pd.testing.assert_frame_equal(forecast_upcoming_entries(races, rankings, entries), expected)


def test_columns_of_the_entries_and_the_features_are_kept():
    races, rankings = make_results(RESULT_DATES)
    forecasts = forecast_upcoming_entries(races, rankings, make_upcoming(["2024-09-01"]))
    assert forecasts.columns.tolist() == OUTPUT_COLUMNS
    assert len(forecasts) == 15


def test_history_starts_window_months_before_the_earliest_race_date():
    races, rankings = make_results(RESULT_DATES)
    entries = make_upcoming(["2024-09-01"])
    assert len(forecast_upcoming_entries(races, rankings, entries, window_months=12)) == 15
    assert forecast_upcoming_entries(races, rankings, entries, window_months=1).empty


def test_no_race_in_the_window_is_logged_and_gives_an_empty_output(caplog):
    races, rankings = make_results(RESULT_DATES)
    with caplog.at_level(logging.WARNING, logger="access_it.model.upcoming"):
        forecasts = forecast_upcoming_entries(races, rankings, make_upcoming(["2026-09-01"]))
    assert "No forecast, the history cannot be selected: No race to forecast" in caplog.text
    assert forecasts.empty
    assert forecasts.columns.tolist() == OUTPUT_COLUMNS


def test_missing_race_date_in_the_results_is_logged_and_gives_an_empty_output(caplog):
    races, rankings = make_results(RESULT_DATES)
    undated = pd.DataFrame({"race_id": ["r9"], "race_date": [None], "season": [2024]})
    races = pd.concat([races, undated], ignore_index=True)
    with caplog.at_level(logging.WARNING, logger="access_it.model.upcoming"):
        forecasts = forecast_upcoming_entries(races, rankings, make_upcoming(["2024-09-01"]))
    assert "No forecast, the history cannot be selected: Missing race dates" in caplog.text
    assert forecasts.empty
    assert forecasts.columns.tolist() == OUTPUT_COLUMNS


def test_no_entry_is_logged_and_gives_an_empty_output(caplog):
    races, rankings = make_results(RESULT_DATES)
    with caplog.at_level(logging.INFO, logger="access_it.model.upcoming"):
        forecasts = forecast_upcoming_entries(races, rankings, make_upcoming([]))
    assert "No entries to forecast" in caplog.text
    assert forecasts.empty
    assert forecasts.columns.tolist() == OUTPUT_COLUMNS


@pytest.mark.parametrize("window_months, duplicate, undated, message", [
    (0, False, False, "window_months must be at least 1, not 0"),
    (12, False, True, "Missing race dates in the entries"),
    (12, True, False, "Riders entered twice in a race"),
    (0, True, True, "window_months must be at least 1, not 0"),
    (12, True, True, "Missing race dates in the entries"),
])
def test_errors_are_raised_in_order(window_months, duplicate, undated, message):
    races, rankings = make_results(RESULT_DATES)
    entries = make_upcoming(["2024-09-01"])
    if duplicate:
        entries = pd.concat([entries, entries.iloc[[0]]], ignore_index=True)
    if undated:
        entries.loc[1, "race_date"] = pd.NaT
    with pytest.raises(ValueError, match=message):
        forecast_upcoming_entries(races, rankings, entries, window_months)
