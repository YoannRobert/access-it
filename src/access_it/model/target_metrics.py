"""Metrics of the forecasts of the targets: lists of riders, probabilities and calibration.

The forecast of a race gives each rider entered a probability and a unique
rank for each target (win, podium, top 5, top 10), as returned by
forecast_place_probabilities of the forecasts module; a method that only gives
one predicted rank (the baseline) copies it into the four rank columns. The
rows given are those of the races evaluated (selected by the evaluation
module). Rules:

- the list of a target holds the riders of rank 1 to its size (LIST_SIZES:
  10 for the win, the podium and the top 5, 20 for the top 10);
- the recall of a target is the number of riders of the list who reached the
  target (finish_rank <= its last rank, tied riders all count), divided by
  the number of ranked riders who reached it; it is missing if none did;
- the reciprocal rank of the winner is 1 / rank_win of the winner best ranked
  by the forecast if he is in the list of 10, 0 otherwise; it is missing if
  the race has no winner;
- the log-loss (probabilities bounded to PROBABILITY_BOUND and 1 -
  PROBABILITY_BOUND) and the Brier score are means over all the rows, one per
  target;
- the calibration splits the probabilities of each target into NB_BINS groups
  of the same size (quantiles, duplicated bounds dropped), and gives for each
  one the mean probability and the observed frequency of the target; a target
  whose probabilities are all equal has no group (no bound can be found).

The computation is free of any Streamlit dependency.
"""

import numpy as np
import pandas as pd

from access_it.analytics.ranking_tools import to_datetime
from access_it.model.forecasts import PROBABILITY_COLUMNS, RANK_COLUMNS, TARGETS

LIST_SIZES = {"win": 10, "podium": 10, "top5": 10, "top10": 20}
LIST_METRICS = [
    "win_recall_at_10", "win_rr_at_10", "podium_recall_at_10", "top5_recall_at_10",
    "top10_recall_at_20",
]
LIST_METRICS_COLUMNS = ["race_id", "race_date", *LIST_METRICS]
PROBABILITY_METRICS_COLUMNS = ["target", "log_loss", "brier", "nb_rows"]
CALIBRATION_COLUMNS = ["target", "bin", "predicted", "observed", "nb_rows"]
PROBABILITY_BOUND = 1e-6
NB_BINS = 10


def compute_list_metrics(forecasts: pd.DataFrame) -> pd.DataFrame:
    """Recalls of the lists of the targets and reciprocal rank of the winner in each race.

    See the module docstring for the rules.

    Args:
        forecasts: One row per race and ranked rider, with race_id,
            race_date, finish_rank (the actual one) and the RANK_COLUMNS.

    Returns:
        One row per race with the LIST_METRICS_COLUMNS: race_id, race_date
        (datetime64[ns]) and the LIST_METRICS (floats, missing where the
        metric is not defined); sorted by race date and race_id, with the
        index reset.

    Raises:
        ValueError: If the ranks of a target are not 1 to the number of
            ranked riders in some races (checked in the order of the
            RANK_COLUMNS, their race_id are given in the message).
    """
    for rank in RANK_COLUMNS:
        ranks = forecasts[["race_id", rank]].sort_values(["race_id", rank])
        is_valid = ranks[rank].eq(ranks.groupby("race_id").cumcount() + 1)
        if not is_valid.all():
            race_ids = ranks.loc[~is_valid, "race_id"].drop_duplicates().tolist()
            raise ValueError(
                f"Races whose {rank} are not 1 to the number of ranked riders: {race_ids!r}"
            )
    terms = {"race_date": forecasts["race_date"]}
    for (target, last_rank), rank in zip(TARGETS.items(), RANK_COLUMNS):
        reached = forecasts["finish_rank"] <= last_rank
        terms[f"{target}_reached"] = reached
        terms[f"{target}_hits"] = reached & (forecasts[rank] <= LIST_SIZES[target])
    # rank_win of the winners, the best one giving the reciprocal rank
    terms["winner_rank"] = forecasts["rank_win"].where(forecasts["finish_rank"] <= TARGETS["win"])
    by_race = pd.DataFrame(terms).groupby(forecasts["race_id"]).agg(
        race_date=("race_date", "first"),
        winner_rank=("winner_rank", "min"),
        **{
            f"{target}_{name}": (f"{target}_{name}", "sum")
            for target in TARGETS for name in ("reached", "hits")
        },
    )
    metrics = by_race.assign(race_date=to_datetime(by_race["race_date"]))
    for target in TARGETS:
        reached = by_race[f"{target}_reached"]
        metrics[f"{target}_recall_at_{LIST_SIZES[target]}"] = (
            by_race[f"{target}_hits"] / reached
        ).where(reached > 0)
    winner_rank = by_race["winner_rank"]
    metrics["win_rr_at_10"] = (1 / winner_rank).where(winner_rank <= LIST_SIZES["win"], 0.0).where(
        winner_rank.notna()
    )
    return (
        metrics.rename_axis("race_id").reset_index()
        .sort_values(["race_date", "race_id"])
        .reset_index(drop=True)[LIST_METRICS_COLUMNS]
        .astype({metric: "float64" for metric in LIST_METRICS})
    )


