"""Entries of the upcoming races read on the startlist pages of the startlists website.

A startlist page holds several tables, each preceded by its heading. A table
is a race. The Access races are recognized by their heading, then the club
column and the name columns of their table by their content.
"""

import logging
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from access_it.common.access_categories import is_women_only_name
from access_it.common.regions import (
    COVERED_REGIONS, get_region_departement_codes, get_regional_committee_id
)
from access_it.common.text import normalize_string_and_fold_case
from access_it.etl.extract.clubs import is_individual_club_id
from access_it.etl.extract.constants import FOREIGN_CLUB_ID, INDIVIDUAL_CLUB_ID
from access_it.etl.extract.upcoming_startlists import UpcomingStartlistPage
from access_it.etl.transform.clubs import ClubLookup, identify_clubs
from access_it.etl.transform.parse import parse_startlists_from_organization_page
from access_it.etl.transform.riders import AffiliationLookup, RiderLookup
from access_it.etl.transform.startlists import (
    has_enough_france_values, identify_riders_on_startlist, is_gender_col,
    is_main_category_column, is_nationality_column
)

logger = logging.getLogger(__name__)


CLUB_COLUMN_MIN_RATE = 0.5
NAME_PART_MIN_RATE = 0.9
CATEGORY_COLUMN_MIN_RATE = 0.5
MIN_IDENTIFIED_RIDERS = 10

ENTRIES_COLUMNS = [
    "race_id", "race_date", "rider_id", "page_id", "page_title", "startlist_heading"
]

EXCLUDED_HEADING_PATTERN = re.compile(r"open|elite")
ACCESS_HEADING_PATTERN = re.compile(r"acc?ess?|\ba\s?[1-4]\b")
NAME_PART_PATTERN = re.compile(r"[^\W\d_]+(?:[ '-][^\W\d_]+)*")
DEPARTEMENT_CODE_PATTERN = re.compile(r"\((\d{2,3}|2[AB])\)")


@dataclass(frozen=True)
class AccessStartlist:
    """A table of a startlist page recognized as an Access race.

    Attributes:
        rank: Rank of the table among all the tables of the page, from 1.
        heading: Heading of the table.
        table: Cells of the table, one column per table column ('col0', ...).
        name_columns: Columns holding the name of the riders (one, or two for
            the last name then the first name).
        club_column: Column holding the club of the riders.
    """
    rank: int
    heading: str
    table: pd.DataFrame
    name_columns: tuple[str, ...]
    club_column: str


def is_access_startlist_heading(heading: str) -> bool:
    """Whether the heading of a startlist table designates an Access race.

    The heading is compared without case nor accents. A heading mentioning Open
    or Elite, or designating women only (see is_women_only_name), is refused.
    Otherwise it is accepted if it mentions Access (or a misspelling such as
    "acces") or an Access subcategory written as a word ("A3-A4", "A 3").

    Args:
        heading: Heading of the table.

    Returns:
        True if the table is an Access race.
    """
    normalized = normalize_string_and_fold_case(heading)
    if EXCLUDED_HEADING_PATTERN.search(normalized) or is_women_only_name(heading):
        return False
    return ACCESS_HEADING_PATTERN.search(normalized) is not None


def _fold_accents_and_separators(text: str) -> str:
    """Text without accents, hyphens and apostrophes read as spaces, case kept."""
    text = "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", re.sub(r"[-'’]", " ", text))


def find_departement_code(description: str, departements: pd.DataFrame) -> str | None:
    """Find the departement of the races of a startlist page in its description.

    The departement is first searched as a code between parentheses ("(44)")
    found in the departements table. Without a single such code, it is searched
    by its name, without accents, hyphens nor apostrophes, from the longest name
    to the shortest one (a matched name is not matched again by a shorter one),
    the name having to start with a capital letter in the description.

    Args:
        description: Description of the startlist page.
        departements: Departements (departement_code, departement_name).

    Returns:
        The departement code, None if no departement or several departements
        are found.
    """
    codes = set(departements["departement_code"])
    found_codes = {c for c in DEPARTEMENT_CODE_PATTERN.findall(description) if c in codes}
    if len(found_codes) == 1:
        return found_codes.pop()
    if found_codes:
        return None
    names = sorted(
        (
            (_fold_accents_and_separators(name), code)
            for code, name in zip(
                departements["departement_code"], departements["departement_name"]
            )
        ),
        key=lambda name_and_code: -len(name_and_code[0]),
    )
    text = _fold_accents_and_separators(description)
    found_codes = set()
    for name, code in names:
        pattern = re.compile(r"\b" + re.escape(name) + r"\b", re.IGNORECASE)
        for match in pattern.finditer(text):
            if match.group(0)[0].isupper():
                found_codes.add(code)
                text = text[:match.start()] + "#" * len(match.group(0)) + text[match.end():]
    return found_codes.pop() if len(found_codes) == 1 else None


