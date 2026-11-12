"""Unit tests of the order of the steps of scripts/etl.py, with recording fake steps."""

import sys

from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import etl as etl_script  # noqa: E402


@pytest.fixture
def run_etl(monkeypatch):
    """Run the ETL with fake steps; return the names of the steps run, in order.

    The fake step named `failing` raises a RuntimeError, which the ETL must propagate.
    """

    def run(failing: str | None = None, **kwargs) -> list[str]:
        names: list[str] = []

        def record(name: str) -> None:
            names.append(name)
            if name == failing:
                raise RuntimeError(f"{name} failed")

        monkeypatch.setattr(etl_script, "sync_cache", record)
        monkeypatch.setattr(etl_script, "extract", lambda: record("extract"))
        monkeypatch.setattr(etl_script, "transform", lambda: record("transform"))
        monkeypatch.setattr(etl_script, "load", lambda: record("load"))
        monkeypatch.setattr(etl_script, "export_database_to_s3_bucket", lambda: record("export"))
        if failing is None:
            etl_script.etl(**kwargs)
        else:
            with pytest.raises(RuntimeError, match=f"{failing} failed"):
                etl_script.etl(**kwargs)
        return names

    return run


def test_all_steps_run_in_order_by_default(run_etl):
    assert run_etl() == ["pull", "extract", "transform", "load", "push", "export"]


def test_no_cache_sync_skips_the_pull_and_the_push(run_etl):
    assert run_etl(cache_sync=False) == ["extract", "transform", "load", "export"]


def test_no_snapshot_export_skips_the_export(run_etl):
    assert run_etl(snapshot_export=False) == ["pull", "extract", "transform", "load", "push"]


@pytest.mark.parametrize("failing, expected", [
    ("pull", ["pull"]),
    ("extract", ["pull", "extract"]),
    ("load", ["pull", "extract", "transform", "load"]),
    ("push", ["pull", "extract", "transform", "load", "push"]),
])
def test_a_failure_stops_the_following_steps(run_etl, failing, expected):
    assert run_etl(failing=failing) == expected
