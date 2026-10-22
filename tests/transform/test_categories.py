"""Unit tests of the category history functions."""

import pandas as pd

from access_it.etl.transform.categories import (
    add_unknown_years_in_category_history, delete_rows_for_riders_having_duplicated_keys
)


def history(*rows: tuple[str, str, int | None]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"rider_id": r, "start_date": pd.Timestamp(d), "rider_category": c} for r, d, c in rows]
    )


def test_riders_with_duplicated_keys_get_an_unknown_category(capsys):
    df = history(
        ("r1", "2023-01-01", 1), ("r1", "2023-06-21", 3), ("r1", "2023-06-21", 1),
        ("r2", "2024-01-01", 2),
    )
    result = delete_rows_for_riders_having_duplicated_keys(df).reset_index(drop=True)
    assert result.to_dict(orient="records") == [
        {"rider_id": "r1", "start_date": pd.Timestamp("2023-01-01"), "rider_category": None},
        {"rider_id": "r2", "start_date": pd.Timestamp("2024-01-01"), "rider_category": 2},
    ]
    output = capsys.readouterr().out
    assert "for 1 rider(s) with duplicated keys" in output
    assert "  r1: 2023-06-21" in output


def test_no_duplicated_keys_prints_nothing(capsys):
    df = history(("r1", "2023-01-01", 1), ("r1", "2024-01-01", 2))
    result = delete_rows_for_riders_having_duplicated_keys(df)
    assert len(result) == 2
    assert capsys.readouterr().out == ""


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
