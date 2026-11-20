"""Unit tests of the evaluation of a forecast: predicted ranks, then metrics of selected races."""

import math

import pandas as pd
import pytest

from access_it.model.evaluation import (
    COMPARISON_COLUMNS, add_predicted_rank, compare_race_metrics, evaluate_forecasts,
    select_evaluated_forecasts
)
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


def test_selected_rows_keep_their_index_and_order():
    forecasts = pd.concat([race_with("r2", 21), race_with("r1", 20), race_with("r3", 22)])
    forecasts = forecasts.drop(columns="predicted_rank").assign(p_win=0.1).iloc[::-1]
    selected = select_evaluated_forecasts(forecasts, "2024-01-01", "2024-12-31")
    expected = forecasts[forecasts["race_id"].isin(["r2", "r3"])]
    pd.testing.assert_frame_equal(selected, expected)


@pytest.mark.parametrize("kwargs, message", [
    ({"start_date": None}, "Missing start date: None"),
    ({"end_date": None}, "Missing end date: None"),
    ({"start_date": "2025-01-01"}, "Start date 2025-01-01 is after end date 2024-12-31"),
    ({"months": [13]}, r"Months must be between 1 and 12, not \[13\]"),
])
def test_selection_errors_raise(kwargs, message):
    kwargs = {"start_date": "2024-01-01", "end_date": "2024-12-31", **kwargs}
    with pytest.raises(ValueError, match=message):
        select_evaluated_forecasts(race_with("r1", 21), **kwargs)


def test_comparison_of_the_races_where_both_metrics_exist():
    race_metrics = pd.DataFrame({
        "race_id": ["r1", "r2", "r3", "r4"],
        "m1": [0.5, 0.7, 0.4, 0.9],
        "m2": [1.0, 2.0, None, 5.0],
    })
    reference = pd.DataFrame({
        "race_id": ["r1", "r2", "r3", "r5"],
        "m1": [0.3, 0.4, 0.4, 0.1],
        "m2": [0.0, 0.0, 1.0, 1.0],
    })
    comparison = compare_race_metrics(race_metrics, reference, ["m1", "m2"]).set_index("metric")
    # m1: differences 0.2, 0.3, 0.0 on r1 to r3; m2: differences 1, 2 on r1 and r2
    assert comparison.loc["m1", "difference"] == pytest.approx(1 / 6)
    assert comparison.loc["m1", "std_error"] == pytest.approx(math.sqrt(7) / 30)
    assert comparison.loc["m1", "ratio"] == pytest.approx(5 / math.sqrt(7))
    assert comparison.loc["m1", "nb_races"] == 3
    assert comparison.loc["m2"].tolist() == pytest.approx([1.5, 0.5, 3.0, 2])


def test_comparison_columns_and_order_of_the_metrics():
    race_metrics = pd.DataFrame({"race_id": ["r1", "r2"], "m1": [0.5, 0.7], "m2": [1.0, 2.0]})
    comparison = compare_race_metrics(race_metrics, race_metrics, ["m2", "m1"])
    assert comparison.columns.tolist() == COMPARISON_COLUMNS
    assert comparison["metric"].tolist() == ["m2", "m1"]
    assert comparison.index.tolist() == [0, 1]


def test_comparison_with_fewer_than_two_races_or_a_null_error():
    reference = pd.DataFrame({"race_id": ["r1", "r2"], "m1": [0.5, 1.5]})
    one_race = compare_race_metrics(
        pd.DataFrame({"race_id": ["r1"], "m1": [1.0]}), reference, ["m1"]
    ).iloc[0]
    assert one_race["difference"] == 0.5
    assert math.isnan(one_race["std_error"]) and math.isnan(one_race["ratio"])
    equal = compare_race_metrics(
        pd.DataFrame({"race_id": ["r1", "r2"], "m1": [1.0, 2.0]}), reference, ["m1"]
    ).iloc[0]
    assert (equal["difference"], equal["std_error"], equal["nb_races"]) == (0.5, 0.0, 2)
    assert math.isnan(equal["ratio"])
    no_race = compare_race_metrics(
        pd.DataFrame({"race_id": ["r9"], "m1": [1.0]}), reference, ["m1"]
    ).iloc[0]
    assert math.isnan(no_race["difference"]) and no_race["nb_races"] == 0
