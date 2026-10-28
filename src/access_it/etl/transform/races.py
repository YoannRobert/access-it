"""Race table: one race per Access ranking of the result pages."""

import hashlib
import pandas as pd

from pathlib import Path

from access_it.etl.extract.cache import read_results_html_file
from access_it.etl.transform.categories import (
    find_ranking_categories, convert_categories_from_dict_to_list
)
from access_it.etl.transform.parse import (
    get_results_html_files, parse_results_from_organization_page
)


def split_results_from_organization_into_races(organization_data: dict) -> list[dict]:
    """Split a parsed result page into races, one per ranking with Access categories.

    Args:
        organization_data: Parsed result page (see
            parse_results_from_organization_page).

    Returns:
        One dict per race: the information of the page, plus race_id,
        ranking_id, ranking_name, ranking_data and categories (e.g. ["A1", "A2"]).
    """
    races_data = []
    race_data_org = organization_data.copy()
    del race_data_org["rankings"]
    rankings = organization_data["rankings"]
    ranking_categories = find_ranking_categories(organization_data)
    season = organization_data["season"]
    code = organization_data["organization_code"]
    for ranking_id in ranking_categories.keys():
        ranking = rankings[ranking_id]
        current_rankin_categories = ranking_categories[ranking_id]
        if not any(current_rankin_categories.values()):
            continue
        categories = convert_categories_from_dict_to_list(current_rankin_categories)
        race_id = create_race_id(season, code, ranking_id)
        race_data = race_data_org.copy() | {
            "race_id": race_id,
            "ranking_id": ranking_id,
            "ranking_name": ranking["name"],
            "ranking_data": ranking["data"],
            "categories": categories
        }
        races_data.append(race_data)
    return races_data


def create_race_id(season: int, organisation_code: str, ranking_id: str) -> str:
    """Stable race ID: hash of the season, organization code and ranking ID."""
    key = f"{season}|{organisation_code}|{ranking_id}".encode()
    return hashlib.blake2b(key, digest_size=8).hexdigest()


def get_results_data(results_dir: Path | None = None) -> list[dict]:
    """Parse every cached result page and split it into races (rankings included).

    Args:
        results_dir: Cache directory of the result pages (default: RESULTS_DIR).
    """
    races_data = []
    for race_html_file in get_results_html_files(results_dir):
        season = int(race_html_file.parent.stem)
        code = race_html_file.stem
        html = read_results_html_file(season, code, results_dir)
        data = parse_results_from_organization_page(html)
        data_split = split_results_from_organization_into_races(data)
        races_data.extend(data_split)
    return races_data


def create_race_table(races_data: list[dict], departements: pd.DataFrame) -> pd.DataFrame:
    """Create the race table from the races data.

    Args:
        races_data: Races (see get_results_data).
        departements: Departements, to find the code of the departement of each race.

    Returns:
        One row per race: race_id, title, categories ("A1,A2"), season,
        discipline, race_date, departement_code, organization_code, race_type,
        organizer, duration, race_code.
    """
    df = pd.DataFrame(races_data)
    d, n, c = "departement", "departement_name", "departement_code"
    df[c] = df[d].apply(lambda x: departements.loc[departements[n] == x][c].values[0])
    df["categories"] = df["categories"].apply(lambda x: ",".join(x))
    columns = [
       'race_id', 'title', 'categories', 'season',
       'discipline', 'race_date', c, 'organization_code',
       'race_type', 'organizer', 'duration', 'race_code'
    ]
    return df[columns]