def compute_probability_metrics(forecasts: pd.DataFrame) -> pd.DataFrame:
    """Log-loss and Brier score of the probabilities of each target, over all the rows.

    See the module docstring for the rules.

    Args:
        forecasts: One row per race and ranked rider, with finish_rank (the
            actual one) and the PROBABILITY_COLUMNS.

    Returns:
        One row per target, in the order of TARGETS, with the
        PROBABILITY_METRICS_COLUMNS: target, log_loss, brier (missing
        without row) and nb_rows.
    """
    rows = []
    for (target, last_rank), probability in zip(TARGETS.items(), PROBABILITY_COLUMNS):
        reached = (forecasts["finish_rank"] <= last_rank).astype(float)
        p = forecasts[probability]
        bounded = p.clip(PROBABILITY_BOUND, 1 - PROBABILITY_BOUND)
        log_loss = -(reached * np.log(bounded) + (1 - reached) * np.log(1 - bounded))
        rows.append({
            "target": target,
            "log_loss": log_loss.mean(),
            "brier": ((p - reached) ** 2).mean(),
            "nb_rows": len(forecasts),
        })
    return pd.DataFrame(rows, columns=PROBABILITY_METRICS_COLUMNS)


def compute_calibration(forecasts: pd.DataFrame) -> pd.DataFrame:
    """Mean probability and observed frequency of each target by group of probabilities.

    See the module docstring for the rules.

    Args:
        forecasts: One row per race and ranked rider, with finish_rank (the
            actual one) and the PROBABILITY_COLUMNS.

    Returns:
        One row per target and group, with the CALIBRATION_COLUMNS: target,
        bin (0 for the lowest probabilities), predicted (mean probability),
        observed (frequency of the target) and nb_rows; sorted by target (in
        the order of TARGETS) and bin, with the index reset.
    """
    if forecasts.empty:
        return pd.DataFrame(columns=CALIBRATION_COLUMNS)
    calibration = []
    for (target, last_rank), probability in zip(TARGETS.items(), PROBABILITY_COLUMNS):
        groups = pd.DataFrame({
            "bin": pd.qcut(forecasts[probability], q=NB_BINS, labels=False, duplicates="drop"),
            "predicted": forecasts[probability],
            "observed": (forecasts["finish_rank"] <= last_rank).astype(float),
        }).groupby("bin").agg(
            predicted=("predicted", "mean"),
            observed=("observed", "mean"),
            nb_rows=("predicted", "size"),
        )
        calibration.append(groups.reset_index().assign(target=target))
    return pd.concat(calibration, ignore_index=True)[CALIBRATION_COLUMNS]
