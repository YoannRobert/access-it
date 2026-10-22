"""Regions, committees and clubs read from the FFC API, and checks on club IDs."""

import logging
import httpx
import pandas as pd
import re

from datetime import datetime
from access_it.common.text import normalize_string_and_fold_case
from access_it.etl.extract.client import get_required
from access_it.etl.extract.constants import INDIVIDUAL_NAME, FOREIGN_NAME, INDIVIDUAL_CLUB_ID, FOREIGN_CLUB_ID
from access_it.etl.extract.departements import get_departement_mapping

logger = logging.getLogger(__name__)


def get_regions(client: httpx.Client) -> list[dict]:
    """Return the regions of the FFC API (label and value of each region)."""
    return get_required(client, "https://velo.ffc.fr/wp-json/sn/terms/region").json()


def get_region_bloc_data(data: dict, departements: pd.DataFrame, overseas: bool=False) -> tuple[list, list]:
    """Read the regional committee and its departemental committees in a region block.

    A departemental committee ID is the regional committee ID followed by the
    first two characters of the departement code.

    Args:
        data: Region block of the FFC API (keys 'region', 'extra_data' and
            'committees').
        departements: Departements (departement_code, departement_name), used
            to find the departement of each committee from its name. It is
            not modified.
        overseas: Unused.

    Returns:
        The regional committee (a list of one dict) and its departemental
        committees, or two empty lists if the block is incomplete (reported).

    Raises:
        IndexError: If the departement of a committee is not found.
    """
    missing_keys = [k for k in ["region", "extra_data", "committees"] if k not in data]
    if missing_keys:
        region = data.get("region")
        logger.warning(f"region block skipped, missing keys {missing_keys}: {region!r}")
        return [], []
    extra_data = data['extra_data']
    if 'id_api' not in extra_data:
        return [], []
    reg_committee_name = data['region']
    reg_committee_id = extra_data['id_api']
    if not isinstance(reg_committee_id, str):
        return [], []
    dep_committees_data = data["committees"]
    if normalize_string_and_fold_case(reg_committee_name).find("mayotte") != -1:
        dep_committees_data = [{"post_title": "CD MAYOTTE"}]
    if len(dep_committees_data) == 0:
        return [], []
    # Normalized names on a copy: the DataFrame of the caller is left unchanged
    departements = departements.assign(
        tmp_name=departements["departement_name"].apply(
            lambda x: normalize_string_and_fold_case(x).replace("-", " ")
        )
    )
    dep_committees = []
    for dep_committee_data in dep_committees_data:
        dep_committee_name = str(dep_committee_data['post_title'])
        dep_name = (
            normalize_string_and_fold_case(dep_committee_name)
            .replace("cd ", "")
            .replace("polynesie", "polynesie francaise")
            .replace("rhone-metropole de lyon", "rhone")
            .replace("-", " ")
        )
        try:
            departement_code = (
                departements
                [departements["tmp_name"] == dep_name]
                .loc[:, "departement_code"]
                .values[0]
            )
            cd_id = reg_committee_id + departement_code[:2]
            dep_committee = {
                "departemental_committee_id": cd_id,
                "name": dep_committee_name,
                "regional_committee_id": reg_committee_id,
                "departement_code": departement_code
            }
            dep_committees.append(dep_committee)
        except IndexError as e:
            logger.error(f"Can not find a department for '{dep_committee_name}'.")
            raise e
    reg_committees = [{"regional_committee_id": reg_committee_id, "name": reg_committee_name}]
    return reg_committees, dep_committees


