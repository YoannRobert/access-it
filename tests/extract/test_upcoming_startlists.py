"""Unit tests of the extraction of the startlist pages of upcoming races (no network)."""

import httpx
import pytest

from access_it.etl.extract import startlists, upcoming_startlists
from access_it.etl.extract.upcoming_startlists import (
    UpcomingStartlistPage, extract_upcoming_startlist_pages
)

BASE_URL = "https://startlists.test/route/engages/"


def entry(page_id: str, publication_date: str, title: str | None) -> str:
    """HTML of an entry of a listing page (publication date as 'DD/MM/YYYY')."""
    title_html = f"<h2>{title}</h2>" if title else ""
    return (
        f'<section id="actus{page_id}" class="newsResume"><a href="{page_id}.html">x</a>'
        f'<ul><li class="date">{publication_date}</li></ul>{title_html}</section>'
    )


def listing_page(entries: list[str], next_href: str | None = None) -> str:
    """HTML of a listing page with the given entries and "next" link."""
    pager = f'<a class="pagerNext" href="{next_href}">next</a>' if next_href else ""
    return f'<div id="newsList">{"".join(entries)}</div>{pager}'


@pytest.fixture
def website(monkeypatch):
    """Fake website: maps an address to a response (HTML or status code)."""
    pages: dict[str, str | int | None] = {}
    requested: list[str] = []

    def fake_try_get(client, url):
        requested.append(url)
        page = pages.get(url, 404)
        if page is None:
            return None
        if isinstance(page, int):
            return httpx.Response(page, text="")
        return httpx.Response(200, text=page)

    monkeypatch.setattr(startlists, "road_startlists_url", lambda: BASE_URL)
    monkeypatch.setattr(upcoming_startlists, "try_get", fake_try_get)
    return pages, requested


def test_pages_of_races_held_from_the_start_date(website):
    pages, _ = website
    pages[BASE_URL] = listing_page([
        entry("3", "18/11/2026", "Noëllet 22 novembre 2026"),
        entry("2", "17/11/2026", "Vallet 21 novembre 2026"),
        entry("1", "16/11/2026", "Clisson 20 novembre 2026"),
    ])
    pages[BASE_URL + "3.html"] = "<html>3</html>"
    pages[BASE_URL + "2.html"] = "<html>2</html>"
    result = extract_upcoming_startlist_pages(client=None, start_date="2026-11-21")
    assert result == [
        UpcomingStartlistPage(
            "3", "2026-11-18", "2026-11-22", "Noëllet 22 novembre 2026",
            BASE_URL + "3.html", "<html>3</html>",
        ),
        UpcomingStartlistPage(
            "2", "2026-11-17", "2026-11-21", "Vallet 21 novembre 2026",
            BASE_URL + "2.html", "<html>2</html>",
        ),
    ]


def test_entry_without_title_is_dated_by_its_publication_date(website):
    pages, _ = website
    pages[BASE_URL] = listing_page([
        entry("2", "21/11/2026", None),
        entry("1", "20/11/2026", None),
    ])
    pages[BASE_URL + "2.html"] = "<html>2</html>"
    result = extract_upcoming_startlist_pages(client=None, start_date="2026-11-21")
    assert [(p.page_id, p.race_date) for p in result] == [("2", "2026-11-21")]


def test_listing_stops_after_the_first_page_published_before_the_lookback(website):
    pages, requested = website
    pages[BASE_URL] = listing_page(
        [
            entry("3", "10/11/2026", "A 12 novembre 2026"),
            entry("2", "06/11/2026", "B 8 novembre 2026"),
        ],
        next_href="page-2.html",
    )
    pages[BASE_URL + "page-2.html"] = listing_page(
        [entry("1", "06/11/2026", "C 25 novembre 2026")], next_href="page-3.html",
    )
    pages[BASE_URL + "1.html"] = "<html>1</html>"
    result = extract_upcoming_startlist_pages(client=None, start_date="2026-11-21")
    assert [p.page_id for p in result] == ["1"]
    assert requested == [BASE_URL, BASE_URL + "page-2.html", BASE_URL + "1.html"]


def test_listing_stops_after_the_last_page(website):
    pages, requested = website
    pages[BASE_URL] = listing_page([entry("1", "20/11/2026", "A 22 novembre 2026")])
    pages[BASE_URL + "1.html"] = "<html>1</html>"
    assert len(extract_upcoming_startlist_pages(client=None, start_date="2026-11-21")) == 1
    assert requested == [BASE_URL, BASE_URL + "1.html"]


@pytest.mark.parametrize("failure", [None, 404])
def test_failed_listing_page_stops_the_listing(website, failure, caplog):
    pages, requested = website
    pages[BASE_URL] = listing_page(
        [entry("1", "20/11/2026", "A 22 novembre 2026")], next_href="page-2.html",
    )
    pages[BASE_URL + "1.html"] = "<html>1</html>"
    pages[BASE_URL + "page-2.html"] = failure
    result = extract_upcoming_startlist_pages(client=None, start_date="2026-11-21")
    assert [p.page_id for p in result] == ["1"]
    assert requested[-1] == BASE_URL + "page-2.html"
    assert "stopped at page 2" in caplog.text


@pytest.mark.parametrize("failure", [None, 404])
def test_failed_startlist_page_is_skipped(website, failure, caplog):
    pages, _ = website
    pages[BASE_URL] = listing_page([
        entry("2", "20/11/2026", "A 22 novembre 2026"),
        entry("1", "20/11/2026", "B 23 novembre 2026"),
    ])
    pages[BASE_URL + "2.html"] = failure
    pages[BASE_URL + "1.html"] = "<html>1</html>"
    result = extract_upcoming_startlist_pages(client=None, start_date="2026-11-21")
    assert [p.page_id for p in result] == ["1"]
    assert "Startlist page 2 skipped" in caplog.text
