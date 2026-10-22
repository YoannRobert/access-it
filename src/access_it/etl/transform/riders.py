"""Riders and affiliations: rider IDs, rider table, lookups of riders and affiliations."""

import hashlib
import pandas as pd

from collections import Counter, defaultdict
from typing import Literal

from access_it.common.text import normalize_string_and_fold_case
from access_it.common.uci import is_valid_uci_id
from access_it.etl.extract.constants import INDIVIDUAL_CLUB_ID
from access_it.etl.transform.clubs import ClubLookup, parse_club_text, identify_club


RED_LIST = "Liste Rouge"
MAX_REPORTED_CLUB_TEXTS = 10  # club texts listed in the report of dropped rows
MAX_REPORTED_RESULTS = 5  # results listed per reason in the report of dropped rows


def define_rider_id(uci_id: str | None, last_name: str, first_name: str) -> str:
    """Return a stable rider ID.

    With a valid UCI ID, the ID depends on the UCI ID only: corrections of the
    names (e.g. by correct_swapped_names) do not change it. Otherwise (red-list
    riders, missing UCI ID), there is no stable identifier and the ID depends on
    the UCI ID field and the normalized names, as before.
    """
    uci_id = "" if (uci_id is None or pd.isna(uci_id)) else str(uci_id).strip()
    if is_valid_uci_id(uci_id):
        key = f"uci|{uci_id}".encode()
    else:
        n_last_name = normalize_string_and_fold_case(last_name).strip()
        n_first_name = normalize_string_and_fold_case(first_name).strip()
        key = f"{uci_id}|{n_last_name}|{n_first_name}".encode()
    return hashlib.blake2b(key, digest_size=8).hexdigest()


def split_race_data_into_rider_data(races_data: list[dict]) -> list[dict]:
    """Flatten the rankings of the races into results (one dict per rider and race).

    The race ID, season and race date are added to each result (in place).
    """
    rider_x_race_data: list[dict] = []
    for race_data in races_data:
        season = race_data["season"]
        race_id = race_data["race_id"]
        race_date = race_data["race_date"]
        for rider_data in race_data["ranking_data"]:
            rider_data["race_id"] = race_id
            rider_data["season"] = season
            rider_data["race_date"] = race_date
            rider_x_race_data.append(rider_data)
    return rider_x_race_data


def identify_club_of_riders(
        rider_x_race_data: list[dict],
        df_clubs: pd.DataFrame | ClubLookup
    ) -> list[dict]:
    """Replace the club text of each result row by the identified club ID.

    Rows whose club cannot be identified are dropped, and reported (number of
    rows per club text) so that missing clubs or name variants can be fixed.
    """
    # Indexes over the club table are built once for all rows
    clubs = df_clubs if isinstance(df_clubs, ClubLookup) else ClubLookup(df_clubs)
    data = []
    unidentified_club_texts: Counter[str] = Counter()
    for single_rider_x_race_data in rider_x_race_data:
        club_text = single_rider_x_race_data["club"]
        club_id, club_name = parse_club_text(club_text)
        del single_rider_x_race_data["club"]
        try:
            _, club_id_2, _ = identify_club(club_id=club_id, club_name=club_name, df_clubs=clubs)
            single_rider_x_race_data["club_id"] = club_id_2
            data.append(single_rider_x_race_data)
        except ValueError:
            unidentified_club_texts[str(club_text)] += 1
    report_unidentified_club_texts(unidentified_club_texts)
    return data


def report_unidentified_club_texts(unidentified_club_texts: Counter[str]) -> None:
    """Print the number of result rows dropped because their club was not identified."""
    if not unidentified_club_texts:
        return
    n_rows = sum(unidentified_club_texts.values())
    n_texts = len(unidentified_club_texts)
    print(f"Warning: {n_rows} result row(s) dropped, club not identified ({n_texts} club text(s)):")
    for club_text, count in unidentified_club_texts.most_common(MAX_REPORTED_CLUB_TEXTS):
        print(f"{count:8d}  {club_text!r}")
    if n_texts > MAX_REPORTED_CLUB_TEXTS:
        print(f"          ... and {n_texts - MAX_REPORTED_CLUB_TEXTS} other club text(s)")


