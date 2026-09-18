import hashlib
import pandas as pd
import re

from access_it.common.text import normalize_string_and_fold_case
from access_it.etl.transform.clubs import INDIVIDUAL_CLUB_ID, parse_club_text, identify_club


def is_valid_uci_id(uci_id: str | None) -> bool:
    if uci_id is None:
        return False
    if not bool(re.fullmatch(r"\d{11}", uci_id)):
        return False
    return int(uci_id[:9]) % 97 == int(uci_id[9:])


def define_rider_id(uci_id: str | None, last_name: str, first_name: str) -> str:
    uci_id = "" if (uci_id is None or pd.isna(uci_id)) else str(uci_id).strip()
    n_last_name = normalize_string_and_fold_case(last_name).strip()
    n_first_name = normalize_string_and_fold_case(first_name).strip()
    key = f"{uci_id}|{n_last_name}|{n_first_name}".encode()
    return hashlib.blake2b(key, digest_size=8).hexdigest()


def split_race_data_into_rider_data(races_data: list[dict]) -> list[dict]:
    rider_x_race_data: list[dict] = []
    for race_data in races_data:
        season = race_data["season"]
        race_id = race_data["race_id"]
        for rider_data in race_data["ranking_data"]:
            rider_data["race_id"] = race_id
            rider_data["season"] = season
            rider_x_race_data.append(rider_data)
    return rider_x_race_data


def identify_club_of_riders(
        rider_x_race_data: list[dict],
        df_clubs: pd.DataFrame
    ) -> list[dict]:
    data = []
    for single_rider_x_race_data in rider_x_race_data:
        club_text = single_rider_x_race_data["club"]
        club_id, club_name = parse_club_text(club_text)
        del single_rider_x_race_data["club"]
        try:
            _, club_id_2, _ = identify_club(club_id=club_id, club_name=club_name, df_clubs=df_clubs)
            single_rider_x_race_data["club_id"] = club_id_2
            data.append(single_rider_x_race_data)
        except ValueError:
            pass
    return data


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
    added_uci_ids = []
    added_names_red_list = []
    added_names_individual_license = []
    added_names_unknown_uci_id = []
    db_rows = []
    i_uci_id, i_red_list, i_individual_license, i_missing_uci_id = 0, 0, 0, 0
    # rider_id_int = 1

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
        isin_red_list = (row.uci_id == "Liste Rouge")
        isin_individual_license = (club_id == INDIVIDUAL_CLUB_ID)

        if is_valid_uci_id(uci_id):
            i_uci_id += 1
            valid_row = True
            if uci_id not in added_uci_ids:
                add_this_row = True
                added_uci_ids.append(uci_id)
        elif isin_red_list:
            i_red_list += 1
            valid_row = True
            if [last_name, first_name] not in added_names_red_list:
                add_this_row = True
                added_names_red_list.append([last_name, first_name])
        elif isin_individual_license:
            i_individual_license += 1
            valid_row = True
            if [last_name, first_name] not in added_names_individual_license:
                add_this_row = True
                added_names_individual_license.append([last_name, first_name])
        elif (
                uci_id == ""
                and [last_name, first_name] not in added_names_red_list + added_names_individual_license
        ):
            i_missing_uci_id += 1
            valid_row = True
            if [last_name, first_name] not in added_names_unknown_uci_id:
                add_this_row = True
                added_names_unknown_uci_id.append([last_name, first_name])
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
            # rider_id_int += 1

    db = pd.concat([db, pd.DataFrame(db_rows)], axis=0)
    print_summary(
        n=total_rows,
        i_list=[i_uci_id, i_red_list, i_individual_license, i_missing_uci_id],
        label_list=["Known UCI IDs", "Red-list riders", "Individual licensees", "Unknown UCI IDs"]
    )

    return db


def get_rider_id(
        db: pd.DataFrame,
        uci_id: str = "",
        last_name: str = "",
        first_name: str = ""
    ) -> str:
    uci_id = "" if pd.isna(uci_id) else uci_id
    if uci_id != "" and uci_id != "Liste Rouge":
        if not is_valid_uci_id(uci_id):
            raise ValueError(f"Invalid UCI ID: {uci_id}")
        return db[db.uci_id == uci_id]['rider_id'].iloc[0]
    elif last_name != "" and first_name != "":
        mask_l = (db.last_name == last_name)
        mask_f = (db.first_name == first_name)
        rider_ids = db[mask_l & mask_f]['rider_id']
        if len(rider_ids) == 0:
            raise ValueError(
                "No rider found with last name "
                + f"'{last_name}' and first name '{first_name}'"
            )
        elif len(rider_ids) > 1:
            raise ValueError(
                "Multiple riders found with last name "
                + f"'{last_name}' and first name '{first_name}'"
            )
        else:
            return rider_ids.iloc[0]
    else:
        raise ValueError(
            "Either UCI ID or last name and first name must be provided"
        )


def define_affiliation_id(rider_id: str, club_id: str) -> str:
    key = f"{rider_id}|{club_id}".encode()
    return hashlib.blake2b(key, digest_size=8).hexdigest()


def create_affiliation_clubs_riders(
        rider_x_race_data: pd.DataFrame,
        races_data: pd.DataFrame,
        rider_db: pd.DataFrame
    ) -> pd.DataFrame:
    race_dates = races_data[["race_id", "date"]]
    race_dates["date"] = pd.to_datetime(race_dates["date"])
    cols = ["uci_id", "last_name", "first_name", "club_id", "date"]
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
    aff_data = {}
    for row in df.itertuples():
        uci_id = row.uci_id
        last_name = row.last_name
        first_name = row.first_name
        club_id = row.club_id
        date = row.date
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
        rider_id = get_rider_id(
            db=rider_db, uci_id=uci_id, last_name=last_name, first_name=first_name
        )
        affiliation_id = define_affiliation_id(rider_id, club_id)
        if rider_id in aff_data:
            if club_id in aff_data[rider_id]:
                aff_data[rider_id][club_id]["start_date"] = min(
                    date,
                    aff_data[rider_id][club_id]["start_date"]
                )
                aff_data[rider_id][club_id]["end_date"] = max(
                    date,
                    aff_data[rider_id][club_id]["end_date"]
                )
            else:
                aff_data[rider_id][club_id] = {
                    "affiliation_id": affiliation_id,
                    "start_date": date,
                    "end_date": date
                }
        else:
            aff_data[rider_id] = {
                club_id: {
                    "affiliation_id": affiliation_id,
                    "start_date": date,
                    "end_date": date
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
