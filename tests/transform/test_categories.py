"""Unit tests of the category history functions."""

import logging
import pandas as pd

from access_it.etl.transform.categories import (
    add_unknown_years_in_category_history, advance_start_dates_in_category_history,
    delete_rows_for_riders_having_duplicated_keys, remove_conflicting_observations,
    search_rider_category
)


def history(*rows: tuple[str, str, int | None]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"rider_id": r, "start_date": pd.Timestamp(d), "rider_category": c} for r, d, c in rows]
    )


def test_riders_with_duplicated_keys_get_an_unknown_category(caplog):
    caplog.set_level(logging.INFO)
    df = history(
        ("r1", "2023-01-01", 1), ("r1", "2023-06-21", 3), ("r1", "2023-06-21", 1),
        ("r2", "2024-01-01", 2),
    )
    result = delete_rows_for_riders_having_duplicated_keys(df).reset_index(drop=True)
    assert result.to_dict(orient="records") == [
        {"rider_id": "r1", "start_date": pd.Timestamp("2023-01-01"), "rider_category": None},
        {"rider_id": "r2", "start_date": pd.Timestamp("2024-01-01"), "rider_category": 2},
    ]
    output = caplog.text
    assert "for 1 rider(s) with duplicated keys" in output
    assert "  r1: 2023-06-21" in output


def test_no_duplicated_keys_prints_nothing(caplog):
    caplog.set_level(logging.INFO)
    df = history(("r1", "2023-01-01", 1), ("r1", "2024-01-01", 2))
    result = delete_rows_for_riders_having_duplicated_keys(df)
    assert len(result) == 2
    assert caplog.records == []


# ---------------------------------------------------------------- advance_start_dates_in_category_history

def advanced(df: pd.DataFrame, *observations: tuple[str, str, int]) -> list[tuple]:
    """History after the move of the start dates, as (rider, date, category) tuples."""
    category_at_given_times = pd.DataFrame(
        [{"rider_id": r, "race_date": pd.Timestamp(d), "rider_category": c} for r, d, c in observations]
    )
    result = advance_start_dates_in_category_history(df, category_at_given_times)
    return [(row.rider_id, str(row.start_date.date()), row.rider_category) for row in result.itertuples()]


def test_change_of_category_between_two_seasons_starts_on_january_1st():
    df = history(("r1", "2025-04-06", 3), ("r1", "2026-04-12", 2))
    assert advanced(
        df, ("r1", "2025-04-06", 3), ("r1", "2025-09-28", 3), ("r1", "2026-04-12", 2), ("r1", "2026-06-07", 2)
    ) == [("r1", "2025-01-01", 3), ("r1", "2026-01-01", 2)]


def test_change_of_category_during_the_season_keeps_its_start_date():
    df = history(("r1", "2025-04-06", 3), ("r1", "2026-06-07", 2))
    assert advanced(
        df, ("r1", "2025-04-06", 3), ("r1", "2026-03-08", 3), ("r1", "2026-05-30", 3), ("r1", "2026-06-07", 2)
    ) == [("r1", "2025-01-01", 3), ("r1", "2026-06-07", 2)]


def test_second_period_starting_the_same_day_keeps_its_start_date():
    df = history(("r1", "2025-04-06", 3), ("r1", "2025-04-06", 2))
    assert advanced(df, ("r1", "2025-04-06", 3), ("r1", "2025-04-06", 2)) == [
        ("r1", "2025-01-01", 3), ("r1", "2025-04-06", 2)
    ]


def test_first_period_of_a_rider_starts_on_january_1st():
    df = history(("r1", "2023-05-01", 4), ("r2", "2024-03-03", 1), ("r2", "2024-07-14", 2))
    assert advanced(
        df, ("r1", "2023-05-01", 4), ("r2", "2024-03-03", 1), ("r2", "2024-07-14", 2)
    ) == [("r1", "2023-01-01", 4), ("r2", "2024-01-01", 1), ("r2", "2024-07-14", 2)]


# ---------------------------------------------------------------- add_unknown_years_in_category_history

def completed(df: pd.DataFrame, race_dates: list[str], current_year: int) -> list[tuple]:
    """History of rider r1 completed for his races on `race_dates`, as (date, category) tuples."""
    races = pd.DataFrame({
        "race_id": [f"race{k}" for k in range(len(race_dates))], "race_date": race_dates
    })
    rankings = pd.DataFrame({"race_id": races["race_id"], "rider_id": "r1", "finish_rank": 1})
    startlists = pd.DataFrame({"rider_id": pd.Series(dtype=str), "race_date": pd.Series(dtype=str)})
    result = add_unknown_years_in_category_history(
        df, races, rankings, startlists, after_year=2025, current_year=current_year
    )
    return [
        (str(row.start_date.date()), None if pd.isna(row.rider_category) else row.rider_category)
        for row in result.itertuples()
    ]


