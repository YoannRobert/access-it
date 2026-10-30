"""Unit tests of the statistics of a season."""

import pandas as pd
import pytest

from access_it.analytics.labels import UNKNOWN_CATEGORY, UNKNOWN_CLUB
from access_it.analytics.season_stats import (
    MOST_TITLED_COLUMNS, RACES_BY_CATEGORIES_COLUMNS, RACES_BY_DEPARTEMENT_COLUMNS,
    RACES_BY_MONTH_COLUMNS, RANKED_RIDERS_COLUMNS, SEASON_RESULT_COLUMNS, SeasonSummary,
    compute_season_summary, count_races_by_categories, count_races_by_departement,
    count_races_by_month, count_ranked_riders, get_season_results, rank_most_titled_riders
)
from access_it.common.regions import BRETAGNE, PAYS_DE_LA_LOIRE
from access_it.common.seasons import FIRST_SEASON

SEASON = FIRST_SEASON + 1
NOT_COVERED_REGION = "NORMANDIE"

REGIONAL_COMMITTEES = pd.DataFrame({
    "regional_committee_id": ["52", "53", "54"],
    "name": [PAYS_DE_LA_LOIRE, BRETAGNE, NOT_COVERED_REGION],
})
DEPARTEMENTAL_COMMITTEES = pd.DataFrame({
    "departemental_committee_id": ["5244", "5249", "5285", "5385", "5414"],
    "regional_committee_id": ["52", "52", "52", "53", "54"],
    "departement_code": ["44", "49", "85", "56", "14"],
})
DEPARTEMENTS = pd.DataFrame({
    "departement_code": ["44", "85", "56", "14"],
    "departement_name": ["Loire-Atlantique", "Vendee", "Morbihan", "Calvados"],
})
CLUBS = pd.DataFrame(
    {"club_id": ["5244001", "5285001"], "name": ["Club Nantes", "Club La Roche"]}
)
RIDERS = pd.DataFrame({
    "rider_id": list("abcde"),
    "last_name": [f"NAME_{r}" for r in "abcde"],
    "first_name": [f"First_{r}" for r in "abcde"],
})
# r4 is held in Bretagne, r5 in the previous season, r6 has no ranking (cancelled race)
RACES = pd.DataFrame({
    "race_id": ["r1", "r2", "r3", "r4", "r5", "r6"],
    "season": [SEASON, SEASON, SEASON, SEASON, FIRST_SEASON, SEASON],
    "race_date": [
        f"{SEASON}-03-10", f"{SEASON}-03-17", f"{SEASON}-05-01", f"{SEASON}-06-01",
        f"{FIRST_SEASON}-04-01", f"{SEASON}-07-01"
    ],
    "departement_code": ["44", "85", "44", "56", "44", "44"],
    "categories": ["A1,A2", "A3,A4", "A2,A3", "A1,A2", "A1", "A4"],
})
RANKINGS = pd.DataFrame(
    [
        ("r1", "a", 1), ("r1", "c", 2), ("r1", "d", 3),
        ("r2", "b", 1), ("r2", "d", 2),
        ("r3", "c", 1), ("r3", "b", 2), ("r3", "a", 25), ("r3", "e", 30),
        ("r4", "a", 1), ("r5", "a", 1),
    ],
    columns=["race_id", "rider_id", "finish_rank"]
)
# a goes up from A2 to A1 on April 1st; the category of d is unknown
RIDER_CATEGORIES = pd.DataFrame({
    "rider_id": ["a", "a", "b", "c", "e"],
    "start_date": [
        f"{FIRST_SEASON}-01-01", f"{SEASON}-04-01", f"{FIRST_SEASON}-01-01",
        f"{FIRST_SEASON}-01-01", f"{FIRST_SEASON}-01-01"
    ],
    "rider_category": pd.array([2, 1, 3, 2, 3], dtype="Int64"),
})
# The club of c is only known from April 1st; the clubs of b and d are unknown
AFFILIATIONS = pd.DataFrame({
    "rider_id": ["a", "c"],
    "start_date": [f"{FIRST_SEASON}-01-01", f"{SEASON}-04-01"],
    "club_id": ["5244001", "5285001"],
})


