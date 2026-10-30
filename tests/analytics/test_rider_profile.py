"""Unit tests of the profile of a rider."""

import pandas as pd
import pytest

from access_it.analytics.labels import NOT_APPLICABLE, UNKNOWN_CATEGORY, UNKNOWN_CLUB
from access_it.analytics.promotion_points import compute_promotion_points
from access_it.analytics.regional_rankings import compute_challenge_points
from access_it.analytics.rider_profile import (
    RESULT_COLUMNS, SEASON_POINTS_COLUMNS, SEASON_STATS_COLUMNS, RiderProfile,
    compute_rider_profile, compute_season_points, compute_season_stats, get_rider_categories,
    get_rider_clubs, get_rider_results
)
from access_it.common.regions import BRETAGNE, PAYS_DE_LA_LOIRE
from access_it.common.seasons import FIRST_SEASON

SEASON = FIRST_SEASON + 1
REFERENCE_DATE = f"{SEASON}-10-01"

REGIONAL_COMMITTEES = pd.DataFrame({
    "regional_committee_id": ["52", "53"],
    "name": [PAYS_DE_LA_LOIRE, BRETAGNE],
})
DEPARTEMENTAL_COMMITTEES = pd.DataFrame({
    "departemental_committee_id": ["5244", "5385"],
    "regional_committee_id": ["52", "53"],
    "departement_code": ["44", "56"],
})
CLUBS = pd.DataFrame({
    "club_id": ["5244001", "5385001"],
    "name": ["Club Nantes", "Club Vannes"],
    "departemental_committee_id": ["5244", "5385"],
})
PDL, BZH = CLUBS["club_id"]


def make_tables(races: list[tuple], results: list[tuple], clubs: dict, categories: dict) -> dict:
    """Tables of a few races.

    Args:
        races: (race_id, race_date, departement_code) tuples.
        results: (race_id, rider_id, finish_rank) tuples.
        clubs: rider_id -> list of (start_date, club_id) periods.
        categories: rider_id -> list of (start_date, category or None) periods.
    """
    races = pd.DataFrame(races, columns=["race_id", "race_date", "departement_code"])
    return {
        "races": races.assign(
            season=pd.to_datetime(races["race_date"]).dt.year, title=races["race_id"] + " title"
        ),
        "rankings": pd.DataFrame(results, columns=["race_id", "rider_id", "finish_rank"]),
        "affiliations": pd.DataFrame(
            [(r, s, c) for r, periods in clubs.items() for s, c in periods],
            columns=["rider_id", "start_date", "club_id"]
        ),
        "rider_categories": pd.DataFrame(
            [(r, s, c) for r, periods in categories.items() for s, c in periods],
            columns=["rider_id", "start_date", "rider_category"]
        ).astype({"rider_category": "Int64"}),
    }


def results_of(tables: dict, rider_id: str = "a") -> pd.DataFrame:
    """Results of a rider on REFERENCE_DATE."""
    return get_rider_results(
        tables["races"], tables["rankings"], CLUBS, tables["affiliations"],
        tables["rider_categories"], rider_id, REFERENCE_DATE
    )


def points_of(points: list[tuple]) -> pd.DataFrame:
    """Race by race points from (race_id, rider_id, category, points) tuples."""
    return pd.DataFrame(points, columns=["race_id", "rider_id", "category", "points"])


def season_points_of(tables: dict, promotion: list[tuple], challenge: list[tuple]) -> pd.DataFrame:
    """Season points of the riders of the tables, indexed by (rider_id, season)."""
    results = pd.concat(results_of(tables, r) for r in tables["rankings"]["rider_id"].unique())
    return compute_season_points(
        results, points_of(promotion), points_of(challenge), CLUBS, DEPARTEMENTAL_COMMITTEES,
        REGIONAL_COMMITTEES, tables["affiliations"]
    ).set_index(["rider_id", "season"])


def test_results_from_the_most_recent_with_category_and_club_on_the_race_date():
    tables = make_tables(
        races=[("r1", f"{SEASON}-03-01", "44"), ("r2", f"{SEASON}-06-01", "56")],
        results=[("r1", "a", 4), ("r2", "a", 1)],
        clubs={"a": [(f"{SEASON}-01-01", PDL), (f"{SEASON}-05-01", BZH)]},
        categories={"a": [(f"{SEASON}-01-01", 3), (f"{SEASON}-05-01", 2)]},
    )
    results = results_of(tables)
    assert results.columns.tolist() == RESULT_COLUMNS
    assert results["category"].dtype == "str"
    assert results[["race_id", "finish_rank", "category", "club"]].values.tolist() == [
        ["r2", 1, "A2", "Club Vannes"], ["r1", 4, "A3", "Club Nantes"]
    ]


