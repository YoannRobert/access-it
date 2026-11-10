"""Configuration of the tests of the dashboard (app/dashboard).

The modules of the dashboard import each other by their bare names (from data
import ...), as Streamlit runs them from their folder: the folder is added to
the import path for these tests only. The tests need the dashboard extra
(pip install -e ".[dashboard]"); without Streamlit, they are not collected.
"""

import importlib.util
import sys

from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parents[2] / "app" / "dashboard"

if importlib.util.find_spec("streamlit") is None:
    collect_ignore_glob = ["test_*.py"]
elif str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))
