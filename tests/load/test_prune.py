"""Unit tests of the deletion of stale riders (in-memory SQLite database)."""

from datetime import date

import pandas as pd
import pytest

from sqlalchemy import create_engine, insert, select

from access_it.etl.load.models import Base
from access_it.etl.load.prune import (
    TooManyStaleRiders, format_report, prune_stale_riders, tables_referring_to_riders
)

TABLES = Base.metadata.tables
DAY = date(2025, 4, 12)
UCI_ID_1 = "10012345656"
UCI_ID_NEW = "10012345757"


def rider(rider_id: str, uci_id: str, last_name: str, first_name: str) -> dict:
    return {
        "rider_id": rider_id, "uci_id": uci_id, "last_name": last_name, "first_name": first_name
    }


def affiliation(rider_id: str) -> dict:
    return {"rider_id": rider_id, "start_date": DAY, "club_id": "4400001"}


def database_with_stale_rider():
    """Database where 'r_old' (no UCI ID) became 'r_new' (with a UCI ID) in the files."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    rows = {
        "riders": [
            rider("r1", UCI_ID_1, "DUPONT", "Paul"),
            rider("r_old", "", "MARTIN", "Jean"),
            rider("r2", "", "BERNARD", "Luc"),
        ],
        "rankings": [
            {"race_id": "race1", "rider_id": "r1", "finish_rank": 1},
            {"race_id": "race1", "rider_id": "r_old", "finish_rank": 2},
            {"race_id": "race2", "rider_id": "r_old", "finish_rank": 1},
            {"race_id": "race1", "rider_id": "r2", "finish_rank": 3},
        ],
        "affiliations": [affiliation("r1"), affiliation("r_old")],
        "rider_categories": [
            {"rider_id": "r1", "start_date": DAY, "rider_category": 2},
            {"rider_id": "r_old", "start_date": DAY, "rider_category": 3},
        ],
    }
    with engine.begin() as connection:
        for table_name, table_rows in rows.items():
            connection.execute(insert(TABLES[table_name]), table_rows)
    return engine


def files() -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Files of the new run: 'r_new' replaces 'r_old'; the result of 'r2' was dropped."""
    riders = pd.DataFrame([
        rider("r1", UCI_ID_1, "DUPONT", "Paul"),
        rider("r_new", UCI_ID_NEW, "MARTIN", "Jean"),
        rider("r2", "", "BERNARD", "Luc"),
    ])
    frames = {
        "rankings": pd.DataFrame({
            "race_id": ["race1", "race1", "race2"],
            "rider_id": ["r1", "r_new", "r_new"],
            "finish_rank": [1, 2, 1],
        }),
        "affiliations": pd.DataFrame([affiliation("r1"), affiliation("r_new")]),
        "rider_categories": pd.DataFrame({
            "rider_id": ["r1", "r_new"], "start_date": [DAY, DAY], "rider_category": [2, 3],
        }),
    }
    return riders, frames


def rider_ids_in(engine, table_name: str) -> list[str]:
    with engine.connect() as connection:
        return sorted(connection.execute(select(TABLES[table_name].c.rider_id)).scalars())


def test_tables_referring_to_riders():
    names = {table.name for table in tables_referring_to_riders()}
    assert names == {"rankings", "affiliations", "rider_categories"}


def test_dry_run_deletes_nothing():
    engine = database_with_stale_rider()
    riders, frames = files()
    report = prune_stale_riders(engine, riders, frames, apply=False)
    assert [row[0] for row in report.stale_riders] == ["r_old"]
    assert report.deleted_rows == {
        "rankings": 2, "affiliations": 1, "rider_categories": 1, "riders": 1
    }
    assert report.unexplained_missing_rows == {"rankings": 1}
    assert rider_ids_in(engine, "riders") == ["r1", "r2", "r_old"]
    assert "Run again with --apply" in format_report(report)


def test_apply_deletes_only_the_stale_rider_and_its_rows():
    engine = database_with_stale_rider()
    riders, frames = files()
    report = prune_stale_riders(engine, riders, frames, apply=True)
    assert report.deleted_rows == {
        "rankings": 2, "affiliations": 1, "rider_categories": 1, "riders": 1
    }
    assert rider_ids_in(engine, "riders") == ["r1", "r2"]
    # The result of 'r2', missing from the files, is kept and only reported
    assert rider_ids_in(engine, "rankings") == ["r1", "r2"]
    assert report.unexplained_missing_rows == {"rankings": 1}
    assert rider_ids_in(engine, "affiliations") == ["r1"]
    assert rider_ids_in(engine, "rider_categories") == ["r1"]
    assert "python scripts/load.py" in format_report(report)


def test_too_many_stale_riders_deletes_nothing():
    engine = database_with_stale_rider()
    riders, frames = files()
    with pytest.raises(TooManyStaleRiders):
        prune_stale_riders(engine, riders, frames, apply=True, max_riders=0)
    assert rider_ids_in(engine, "riders") == ["r1", "r2", "r_old"]


def test_no_stale_rider():
    engine = database_with_stale_rider()
    riders, frames = files()
    riders = pd.concat([riders, pd.DataFrame([rider("r_old", "", "MARTIN", "Jean")])])
    report = prune_stale_riders(engine, riders, frames, apply=True)
    assert report.stale_riders == []
    assert set(report.deleted_rows.values()) == {0}