def add_riders_to_database(rider_x_race_data: pd.DataFrame) -> pd.DataFrame:
    """Create the rider table from the results.

    One rider is created per valid UCI ID, and per names for the red-list
    riders, the individual licensees and the riders without UCI ID (names
    already used by red-list or individual riders are not duplicated). Results
    without names are skipped. A summary is printed.

    Args:
        rider_x_race_data: Results of the riders.

    Returns:
        One row per rider: rider_id, uci_id, last_name, first_name.
    """
    def print_summary(n: int, i_list: list[int], label_list: list[str]):
        """Print the number of results per type of rider, and whether all are covered."""
        print('-' * 120)
        print("Summary:")
        i_cum = 0
        j = 0
        while j < 4:
            i = i_list[j]
            i_cum += i
            label = label_list[j]
            print_summary_line(i, i_cum, n, label)
            j += 1
        print("Status: ", end="")
        if i_cum == n:
            print("✅ Complete")
        else:
            print("❌ Incomplete")
        print('-' * 120)


    def print_summary_line(i: int, i_tot: int, n: int, label: str):
        """Print the number and share of results of one type of rider."""
        msg = f"{label:24s}:"
        msg += "   added"
        msg += f" {i:9d}"
        msg += f" ({i / n:7.2%}),"
        msg += "   cum. added"
        msg += f" {i_tot:9d}"
        msg += f" ({i_tot / n:7.2%}),"
        msg += "   remaining"
        msg += f" {n - i_tot:9d}"
        msg += f" ({(n - i_tot) / n:7.2%})"
        print(msg)

    df = rider_x_race_data.copy()
    total_rows = df.shape[0]
    db = pd.DataFrame(
        {
            "rider_id": pd.Series(dtype="str"),
            "uci_id": pd.Series(dtype="str"),
            "last_name": pd.Series(dtype="str"),
            "first_name": pd.Series(dtype="str")
        }
    )
    added_index = []
    # Sets give constant-time membership tests (lists were scanned at every row)
    added_uci_ids: set[str] = set()
    added_names_red_list: set[tuple[str, str]] = set()
    added_names_individual_license: set[tuple[str, str]] = set()
    added_names_unknown_uci_id: set[tuple[str, str]] = set()
    db_rows = []
    i_uci_id, i_red_list, i_individual_license, i_missing_uci_id = 0, 0, 0, 0

    for row in df.itertuples():
        index = row.Index
        last_name = row.last_name
        first_name = row.first_name
        uci_id = row.uci_id
        club_id = row.club_id
        add_this_row = False
        valid_row = False

        if not isinstance(last_name, str) or not isinstance(first_name, str):
            continue
        if len(last_name) == 0 or len(first_name) == 0:
            continue
        uci_id = uci_id if isinstance(uci_id, str) else ""
        club_id = club_id if isinstance(club_id, str) else ""
        isin_red_list = (row.uci_id == RED_LIST)
        isin_individual_license = (club_id == INDIVIDUAL_CLUB_ID)
        names = (last_name, first_name)

        if is_valid_uci_id(uci_id):
            i_uci_id += 1
            valid_row = True
            if uci_id not in added_uci_ids:
                add_this_row = True
                added_uci_ids.add(uci_id)
        elif isin_red_list:
            i_red_list += 1
            valid_row = True
            if names not in added_names_red_list:
                add_this_row = True
                added_names_red_list.add(names)
        elif isin_individual_license:
            i_individual_license += 1
            valid_row = True
            if names not in added_names_individual_license:
                add_this_row = True
                added_names_individual_license.add(names)
        elif (
                uci_id == ""
                and names not in added_names_red_list
                and names not in added_names_individual_license
        ):
            i_missing_uci_id += 1
            valid_row = True
            if names not in added_names_unknown_uci_id:
                add_this_row = True
                added_names_unknown_uci_id.add(names)
        if valid_row:
            added_index.append(index)
        if add_this_row:
            row2: dict[str, str] = {
                "rider_id": define_rider_id(uci_id, last_name, first_name),
                "uci_id": uci_id,
                "last_name": last_name,
                "first_name": first_name
            }
            db_rows.append(row2)

    db = pd.concat([db, pd.DataFrame(db_rows)], axis=0)
    print_summary(
        n=total_rows,
        i_list=[i_uci_id, i_red_list, i_individual_license, i_missing_uci_id],
        label_list=["Known UCI IDs", "Red-list riders", "Individual licensees", "Unknown UCI IDs"]
    )

    return db


def _text(value) -> str:
    """Stripped text of a value of the results, or "" if it is missing."""
    return value.strip() if isinstance(value, str) else ""


