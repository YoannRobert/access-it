import hashlib
import pandas as pd

from access_it.etl.extract.cache import read_html_file
from access_it.etl.transform.categories import (
    find_ranking_categories, convert_categories_from_dict_to_list
)
from access_it.etl.transform.parse import get_race_html_files, parse_organisation_page


def split_organization_into_races(organization_data: dict) -> list[dict]:
    races_data = []
    race_data_org = organization_data.copy()
    del race_data_org["rankings"]
    rankings = organization_data["rankings"]
    ranking_categories = find_ranking_categories(organization_data)
    season = organization_data["season"]
    code = organization_data["organization_code"]
    for ranking_id in ranking_categories.keys():
        ranking = rankings[ranking_id]
        categories = convert_categories_from_dict_to_list(ranking_categories[ranking_id])
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
    key = f"{season}|{organisation_code}|{ranking_id}".encode()
    return hashlib.blake2b(key, digest_size=8).hexdigest()


def get_race_data() -> list[dict]:
    races_data = []
    for race_html_file in get_race_html_files():
        season = int(race_html_file.parent.stem)
        code = race_html_file.stem
        html = read_html_file(season, code)
        data = parse_organisation_page(html)
        data_split = split_organization_into_races(data)
        races_data.extend(data_split)
    return races_data


def create_race_table(races_data: list[dict], departements: pd.DataFrame) -> pd.DataFrame:
    df = pd.DataFrame(races_data)
    d, n, c = "departement", "departement_name", "departement_code"
    df[c] = df[d].apply(lambda x: departements.loc[departements[n] == x][c].values[0])
    df["categories"] = df["categories"].apply(lambda x: ",".join(x))
    columns = [
       'race_id', 'title', 'categories', 'season',
       'discipline', 'date', c, 'organization_code',
       'race_type', 'organizer', 'duration', 'race_code'
    ]
    return df[columns]
