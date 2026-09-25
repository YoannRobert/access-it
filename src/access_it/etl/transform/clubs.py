import pandas as pd
import re

from datetime import datetime
from types import NoneType
from access_it.common.text import normalize_string_and_fold_case
from access_it.etl.extract.cache import read_html_file
from access_it.etl.extract.clubs import (
    get_departemental_committee_id,
    is_valid_french_club_id, is_individual_license,
    is_individual_club, is_foreign_license, is_foreign_club,
    INDIVIDUAL_NAME, FOREIGN_NAME, INDIVIDUAL_CLUB_ID, FOREIGN_CLUB_ID
)
from access_it.etl.transform.parse import (
    parse_clubs_in_organisation_page, get_race_html_files
)


def is_valid_season(season: int):
    return 2023 <= season <= datetime.now().year


def add_club(
        df_clubs: pd.DataFrame,
        club_id: str | None,
        club_name: str | None,
        season: int,
        departemental_committees: pd.DataFrame | list[dict],
        verbose: bool = False
    ) -> pd.DataFrame:
    df = df_clubs.copy()
    if club_id is None or club_name is None:
        return df
    if not is_valid_season(season):
        raise ValueError(f"Invalid season: {season}")

    if club_id in df["club_id"].values:
        if verbose:
            print(f">>>>>>> Club {club_id} already exists in database")
        changed = False
        mask_club = df["club_id"] == club_id
        dfi = df[mask_club].iloc[0]
        db_club_name = dfi["name"]
        db_min_year = dfi["min_year"]
        db_max_year = dfi["max_year"]
        db_alt_names = dfi["alternative_names"].split(",")
        if not isinstance(db_club_name, str):
            raise TypeError(f"Invalid type of club name: {type(db_club_name)}")
        if db_alt_names == [""]:
            db_alt_names = []
        n_club_name = normalize_string_and_fold_case(club_name)
        if n_club_name != normalize_string_and_fold_case(db_club_name):
            alt_name_found = False
            for alt_names in db_alt_names:
                n_alt_name = normalize_string_and_fold_case(alt_names)
                if n_club_name == n_alt_name:
                    alt_name_found = True
                    break
            if not alt_name_found:
                db_alt_names.append(club_name)
                changed = True
        if db_min_year > season:
            db_min_year = season
            changed = True
        if db_max_year < season:
            db_max_year = season
            changed = True
        if changed:
            df.loc[mask_club, "min_year"] = db_min_year
            df.loc[mask_club, "max_year"] = db_max_year
            df.loc[mask_club, "alternative_names"] = ",".join(db_alt_names)
            if verbose:
                print("Club updated:", df.loc[mask_club, :])
    elif is_valid_french_club_id(club_id):
        if verbose:
            print(f">>>>>>> {club_id} is a valid French club ID")
        cd_id = get_departemental_committee_id(club_id, departemental_committees)
        df_club = pd.DataFrame(
            [
                {
                    "club_id": club_id,
                    "name": club_name,
                    "departemental_committee_id": cd_id,
                    "min_year": season,
                    "max_year": season,
                    "alternative_names": "",
                }
            ]
        )
        df = pd.concat([df, df_club], ignore_index=True)
        if verbose:
            print("Club added:", df.tail(1))
    else:
        if verbose:
            print(f">>>>>>> {club_id} NOT IN DATABASE AND NOT A VALID FRENCH CLUB ID")
    return df


def parse_club_text(text: str | None) -> tuple[str | None, str | None]:
    if text is None:
        return None, None
    RE_CLUB = re.compile(r"^(?:(\d{7})\s*-?\s*)?(.*)$")
    m = RE_CLUB.match(text.strip())
    if m is None:
        print(f"In parse_club_text: ValueError was raised, text={text}")
        raise ValueError(f"Club not found in {text}")
    club_id, club_name = m.group(1), m.group(2).strip()
    return club_id, club_name


