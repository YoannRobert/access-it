"""Probabilities of the riders entered in each race to win or make the podium, top 5 or top 10.

The forecast is made by a multiclass XGBoost model on place classes. Rules:

- the place class of a ranked rider is 0 for a win, 1 for the 2nd and 3rd
  places, 2 for the 4th and 5th, 3 for the 6th to 10th, 4 beyond (absolute
  finish ranks, tied riders all count);
- one model is trained per date of the entries (the races of the same day
  share it), on the rows of the history held from the date minus
  window_months (included) to the eve of the date: no race uses a result of
  its own day; the features are the FEATURES of the examples module; the
  training rows are sorted by race date, race_id and rider_id, so that the
  models do not depend on the order of the history (the trees of XGBoost
  change with the order of the rows);
- a date whose training window does not hold the five place classes (or no
  row at all) is not forecast: its entries are absent from the output, and
  the dates skipped are logged as a warning;
- the probabilities of the classes of each race are normalized by Sinkhorn
  scaling (normalize_place_classes): each rider sums to 1, and the classes
  hold 1, 2, 2, 5 and n - 10 riders (n riders entered, the numbers being
  brought down to n in a race of fewer than 10 riders); the probabilities of
  the targets (TARGETS) are then the cumulative sums of the classes;
- the rank of a rider for a target orders the riders of his race by
  decreasing probability, then by rider_id, so that it is unique (1 to the
  number of riders entered).

The computation is free of any Streamlit dependency.
"""

import logging

import numpy as np
import pandas as pd

from xgboost import XGBClassifier

from access_it.analytics.ranking_tools import check_at_least_one, to_datetime
from access_it.features.entries import check_entries
from access_it.features.examples import FEATURES

logger = logging.getLogger(__name__)

TARGETS = {"win": 1, "podium": 3, "top5": 5, "top10": 10}  # last finish rank of each target
PROBABILITY_COLUMNS = [f"p_{target}" for target in TARGETS]
RANK_COLUMNS = [f"rank_{target}" for target in TARGETS]
XGB_PARAMS = {
    "n_estimators": 200,
    "max_depth": 3,
    "learning_rate": 0.1,
    "tree_method": "hist",
    "n_jobs": 1,
    "objective": "multi:softprob",
}
NB_CLASSES = len(TARGETS) + 1
MAX_ITERATIONS = 200
TOLERANCE = 1e-9
PROBABILITY_FLOOR = 1e-12


def normalize_place_classes(probabilities: np.ndarray) -> np.ndarray:
    """Probabilities of the place classes of the riders of a race, adjusted by Sinkhorn scaling.

    See the module docstring for the rules. The rows and the columns are
    scaled one after the other, up to MAX_ITERATIONS times, until the class
    sums are within TOLERANCE of their numbers of riders; the probabilities
    are first floored at PROBABILITY_FLOOR.

    Args:
        probabilities: One row per rider of the race and one column per place
            class (NB_CLASSES).

    Returns:
        The adjusted probabilities, same shape: each row sums to 1, each
        column to its number of riders (a class without rider gets 0).
    """
    nb_riders = len(probabilities)
    cumulative = np.minimum([*TARGETS.values(), nb_riders], nb_riders)
    class_sizes = np.diff(np.concatenate([[0], cumulative])).astype(float)
    adjusted = np.clip(probabilities, PROBABILITY_FLOOR, None)
    for _ in range(MAX_ITERATIONS):
        column_sums = adjusted.sum(axis=0)
        adjusted = adjusted * np.divide(
            class_sizes, column_sums, out=np.zeros_like(class_sizes), where=column_sums > 0
        )
        adjusted = adjusted / adjusted.sum(axis=1, keepdims=True)
        if np.abs(adjusted.sum(axis=0) - class_sizes).max() < TOLERANCE:
            break
    return adjusted


def forecast_place_probabilities(
        history: pd.DataFrame,
        entries: pd.DataFrame,
        window_months: int = 12
    ) -> pd.DataFrame:
    """Probability and rank of each rider entered to win, make the podium, the top 5 or the top 10.

    See the module docstring for the rules.

    Args:
        history: Rows used to train the models: one row per past race and
            ranked rider, with race_id, race_date, rider_id, finish_rank and
            the FEATURES, as returned by build_race_eve_features.
        entries: Rows to forecast: one row per race and rider entered, with
            race_id, race_date, rider_id and the FEATURES; any other column
            is kept.
        window_months: Length of the training window before each date, at
            least 1.

    Returns:
        The columns of the entries (race_date as datetime64[ns]), then the
        PROBABILITY_COLUMNS (p_win, p_podium, p_top5, p_top10) and the
        RANK_COLUMNS (rank_win, rank_podium, rank_top5, rank_top10); sorted
        by race date, race_id and rank_win, with the index reset. The dates
        not forecast are absent.

    Raises:
        ValueError: If window_months is lower than 1, then if there is no
            entry, then if a race date of the entries is missing, then if a
            rider is entered twice in a race, then if a finish rank of the
            history is missing.
    """
    check_at_least_one(window_months, "window_months")
    check_entries(entries)
    if history["finish_rank"].isna().any():
        raise ValueError("Missing finish ranks in the history")
    history = history.assign(
        race_date=lambda df: to_datetime(df["race_date"]),
        place_class=pd.cut(
            history["finish_rank"], bins=[0, *TARGETS.values(), np.inf], labels=False
        ),
    ).sort_values(["race_date", "race_id", "rider_id"])
    entries = entries.reset_index(drop=True).assign(
        race_date=lambda df: to_datetime(df["race_date"])
    )
    forecasts = []
    skipped_dates = []
    for race_date, day_entries in entries.groupby("race_date"):
        start = race_date - pd.DateOffset(months=window_months)
        train = history[(history["race_date"] >= start) & (history["race_date"] < race_date)]
        if train["place_class"].nunique() < NB_CLASSES:
            skipped_dates.append(race_date.date().isoformat())
            continue
        model = XGBClassifier(**XGB_PARAMS)
        model.fit(train[FEATURES], train["place_class"])
        day_classes = model.predict_proba(day_entries[FEATURES])
        day_probabilities = np.empty((len(day_entries), len(TARGETS)))
        for positions in day_entries.groupby("race_id").indices.values():
            normalized = normalize_place_classes(day_classes[positions])
            day_probabilities[positions] = normalized.cumsum(axis=1)[:, :len(TARGETS)]
        forecasts.append(day_entries.assign(**dict(zip(PROBABILITY_COLUMNS, day_probabilities.T))))
    if skipped_dates:
        logger.warning(
            "Dates skipped, their training window lacks a place class: %s", skipped_dates
        )
    columns = [*entries.columns, *PROBABILITY_COLUMNS, *RANK_COLUMNS]
    if not forecasts:
        return pd.DataFrame(columns=columns)
    forecasts = pd.concat(forecasts)
    for probability, rank in zip(PROBABILITY_COLUMNS, RANK_COLUMNS):
        ordered = forecasts.sort_values(
            ["race_id", probability, "rider_id"], ascending=[True, False, True]
        )
        forecasts[rank] = ordered.groupby("race_id").cumcount() + 1
    return (
        forecasts.sort_values(["race_date", "race_id", "rank_win"])
        .reset_index(drop=True)[columns]
    )
