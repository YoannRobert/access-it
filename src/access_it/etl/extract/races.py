import httpx
from bs4 import BeautifulSoup, Tag
from datetime import datetime, timezone
from access_it.etl.extract.cache import CACHE_DIR, get_sidecar_file, write_sidecar_and_html_files
from access_it.etl.extract.client import BASE_URL, make_client, get
from access_it.etl.extract.listing import is_this_organization_excluded, is_this_organization_included


def extract_unlisted_organizations(client: httpx.Client, start_year: int = 2023):
    seasons = range(start_year, datetime.now(timezone.utc).year + 1)
    saved_organization_codes = sorted([p.stem for p in CACHE_DIR.rglob("*.html")])

    results_base_url = f"{BASE_URL}/resultats/resultat"
    for season_int in seasons:
        season_str = str(season_int)
        for code in saved_organization_codes:
            if get_sidecar_file(season_int, code).exists():
                print(f"{season_str}/{code}: already exists.")
                continue
            url = f"{results_base_url}/{season_str}/{code}"
            race_response = get(client=client, url=url)
            if not isinstance(race_response, httpx.Response):
                print(f"{season_str}/{code}: network error.")
                continue
            dst_url = str(race_response.url)
            page_not_found = dst_url.find("error") != -1 and dst_url.find("404") != -1
            if page_not_found:
                print(f"{season_str}/{code}: page not found.")
                continue

            html = race_response.text
            bs = BeautifulSoup(html, features="html.parser")
            name = bs.find(name="h1", class_="titre")
            if not isinstance(name, Tag):
                continue
            name = name.get_text(strip=True)
            excluded = is_this_organization_excluded(name)
            included = is_this_organization_included(name)
            if excluded or not included:
                print(f"excluded race: {name}")
                continue
            write_sidecar_and_html_files(season_int, code, race_response)
            print(f"{season_str}/{code}: cached.")


if __name__ == "__main__":
    extract_unlisted_organizations()
