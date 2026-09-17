import httpx
from bs4 import BeautifulSoup
from bs4.element import Tag
from datetime import datetime, timezone
from access_it.etl.extract.cache import CACHE_DIR, write_sidecar_and_html_files, sidecar_exists
from access_it.etl.extract.client import BASE_URL, get
from access_it.etl.extract.listing import is_this_organization_excluded, is_this_organization_included
from access_it.etl.transform.parse import get_text_safe


def extract_organization_page(
        client: httpx.Client,
        season: int,
        code: str
    ):

    results_base_url = f"{BASE_URL}/resultats/resultat"
    season_int = int(season)
    season_str = f"{season_int:4d}"
    org_ref = f"{season_str:4s}/{code:11s}"
    if sidecar_exists(season_int, code):
        print(f"{org_ref} already exists")
        return

    url = f"{results_base_url}/{season_str}/{code}"
    race_response = get(client=client, url=url)

    # any error
    if not isinstance(race_response, httpx.Response):
        print(f"{org_ref} network error")
        return

    # 404 error
    dst_url = str(race_response.url)
    page_not_found = dst_url.find("error") != -1 and dst_url.find("404") != -1
    if page_not_found:
        write_sidecar_and_html_files(season_int, code, race_response, force_404=True)
        print(f"{org_ref} page not found")
        return

    # No errors
    html = race_response.text
    bs = BeautifulSoup(html, features="html.parser")
    name = get_text_safe(bs.find(name="h1", class_="titre"))
    discipline = get_text_safe(bs.find(name="div", class_="discipline"))
    excluded = is_this_organization_excluded(name) or discipline != "Route"
    included = is_this_organization_included(name)
    # Races not kept:
    if excluded or not included:
        write_sidecar_and_html_files(season_int, code, race_response, kept=False)
        print(f"{org_ref} excluded race: {name}")
        return
    # Races kept:
    write_sidecar_and_html_files(season_int, code, race_response, kept=True)
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
        page_response = get(client=client, url=search_url)
        if not isinstance(page_response, httpx.Response):
            continue
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
            extract_organization_page(client=client, season=int(season), code=code)
        page += 1


def extract_former_organization_pages_from_existing_ones(
        client: httpx.Client,
        start_year: int = 2023
    ):
    saved_sidecar_files = [
        [p.parent.name, p.name.removesuffix(".meta.json")]
        for p in CACHE_DIR.rglob("*.meta.json")
    ]
    saved_sidecar_files = sorted(saved_sidecar_files)
    seasons = range(start_year, datetime.now(timezone.utc).year + 1)
    org_codes = list(set([org_code for _, org_code in saved_sidecar_files]))
    for season_int in seasons:
        for code in org_codes:
            extract_organization_page(client=client, season=season_int, code=code)


def extract_former_organization_pages_using_bruteforce(
        client: httpx.Client,
        start_year: int = 2023,
        margin: int = 0
    ):
    known_organization_codes = [
        p.name.removesuffix(".meta.json")
        for p in CACHE_DIR.rglob("*.meta.json")
    ]
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
    seasons = range(start_year, datetime.now(timezone.utc).year + 1)
    for season_int in seasons:
        for organizer_id in organizer_ids:
            organization_codes = [
                f"C{organizer_id}{i:03d}"
                for i in range(1, max_index_by_organizer[organizer_id] + margin)
            ]
            for organization_code in organization_codes:
                extract_organization_page(client=client, season=season_int, code=organization_code)
