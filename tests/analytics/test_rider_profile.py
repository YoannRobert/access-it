"""Unit tests of the profile of a rider."""

import pandas as pd
import pytest

from access_it.analytics.labels import NOT_APPLICABLE, UNKNOWN_CATEGORY, UNKNOWN_CLUB
from access_it.analytics.promotion_points import compute_promotion_points
from access_it.analytics.regional_rankings import compute_challenge_points
from access_it.analytics.ranking_tools import get_rider_results
from access_it.analytics.rider_profile import (
    SEASON_POINTS_COLUMNS, RiderProfile, compute_rider_profile, compute_season_points,
    get_rider_categories, get_rider_clubs
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
RIDERS = pd.DataFrame({"rider_id": ["a", "b"]})


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


def test_category_periods_from_the_first_season_to_the_reference_date():
    rider_categories = pd.DataFrame({
        "rider_id": ["a"] * 5 + ["b"],
        "start_date": [
            f"{FIRST_SEASON - 2}-01-01", f"{FIRST_SEASON - 1}-06-01", f"{SEASON}-03-01",
            f"{SEASON}-06-01", REFERENCE_DATE, f"{SEASON}-01-01"
        ],
        "rider_category": pd.array([4, 3, None, 2, 1, 4], dtype="Int64"),
    })
    periods = get_rider_categories(RIDERS, rider_categories, "a", REFERENCE_DATE)
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
    periods = get_rider_clubs(RIDERS, CLUBS, affiliations, "a", REFERENCE_DATE)
    assert periods["club"].tolist() == ["Club Nantes", UNKNOWN_CLUB]


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


def test_challenge_not_applicable_when_the_region_has_no_challenge():
    tables = make_tables(
        races=[("r1", f"{SEASON}-03-01", "56")],
        results=[("r1", "b", 1)],
        clubs={"b": [(f"{SEASON}-01-01", BZH)]},
        categories={"b": [(f"{SEASON}-01-01", 3)]},
    )
    points = compute_season_points(
        results_of(tables, "b"), points_of([]), points_of([]), CLUBS, DEPARTEMENTAL_COMMITTEES,
        REGIONAL_COMMITTEES, tables["affiliations"], region=BRETAGNE
    )
    row = points.set_index(["rider_id", "season"]).loc[("b", SEASON)]
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
        *common, RIDERS, CLUBS, DEPARTEMENTAL_COMMITTEES, REGIONAL_COMMITTEES,
        tables["affiliations"], tables["rider_categories"], promotion, challenge, "a",
        REFERENCE_DATE
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
        tables["races"], tables["rankings"], RIDERS, CLUBS, DEPARTEMENTAL_COMMITTEES,
        REGIONAL_COMMITTEES, tables["affiliations"], tables["rider_categories"], points_of([]),
        points_of([]), "a", REFERENCE_DATE
    )
    assert profile.results.empty and profile.season_stats.empty and profile.season_points.empty
    assert profile.season_points.columns.tolist() == SEASON_POINTS_COLUMNS
    assert len(profile.categories) == 1 and len(profile.clubs) == 1
    assert profile.recent_form[["nb_races_used", "top_n_rate"]].values.tolist() == [[0, 0.0]]


@pytest.mark.parametrize("compute", [
    lambda tables: get_rider_categories(RIDERS, tables["rider_categories"], "x", REFERENCE_DATE),
    lambda tables: get_rider_clubs(RIDERS, CLUBS, tables["affiliations"], "x", REFERENCE_DATE),
    lambda tables: compute_rider_profile(
        tables["races"], tables["rankings"], RIDERS, CLUBS, DEPARTEMENTAL_COMMITTEES,
        REGIONAL_COMMITTEES, tables["affiliations"], tables["rider_categories"], points_of([]),
        points_of([]), "x", REFERENCE_DATE
    ),
], ids=["categories", "clubs", "profile"])
def test_unknown_rider_raises(compute):
    tables = make_tables(
        races=[("r1", f"{SEASON}-03-01", "44")],
        results=[("r1", "a", 1)],
        clubs={"a": [(f"{SEASON}-01-01", PDL)]},
        categories={"a": [(f"{SEASON}-01-01", 3)]},
    )
    with pytest.raises(ValueError, match="Unknown rider: 'x'"):
        compute(tables)


