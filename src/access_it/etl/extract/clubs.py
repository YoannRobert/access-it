import httpx
import pandas as pd
import re

from datetime import datetime
from access_it.common.text import normalize_string_and_fold_case
from access_it.etl.extract.departements import get_departement_mapping


def get_regions(client: httpx.Client) -> list[dict]:
    r = client.get("https://velo.ffc.fr/wp-json/sn/terms/region")
    r.raise_for_status()
    return r.json()


def get_committees(client: httpx.Client, verbose: bool = False) -> tuple[list[dict], list[dict]]:
    reg_committees = []
    dep_committees = []
    regions = get_regions(client=client)
    departements = get_departement_mapping(client=client)
    # regions = [{"value": "Ile de France", "label": "ile-de-france"}]
    for region in regions:
        region_label = region["label"]
        region_value = region["value"]
        if region_value == "outre-mer":  # because it is a duplicate of Polynésie
            continue
        if verbose:
            print(f"{region_label}")
        r = client.get(f"https://velo.ffc.fr/wp-json/sn/cpt/comite?region={region_value}")
        r.raise_for_status()
        try:
            reg_committee_data = r.json()
            if "region" not in reg_committee_data:
                continue
            reg_committee_name = reg_committee_data['region']
            if "extra_data" not in reg_committee_data:
                continue
            reg_committee_extra_data = reg_committee_data['extra_data']
            if not isinstance(reg_committee_extra_data, dict):
                continue
            if 'id_api' not in reg_committee_extra_data:
                continue
            reg_committee_id = reg_committee_extra_data['id_api']
            if not isinstance(reg_committee_id, str):
                continue
            if "committees" in reg_committee_data:
                cur_dep_committees = reg_committee_data["committees"]
                if len(cur_dep_committees) == 0:
                    if reg_committee_name.lower().find("polynésie") != -1:
                        dep_committee_name = "CD POLYNÉSIE"
                        reg_committee_id = "66"
                    else:
                        dep_committee_name = "CD " + reg_committee_name.upper()
                    cur_dep_committees = [{'post_title': dep_committee_name}]
                for dep_committee_data in cur_dep_committees:
                    dep_committee_name = str(dep_committee_data['post_title'])
                    dep_name = (
                        normalize_string_and_fold_case(dep_committee_name)
                        .replace("cd ", "")
                        .replace("polynesie", "polynesie francaise")
                        .replace("rhone-metropole de lyon", "rhone")
                        .replace("-", " ")
                    )
                    departements["tmp_name"] = departements["departement_name"].apply(
                        lambda x: normalize_string_and_fold_case(x).replace("-", " ")
                    )
                    try:
                        departement_code = (
                            departements
                            [departements["tmp_name"] == dep_name]
                            .loc[:, "departement_code"]
                            .values[0]
                        )
                        cd_id = reg_committee_id + departement_code[:2]
                        # dep_committees[cd_id] = {
                        #     "name": dep_committee_name,
                        #     "regional_committee_id": reg_committee_id,
                        #     "departement_code": departement_code
                        # }
                        dep_committee = {
                            "departemental_committee_id": cd_id,
                            "name": dep_committee_name,
                            "regional_committee_id": reg_committee_id,
                            "departement_code": departement_code
                        }
                        dep_committees.append(dep_committee)
                        if verbose:
                            print(f"\t{dep_committee_name:30s} {cd_id:4s} {departement_code:3s}")
                    except IndexError as e:
                        print(f"Can not find a department for '{dep_committee_name}'.")
                        raise e
            # reg_committees[reg_committee_id] = {"name": reg_committee_name}
            reg_committees.append(
                {
                    "regional_committee_id": reg_committee_id,
                    "name": reg_committee_name
                }
            )
        except KeyError:
            continue
    return reg_committees, dep_committees


def get_clubs(
        client: httpx.Client,
        departemental_committees: list[dict],
        verbose: bool = False,
    ) -> pd.DataFrame:
    clubs = []
    this_year = datetime.now().year
    alternative_names = ""
    regions = get_regions(client=client)
    for region in regions:
        region_label = region["label"]
        region_value = region["value"]
        if region_value == "outre-mer":  # because it is a duplicate of Polynésie
            continue
        if verbose:
            print(f"{region_label}")
        r = client.get(f"https://velo.ffc.fr/wp-json/sn/cpt/clubs?region={region_value}")
        r.raise_for_status()
        try:
            data = r.json()
            if "committees" not in data:
                continue
            for dep_committee_data in data['committees']:
                dep_committee_name = dep_committee_data['title']
                if verbose:
                    print(f"\t{dep_committee_name}")
                for club_data in dep_committee_data['items']:
                    club_name = str(club_data['post_title'])
                    club_id = str(club_data['extra_data']['id_ffc'])
                    if not is_valid_french_club_id(club_id, include_specific_cases=False):
                        raise ValueError(f"Invalid club ID: {club_id}")
                    departemental_committee_id = get_departemental_committee_id(
                        club_id, departemental_committees
                    )
                    clubs.append(
                        {
                            "club_id": club_id,
                            "name": club_name,
                            "departemental_committee_id": departemental_committee_id,
                            "min_year": this_year,
                            "max_year": this_year,
                            "alternative_names": alternative_names
                        }
                    )
        except KeyError:
            continue
    return pd.DataFrame(clubs)


def get_disciplines(client: httpx.Client) -> list[dict[str, str]]:
    r = client.get("https://velo.ffc.fr/wp-json/sn/terms/disciplines")
    r.raise_for_status()
    return r.json()


def get_departemental_committee_id(
        club_id: str,
        departemental_committees: pd.DataFrame | list[dict]
    ) -> str:
    df = departemental_committees.copy()
    try:
        df = pd.DataFrame(df)
    except ValueError:
        raise ValueError(
            "departemental_committees must be a DataFrame or a list of dictionaries"
        )
    dep_com_ids = df["departemental_committee_id"].to_list()
    if not is_valid_french_club_id(club_id, include_specific_cases=False):
        raise ValueError(f"Invalid club ID: {club_id}")
    dep_com_id = club_id[:4]
    dep_com_id = dep_com_id.replace("6098", "6097")  # Two possibilities in Guadeloupe
    if dep_com_id not in dep_com_ids:
        raise ValueError(f"Departemental committee ID not found: {dep_com_id}")
    return dep_com_id


def is_valid_french_club_id(
        club_id: str | None,
        include_specific_cases: bool = True
    ) -> bool:
    if club_id is None:
        return False
    if include_specific_cases:
        if is_foreign_license(club_id) or is_individual_license(club_id):
            return False
    return bool(re.fullmatch(r"\d{7}", club_id))


def is_individual_license(club_id: str | None) -> bool:
    if club_id is None:
        return False
    return club_id.endswith("800")


def is_individual_club(club_name: str | None) -> bool:
    if club_name is None:
        return False
    return normalize_string_and_fold_case(club_name).find("individuel") != -1


def is_foreign_license(club_id: str | None) -> bool:
    if club_id is None:
        return False
    return club_id.startswith("00")


def is_foreign_club(club_name: str | None) -> bool:
    if club_name is None:
        return False
    foreign_names = ["etranger", "licencies uci", "autres federations"]
    return normalize_string_and_fold_case(club_name) in foreign_names