def season_results(races: pd.DataFrame = RACES, **kwargs) -> pd.DataFrame:
    """Results of the season in Pays de la Loire, with the arguments given."""
    return get_season_results(
        races, RANKINGS, DEPARTEMENTAL_COMMITTEES, REGIONAL_COMMITTEES, RIDER_CATEGORIES,
        **{"season": SEASON, "region": PAYS_DE_LA_LOIRE, **kwargs}
    )


def most_titled(results: pd.DataFrame, max_riders: int = 10) -> pd.DataFrame:
    """Most titled riders of the results."""
    return rank_most_titled_riders(
        results, RIDERS, CLUBS, AFFILIATIONS, RIDER_CATEGORIES, SEASON, max_riders
    )


def test_race_filter_keeps_the_ranked_races_of_the_season_and_the_region():
    results = season_results()
    assert results.columns.tolist() == SEASON_RESULT_COLUMNS
    assert results["race_id"].unique().tolist() == ["r1", "r2", "r3"]
    assert results["rider_id"].tolist() == ["a", "c", "d", "b", "d", "c", "b", "a", "e"]


def test_race_filter_keeps_the_races_with_one_requested_category():
    assert season_results(categories=["A4"])["race_id"].unique().tolist() == ["r2"]
    assert season_results(categories=["A1"])["race_id"].unique().tolist() == ["r1"]
    assert season_results(categories=["A2"])["race_id"].unique().tolist() == ["r1", "r3"]


def test_requested_categories_in_any_order_and_with_duplicates():
    pd.testing.assert_frame_equal(
        season_results(categories=["A3", "A2", "A3"]), season_results(categories=["A2", "A3"])
    )


def test_rider_filter_keeps_the_results_in_a_requested_category():
    results = season_results(categories=["A2"], category_filter="rider")
    assert results[["race_id", "rider_id"]].values.tolist() == [
        ["r1", "a"], ["r1", "c"], ["r3", "c"]
    ]
    assert count_races_by_month(results)["nb_races"].tolist()[2:5] == [1, 0, 1]
    assert count_ranked_riders(results)["nb_ranked_riders"].tolist() == [2]


def test_races_by_month_cover_the_twelve_months():
    by_month = count_races_by_month(season_results())
    assert by_month.columns.tolist() == RACES_BY_MONTH_COLUMNS
    assert by_month["month"].tolist() == list(range(1, 13))
    assert by_month["nb_races"].tolist() == [0, 0, 2, 0, 1, 0, 0, 0, 0, 0, 0, 0]


def test_races_by_departement_cover_the_departements_of_the_region():
    by_departement = count_races_by_departement(
        season_results(), DEPARTEMENTS, DEPARTEMENTAL_COMMITTEES, REGIONAL_COMMITTEES,
        PAYS_DE_LA_LOIRE
    )
    assert by_departement.columns.tolist() == RACES_BY_DEPARTEMENT_COLUMNS
    assert by_departement["departement_code"].tolist() == ["44", "49", "85"]
    assert by_departement["nb_races"].tolist() == [2, 0, 1]
    assert pd.isna(by_departement["departement_name"].iloc[1])


def test_races_by_categories_in_the_order_of_the_combinations():
    races = pd.concat([RACES, pd.DataFrame({
        "race_id": ["r7"], "season": [SEASON], "race_date": [f"{SEASON}-08-01"],
        "departement_code": ["85"], "categories": ["A1"],
    })])
    rankings = pd.concat(
        [RANKINGS, pd.DataFrame({"race_id": ["r7"], "rider_id": ["a"], "finish_rank": [1]})]
    )
    results = get_season_results(
        races, rankings, DEPARTEMENTAL_COMMITTEES, REGIONAL_COMMITTEES, RIDER_CATEGORIES,
        SEASON, PAYS_DE_LA_LOIRE
    )
    by_categories = count_races_by_categories(results)
    assert by_categories.columns.tolist() == RACES_BY_CATEGORIES_COLUMNS
    assert by_categories.values.tolist() == [["A1", 1], ["A1,A2", 1], ["A2,A3", 1], ["A3,A4", 1]]


