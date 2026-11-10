"""Configuration of the tests of the dashboard (app/dashboard).

The modules of the dashboard import each other by their bare names (from data
import ...), as Streamlit runs them from their folder: the folder is added to
the import path for these tests only. The tests need the dashboard extra
(pip install -e ".[dashboard]"); without Streamlit, they are not collected.

The page tests run the app with Streamlit's AppTest on a small fake snapshot
(see dashboard_snapshot.py), written once as a ZIP archive; the download of
the snapshot (and its checking thread) is replaced by this archive.
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


@pytest.fixture
def open_page(monkeypatch, snapshot_path) -> Callable:
    """Function running the app on a page, with the fake snapshot and query parameters."""
    import data

    from streamlit.testing.v1 import AppTest

    monkeypatch.setattr(data, "get_snapshot_holder", lambda: data.SnapshotHolder(snapshot_path))

    def open_page(page: str | None = None, **query_params: str):
        app = AppTest.from_file(str(DASHBOARD_DIR / "streamlit_app.py"), default_timeout=APP_TIMEOUT)
        app.run()
        if page is not None:
            for name, value in query_params.items():
                app.query_params[name] = value
            app.switch_page(page).run()
        return app

    return open_page
