"""Parsing of the cached HTML pages: FFC result pages and startlist pages."""

import json
import re

from bs4 import BeautifulSoup
from bs4.element import Tag
from pathlib import Path
from typing import Any
from access_it.common.access_categories import is_women_only_name
from access_it.common.text import collapse_spaces
from access_it.common.date import convert_date, parse_startlist_title
from access_it.common.html import TRANSLATIONS, get_elements_from_results_page, get_text_safe
from access_it.etl.extract.cache import RESULTS_DIR, STARTLISTS_DIR


def get_results_html_files(results_dir: Path | None = None) -> list[Path]:
    """HTML files of the kept result pages of the cache, sorted (RESULTS_DIR by default)."""
    return sorted((results_dir or RESULTS_DIR).rglob("*.html"))


def parse_clubs_in_organisation_page(html: str) -> list[str]:
    """Club texts found in the rankings of a result page, without duplicates."""
    try:
        rankings = get_rankings(html)
    except ValueError:
        rankings = []
    club_texts = []
    for ranking in rankings:
        for row in ranking["resultats"]:
            if "CLUB" in row:
                if (
                        row["CLUB"] is not None
                        and row["CLUB"] != ""
                        and row["CLUB"] not in club_texts
                ):
                    club_texts.append(row["CLUB"])
    return club_texts


def parse_results_from_organization_page(html: str) -> dict[str, Any]:
    """Parse a result page: general information and rankings.

    Women's rankings (see is_women_only_name) are left out, even when alone
    on the page. Rows without a numeric rank (e.g. "DNS",
    "DNF") are left out: these riders are not ranked.

    Args:
        html: HTML of the result page.

    Returns:
        A dict with discipline, race_date ('YYYY-MM-DD'), title, departement,
        the general information (see TRANSLATIONS) and rankings: ranking ID
        mapped to {'name': ranking name, 'data': rows with finish_rank,
        last_name, first_name, uci_id and club}.
    """
    bs = BeautifulSoup(html, features="html.parser")
    discipline = get_text_safe(bs.find(name="div", class_="discipline"))
    race_date = convert_date(get_text_safe(bs.find(name="div", class_="date")))
    title = get_text_safe(bs.find(name="h1", class_="titre"))
    departement = get_text_safe(bs.find(name="div", class_="localisation"))
    data: dict[str, Any] = {
        "discipline": discipline,
        "race_date": race_date,
        "title": title,
        "departement": departement,
        "rankings": {}
    }
    data = data | get_elements_from_results_page(bs)
    try:
        rankings = get_rankings(html)
    except ValueError:
        rankings = []
    for ranking in rankings:
        ranking_id = ranking["uid"]
        ranking_name = bs.find(name="a", grille=ranking_id)
        if not isinstance(ranking_name, Tag):
            continue
        ranking_name = ranking_name.get_text(strip=True)
        if is_women_only_name(ranking_name):
            continue
        try:
            cols = ["RANG", "NOM", "PRENOM", "UCIID", "CLUB"]
            # Rows without a numeric rank (e.g. 'DNS', 'DNF': rider not ranked) are left out
            ranking_data = [
                {TRANSLATIONS[k]: int(row[k]) if k == "RANG" else row[k] for k in cols}
                for row in ranking["resultats"]
                if str(row["RANG"]).strip().isdigit()
            ]
            data["rankings"][ranking_id] = {"name": ranking_name, "data": ranking_data}
        except KeyError:
            pass
    return data


def get_rankings(html: str) -> list[dict]:
    """Rankings of a result page, read in its JavaScript variable resultatsJson.

    Raises:
        ValueError: If the variable is not found in the page.
    """
    m = re.compile(pattern=r"var resultatsJson = (\{.*?\});", flags=re.S).search(html)
    if m is None:
        raise ValueError("resultatsJson not found")
    return json.loads(m.group(1))["grilles"]


def get_startlists_html_files() -> list[Path]:
    """HTML files of the kept startlist pages of the cache, sorted."""
    return sorted(STARTLISTS_DIR.rglob("*.html"))


