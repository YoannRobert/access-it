"""OpenSkill ratings of the riders on the eve of each race.

The rating of a rider is a skill estimate mu and its uncertainty sigma, from
the Plackett-Luce model of the openskill library. Rules:

- the races forecast and their start lists (their ranked riders) are
  selected by select_forecast_entries of the entries module (see its
  docstring);
- the ratings are built from the results of every race of the seasons
  FIRST_SEASON to last_season, whatever its number of ranked riders, in
  chronological order; the races before first_race_date are not forecast,
  but their results update the ratings;
- for each race date, the ratings of all the ranked riders of the day are
  read first (ratings on the eve), then updated with the races of the day,
  in race_id order: no race uses a result of its own day;
- a new rider gets the default rating of the model (mu of 25, sigma given);
- before being read, the sigma of a known rider grows with the number of days
  since his last race: sigma^2 + sigma_growth_per_day^2 * days, capped at the
  initial sigma, and never lowered (no growth with sigma_growth_per_day = 0);
  the grown rating is also the one updated by the race;
- tied riders keep their tie (the finish ranks are given as the ranks of the
  model);
- a race with a single ranked rider does not update the ratings (it says
  nothing about relative skills), but counts as his last race for the
  growth of sigma.

The computation is free of any Streamlit dependency.
"""

import math

import pandas as pd

from openskill.models import PlackettLuce

from access_it.common.seasons import FIRST_SEASON
from access_it.features.entries import select_forecast_entries

COLUMNS = ["race_id", "race_date", "rider_id", "finish_rank", "mu", "sigma"]


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
    for name, value in (("sigma", sigma), ("beta", beta)):
        if not value > 0:
            raise ValueError(f"{name} must be greater than 0, not {value}")
    for name, value in (("tau", tau), ("sigma_growth_per_day", sigma_growth_per_day)):
        if value < 0:
            raise ValueError(f"{name} must not be negative, not {value}")
    forecast_entries = select_forecast_entries(races, rankings, last_season, first_race_date)
    all_entries = select_forecast_entries(
        races, rankings, last_season, f"{FIRST_SEASON}-01-01"
    )
    forecast_race_ids = set(forecast_entries["race_id"])
    model = PlackettLuce(sigma=sigma, beta=beta, tau=tau)
    ratings = {}
    last_race_dates = {}
    eve_ratings = []
    for race_date, day_entries in all_entries.groupby("race_date"):
        day_rider_ids = day_entries["rider_id"].unique()
        # Ratings on the eve of the day, sigma grown since the last race of each rider
        for rider_id in day_rider_ids:
            rating = ratings.get(rider_id)
            if rating is None:
                ratings[rider_id] = model.rating()
            elif sigma_growth_per_day > 0:
                days = (race_date - last_race_dates[rider_id]).days
                grown_sigma = min(
                    math.sqrt(rating.sigma**2 + sigma_growth_per_day**2 * days), sigma
                )
                ratings[rider_id] = model.rating(mu=rating.mu, sigma=max(rating.sigma, grown_sigma))
        day_forecasts = day_entries[day_entries["race_id"].isin(forecast_race_ids)]
        if not day_forecasts.empty:
            eve_ratings.append(day_forecasts.assign(
                mu=day_forecasts["rider_id"].map(lambda rider_id: ratings[rider_id].mu),
                sigma=day_forecasts["rider_id"].map(lambda rider_id: ratings[rider_id].sigma),
            ))
        for _, race_results in day_entries.groupby("race_id", sort=True):
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
        .reset_index(drop=True)[COLUMNS]
    )
