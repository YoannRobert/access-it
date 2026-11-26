"""Configuration of the tests of the dashboard (app/dashboard).

The modules of the dashboard import each other by their bare names (from data
import ...), as Streamlit runs them from their folder: the folder is added to
the import path for these tests only. The tests need the dashboard extra
(pip install -e ".[dashboard]"); without Streamlit, they are not collected.

The page tests run the app with Streamlit's AppTest on a small fake snapshot
(see dashboard_snapshot.py), written once as a ZIP archive, and on two fake runs of
forecasts (upcoming_files); the download of the snapshot and of the forecasts (and their
checking thread) is replaced by these files.
"""

import importlib.util
import pytest
import sys

from collections.abc import Callable
from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parents[2] / "app" / "dashboard"
APP_TIMEOUT = 60  # seconds; the first run computes the points of every season

if importlib.util.find_spec("streamlit") is None:
    collect_ignore_glob = ["test_*.py"]
elif str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))


@pytest.fixture(scope="session")
def snapshot_path(tmp_path_factory) -> Path:
    """Fake snapshot archive of the tests, written once."""
    from access_it.export.snapshot import build_snapshot_zip
    from dashboard_snapshot import TABLES

    return build_snapshot_zip(TABLES, tmp_path_factory.mktemp("snapshots") / "snapshot.zip")


@pytest.fixture(scope="session")
def upcoming_files(tmp_path_factory) -> tuple:
    """Two fake runs of forecasts, written once.

    The run of 2026-09-25 forecasts a race on 2026-09-26 (r1, r2, r3, r2 favourite) and has a
    race without forecast the same day (r4, r5); the run of 2026-10-02 forecasts a race on
    2026-10-03 (r1, r6, r1 favourite, r6 without recent race).
    """
    import pandas as pd

    from datetime import datetime, timezone

    from access_it.export.upcoming import UpcomingFiles

    directory = tmp_path_factory.mktemp("upcoming")
    runs = [
        (datetime(2026, 9, 25, 19, 30, tzinfo=timezone.utc), "2026-09-26",
         {"vpc-1-1": ["r2", "r1", "r3"]}, {"vpc-2-1": ["r4", "r5"]}),
        (datetime(2026, 10, 2, 19, 30, tzinfo=timezone.utc), "2026-10-03",
         {"vpc-3-1": ["r1", "r6"]}, {}),
    ]
    files = []
    for timestamp, race_date, forecast_races, other_races in runs:
        rows = [
            {"race_id": race_id, "race_date": pd.Timestamp(race_date), "rider_id": rider_id,
             "page_id": race_id.split("-")[1], "page_title": f"Grand Prix {race_id}",
             "startlist_heading": "Access 1-2-3-4", "rank": rank}
            for races in (forecast_races, other_races)
            for race_id, rider_ids in races.items()
            for rank, rider_id in enumerate(rider_ids, start=1)
        ]
        entries = pd.DataFrame(rows).drop(columns="rank")
        forecasts = pd.DataFrame(
            [row for row in rows if row["race_id"] in forecast_races]
        ).assign(
            nb_races_used=lambda df: [0 if r == "r6" else 5 for r in df["rider_id"]],
            nb_top_n=1, top_n_rate=0.2, mu=25.0, sigma=8.0,
            best_place=lambda df: [100 if r == "r6" else 3 for r in df["rider_id"]],
            mean_place=12.0, p_win=lambda df: 0.6 / df["rank"], p_podium=0.9, p_top5=1.0,
            p_top10=1.0, rank_win=lambda df: df["rank"], rank_podium=1, rank_top5=1,
            rank_top10=1,
        ).drop(columns="rank")
        stamp = timestamp.strftime("%Y%m%dT%H%M%SZ")
        forecasts_path = directory / f"forecasts_{stamp}.parquet"
        entries_path = directory / f"entries_{stamp}.parquet"
        forecasts.to_parquet(forecasts_path, index=False)
        entries.to_parquet(entries_path, index=False)
        files.append(UpcomingFiles(timestamp, forecasts_path, entries_path))
    return tuple(reversed(files))


@pytest.fixture
def open_page(monkeypatch, snapshot_path, upcoming_files) -> Callable:
    """Function running the app on a page, with the fake data and query parameters."""
    import data

    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(
        data, "get_snapshot_holder", lambda: data.SnapshotHolder(snapshot_path, upcoming_files)
    )

    def open_page(page: str | None = None, **query_params: str):
        app = AppTest.from_file(str(DASHBOARD_DIR / "streamlit_app.py"), default_timeout=APP_TIMEOUT)
        app.run()
        if page is not None:
            for name, value in query_params.items():
                app.query_params[name] = value
            app.switch_page(page).run()
        return app

    return open_page
