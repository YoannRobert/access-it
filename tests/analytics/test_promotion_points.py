"""Unit tests of the promotion points of the Access riders."""

import pandas as pd
import pytest

from access_it.analytics.promotion_points import (
    COLUMNS, PROMOTION_SCALE, compute_promotion_points, compute_promotion_rankings,
    get_promotion_ranking
)
from access_it.common.regions import BRETAGNE, PAYS_DE_LA_LOIRE
from access_it.etl.extract.constants import FOREIGN_CLUB_ID, INDIVIDUAL_CLUB_ID

SEASON = 2026

REGIONAL_COMMITTEES = pd.DataFrame({
    "regional_committee_id": ["52", "53", "98", "99"],
    "name": [PAYS_DE_LA_LOIRE, BRETAGNE, "INDIVIDUEL", "ETRANGER"],
})
DEPARTEMENTAL_COMMITTEES = pd.DataFrame({
    "departemental_committee_id": ["5244", "5385", "9898", "9999"],
    "name": ["LOIRE-ATLANTIQUE", "MORBIHAN", "INDIVIDUEL", "ETRANGER"],
    "regional_committee_id": ["52", "53", "98", "99"],
    "departement_code": ["44", "56", "98", "99"],
})
CLUBS = pd.DataFrame({
    "club_id": ["5244001", "5385001", INDIVIDUAL_CLUB_ID, FOREIGN_CLUB_ID, "5385800"],
    "name": ["Club Nantes", "Club Vannes", "Individuel", "Etranger", "Individuel 56"],
    "departemental_committee_id": ["5244", "5385", "9898", "9999", "5385"],
})
PDL, BZH, IND, FOR, IND_BZH = CLUBS["club_id"]


def make_tables(races: list[tuple], results: list[tuple], clubs: dict, categories: dict) -> dict:
    """Tables of a small season.

    Args:
        races: (race_id, race_date) tuples.
        results: (race_id, rider_id, finish_rank) tuples.
        clubs: rider_id -> list of (start_date, club_id) periods.
        categories: rider_id -> list of (start_date, category or None) periods.
    """
    rider_ids = sorted({rider_id for _, rider_id, _ in results})
    return {
        "races": pd.DataFrame(races, columns=["race_id", "race_date"]).assign(season=SEASON),
        "rankings": pd.DataFrame(results, columns=["race_id", "rider_id", "finish_rank"]),
        "riders": pd.DataFrame({
            "rider_id": rider_ids,
            "last_name": [f"NAME_{r}" for r in rider_ids],
            "first_name": [f"First_{r}" for r in rider_ids],
        }),
        "clubs": CLUBS,
        "departemental_committees": DEPARTEMENTAL_COMMITTEES,
        "regional_committees": REGIONAL_COMMITTEES,
        "affiliations": pd.DataFrame(
            [(r, s, c) for r, periods in clubs.items() for s, c in periods],
            columns=["rider_id", "start_date", "club_id"]
        ),
        "rider_categories": pd.DataFrame(
            [(r, s, c) for r, periods in categories.items() for s, c in periods],
            columns=["rider_id", "start_date", "rider_category"]
        ).astype({"rider_category": "Int64"}),
    }


def single_race(ranks: dict[str, int], clubs: dict[str, str], categories: dict[str, int | None]):
    """Tables of a single race, each rider with one club and one category."""
    return make_tables(
        races=[("r1", "2026-06-07")],
        results=[("r1", rider_id, rank) for rider_id, rank in ranks.items()],
        clubs={r: [("2026-01-01", c)] for r, c in clubs.items()},
        categories={r: [("2026-01-01", c)] for r, c in categories.items()},
    )


def points_of(tables: dict) -> dict[str, int]:
    """Points per rider, race by race summed."""
    df = compute_promotion_points(
        tables["races"], tables["rankings"], tables["affiliations"], tables["rider_categories"],
        season=SEASON
    )
    return df.groupby("rider_id")["points"].sum().to_dict()


def rankings_of(tables: dict) -> pd.DataFrame:
    return compute_promotion_rankings(**tables, season=SEASON)


def test_scale_of_the_first_five_places():
    assert PROMOTION_SCALE == (6, 4, 3, 2, 1)
    riders = [f"r{i}" for i in range(1, 7)]
    tables = single_race(
        ranks={r: i for i, r in enumerate(riders, start=1)},
        clubs={r: PDL for r in riders},
        categories={r: 3 for r in riders},
    )
    assert points_of(tables) == {"r1": 6, "r2": 4, "r3": 3, "r4": 2, "r5": 1, "r6": 0}


def test_foreign_rider_is_removed_and_riders_of_every_region_count():
    tables = single_race(
        ranks={"a": 1, "b": 2, "c": 3, "d": 4},
        clubs={"a": FOR, "b": BZH, "c": IND, "d": PDL},
        categories={"a": 3, "b": 3, "c": 3, "d": 3},
    )
    assert points_of(tables) == {"b": 6, "c": 4, "d": 3}


