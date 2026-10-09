import json
import re

from bs4 import BeautifulSoup
from bs4.element import Tag
from pathlib import Path
from typing import Any
from access_it.common.text import normalize_string_and_fold_case, collapse_spaces
from access_it.common.date import convert_date, MONTH_CONVERT
from access_it.etl.extract.cache import RESULTS_DIR, STARTLISTS_DIR


TRANSLATIONS = {
    "RANG": "finish_rank",
    "NOM": "last_name",
    "PRENOM": "first_name",
    "UCIID": "uci_id",
    "CLUB": "club",
    "N° d'épreuve": "organization_code",
    "Saison": "season",
    "Type de compétition": "race_type",
    "Organisateur": "organizer",
    "Durée": "duration",
    "Code épreuve": "race_code"
}


def get_text_safe(tag: Tag | None) -> str | None:
    if tag is None:
        page_element = None
    else:
        page_element = tag.get_text(strip=True)
    return page_element


def get_results_html_files() -> list[Path]:
    return sorted(RESULTS_DIR.rglob("*.html"))


def parse_clubs_in_organisation_page(html: str) -> list[str]:
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


def get_elements_from_results_page(bs: BeautifulSoup) -> dict[str, str]:
    data = {}
    for blk in bs.find_all(name="div", class_="info-principale"):
        key = blk.find(name="div", class_="titreValeur-titre")
        value = blk.find(name="div", class_="titreValeur-valeur")
        key = get_text_safe(key)
        value = get_text_safe(value)
        key2 = TRANSLATIONS[key]
        if key and value:
            data[key2] = value
            if key2 == "season":
                try:
                    data[key2] = int(value)
                except ValueError:
                    raise ValueError(f"'season' value ({value}) not convertible to int")
    return data


def parse_results_from_organization_page(html: str) -> dict[str, Any]:
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
        normalized_ranking_name = normalize_string_and_fold_case(ranking_name).strip()
        if (
            len(rankings) > 1
            and any([normalized_ranking_name.startswith(n) for n in ["femme", "dame"]])
        ):
            continue
        try:
            cols = ["RANG", "NOM", "PRENOM", "UCIID", "CLUB"]
            ranking_data = [
                {TRANSLATIONS[k]: int(row[k]) if k == "RANG" else row[k] for k in cols}
                for row in ranking["resultats"]
            ]
            data["rankings"][ranking_id] = {"name": ranking_name, "data": ranking_data}
        except KeyError:
            pass
    return data


def get_rankings(html: str) -> list[dict]:
    m = re.compile(pattern=r"var resultatsJson = (\{.*?\});", flags=re.S).search(html)
    if m is None:
        raise ValueError("resultatsJson not found")
    return json.loads(m.group(1))["grilles"]


def get_startlists_html_files() -> list[Path]:
    return sorted(STARTLISTS_DIR.rglob("*.html"))


def parse_startlists_from_organization_page(html: str) -> dict[str, Any]:
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

    months_org = [m for m in list(MONTH_CONVERT.keys())]
    months = [normalize_string_and_fold_case(m) for m in months_org]
    words_org = collapse_spaces(title).split()
    words = [normalize_string_and_fold_case(w.replace(",", "")) for w in words_org]
    i = 0
    month = ""
    name = title
    while i < len(words):
        word = words[i]
        if word in months:
            month = MONTH_CONVERT[months_org[months.index(word)]]
            break
        i += 1
    if month == "":
        date = fallback_date
    else:
        if words[i - 2] == "et":
            day = words[i - 3].replace("1er", "1").zfill(2)
            name = " ".join(words_org[: i - 3])
        else:
            j = 1
            while i - j >= 0:
                try:
                    int(words[i - j].replace("1er", "1"))
                except ValueError:
                    j -= 1
                    break
                j += 1
            day = words[i - j].replace("1er", "1").zfill(2)
            name = " ".join(words_org[: i - j])
        if words[i + 1] == "et":
            year = words[i + 4]
        else:
            year = words[i + 1]
        try:
            int(year)
            int(day)
            date = f"{year:4s}-{month:2s}-{day:2s}"
        except ValueError:
            date = fallback_date

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
                    heading = table.find_previous_sibling(["h2", "h3"])
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
        "fallback_date": fallback_date,
        "name": name,
        "startlists": startlists
    }

    return data
