"""Unit tests of the selection of the races forecast and of their start lists."""

import pandas as pd
import pytest

from access_it.features.entries import COLUMNS, check_entries, select_forecast_entries

FIRST_RACE_DATE = "2023-04-01"


@pytest.fixture
def entries_of(make_tables):
    """Entries from FIRST_RACE_DATE to the season 2026 (unless given in kwargs)."""
    def compute(results: list[tuple], **kwargs) -> pd.DataFrame:
        races, rankings = make_tables(results)
        kwargs = {"last_season": 2026, "first_race_date": FIRST_RACE_DATE, **kwargs}
        return select_forecast_entries(races, rankings, **kwargs)
    return compute


def test_races_from_the_first_race_date_to_the_last_season(entries_of):
    entries = entries_of(
        [
            ("r1", "2023-03-31", "a", 1), ("r2", "2023-04-01", "a", 1),
            ("r3", "2025-10-01", "a", 1), ("r4", "2026-04-01", "a", 1),
        ],
        last_season=2025
    )
    assert entries.columns.tolist() == COLUMNS
    assert sorted(entries["race_id"]) == ["r2", "r3"]
    assert entries["race_date"].dtype == "datetime64[ns]"


def test_start_list_is_made_of_the_ranked_riders(make_tables):
    races, rankings = make_tables([
        ("r1", "2023-05-01", "a", 1), ("r1", "2023-05-01", "b", 2),
    ])
    unranked = pd.DataFrame({"race_id": ["r2"], "race_date": ["2023-05-02"], "season": [2023]})
    entries = select_forecast_entries(
        pd.concat([races, unranked], ignore_index=True), rankings, 2026, FIRST_RACE_DATE
    )
    assert entries[["race_id", "rider_id", "finish_rank"]].values.tolist() == [
        ["r1", "a", 1], ["r1", "b", 2]
    ]


@pytest.mark.parametrize("kwargs, message", [
    ({"last_season": 2022}, "Season 2022 is before the first season 2023"),
    ({"first_race_date": None}, "Missing first race date: None"),
    ({"first_race_date": "2022-12-31"}, "First race date 2022-12-31 is not in the seasons"),
    ({"first_race_date": "2027-04-01"}, "First race date 2027-04-01 is not in the seasons"),
    ({"first_race_date": "2023-06-01"}, "No race to forecast from 2023-06-01 to the season 2026"),
])
def test_invalid_arguments_raise(kwargs, message, entries_of):
    with pytest.raises(ValueError, match=message):
        entries_of([("r1", "2023-05-01", "a", 1)], **kwargs)


def test_missing_race_date_raises(make_tables, with_undated_race):
    races, rankings = make_tables([("r1", "2023-05-01", "a", 1)])
    with pytest.raises(ValueError, match="Missing race dates"):
        select_forecast_entries(with_undated_race(races), rankings, 2026, FIRST_RACE_DATE)


@pytest.mark.parametrize("undated, kwargs, message", [
    (False, {"last_season": 2022, "first_race_date": None}, "Season 2022 is before"),
    (True, {"first_race_date": None}, "Missing first race date"),
    (True, {"first_race_date": "2027-04-01"}, "First race date 2027-04-01 is not in"),
    (True, {"first_race_date": "2023-06-01"}, "Missing race dates"),
])
def test_errors_raise_in_order(undated, kwargs, message, make_tables, with_undated_race):
    races, rankings = make_tables([("r1", "2023-05-01", "a", 1)])
    if undated:
        races = with_undated_race(races)
    kwargs = {"last_season": 2026, "first_race_date": FIRST_RACE_DATE, **kwargs}
    with pytest.raises(ValueError, match=message):
        select_forecast_entries(races, rankings, **kwargs)


def test_valid_entries_pass(make_entries):
    entries = make_entries([("r1", "2026-05-01", "a"), ("r1", "2026-05-01", "b")])
    check_entries(entries.assign(category="A1"))


@pytest.mark.parametrize("rows, message", [
    ([], "No entries"),
    ([("r1", None, "a"), ("r1", "2026-05-01", "b")], "Missing race dates in the entries"),
    (
        [
            ("r2", "2026-05-01", "b"), ("r2", "2026-05-01", "b"),
            ("r1", "2026-05-01", "a"), ("r1", "2026-05-01", "a"), ("r1", "2026-05-01", "a"),
            ("r1", "2026-05-01", "c"),
        ],
        r"Riders entered twice in a race: \[\('r1', 'a'\), \('r2', 'b'\)\]",
    ),
])
def test_invalid_entries_raise(rows, message, make_entries):
    with pytest.raises(ValueError, match=message):
        check_entries(make_entries(rows))


def test_missing_race_date_raises_before_duplicates(make_entries):
    entries = make_entries([("r1", None, "a"), ("r1", None, "a")])
    with pytest.raises(ValueError, match="Missing race dates in the entries"):
        check_entries(entries)
