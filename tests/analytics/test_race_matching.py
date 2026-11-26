"""Unit tests of the matching of the races of the entries with the ranked races."""

import logging

import pandas as pd
import pytest

from access_it.analytics.race_matching import RACE_MATCH_COLUMNS, match_races

DAY = pd.Timestamp("2026-05-02")


def make_entries(*races: tuple[str, str, list[str]]) -> pd.DataFrame:
    """Entries of races given as (race_id, race_date, rider ids)."""
    return pd.DataFrame(
        [
            {"race_id": race_id, "race_date": race_date, "rider_id": rider_id,
             "page_id": race_id.split("-")[1], "page_title": "Page", "startlist_heading": "ACCESS"}
            for race_id, race_date, rider_ids in races
            for rider_id in rider_ids
        ],
        columns=["race_id", "race_date", "rider_id", "page_id", "page_title", "startlist_heading"],
    )


def make_results(*races: tuple[str, str, list[str]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Race and ranking tables of ranked races given as (race_id, race_date, rider ids)."""
    race_table = pd.DataFrame({
        "race_id": [race_id for race_id, _, _ in races],
        "race_date": [race_date for _, race_date, _ in races],
    })
    ranking_table = pd.DataFrame(
        [
            {"race_id": race_id, "rider_id": rider_id, "finish_rank": rank}
            for race_id, _, rider_ids in races
            for rank, rider_id in enumerate(rider_ids, start=1)
        ],
        columns=["race_id", "rider_id", "finish_rank"],
    )
    return race_table, ranking_table


def riders(prefix: str, count: int) -> list[str]:
    """Fictitious rider ids."""
    return [f"{prefix}{i}" for i in range(count)]


def day(offset: int) -> str:
    """Date of DAY shifted by a number of days."""
    return str((DAY + pd.Timedelta(days=offset)).date())


def rows(matches: pd.DataFrame) -> list[tuple]:
    """Rows of a matching result, missing values as None."""
    return [
        tuple(None if pd.isna(value) else value for value in row)
        for row in matches.itertuples(index=False)
    ]


def test_race_matched_on_the_same_day_with_its_diagnostic():
    entries = make_entries(("vpc-1-1", day(0), riders("a", 10)))
    races, rankings = make_results(
        ("f1", day(0), riders("a", 8) + riders("x", 2)),
        ("f2", day(0), riders("y", 5)),
    )
    matches = match_races(entries, races, rankings)
    assert list(matches.columns) == RACE_MATCH_COLUMNS
    assert rows(matches) == [("vpc-1-1", "f1", 8, 10, 0.8)]


def test_race_matched_with_two_ranked_races_of_the_same_day():
    entries = make_entries(("vpc-1-1", day(0), riders("a", 10)))
    races, rankings = make_results(
        ("f1", day(0), riders("a", 4)),
        ("f2", day(0), riders("a", 10)[4:] + riders("x", 2)),
    )
    assert rows(match_races(entries, races, rankings)) == [
        ("vpc-1-1", "f1", 4, 4, 1.0),
        ("vpc-1-1", "f2", 6, 8, 0.75),
    ]


def test_pair_kept_from_the_threshold_included():
    entries = make_entries(("vpc-1-1", day(0), riders("a", 10)))
    races, rankings = make_results(
        ("f1", day(0), riders("a", 5) + riders("x", 5)),
        ("f2", day(0), riders("a", 10)[5:9] + riders("y", 5)),
    )
    assert rows(match_races(entries, races, rankings)) == [("vpc-1-1", "f1", 5, 10, 0.5)]


def test_race_without_any_kept_pair_gets_a_row_without_ranked_race():
    entries = make_entries(
        ("vpc-1-1", day(0), riders("a", 10)),
        ("vpc-2-1", day(0), riders("b", 10)),
    )
    races, rankings = make_results(
        ("f1", day(0), riders("a", 10)),
        ("f2", day(0), riders("b", 2) + riders("x", 8)),
    )
    matches = match_races(entries, races, rankings)
    assert rows(matches) == [
        ("vpc-1-1", "f1", 10, 10, 1.0),
        ("vpc-2-1", None, None, None, None),
    ]


@pytest.mark.parametrize("offset, matched", [(-1, False), (1, True), (2, True), (3, False)])
def test_candidates_from_the_race_date_to_the_maximal_day_offset(offset, matched):
    entries = make_entries(("vpc-1-1", day(0), riders("a", 10)))
    races, rankings = make_results(("f1", day(offset), riders("a", 10)))
    expected = ("vpc-1-1", "f1", 10, 10, 1.0) if matched else ("vpc-1-1", None, None, None, None)
    assert rows(match_races(entries, races, rankings)) == [expected]


def test_day_of_the_highest_ranked_share_chosen_with_all_its_pairs():
    entries = make_entries(("vpc-1-1", day(0), riders("a", 20)))
    races, rankings = make_results(
        ("f1", day(0), riders("a", 6) + riders("x", 4)),
        ("f2", day(1), riders("a", 20)[10:19] + riders("y", 1)),
        ("f3", day(1), riders("a", 20)[6:10] + riders("z", 4)),
    )
    assert rows(match_races(entries, races, rankings)) == [
        ("vpc-1-1", "f2", 9, 10, 0.9),
        ("vpc-1-1", "f3", 4, 8, 0.5),
    ]


def test_earliest_day_chosen_in_case_of_a_tie():
    entries = make_entries(("vpc-1-1", day(0), riders("a", 20)))
    races, rankings = make_results(
        ("f1", day(1), riders("a", 10)),
        ("f2", day(2), riders("a", 20)[10:]),
    )
    assert rows(match_races(entries, races, rankings)) == [("vpc-1-1", "f1", 10, 10, 1.0)]


def test_ranked_race_matched_with_several_races_is_kept_and_logged(caplog):
    entries = make_entries(
        ("vpc-1-1", day(0), riders("a", 10)),
        ("vpc-2-1", day(0), riders("a", 10)),
    )
    races, rankings = make_results(("f1", day(0), riders("a", 10)))
    with caplog.at_level(logging.WARNING, logger="access_it.analytics.race_matching"):
        matches = match_races(entries, races, rankings)
    assert rows(matches) == [
        ("vpc-1-1", "f1", 10, 10, 1.0),
        ("vpc-2-1", "f1", 10, 10, 1.0),
    ]
    assert "FFC races matched with several races of the entries: ['f1']" in caplog.text


def test_race_with_several_dates_keeps_its_rows_of_the_latest_date_and_is_logged(caplog):
    entries = pd.concat([
        make_entries(("vpc-1-1", day(0), riders("a", 10))),
        make_entries(("vpc-1-1", day(7), riders("a", 10)[6:] + riders("b", 6))),
    ])
    races, rankings = make_results(
        ("f1", day(0), riders("a", 10)),
        ("f2", day(7), riders("a", 10)[4:] + riders("b", 6)),
    )
    with caplog.at_level(logging.WARNING, logger="access_it.analytics.race_matching"):
        matches = match_races(entries, races, rankings)
    assert rows(matches) == [("vpc-1-1", "f2", 10, 12, 10 / 12)]
    assert "Races with several dates in the entries, latest date kept: ['vpc-1-1']" in caplog.text

def test_empty_entries_give_an_empty_output():
    races, rankings = make_results(("f1", day(0), riders("a", 10)))
    matches = match_races(make_entries(), races, rankings)
    assert matches.empty
    assert list(matches.columns) == RACE_MATCH_COLUMNS
    assert matches.dtypes.astype(str).to_dict() == {
        "race_id": "str", "ffc_race_id": "str", "nb_common_riders": "Int64",
        "nb_ranked_riders": "Int64", "ranked_share": "float64",
    }


def test_rows_sorted_by_race_then_from_the_highest_ranked_share_then_by_ranked_race():
    entries = make_entries(
        ("vpc-1-2", day(0), riders("b", 10)),
        ("vpc-1-10", day(0), riders("c", 10)),
        ("vpc-1-1", day(0), riders("a", 12)),
    )
    races, rankings = make_results(
        ("f9", day(0), riders("b", 10)),
        ("f3", day(0), riders("a", 4)),
        ("f2", day(0), riders("a", 12)[4:8]),
        ("f1", day(0), riders("a", 12)[8:] + riders("x", 1)),
    )
    matches = match_races(entries, races, rankings)
    assert [(race_id, ffc_race_id) for race_id, ffc_race_id, *_ in rows(matches)] == [
        ("vpc-1-1", "f2"), ("vpc-1-1", "f3"), ("vpc-1-1", "f1"),
        ("vpc-1-10", None), ("vpc-1-2", "f9"),
    ]


def test_unranked_race_without_date_is_ignored():
    entries = make_entries(("vpc-1-1", day(0), riders("a", 10)))
    races, rankings = make_results(("f1", day(0), riders("a", 10)))
    races = pd.concat([races, pd.DataFrame({"race_id": ["f2"], "race_date": [None]})])
    assert rows(match_races(entries, races, rankings)) == [("vpc-1-1", "f1", 10, 10, 1.0)]


@pytest.mark.parametrize("table, message", [
    ("entries", "Missing race dates in the entries"),
    ("races", "Missing race dates in the results"),
])
def test_missing_race_dates_raise_an_error(table, message):
    tables = {"entries": make_entries(("vpc-1-1", day(0), riders("a", 10)))}
    tables["races"], tables["rankings"] = make_results(("f1", day(0), riders("a", 10)))
    tables[table] = tables[table].assign(race_date=None)
    with pytest.raises(ValueError, match=message):
        match_races(**tables)


def test_dates_of_the_entries_checked_before_those_of_the_ranked_races():
    entries = make_entries(("vpc-1-1", day(0), riders("a", 10))).assign(race_date=None)
    races, rankings = make_results(("f1", day(0), riders("a", 10)))
    with pytest.raises(ValueError, match="Missing race dates in the entries"):
        match_races(entries, races.assign(race_date=None), rankings)
