import httpx

from bs4 import BeautifulSoup
from datetime import datetime, timezone
from access_it.etl.extract.cache import (
    RESULTS_DIR, write_results_sidecar_and_html_files, results_sidecar_exists
)
from access_it.etl.extract.client import BASE_URL, try_get
from access_it.etl.transform.parse import get_text_safe, get_elements_from_results_page


def extract_results_from_organization_page(
        client: httpx.Client,
        season: int,
        code: str
    ):

    results_base_url = f"{BASE_URL}/resultats/resultat"
    season_str = f"{season:4d}"
    org_ref = f"{season_str:4s}/{code:11s}"
    if results_sidecar_exists(season, code):
        print(f"{org_ref} already exists")
        return

    url = f"{results_base_url}/{season_str}/{code}"
    race_response = try_get(client=client, url=url)

    # Request failed for good: nothing is cached, the page is requested again at the next run
    if not isinstance(race_response, httpx.Response):
        print(f"{org_ref} request failed, skipped")
        return

    # 404 error (HTTP status, or redirection to the error page)
    dst_url = str(race_response.url)
    page_not_found = (
        race_response.status_code == 404
        or (dst_url.find("error") != -1 and dst_url.find("404") != -1)
    )
    if page_not_found:
        write_results_sidecar_and_html_files(season, code, race_response, force_404=True)
        print(f"{org_ref} page not found")
        return

    # No errors
    html = race_response.text
    bs = BeautifulSoup(html, features="html.parser")
    name = get_text_safe(bs.find(name="h1", class_="titre"))
    discipline = get_text_safe(bs.find(name="div", class_="discipline"))
    general_info = get_elements_from_results_page(bs)
    race_code = general_info.get("race_code")
    # Unexpected page layout: not cached, so that the page is read again at the next run
    if race_code is None:
        print(f"Warning: {org_ref} no race code found on the page, skipped: {name}")
        return
    included = (
        discipline == "Route"
        and (
            race_code.startswith("1.27.")
            or race_code.startswith("3.07.")
            or race_code.startswith("3.7.")
            or race_code.startswith("3.28.")
        )
    )
    # Races not kept:
    if not included:
        write_results_sidecar_and_html_files(season, code, race_response, kept=False)
        print(f"{org_ref} excluded race: {name}")
        return
    # Races kept:
    write_results_sidecar_and_html_files(season, code, race_response, kept=True)
    print(f"{org_ref}: cached")


def extract_organization_pages_from_search_url(
        client: httpx.Client,
        dept: int | None = None,
        max_pages: int = -1
    ):
    if dept is None:
        dept = ""
    elif isinstance(dept, int):
        dept = f"{dept:02d}"
    else:
        raise ValueError(f"departement must be an int or None")
    results_url = f"{BASE_URL}/resultats"
    page = 1
    while True and (max_pages == -1 or page <= max_pages):
        search_url = f"{results_url}/?discipline=1&departement={dept}&page={page}"
        page_response = try_get(client=client, url=search_url)
        if not isinstance(page_response, httpx.Response):
            # The next search pages cannot be trusted: stop for this departement
            print(f"Search of departement {dept!r} stopped at page {page} (request failed)")
            break
        html = page_response.text
        soup = BeautifulSoup(html, features="html.parser")
        results = soup.find(name="div", id="resultats")
        if results is None:
            break
        races = results.find_all(name="a", class_="resultat")
        if len(races) == 0:
            break
        for race in races:
            season = race.get("saison")
            code = race.get("numero")
            if not isinstance(season, str) or not isinstance(code, str):
                continue
            try:
                season = int(season)
            except ValueError:
                raise ValueError(f"'season' value ({season}) not convertible to int")
            extract_results_from_organization_page(client=client, season=season, code=code)
        page += 1


def completed_seasons(start_year: int, now: datetime | None = None) -> range:
    """Seasons from `start_year` to the previous one (the current season is excluded).

    Requesting a page of the current season by its number may cache a "not
    found" page for a race not held yet, which would then block its results
    once published: pages of the current season are only found by the search
    engine (see extract_organization_pages_from_search_url).
    """
    now = now or datetime.now(timezone.utc)
    return range(start_year, now.year)


def extract_former_organization_pages_from_existing_ones(
        client: httpx.Client,
        start_year: int = 2023
    ):
    saved_sidecar_files = [
        [p.parent.name, p.name.removesuffix(".meta.json")]
        for p in RESULTS_DIR.rglob("*.meta.json")
    ]
    saved_sidecar_files = sorted(saved_sidecar_files)
    seasons = completed_seasons(start_year)
    org_codes = list(set([org_code for _, org_code in saved_sidecar_files]))
    for season in seasons:
        for code in org_codes:
            extract_results_from_organization_page(client=client, season=season, code=code)


def extract_former_organization_pages_using_bruteforce(
        client: httpx.Client,
        start_year: int = 2023,
        margin: int = 0
    ):
    known_organization_codes = [
        p.name.removesuffix(".meta.json")
        for p in RESULTS_DIR.rglob("*.meta.json")
    ]
    known_organization_codes = [c for c in known_organization_codes if c.startswith("C")]
    organizer_ids = sorted(list(set([c[1:8] for c in known_organization_codes])))
    max_index_by_organizer = {
        organizer_id: max(
            [
                int(c[8:])
                for c in known_organization_codes
                if c.startswith("C" + organizer_id)
            ]
        )
        for organizer_id in organizer_ids
    }
    seasons = completed_seasons(start_year)
    for season in seasons:
        for organizer_id in organizer_ids:
            organization_codes = [
                f"C{organizer_id}{i:03d}"
                for i in range(1, max_index_by_organizer[organizer_id] + margin)
            ]
            for organization_code in organization_codes:
                extract_results_from_organization_page(client=client, season=season, code=organization_code)
