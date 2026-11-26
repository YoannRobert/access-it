"""Matching of the races of the entries with the ranked races of the database.

The races of the entries (one table of a startlist page, race_id
"vpc-<page ID>-<rank of the table>") have no link with the races of the
database: they are matched by the riders they share. Rules:

- the ranked share of a pair (race of the entries, ranked race) is the number
  of riders both entered in the first and ranked in the second, divided by the
  number of riders ranked in the second;
- a race of the entries with several dates (e.g. entries of several runs,
  the race being postponed in between) keeps only its rows of the latest
  date, a race being postponed rather than brought forward, with a warning
  in the log;
- the candidates of a race of the entries are the ranked races held from its
  race date (the first day of its page) to MAX_DAY_OFFSET days later, a page
  covering several days at times; a pair is kept if its ranked share is at
  least MIN_RANKED_SHARE;
- among the days of the kept pairs, the day of the highest ranked share is
  chosen (the earliest one in case of a tie), with all the kept pairs of this
  day: a race of the entries may be ranked as several races (e.g. A1,A2 and
  A3,A4);
- a ranked race matched with several races of the entries is kept for each of
  them, with a warning in the log;
- a race of the entries without any kept pair gets a single row without
  ranked race.

Limits: the ranked share does not depend on the length of a ranking, chosen
by the organizer, but a short ranking makes it less reliable, a few riders
being enough to reach the threshold; a wrong race of another day could also
win over the right one with a higher ranked share. Neither case was seen on
the races of 2026. The computation is free of any Streamlit dependency.
"""

import logging

import pandas as pd

from access_it.analytics.ranking_tools import check_race_dates, to_datetime

MIN_RANKED_SHARE = 0.5
MAX_DAY_OFFSET = 2
RACE_MATCH_COLUMNS = [
    "race_id", "ffc_race_id", "nb_common_riders", "nb_ranked_riders", "ranked_share"
]

logger = logging.getLogger(__name__)


def match_races(
        entries: pd.DataFrame,
        races: pd.DataFrame,
        rankings: pd.DataFrame
    ) -> pd.DataFrame:
    """Ranked races matching the races of the entries (see the module docstring for the rules).

    Args:
        entries: Entries of the races, one row per rider entered in a race
            (race_id, race_date and rider_id are used); a race may appear with
            several dates (see the module docstring).
        races: Race table.
        rankings: Ranking table.

    Returns:
        The RACE_MATCH_COLUMNS: one row per kept pair (race_id of the entries,
        ffc_race_id of the ranked race, numbers of common and ranked riders as
        Int64, ranked share), and one row per race of the entries without any
        kept pair, its other columns missing; sorted by race_id, then from
        the highest ranked share, then by ffc_race_id; empty if there is no
        entry.

    Raises:
        ValueError: If a race date of the entries is missing, then if a race
            date of a ranked race is missing.
    """
    entries = entries.assign(race_date=to_datetime(entries["race_date"]))
    if entries["race_date"].isna().any():
        raise ValueError("Missing race dates in the entries")
    ranked_races = races[races["race_id"].isin(rankings["race_id"])]
    ranked_dates = to_datetime(ranked_races["race_date"])
    check_race_dates(ranked_dates)

    latest_dates = entries.groupby("race_id")["race_date"].transform("max")
    postponed = sorted(entries.loc[entries["race_date"] != latest_dates, "race_id"].unique())
    if postponed:
        logger.warning("Races with several dates in the entries, latest date kept: %s", postponed)
    entries = entries[entries["race_date"] == latest_dates]

    race_dates = entries[["race_id", "race_date"]].drop_duplicates("race_id")
    ffc_dates = pd.DataFrame({
        "ffc_race_id": ranked_races["race_id"], "ffc_race_date": ranked_dates
    })
    nb_ranked = (
        rankings.groupby("race_id").size().rename("nb_ranked_riders")
        .rename_axis("ffc_race_id").reset_index()
    )
    pairs = (
        entries[["race_id", "rider_id"]]
        .merge(
            rankings[["race_id", "rider_id"]].rename(columns={"race_id": "ffc_race_id"}),
            on="rider_id"
        )
        .groupby(["race_id", "ffc_race_id"])["rider_id"].nunique()
        .rename("nb_common_riders")
        .reset_index()
        .merge(race_dates, on="race_id")
        .merge(ffc_dates, on="ffc_race_id")
        .merge(nb_ranked, on="ffc_race_id")
    )
    pairs["day_offset"] = (pairs["ffc_race_date"] - pairs["race_date"]).dt.days
    pairs["ranked_share"] = pairs["nb_common_riders"] / pairs["nb_ranked_riders"]
    kept = pairs[
        pairs["day_offset"].between(0, MAX_DAY_OFFSET)
        & (pairs["ranked_share"] >= MIN_RANKED_SHARE)
    ]
    best_days = (
        kept
        .sort_values(["race_id", "ranked_share", "day_offset"], ascending=[True, False, True])
        .drop_duplicates("race_id")
        [["race_id", "day_offset"]]
    )
    matched = kept.merge(best_days, on=["race_id", "day_offset"])

    shared = sorted(matched.loc[matched["ffc_race_id"].duplicated(), "ffc_race_id"].unique())
    if shared:
        logger.warning("FFC races matched with several races of the entries: %s", shared)

    return (
        race_dates[["race_id"]]
        .merge(matched[RACE_MATCH_COLUMNS], on="race_id", how="left")
        .astype({
            "race_id": "str", "ffc_race_id": "str", "nb_common_riders": "Int64",
            "nb_ranked_riders": "Int64", "ranked_share": "float64",
        })
        .sort_values(["race_id", "ranked_share", "ffc_race_id"], ascending=[True, False, True])
        .reset_index(drop=True)
    )
