"""Unit tests of the forecasts of the races for the choice of a date and a race."""

import pandas as pd
import pytest

from access_it.analytics.forecast_list import (
    DAY_RACE_COLUMNS,
    RACE_ENTRY_COLUMNS,
    RACE_RUN_COLUMNS,
    clean_page_title,
    get_default_forecast_date,
    get_race_entries,
    list_day_races,
    list_forecast_dates,
    select_race_runs,
)

ENTRIES_COLUMNS = [
    "race_id", "race_date", "rider_id", "page_id", "page_title", "startlist_heading", "run_time"
]
RUN_1 = pd.Timestamp("2026-03-06 19:30", tz="UTC")
RUN_2 = pd.Timestamp("2026-03-11 19:30", tz="UTC")

RIDER_LIST = pd.DataFrame({
    "last_name": ["MARTIN", "DUPONT", "DUPONT"],
    "first_name": ["Paul", "Luc", "Jean"],
    "category": ["A2", "A3", "A2"],
    "club": ["Club A", "Club B", "Club A"],
    "departement_code": ["44", "85", "44"],
    "departement_name": ["Loire-Atlantique", "Vendée", "Loire-Atlantique"],
    "region": ["PAYS DE LA LOIRE"] * 3,
    "club_id": ["c1", "c2", "c1"],
    "rider_id": ["r1", "r2", "r3"],
})


def make_entries(race_id: str, race_date: str, run_time: pd.Timestamp, page_title: str = "Race",
                 rider_ids: tuple[str, ...] = ("r1", "r2", "r3")) -> pd.DataFrame:
    """Entries of a race in a run, the riders being listed in the given order."""
    return pd.DataFrame({
        "race_id": race_id,
        "race_date": pd.Timestamp(race_date),
        "rider_id": list(rider_ids),
        "page_id": race_id.split("-")[1],
        "page_title": page_title,
        "startlist_heading": "A1-A2",
        "run_time": run_time,
    })


def make_forecasts(entries: pd.DataFrame) -> pd.DataFrame:
    """Forecasts of entries: the first rider listed is the favourite."""
    nb_riders = len(entries)
    p_win = [0.5 / (rank + 1) for rank in range(nb_riders)]
    return entries.assign(
        nb_races_used=10, nb_top_n=3, top_n_rate=0.3, mu=25.0, sigma=8.0, best_place=2,
        mean_place=12.0, p_win=p_win, p_podium=0.6, p_top5=0.7, p_top10=0.9,
        rank_win=range(1, nb_riders + 1), rank_podium=1, rank_top5=1, rank_top10=1,
    )


def no_entries() -> pd.DataFrame:
    """Empty table of entries."""
    return pd.DataFrame(columns=ENTRIES_COLUMNS)


# select_race_runs

def test_the_most_recent_run_forecasting_a_race_is_kept():
    old = make_entries("vpc-1-1", "2026-03-15", RUN_1)
    new = make_entries("vpc-1-1", "2026-03-15", RUN_2, rider_ids=("r2", "r1"))
    race_runs = select_race_runs(
        pd.concat([make_forecasts(old), make_forecasts(new)]), pd.concat([old, new])
    )
    assert race_runs["run_time"].eq(RUN_2).all()
    assert race_runs["rider_id"].tolist() == ["r2", "r1"]
    assert race_runs["has_forecast"].all()


def test_an_older_forecast_is_kept_when_the_latest_run_has_no_forecast_of_the_race():
    old = make_entries("vpc-1-1", "2026-03-15", RUN_1)
    new = make_entries("vpc-1-1", "2026-03-15", RUN_2, rider_ids=("r1",))
    race_runs = select_race_runs(make_forecasts(old), pd.concat([old, new]))
    assert race_runs["run_time"].eq(RUN_1).all()
    assert race_runs["has_forecast"].all()
    assert len(race_runs) == 3


def test_a_race_without_forecast_comes_from_the_latest_run_of_its_entries():
    old = make_entries("vpc-2-1", "2026-03-15", RUN_1)
    new = make_entries("vpc-2-1", "2026-03-15", RUN_2, rider_ids=("r1", "r3"))
    race_runs = select_race_runs(make_forecasts(old.iloc[:0]), pd.concat([old, new]))
    assert race_runs["run_time"].eq(RUN_2).all()
    assert not race_runs["has_forecast"].any()
    assert race_runs["p_win"].isna().all()
    assert race_runs["rider_id"].tolist() == ["r1", "r3"]


def test_the_race_runs_have_their_columns_and_are_sorted():
    sunday = make_entries("vpc-1-1", "2026-03-15", RUN_1, rider_ids=("r3", "r1"))
    saturday = make_entries("vpc-2-1", "2026-03-14", RUN_1)
    without_forecast = make_entries("vpc-3-1", "2026-03-14", RUN_1)
    race_runs = select_race_runs(
        pd.concat([make_forecasts(sunday), make_forecasts(saturday)]),
        pd.concat([sunday, saturday, without_forecast]),
    )
    assert race_runs.columns.tolist() == RACE_RUN_COLUMNS
    assert race_runs["race_date"].dtype == "datetime64[ns]"
    assert list(zip(race_runs["race_id"], race_runs["rider_id"])) == [
        ("vpc-2-1", "r1"), ("vpc-2-1", "r2"), ("vpc-2-1", "r3"),
        ("vpc-3-1", "r1"), ("vpc-3-1", "r2"), ("vpc-3-1", "r3"),
        ("vpc-1-1", "r3"), ("vpc-1-1", "r1"),
    ]


def test_empty_tables_give_no_race_run():
    race_runs = select_race_runs(make_forecasts(no_entries()), no_entries())
    assert race_runs.empty
    assert race_runs.columns.tolist() == RACE_RUN_COLUMNS


