import json
import re

from bs4 import BeautifulSoup
from bs4.element import Tag
from pathlib import Path
from typing import Any
from access_it.common.text import normalize_string_and_fold_case
from access_it.common.date import convert_date
from access_it.etl.extract.cache import CACHE_DIR


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


def get_race_html_files() -> list[Path]:
    return sorted(CACHE_DIR.rglob("*.html"))


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


def get_page_elements(bs: BeautifulSoup) -> dict[str, str]:
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


def parse_organisation_page(html: str) -> dict[str, Any]:
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
    data = data | get_page_elements(bs)
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
