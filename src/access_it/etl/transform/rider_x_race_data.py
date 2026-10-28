"""Results of the riders (one row per rider and race): corrections, completion, rankings.

The hard-coded corrections fix errors of the FFC result pages, identified
by race ID and finish rank.
"""

import pandas as pd

from access_it.etl.extract.constants import INDIVIDUAL_NAME, FOREIGN_NAME


# UCI IDs wrong or missing on the result pages: (race ID, finish rank,
# wrong UCI ID or "" if missing, correct UCI ID)
UCI_ID_CORRECTIONS: list[tuple] = [
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

# Results of individual licensees whose club is missing on the result pages:
# (race ID, finish rank)
INDIVIDUAL_LABEL_CORRECTIONS: list[tuple] = [
    ("7c605505e10d81a6", 49)
]

# Results whose club is wrong on the result pages (e.g. a rider still shown as
# an individual licensee after joining a club): (race ID, finish rank, correct
# club text, read as the club texts of the result pages)
CLUB_CORRECTIONS: list[tuple] = [
    ("87864c14f8dd5055", 35, "4335104 - VCS LOUVIGNEEN"),
    ("1c7e41df8bdd9475", 12, "4335104 - VCS LOUVIGNEEN"),
]

# Results of foreign riders whose club is missing on the result pages:
# (race ID, finish rank)
FOREIGN_LABEL_CORRECTIONS: list[tuple] = [
    ("88cf222e097b8b6b", 23),
    ("3dfce1e035f3e7ca", 28),
    ("58fd279416dc2e71", 17),
    ("58fd279416dc2e71", 44),
    ("3dfce1e035f3e7ca", 25),
    ("3dfce1e035f3e7ca", 37)
]


def fill_missing_values_by_groups(
        col_to_fill: str,
        grouping_cols: list[str],
        not_na_col: str,
        df: pd.DataFrame
    ) -> pd.DataFrame:
    """Fill the missing values of a column within groups of rows.

    Only the rows where `not_na_col` is known are considered; within each
    group of `grouping_cols`, missing values of `col_to_fill` are filled with
    the known ones (forward then backward fill).

    Args:
        col_to_fill: Column to fill.
        grouping_cols: Columns defining the groups.
        not_na_col: Column that must be known for a row to be considered.
        df: Results of the riders.

    Returns:
        A copy of `df` with the column filled.
    """
    df = df.copy()
    mask_known_keys = df[not_na_col].notna()
    df.loc[mask_known_keys, col_to_fill] = (
        df.loc[mask_known_keys]
        .groupby(grouping_cols)[col_to_fill]
        .transform(lambda group: group.ffill().bfill())
    )
    return df


def fill_missing_club_ids(df: pd.DataFrame) -> pd.DataFrame:
    """Fill missing club IDs from the results of the same rider (names, UCI ID) and season."""
    grouping_cols = ["last_name", "first_name", "season", "uci_id"]
    df = fill_missing_values_by_groups(
        col_to_fill="club_id",
        grouping_cols=grouping_cols,
        not_na_col="uci_id",
        df=df
    )
    return df


def fill_missing_uci_ids(df: pd.DataFrame) -> pd.DataFrame:
    """Fill missing UCI IDs from the results of the same rider (names, club) and season."""
    grouping_cols = ["last_name", "first_name", "season", "club_id"]
    df = fill_missing_values_by_groups(
        col_to_fill="uci_id",
        grouping_cols=grouping_cols,
        not_na_col="club_id",
        df=df
    )
    return df


def fill_missing_club_and_uci_ids(df: pd.DataFrame) -> pd.DataFrame:
    """Fill missing club IDs, then missing UCI IDs (see the two functions above)."""
    df = fill_missing_club_ids(df)
    df = fill_missing_uci_ids(df)
    return df


def fill_missing_uci_ids_deep_mode(df: pd.DataFrame) -> pd.DataFrame:
    """Fill missing UCI IDs from the results of riders with the same names, any season.

    A single UCI ID known for the names fills every missing one. With several
    UCI IDs (homonyms), a missing one is filled only if exactly one of them has
    no result in the season of the row; ambiguous rows are left missing.
    """
    def _fill_uci_ids(group):
        """Fill the missing UCI IDs of one group of rows with the same names."""
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
    """Correct UCI IDs that are wrong on the result pages.

    To add a correction, append (race ID, finish rank, wrong UCI ID or "" if
    missing, correct UCI ID) to UCI_ID_CORRECTIONS.
    """
    for d in data:
        for race_id, finish_rank, wrong_uci_id, correct_uci_id in UCI_ID_CORRECTIONS:
            d_uci_id = d["uci_id"] if isinstance(d["uci_id"], str) else ""
            if ((
                    d["race_id"] == race_id)
                    & (d["finish_rank"] == finish_rank)
                    & (d_uci_id == wrong_uci_id)
            ):
                d["uci_id"] = correct_uci_id
    return data


def correct_swapped_names(records: list[dict]) -> list[dict]:
    """Harmonize rider names across races using the UCI ID as the reference key.

    For each `uci_id`, the most frequent (last_name, first_name) pair is kept as
    the reference. Ties are broken by the most recent `race_date` (YYYY-MM-DD
    strings). All other name variants of that `uci_id` are replaced by the
    reference pair. Rows with a missing or empty `uci_id` are left untouched.
    Incomplete pairs (missing last or first name) never become the reference;
    a `uci_id` with only incomplete pairs is left untouched as well.

    Takes a list of dicts (one per rider result) and returns a corrected list
    of dicts with the same length and order as `records`.
    """
    df = pd.DataFrame(records)

    name_cols = ["last_name", "first_name"]
    corrected = df.copy()

    # Ignore rows whose uci_id is missing or an empty / blank string
    uci_id = corrected["uci_id"]
    valid_mask = uci_id.notna() & (uci_id.astype(str).str.strip() != "") & (uci_id != "Liste Rouge")
    valid = corrected.loc[valid_mask]

    # Occurrences and most recent race date for each complete (uci_id, name) sub-group;
    # pairs with a missing name are dropped so they can never become the reference
    stats = (
        valid.groupby(["uci_id", *name_cols])
        .agg(n_occurrences=("race_date", "size"), latest_date=("race_date", "max"))
        .reset_index()
    )

    # Reference name per uci_id: highest count, then most recent date
    reference = (
        stats.sort_values(
            by=["n_occurrences", "latest_date"],
            ascending=[False, False],
            na_position="last",
            kind="stable",
        )
        .drop_duplicates(subset="uci_id", keep="first")
        .set_index("uci_id")[name_cols]
    )

    # Only correct rows whose uci_id has a reference, so no name is ever set to NaN
    valid_mask &= uci_id.isin(reference.index)

    # Overwrite names of valid rows only; excluded rows keep their original values
    for col in name_cols:
        corrected.loc[valid_mask, col] = corrected.loc[valid_mask, "uci_id"].map(reference[col])

    # Convert back to a list of dicts, turning pandas NaN back into None
    return corrected.astype(object).where(corrected.notna(), other=None).to_dict(orient="records")


def apply_corrections_for_missing_club_labels(
        data: list[dict],
        corrections: list[tuple[str, int]],
        correction_value: str
    ) -> list[dict]:
    """Set the club of the results identified by (race ID, finish rank), when it is empty.

    Args:
        data: Results of the riders.
        corrections: (race ID, finish rank) of the results to correct.
        correction_value: Club label to set.

    Returns:
        The corrected results (modified in place).
    """
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
    """Set the club "Individuel" of results whose club is missing on the result pages.

    To add a correction, append (race ID, finish rank) to INDIVIDUAL_LABEL_CORRECTIONS.
    """
    return apply_corrections_for_missing_club_labels(
        data, INDIVIDUAL_LABEL_CORRECTIONS, INDIVIDUAL_NAME
    )


def correct_wrong_clubs(data: list[dict]) -> list[dict]:
    """Replace the club of the results whose club is wrong on the result pages.

    Unlike the label corrections, which only fill a missing club, the club is
    replaced whatever its value. To add a correction, append (race ID, finish
    rank, correct club text) to CLUB_CORRECTIONS.
    """
    correct_club_by_result = {
        (race_id, finish_rank): club for race_id, finish_rank, club in CLUB_CORRECTIONS
    }
    for d in data:
        club = correct_club_by_result.get((d["race_id"], d["finish_rank"]))
        if club is not None:
            d["club"] = club
    return data


def add_missing_foreign_labels(data: list[dict]) -> list[dict]:
    """Set the club "Etranger" of results whose club is missing on the result pages.

    To add a correction, append (race ID, finish rank) to FOREIGN_LABEL_CORRECTIONS.
    """
    return apply_corrections_for_missing_club_labels(
        data, FOREIGN_LABEL_CORRECTIONS, FOREIGN_NAME
    )


def create_ranking_table(rider_x_race_data: pd.DataFrame) -> pd.DataFrame:
    """Create the ranking table: one row per rider and race.

    Args:
        rider_x_race_data: Results of the riders, with their rider ID (see
            assign_rider_ids).

    Returns:
        One row per result: race_id, rider_id, finish_rank.
    """
    return rider_x_race_data[["race_id", "rider_id", "finish_rank"]].copy()
