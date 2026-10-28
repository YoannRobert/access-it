"""Unit tests of the regional Access rankings (regional challenge)."""

import pandas as pd
import pytest

from access_it.analytics.regional_rankings import (
    COLUMNS, PAYS_DE_LA_LOIRE, POINTS_SCALES, compute_challenge_points,
    compute_regional_rankings, get_category_ranking
)
from access_it.etl.extract.constants import FOREIGN_CLUB_ID, INDIVIDUAL_CLUB_ID

SEASON = 2026

REGIONAL_COMMITTEES = pd.DataFrame({
    "regional_committee_id": ["52", "53", "98", "99"],
    "name": [PAYS_DE_LA_LOIRE, "BRETAGNE", "INDIVIDUEL", "ETRANGER"],
})
DEPARTEMENTAL_COMMITTEES = pd.DataFrame({
    "departemental_committee_id": ["5244", "5385", "9898", "9999"],
    "name": ["LOIRE-ATLANTIQUE", "MORBIHAN", "INDIVIDUEL", "ETRANGER"],
    "regional_committee_id": ["52", "53", "98", "99"],
    "departement_code": ["44", "56", "98", "99"],
})
CLUBS = pd.DataFrame({
    "club_id": [
        "5244001", "5244002", "5385001", INDIVIDUAL_CLUB_ID, FOREIGN_CLUB_ID, "5244800", "5385800"
    ],
    "name": [
        "Club Nantes", "Club Heric", "Club Vannes", "Individuel", "Etranger",
        "Individuel 44", "Individuel 56"
    ],
    "departemental_committee_id": ["5244", "5244", "5385", "9898", "9999", "5244", "5385"],
})
PDL, PDL_2, BZH, IND, FOR, IND_PDL, IND_BZH = CLUBS["club_id"]


