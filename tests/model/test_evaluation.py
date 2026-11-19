"""Unit tests of the evaluation of a forecast: predicted ranks, then metrics of selected races."""

import pandas as pd
import pytest

from access_it.model.evaluation import add_predicted_rank, evaluate_forecasts
from access_it.model.metrics import compute_race_metrics


def race_with(race_id: str, nb_riders: int, race_date: str = "2024-05-01") -> pd.DataFrame:
    """Forecast of a race whose riders are predicted in their finishing order."""
    return pd.DataFrame({
        "race_id": race_id,
        "race_date": race_date,
        "rider_id": [f"{race_id}-{i:02d}" for i in range(1, nb_riders + 1)],
        "finish_rank": range(1, nb_riders + 1),
        "predicted_rank": range(1, nb_riders + 1),
    })


def evaluated_race_ids(forecasts: pd.DataFrame, **kwargs) -> list[str]:
    """Races evaluated in 2024 (unless the dates are given in kwargs)."""
    kwargs = {"start_date": "2024-01-01", "end_date": "2024-12-31", **kwargs}
    return evaluate_forecasts(forecasts, **kwargs)["race_id"].tolist()


def test_predicted_rank_by_decreasing_score_then_rider_id():
    forecasts = pd.DataFrame({
        "race_id": ["r1"] * 4,
        "race_date": "2024-05-01",
        "rider_id": ["d", "c", "b", "a"],
        "score": [1.0, 3.0, 2.0, 2.0],
    })
    ranked = add_predicted_rank(forecasts, "score")
    assert ranked[["rider_id", "predicted_rank"]].values.tolist() == [
        ["c", 1], ["a", 2], ["b", 3], ["d", 4]
    ]


def test_predicted_rank_output_sorted_copy_with_the_rank_replaced():
    forecasts = pd.DataFrame({
        "race_id": ["r2", "r2", "r1"],
        "race_date": ["2024-05-02", "2024-05-02", "2024-05-01"],
        "rider_id": ["a", "b", "c"],
        "score": [1.0, 2.0, 1.0],
        "predicted_rank": [9, 9, 9],
    }, index=[5, 6, 7])
    original = forecasts.copy()
    ranked = add_predicted_rank(forecasts, "score")
    assert ranked[["race_id", "rider_id", "predicted_rank"]].values.tolist() == [
        ["r1", "c", 1], ["r2", "b", 1], ["r2", "a", 2]
    ]
    assert ranked.index.tolist() == [0, 1, 2]
    pd.testing.assert_frame_equal(forecasts, original)


def test_missing_score_raises():
    forecasts = pd.DataFrame({
        "race_id": ["r1", "r1"], "race_date": "2024-05-01", "rider_id": ["a", "b"],
        "score": [1.0, None],
    })
    with pytest.raises(ValueError, match="Missing scores in the forecasts"):
        add_predicted_rank(forecasts, "score")


def test_races_of_more_than_20_ranked_riders_evaluated():
    forecasts = pd.concat([race_with("r1", 21), race_with("r2", 20)], ignore_index=True)
    assert evaluated_race_ids(forecasts) == ["r1"]


def test_races_between_the_dates_included_evaluated():
    forecasts = pd.concat([
        race_with("r1", 21, "2023-12-31"), race_with("r2", 21, "2024-01-01"),
        race_with("r3", 21, "2024-12-31"), race_with("r4", 21, "2025-01-01"),
    ], ignore_index=True)
    assert evaluated_race_ids(forecasts) == ["r2", "r3"]


def test_races_of_the_given_months_evaluated():
    forecasts = pd.concat([
        race_with("r1", 21, "2024-02-10"), race_with("r2", 21, "2024-03-10"),
        race_with("r3", 21, "2024-04-10"),
    ], ignore_index=True)
    assert evaluated_race_ids(forecasts, months=[2, 3]) == ["r1", "r2"]


def test_metrics_of_the_races_evaluated():
    forecasts = pd.concat([race_with("r1", 21), race_with("r2", 20)], ignore_index=True)
    expected = compute_race_metrics(forecasts[forecasts["race_id"] == "r1"])
    pd.testing.assert_frame_equal(
        evaluate_forecasts(forecasts, "2024-01-01", "2024-12-31"), expected
    )


@pytest.mark.parametrize("kwargs, message", [
    ({"start_date": None}, "Missing start date: None"),
    ({"end_date": None}, "Missing end date: None"),
    ({"start_date": "2025-01-01"}, "Start date 2025-01-01 is after end date 2024-12-31"),
    ({"months": [0, 3]}, r"Months must be between 1 and 12, not \[0, 3\]"),
    ({"months": [13]}, r"Months must be between 1 and 12, not \[13\]"),
])
def test_invalid_arguments_raise(kwargs, message):
    with pytest.raises(ValueError, match=message):
        evaluated_race_ids(race_with("r1", 21), **kwargs)


def test_invalid_predicted_ranks_raise():
    forecasts = race_with("r1", 21).assign(predicted_rank=1)
    with pytest.raises(ValueError, match="Races whose predicted ranks are not 1"):
        evaluated_race_ids(forecasts)


@pytest.mark.parametrize("kwargs, message", [
    ({"start_date": None, "end_date": None}, "Missing start date"),
    ({"end_date": None, "months": [0]}, "Missing end date"),
    ({"start_date": "2025-01-01", "months": [0]}, "Start date 2025-01-01 is after"),
    ({"months": [0]}, "Months must be between 1 and 12"),
])
def test_errors_raise_in_order(kwargs, message):
    forecasts = race_with("r1", 21).assign(predicted_rank=1)
    with pytest.raises(ValueError, match=message):
        evaluated_race_ids(forecasts, **kwargs)