# list_forecast_dates

def test_only_the_dates_with_a_forecast_race_are_listed_once_in_order():
    sunday = make_entries("vpc-1-1", "2026-03-15", RUN_1)
    saturday = make_entries("vpc-2-1", "2026-03-14", RUN_1)
    second_sunday_race = make_entries("vpc-3-1", "2026-03-15", RUN_1)
    without_forecast = make_entries("vpc-4-1", "2026-03-21", RUN_1)
    race_runs = select_race_runs(
        pd.concat([make_forecasts(sunday), make_forecasts(saturday),
                   make_forecasts(second_sunday_race)]),
        pd.concat([sunday, saturday, second_sunday_race, without_forecast]),
    )
    assert list_forecast_dates(race_runs) == [
        pd.Timestamp("2026-03-14"), pd.Timestamp("2026-03-15")
    ]


# get_default_forecast_date

DATES = [pd.Timestamp("2026-03-14"), pd.Timestamp("2026-03-15"), pd.Timestamp("2026-03-22")]


@pytest.mark.parametrize("today, expected", [
    ("2026-03-15", "2026-03-15"),
    ("2026-03-16", "2026-03-22"),
    ("2026-11-26", "2026-03-22"),
], ids=["race_day", "between_two_dates", "after_all_dates"])
def test_the_default_date_is_the_first_from_today_or_else_the_last(today, expected):
    assert get_default_forecast_date(DATES, today) == pd.Timestamp(expected)


def test_no_date_gives_no_default_date():
    assert get_default_forecast_date([], "2026-11-26") is None


# list_day_races

def test_the_races_of_a_day_are_sorted_by_title_then_table_rank():
    races = [
        make_entries("vpc-7-10", "2026-03-15", RUN_1, page_title="Grand Prix B"),
        make_entries("vpc-7-2", "2026-03-15", RUN_1, page_title="Grand Prix B"),
        make_entries("vpc-9-1", "2026-03-15", RUN_1, page_title="Grand Prix A"),
        make_entries("vpc-8-1", "2026-03-14", RUN_1, page_title="Other day"),
    ]
    race_runs = select_race_runs(make_forecasts(races[0]), pd.concat(races))
    day_races = list_day_races(race_runs, "2026-03-15")
    assert day_races.columns.tolist() == DAY_RACE_COLUMNS
    assert day_races["race_id"].tolist() == ["vpc-9-1", "vpc-7-2", "vpc-7-10"]
    assert day_races["has_forecast"].tolist() == [False, False, True]


@pytest.mark.parametrize("title, expected", [
    ("Andrezé 12 septembre 2026 engagés de courses cyclistes", "Andrezé 12 septembre 2026"),
    ("Avessac 1er mai 2026 les engagés de courses cyclistes", "Avessac 1er mai 2026"),
    ("Maumusson 5 juillet 2026 Engagés de courses cyclistes", "Maumusson 5 juillet 2026"),
    ("Plouigneau 18 avril 2026 les engagées de courses cyclistes", "Plouigneau 18 avril 2026"),
    ("Baud 11 juillet 2026 engagés de criterium", "Baud 11 juillet 2026"),
    ("Beaupréau Challenge des Mauges 27 septembre 2026 engagés",
     "Beaupréau Challenge des Mauges 27 septembre 2026"),
    ("Bonnétable Les 2 Jours Cyclistes Du Comice 28 et 29 août 2026 engagés",
     "Bonnétable Les 2 Jours Cyclistes Du Comice 28 et 29 août 2026"),
    ("Grand Prix A", "Grand Prix A"),
])
def test_page_title_loses_the_mention_of_the_entries(title, expected):
    assert clean_page_title(title) == expected


def test_the_races_of_a_day_are_sorted_by_their_cleaned_title():
    # By raw title, "Vay 15 mars 2026 Grand Prix" would come first
    races = [
        make_entries("vpc-1-1", "2026-03-15", RUN_1, page_title="Vay 15 mars 2026 Grand Prix"),
        make_entries("vpc-2-1", "2026-03-15", RUN_1, page_title="Vay 15 mars 2026 les engagés"),
    ]
    race_runs = select_race_runs(make_forecasts(races[0]), pd.concat(races))
    day_races = list_day_races(race_runs, "2026-03-15")
    assert day_races["page_title"].tolist() == ["Vay 15 mars 2026", "Vay 15 mars 2026 Grand Prix"]


# get_race_entries

def test_the_riders_of_a_forecast_race_are_sorted_by_rank_with_their_names():
    entries = make_entries("vpc-1-1", "2026-03-15", RUN_1, rider_ids=("r3", "r1", "r2"))
    race_runs = select_race_runs(make_forecasts(entries), entries)
    race_entries = get_race_entries(race_runs, "vpc-1-1", RIDER_LIST)
    assert race_entries.columns.tolist() == RACE_ENTRY_COLUMNS
    assert race_entries["rank_win"].tolist() == [1, 2, 3]
    assert race_entries["rider_id"].tolist() == ["r3", "r1", "r2"]
    assert race_entries["club"].tolist() == ["Club A", "Club A", "Club B"]


def test_the_riders_of_a_race_without_forecast_are_sorted_by_name():
    entries = make_entries("vpc-1-1", "2026-03-15", RUN_1)
    race_runs = select_race_runs(make_forecasts(no_entries()), entries)
    race_entries = get_race_entries(race_runs, "vpc-1-1", RIDER_LIST)
    assert race_entries["rider_id"].tolist() == ["r3", "r2", "r1"]
    assert race_entries["p_win"].isna().all()
    with pytest.raises(ValueError, match="Unknown race: 'vpc-0-1'"):
        get_race_entries(race_runs, "vpc-0-1", RIDER_LIST)