def make_tables(races: list[tuple], results: list[tuple], clubs: dict, categories: dict) -> dict:
    """Tables of a small season.

    Args:
        races: (race_id, race_date, departement_code) tuples.
        results: (race_id, rider_id, finish_rank) tuples.
        clubs: rider_id -> list of (start_date, club_id) periods.
        categories: rider_id -> list of (start_date, category or None) periods.
    """
    rider_ids = sorted({rider_id for _, rider_id, _ in results})
    return {
        "races": pd.DataFrame(races, columns=["race_id", "race_date", "departement_code"]).assign(
            season=SEASON
        ),
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


def single_race(ranks: dict[str, int], clubs: dict[str, str], categories: dict[str, int | None],
                departement_code: str = "44") -> dict:
    """Tables of a single race in June, each rider with one club and one category."""
    return make_tables(
        races=[("r1", "2026-06-07", departement_code)],
        results=[("r1", rider_id, rank) for rider_id, rank in ranks.items()],
        clubs={r: [("2026-01-01", c)] for r, c in clubs.items()},
        categories={r: [("2026-01-01", c)] for r, c in categories.items()},
    )


def points_of(tables: dict) -> dict[str, int]:
    """Points per rider of the challenge, race by race summed."""
    tables = {k: v for k, v in tables.items() if k != "riders"}
    df = compute_challenge_points(**tables, season=SEASON)
    return df.groupby("rider_id")["points"].sum().to_dict()


def test_points_scale():
    scale = POINTS_SCALES[PAYS_DE_LA_LOIRE]
    assert len(scale) == 20
    assert scale[:7] == (30, 26, 24, 22, 20, 15, 14)
    assert scale[18] == 2  # 19th place
    assert scale[19] == 1


def test_rider_of_another_region_is_removed_and_next_riders_move_up():
    tables = single_race(
        ranks={"a": 1, "b": 2, "c": 3},
        clubs={"a": PDL, "b": BZH, "c": PDL},
        categories={"a": 3, "b": 3, "c": 3},
    )
    assert points_of(tables) == {"a": 30, "c": 26}


def test_foreign_rider_and_individual_licensee_of_unknown_committee_are_removed():
    tables = single_race(
        ranks={"a": 1, "b": 2, "c": 3},
        clubs={"a": FOR, "b": IND, "c": PDL},
        categories={"a": 3, "b": 3, "c": 3},
    )
    assert points_of(tables) == {"c": 30}


def test_race_held_outside_the_region_is_ignored():
    tables = single_race(
        ranks={"a": 1, "b": 2},
        clubs={"a": PDL, "b": IND_PDL},
        categories={"a": 3, "b": 3},
        departement_code="56",
    )
    assert points_of(tables) == {}


def test_nineteenth_place_scores_two_points():
    riders = [f"r{i:02d}" for i in range(1, 23)]
    tables = single_race(
        ranks={r: i for i, r in enumerate(riders, start=1)},
        clubs={r: PDL for r in riders},
        categories={r: 4 for r in riders},
    )
    points = points_of(tables)
    assert points["r19"] == 2
    assert points["r20"] == 1
    assert points["r21"] == 0


def test_no_reranking_by_category_in_a_race_of_several_categories():
    tables = single_race(
        ranks={"a": 1, "b": 2, "c": 3, "d": 4},
        clubs={"a": PDL, "b": PDL, "c": PDL, "d": PDL},
        categories={"a": 1, "b": 1, "c": 1, "d": 2},
    )
    df = compute_challenge_points(
        **{k: v for k, v in tables.items() if k != "riders"}, season=SEASON
    )
    first_a2 = df[df["category"] == "A2"].iloc[0]
    assert (first_a2["place"], first_a2["points"]) == (4, 22)


def test_tied_riders_share_the_points_and_the_next_place_is_skipped():
    tables = single_race(
        ranks={"a": 1, "b": 2, "c": 3, "d": 3, "e": 5},
        clubs={"a": PDL, "b": BZH, "c": PDL, "d": PDL, "e": PDL},
        categories={"a": 3, "b": 3, "c": 3, "d": 3, "e": 3},
    )
    assert points_of(tables) == {"a": 30, "c": 26, "d": 26, "e": 22}


def test_rider_of_unknown_category_keeps_his_place_without_points():
    tables = single_race(
        ranks={"a": 1, "b": 2, "c": 3},
        clubs={"a": PDL, "b": PDL, "c": PDL},
        categories={"a": 3, "b": None, "c": 3},
    )
    assert points_of(tables) == {"a": 30, "b": 0, "c": 24}


def test_rider_without_category_period_keeps_his_place_without_points():
    tables = single_race(
        ranks={"a": 1, "b": 2},
        clubs={"a": PDL, "b": PDL},
        categories={"a": 3},
    )
    assert points_of(tables) == {"a": 30, "b": 0}


def test_change_of_category_keeps_the_points_of_the_former_category():
    tables = make_tables(
        races=[("r1", "2026-05-01", "44"), ("r2", "2026-07-01", "44"), ("r3", "2026-09-30", "44")],
        results=[("r1", "a", 1), ("r2", "a", 1), ("r3", "a", 2)],
        clubs={"a": [("2026-01-01", PDL)]},
        categories={"a": [("2026-01-01", 4), ("2026-06-15", 3)]},
    )
    rankings = compute_regional_rankings(**tables, season=SEASON)
    # Alone in the challenge in r3, the rider is 1st there despite his 2nd finish rank
    assert rankings.set_index("category")["points"].to_dict() == {"A3": 60, "A4": 30}


def test_change_of_region_during_the_season_keeps_the_points():
    tables = make_tables(
        races=[("r1", "2026-04-01", "44"), ("r2", "2026-08-01", "44")],
        results=[("r1", "a", 1), ("r2", "a", 1)],
        clubs={"a": [("2026-01-01", PDL), ("2026-06-01", BZH)]},
        categories={"a": [("2026-01-01", 3)]},
    )
    assert points_of(tables) == {"a": 30}


def test_tie_in_points_broken_by_places_then_names():
    tables = make_tables(
        races=[("r1", "2026-05-01", "44"), ("r2", "2026-06-01", "44")],
        results=[
            ("r1", "b", 1), ("r1", "a", 2), ("r1", "c", 3),
            ("r2", "c", 1), ("r2", "a", 2), ("r2", "b", 3),
        ],
        clubs={r: [("2026-01-01", PDL)] for r in "abc"},
        categories={r: [("2026-01-01", 2)] for r in "abc"},
    )
    ranking = get_category_ranking(compute_regional_rankings(**tables, season=SEASON), "A2")
    # b and c: 30 + 24 = 54 with one 1st place each, tie broken by last name; a: 52
    assert ranking["last_name"].tolist() == ["NAME_b", "NAME_c", "NAME_a"]
    assert ranking["points"].tolist() == [54, 54, 52]
    assert ranking["rank"].tolist() == [1, 2, 3]


def test_more_first_places_wins_a_tie_in_points():
    fillers = ["f1", "f2", "f3", "f4", "f5"]
    tables = make_tables(
        races=[("r1", "2026-05-01", "44"), ("r2", "2026-06-01", "44")],
        # a: 30 (one 1st place); b: 15 + 15 (two 6th places); fillers are A2 riders
        results=[
            ("r1", "a", 1), *[("r1", f, i) for i, f in enumerate(fillers[:4], start=2)], ("r1", "b", 6),
            *[("r2", f, i) for i, f in enumerate(fillers, start=1)], ("r2", "b", 6),
        ],
        clubs={r: [("2026-01-01", PDL)] for r in ["a", "b", *fillers]},
        categories={"a": [("2026-01-01", 1)], "b": [("2026-01-01", 1)],
                    **{f: [("2026-01-01", 2)] for f in fillers}},
    )
    ranking = get_category_ranking(compute_regional_rankings(**tables, season=SEASON), "A1")
    assert ranking[["last_name", "points"]].values.tolist() == [["NAME_a", 30], ["NAME_b", 30]]


def test_club_shown_is_the_first_scoring_club_unless_individual():
    tables = make_tables(
        races=[("r1", "2026-03-01", "44"), ("r2", "2026-05-01", "44"), ("r3", "2026-07-01", "44")],
        results=[("r1", "a", 1), ("r2", "a", 1), ("r3", "a", 1),
                 ("r1", "b", 2), ("r2", "b", 2), ("r3", "b", 2)],
        clubs={
            "a": [("2026-01-01", IND_PDL), ("2026-04-01", PDL_2), ("2026-06-01", PDL)],
            "b": [("2026-01-01", BZH), ("2026-04-01", PDL)],
        },
        categories={"a": [("2026-01-01", 3)], "b": [("2026-01-01", 3)]},
    )
    ranking = compute_regional_rankings(**tables, season=SEASON).set_index("last_name")
    assert ranking.loc["NAME_a", "club"] == "Club Heric"
    assert ranking.loc["NAME_b", "club"] == "Club Nantes"
    assert ranking.loc["NAME_b", "nb_scoring_races"] == 2


def test_output_columns_and_season_filter():
    tables = single_race(ranks={"a": 1}, clubs={"a": PDL}, categories={"a": 4})
    rankings = compute_regional_rankings(**tables, season=SEASON)
    assert rankings.columns.tolist() == COLUMNS
    assert rankings.iloc[0].tolist() == ["A4", 1, 30, "NAME_a", "First_a", "Club Nantes", 1]
    empty = compute_regional_rankings(**tables, season=SEASON - 1)
    assert empty.empty and empty.columns.tolist() == COLUMNS


def test_unknown_or_unconfigured_region_raises():
    tables = single_race(ranks={"a": 1}, clubs={"a": PDL}, categories={"a": 4})
    with pytest.raises(ValueError, match="Unknown region"):
        compute_regional_rankings(**tables, season=SEASON, region="Pays de la Loire")
    with pytest.raises(ValueError, match="No regional ranking configured"):
        compute_regional_rankings(**tables, season=SEASON, region="BRETAGNE")


def test_unknown_category_raises():
    with pytest.raises(ValueError, match="Unknown category"):
        get_category_ranking(pd.DataFrame(columns=COLUMNS), "A5")


def test_individual_licensee_counts_in_the_region_of_his_committee():
    tables = single_race(
        ranks={"a": 1, "b": 2, "c": 3},
        clubs={"a": IND_BZH, "b": IND_PDL, "c": PDL},
        categories={"a": 3, "b": 3, "c": 3},
    )
    assert points_of(tables) == {"b": 30, "c": 26}


def test_club_shown_skips_the_pseudo_club_of_a_committee():
    tables = make_tables(
        races=[("r1", "2026-03-01", "44"), ("r2", "2026-05-01", "44")],
        results=[("r1", "a", 1), ("r2", "a", 1)],
        clubs={"a": [("2026-01-01", IND_PDL), ("2026-04-01", PDL_2)]},
        categories={"a": [("2026-01-01", 3)]},
    )
    ranking = compute_regional_rankings(**tables, season=SEASON)
    assert ranking["club"].tolist() == ["Club Heric"]
