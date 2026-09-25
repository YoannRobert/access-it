import pandas as pd

from access_it.etl.extract.clubs import INDIVIDUAL_NAME, FOREIGN_NAME
from access_it.etl.transform.riders import get_rider_id


def fill_missing_values_by_groups(
        col_to_fill: str,
        grouping_cols: list[str],
        not_na_col: str,
        df: pd.DataFrame
    ) -> pd.DataFrame:
    df = df.copy()
    mask_known_keys = df[not_na_col].notna()
    df.loc[mask_known_keys, col_to_fill] = (
        df.loc[mask_known_keys]
        .groupby(grouping_cols)[col_to_fill]
        .transform(lambda group: group.ffill().bfill())
    )
    return df


def fill_missing_club_ids(df: pd.DataFrame) -> pd.DataFrame:
    grouping_cols = ["last_name", "first_name", "season", "uci_id"]
    df = fill_missing_values_by_groups(
        col_to_fill="club_id",
        grouping_cols=grouping_cols,
        not_na_col="uci_id",
        df=df
    )
    return df


def fill_missing_uci_ids(df: pd.DataFrame) -> pd.DataFrame:
    grouping_cols = ["last_name", "first_name", "season", "club_id"]
    df = fill_missing_values_by_groups(
        col_to_fill="uci_id",
        grouping_cols=grouping_cols,
        not_na_col="club_id",
        df=df
    )
    return df


def fill_missing_club_and_uci_ids(df: pd.DataFrame) -> pd.DataFrame:
    df = fill_missing_club_ids(df)
    df = fill_missing_uci_ids(df)
    return df


def fill_missing_uci_ids_deep_mode(df: pd.DataFrame) -> pd.DataFrame:

    def _fill_uci_ids(group):
        known_ids = group.loc[group["uci_id"].notna(), "uci_id"].unique()

        # No known uci_id for this (last_name, first_name): nothing to do
        if len(known_ids) == 0:
            return group

        # Only one possible uci_id: fill all missing rows with it
        if len(known_ids) == 1:
            group.loc[group["uci_id"].isna(), "uci_id"] = known_ids[0]
            return group

        # Multiple possible uci_id: for each missing row, pick the candidate
        # whose triplet has no existing row with the same season
        seasons_per_id = {
            uid: set(group.loc[group["uci_id"] == uid, "season"])
            for uid in known_ids
        }

        for idx in group.index[group["uci_id"].isna()]:
            season = group.loc[idx, "season"]
            candidates = [uid for uid in known_ids if season not in seasons_per_id[uid]]
            if len(candidates) == 1:
                group.loc[idx, "uci_id"] = candidates[0]
            # 0 or several candidates: ambiguous, left as NaN for manual review

        return group

    df = (
        df.groupby(by=["last_name", "first_name"], group_keys=False)
        .apply(_fill_uci_ids, include_groups=False)
        .combine_first(df)  # restores last_name/first_name withdrawn by include_groups
    )
    return df


def correct_wrong_uci_ids(data: list[dict]) -> list[dict]:
    corrections = [
        ("25e7949a45ba0148", 52, "10137846680", "10051737861"),
        ("163378aa7e736570", 7, "10137846680", "10051737861"),
        ("e226c6b3c04081ba", 2, "10137846680", "10051737861"),
        ("46729e14b576fd3a", 1, "10025630818", "10165044369"),
        ("fd3d489f5e2e2c76", 16, "10025630818", "10165044369"),
        ("e7bf6f878a51c77e", 28, "", "10145288705"),
        ("2a11e53992ee34a1", 4, "", "10158245881"),
        ("a0e48493fb6fc308", 12, "", "10158245881"),
        ("1361d0b2d93516e9", 34, "", "10025488651"),
        ("797041cd80520893", 28, "", "10127344816"),
        ("16d947c7ec2eeebe", 46, "", "10145307596"),
        ("7bc45e816a53236d", 64, "", "10145307596")
    ]
    for d in data:
        for race_id, finish_rank, wrong_uci_id, correct_uci_id in corrections:
            d_uci_id = d["uci_id"] if isinstance(d["uci_id"], str) else ""
            if ((
                    d["race_id"] == race_id)
                    & (d["finish_rank"] == finish_rank)
                    & (d_uci_id == wrong_uci_id)
            ):
                d["uci_id"] = correct_uci_id
    return data


def apply_corrections_for_missing_club_labels(
        data: list[dict],
        corrections: list[tuple[str, int]],
        correction_value: str
    ) -> list[dict]:
    for d in data:
        d_club = d["club"] if isinstance(d["club"], str) else ""
        for race_id, finish_rank in corrections:
            if (
                    (d["race_id"] == race_id)
                    & (d["finish_rank"] == finish_rank)
                    & (d_club == "")
            ):
                d["club"] = correction_value
    return data

def add_missing_individual_labels(data: list[dict]) -> list[dict]:
    corrections = [
        ("7c605505e10d81a6", 49)
    ]
    return apply_corrections_for_missing_club_labels(data, corrections, INDIVIDUAL_NAME)


def add_missing_foreign_labels(data: list[dict]) -> list[dict]:
    corrections = [
        ("88cf222e097b8b6b", 23),
        ("3dfce1e035f3e7ca", 28),
        ("58fd279416dc2e71", 17),
        ("58fd279416dc2e71", 44),
        ("3dfce1e035f3e7ca", 25),
        ("88cf222e097b8b6b", 23),
        ("3dfce1e035f3e7ca", 28),
        ("3dfce1e035f3e7ca", 37)
    ]
    return apply_corrections_for_missing_club_labels(data, corrections, FOREIGN_NAME)


def create_ranking_table(
        rider_x_race_data: pd.DataFrame,
        rider_db: pd.DataFrame
    ) -> pd.DataFrame:
    df = rider_x_race_data.copy()
    df["rider_id"] = [
        get_rider_id(rider_db, uci_id, last_name, first_name)
        for uci_id, last_name, first_name in zip(
            df["uci_id"], df["last_name"], df["first_name"]
        )
    ]
    return df[["race_id", "rider_id", "finish_rank"]]
