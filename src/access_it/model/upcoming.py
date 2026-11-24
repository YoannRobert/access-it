"""Probabilities of the riders entered in upcoming races to win or make the podium, top 5 or top 10.

The forecast chains the features and the model layers on a table of entries
(for instance the entries of the upcoming races built from their startlist
pages). Rules:

- the history is made of the ranked riders of the past races selected by
  select_forecast_entries of the entries module: from the earliest race date
  of the entries minus window_months, to the end of the season of the latest
  race date of the entries; the history and the entries get their features
  from two calls of build_race_eve_features of the examples module, with its
  default settings;
- the probabilities and the ranks are given by forecast_place_probabilities
  of the forecasts module, with the same window_months (see its docstring);
  the features of the entries are kept in the output, to explain the
  forecasts; a date whose training window lacks a place class is not
  forecast, and its races are absent from the output;
- a forecast error must not stop the other forecasts: an empty table of
  entries gives an empty output (logged as an information), and a history
  that cannot be selected (no race in the window, missing race date in the
  results...) gives an empty output, the error being logged as a warning.

The computation is free of any Streamlit dependency.
"""

import logging

import pandas as pd

from access_it.analytics.ranking_tools import check_at_least_one, to_datetime
from access_it.features.entries import check_entries, select_forecast_entries
from access_it.features.examples import FEATURES, build_race_eve_features
from access_it.model.forecasts import (
    PROBABILITY_COLUMNS, RANK_COLUMNS, forecast_place_probabilities
)

logger = logging.getLogger(__name__)


def forecast_upcoming_entries(
        races: pd.DataFrame,
        rankings: pd.DataFrame,
        entries: pd.DataFrame,
        window_months: int = 12
    ) -> pd.DataFrame:
    """Probability and rank of each rider entered in upcoming races to reach each target.

    See the module docstring for the rules.

    Args:
        races: Race table.
        rankings: Ranking table.
        entries: One row per race and rider entered, with race_id, race_date
            and rider_id; any other column is kept.
        window_months: Length of the training window before each date, and of
            the history before the earliest race date, at least 1.

    Returns:
        The output of forecast_place_probabilities: the columns of the
        entries, then the FEATURES of the examples module, the
        PROBABILITY_COLUMNS and the RANK_COLUMNS; the races not forecast are
        absent, and the table is empty (same columns) if no race is forecast.

    Raises:
        ValueError: If window_months is lower than 1, then if a race date of
            the entries is missing, then if a rider is entered twice in a race.
    """
    check_at_least_one(window_months, "window_months")
    empty = pd.DataFrame(
        columns=[*entries.columns, *FEATURES, *PROBABILITY_COLUMNS, *RANK_COLUMNS]
    )
    if entries.empty:
        logger.info("No entries to forecast")
        return empty
    check_entries(entries)
    race_dates = to_datetime(entries["race_date"])
    try:
        past_entries = select_forecast_entries(
            races,
            rankings,
            race_dates.max().year,
            race_dates.min() - pd.DateOffset(months=window_months),
        )
    except ValueError as error:
        logger.warning("No forecast, the history cannot be selected: %s", error)
        return empty
    history = build_race_eve_features(races, rankings, past_entries)
    upcoming = build_race_eve_features(races, rankings, entries)
    return forecast_place_probabilities(history, upcoming, window_months)