def test_results_keep_the_seasons_covered_before_the_reference_date():
    tables = make_tables(
        races=[
            ("r0", f"{FIRST_SEASON - 1}-06-01", "44"), ("r1", f"{SEASON}-09-30", "44"),
            ("r2", REFERENCE_DATE, "44")
        ],
        results=[("r0", "a", 1), ("r1", "a", 1), ("r2", "a", 1)],
        clubs={"a": [(f"{FIRST_SEASON - 1}-01-01", PDL)]},
        categories={"a": [(f"{FIRST_SEASON - 1}-01-01", 1)]},
    )
    assert results_of(tables)["race_id"].tolist() == ["r1"]


def test_results_of_the_same_day_keep_the_best_place_first():
    tables = make_tables(
        races=[("r1", f"{SEASON}-06-01", "44"), ("r2", f"{SEASON}-06-01", "44")],
        results=[("r1", "a", 5), ("r2", "a", 2)],
        clubs={"a": [(f"{SEASON}-01-01", PDL)]},
        categories={"a": [(f"{SEASON}-01-01", 3)]},
    )
    assert results_of(tables)["race_id"].tolist() == ["r2", "r1"]


def test_results_with_unknown_category_and_club():
    tables = make_tables(
        races=[("r1", f"{SEASON}-03-01", "44")],
        results=[("r1", "a", 1)],
        clubs={"a": [(f"{SEASON}-06-01", PDL)]},
        categories={"a": [(f"{SEASON}-01-01", None)]},
    )
    assert results_of(tables)[["category", "club"]].values.tolist() == [
        [UNKNOWN_CATEGORY, UNKNOWN_CLUB]
    ]


def test_category_periods_from_the_first_season_to_the_reference_date():
    rider_categories = pd.DataFrame({
        "rider_id": ["a"] * 5 + ["b"],
        "start_date": [
            f"{FIRST_SEASON - 2}-01-01", f"{FIRST_SEASON - 1}-06-01", f"{SEASON}-03-01",
            f"{SEASON}-06-01", REFERENCE_DATE, f"{SEASON}-01-01"
        ],
        "rider_category": pd.array([4, 3, None, 2, 1, 4], dtype="Int64"),
    })
    periods = get_rider_categories(rider_categories, "a", REFERENCE_DATE)
    assert periods.columns.tolist() == ["rider_id", "start_date", "end_date", "category"]
    assert periods["category"].tolist() == ["A3", UNKNOWN_CATEGORY, "A2"]
    assert periods["start_date"].tolist() == pd.to_datetime(
        [f"{FIRST_SEASON}-01-01", f"{SEASON}-03-01", f"{SEASON}-06-01"]
    ).tolist()
    assert periods["end_date"].iloc[:2].tolist() == pd.to_datetime(
        [f"{SEASON}-02-28" if SEASON % 4 else f"{SEASON}-02-29", f"{SEASON}-05-31"]
    ).tolist()
    assert periods["end_date"].isna().iloc[-1]


def test_club_periods_with_an_unknown_club():
    affiliations = pd.DataFrame({
        "rider_id": ["a", "a"],
        "start_date": [f"{SEASON}-01-01", f"{SEASON}-05-01"],
        "club_id": [PDL, "0000000"],
    })
    periods = get_rider_clubs(CLUBS, affiliations, "a", REFERENCE_DATE)
    assert periods["club"].tolist() == ["Club Nantes", UNKNOWN_CLUB]


def test_season_stats_count_inclusive_tops_and_ties():
    results = pd.DataFrame({
        "rider_id": ["a"] * 5 + ["b"],
        "season": [SEASON] * 4 + [FIRST_SEASON, SEASON],
        "race_id": ["r1", "r2", "r3", "r4", "r0", "r1"],
        "finish_rank": [1, 1, 5, 21, 20, 3],
    })
    stats = compute_season_stats(results)
    assert stats.columns.tolist() == SEASON_STATS_COLUMNS
    assert stats.drop(columns="rider_id").values.tolist() == [
        [FIRST_SEASON, 1, 0, 0, 0, 0, 1],
        [SEASON, 4, 2, 2, 3, 3, 3],
        [SEASON, 1, 0, 1, 1, 1, 1],
    ]


