"""Committee of the individual licensees whose result pages do not give it.

The result pages give the club ID of an individual license (committee ID
followed by 800) until 2025, but mostly "Individuel" alone since 2026, which
gives the pseudo-club of unknown committee (INDIVIDUAL_CLUB_ID). For each
rider and season with such results, the committee is found, in this order:

1. imposed: the committee of the departement given by a manual correction
   (INDIVIDUAL_COMMITTEE_CORRECTIONS), checked outside the result pages;
2. observed: the committee of an individual license ID of the rider in the
   season, in any region (the most frequent one, then the most recent one);
3. observed: the same in the nearest season with such an ID (the previous
   season before the next one);
4. deduced: the region where the rider raced most in the season, then, in this
   region, the committee where he raced most; ties are broken by all his
   seasons, then by his most recent race of the season.

The places of the races come from the results of Bretagne and Pays de la
Loire, and from the result pages of the other regions (NATIONAL_RESULTS_DIR),
only read here: no race, result or rider of these pages enters the tables.
The results of INDIVIDUAL_CLUB_ID then get the pseudo-club of the committee
found, added to the club table.
"""

import logging

from collections import Counter

import pandas as pd

from access_it.common.text import normalize_string_and_fold_case
from access_it.common.uci import is_valid_uci_id
from access_it.etl.extract.clubs import (
    get_departemental_committee_id, individual_club_id_mask, is_individual_license
)
from access_it.etl.extract.constants import INDIVIDUAL_CLUB_ID, INDIVIDUAL_NAME
from access_it.etl.transform.clubs import add_club, parse_club_text

logger = logging.getLogger(__name__)

INDIVIDUAL_LICENSE_SUFFIX = "800"

# Committees of individual licensees checked outside the result pages, imposed
# before any other rule: (rider ID, season, departement code)
INDIVIDUAL_COMMITTEE_CORRECTIONS: list[tuple[str, int, str]] = [
    ("02b45996a8def6b3", 2026, "35"),
    ("c489c11e08c63539", 2026, "16"),
    ("9d4acc5b43c37a62", 2026, "72"),
    ("852440febc154132", 2026, "72"),
    ("c219da496a6e2757", 2026, "35"),
    ("20fb49c3990289f9", 2026, "56"),
    ("bb63a6cad4c9a73a", 2026, "69"),
    ("486f8cdd905750d6", 2026, "14"),
    ("c6b517427910f533", 2026, "22"),
    ("22e58a62c102fd2a", 2026, "50"),
    ("1ba892d77239c15f", 2026, "14"),
]

IMPOSED_BY_A_CORRECTION = "imposed by a correction"
OBSERVED_IN_SEASON = "observed in the season"
OBSERVED_IN_NEAREST_SEASON = "observed in the nearest season"
DEDUCED_FROM_RACES = "deduced from the places of the races"


def _text(value) -> str:
    """Stripped text of a value of the results, or "" if it is missing."""
    return value.strip() if isinstance(value, str) else ""


def _fold_names(last_name, first_name) -> tuple[str, str]:
    """Names folded (case, accents, spaces), to match the riders by names."""
    return (
        " ".join(normalize_string_and_fold_case(_text(last_name)).split()),
        " ".join(normalize_string_and_fold_case(_text(first_name)).split()),
    )


class CommitteeOfLicense:
    """Departemental committee of an individual license ID, cached (None if unknown)."""

    def __init__(self, departemental_committees: pd.DataFrame):
        self.departemental_committees = departemental_committees
        self.cache: dict[str, str | None] = {}

    def __call__(self, club_id: str | None) -> str | None:
        if not isinstance(club_id, str) or not is_individual_license(club_id):
            return None
        if club_id not in self.cache:
            try:
                self.cache[club_id] = get_departemental_committee_id(
                    club_id, self.departemental_committees
                )
            except ValueError:
                self.cache[club_id] = None
        return self.cache[club_id]


