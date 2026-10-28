"""Club table of the transform step: clubs found in the results, and identification of clubs.

The club table read from the FFC API is completed with former clubs
(add_legacy_clubs) and with the clubs found in the result pages; the club of
each result is then identified from its club text (club ID and/or name).
"""

import logging
import pandas as pd
import re

from datetime import datetime
from types import NoneType
from access_it.common.seasons import FIRST_SEASON
from access_it.common.text import normalize_string_and_fold_case
from access_it.etl.extract.cache import read_results_html_file
from access_it.etl.extract.clubs import (
    get_departemental_committee_id, get_individual_license_club_name,
    is_valid_french_club_id, is_individual_license,
    is_individual_club, is_foreign_license, is_foreign_club
)
from access_it.etl.extract.constants import (
    INDIVIDUAL_NAME, FOREIGN_NAME, INDIVIDUAL_CLUB_ID, FOREIGN_CLUB_ID
)
from access_it.etl.transform.parse import (
    parse_clubs_in_organisation_page, get_results_html_files
)

logger = logging.getLogger(__name__)


def is_valid_season(season: int):
    """Whether the season is between FIRST_SEASON and the current year."""
    return FIRST_SEASON <= season <= datetime.now().year


def add_club(
        df_clubs: pd.DataFrame,
        club_id: str | None,
        club_name: str | None,
        season: int,
        departemental_committees: pd.DataFrame | list[dict],
        verbose: bool = False
    ) -> pd.DataFrame:
    """Add a club to the club table, or update it if it already exists.

    An existing club gets the name read as an alternative name (when it
    differs from its name and alternative names, ignoring case and accents),
    and its year range is extended to the season. An unknown club is added
    only if its ID is a valid French club ID, or the ID of the individual
    licensees of a committee (ending with 800); otherwise the table is
    returned unchanged. The pseudo-club of the individual licensees of a
    committee is always named "Individuel <departement code>", whatever the
    name read (no alternative name).

    Args:
        df_clubs: Club table (club_id, name, departemental_committee_id,
            min_year, max_year, alternative_names). It is not modified.
        club_id: FFC club ID (7 digits), or None.
        club_name: Club name as read in the results, or None.
        season: Season in which the club was observed.
        departemental_committees: Departemental committees, used to find
            the committee of a new club.
        verbose: Whether to log (level INFO) the changes made.

    Returns:
        A new club table including the change, or a copy of `df_clubs`
        if `club_id` or `club_name` is None.

    Raises:
        ValueError: If the season is outside FIRST_SEASON to the current year, or
            if the departemental committee of a new club is not found.
    """
    df = df_clubs.copy()
    if club_id is None or club_name is None:
        return df
    if not is_valid_season(season):
        raise ValueError(f"Invalid season: {season}")
    if is_individual_license(club_id):
        club_name = get_individual_license_club_name(club_id, departemental_committees)

    if club_id in df["club_id"].values:
        if verbose:
            logger.info(f">>>>>>> Club {club_id} already exists in database")
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
                logger.info(f"Club updated: {df.loc[mask_club, :]}")
    elif is_valid_french_club_id(club_id) or is_individual_license(club_id):
        if verbose:
            logger.info(f">>>>>>> {club_id} is a valid French club ID")
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
            logger.info(f"Club added: {df.tail(1)}")
    else:
        if verbose:
            logger.info(f">>>>>>> {club_id} NOT IN DATABASE AND NOT A VALID FRENCH CLUB ID")
    return df


RE_CLUB = re.compile(r"^(?:(\d{7})\s*-?\s*)?(.*)$")


def parse_club_text(text: str | None) -> tuple[str | None, str | None]:
    """Split a club text of the results into club ID and club name.

    Examples: "5244001 - VC NANTAIS" gives ("5244001", "VC NANTAIS"), and
    "VC NANTAIS" gives (None, "VC NANTAIS").

    Args:
        text: Club text, or None.

    Returns:
        The club ID (7 digits at the start of the text, or None) and the club
        name (whitespace collapsed), or (None, None) if `text` is None.
    """
    if text is None:
        return None, None
    text = " ".join(text.split())
    m = RE_CLUB.match(text.strip())
    if m is None:
        logger.error(f"In parse_club_text: ValueError was raised, text={text}")
        raise ValueError(f"Club not found in {text}")
    club_id, club_name = m.group(1), m.group(2).strip()
    return club_id, club_name


def _fold_alternative_names(alternative_names: str) -> list[str]:
    """Normalized alternative names, as compared by `identify_club`."""
    return [
        normalize_string_and_fold_case(name.strip())
        for name in " ".join(alternative_names.split()).split(",")
    ]