def assign_rider_ids(rider_x_race_data: pd.DataFrame, rider_db: pd.DataFrame) -> pd.DataFrame:
    """Add the rider ID of each result, with the rules of add_riders_to_database.

    - a valid UCI ID gives the rider with this UCI ID;
    - "Liste Rouge" gives the red-list rider with the same names;
    - a missing UCI ID, or any UCI ID of an individual licensee, gives the
      rider without valid UCI ID with the same names (red-list riders last).

    Results without rider (invalid UCI ID, missing names) are dropped and
    reported, so that one atypical result cannot stop the transform step.

    Args:
        rider_x_race_data: Results of the riders.
        rider_db: Rider table (see add_riders_to_database).

    Returns:
        A copy of the identified results, with a rider_id column.
    """
    by_uci_id: dict[str, str] = {}
    red_list_by_names: dict[tuple[str, str], str] = {}
    other_by_names: dict[tuple[str, str], str] = {}
    for rider_id, uci_id, last_name, first_name in zip(
            rider_db["rider_id"], rider_db["uci_id"], rider_db["last_name"], rider_db["first_name"]
    ):
        uci_id = _text(uci_id)
        names = (_text(last_name), _text(first_name))
        if is_valid_uci_id(uci_id):
            by_uci_id[uci_id] = rider_id
        elif uci_id == RED_LIST:
            red_list_by_names.setdefault(names, rider_id)
        else:
            other_by_names.setdefault(names, rider_id)

    rider_ids = []
    dropped: dict[str, list[str]] = defaultdict(list)
    for row in rider_x_race_data.itertuples():
        uci_id = _text(row.uci_id)
        names = (_text(row.last_name), _text(row.first_name))
        has_names = names[0] != "" and names[1] != ""
        if is_valid_uci_id(uci_id):
            rider_id = by_uci_id.get(uci_id)
        elif not has_names:
            rider_id = None
        elif uci_id == RED_LIST:
            rider_id = red_list_by_names.get(names)
        elif uci_id == "" or row.club_id == INDIVIDUAL_CLUB_ID:
            rider_id = other_by_names.get(names) or red_list_by_names.get(names)
        else:
            rider_id = None
        if rider_id is None:
            if has_names and uci_id not in ("", RED_LIST) and not is_valid_uci_id(uci_id):
                reason = "invalid UCI ID, to fix in UCI_ID_CORRECTIONS"
            elif not has_names:
                reason = "missing names"
            else:
                reason = "rider not found"
            dropped[reason].append(
                f"race_id={row.race_id}, finish_rank={row.finish_rank}, "
                f"uci_id='{uci_id}', names='{names[0]} {names[1]}'"
            )
        rider_ids.append(rider_id)

    df = rider_x_race_data.copy()
    df["rider_id"] = rider_ids
    if dropped:
        n = sum(len(results) for results in dropped.values())
        print(f"Warning: {n} result row(s) dropped, rider not identified:")
        for reason, results in dropped.items():
            print(f"  {reason}: {len(results)}")
            for result in results[:MAX_REPORTED_RESULTS]:
                print(f"    {result}")
    return df[df["rider_id"].notna()].copy()


def _group_positions(keys: list) -> dict:
    """Map each key to the list of its positions, in increasing order."""
    positions = defaultdict(list)
    for position, key in enumerate(keys):
        positions[key].append(position)
    return dict(positions)


