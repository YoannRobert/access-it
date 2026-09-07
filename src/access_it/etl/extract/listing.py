import httpx
from bs4 import BeautifulSoup
from bs4.element import Tag
from datetime import datetime, timezone
from access_it.etl.extract.client import BASE_URL, make_client, get
from access_it.etl.extract.cache import (
    get_sidecar_file, read_sidecar_data, write_sidecar_file, write_html_file
)
from access_it.common.text import normalize_string_and_fold_case


RESULTS_ENDPOINT = "/resultats"


def get_organisation_list(client: httpx.Client, dept: int | None = None, max_pages: int = -1):
    if dept is None:
        dept = ""
    elif isinstance(dept, int):
        dept = f"{dept:02d}"
    else:
        raise ValueError(f"departement must be an int or None")
    results_url = f"{BASE_URL}{RESULTS_ENDPOINT}"
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
            relative_url = race.get("href")
            season = race.get("saison")
            code = race.get("numero")

            title_contents = race.find(name="div", class_="resultat-contenu")
            if not isinstance(title_contents, Tag):
                continue
            name = title_contents.find(name="div", class_="resultat-contenu-nom")
            if not isinstance(name, Tag):
                continue
            name = name.get_text(strip=True)
            excluded = is_this_organization_excluded(name)
            included = is_this_organization_included(name)
            if excluded or not included:
                print(f"excluded race: {name}")
                continue
            if (
                isinstance(relative_url, str)
                and isinstance(season, str)
                and isinstance(code, str)
            ):
                season = int(season)
                url = BASE_URL + relative_url
                race_sidecar_file = get_sidecar_file(season, code)
                read_race_page = True
                if race_sidecar_file.exists():
                    meta = read_sidecar_data(season, code)
                    read_race_page = meta["status"] != 200
                if read_race_page:
                    race_response = get(client=client, url=url)
                    if not isinstance(race_response, httpx.Response):
                        continue
                    meta = {
                        "status": race_response.status_code,
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                        "url": str(race_response.url),
                        "encoding": race_response.encoding
                    }
                    write_sidecar_file(season, code, meta)
                    write_html_file(season, code, race_response)
                    print(f"{season}/{code}: cached.")
                else:
                    print(f"{season}/{code}: already cached.")
        page += 1


def is_this_organization_excluded(name: str) -> bool:
    excluded = False
    excluding_patterns = [
        "elite",
        "el a ", "el à ", "el-o", "el+o", "el.o", "el/o",
        "open ",
        "open-", "open - ", "op-",
        "open+", "open + ", "op+",
        "open/", "open / ", "op/",
        "open1", "open 1",
        "open2", "open 2",
        "open3", "open 3",
        "op1", "op2", "op3",
        "op ", "op1", "op2", "op3",
        "u7", "u8", "u9", "u10", "u11", "u12",
        "u13", "u14", "u15", "u16", "u17",
        "u 7", "u 8", "u 9", "u 10", "u 11", "u 12",
        "u 13", "u 14", "u 15", "u 16", "u 17",
    ]
    n = normalize_string_and_fold_case(name)
    for exc in excluding_patterns:
        excluded = excluded or (n.find(exc) != -1)
    return excluded


def is_this_organization_included(name: str) -> bool:
    included = False
    including_patterns = [
        "access", "acess", "acces", "accce", "acc",
        "a1", "a2", "a3", "a4"
    ]
    n = normalize_string_and_fold_case(name)
    for inc in including_patterns:
        included = included or (n.find(inc) != -1)
    return included


if __name__ == "__main__":
    get_organisation_list(dept=44, max_pages=3)