def identify_club(
        club_id: str | None,
        club_name: str | None,
        df_clubs: pd.DataFrame,
    ) -> tuple[bool, str | None, str | None]:
    add_this_club = False
    df = df_clubs.copy()
    if is_valid_french_club_id(club_id, include_specific_cases=False):
        if club_id in df["club_id"].values:
            club_name = df[df["club_id"] == club_id]["name"].values[0]
            add_this_club = True
        elif is_individual_license(club_id) or is_individual_club(club_name):
            club_id = INDIVIDUAL_CLUB_ID
            club_name = INDIVIDUAL_NAME
        elif is_foreign_license(club_id) or is_foreign_club(club_name):
            club_id = FOREIGN_CLUB_ID
            club_name = FOREIGN_NAME
        else:
            add_this_club = True
    else:
        if club_name is None:
            return False, None, None
        n_club_name = normalize_string_and_fold_case(club_name)
        mask_names = df["name"].apply(normalize_string_and_fold_case) == n_club_name
        mask_alt_names = df["alternative_names"].str.split(",") \
            .apply(
                lambda names: n_club_name in [
                    normalize_string_and_fold_case(n.strip())
                    for n in names
                ]
            )
        if is_individual_club(club_name):
            club_id = INDIVIDUAL_CLUB_ID
            club_name = INDIVIDUAL_NAME
        elif is_foreign_club(club_name):
            club_id = FOREIGN_CLUB_ID
            club_name = FOREIGN_NAME
        elif n_club_name.find("VC CHATILLONNAIS".lower()) != -1:
            # Problem with a name shared by 2 clubs: "VC CHATILLONNAIS"
            # (FFC IDs "4436087" and "5079082")
            # For now, we'll just take the first one.
            club_id, club_name = "4436087", "VC CHATILLONNAIS"
            add_this_club = True
        elif mask_names.any():
            club_id, club_name = df.loc[mask_names, ["club_id", "name"]].iloc[0]
            add_this_club = True
        elif mask_alt_names.any():
            club_id, club_name = df.loc[mask_alt_names, ["club_id", "name"]].iloc[0]
            add_this_club = True
        else:
            raise ValueError(f"Club not found (club_id={str(club_id)}, club_name={str(club_name)})")
    if not isinstance(club_id, (str, NoneType)) or not isinstance(club_name, (str, NoneType)):
        raise TypeError(
            "club_id and club_name types must be str or None, " +
            f"got {type(club_id)} and {type(club_name)}"
        )
    return add_this_club, club_id, club_name


def add_legacy_clubs(
        df_clubs: pd.DataFrame,
        departemental_committees: pd.DataFrame | list[dict],
    ) -> pd.DataFrame:
    df = df_clubs.copy()
    legacy_clubs = [
        ("4356456", "TEAM IMMO GOLFE", 2024),
        ("5304099", "RO SISTERON TEAM PAYANY", 2026),
        ("4356310", "VC DU GOLFE PLOEREN", 2024),
        ("5244257", "LOIRE & SILLON CYCLISME", 2023),
        ("4335311", "ASSOCIATION CYCLISTE NOYAL/CHATILLON FORMATION", 2024),
        ("4356478", "ALLROADS PLUMELEC", 2026),
        ("4322053", "VC QUINTINAIS", 2025),
        ("4760017", "SPRINTEUR CLUB FEMININ  - NOUVEAU", 2025),
        ("4950169", "VC SAINT JAMES", 2025),
        ("4356483", "TEAM ADRIS / LA CREPE DE BROCELIANDE / BLC", 2025),
        ("4335493", "TEAM BELO KLUB", 2025),
        ("4654012", "VC TUCQUEGNIEUX", 2025),
        ("4950217", "UC BRICQUEBEC", 2025),
        ("5249287", "SC BEAUCOUZE", 2025),
        ("5249017", "MOTO VELO CLUB BEAUFORTAIS", 2025),
        ("4927279", "AS BRETOLIENNE", 2025),
        ("4927424", "SUD DE L'EURE CYCLISME", 2025),
        ("5165207", "TARBES CYCLISTE COMPETITION", 2025),
        ("5017238", "TC LE CHATEAU D'OLERON", 2025),
        ("4895742", "VAL D'OISE CYCLISME", 2025),
        ("4927279", "AS BRETEUIL CYCLISME", 2026),
        ("4927279", "AS BRETEUILCYCLISME", 2026),
        ("4927024", "CS BONNEVILLE", 2026),
        ("4927024", "CLUB SPORTIF BONNEVILLOIS", 2026),
        ("4892411", "CSM CLAMART", 2024)
    ]
    for club_id, club_name, season in legacy_clubs:
        df = add_club(
            df_clubs=df,
            club_id=club_id,
            club_name=club_name,
            season=season,
            departemental_committees=departemental_committees
        )
    return df


def add_clubs_found_in_race_html_files(
        clubs: pd.DataFrame,
        departemental_committees: pd.DataFrame | list[dict]
    ) -> pd.DataFrame:
    for race_html_file in get_race_html_files():
        season = int(race_html_file.parent.stem)
        code = race_html_file.stem
        html = read_html_file(season, code)
        club_texts = parse_clubs_in_organisation_page(html)
        for club_text in club_texts:
            try:
                club_id, club_name = parse_club_text(club_text)
                add_this_club, club_id_2, club_name_2 = identify_club(
                    club_id=club_id, club_name=club_name, df_clubs=clubs
                )
                if add_this_club:
                    clubs = add_club(
                        df_clubs=clubs,
                        club_id=club_id_2,
                        club_name=club_name_2,
                        season=season,
                        departemental_committees=departemental_committees
                    )
            except ValueError:
                pass
    return clubs
