"""Unit tests of the features of the riders entered in each race, on the eve of the race."""

import pandas as pd
import pytest

from access_it.features.examples import FEATURES, MISSING_PLACE, build_race_eve_features
from access_it.features.ratings import rate_entries_on_race_eve


def features_of(features: pd.DataFrame, race_id: str, rider_id: str) -> dict:
    """Features of a rider entered in a race."""
    row = features[(features["race_id"] == race_id) & (features["rider_id"] == rider_id)]
    return row[FEATURES].iloc[0].to_dict()


def test_recent_form_counts_the_previous_races_only(make_tables, make_entries):
    races, rankings = make_tables([
        ("r1", "2023-04-01", "a", 3), ("r1", "2023-04-01", "b", 3),
        ("r2", "2023-04-10", "a", 21),
        ("r3", "2023-05-01", "a", 1),
        ("r4", "2023-05-01", "a", 2),
    ])
    features = build_race_eve_features(
        races, rankings, make_entries([("r4", "2023-05-01", "a"), ("r4", "2023-05-01", "b")])
    )
    a = features_of(features, "r4", "a")
    assert (a["nb_races_used"], a["nb_top_n"], a["top_n_rate"]) == (2, 1, 0.5)
    b = features_of(features, "r4", "b")
    assert (b["nb_races_used"], b["nb_top_n"], b["top_n_rate"]) == (1, 1, 1.0)


def test_places_are_the_best_and_mean_finish_ranks_of_the_same_races(make_tables, make_entries):
    races, rankings = make_tables([
        ("r1", "2023-04-01", "a", 23),
        ("r2", "2023-04-10", "a", 8),
    ])
    features = build_race_eve_features(races, rankings, make_entries([("f1", "2023-05-01", "a")]))
    a = features_of(features, "f1", "a")
    assert (a["best_place"], a["mean_place"]) == (8.0, 15.5)


def test_rider_without_recent_result_gets_zero_form_and_missing_places(make_tables, make_entries):
    races, rankings = make_tables([("r1", "2023-04-01", "a", 1)])
    features = build_race_eve_features(races, rankings, make_entries([("f1", "2023-05-01", "z")]))
    z = features_of(features, "f1", "z")
    assert (z["nb_races_used"], z["nb_top_n"], z["top_n_rate"]) == (0, 0, 0.0)
    assert (z["best_place"], z["mean_place"]) == (MISSING_PLACE, MISSING_PLACE)


def test_ratings_are_those_on_the_eve_of_the_race(make_tables, make_entries):
    races, rankings = make_tables([
        ("r1", "2023-04-01", "a", 1), ("r1", "2023-04-01", "b", 2),
        ("r2", "2023-05-01", "b", 1), ("r2", "2023-05-01", "a", 2),
    ])
    entries = make_entries([("r2", "2023-05-01", "a"), ("r2", "2023-05-01", "b")])
    features = build_race_eve_features(races, rankings, entries)
    ratings = rate_entries_on_race_eve(races, rankings, entries)
    pd.testing.assert_frame_equal(features[["mu", "sigma"]], ratings[["mu", "sigma"]])


def test_last_races_and_window_months_limit_the_results_used(make_tables, make_entries):
    races, rankings = make_tables([
        ("r1", "2023-03-15", "a", 2),
        ("r2", "2023-04-20", "a", 30),
    ])
    entries = make_entries([("f1", "2023-05-01", "a")])
    last_race = features_of(
        build_race_eve_features(races, rankings, entries, last_races=1), "f1", "a"
    )
    assert (last_race["nb_races_used"], last_race["best_place"]) == (1, 30.0)
    last_month = features_of(
        build_race_eve_features(races, rankings, entries, window_months=1), "f1", "a"
    )
    assert (last_month["nb_races_used"], last_month["mean_place"]) == (1, 30.0)


def test_entries_of_a_coming_race_get_their_features(make_tables, make_entries):
    races, rankings = make_tables([("r1", "2023-04-01", "a", 1), ("r1", "2023-04-01", "b", 2)])
    features = build_race_eve_features(
        races, rankings, make_entries([("f1", "2023-06-01", "a"), ("f1", "2023-06-01", "z")])
    )
    a = features_of(features, "f1", "a")
    assert (a["nb_races_used"], a["nb_top_n"], a["best_place"]) == (1, 1, 1.0)
    assert a["mu"] > 25.0
    z = features_of(features, "f1", "z")
    assert (z["nb_races_used"], z["best_place"], z["mu"]) == (0, MISSING_PLACE, 25.0)


def test_output_keeps_the_columns_of_the_entries_then_the_features(make_tables, make_entries):
    races, rankings = make_tables([("r1", "2023-04-01", "a", 1), ("r1", "2023-04-01", "b", 2)])
    entries = make_entries([
        ("f2", "2023-06-01", "b"), ("f1", "2023-06-01", "b"), ("f1", "2023-06-01", "a"),
    ]).assign(category="A1")
    features = build_race_eve_features(races, rankings, entries)
    assert features.columns.tolist() == ["race_id", "race_date", "rider_id", "category", *FEATURES]
    assert features[["race_id", "rider_id"]].values.tolist() == [
        ["f1", "a"], ["f1", "b"], ["f2", "b"]
    ]
    assert features.index.tolist() == [0, 1, 2]
    assert features["race_date"].dtype == "datetime64[ns]"
    assert features[["nb_races_used", "nb_top_n"]].dtypes.tolist() == ["int64", "int64"]
    assert features[FEATURES[2:]].dtypes.tolist() == ["float64"] * 5


@pytest.mark.parametrize("rows, kwargs, message", [
    ([("f1", "2023-05-01", "a")], {"top_n": 0}, "top_n must be between 1 and 20, not 0"),
    ([("f1", "2023-05-01", "a")], {"last_races": 0}, "last_races must be at least 1, not 0"),
    ([("f1", "2023-05-01", "a")], {"window_months": 0}, "window_months must be at least 1, not 0"),
    ([], {}, "No entries"),
])
def test_invalid_arguments_raise(rows, kwargs, message, make_tables, make_entries):
    races, rankings = make_tables([("r1", "2023-04-01", "a", 1)])
    with pytest.raises(ValueError, match=message):
        build_race_eve_features(races, rankings, make_entries(rows), **kwargs)


@pytest.mark.parametrize("rows, undated, kwargs, message", [
    ([], False, {"top_n": 0}, "top_n must be between"),
    ([], True, {}, "No entries"),
    (
        [("f1", "2023-05-01", "a"), ("f1", "2023-05-01", "a")], True, {},
        "Riders entered twice in a race",
    ),
])
def test_errors_raise_in_order(
        rows, undated, kwargs, message, make_tables, make_entries, with_undated_race
    ):
    races, rankings = make_tables([("r1", "2023-04-01", "a", 1)])
    if undated:
        races = with_undated_race(races)
    with pytest.raises(ValueError, match=message):
        build_race_eve_features(races, rankings, make_entries(rows), **kwargs)
