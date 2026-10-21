"""Unit tests of the category history functions."""

import pandas as pd

from access_it.etl.transform.categories import delete_rows_for_riders_having_duplicated_keys


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