def parse_startlists_from_organization_page(html: str) -> dict[str, Any]:
    """Parse a startlist page: race date, name and startlist tables.

    The name and the race date are read in the title and checked against the
    publication date of the page (see parse_startlist_title). Each table
    preceded by a heading is a startlist; cell values are cleaned, and the
    labels of riders without club are replaced by "Individuel". A table has
    the columns of its first row: the cells missing from a shorter row are
    None.

    Args:
        html: HTML of the startlist page.

    Returns:
        A dict with title, description, date (race date), title_date (date read
        in the title), fallback_date (publication date), name and startlists:
        heading mapped to the rows of the table ({'col0': value, ...}). An empty
        dict if the page has no article.

    Raises:
        ValueError: If the title, description or publication date is missing.
    """
    bs = BeautifulSoup(html, features="html.parser")
    title = get_text_safe(bs.find(name="h1"))
    description = get_text_safe(bs.find(name="div", class_="description"))
    fallback_date = get_text_safe(bs.find(name="div", class_="date"))
    if not isinstance(title, str):
        raise ValueError("title is not a string")
    if not isinstance(description, str):
        raise ValueError("description is not a string")
    if not isinstance(fallback_date, str):
        raise ValueError("fallback_date is not a string")
    title = collapse_spaces(title.replace("\n", " "))
    description = collapse_spaces(description.replace("\n", " "))
    fallback_date = "-".join(list(reversed(fallback_date.split("/"))))

    name, title_date, date = parse_startlist_title(title, fallback_date)

    startlists = {}
    article = bs.find(name="div", id="article")
    if article is None:
        return {}
    simple_texts = article.find_all(name="div", class_="simpleText")
    for simple_text in simple_texts:
        structured_texts = simple_text.find_all(name="div", class_="structured_text_semantique_text")
        for structured_text in structured_texts:
            code_html_elements = structured_text.find_all(name="div", class_="code_html")
            for code_html_element in code_html_elements:
                tables = code_html_element.find_all(name="table")
                for table in tables:
                    heading = table.find_previous_sibling(["h2", "h3", "h4"])
                    heading_text = get_text_safe(heading)
                    if heading_text is None:
                        continue
                    rows = table.find_all(name="tr")
                    nb_cols = len(rows[0].find_all(name="td"))
                    table_data = []
                    for row in rows:
                        row_data = {}
                        cols = row.find_all(name="td")
                        i_col = 0
                        while i_col < nb_cols:
                            # Row shorter than the first one: the missing cells are empty
                            if i_col >= len(cols):
                                row_data[f"col{i_col}"] = None
                                i_col += 1
                                continue
                            col_content = cols[i_col]
                            all_p = col_content.find_all(name="p")
                            if all_p:
                                value = ""
                                for p in all_p:
                                    p_str = get_text_safe(p)
                                    if not isinstance(p_str, str):
                                        p_str = ""
                                    value += " " + p_str
                            else:
                                value = get_text_safe(col_content)
                            if isinstance(value, str):
                                value = " ".join(value.split())  # Remove non-breaking spaces
                                value = collapse_spaces(value.strip())
                                value = value.replace("*", "").strip()
                                value = value.replace("`", "'")
                                value = value.replace("’", "'")
                                value = value.replace("‘", "'")
                                if value.startswith("-"):
                                    value = value.replace("-", "", 1).strip()
                                if value.upper() in [
                                    "INDIV", "INDV", "IND",
                                    "PASS' DÉCOUVERTE", "PASS DÉCOUVERTE",
                                    "PASS' DECOUVERTE", "PASS DECOUVERTE",
                                    "SANS CLUB", "TEMPORAIRE",
                                    "NON LICENCIÉ", "NON LICENCIE"
                                ]:
                                    value = "Individuel"
                            if value == "":
                                value = None
                            row_data[f"col{i_col}"] = value
                            i_col += 1
                        table_data.append(row_data)
                    startlists[heading_text] = table_data

    data: dict[str, Any] = {
        "title": title,
        "description": description,
        "date": date,
        "title_date": title_date,
        "fallback_date": fallback_date,
        "name": name,
        "startlists": startlists
    }

    return data