def test_rider_categories_missing_start_date_raises():
    rider_categories = pd.DataFrame(
        {"rider_id": ["a"], "start_date": [None], "rider_category": pd.array([3], dtype="Int64")}
    )
    with pytest.raises(ValueError, match="Missing start dates in the history"):
        get_rider_categories(RIDERS, rider_categories, "a", REFERENCE_DATE)


def test_rider_categories_unknown_rider_raises_before_missing_start_date():
    rider_categories = pd.DataFrame(
        {"rider_id": ["x"], "start_date": [None], "rider_category": pd.array([3], dtype="Int64")}
    )
    with pytest.raises(ValueError, match="Unknown rider: 'x'"):
        get_rider_categories(RIDERS, rider_categories, "x", REFERENCE_DATE)


def test_rider_clubs_missing_start_date_raises():
    affiliations = pd.DataFrame({"rider_id": ["a"], "start_date": [None], "club_id": [PDL]})
    with pytest.raises(ValueError, match="Missing start dates in the history"):
        get_rider_clubs(RIDERS, CLUBS, affiliations, "a", REFERENCE_DATE)


def test_rider_clubs_unknown_rider_raises_before_missing_start_date():
    affiliations = pd.DataFrame({"rider_id": ["x"], "start_date": [None], "club_id": [PDL]})
    with pytest.raises(ValueError, match="Unknown rider: 'x'"):
        get_rider_clubs(RIDERS, CLUBS, affiliations, "x", REFERENCE_DATE)


def test_rider_categories_missing_reference_date_raises():
    rider_categories = pd.DataFrame({
        "rider_id": ["a"], "start_date": [f"{SEASON}-01-01"],
        "rider_category": pd.array([3], dtype="Int64"),
    })
    with pytest.raises(ValueError, match="Missing reference date"):
        get_rider_categories(RIDERS, rider_categories, "a", None)


@pytest.mark.parametrize("rider_id, start_date, message", [
    ("x", f"{SEASON}-01-01", "Unknown rider: 'x'"),
    ("a", None, "Missing reference date"),
], ids=["unknown-rider", "missing-start-date"])
def test_rider_categories_missing_reference_date_raises_in_order(rider_id, start_date, message):
    rider_categories = pd.DataFrame({
        "rider_id": [rider_id], "start_date": [start_date],
        "rider_category": pd.array([3], dtype="Int64"),
    })
    with pytest.raises(ValueError, match=message):
        get_rider_categories(RIDERS, rider_categories, rider_id, None)


def test_rider_clubs_missing_reference_date_raises():
    affiliations = pd.DataFrame(
        {"rider_id": ["a"], "start_date": [f"{SEASON}-01-01"], "club_id": [PDL]}
    )
    with pytest.raises(ValueError, match="Missing reference date"):
        get_rider_clubs(RIDERS, CLUBS, affiliations, "a", None)


@pytest.mark.parametrize("rider_id, start_date, message", [
    ("x", f"{SEASON}-01-01", "Unknown rider: 'x'"),
    ("a", None, "Missing reference date"),
], ids=["unknown-rider", "missing-start-date"])
def test_rider_clubs_missing_reference_date_raises_in_order(rider_id, start_date, message):
    affiliations = pd.DataFrame(
        {"rider_id": [rider_id], "start_date": [start_date], "club_id": [PDL]}
    )
    with pytest.raises(ValueError, match=message):
        get_rider_clubs(RIDERS, CLUBS, affiliations, rider_id, None)


def profile_tables() -> dict:
    """Tables of one race of rider a."""
    return make_tables(
        races=[("r1", f"{SEASON}-03-01", "44")],
        results=[("r1", "a", 1)],
        clubs={"a": [(f"{SEASON}-01-01", PDL)]},
        categories={"a": [(f"{SEASON}-01-01", 3)]},
    )


def season_points_with(rider_results: pd.DataFrame, affiliations: pd.DataFrame) -> pd.DataFrame:
    """compute_season_points without points, with the given results and affiliations."""
    return compute_season_points(
        rider_results, points_of([]), points_of([]), CLUBS, DEPARTEMENTAL_COMMITTEES,
        REGIONAL_COMMITTEES, affiliations
    )