def compute_club_rate(s: pd.Series, clubs: ClubLookup) -> float:
    """Share of the cells of a column holding a club identified in the clubs table.

    The cells of individual licensees are left out of the count, and neither
    their pseudo-clubs nor the foreign club count as identified.

    Args:
        s: Cells of the column (None when empty).
        clubs: Clubs table.

    Returns:
        The identified clubs over the non-empty cells that are not individual
        licensees, 0 if there is none.
    """
    club_ids = identify_clubs(s.where(s.notna(), None), clubs)
    individual = club_ids.map(is_individual_club_id)
    identified = club_ids.notna() & ~individual & (club_ids != FOREIGN_CLUB_ID)
    count = int(s.notna().sum()) - int(individual.sum())
    return float(identified.sum() / count) if count > 0 else 0.0


def find_club_column(table: pd.DataFrame, clubs: ClubLookup) -> str | None:
    """Find the column of a startlist table holding the club of the riders.

    Args:
        table: Cells of the table.
        clubs: Clubs table.

    Returns:
        The column with the highest club rate (see compute_club_rate), the
        leftmost one on a tie, None if this rate is below CLUB_COLUMN_MIN_RATE.
    """
    best_column, best_rate = None, 0.0
    for column in table.columns:
        rate = compute_club_rate(table[column], clubs)
        if rate > best_rate:
            best_column, best_rate = column, rate
    return best_column if best_rate >= CLUB_COLUMN_MIN_RATE else None


def is_name_part_column(s: pd.Series) -> bool:
    """Whether a column holds a part of the name of the riders (e.g. the first name).

    Args:
        s: Cells of the column (None when empty).

    Returns:
        False for a gender, nationality or category column; otherwise True if
        at least NAME_PART_MIN_RATE of the non-empty cells are made of letters
        only, separated by a space, a hyphen or an apostrophe.
    """
    values = s.dropna()
    if values.empty:
        return False
    if (
            is_gender_col(s)
            or is_nationality_column(s)
            or has_enough_france_values(s)
            or is_main_category_column(s, min_ratio=CATEGORY_COLUMN_MIN_RATE)
    ):
        return False
    is_name_part = values.map(lambda v: NAME_PART_PATTERN.fullmatch(v) is not None)
    return float(is_name_part.mean()) >= NAME_PART_MIN_RATE


def find_name_columns(table: pd.DataFrame, club_column: str) -> list[str]:
    """Find the columns of a startlist table holding the name of the riders.

    Args:
        table: Cells of the table.
        club_column: Club column of the table.

    Returns:
        The first two columns (last name then first name) if the second one is
        not the club column and holds a part of the name (see
        is_name_part_column), the first column alone otherwise.
    """
    columns = list(table.columns)
    if (
            len(columns) > 1
            and columns[1] != club_column
            and is_name_part_column(table[columns[1]])
    ):
        return columns[:2]
    return columns[:1]


def find_access_startlists(
        startlists: dict[str, list[dict]],
        clubs: ClubLookup
    ) -> list[AccessStartlist]:
    """Find the Access races of a startlist page and the columns of their tables.

    A table is kept if its heading designates an Access race (see
    is_access_startlist_heading), if it has rows and if its club column is
    found (see find_club_column).

    Args:
        startlists: Tables of the page by heading, as read by
            parse_startlists_from_organization_page.
        clubs: Clubs table.

    Returns:
        The Access races of the page, in the order of the page.
    """
    access_startlists = []
    for rank, (heading, rows) in enumerate(startlists.items(), start=1):
        if not is_access_startlist_heading(heading) or not rows:
            continue
        table = pd.DataFrame(rows)
        club_column = find_club_column(table, clubs)
        if club_column is None:
            continue
        access_startlists.append(AccessStartlist(
            rank=rank,
            heading=heading,
            table=table,
            name_columns=tuple(find_name_columns(table, club_column)),
            club_column=club_column,
        ))
    return access_startlists


def get_covered_departement_codes(
        departemental_committees: pd.DataFrame,
        regional_committees: pd.DataFrame
    ) -> set[str]:
    """Codes of the departements of the covered regions (see COVERED_REGIONS)."""
    return {
        code
        for region in COVERED_REGIONS
        for code in get_region_departement_codes(
            departemental_committees, get_regional_committee_id(regional_committees, region)
        )
    }


