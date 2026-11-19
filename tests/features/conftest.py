"""Shared fixtures of the unit tests of the features layer."""

from collections.abc import Callable

import pandas as pd
import pytest


@pytest.fixture
def make_tables() -> Callable[[list[tuple]], tuple[pd.DataFrame, pd.DataFrame]]:
    """Builder of the race and ranking tables from (race_id, race_date, rider_id, finish_rank)."""
    def build(results: list[tuple]) -> tuple[pd.DataFrame, pd.DataFrame]:
        df = pd.DataFrame(results, columns=["race_id", "race_date", "rider_id", "finish_rank"])
        races = df[["race_id", "race_date"]].drop_duplicates().assign(
            season=lambda d: pd.to_datetime(d["race_date"]).dt.year
        )
        return races, df[["race_id", "rider_id", "finish_rank"]]
    return build


@pytest.fixture
def with_undated_race() -> Callable[[pd.DataFrame], pd.DataFrame]:
    """Adder of a race of 2023 without date to a race table."""
    def add(races: pd.DataFrame) -> pd.DataFrame:
        undated = pd.DataFrame({"race_id": ["r0"], "race_date": [None], "season": [2023]})
        return pd.concat([races, undated], ignore_index=True)
    return add
