"""Unit tests of scripts/forecast_upcoming_races.py, with a fake forecast (no training)."""

import sys

from pathlib import Path

import pandas as pd

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import forecast_upcoming_races as script  # noqa: E402

ENTRIES = pd.DataFrame({
    "race_id": ["vpc-2-1", "vpc-2-1", "vpc-1-3"],
    "race_date": pd.to_datetime(["2026-11-22", "2026-11-22", "2026-11-21"]),
    "rider_id": ["r1", "r2", "r3"],
    "page_id": ["2", "2", "1"],
    "page_title": ["Vallet", "Vallet", "Clisson"],
    "startlist_heading": ["ACCESS 3.4", "ACCESS 3.4", "ACCESS 1.2"],
})
FORECASTS = ENTRIES.iloc[[1, 0]].assign(p_win=[0.6, 0.4], rank_win=[1, 2])


def test_tables_and_entries_are_given_to_the_forecast(monkeypatch):
    calls = {}

    def fake_read_parquet(path):
        calls.setdefault("paths", []).append(path)
        return ENTRIES if path == Path("entries.parquet") else pd.DataFrame({"table": [path]})

    def fake_forecast(races, rankings, entries):
        calls["tables"] = [races["table"][0], rankings["table"][0]]
        calls["entries"] = entries
        return FORECASTS

    monkeypatch.setattr(script.pd, "read_parquet", fake_read_parquet)
    monkeypatch.setattr(script, "forecast_upcoming_entries", fake_forecast)
    entries, forecasts = script.forecast_upcoming_races(Path("entries.parquet"))
    assert entries is ENTRIES and forecasts is FORECASTS
    assert calls["tables"] == [script.RACES_PARQUET_FILE, script.RANKINGS_PARQUET_FILE]
    assert calls["entries"] is ENTRIES


def test_summary_gives_one_line_per_race_forecast_or_not(capsys):
    script.print_summary(ENTRIES, FORECASTS)
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "2 races, 3 entries: 1 races forecast, 1 not forecast"
    assert lines[1].split()[:5] == ["2026-11-21", "vpc-1-3", "1", "not", "forecast"]
    assert lines[2].split()[:4] == ["2026-11-22", "vpc-2-1", "2", "forecast"]


def test_summary_without_entries(capsys):
    script.print_summary(ENTRIES.iloc[0:0], FORECASTS.iloc[0:0])
    assert capsys.readouterr().out == "No entries\n"


def test_forecasts_are_written_to_the_output_file_even_empty(monkeypatch, tmp_path):
    for forecasts in (FORECASTS, FORECASTS.iloc[0:0]):
        monkeypatch.setattr(
            script, "forecast_upcoming_races", lambda path, f=forecasts: (ENTRIES, f)
        )
        output = tmp_path / "forecasts.parquet"
        script.main(Path("entries.parquet"), output)
        pd.testing.assert_frame_equal(pd.read_parquet(output), forecasts.reset_index(drop=True))


def test_nothing_is_written_without_output_file(monkeypatch, tmp_path):
    monkeypatch.setattr(script, "forecast_upcoming_races", lambda path: (ENTRIES, FORECASTS))
    monkeypatch.chdir(tmp_path)
    script.main(Path("entries.parquet"))
    assert list(tmp_path.iterdir()) == []
