"""Unit tests of the extraction of former result pages (no network, temporary cache)."""

from datetime import datetime, timezone

import httpx
import pytest

from access_it.etl.extract import cache, races
from access_it.etl.extract.client import RequestFailures, RequestThrottle, try_get
from access_it.etl.extract.races import completed_seasons

NO_WAIT = RequestThrottle({}, default_min_delay=0.0, sleep=lambda seconds: None)

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


# ---------------------------------------------------------------- failed requests

class SearchClient:
    """Search pages: page 1 lists one race, page 2 fails, page 3 must never be requested."""

    def __init__(self):
        self.urls: list[str] = []

    def get(self, url: str) -> httpx.Response:
        self.urls.append(url)
        request = httpx.Request("GET", url)
        if "page=1" in url:
            html = (
                "<div id='resultats'>"
                "<a class='resultat' saison='2026' numero='C4400001001'></a></div>"
            )
            return httpx.Response(200, text=html, request=request)
        return httpx.Response(403, request=request)


def test_failed_result_page_is_not_cached(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(races, "try_get", lambda client, url: None)
    races.extract_results_from_organization_page(None, 2026, "C4400001001")
    assert not cache.results_sidecar_exists(2026, "C4400001001")


def test_http_404_status_is_cached_as_not_found(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "RESULTS_DIR", tmp_path / "results")
    url = "https://competitions.ffc.fr/resultats/resultat/2026/C4400001001"
    response = httpx.Response(404, request=httpx.Request("GET", url))
    monkeypatch.setattr(races, "try_get", lambda client, url: response)
    races.extract_results_from_organization_page(None, 2026, "C4400001001")
    assert cache.read_results_sidecar_data(2026, "C4400001001")["status"] == 404


def test_search_stops_at_the_first_failed_page(monkeypatch):
    pages = []
    monkeypatch.setattr(
        races, "extract_results_from_organization_page",
        lambda client, season, code: pages.append((season, code)),
    )
    monkeypatch.setattr(
        races, "try_get",
        lambda client, url: try_get(client, url, throttle=NO_WAIT, failures=RequestFailures()),
    )
    client = SearchClient()
    races.extract_organization_pages_from_search_url(client, dept=44)
    assert pages == [(2026, "C4400001001")]
    assert len(client.urls) == 2


def test_page_without_race_code_is_not_cached(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(cache, "RESULTS_DIR", tmp_path / "results")
    url = "https://competitions.ffc.fr/resultats/resultat/2026/C4400001001"
    html = "<h1 class='titre'>Course</h1><div class='discipline'>Route</div>"
    response = httpx.Response(200, text=html, request=httpx.Request("GET", url))
    monkeypatch.setattr(races, "try_get", lambda client, url: response)
    races.extract_results_from_organization_page(None, 2026, "C4400001001")
    assert not cache.results_sidecar_exists(2026, "C4400001001")
    assert "no race code found on the page" in caplog.text
    assert caplog.records[-1].levelname == "WARNING"


# ---------------------------------------------------------------- national result pages

class NationalSearchClient:
    """Search page 1 lists three races (2025, 2026 already cached, 2026 new); page 2 is empty."""

    def get(self, url: str) -> httpx.Response:
        request = httpx.Request("GET", url)
        if "page=1" in url:
            html = (
                "<div id='resultats'>"
                "<a class='resultat' saison='2025' numero='C4950101001'></a>"
                "<a class='resultat' saison='2026' numero='C4400001001'></a>"
                "<a class='resultat' saison='2026' numero='C4950101002'></a></div>"
            )
            return httpx.Response(200, text=html, request=request)
        return httpx.Response(200, text="<div id='resultats'></div>", request=request)


def test_national_search_skips_former_seasons_and_pages_of_the_main_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "RESULTS_DIR", tmp_path / "results")
    (tmp_path / "results" / "2026").mkdir(parents=True)
    (tmp_path / "results" / "2026" / "C4400001001.meta.json").write_text("{}")
    monkeypatch.setattr(races, "NATIONAL_RESULTS_DIR", tmp_path / "results_national")
    pages = []
    monkeypatch.setattr(
        races, "extract_results_from_organization_page",
        lambda client, season, code, results_dir: pages.append((season, code, results_dir)),
    )
    monkeypatch.setattr(
        races, "try_get",
        lambda client, url: try_get(client, url, throttle=NO_WAIT, failures=RequestFailures()),
    )
    races.extract_national_organization_pages(NationalSearchClient(), first_season=2026)
    assert pages == [(2026, "C4950101002", tmp_path / "results_national")]


def test_national_result_page_is_cached_apart(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "RESULTS_DIR", tmp_path / "results")
    national_dir = tmp_path / "results_national"
    url = "https://competitions.ffc.fr/resultats/resultat/2026/C4950101002"
    html = "<h1 class='titre'>Course</h1><div class='discipline'>Route</div>"
    response = httpx.Response(200, text=html, request=httpx.Request("GET", url))
    monkeypatch.setattr(races, "try_get", lambda client, url: response)
    monkeypatch.setattr(races, "get_elements_from_results_page", lambda bs: {"race_code": "1.27.1"})
    races.extract_results_from_organization_page(None, 2026, "C4950101002", results_dir=national_dir)
    assert cache.results_sidecar_exists(2026, "C4950101002", national_dir)
    assert cache.read_results_sidecar_data(2026, "C4950101002", national_dir)["kept"] is True
    assert not cache.results_sidecar_exists(2026, "C4950101002")