class RiderLookup:
    """Indexes over the rider table, built once and queried many times.

    Replaces the full scan (copy + string normalization of the whole table)
    previously done at every call of `get_rider_id`. Results are identical,
    including the order of the returned rider IDs (order of the table).
    """

    def __init__(self, db: pd.DataFrame):
        """Build the indexes from the rider table (rider_id, uci_id, last_name, first_name)."""
        self.rider_ids: list[str] = db["rider_id"].to_list()
        self.uci_ids: list[str] = db["uci_id"].to_list()
        stripped_last_names = [x.strip() for x in db["last_name"]]
        stripped_first_names = [x.strip() for x in db["first_name"]]
        # Names as compared in case-sensitive (True) and case-insensitive (False) modes
        self.names: dict[bool, tuple[list[str], list[str]]] = {
            True: (stripped_last_names, stripped_first_names),
            False: (
                [normalize_string_and_fold_case(x) for x in stripped_last_names],
                [normalize_string_and_fold_case(x) for x in stripped_first_names],
            ),
        }
        self.positions_by_uci_id = _group_positions(self.uci_ids)
        self._name_indexes: dict[bool, dict[str, dict]] = {}

    def name_indexes(self, case_sensitive: bool) -> dict[str, dict]:
        """Name indexes for one mode, built on first use."""
        if case_sensitive not in self._name_indexes:
            last_names, first_names = self.names[case_sensitive]
            pairs = list(zip(last_names, first_names))
            self._name_indexes[case_sensitive] = {
                "name": _group_positions(pairs),
                "full_name": _group_positions([f"{l} {f}" for l, f in pairs]),
                "red_list_name": _group_positions(
                    [pair if uci_id == RED_LIST else None for pair, uci_id in zip(pairs, self.uci_ids)]
                ),
            }
        return self._name_indexes[case_sensitive]

    def get_rider_id(
            self,
            uci_id: str = "",
            last_name: str = "",
            first_name: str = "",
            full_name: str = "",
            case_sensitive: bool = True,
            broader_search: bool = False,
            output: Literal["first", "last", "all"] = "first"
        ) -> str | list[str]:
        """Find rider ID(s), by UCI ID, names, full name or red-list names.

        The search mode depends on the arguments given:
        - a valid UCI ID: the rider with this UCI ID;
        - `broader_search`: riders whose names contain the given names (all returned);
        - UCI ID "Liste Rouge" with `output="all"`: red-list riders with the last
          name and the initial of the first name;
        - last and first names: riders with these names;
        - full name ("<last name> <first name>"): riders with this full name (all returned).

        Args:
            uci_id: UCI ID, "Liste Rouge" or "".
            last_name: Last name.
            first_name: First name.
            full_name: Last and first names joined by a space.
            case_sensitive: Whether names are compared with their case and accents.
            broader_search: Whether names may be contained in the rider names.
            output: Rider returned when several match: "first", "last" or "all".

        Returns:
            A rider ID, or a list of rider IDs if `output` is "all".

        Raises:
            ValueError: If the UCI ID is invalid, if no rider is found, if several
                riders are found while only one is asked, or if the arguments are
                not enough to search.
        """
        if case_sensitive:
            last_name = last_name.strip()
            first_name = first_name.strip()
            full_name = full_name.strip()
        else:
            last_name = normalize_string_and_fold_case(last_name.strip())
            first_name = normalize_string_and_fold_case(first_name.strip())
            full_name = normalize_string_and_fold_case(full_name.strip())
        db_last_names, db_first_names = self.names[case_sensitive]
        uci_id = "" if pd.isna(uci_id) else uci_id
        if uci_id != "" and uci_id != RED_LIST:
            if not is_valid_uci_id(uci_id):
                raise ValueError(f"Invalid UCI ID: {uci_id}")
            positions = self.positions_by_uci_id.get(uci_id, [])
        elif broader_search:
            if last_name == "" and first_name == "":
                raise ValueError(
                    "Both last and first names cannot be empty when broader search is enabled."
                )
            positions = [
                position
                for position, (db_last_name, db_first_name)
                in enumerate(zip(db_last_names, db_first_names))
                if (last_name == "" or last_name in db_last_name)
                and (first_name == "" or first_name in db_first_name)
            ]
            output = "all"
        elif (
                uci_id == RED_LIST
                and last_name != ""
                and first_name != "" and len(first_name) >= 1
                and output == "all"
        ):
            first_name = first_name[0] + "."
            positions = self.name_indexes(case_sensitive)["red_list_name"].get(
                (last_name, first_name), []
            )
        elif last_name != "" and first_name != "":
            positions = self.name_indexes(case_sensitive)["name"].get((last_name, first_name), [])
        elif full_name != "":
            positions = self.name_indexes(case_sensitive)["full_name"].get(full_name, [])
            # Forcing "all" to ensure all same-name riders are returned,
            # then the rider can be determined by his club affiliation.
            output = "all"
        else:
            raise ValueError(
                "Please provide:\n"
                + "- UCI ID, or\n"
                + "- last name and first name, or\n"
                + "- full name (last and first names joined by a space), or\n"
                + "- UCI ID = 'Liste Rouge', complete last name and first letter of the first name."
            )
        rider_ids = [self.rider_ids[position] for position in positions]
        n = len(rider_ids)
        if n == 0:
            raise ValueError("Rider(s) not found")
        elif n > 1 and output != "all":
            raise ValueError(f"Multiple riders found while only one is asked:\n{rider_ids}")
        if output == "first":
            return rider_ids[0]
        elif output == "last":
            return rider_ids[-1]
        else:
            return rider_ids