def identify_startlist_riders(
        startlist: AccessStartlist,
        race_date: pd.Timestamp,
        clubs: ClubLookup,
        riders: RiderLookup,
        affiliations: AffiliationLookup
    ) -> list[str]:
    """Identify the riders of an Access race from their name and club.

    The name is the name column, or the two name columns joined by a space;
    a row without name is left out. An empty club cell is that of an
    individual licensee (INDIVIDUAL_CLUB_ID), searched among all the
    pseudo-clubs of individual licensees; a row whose club is not identified
    is left out.

    Args:
        startlist: Access race of a startlist page.
        race_date: Race date.
        clubs: Clubs table.
        riders: Riders table.
        affiliations: Affiliations table.

    Returns:
        The IDs of the identified riders, without duplicates, in the order of
        the table.
    """
    table = startlist.table
    names = table[list(startlist.name_columns)].apply(
        lambda row: " ".join(v.strip() for v in row if isinstance(v, str) and v.strip()),
        axis=1,
    )
    club_texts = table[startlist.club_column]
    club_ids = identify_clubs(club_texts.where(club_texts.notna(), None), clubs)
    club_ids = club_ids.where(club_texts.notna(), INDIVIDUAL_CLUB_ID)
    rows = pd.DataFrame({"full_name": names, "club_id": club_ids})
    rows = rows[(rows["full_name"] != "") & rows["club_id"].notna()]
    if rows.empty:
        return []
    rows = identify_riders_on_startlist(
        rows, riders, affiliations, on_date=race_date, search_individuals=True
    )
    return list(dict.fromkeys(rows["rider_id"].dropna()))


def build_upcoming_entries(
        pages: Sequence[UpcomingStartlistPage],
        clubs: pd.DataFrame,
        riders: pd.DataFrame,
        affiliations: pd.DataFrame,
        departements: pd.DataFrame,
        departemental_committees: pd.DataFrame,
        regional_committees: pd.DataFrame
    ) -> pd.DataFrame:
    """Build the entries of the upcoming races from their startlist pages.

    A page that cannot be read is skipped with a warning. A page whose
    departement is found outside the covered regions is left out; a page
    whose departement is not found is kept. Each Access race of a kept page
    (see find_access_startlists) gives its identified riders (see
    identify_startlist_riders), and is kept if it has at least
    MIN_IDENTIFIED_RIDERS of them.

    Args:
        pages: Startlist pages of the upcoming races.
        clubs: Clubs table.
        riders: Riders table.
        affiliations: Affiliations table.
        departements: Departements table.
        departemental_committees: Departemental committees table.
        regional_committees: Regional committees table.

    Returns:
        One row per race and identified rider, with race_id
        ("vpc-<page ID>-<rank of the table>"), race_date (datetime64[ns]),
        rider_id, page_id, page_title (title of the page as listed) and
        startlist_heading, in the order of the pages and of their tables.
    """
    covered_codes = get_covered_departement_codes(departemental_committees, regional_committees)
    club_lookup = ClubLookup(clubs)
    rider_lookup = RiderLookup(riders)
    affiliation_lookup = AffiliationLookup(affiliations)
    records = []
    for page in pages:
        try:
            data = parse_startlists_from_organization_page(page.html)
        except ValueError as error:
            logger.warning(f"Startlist page {page.page_id} skipped (unreadable: {error})")
            continue
        if not data:
            logger.warning(f"Startlist page {page.page_id} skipped (no article)")
            continue
        departement_code = find_departement_code(data["description"], departements)
        if departement_code is not None and departement_code not in covered_codes:
            continue
        race_date = pd.Timestamp(page.race_date)
        for startlist in find_access_startlists(data["startlists"], club_lookup):
            rider_ids = identify_startlist_riders(
                startlist, race_date, club_lookup, rider_lookup, affiliation_lookup
            )
            if len(rider_ids) < MIN_IDENTIFIED_RIDERS:
                continue
            records.extend(
                {
                    "race_id": f"vpc-{page.page_id}-{startlist.rank}",
                    "race_date": race_date,
                    "rider_id": rider_id,
                    "page_id": page.page_id,
                    "page_title": page.title,
                    "startlist_heading": startlist.heading,
                }
                for rider_id in rider_ids
            )
    entries = pd.DataFrame(records, columns=ENTRIES_COLUMNS)
    entries["race_date"] = pd.to_datetime(entries["race_date"]).astype("datetime64[ns]")
    return entries
