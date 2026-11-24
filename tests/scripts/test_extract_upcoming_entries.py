"""Unit tests of scripts/extract_upcoming_entries.py, with fake steps (no network, no files)."""

import sys

from pathlib import Path

import pandas as pd

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import extract_upcoming_entries as script  # noqa: E402

ENTRIES = pd.DataFrame({
    "race_id": ["vpc-2-1", "vpc-2-1", "vpc-1-3"],
    "race_date": pd.to_datetime(["2026-11-22", "2026-11-22", "2026-11-21"]),
    "rider_id": ["r1", "r2", "r3"],
    "page_id": ["2", "2", "1"],
    "page_title": ["Vallet", "Vallet", "Clisson"],
    "startlist_heading": ["ACCESS 3.4", "ACCESS 3.4", "ACCESS 1.2"],
})


def test_pages_from_the_start_date_give_the_entries(monkeypatch):
    calls = {}

    def fake_extract(client, start_date):
        calls["start_date"] = start_date
        return ["page"]

    def fake_build(pages, *tables):
        calls["pages"] = pages
        calls["tables"] = len(tables)
        return ENTRIES

    monkeypatch.setattr(script.pd, "read_parquet", lambda path: pd.DataFrame())
    monkeypatch.setattr(script, "extract_upcoming_startlist_pages", fake_extract)
    monkeypatch.setattr(script, "build_upcoming_entries", fake_build)
    assert script.extract_upcoming_entries("2026-11-21") is ENTRIES
    assert calls == {"start_date": "2026-11-21", "pages": ["page"], "tables": 6}



def test_start_date_defaults_to_the_day_after_the_last_race(monkeypatch, capsys):
    races = pd.DataFrame({"race_date": pd.to_datetime(["2026-11-15", "2026-11-22"])})
    calls = {}

    def fake_read_parquet(path):
        return races if path == script.RACES_PARQUET_FILE else pd.DataFrame()

    def fake_extract(client, start_date):
        calls["start_date"] = start_date
        return []

    monkeypatch.setattr(script.pd, "read_parquet", fake_read_parquet)
    monkeypatch.setattr(script, "extract_upcoming_startlist_pages", fake_extract)
    monkeypatch.setattr(script, "build_upcoming_entries", lambda pages, *tables: ENTRIES)
    script.extract_upcoming_entries()
    assert calls == {"start_date": "2026-11-23"}
    assert "Start date: 2026-11-23" in capsys.readouterr().out

def test_summary_gives_one_line_per_race_by_date(capsys):
    script.print_summary(ENTRIES)
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "2 races, 3 entries"
    assert lines[1].split()[:3] == ["2026-11-21", "vpc-1-3", "1"]
    assert lines[2].split()[:3] == ["2026-11-22", "vpc-2-1", "2"]


def test_summary_without_entries(capsys):
    script.print_summary(ENTRIES.iloc[0:0])
    assert capsys.readouterr().out == "No entries\n"


def test_entries_are_written_to_the_output_file(monkeypatch, tmp_path):
    monkeypatch.setattr(script, "extract_upcoming_entries", lambda start_date: ENTRIES)
    output = tmp_path / "entries.parquet"
    script.main("2026-11-21", output)
    pd.testing.assert_frame_equal(pd.read_parquet(output), ENTRIES)


def test_nothing_is_written_without_output_file(monkeypatch, tmp_path):
    monkeypatch.setattr(script, "extract_upcoming_entries", lambda start_date: ENTRIES)
    monkeypatch.chdir(tmp_path)
    script.main("2026-11-21")
    assert list(tmp_path.iterdir()) == []