def get_rider_id(
        db: pd.DataFrame | RiderLookup,
        uci_id: str = "",
        last_name: str = "",
        first_name: str = "",
        full_name: str = "",
        case_sensitive: bool = True,
        broader_search: bool = False,
        output: Literal["first", "last", "all"] = "first"
    ) -> str | list[str]:
    """Find rider ID(s) in the rider table.

    For repeated calls, pass a `RiderLookup` built once instead of the DataFrame.
    """
    lookup = db if isinstance(db, RiderLookup) else RiderLookup(db)
    return lookup.get_rider_id(
        uci_id=uci_id,
        last_name=last_name,
        first_name=first_name,
        full_name=full_name,
        case_sensitive=case_sensitive,
        broader_search=broader_search,
        output=output,
    )


# An isolated club observation has at most this number of results
MAX_ISOLATED_RESULTS = 2


def group_club_runs(observations: list[tuple]) -> list[dict]:
    """Group observations (race_date, club_id), sorted by date, into runs of the same club."""
    runs: list[dict] = []
    for race_date, club_id in observations:
        if runs and runs[-1]["club_id"] == club_id:
            runs[-1]["dates"].append(race_date)
        else:
            runs.append({"club_id": club_id, "dates": [race_date]})
    return runs


def is_isolated_run(before: dict, run: dict, after: dict) -> bool:
    """Whether `run` is an isolated observation between two runs of one same other club.

    The run must have at most MAX_ISOLATED_RESULTS results, and the surrounding
    results must be in the same calendar year as the run (e.g. a single result
    with another club between two results of the usual club, a few weeks apart).
    """
    year = run["dates"][0].year
    return (
        before["club_id"] == after["club_id"]
        and len(run["dates"]) <= MAX_ISOLATED_RESULTS
        and before["dates"][-1].year == year
        and run["dates"][-1].year == year
        and after["dates"][0].year == year
    )


def compute_rider_affiliation_periods(observations: list[tuple]) -> tuple[list[dict], int]:
    """Compute the affiliation periods of one rider from its observations (race_date, club_id).

    Observations must be sorted by date. Return the periods (start_date, club_id),
    sorted by start date, and the number of isolated observations ignored.
    Rules:
    - isolated observations (see is_isolated_run) are ignored;
    - a period starts on January 1st of the year of its first result, unless
      another club was observed earlier the same year: it then starts on the
      date of its first result;
    - a period ends the day before the next one starts, or is still ongoing:
      years without results are covered by the previous club.
    """
    runs = group_club_runs(observations)
    isolated = {
        k for k in range(1, len(runs) - 1) if is_isolated_run(runs[k - 1], runs[k], runs[k + 1])
    }
    n_ignored = sum(len(runs[k]["dates"]) for k in isolated)
    if isolated:
        kept = [
            (race_date, run["club_id"])
            for k, run in enumerate(runs) if k not in isolated
            for race_date in run["dates"]
        ]
        runs = group_club_runs(kept)

    periods: list[dict] = []
    previous_last_date = None
    for run in runs:
        first_date = run["dates"][0]
        if previous_last_date is not None and previous_last_date.year == first_date.year:
            start_date = first_date
        else:
            start_date = pd.Timestamp(year=first_date.year, month=1, day=1)
        previous_last_date = run["dates"][-1]
        # Same-day observations with different clubs: the latest one wins
        if periods and periods[-1]["start_date"] >= start_date:
            periods.pop()
        if periods and periods[-1]["club_id"] == run["club_id"]:
            continue
        periods.append({"start_date": start_date, "club_id": run["club_id"]})
    return periods, n_ignored


def compute_affiliation_periods(observations: pd.DataFrame) -> pd.DataFrame:
    """Compute the affiliation periods of all riders.

    `observations` has one row per result: rider_id, race_id, race_date, club_id.
    Return one row per period: rider_id, start_date, club_id (see
    compute_rider_affiliation_periods), and print the number of isolated
    observations ignored.
    """
    df = observations.sort_values(["rider_id", "race_date", "race_id"], kind="stable")
    rows = []
    n_ignored, riders_with_ignored = 0, 0
    for rider_id, results in df.groupby("rider_id", sort=True):
        periods, n = compute_rider_affiliation_periods(
            list(zip(results["race_date"], results["club_id"]))
        )
        rows += [{"rider_id": rider_id, **period} for period in periods]
        n_ignored += n
        riders_with_ignored += n > 0
    if n_ignored:
        print(
            f"Info: {n_ignored} isolated club observation(s) of {riders_with_ignored} rider(s) "
            f"ignored for affiliations"
        )
    periods = pd.DataFrame(rows, columns=["rider_id", "start_date", "club_id"])
    periods["start_date"] = pd.to_datetime(periods["start_date"])
    return periods


