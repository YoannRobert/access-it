"""Unit tests of the probabilities of the riders entered in each race to reach each target."""

import logging

import numpy as np
import pandas as pd
import pytest

from access_it.features.examples import FEATURES
from access_it.model.forecasts import (
    PROBABILITY_COLUMNS, RANK_COLUMNS, forecast_place_probabilities, normalize_place_classes
)


def make_history(dates: list[str], nb_riders: int, seed: int = 0) -> pd.DataFrame:
    """One race per date, its riders ranked in the order of features drawn with a fixed seed."""
    rng = np.random.default_rng(seed)
    races = []
    for i, race_date in enumerate(dates):
        features = pd.DataFrame(rng.random((nb_riders, len(FEATURES))), columns=FEATURES)
        races.append(features.assign(
            race_id=f"r{i}",
            race_date=race_date,
            rider_id=[f"rider{j:02d}" for j in range(nb_riders)],
            finish_rank=features["mu"].rank(ascending=False, method="first").astype(int),
        ))
    return pd.concat(races, ignore_index=True)[
        ["race_id", "race_date", "rider_id", "finish_rank", *FEATURES]
    ]


HISTORY_DATES = [f"2024-{month:02d}-01" for month in range(3, 10)]


def test_normalized_classes_hold_their_numbers_of_riders():
    probabilities = np.random.default_rng(0).random((15, 5))
    normalized = normalize_place_classes(probabilities)
    assert normalized.sum(axis=1) == pytest.approx(np.ones(15))
    assert normalized.sum(axis=0) == pytest.approx([1, 2, 2, 5, 5], abs=1e-6)


def test_class_numbers_are_brought_down_in_a_small_race():
    normalized = normalize_place_classes(np.random.default_rng(0).random((4, 5)))
    assert normalized.sum(axis=0) == pytest.approx([1, 2, 1, 0, 0], abs=1e-6)
    assert (normalized[:, 3:] == 0).all()


def test_null_probabilities_are_floored():
    probabilities = np.random.default_rng(0).random((12, 5))
    probabilities[0] = 0.0
    normalized = normalize_place_classes(probabilities)
    assert np.isfinite(normalized).all()
    assert normalized.sum(axis=1) == pytest.approx(np.ones(12))
    assert normalized.sum(axis=0) == pytest.approx([1, 2, 2, 5, 2], abs=1e-6)


def test_probabilities_are_cumulative_and_sum_to_the_targets():
    history = make_history(HISTORY_DATES, 20)
    entries = make_history(["2024-10-01", "2024-10-08"], 15, seed=1)
    forecasts = forecast_place_probabilities(history, entries)
    probabilities = forecasts[PROBABILITY_COLUMNS].to_numpy()
    assert (np.diff(probabilities, axis=1) >= 0).all()
    sums = forecasts.groupby("race_id")[PROBABILITY_COLUMNS].sum().to_numpy()
    assert sums == pytest.approx(np.tile([1, 3, 5, 10], (2, 1)), abs=1e-6)


def test_ranks_follow_decreasing_probabilities_then_rider_id():
    history = make_history(HISTORY_DATES, 20)
    entries = make_history(["2024-10-01"], 15, seed=1)
    entries.loc[entries["rider_id"] == "rider01", FEATURES] = (
        entries.loc[entries["rider_id"] == "rider00", FEATURES].to_numpy()
    )
    forecasts = forecast_place_probabilities(history, entries)
    for probability, rank in zip(PROBABILITY_COLUMNS, RANK_COLUMNS):
        assert sorted(forecasts[rank]) == list(range(1, 16))
        ordered = forecasts.sort_values(rank)
        assert ordered[probability].is_monotonic_decreasing
        tied = forecasts.set_index("rider_id").loc[["rider00", "rider01"], rank]
        assert tied["rider01"] == tied["rider00"] + 1