def profile_with(
        tables: dict,
        rider_id: str = "a",
        region: str = PAYS_DE_LA_LOIRE,
        reference_date: str | None = REFERENCE_DATE,
        **kwargs
    ) -> RiderProfile:
    """compute_rider_profile on the tables, without points (kwargs: recent form arguments)."""
    return compute_rider_profile(
        tables["races"], tables["rankings"], RIDERS, CLUBS, DEPARTEMENTAL_COMMITTEES,
        REGIONAL_COMMITTEES, tables["affiliations"], tables["rider_categories"], points_of([]),
        points_of([]), rider_id, reference_date, region, **kwargs
    )


@pytest.mark.parametrize("table, column, message", [
    ("rider_results", "race_date", "Missing race dates in the results"),
    ("affiliations", "start_date", "Missing start dates in the history"),
])
def test_season_points_missing_date_raises(table, column, message):
    tables = profile_tables()
    tables["rider_results"] = results_of(tables)
    tables[table].loc[0, column] = None
    with pytest.raises(ValueError, match=message):
        season_points_with(tables["rider_results"], tables["affiliations"])


def test_season_points_missing_race_date_raises_before_missing_start_date():
    tables = profile_tables()
    rider_results = results_of(tables)
    rider_results.loc[0, "race_date"] = None
    tables["affiliations"].loc[0, "start_date"] = None
    with pytest.raises(ValueError, match="Missing race dates in the results"):
        season_points_with(rider_results, tables["affiliations"])


@pytest.mark.parametrize("table, column, message", [
    ("races", "race_date", "Missing race dates in the results"),
    ("rider_categories", "start_date", "Missing start dates in the history"),
    ("affiliations", "start_date", "Missing start dates in the history"),
])
def test_rider_profile_missing_date_raises(table, column, message):
    tables = profile_tables()
    tables[table].loc[0, column] = None
    with pytest.raises(ValueError, match=message):
        profile_with(tables)


def test_rider_profile_missing_race_date_raises_before_missing_start_date():
    tables = profile_tables()
    tables["races"].loc[0, "race_date"] = None
    tables["rider_categories"].loc[0, "start_date"] = None
    with pytest.raises(ValueError, match="Missing race dates in the results"):
        profile_with(tables)


def test_rider_profile_unknown_rider_raises_before_missing_race_date():
    tables = make_tables(
        races=[("r1", None, "44")],
        results=[("r1", "x", 1)],
        clubs={"x": [(f"{SEASON}-01-01", PDL)]},
        categories={"x": [(f"{SEASON}-01-01", 3)]},
    )
    with pytest.raises(ValueError, match="Unknown rider: 'x'"):
        profile_with(tables, rider_id="x")


def test_rider_profile_unknown_region_raises_before_missing_race_date():
    tables = profile_tables()
    tables["races"].loc[0, "race_date"] = None
    with pytest.raises(ValueError, match="Unknown region"):
        profile_with(tables, region="NOWHERE")


@pytest.mark.parametrize("kwargs, message", [
    ({"top_n": 21}, "top_n must be between 1 and 20"),
    ({"last_races": 0}, "last_races must be at least 1"),
    ({"window_months": 0}, "window_months must be at least 1"),
])
def test_rider_profile_invalid_recent_form_arguments_raise(kwargs, message):
    with pytest.raises(ValueError, match=message):
        profile_with(profile_tables(), **kwargs)


def test_rider_profile_invalid_top_n_raises_before_unknown_rider():
    with pytest.raises(ValueError, match="top_n must be between 1 and 20"):
        profile_with(profile_tables(), rider_id="x", top_n=21)


def test_rider_profile_missing_reference_date_raises():
    with pytest.raises(ValueError, match="Missing reference date"):
        profile_with(profile_tables(), reference_date=None)


@pytest.mark.parametrize("region, race_date, message", [
    ("NOWHERE", f"{SEASON}-03-01", "Unknown region"),
    (PAYS_DE_LA_LOIRE, None, "Missing reference date"),
], ids=["unknown-region", "missing-race-date"])
def test_rider_profile_missing_reference_date_raises_in_order(region, race_date, message):
    tables = profile_tables()
    tables["races"].loc[0, "race_date"] = race_date
    with pytest.raises(ValueError, match=message):
        profile_with(tables, region=region, reference_date=None)
