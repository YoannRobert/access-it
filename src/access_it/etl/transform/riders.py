import hashlib
import pandas as pd
import re

from collections import Counter, defaultdict
from typing import Literal

from access_it.common.text import normalize_string_and_fold_case
from access_it.etl.extract.constants import INDIVIDUAL_CLUB_ID
from access_it.etl.transform.clubs import ClubLookup, parse_club_text, identify_club


RED_LIST = "Liste Rouge"
MAX_REPORTED_CLUB_TEXTS = 10  # club texts listed in the report of dropped rows


def is_valid_uci_id(uci_id: str | None) -> bool:
    if uci_id is None:
        return False
    if not bool(re.fullmatch(r"\d{11}", uci_id)):
        return False
    return int(uci_id[:9]) % 97 == int(uci_id[9:])


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

    def print_summary(n: int, i_list: list[int], label_list: list[str]):
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


def define_affiliation_id(rider_id: str, club_id: str) -> str:
    key = f"{rider_id}|{club_id}".encode()
    return hashlib.blake2b(key, digest_size=8).hexdigest()


def create_affiliation_clubs_riders(
        rider_x_race_data: pd.DataFrame,
        races_data: pd.DataFrame,
        rider_db: pd.DataFrame
    ) -> pd.DataFrame:
    race_dates = races_data[["race_id", "race_date"]].copy()
    race_dates["race_date"] = pd.to_datetime(race_dates["race_date"])
    cols = ["uci_id", "last_name", "first_name", "club_id", "race_date"]
    rider_x_race_data = rider_x_race_data.drop(columns=["race_date"])
    df = rider_x_race_data.merge(race_dates, on="race_id", how="inner")[cols]
    aff = pd.DataFrame(
        {
            "affiliation_id": pd.Series(dtype="str"),
            "rider_id": pd.Series(dtype="str"),
            "club_id": pd.Series(dtype="str"),
            "start_date": pd.Series(dtype="datetime64[ns]"),
            "end_date": pd.Series(dtype="datetime64[ns]")
        }
    )
    riders = RiderLookup(rider_db)
    aff_data = {}
    for row in df.itertuples():
        uci_id = row.uci_id
        last_name = row.last_name
        first_name = row.first_name
        club_id = row.club_id
        race_date = row.race_date
        uci_id = uci_id if isinstance(uci_id, str) else ""
        last_name = last_name if isinstance(last_name, str) else ""
        first_name = first_name if isinstance(first_name, str) else ""
        if (
                not isinstance(uci_id, str)
                or not isinstance(last_name, str)
                or not isinstance(first_name, str)
                or not isinstance(club_id, str)
        ):
            raise TypeError(
                "Invalid data type for uci_id, last_name, or first_name "
                + "(should be str)."
            )
        rider_id = riders.get_rider_id(
            uci_id=uci_id, last_name=last_name, first_name=first_name
        )
        if not isinstance(rider_id, str):
            raise TypeError(
                "Invalid data type for rider_id (should be str).\n"
                + f"type: {type(rider_id)}\n"
                + f"value: {str(rider_id)}\n"
                + f"arguments: uci_id={uci_id}, last_name={last_name}, first_name={first_name}"
            )
        affiliation_id = define_affiliation_id(rider_id, club_id)
        if rider_id in aff_data:
            if club_id in aff_data[rider_id]:
                aff_data[rider_id][club_id]["start_date"] = min(
                    race_date,
                    aff_data[rider_id][club_id]["start_date"]
                )
                aff_data[rider_id][club_id]["end_date"] = max(
                    race_date,
                    aff_data[rider_id][club_id]["end_date"]
                )
            else:
                aff_data[rider_id][club_id] = {
                    "affiliation_id": affiliation_id,
                    "start_date": race_date,
                    "end_date": race_date
                }
        else:
            aff_data[rider_id] = {
                club_id: {
                    "affiliation_id": affiliation_id,
                    "start_date": race_date,
                    "end_date": race_date
                }
            }
    # flattening the dictionary into a list of single-level dictionaries
    aff_data_list = []
    for rider_id, clubs in aff_data.items():
        for club_id, affiliation in clubs.items():
            aff_data_list.append(
                {
                    "affiliation_id": affiliation["affiliation_id"],
                    "rider_id": rider_id,
                    "club_id": club_id,
                    "start_date": affiliation["start_date"],
                    "end_date": affiliation["end_date"]
                }
            )
    aff = pd.concat([aff, pd.DataFrame(aff_data_list)], ignore_index=True)
    return aff


def build_riders_by_club(affiliations: pd.DataFrame) -> dict[str, set[str]]:
    """Map each club ID to the set of rider IDs affiliated with it."""
    riders_by_club: dict[str, set[str]] = defaultdict(set)
    for club_id, rider_id in zip(affiliations["club_id"], affiliations["rider_id"]):
        riders_by_club[club_id].add(rider_id)
    return dict(riders_by_club)


def get_rider_id_using_affiliations(
        rider_ids: list[str],
        affiliations: pd.DataFrame | dict[str, set[str]],
        club_id: str
    ) -> str:
    """Return the only rider among `rider_ids` affiliated with `club_id`.

    For repeated calls, pass the mapping returned by `build_riders_by_club`
    instead of the affiliation DataFrame.
    """
    if len(rider_ids) == 0:
        raise ValueError("No rider IDs provided")
    if isinstance(affiliations, pd.DataFrame):
        affiliations = build_riders_by_club(affiliations)
    rider_ids_out = list(set(rider_ids) & affiliations.get(club_id, set()))
    n = len(rider_ids_out)
    if n == 0:
        raise ValueError(f"No rider ID found for club ID {club_id}")
    if n > 1:
        raise ValueError(f"Multiple rider IDs found for club ID {club_id}")
    return rider_ids_out[0]