def test_training_window_excludes_the_day_and_older_rows():
    entries = make_history(["2025-04-01"], 15, seed=1)
    same_day = make_history(["2025-04-01"], 20)
    assert forecast_place_probabilities(same_day, entries).empty
    old = make_history(["2024-03-01"], 20)
    assert forecast_place_probabilities(old, entries).empty
    assert len(forecast_place_probabilities(old, entries, window_months=14)) == 15


def test_skipped_date_is_logged_and_absent(caplog):
    history = make_history(["2024-09-01"], 20)
    entries = make_history(["2024-10-01", "2026-10-01"], 15, seed=1)
    with caplog.at_level(logging.WARNING, logger="access_it.model.forecasts"):
        forecasts = forecast_place_probabilities(history, entries)
    assert "Dates skipped, their training window lacks a place class: ['2026-10-01']" in (
        caplog.text
    )
    assert forecasts["race_date"].unique().tolist() == [pd.Timestamp("2024-10-01")]


def test_all_dates_skipped_give_an_empty_table():
    entries = make_history(["2024-10-01"], 15, seed=1).assign(category="A1")
    forecasts = forecast_place_probabilities(make_history(["2020-01-01"], 20), entries)
    assert forecasts.empty
    assert forecasts.columns.tolist() == [
        *entries.columns, *PROBABILITY_COLUMNS, *RANK_COLUMNS
    ]


def test_forecast_does_not_depend_on_the_order_of_the_history():
    # Large enough (4,000 rows) for the trees of XGBoost to change with the order of the rows
    dates = pd.date_range("2023-10-01", periods=40, freq="7D").strftime("%Y-%m-%d").tolist()
    history = make_history(dates, 100)
    entries = make_history(["2024-10-01"], 15, seed=1)
    forecasts = forecast_place_probabilities(history, entries)
    shuffled = forecast_place_probabilities(history.sample(frac=1, random_state=1), entries)
    pd.testing.assert_frame_equal(shuffled, forecasts)


def test_output_keeps_the_columns_of_the_entries():
    history = make_history(HISTORY_DATES, 20)
    entries = pd.concat([
        make_history(["2024-10-08"], 12, seed=1).assign(race_id="b"),
        make_history(["2024-10-01"], 12, seed=2).assign(race_id="c"),
        make_history(["2024-10-01"], 12, seed=3).assign(race_id="a"),
    ], ignore_index=True).assign(category="A1")
    forecasts = forecast_place_probabilities(history, entries)
    assert forecasts.columns.tolist() == [*entries.columns, *PROBABILITY_COLUMNS, *RANK_COLUMNS]
    assert forecasts["race_id"].drop_duplicates().tolist() == ["a", "c", "b"]
    assert (forecasts.groupby("race_id")["rank_win"].diff().dropna() == 1).all()
    assert forecasts.index.tolist() == list(range(36))
    assert forecasts["race_date"].dtype == "datetime64[ns]"


@pytest.mark.parametrize("kwargs, no_entry, missing_rank, message", [
    ({"window_months": 0}, False, False, "window_months must be at least 1, not 0"),
    ({}, True, False, "No entries"),
    ({}, False, True, "Missing finish ranks in the history"),
])
def test_invalid_arguments_raise(kwargs, no_entry, missing_rank, message):
    history = make_history(HISTORY_DATES, 20)
    if missing_rank:
        history.loc[0, "finish_rank"] = None
    entries = make_history(["2024-10-01"], 15, seed=1)
    if no_entry:
        entries = entries.iloc[0:0]
    with pytest.raises(ValueError, match=message):
        forecast_place_probabilities(history, entries, **kwargs)


@pytest.mark.parametrize("kwargs, missing_rank, message", [
    ({"window_months": 0}, False, "window_months must be at least 1"),
    ({}, True, "No entries"),
])
def test_errors_raise_in_order(kwargs, missing_rank, message):
    history = make_history(HISTORY_DATES, 20)
    if missing_rank:
        history.loc[0, "finish_rank"] = None
    with pytest.raises(ValueError, match=message):
        forecast_place_probabilities(history, history.iloc[0:0], **kwargs)