class ClubLookup:
    """Indexes over the club table, built once and queried many times.

    Replaces the normalization of every club name previously done at every
    call of `identify_club`. When several clubs match, the first one in table
    order is returned, except for an ambiguous name (exact name or alternative
    name of several clubs, see `is_ambiguous`).
    """

    def __init__(self, df_clubs: pd.DataFrame):
        """Build the indexes from the club table (club_id, name, alternative_names)."""
        self.club_ids: list = []
        self.names: list[str] = []
        self.collapsed_names: list[str] = []
        self.folded_names: list[str] = []
        self.raw_alternative_names: list[str] = []
        self.folded_alternative_names: list[list[str]] = []
        self.position_by_id: dict = {}
        self.position_by_folded_name: dict[str, int] = {}
        self.position_by_folded_alternative_name: dict[str, int] = {}
        self.club_ids_by_folded_name: dict[str, set] = {}  # names and alternative names
        for club_id, name, alternative_names in zip(
                df_clubs["club_id"], df_clubs["name"], df_clubs["alternative_names"]
        ):
            self._append(club_id, name, alternative_names)

    def _add_name_owner(self, folded_name: str, club_id) -> None:
        """Record that the (normalized) name belongs to the club."""
        if folded_name:
            self.club_ids_by_folded_name.setdefault(folded_name, set()).add(club_id)

    def is_ambiguous(self, folded_name: str) -> bool:
        """Whether the name (or alternative name) belongs to several clubs."""
        return len(self.club_ids_by_folded_name.get(folded_name, ())) > 1

    def _append(self, club_id, name: str, alternative_names: str) -> None:
        """Add a club at the end of the indexes."""
        position = len(self.club_ids)
        collapsed_name = " ".join(name.split())
        folded_name = normalize_string_and_fold_case(collapsed_name)
        folded_alternative_names = _fold_alternative_names(alternative_names)
        self.club_ids.append(club_id)
        self.names.append(name)
        self.collapsed_names.append(collapsed_name)
        self.folded_names.append(folded_name)
        self.raw_alternative_names.append(alternative_names)
        self.folded_alternative_names.append(folded_alternative_names)
        # setdefault keeps the first position, as .iloc[0] did on a boolean mask
        self.position_by_id.setdefault(club_id, position)
        self.position_by_folded_name.setdefault(folded_name, position)
        for folded_alternative_name in folded_alternative_names:
            self.position_by_folded_alternative_name.setdefault(folded_alternative_name, position)
        self._add_name_owner(folded_name, club_id)
        for folded_alternative_name in folded_alternative_names:
            self._add_name_owner(folded_alternative_name, club_id)

    def _rebuild_alternative_name_index(self) -> None:
        """Rebuild the indexes of the alternative names and of the name owners."""
        self.position_by_folded_alternative_name = {}
        self.club_ids_by_folded_name = {}
        for position, folded_alternative_names in enumerate(self.folded_alternative_names):
            club_id = self.club_ids[position]
            self._add_name_owner(self.folded_names[position], club_id)
            for folded_alternative_name in folded_alternative_names:
                self.position_by_folded_alternative_name.setdefault(
                    folded_alternative_name, position
                )
                self._add_name_owner(folded_alternative_name, club_id)

    def sync(self, df_clubs: pd.DataFrame, club_id: str | None) -> None:
        """Apply the changes made by `add_club` to the club `club_id` of `df_clubs`.

        `add_club` either appends new clubs at the end of the table or updates
        the alternative names of an existing club (names and positions never change).
        """
        for position in range(len(self.club_ids), len(df_clubs)):
            row = df_clubs.iloc[position]
            self._append(row["club_id"], row["name"], row["alternative_names"])
        position = self.position_by_id.get(club_id)
        if position is None:
            return
        alternative_names = df_clubs["alternative_names"].iat[position]
        if alternative_names != self.raw_alternative_names[position]:
            self.raw_alternative_names[position] = alternative_names
            self.folded_alternative_names[position] = _fold_alternative_names(alternative_names)
            self._rebuild_alternative_name_index()

    def find_first_club_containing(self, folded_name: str) -> int | None:
        """Position of the first club whose name or an alternative name contains `folded_name`."""
        for position, (name, alternative_names) in enumerate(
                zip(self.folded_names, self.folded_alternative_names)
        ):
            if folded_name in name or any(folded_name in n for n in alternative_names):
                return position
        return None