def get_committees(client: httpx.Client, verbose: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Read the regional and departemental committees of every region from the FFC API.

    The pseudo-committees of the individual and foreign riders are added.
    Regions whose data are incomplete are skipped and reported.

    Args:
        client: HTTP client.
        verbose: Whether to print each region.

    Returns:
        The regional committees (regional_committee_id, name) and the
        departemental committees (departemental_committee_id, name,
        regional_committee_id, departement_code).
    """
    reg_committees = []
    dep_committees = []
    regions = get_regions(client=client)
    departements = get_departement_mapping(client=client)
    for region in regions:
        region_label = region["label"]
        region_value = region["value"]
        if verbose:
            logger.info(f"{region_label}")
        url = f"https://velo.ffc.fr/wp-json/sn/cpt/comite?region={region_value}"
        r = get_required(client, url)
        try:
            reg_committee_data = r.json()
            if "overseas" in reg_committee_data:
                for overseas_region_data in reg_committee_data['overseas']:
                    cur_reg_committee, cur_dep_committees = get_region_bloc_data(data=overseas_region_data, departements=departements)
                    if len(cur_reg_committee) > 0 and len(cur_dep_committees) > 0:
                        reg_committees.extend(cur_reg_committee)
                        dep_committees.extend(cur_dep_committees)
            elif "extra_data" in reg_committee_data:
                cur_reg_committee, cur_dep_committees = get_region_bloc_data(data=reg_committee_data, departements=departements)
                if len(cur_reg_committee) > 0 and len(cur_dep_committees) > 0:
                    reg_committees.extend(cur_reg_committee)
                    dep_committees.extend(cur_dep_committees)
        except KeyError as error:
            logger.warning(f"committees of region {region_label!r} skipped, missing key {error}")
            continue
    reg_committees.extend(
        [
            {
                "regional_committee_id": INDIVIDUAL_CLUB_ID[:2],
                "name": INDIVIDUAL_NAME
            },
            {
                "regional_committee_id": FOREIGN_CLUB_ID[:2],
                "name": FOREIGN_NAME
            }
        ]
    )
    dep_committees.extend(
        [
            {
                "departemental_committee_id": INDIVIDUAL_CLUB_ID[:4],
                "name": INDIVIDUAL_NAME,
                "regional_committee_id": INDIVIDUAL_CLUB_ID[:2],
                "departement_code": INDIVIDUAL_CLUB_ID[2:4]
            },
            {
                "departemental_committee_id": FOREIGN_CLUB_ID[:4],
                "name": FOREIGN_NAME,
                "regional_committee_id": FOREIGN_CLUB_ID[:2],
                "departement_code": FOREIGN_CLUB_ID[2:4]
            }
        ]
    )
    reg_committees = (
        pd.DataFrame(reg_committees)
        .drop_duplicates(subset="name")
        .sort_values(by="regional_committee_id")
        .reset_index(drop=True)
    )
    dep_committees = (
        pd.DataFrame(dep_committees)
        .drop_duplicates(subset="name")
        .sort_values(by="departemental_committee_id")
        .reset_index(drop=True)
    )
    return reg_committees, dep_committees


def get_clubs(
        client: httpx.Client,
        departemental_committees: pd.DataFrame | list[dict],
        verbose: bool = False,
    ) -> pd.DataFrame:
    """Read the clubs of every region from the FFC API.

    The pseudo-clubs of the individual and foreign riders are added. The year
    range of every club is set to the current year (it is extended by the
    transform step with the seasons in which the club is observed).

    Args:
        client: HTTP client.
        departemental_committees: Departemental committees, used to find the
            committee of each club from its ID.
        verbose: Whether to print each region and committee.

    Returns:
        One row per club (club_id, name, departemental_committee_id,
        min_year, max_year, alternative_names).

    Raises:
        ValueError: If a club ID is invalid or its committee is not found.
    """
    departemental_committees = pd.DataFrame(departemental_committees)
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
            logger.info(f"{region_label}")
        url = f"https://velo.ffc.fr/wp-json/sn/cpt/clubs?region={region_value}"
        r = get_required(client, url)
        try:
            data = r.json()
            if "committees" not in data:
                continue
            for dep_committee_data in data['committees']:
                dep_committee_name = dep_committee_data['title']
                if verbose:
                    logger.info(f"\t{dep_committee_name}")
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
        except KeyError as error:
            logger.warning(f"clubs of region {region_label!r} skipped, missing key {error}")
            continue
    clubs.extend(
        [
            {
                "club_id": INDIVIDUAL_CLUB_ID,
                "name": INDIVIDUAL_NAME,
                "departemental_committee_id": INDIVIDUAL_CLUB_ID[:4],
                "min_year": this_year,
                "max_year": this_year,
                "alternative_names": alternative_names
            },
            {
                "club_id": FOREIGN_CLUB_ID,
                "name": FOREIGN_NAME,
                "departemental_committee_id": FOREIGN_CLUB_ID[:4],
                "min_year": this_year,
                "max_year": this_year,
                "alternative_names": alternative_names
            },
        ]
    )
    clubs = pd.DataFrame(clubs)
    this_year = datetime.now().year
    clubs["min_year"] = this_year
    clubs["max_year"] = this_year
    clubs["alternative_names"] = ""
    return clubs


def get_disciplines(client: httpx.Client) -> list[dict[str, str]]:
    """Return the disciplines of the FFC API."""
    return get_required(client, "https://velo.ffc.fr/wp-json/sn/terms/disciplines").json()


def get_departemental_committee_id(
        club_id: str,
        departemental_committees: pd.DataFrame | list[dict]
    ) -> str:
    """Return the departemental committee ID of a club (its first four digits).

    The two committee IDs of Guadeloupe (6097 and 6098) are merged into 6097.

    Args:
        club_id: FFC club ID (7 digits).
        departemental_committees: Departemental committees.

    Returns:
        The departemental committee ID.

    Raises:
        ValueError: If the club ID is invalid or the committee is not found.
    """
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
    """Whether `club_id` is a 7-digit FFC club ID.

    Args:
        club_id: Club ID, or None.
        include_specific_cases: Whether individual licenses and foreign
            licenses are rejected too.
    """
    if club_id is None:
        return False
    if include_specific_cases:
        if is_foreign_license(club_id) or is_individual_license(club_id):
            return False
    return bool(re.fullmatch(r"\d{7}", club_id))


def is_individual_license(club_id: str | None) -> bool:
    """Whether the club ID is that of an individual license (ending with 800)."""
    if club_id is None:
        return False
    return club_id.endswith("800")


def is_individual_club(club_name: str | None) -> bool:
    """Whether the club name is that of individual licenses ('Individuel')."""
    if club_name is None:
        return False
    return normalize_string_and_fold_case(club_name).find("individuel") != -1


def is_foreign_license(club_id: str | None) -> bool:
    """Whether the club ID is that of a foreign license (starting with 00)."""
    if club_id is None:
        return False
    return club_id.startswith("00")


def is_foreign_club(club_name: str | None) -> bool:
    """Whether the club name is that of foreign riders ('Etranger', 'Licenciés UCI', ...)."""
    if club_name is None:
        return False
    foreign_names = ["etranger", "licencies uci", "autres federations"]
    return normalize_string_and_fold_case(club_name) in foreign_names
