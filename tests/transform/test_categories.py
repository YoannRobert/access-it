"""Unit tests of the category history functions."""

import logging
import pandas as pd

from access_it.etl.transform.categories import (
    add_unknown_years_in_category_history, advance_start_dates_in_category_history,
    delete_rows_for_riders_having_duplicated_keys
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