def test_no_unknown_category_for_the_current_year_without_race_yet():
    df = history(("r1", "2025-01-01", 2))
    assert completed(df, ["2025-05-01"], current_year=2026) == [("2025-01-01", 2)]


def test_unknown_category_once_the_year_without_race_is_over():
    df = history(("r1", "2025-01-01", 2))
    assert completed(df, ["2025-05-01"], current_year=2027) == [
        ("2025-01-01", 2), ("2026-01-01", None)
    ]


def test_rider_back_after_a_year_without_race_gets_his_last_category():
    df = history(("r1", "2025-01-01", 2), ("r1", "2027-03-01", 2))
    assert completed(df, ["2025-05-01", "2027-03-01"], current_year=2027) == [
        ("2025-01-01", 2), ("2026-01-01", None), ("2027-03-01", 2)
    ]


def test_rider_back_after_a_year_without_race_keeps_his_category_until_a_change_during_the_season():
    df = history(("r1", "2025-01-01", 3), ("r1", "2027-06-07", 2))
    assert completed(df, ["2025-05-01", "2027-03-01", "2027-06-07"], current_year=2027) == [
        ("2025-01-01", 3), ("2026-01-01", None), ("2027-01-01", 3), ("2027-06-07", 2)
    ]


# ---------------------------------------------------------------- remove_conflicting_observations

def observations(*rows: tuple[str, str, str]) -> pd.DataFrame:
    """Observations from (rider, date, categories) tuples."""
    df = pd.DataFrame(
        [{"rider_id": r, "race_date": pd.Timestamp(d), "categories": c} for r, d, c in rows]
    )
    df["race_hc"] = df["categories"].str.replace("A", "").str.split(",").str[0].astype(int)
    df["race_lc"] = df["categories"].str.replace("A", "").str.split(",").str[-1].astype(int)
    return df


def kept(df: pd.DataFrame) -> list[tuple]:
    return [
        (row.rider_id, str(row.race_date.date()), row.categories)
        for row in remove_conflicting_observations(df).itertuples()
    ]


def test_rankings_of_disjoint_categories_on_the_same_day_are_removed(caplog):
    caplog.set_level(logging.INFO)
    df = observations(
        ("r1", "2024-02-25", "A1,A2"), ("r1", "2024-03-03", "A1,A2"), ("r1", "2024-03-03", "A3,A4"),
        ("r2", "2024-03-03", "A3,A4"),
    )
    assert kept(df) == [("r1", "2024-02-25", "A1,A2"), ("r2", "2024-03-03", "A3,A4")]
    assert "for 1 rider(s) and day(s) with conflicting categories" in caplog.text
    assert "  r1, 2024-03-03: A1,A2 / A3,A4" in caplog.text


def test_startlist_category_outside_the_race_categories_is_removed():
    df = observations(("r1", "2026-08-30", "A3"), ("r1", "2026-08-30", "A1,A2"))
    assert kept(df) == []


def test_compatible_observations_on_the_same_day_are_kept(caplog):
    caplog.set_level(logging.INFO)
    df = observations(("r1", "2026-08-30", "A2"), ("r1", "2026-08-30", "A1,A2"))
    assert kept(df) == [("r1", "2026-08-30", "A2"), ("r1", "2026-08-30", "A1,A2")]
    assert caplog.records == []


def test_category_of_a_conflicting_day_is_filled_from_the_other_races():
    races = pd.DataFrame({
        "race_id": ["a", "b", "c", "d"],
        "categories": ["A1,A2", "A1,A2", "A3,A4", "A1"],
        "race_date": ["2024-02-25", "2024-03-03", "2024-03-03", "2024-04-07"],
    })
    rankings = pd.DataFrame({"race_id": ["a", "b", "c", "d"], "rider_id": "r1", "finish_rank": 30})
    startlists = pd.DataFrame(columns=["rider_id", "race_date", "category"])
    result = search_rider_category(races, rankings, startlists)
    assert result["race_date"].dt.strftime("%Y-%m-%d").tolist() == ["2024-02-25", "2024-04-07"]
    assert result["rider_category"].tolist() == [1, 1]
