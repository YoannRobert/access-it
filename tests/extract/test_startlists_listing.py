"""Unit tests of the reading of the listing pages of the startlists website (no network)."""

import httpx

from access_it.etl.extract import startlists
from access_it.etl.extract.startlists import ListedStartlist, parse_startlists_listing_page

BASE_URL = "https://startlists.test/route/engages/"


def entry(page_id: str, date: str | None, href: str | None, title: str | None) -> str:
    """HTML of an entry of a listing page, without the parts given as None."""
    date_html = f'<ul class="tag"><li class="date">{date}</li></ul>' if date else ""
    link_html = f'<a href="{href}">{title or ""}</a>' if href else "<a>no link</a>"
    title_html = f"<h2>{title}</h2>" if title else ""
    return (
        f'<section id="actus{page_id}" class="newsResume">{link_html}'
        f'<div class="infoNews">{date_html}</div>{title_html}</section>'
    )


def listing_page(entries: list[str], next_href: str | None = None) -> str:
    """HTML of a listing page with the given entries and "next" link."""
    pager = f'<a class="pagerNext" href="{next_href}">next</a>' if next_href else ""
    return f'<div id="newsList">{"".join(entries)}</div>{pager}'


def test_entries_and_next_page_of_a_listing_page():
    html = listing_page(
        [entry("38949", "14/10/2026", "38949-noellet.html", "Noëllet 17 octobre 2026 engagés")],
        next_href="page-2.html",
    )
    listed, next_url = parse_startlists_listing_page(html, BASE_URL)
    assert listed == [ListedStartlist(
        page_id="38949",
        publication_date="2026-10-14",
        url=BASE_URL + "38949-noellet.html",
        title="Noëllet 17 octobre 2026 engagés",
    )]
    assert next_url == BASE_URL + "page-2.html"


def test_incomplete_entry_is_left_out():
    html = listing_page([
        entry("1", None, "1-a.html", "A"),
        entry("2", "01/09/2026", None, "B"),
        entry("3", "01/09/2026", "3-c.html", None),
    ])
    listed, _ = parse_startlists_listing_page(html, BASE_URL)
    assert [(s.page_id, s.title) for s in listed] == [("3", None)]


def test_last_listing_page_has_no_next_page():
    html = listing_page([entry("1", "01/09/2026", "1-a.html", "A")])
    assert parse_startlists_listing_page(html, BASE_URL)[1] is None


def test_page_without_listing():
    assert parse_startlists_listing_page("<html><body></body></html>", BASE_URL) == ([], None)


def test_listing_requests_each_page_and_extracts_each_entry(monkeypatch):
    pages = {
        BASE_URL: listing_page(
            [entry("2", "02/09/2026", "2-b.html", "B"), entry("1", "28/12/2025", "1-a.html", "A")],
            next_href="page-2.html",
        ),
        BASE_URL + "page-2.html": listing_page([entry("0", "15/08/2025", "0-z.html", "Z")]),
    }
    requested, extracted = [], []

    def fake_try_get(client, url):
        requested.append(url)
        return httpx.Response(200, text=pages[url])

    monkeypatch.setattr(startlists, "road_startlists_url", lambda: BASE_URL)
    monkeypatch.setattr(startlists, "try_get", fake_try_get)
    monkeypatch.setattr(
        startlists, "extract_startlists_from_organization_page",
        lambda client, season, code, url: extracted.append((season, code, url)),
    )
    startlists.extract_startlists_pages_from_search_url(client=None)
    assert requested == [BASE_URL, BASE_URL + "page-2.html"]
    assert extracted == [
        (2026, "2", BASE_URL + "2-b.html"),
        (2025, "1", BASE_URL + "1-a.html"),
        (2025, "0", BASE_URL + "0-z.html"),
    ]