def test_ranked_riders_counted_once():
    ranked = count_ranked_riders(season_results())
    assert ranked.columns.tolist() == RANKED_RIDERS_COLUMNS
    assert ranked["nb_ranked_riders"].tolist() == [5]


def test_most_titled_riders_sorted_with_shared_ranks_and_labels():
    titled = most_titled(season_results())
    assert titled.columns.tolist() == MOST_TITLED_COLUMNS
    columns = ["rank", "last_name", "club", "category", "nb_wins", "nb_races"]
    assert titled[columns].values.tolist() == [
        [1, "NAME_b", UNKNOWN_CLUB, "A3", 1, 2],
        [1, "NAME_c", "Club La Roche", "A2", 1, 2],
        [3, "NAME_a", "Club Nantes", "A1", 1, 2],
        [4, "NAME_d", UNKNOWN_CLUB, UNKNOWN_CATEGORY, 0, 2],
    ]


def test_most_titled_riders_cut_at_max_riders():
    assert most_titled(season_results(), max_riders=1)["last_name"].tolist() == ["NAME_b"]
    assert most_titled(season_results(), max_riders=3)["last_name"].tolist() == [
        "NAME_b", "NAME_c", "NAME_a"
    ]


def test_most_titled_riders_in_rider_filter_keep_the_requested_categories():
    titled = most_titled(season_results(categories=["A2", "A3"], category_filter="rider"))
    row = titled.set_index("last_name").loc["NAME_a"]
    assert titled["last_name"].tolist() == ["NAME_b", "NAME_c", "NAME_a"]
    assert row["category"] == "A2" and row["nb_races"] == 1


@pytest.mark.parametrize("kwargs", [
    {"category_filter": "club"},
    {"region": NOT_COVERED_REGION},
    {"season": FIRST_SEASON - 1},
    {"categories": []},
    {"categories": ["A5"]},
    {"categories": ["A1", "A3"]},
])
def test_invalid_arguments_raise(kwargs):
    with pytest.raises(ValueError):
        season_results(**kwargs)


def test_race_with_non_contiguous_categories_raises_before_any_filter():
    races = pd.concat([RACES, pd.DataFrame({
        "race_id": ["r7"], "season": [SEASON], "race_date": [f"{SEASON}-08-01"],
        "departement_code": ["44"], "categories": ["A1,A3"],
    })])
    with pytest.raises(ValueError, match="non contiguous"):
        season_results(races, categories=["A4"])


def test_departements_of_a_region_not_covered_raise():
    with pytest.raises(ValueError):
        count_races_by_departement(
            season_results(), DEPARTEMENTS, DEPARTEMENTAL_COMMITTEES, REGIONAL_COMMITTEES,
            NOT_COVERED_REGION
        )


def test_max_riders_lower_than_one_raises():
    with pytest.raises(ValueError):
        most_titled(season_results(), max_riders=0)


def test_season_summary_gathers_the_statistics():
    summary = compute_season_summary(
        RACES, RANKINGS, RIDERS, CLUBS, DEPARTEMENTS, DEPARTEMENTAL_COMMITTEES,
        REGIONAL_COMMITTEES, AFFILIATIONS, RIDER_CATEGORIES, SEASON, PAYS_DE_LA_LOIRE
    )
    assert isinstance(summary, SeasonSummary)
    assert len(summary.races_by_month) == 12
    assert len(summary.races_by_departement) == 3
    assert len(summary.races_by_categories) == 3
    assert summary.ranked_riders["nb_ranked_riders"].tolist() == [5]
    assert len(summary.most_titled_riders) == 4