def test_season_points_by_category_held():
    tables = make_tables(
        races=[("r1", f"{SEASON}-03-01", "44"), ("r2", f"{SEASON}-06-01", "56")],
        results=[("r1", "a", 1), ("r2", "a", 1)],
        clubs={"a": [(f"{SEASON}-01-01", PDL)]},
        categories={"a": [(f"{SEASON}-01-01", 3), (f"{SEASON}-05-01", 2)]},
    )
    points = season_points_of(tables, promotion=[("r1", "a", "A3", 6)], challenge=[])
    row = points.loc[("a", SEASON)]
    assert points.reset_index().columns.tolist() == SEASON_POINTS_COLUMNS
    assert row["promotion_points_a3"] == 6 and row["promotion_points_a2"] == 0
    assert row["challenge_points_a3"] == 0 and row["challenge_points_a2"] == 0
    assert pd.isna(row["promotion_points_a1"]) and pd.isna(row["challenge_points_a4"])
    assert pd.isna(row["challenge"])


def test_challenge_not_applicable_when_no_club_of_the_region():
    tables = make_tables(
        races=[("r1", f"{SEASON}-03-01", "44")],
        results=[("r1", "b", 1)],
        clubs={"b": [(f"{SEASON}-01-01", BZH)]},
        categories={"b": [(f"{SEASON}-01-01", 3)]},
    )
    points = season_points_of(tables, promotion=[("r1", "b", "A3", 6)], challenge=[])
    row = points.loc[("b", SEASON)]
    assert row["promotion_points_a3"] == 6
    assert row[[f"challenge_points_a{c}" for c in range(1, 5)]].isna().all()
    assert row["challenge"] == NOT_APPLICABLE


def test_unknown_region_raises():
    tables = make_tables(
        races=[("r1", f"{SEASON}-03-01", "44")],
        results=[("r1", "a", 1)],
        clubs={"a": [(f"{SEASON}-01-01", PDL)]},
        categories={"a": [(f"{SEASON}-01-01", 3)]},
    )
    with pytest.raises(ValueError, match="Unknown region"):
        compute_season_points(
            results_of(tables), points_of([]), points_of([]), CLUBS, DEPARTEMENTAL_COMMITTEES,
            REGIONAL_COMMITTEES, tables["affiliations"], region="NOWHERE"
        )


def test_profile_from_the_computed_points():
    tables = make_tables(
        races=[("r1", f"{SEASON}-03-01", "44"), ("r2", f"{SEASON}-06-01", "56")],
        results=[("r1", "a", 1), ("r1", "b", 2), ("r2", "a", 2), ("r2", "b", 1)],
        clubs={"a": [(f"{SEASON}-01-01", PDL)], "b": [(f"{SEASON}-01-01", BZH)]},
        categories={"a": [(f"{SEASON}-01-01", 3)], "b": [(f"{SEASON}-01-01", 3)]},
    )
    common = (tables["races"], tables["rankings"])
    promotion = compute_promotion_points(
        *common, tables["affiliations"], tables["rider_categories"], SEASON
    )
    challenge = compute_challenge_points(
        *common, CLUBS, DEPARTEMENTAL_COMMITTEES, REGIONAL_COMMITTEES, tables["affiliations"],
        tables["rider_categories"], SEASON
    )
    profile = compute_rider_profile(
        *common, CLUBS, DEPARTEMENTAL_COMMITTEES, REGIONAL_COMMITTEES, tables["affiliations"],
        tables["rider_categories"], promotion, challenge, "a", REFERENCE_DATE
    )
    assert isinstance(profile, RiderProfile)
    assert profile.season_stats[["nb_races", "nb_wins"]].values.tolist() == [[2, 1]]
    points = profile.season_points.iloc[0]
    assert (points["promotion_points_a3"], points["challenge_points_a3"]) == (10, 30)
    assert profile.recent_form[["rider_id", "nb_races_used", "nb_top_n"]].values.tolist() == [
        ["a", 1, 1]
    ]


def test_profile_of_a_rider_without_race():
    tables = make_tables(
        races=[("r1", f"{SEASON}-03-01", "44")],
        results=[("r1", "b", 1)],
        clubs={"a": [(f"{SEASON}-01-01", PDL)], "b": [(f"{SEASON}-01-01", PDL)]},
        categories={"a": [(f"{SEASON}-01-01", 3)], "b": [(f"{SEASON}-01-01", 3)]},
    )
    profile = compute_rider_profile(
        tables["races"], tables["rankings"], CLUBS, DEPARTEMENTAL_COMMITTEES,
        REGIONAL_COMMITTEES, tables["affiliations"], tables["rider_categories"], points_of([]),
        points_of([]), "a", REFERENCE_DATE
    )
    assert profile.results.empty and profile.season_stats.empty and profile.season_points.empty
    assert profile.season_points.columns.tolist() == SEASON_POINTS_COLUMNS
    assert len(profile.categories) == 1 and len(profile.clubs) == 1
    assert profile.recent_form[["nb_races_used", "top_n_rate"]].values.tolist() == [[0, 0.0]]