def create_affiliation_clubs_riders(
        rider_x_race_data: pd.DataFrame,
        races_data: pd.DataFrame
    ) -> pd.DataFrame:
    """Create the affiliation table: one row per rider and period with the same club.

    Columns: rider_id, start_date, club_id. A period ends the day before the
    next start_date of the same rider, or is still ongoing if there is none.

    Args:
        rider_x_race_data: Results of the riders, with their rider ID (see
            assign_rider_ids).
        races_data: Races, for the race dates.
    """
    race_dates = races_data[["race_id", "race_date"]].copy()
    race_dates["race_date"] = pd.to_datetime(race_dates["race_date"])
    cols = ["rider_id", "club_id", "race_id", "race_date"]
    rider_x_race_data = rider_x_race_data.drop(columns=["race_date"])
    df = rider_x_race_data.merge(race_dates, on="race_id", how="inner")[cols]
    # Results without identified club (e.g. ambiguous club name) give no observation
    unknown_club = df["club_id"].map(lambda club_id: not isinstance(club_id, str))
    if unknown_club.any():
        print(f"Info: {unknown_club.sum()} result(s) without identified club "
              f"ignored for affiliations")
    df = df[~unknown_club].copy()
    return compute_affiliation_periods(df[["rider_id", "race_id", "race_date", "club_id"]])


class AffiliationLookup:
    """Affiliation periods indexed by club, to find the riders of a club at a given date.

    A period starts at its start_date and ends the day before the next
    start_date of the same rider, or is still ongoing if there is none.
    For the lookup only, the first period of a rider also covers the dates
    before its start: before his first result, nothing contradicts his club
    (e.g. a rider on a startlist before his first result with the club).
    """

    def __init__(self, affiliations: pd.DataFrame):
        """Build the periods of each club from the affiliations (rider_id, start_date, club_id)."""
        df = affiliations.sort_values(["rider_id", "start_date"])
        end_dates = df.groupby("rider_id")["start_date"].shift(-1)  # exclusive end
        is_first_period = df.groupby("rider_id").cumcount() == 0
        self.periods_by_club: dict[str, list[tuple]] = defaultdict(list)
        for rider_id, club_id, start_date, end_date, is_first in zip(
                df["rider_id"], df["club_id"], df["start_date"], end_dates, is_first_period
        ):
            start_date = None if is_first else pd.Timestamp(start_date)
            end_date = None if pd.isna(end_date) else pd.Timestamp(end_date)
            self.periods_by_club[club_id].append((rider_id, start_date, end_date))

    def riders_of_club(self, club_id: str, on_date: pd.Timestamp | None = None) -> set[str]:
        """Riders affiliated with the club on the date (at any time if no date is given)."""
        periods = self.periods_by_club.get(club_id, [])
        if on_date is None:
            return {rider_id for rider_id, _, _ in periods}
        return {
            rider_id
            for rider_id, start_date, end_date in periods
            if (start_date is None or start_date <= on_date)
            and (end_date is None or on_date < end_date)
        }


def get_rider_id_using_affiliations(
        rider_ids: list[str],
        affiliations: pd.DataFrame | AffiliationLookup,
        club_id: str,
        on_date: pd.Timestamp | None = None
    ) -> str:
    """Return the only rider among `rider_ids` affiliated with `club_id` on the date.

    Without date, any affiliation period with the club is accepted. For
    repeated calls, pass an AffiliationLookup built once instead of the DataFrame.
    """
    if len(rider_ids) == 0:
        raise ValueError("No rider IDs provided")
    if isinstance(affiliations, pd.DataFrame):
        affiliations = AffiliationLookup(affiliations)
    rider_ids_out = list(set(rider_ids) & affiliations.riders_of_club(club_id, on_date))
    n = len(rider_ids_out)
    if n == 0:
        raise ValueError(f"No rider ID found for club ID {club_id}")
    if n > 1:
        raise ValueError(f"Multiple rider IDs found for club ID {club_id}")
    return rider_ids_out[0]
