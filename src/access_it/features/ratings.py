"""OpenSkill ratings of the riders on the eve of each race.

The rating of a rider is a skill estimate mu and its uncertainty sigma, from
the Plackett-Luce model of the openskill library. Rules:

- rate_entries_on_race_eve rates the riders of a table of entries given by
  the caller (checked by check_entries of the entries module): the ranked
  riders of past races, or the riders entered in coming races;
  rate_riders_on_race_eve rates the ranked riders of the races forecast,
  selected by select_forecast_entries of the entries module (see its
  docstring);
- the ratings are built from the results of every race of the seasons
  FIRST_SEASON to the season of the last entry, whatever its number of ranked
  riders, in chronological order; the races before the first entry are not
  rated, but their results update the ratings;
- for each date, the ratings of the riders entered on that day are read
  first (ratings on the eve), then updated with the races of the day, in
  race_id order: no race uses a result of its own day;
- a new rider gets the default rating of the model (mu of 25, sigma given);
- before being read, the sigma of a known rider grows with the number of days
  since his last race (his last result, an entry without result does not
  count): sigma^2 + sigma_growth_per_day^2 * days, capped at the initial
  sigma, and never lowered (no growth with sigma_growth_per_day = 0); the
  grown rating is also the one updated by the race;
- tied riders keep their tie (the finish ranks are given as the ranks of the
  model);
- a race with a single ranked rider does not update the ratings (it says
  nothing about relative skills), but counts as his last race for the
  growth of sigma.

The computation is free of any Streamlit dependency.
"""

import math

import pandas as pd

from openskill.models import PlackettLuce, PlackettLuceRating

from access_it.analytics.ranking_tools import check_race_dates, to_datetime
from access_it.common.seasons import FIRST_SEASON
from access_it.features.entries import check_entries, select_forecast_entries

COLUMNS = ["race_id", "race_date", "rider_id", "finish_rank", "mu", "sigma"]


def check_rating_arguments(
        sigma: float, beta: float, tau: float, sigma_growth_per_day: float
    ) -> None:
    """Check the arguments of the ratings.

    Args:
        sigma: Initial uncertainty of a rating.
        beta: Variability of the performances in a race.
        tau: Uncertainty added to the ratings at each race.
        sigma_growth_per_day: Growth of sigma per day without race.

    Raises:
        ValueError: If sigma is not greater than 0, then if beta is not
            greater than 0, then if tau is negative, then if
            sigma_growth_per_day is negative.
    """
    for name, value in (("sigma", sigma), ("beta", beta)):
        if not value > 0:
            raise ValueError(f"{name} must be greater than 0, not {value}")
    for name, value in (("tau", tau), ("sigma_growth_per_day", sigma_growth_per_day)):
        if value < 0:
            raise ValueError(f"{name} must not be negative, not {value}")


