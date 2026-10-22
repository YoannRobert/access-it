"""Extraction of the startlist pages of the startlists website (road races).

The address of the website is read from the STARTLISTS_URL setting.
"""

import logging
import httpx

from bs4 import BeautifulSoup

from access_it.config import get_settings
from access_it.etl.extract.cache import (
    startlists_json_file_exists, write_startlists_json_and_html_files
)
from access_it.etl.extract.client import try_get
from access_it.common.access_categories import find_access_categories_from_name
from access_it.common.html import get_text_safe

logger = logging.getLogger(__name__)


STARTLISTS_URL = get_settings().startlists_url
ROAD_STARTLISTS_URL = f"{STARTLISTS_URL}/route/engages/"


def extract_startlists_from_organization_page(
        client: httpx.Client,
        season: int,
        code: str,
        url: str
    ):
    """Request and cache a startlist page, unless it is already cached.

    The page is kept if its description mentions Access and one of its
    startlists has an Access category in its name. A page whose request
    fails is skipped without being cached, so that it is requested again at
    the next run.

    Args:
        client: HTTP client.
        season: Season of the page (year of its publication).
        code: Identifier of the page on the startlists website.
        url: URL of the page.
    """
    season_str = f"{season:4d}"
    org_ref = f"{season_str:4s}/{code:s}".ljust(10)
    if startlists_json_file_exists(season, code):
        logger.debug(f"{org_ref} already exists")
        return

    race_response = try_get(client=client, url=url)

    # Request failed for good: nothing is cached, the page is requested again at the next run
    if not isinstance(race_response, httpx.Response):
        logger.info(f"{org_ref} request failed, skipped")
        return

    # No errors
    html = race_response.text
    bs = BeautifulSoup(html, features="html.parser")
    title = get_text_safe(bs.find(name="h1"))
    description = get_text_safe(bs.find(name="div", class_="description"))
    if not isinstance(description, str):
        return
    race_names = [get_text_safe(n) for n in bs.find_all(name="h3")]
    access_category_found = any(
        [
            sum(
                [
                    int(v)
                    for v in find_access_categories_from_name(n).values()
                ]
            ) > 0
            for n in race_names
            if isinstance(n, str)
        ]
    )
    included = (
        description.lower().find("access") != -1
        and access_category_found
    )
    # Races not kept:
    if not included:
        write_startlists_json_and_html_files(season, code, race_response, kept=False)
        logger.info(f"{org_ref} excluded race: {title}")
        return
    # Races kept:
    write_startlists_json_and_html_files(season, code, race_response, kept=True)
    logger.info(f"{org_ref}: cached")


def extract_startlists_pages_from_search_url(
        client: httpx.Client,
        max_pages: int = -1
    ):
    """Extract the startlist pages listed by the startlists website, page by page.

    The listing stops at its last page, or at the first listing page whose
    request fails.

    Args:
        client: HTTP client.
        max_pages: Maximum number of listing pages (-1: no limit).
    """
    page = 1
    organization_count = 0
    search_url = ROAD_STARTLISTS_URL
    while True and (max_pages == -1 or page <= max_pages):
        page_response = try_get(client=client, url=search_url)
        if not isinstance(page_response, httpx.Response):
            logger.warning(f"Startlists listing stopped at page {page} (request failed)")
            break
        html = page_response.text
        soup = BeautifulSoup(html, features="html.parser")
        results = soup.find(name="div", id="newsList")
        if results is None:
            break
        organizations = results.find_all(name="section", class_="newsResume")
        if len(organizations) == 0:
            break
        for organization in organizations:
            organization_count += 1
            organization_id = organization.get("id")
            organization_date = get_text_safe(organization.find(name="li", class_="date"))
            tmp = organization.find_all(name="a")[0]
            organization_relative_url = tmp.get("href")
            if (
                    not isinstance(organization_id, str)
                    or not isinstance(organization_date, str)
                    or not isinstance(organization_relative_url, str)
            ):
                continue
            organization_id = organization_id.replace("actus", "")
            organization_date = "-".join(list(reversed(organization_date.split("/"))))
            extract_startlists_from_organization_page(
                client=client,
                season=int(organization_date.split("-")[0]),
                code=organization_id,
                url=ROAD_STARTLISTS_URL + organization_relative_url
            )
        pagerNext = soup.find(name="a", class_="pagerNext")
        if pagerNext is None:
            break
        relative_url_next_page = pagerNext.get("href")
        if not isinstance(relative_url_next_page, str):
            break
        search_url = ROAD_STARTLISTS_URL + relative_url_next_page
        page += 1
