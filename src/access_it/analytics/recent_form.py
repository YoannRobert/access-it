"""Recent form of the riders: share of top N finishes in their last races.

Shown in the dashboard, then reused as a feature of the models (win, podium,
top 5, top 10 and top 20 probabilities). Rules:

- only the races strictly before the reference date count, so that no
  future result leaks into a feature;
- the races of the window count, from reference_date minus window_months
  (included); for each rider, his last_races most recent ones are used; two
  races of the same day are ordered by finish rank (best place kept first),
  then by race_id;
- every race counts, whatever its number of ranked riders;
- the rank is the absolute finish rank: a top N is finish_rank <= top_n, and
  tied riders all count; foreign riders are kept, nobody moves up;
- a race where the rider is not ranked (did not finish or start) is absent
  from the rankings, so it is not counted.

Known limit: a top N is easier in a small field.

The computation is free of any Streamlit dependency.
"""

from collections.abc import Sequence

import pandas as pd

from access_it.analytics.ranking_tools import to_datetime

COLUMNS = ["rider_id", "nb_races_used", "nb_top_n", "top_n_rate"]


def compute_recent_form(
        races: pd.DataFrame,
        rankings: pd.DataFrame,
        rider_ids: Sequence[str],
        reference_date: str | pd.Timestamp,
        top_n: int = 20,
        last_races: int = 10,
        window_months: int = 6
    ) -> pd.DataFrame:
    """Share of top N finishes of each rider in his last races before a date.

    See the module docstring for the rules.

    Args:
        races: Race table.
        rankings: Ranking table.
        rider_ids: Riders to compute, chosen by the caller.
        reference_date: Day of the forecast, as "YYYY-MM-DD" or a date (the
            time of day is ignored); its races are excluded.
        top_n: Last finish rank counting as a top N.
        last_races: Maximum number of races used per rider.
        window_months: Length of the window before the reference date.

    Returns:
        One row per rider of rider_ids, in the same order: rider_id,
        nb_races_used, nb_top_n and top_n_rate (nb_top_n / nb_races_used,
        0 for a rider without race in the window).
    """
    end = to_datetime(pd.Series([reference_date])).dt.normalize().iloc[0]
    start = end - pd.DateOffset(months=window_months)
    race_dates = races[["race_id", "race_date"]].assign(
        race_date=lambda df: to_datetime(df["race_date"])
    )
    results = rankings[["race_id", "rider_id", "finish_rank"]].merge(race_dates, on="race_id")
    in_window = (
        results["rider_id"].isin(rider_ids)
        & (results["race_date"] >= start)
        & (results["race_date"] < end)
    )
    recent = (
        results[in_window]
        .sort_values(["race_date", "finish_rank", "race_id"], ascending=[False, True, False])
        .groupby("rider_id")
        .head(last_races)
    )
    form = (
        recent.assign(is_top_n=recent["finish_rank"] <= top_n)
        .groupby("rider_id")
        .agg(nb_races_used=("race_id", "size"), nb_top_n=("is_top_n", "sum"))
        .reindex(rider_ids, fill_value=0)
        .astype(int)
        .rename_axis("rider_id")
        .reset_index()
    )
    form["top_n_rate"] = (form["nb_top_n"] / form["nb_races_used"]).fillna(0.0)
    return form[COLUMNS]