def collect_individual_observations(
        rider_x_race_data: pd.DataFrame,
        races: pd.DataFrame,
        national_races_data: list[dict],
        departements: pd.DataFrame,
        departemental_committees: pd.DataFrame
    ) -> pd.DataFrame:
    """Results of the individual licensees, with the place of the race and the observed committee.

    The riders are those with at least one result of an individual licensee.
    All their results are taken, with a club or not: those of Bretagne and Pays
    de la Loire, and those of the other regions, matched by UCI ID, or by
    names for the riders without valid UCI ID (names shared by several riders
    are ignored). The pages of the other regions already in the race table
    are skipped.

    Args:
        rider_x_race_data: Results of the riders, with their rider ID.
        races: Race table (race_id, departement_code).
        national_races_data: Races of the other regions (see get_results_data).
        departements: Departements, to read the place of the races of the other regions.
        departemental_committees: Departemental committees.

    Returns:
        One row per result: rider_id, season, race_date, location (committee
        of the place of the race, or None) and observed (committee of an
        individual license ID, or None).
    """
    committee_by_departement_code = dict(zip(
        departemental_committees["departement_code"],
        departemental_committees["departemental_committee_id"]
    ))
    code_by_departement_name = dict(zip(
        departements["departement_name"], departements["departement_code"]
    ))
    committee_of_license = CommitteeOfLicense(departemental_committees)

    is_individual = individual_club_id_mask(rider_x_race_data["club_id"])
    rider_ids = set(rider_x_race_data.loc[is_individual, "rider_id"])
    own = rider_x_race_data[rider_x_race_data["rider_id"].isin(rider_ids)]
    own = own.merge(races[["race_id", "departement_code"]], on="race_id", how="left")
    rows = [
        {
            "rider_id": row.rider_id,
            "season": int(row.season),
            "race_date": pd.Timestamp(row.race_date),
            "location": committee_by_departement_code.get(row.departement_code),
            "observed": committee_of_license(row.club_id),
        }
        for row in own.itertuples()
    ]

    # Matching of the riders of the other regions
    rider_id_by_uci_id: dict[str, str] = {}
    rider_ids_by_names: dict[tuple[str, str], set] = {}
    for row in own.drop_duplicates(["rider_id", "uci_id", "last_name", "first_name"]).itertuples():
        uci_id = _text(row.uci_id)
        if is_valid_uci_id(uci_id):
            rider_id_by_uci_id[uci_id] = row.rider_id
    riders_with_uci_id = set(rider_id_by_uci_id.values())
    for row in own.drop_duplicates(["rider_id", "last_name", "first_name"]).itertuples():
        if row.rider_id not in riders_with_uci_id:
            rider_ids_by_names.setdefault(
                _fold_names(row.last_name, row.first_name), set()
            ).add(row.rider_id)

    known_race_ids = set(races["race_id"])
    n_national = 0
    for race in national_races_data:
        if race["race_id"] in known_race_ids:
            continue
        location = committee_by_departement_code.get(
            code_by_departement_name.get(race.get("departement"))
        )
        for result in race["ranking_data"]:
            uci_id = _text(result.get("uci_id"))
            if is_valid_uci_id(uci_id):
                rider_id = rider_id_by_uci_id.get(uci_id)
            else:
                candidates = rider_ids_by_names.get(
                    _fold_names(result.get("last_name"), result.get("first_name")), set()
                )
                rider_id = next(iter(candidates)) if len(candidates) == 1 else None
            if rider_id is None:
                continue
            club_text = result.get("club")
            club_id, _ = parse_club_text(club_text if isinstance(club_text, str) else None)
            rows.append({
                "rider_id": rider_id,
                "season": int(race["season"]),
                "race_date": pd.Timestamp(race["race_date"]),
                "location": location,
                "observed": committee_of_license(club_id),
            })
            n_national += 1
    logger.info(
        f"{len(rider_ids)} individual licensee(s): {len(rows) - n_national} result(s) in "
        f"Bretagne and Pays de la Loire, {n_national} result(s) in the other regions"
    )
    columns = ["rider_id", "season", "race_date", "location", "observed"]
    return pd.DataFrame(rows, columns=columns)


def _majority(counter: Counter):
    """Most frequent value, or None if there is none or a tie at the top."""
    top = counter.most_common(2)
    if not top or (len(top) == 2 and top[0][1] == top[1][1]):
        return None
    return top[0][0]


def _most_frequent_then_most_recent(observations: pd.DataFrame, column: str):
    """Most frequent value of `column`, ties broken by the most recent race."""
    values = observations.dropna(subset=[column])
    if values.empty:
        return None
    best = _majority(Counter(values[column]))
    if best is not None:
        return best
    counts = Counter(values[column])
    top_count = max(counts.values())
    tied = values[values[column].map(counts) == top_count]
    return tied.sort_values("race_date").iloc[-1][column]


def _by_place(season_rows: pd.DataFrame, all_rows: pd.DataFrame, column: str):
    """Value of `column` where the rider raced most in the season.

    Ties are broken by all his seasons, then by his most recent race of the season.
    """
    season_rows = season_rows.dropna(subset=[column])
    if season_rows.empty:
        return None
    for rows in (season_rows, all_rows.dropna(subset=[column])):
        best = _majority(Counter(rows[column]))
        if best is not None:
            return best
    return season_rows.sort_values("race_date").iloc[-1][column]


