"""Unit tests of the extraction of former result pages (no network, temporary cache)."""

from datetime import datetime, timezone

import pytest

from access_it.etl.extract import races
from access_it.etl.extract.races import completed_seasons

CURRENT_YEAR = datetime.now(timezone.utc).year


@pytest.fixture
def requested_pages(tmp_path, monkeypatch):
    """Temporary cache holding two known pages; record the pages requested."""
    results_dir = tmp_path / "results"
    for season, code in [(CURRENT_YEAR - 1, "C4400001002"), (CURRENT_YEAR, "C4400001003")]:
        (results_dir / str(season)).mkdir(parents=True, exist_ok=True)
        (results_dir / str(season) / f"{code}.meta.json").write_text("{}")
    monkeypatch.setattr(races, "RESULTS_DIR", results_dir)
    pages = []
    monkeypatch.setattr(
        races,
        "extract_results_from_organization_page",
        lambda client, season, code: pages.append((season, code)),
    )
    return pages


def test_completed_seasons_exclude_the_current_season():
    now = datetime(2026, 10, 21, tzinfo=timezone.utc)
    assert list(completed_seasons(2023, now)) == [2023, 2024, 2025]
    assert list(completed_seasons(2026, now)) == []


def test_former_pages_from_existing_ones_skip_the_current_season(requested_pages):
    races.extract_former_organization_pages_from_existing_ones(None, start_year=CURRENT_YEAR - 2)
    seasons = {season for season, _ in requested_pages}
    assert seasons == {CURRENT_YEAR - 2, CURRENT_YEAR - 1}
    assert {code for _, code in requested_pages} == {"C4400001002", "C4400001003"}


def test_bruteforce_skips_the_current_season(requested_pages):
    races.extract_former_organization_pages_using_bruteforce(None, start_year=CURRENT_YEAR - 2)
    seasons = {season for season, _ in requested_pages}
    assert seasons == {CURRENT_YEAR - 2, CURRENT_YEAR - 1}
    assert {code for _, code in requested_pages} == {"C4400001001", "C4400001002"}