def rate_entries_on_race_eve(
        races: pd.DataFrame,
        rankings: pd.DataFrame,
        entries: pd.DataFrame,
        sigma: float = 25 / 3,
        beta: float = 25 / 6,
        tau: float = 25 / 300,
        sigma_growth_per_day: float = 0.0
    ) -> pd.DataFrame:
    """OpenSkill rating of the riders of a table of entries on the eve of their race.

    See the module docstring for the rules.

    Args:
        races: Race table.
        rankings: Ranking table.
        entries: One row per race and rider entered, with race_id, race_date
            and rider_id; any other column is kept.
        sigma: Initial uncertainty of a rating, greater than 0.
        beta: Variability of the performances in a race, greater than 0.
        tau: Uncertainty added to the ratings at each race, not negative.
        sigma_growth_per_day: Growth of sigma per day without race, not
            negative.

    Returns:
        The columns of the entries (race_date as datetime64[ns]), then mu and
        sigma (rating on the eve of the race); sorted by race date, race_id
        and rider_id, with the index reset.

    Raises:
        ValueError: If sigma is not greater than 0, then if beta is not
            greater than 0, then if tau is negative, then if
            sigma_growth_per_day is negative, then if there is no entry, then
            if a race date of the entries is missing, then if a rider is
            entered twice in a race, then if a race date of the seasons
            FIRST_SEASON to the season of the last entry is missing.
    """
    check_rating_arguments(sigma, beta, tau, sigma_growth_per_day)
    check_entries(entries)
    entries = entries.assign(race_date=to_datetime(entries["race_date"]))
    last_season = entries["race_date"].max().year
    season_races = races.loc[
        races["season"].between(FIRST_SEASON, last_season), ["race_id", "race_date"]
    ].assign(race_date=lambda df: to_datetime(df["race_date"]))
    check_race_dates(season_races["race_date"])
    results = season_races.merge(rankings[["race_id", "rider_id", "finish_rank"]], on="race_id")
    model = PlackettLuce(sigma=sigma, beta=beta, tau=tau)
    ratings = {}
    last_race_dates = {}

    def rating_on_eve(rider_id: str, race_date: pd.Timestamp) -> PlackettLuceRating:
        """Rating of a rider on the eve of a date, sigma grown since his last race."""
        rating = ratings.get(rider_id)
        if rating is None:
            return model.rating()
        if sigma_growth_per_day > 0:
            days = (race_date - last_race_dates[rider_id]).days
            grown_sigma = min(math.sqrt(rating.sigma**2 + sigma_growth_per_day**2 * days), sigma)
            return model.rating(mu=rating.mu, sigma=max(rating.sigma, grown_sigma))
        return rating

    results_by_date = dict(tuple(results.groupby("race_date")))
    entries_by_date = dict(tuple(entries.groupby("race_date")))
    eve_ratings = []
    for race_date in sorted(results_by_date.keys() | entries_by_date.keys()):
        day_entries = entries_by_date.get(race_date)
        if day_entries is not None:
            eve = day_entries["rider_id"].map(lambda rider_id: rating_on_eve(rider_id, race_date))
            eve_ratings.append(day_entries.assign(
                mu=eve.map(lambda rating: rating.mu), sigma=eve.map(lambda rating: rating.sigma)
            ))
        day_results = results_by_date.get(race_date)
        if day_results is None:
            continue
        day_rider_ids = day_results["rider_id"].unique()
        # The grown ratings are the ones updated by the races of the day
        for rider_id in day_rider_ids:
            ratings[rider_id] = rating_on_eve(rider_id, race_date)
        for _, race_results in day_results.groupby("race_id", sort=True):
            if len(race_results) < 2:
                continue
            rider_ids = race_results["rider_id"].tolist()
            new_teams = model.rate(
                [[ratings[rider_id]] for rider_id in rider_ids],
                ranks=race_results["finish_rank"].tolist()
            )
            for rider_id, [new_rating] in zip(rider_ids, new_teams):
                ratings[rider_id] = new_rating
        for rider_id in day_rider_ids:
            last_race_dates[rider_id] = race_date
    return (
        pd.concat(eve_ratings)
        .sort_values(["race_date", "race_id", "rider_id"])
        .reset_index(drop=True)
    )


def rate_riders_on_race_eve(
        races: pd.DataFrame,
        rankings: pd.DataFrame,
        last_season: int,
        first_race_date: str | pd.Timestamp,
        sigma: float = 25 / 3,
        beta: float = 25 / 6,
        tau: float = 25 / 300,
        sigma_growth_per_day: float = 0.0
    ) -> pd.DataFrame:
    """OpenSkill rating of the ranked riders of each race on the eve of the race.

    See the module docstring for the rules.

    Args:
        races: Race table.
        rankings: Ranking table.
        last_season: Last season forecast, as a calendar year, not before
            FIRST_SEASON.
        first_race_date: Day of the first races forecast, as "YYYY-MM-DD" or
            a date (the time of day is ignored), in the seasons FIRST_SEASON
            to last_season.
        sigma: Initial uncertainty of a rating, greater than 0.
        beta: Variability of the performances in a race, greater than 0.
        tau: Uncertainty added to the ratings at each race, not negative.
        sigma_growth_per_day: Growth of sigma per day without race, not
            negative.

    Returns:
        One row per race forecast and ranked rider, with the COLUMNS:
        race_id, race_date (datetime64[ns]), rider_id, finish_rank (the
        actual one), mu and sigma (rating on the eve of the race); sorted by
        race date, race_id and rider_id, with the index reset.

    Raises:
        ValueError: If sigma is not greater than 0, then if beta is not
            greater than 0, then if tau is negative, then if
            sigma_growth_per_day is negative, then if last_season is before
            FIRST_SEASON, then if first_race_date is missing, then if it is
            not in the seasons FIRST_SEASON to last_season, then if a race
            date of these seasons is missing, then if no race with a ranked
            rider is held from first_race_date to the end of last_season.
    """
    check_rating_arguments(sigma, beta, tau, sigma_growth_per_day)
    entries = select_forecast_entries(races, rankings, last_season, first_race_date)
    return rate_entries_on_race_eve(
        races, rankings, entries, sigma, beta, tau, sigma_growth_per_day
    )[COLUMNS]