def resolve_individual_committees(
        observations: pd.DataFrame,
        pending: set[tuple[str, int]],
        region_by_committee: dict[str, str],
        imposed: dict[tuple[str, int], str] | None = None
    ) -> dict[tuple[str, int], tuple[str, str]]:
    """Find the committee of each (rider_id, season) of `pending` (see the module docstring).

    Args:
        observations: Results of the individual licensees (see collect_individual_observations).
        pending: (rider_id, season) pairs whose committee is to be found.
        region_by_committee: Regional committee ID of each departemental committee.
        imposed: Committee imposed by a correction for some (rider_id, season) pairs.

    Returns:
        (committee ID, step) of each pair found; pairs without any result are missing.
    """
    by_rider = {rider_id: rows for rider_id, rows in observations.groupby("rider_id")}
    found: dict[tuple[str, int], tuple[str, str]] = {}
    imposed = imposed or {}
    for rider_id, season in sorted(pending):
        if (rider_id, season) in imposed:
            found[(rider_id, season)] = (imposed[(rider_id, season)], IMPOSED_BY_A_CORRECTION)
            continue
        rows = by_rider.get(rider_id)
        if rows is None:
            continue
        observed = rows.dropna(subset=["observed"])
        in_season = observed[observed["season"] == season]
        committee = _most_frequent_then_most_recent(in_season, "observed")
        if committee is not None:
            found[(rider_id, season)] = (committee, OBSERVED_IN_SEASON)
            continue
        if not observed.empty:
            seasons = sorted(set(observed["season"]), key=lambda s: (abs(s - season), s > season))
            nearest = observed[observed["season"] == seasons[0]]
            found[(rider_id, season)] = (
                _most_frequent_then_most_recent(nearest, "observed"), OBSERVED_IN_NEAREST_SEASON
            )
            continue
        located = rows.dropna(subset=["location"]).copy()
        located["region"] = located["location"].map(region_by_committee)
        season_rows = located[located["season"] == season]
        region = _by_place(season_rows, located, "region")
        if region is None:
            continue
        committee = _by_place(
            season_rows[season_rows["region"] == region],
            located[located["region"] == region],
            "location"
        )
        found[(rider_id, season)] = (committee, DEDUCED_FROM_RACES)
    return found


def imposed_committees(
        pending: set[tuple[str, int]],
        departemental_committees: pd.DataFrame
    ) -> dict[tuple[str, int], str]:
    """Committees imposed by INDIVIDUAL_COMMITTEE_CORRECTIONS, for the pairs of `pending`.

    A correction whose departement has no committee, or which matches no
    (rider, season) of unknown committee, is logged (warning) and ignored.
    """
    committee_by_departement_code = dict(zip(
        departemental_committees["departement_code"],
        departemental_committees["departemental_committee_id"]
    ))
    imposed: dict[tuple[str, int], str] = {}
    unused = []
    for rider_id, season, departement_code in INDIVIDUAL_COMMITTEE_CORRECTIONS:
        committee = committee_by_departement_code.get(departement_code)
        if committee is None or (rider_id, season) not in pending:
            unused.append(f"  {rider_id}, {season}, {departement_code}")
            continue
        imposed[(rider_id, season)] = committee
    if unused:
        logger.warning(
            f"{len(unused)} committee correction(s) ignored (unknown departement, or no result "
            f"of unknown committee for the rider and season):\n" + "\n".join(unused)
        )
    return imposed


def assign_individual_committees(
        rider_x_race_data: pd.DataFrame,
        races: pd.DataFrame,
        national_races_data: list[dict],
        clubs: pd.DataFrame,
        departements: pd.DataFrame,
        departemental_committees: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Give the results of INDIVIDUAL_CLUB_ID the pseudo-club of the committee found.

    Args:
        rider_x_race_data: Results of the riders, with their rider ID.
        races: Race table.
        national_races_data: Races of the other regions (see get_results_data).
        clubs: Club table, completed with the pseudo-clubs used.
        departements: Departements.
        departemental_committees: Departemental committees.

    Returns:
        The results and the club table, both updated. The number of
        (rider, season) pairs found at each step, and of those not found, is logged.
    """
    df = rider_x_race_data.copy()
    unknown = df["club_id"] == INDIVIDUAL_CLUB_ID
    pending = set(zip(df.loc[unknown, "rider_id"], df.loc[unknown, "season"].astype(int)))
    if not pending:
        return df, clubs
    observations = collect_individual_observations(
        df, races, national_races_data, departements, departemental_committees
    )
    region_by_committee = dict(zip(
        departemental_committees["departemental_committee_id"],
        departemental_committees["regional_committee_id"]
    ))
    imposed = imposed_committees(pending, departemental_committees)
    found = resolve_individual_committees(observations, pending, region_by_committee, imposed)

    new_club_ids = []
    for rider_id, season, club_id, is_unknown in zip(
            df["rider_id"], df["season"], df["club_id"], unknown
    ):
        key = (rider_id, int(season))
        new_club_ids.append(
            found[key][0] + INDIVIDUAL_LICENSE_SUFFIX if is_unknown and key in found else club_id
        )
    df["club_id"] = new_club_ids
    new_clubs = set(zip(df.loc[unknown, "club_id"], df.loc[unknown, "season"].astype(int)))
    for club_id, season in sorted(new_clubs):
        if club_id != INDIVIDUAL_CLUB_ID:
            clubs = add_club(clubs, club_id, INDIVIDUAL_NAME, season, departemental_committees)

    steps = Counter(step for _, step in found.values())
    lines = [
        f"committee of {len(pending)} individual licensee(s) x season(s) of unknown committee:"
    ]
    for step in (
            IMPOSED_BY_A_CORRECTION, OBSERVED_IN_SEASON, OBSERVED_IN_NEAREST_SEASON,
            DEDUCED_FROM_RACES
    ):
        lines.append(f"  {step}: {steps[step]}")
    lines.append(f"  not found (left in {INDIVIDUAL_CLUB_ID}): {len(pending) - len(found)}")
    logger.info("\n".join(lines))
    return df, clubs
