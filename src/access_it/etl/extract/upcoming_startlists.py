"""Extraction of the startlist pages of upcoming races from the startlists website.

The pages are requested at each run and kept in memory: nothing is cached.
"""

import logging
from dataclasses import dataclass
from datetime import date as Date, timedelta

import httpx

from access_it.common.date import parse_startlist_title
from access_it.etl.extract import startlists
from access_it.etl.extract.client import try_get

logger = logging.getLogger(__name__)


LISTING_LOOKBACK_DAYS = 14


@dataclass(frozen=True)
class UpcomingStartlistPage:
    """A startlist page of an upcoming race.

    Attributes:
        page_id: ID of the page on the startlists website (e.g. "38949").
        publication_date: Publication date of the page ('YYYY-MM-DD').
        race_date: Race date read in the listed title ('YYYY-MM-DD').
        title: Title of the page as listed, None if missing.
        url: Absolute address of the page.
        html: HTML of the page.
    """
    page_id: str
    publication_date: str
    race_date: str
    title: str | None
    url: str
    html: str


def _try_get_page(client: httpx.Client, url: str) -> httpx.Response | None:
    """Request a page, None if the request fails or the response is not a 200."""
    response = try_get(client=client, url=url)
    if not isinstance(response, httpx.Response) or response.status_code != 200:
        return None
    return response


def extract_upcoming_startlist_pages(
        client: httpx.Client,
        start_date: str
    ) -> list[UpcomingStartlistPage]:
    """Request the startlist pages of the races held from a start date.

    The listing is read page by page. Each listed page is dated with the race
    date read in its title (the publication date if it has no title), and is
    requested if the race is held on or after `start_date`. The listing stops
    after the first page whose entries were all published more than
    LISTING_LOOKBACK_DAYS days before `start_date`, or after the last page.

    A listing page whose request fails stops the listing; a startlist page whose
    request fails is skipped. A request fails if no response is received or if
    the response is not a 200. Both cases are logged as warnings.

    Args:
        client: HTTP client.
        start_date: First race date to keep ('YYYY-MM-DD').

    Returns:
        The startlist pages of the races held from `start_date`, in the order
        of the listing.
    """
    oldest_publication_date = (
        Date.fromisoformat(start_date) - timedelta(days=LISTING_LOOKBACK_DAYS)
    ).isoformat()
    base_url = startlists.road_startlists_url()
    listing_url: str | None = base_url
    page = 1
    upcoming = []
    while listing_url is not None:
        listing_response = _try_get_page(client, listing_url)
        if listing_response is None:
            logger.warning(f"Startlists listing stopped at page {page} (request failed)")
            break
        listed, listing_url = startlists.parse_startlists_listing_page(
            listing_response.text, base_url
        )
        for startlist in listed:
            race_date = parse_startlist_title(
                startlist.title or "", startlist.publication_date
            )[2]
            if race_date < start_date:
                continue
            page_response = _try_get_page(client, startlist.url)
            if page_response is None:
                logger.warning(f"Startlist page {startlist.page_id} skipped (request failed)")
                continue
            upcoming.append(UpcomingStartlistPage(
                page_id=startlist.page_id,
                publication_date=startlist.publication_date,
                race_date=race_date,
                title=startlist.title,
                url=startlist.url,
                html=page_response.text,
            ))
        if all(s.publication_date < oldest_publication_date for s in listed):
            break
        page += 1
    return upcoming