def test_tied_riders_share_the_points_and_unknown_category_scores_nothing():
    tables = single_race(
        ranks={"a": 1, "b": 1, "c": 3, "d": 4},
        clubs={"a": PDL, "b": PDL, "c": PDL, "d": PDL},
        categories={"a": 2, "b": 2, "c": None, "d": 2},
    )
    assert points_of(tables) == {"a": 6, "b": 6, "c": 0, "d": 2}


def test_each_category_has_its_own_total():
    tables = make_tables(
        races=[("r1", "2026-04-01"), ("r2", "2026-05-01"), ("r3", "2026-07-01")],
        results=[("r1", "a", 1), ("r2", "b", 1), ("r2", "a", 2), ("r3", "a", 1)],
        clubs={"a": [("2026-01-01", PDL)], "b": [("2026-01-01", PDL)]},
        categories={"a": [("2026-01-01", 4), ("2026-06-15", 3)], "b": [("2026-01-01", 2)]},
    )
    ranking = rankings_of(tables)
    ranking = ranking[ranking["last_name"] == "NAME_a"]
    assert ranking.set_index("category")[["points", "nb_scoring_races", "nb_wins"]].to_dict(
        orient="index"
    ) == {
        "A3": {"points": 6, "nb_scoring_races": 1, "nb_wins": 1},
        "A4": {"points": 10, "nb_scoring_races": 2, "nb_wins": 1},
    }


def test_columns_and_first_region_of_the_season():
    tables = make_tables(
        races=[("r1", "2026-03-01"), ("r2", "2026-05-01")],
        results=[("r1", "a", 1), ("r2", "a", 1)],
        clubs={"a": [("2026-01-01", BZH), ("2026-04-01", PDL)]},
        categories={"a": [("2026-01-01", 2)]},
    )
    ranking = get_promotion_ranking(rankings_of(tables), "A2")
    assert ranking.columns.tolist() == [c for c in COLUMNS if c != "category"]
    assert ranking.iloc[0].tolist() == [1, 12, "NAME_a", "First_a", "Club Vannes", 2, 2, BRETAGNE]


def test_region_filter_keeps_the_national_total_and_ranks_again():
    tables = make_tables(
        races=[("r1", "2026-03-01"), ("r2", "2026-05-01")],
        # a: Bretagne only; b: Bretagne then Pays de la Loire; c: Pays de la Loire;
        # d: individual licensee of unknown committee
        results=[
            ("r1", "a", 1), ("r1", "b", 2), ("r1", "c", 3), ("r1", "d", 4),
            ("r2", "c", 1), ("r2", "b", 2), ("r2", "d", 3),
        ],
        clubs={
            "a": [("2026-01-01", IND_BZH)],
            "b": [("2026-01-01", BZH), ("2026-04-01", PDL)],
            "c": [("2026-01-01", PDL)],
            "d": [("2026-01-01", IND)],
        },
        categories={r: [("2026-01-01", 1)] for r in "abcd"},
    )
    rankings = rankings_of(tables)
    national = get_promotion_ranking(rankings, "A1")
    assert national[["last_name", "rank", "points"]].values.tolist() == [
        ["NAME_c", 1, 9], ["NAME_b", 2, 8], ["NAME_a", 3, 6], ["NAME_d", 4, 5]
    ]
    pdl = get_promotion_ranking(rankings, "A1", PAYS_DE_LA_LOIRE, REGIONAL_COMMITTEES)
    assert pdl[["last_name", "rank", "points", "region"]].values.tolist() == [
        ["NAME_c", 1, 9, PAYS_DE_LA_LOIRE], ["NAME_b", 2, 8, BRETAGNE]
    ]
    bzh = get_promotion_ranking(rankings, "A1", BRETAGNE, REGIONAL_COMMITTEES)
    assert bzh["last_name"].tolist() == ["NAME_b", "NAME_a"]
    assert bzh["rank"].tolist() == [1, 2]
    assert pd.isna(national.set_index("last_name").loc["NAME_d", "region"])


def test_unknown_region_or_category_raises():
    tables = single_race(ranks={"a": 1}, clubs={"a": PDL}, categories={"a": 4})
    rankings = rankings_of(tables)
    with pytest.raises(ValueError, match="Unknown region"):
        get_promotion_ranking(rankings, "A4", "Pays de la Loire", REGIONAL_COMMITTEES)
    with pytest.raises(ValueError, match="Unknown category"):
        get_promotion_ranking(rankings, "A5")


def test_empty_season_gives_an_empty_ranking():
    tables = single_race(ranks={"a": 1}, clubs={"a": PDL}, categories={"a": 4})
    rankings = compute_promotion_rankings(**tables, season=SEASON - 1)
    assert rankings.empty
    assert get_promotion_ranking(rankings, "A4").empty