def identify_club(
        club_id: str | None,
        club_name: str | None,
        df_clubs: pd.DataFrame | ClubLookup,
    ) -> tuple[bool, str | None, str | None]:
    """Identify a club from its ID and/or name.

    The ID of an individual license (ending with 800) gives the pseudo-club of
    the individual licensees of its committee; the name "Individuel" without
    this ID gives the pseudo-club of unknown committee (INDIVIDUAL_CLUB_ID).
    Without a valid club ID, an empty name or an ambiguous name (shared by
    several clubs) gives an unknown club (False, None, None): the club of the
    rider may then be completed from his other results (fill_missing_club_ids).
    For repeated calls, pass a `ClubLookup` built once instead of the DataFrame.
    """
    clubs = df_clubs if isinstance(df_clubs, ClubLookup) else ClubLookup(df_clubs)
    add_this_club = False
    if is_valid_french_club_id(club_id, include_specific_cases=False):
        position = clubs.position_by_id.get(club_id)
        if position is not None:
            club_name = clubs.names[position]
            add_this_club = True
        elif is_individual_license(club_id):
            # Pseudo-club of the individual licensees of the committee (named by add_club)
            add_this_club = True
        elif is_individual_club(club_name):
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
        n_club_name = " ".join(n_club_name.split())
        if n_club_name == "" or clubs.is_ambiguous(n_club_name):
            return False, None, None
        if is_individual_club(club_name):
            club_id = INDIVIDUAL_CLUB_ID
            club_name = INDIVIDUAL_NAME
        elif is_foreign_club(club_name):
            club_id = FOREIGN_CLUB_ID
            club_name = FOREIGN_NAME
        else:
            position = clubs.position_by_folded_name.get(n_club_name)
            if position is None:
                position = clubs.position_by_folded_alternative_name.get(n_club_name)
            if position is None and len(n_club_name) >= 10:
                position = clubs.find_first_club_containing(n_club_name)
            if position is None:
                raise ValueError(
                    f"Club not found (club_id={str(club_id)}, club_name={str(club_name)})"
                )
            # The returned name has its whitespace collapsed
            club_id, club_name = clubs.club_ids[position], clubs.collapsed_names[position]
            add_this_club = True
    if not isinstance(club_id, (str, NoneType)) or not isinstance(club_name, (str, NoneType)):
        raise TypeError(
            "club_id and club_name types must be str or None, " +
            f"got {type(club_id)} and {type(club_name)}"
        )
    return add_this_club, club_id, club_name


def identify_clubs(s: pd.Series, df_clubs: pd.DataFrame | ClubLookup) -> pd.Series:
    """Identify the club ID of each club text of a series (None when not identified)."""
    clubs = df_clubs if isinstance(df_clubs, ClubLookup) else ClubLookup(df_clubs)
    club_ids_out = []
    for club_text in s:
        try:
            club_id_in, club_name_in = parse_club_text(club_text)
            club_id_out = identify_club(
                club_id=club_id_in, club_name=club_name_in, df_clubs=clubs
            )[1]
        except AttributeError:
            club_id_out = None
        except ValueError:
            club_id_out = None
        club_ids_out.append(club_id_out)
    return pd.Series(club_ids_out, index=s.index)


def add_legacy_clubs(
        df_clubs: pd.DataFrame,
        departemental_committees: pd.DataFrame | list[dict],
    ) -> pd.DataFrame:
    """Add the former clubs, missing from the FFC API but found in the results.

    To add a club, append (club ID, name, a season in which it is observed)
    to the list `legacy_clubs`.

    Args:
        df_clubs: Club table.
        departemental_committees: Departemental committees.

    Returns:
        The club table including the former clubs.
    """
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
        ("4892411", "CSM CLAMART", 2024),
        ("4976078", "AC MONTIVILLIERS", 2025),
        ("4976078", "AC MONTIVILLIERS", 2026)
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
    # Indexes over the club table, kept in sync with the clubs added below
    """Add or update the clubs found in the rankings of every cached result page.

    A club identified by its ID gets the name read with the ID as an
    alternative name; clubs that cannot be identified are ignored.

    Args:
        clubs: Club table.
        departemental_committees: Departemental committees.

    Returns:
        The completed club table.
    """
    club_lookup = ClubLookup(clubs)
    for race_html_file in get_results_html_files():
        season = int(race_html_file.parent.stem)
        code = race_html_file.stem
        html = read_results_html_file(season, code)
        club_texts = parse_clubs_in_organisation_page(html)
        for club_text in club_texts:
            try:
                club_id, club_name = parse_club_text(club_text)
                add_this_club, club_id_2, club_name_2 = identify_club(
                    club_id=club_id, club_name=club_name, df_clubs=club_lookup
                )
                if add_this_club:
                    # When the club was identified by the ID read in the text, keep the
                    # name read in the text: add_club records it as an alternative name
                    # if it differs from the known name
                    name_to_store = club_name if club_id == club_id_2 else club_name_2
                    clubs = add_club(
                        df_clubs=clubs,
                        club_id=club_id_2,
                        club_name=name_to_store,
                        season=season,
                        departemental_committees=departemental_committees
                    )
                    club_lookup.sync(clubs, club_id_2)
            except ValueError:
                pass
    return clubs
