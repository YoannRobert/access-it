"""Unit tests of the building blocks shared by the rankings."""

import pandas as pd
import pytest

from access_it.analytics.labels import UNKNOWN_CATEGORY, UNKNOWN_CLUB
from access_it.analytics.ranking_tools import (
    SEASON_STATS_COLUMNS, add_category_and_club_on_race_date, add_shared_rank, check_categories,
    check_category, check_race_categories, compute_places, count_wins_and_tops,
    filter_results_by_categories, format_category, get_reference_date, get_region_club_ids,
    get_region_races, rank_scoring_riders, scale_points, select_category, select_club,
    to_datetime
)
from access_it.common.seasons import FIRST_SEASON
from access_it.etl.extract.constants import INDIVIDUAL_CLUB_ID


def test_places_skip_the_next_place_after_tied_riders():
    results = pd.DataFrame({"race_id": ["r1"] * 4 + ["r2"], "finish_rank": [1, 3, 3, 7, 4]})
    assert compute_places(results).tolist() == [1, 2, 2, 4, 1]


def test_wins_and_tops_count_inclusive_tops_and_ties():
    season = FIRST_SEASON + 1
    results = pd.DataFrame({
        "rider_id": ["a"] * 5 + ["b"],
        "season": [season] * 4 + [FIRST_SEASON, season],
        "race_id": ["r1", "r2", "r3", "r4", "r0", "r1"],
        "finish_rank": [1, 1, 5, 21, 20, 3],
    })
    stats = count_wins_and_tops(results)
    assert stats.columns.tolist() == SEASON_STATS_COLUMNS
    assert stats.drop(columns="rider_id").values.tolist() == [
        [FIRST_SEASON, 1, 0, 0, 0, 0, 1],
        [season, 4, 2, 2, 3, 3, 3],
        [season, 1, 0, 1, 1, 1, 1],
    ]


def test_wins_and_tops_by_club():
    results = pd.DataFrame({
        "club_id": ["5244001", "5285001", "5244001", "5244001"],
        "race_id": ["r1", "r1", "r2", "r3"],
        "finish_rank": [1, 2, 4, 25],
    })
    stats = count_wins_and_tops(results, by=("club_id",))
    assert stats.columns.tolist() == ["club_id", *SEASON_STATS_COLUMNS[2:]]
    assert stats.values.tolist() == [
        ["5244001", 3, 1, 1, 2, 2, 2],
        ["5285001", 1, 0, 1, 1, 1, 1],
    ]


def test_points_of_the_scale_and_none_for_an_unknown_category():
    results = pd.DataFrame({"place": [1, 2, 3, 2], "category": ["A1", "A1", "A1", None]})
    assert scale_points(results, (6, 4)).tolist() == [6, 4, 0, 0]


def test_club_shown_skips_the_individual_licences():
    assert select_club(pd.Series([INDIVIDUAL_CLUB_ID, "5244800", "5244001"])) == "5244001"
    assert select_club(pd.Series(["5244800"])) == "5244800"


def test_riders_ranked_by_points_then_places_then_names():
    scoring = pd.DataFrame({
        "race_id": ["r1", "r1", "r2", "r2", "r3"],
        "rider_id": ["a", "b", "b", "c", "c"],
        "club_id": ["X"] * 5,
        "place": [1, 2, 1, 2, 2],
        "category": ["A1"] * 5,
        "points": [6, 4, 6, 4, 4],
    })
    riders = pd.DataFrame(
        {"rider_id": ["a", "b", "c"], "last_name": ["A", "B", "C"], "first_name": "x"}
    )
    clubs = pd.DataFrame({"club_id": ["X"], "name": ["Club X"]})
    ranking = rank_scoring_riders(scoring, riders, clubs, max_place=5)
    assert ranking[["rider_id", "rank", "points", "nb_wins"]].values.tolist() == [
        ["b", 1, 10, 1], ["c", 2, 8, 0], ["a", 3, 6, 1]
    ]


def test_unknown_category_raises():
    with pytest.raises(ValueError, match="Unknown category"):
        select_category(pd.DataFrame(columns=["category"]), "A5")


def test_check_category_accepts_a1_to_a4_and_raises_otherwise():
    for category in ("A1", "A2", "A3", "A4"):
        check_category(category)
    with pytest.raises(ValueError, match="Unknown category: 'A5'"):
        check_category("A5")


def test_category_labels_of_the_history():
    assert [format_category(c) for c in pd.array([1, 4], dtype="Int8")] == ["A1", "A4"]
    assert format_category(pd.NA) is None
    assert format_category(None) is None


def test_reference_date_is_the_day_after_the_last_race():
    races = pd.DataFrame({"race_date": ["2026-10-25", "2026-10-26", "2026-03-01"]})
    assert get_reference_date(races) == pd.Timestamp("2026-10-27")


def test_reference_date_of_an_empty_race_table_raises():
    with pytest.raises(ValueError):
        get_reference_date(pd.DataFrame({"race_date": []}))


def test_clubs_of_a_region_include_the_individual_pseudo_clubs():
    departemental_committees = pd.DataFrame({
        "departemental_committee_id": ["5244", "5285", "5385"],
        "regional_committee_id": ["52", "52", "53"],
    })
    clubs = pd.DataFrame({
        "club_id": ["5244001", "5285001", "5244800", "5385001", "5385800"],
        "departemental_committee_id": ["5244", "5285", "5244", "5385", "5385"],
    })
    club_ids = get_region_club_ids(clubs, departemental_committees, "52")
    assert club_ids.tolist() == ["5244001", "5285001", "5244800"]


def test_races_of_a_region_are_those_of_the_season_in_its_departements():
    departemental_committees = pd.DataFrame({
        "regional_committee_id": ["52", "52", "53"],
        "departement_code": ["44", "85", "56"],
    })
    races = pd.DataFrame({
        "race_id": ["r1", "r2", "r3", "r4"],
        "season": [FIRST_SEASON, FIRST_SEASON, FIRST_SEASON, FIRST_SEASON + 1],
        "departement_code": ["44", "56", "85", "44"],
    })
    region_races = get_region_races(races, departemental_committees, "52", FIRST_SEASON)
    assert region_races.columns.tolist() == races.columns.tolist()
    assert region_races["race_id"].tolist() == ["r1", "r3"]


def test_category_and_club_on_the_race_date_with_labels_when_unknown():
    results = pd.DataFrame({
        "race_id": ["r1", "r2", "r3"],
        "rider_id": ["a", "a", "b"],
        "race_date": to_datetime(pd.Series(
            [f"{FIRST_SEASON}-03-01", f"{FIRST_SEASON}-06-01", f"{FIRST_SEASON}-06-01"]
        )),
    })
    clubs = pd.DataFrame({"club_id": ["5244001"], "name": ["Club Nantes"]})
    affiliations = pd.DataFrame(
        {"rider_id": ["a"], "start_date": [f"{FIRST_SEASON}-05-01"], "club_id": ["5244001"]}
    )
    rider_categories = pd.DataFrame({
        "rider_id": ["a", "a", "b"],
        "start_date": [f"{FIRST_SEASON}-01-01", f"{FIRST_SEASON}-05-01", f"{FIRST_SEASON}-01-01"],
        "rider_category": pd.array([3, 2, None], dtype="Int64"),
    })
    labelled = add_category_and_club_on_race_date(
        results, clubs, affiliations, rider_categories
    ).sort_values("race_id")
    assert "club_id" not in labelled.columns
    assert labelled[["category", "club"]].values.tolist() == [
        ["A3", UNKNOWN_CLUB], ["A2", "Club Nantes"], [UNKNOWN_CATEGORY, UNKNOWN_CLUB]
    ]


def test_requested_categories_are_ordered_without_duplicates():
    assert check_categories(["A3", "A2", "A3"]) == ("A2", "A3")


@pytest.mark.parametrize(
    "categories, message",
    [([], "Invalid categories"), (["A1", "A5"], "Invalid categories"),
     (["A1", "A3"], "Categories not contiguous")]
)
def test_invalid_requested_categories_raise(categories, message):
    with pytest.raises(ValueError, match=message):
        check_categories(categories)


def test_races_with_non_contiguous_categories_raise():
    races = pd.DataFrame({"race_id": ["r1", "r2", "r3"], "categories": ["A1,A2", "A1,A3", "A4"]})
    check_race_categories(races.drop(index=1))
    with pytest.raises(ValueError, match=r"Races with non contiguous categories: \['r2'\]"):
        check_race_categories(races)


# a goes up from A3 to A2 on May 1st; the category of c is unknown
FILTER_RESULTS = pd.DataFrame(
    {
        "race_id": ["r1", "r1", "r2", "r3", "r3"],
        "rider_id": ["a", "b", "a", "c", "b"],
        "race_date": to_datetime(pd.Series([
            f"{FIRST_SEASON}-06-01", f"{FIRST_SEASON}-06-01", f"{FIRST_SEASON}-03-01",
            f"{FIRST_SEASON}-04-01", f"{FIRST_SEASON}-04-01"
        ])).to_numpy(),
        "categories": ["A1,A2", "A1,A2", "A3,A4", "A4", "A4"],
    },
    index=[10, 11, 12, 13, 14]
)
FILTER_RIDER_CATEGORIES = pd.DataFrame({
    "rider_id": ["a", "a", "b"],
    "start_date": [f"{FIRST_SEASON}-01-01", f"{FIRST_SEASON}-05-01", f"{FIRST_SEASON}-01-01"],
    "rider_category": pd.array([3, 2, 1], dtype="Int64"),
})


def test_results_filtered_on_the_categories_of_the_races_keep_order_and_index():
    kept = filter_results_by_categories(
        FILTER_RESULTS, FILTER_RIDER_CATEGORIES, ["A3", "A4"], "race"
    )
    assert kept.columns.tolist() == FILTER_RESULTS.columns.tolist()
    assert kept.index.tolist() == [12, 13, 14]


def test_results_filtered_on_the_categories_of_the_riders_keep_order_and_index():
    kept = filter_results_by_categories(
        FILTER_RESULTS, FILTER_RIDER_CATEGORIES, ["A2", "A3"], "rider"
    )
    assert kept.columns.tolist() == FILTER_RESULTS.columns.tolist()
    assert kept.index.tolist() == [10, 12]


def test_unknown_category_filter_raises():
    with pytest.raises(ValueError, match="Unknown category filter"):
        filter_results_by_categories(FILTER_RESULTS, FILTER_RIDER_CATEGORIES, ["A1"], "club")


def test_rows_tied_on_every_criterion_share_the_rank():
    df = pd.DataFrame(
        {"nb_wins": [3, 2, 2, 2, 1], "nb_top_3": [1, 5, 5, 4, 0], "name": list("vwxyz")},
        index=[7, 3, 9, 1, 5]
    )
    ranked = add_shared_rank(df, ["nb_wins", "nb_top_3"])
    assert ranked.columns.tolist() == ["nb_wins", "nb_top_3", "name", "rank"]
    assert ranked.index.tolist() == [7, 3, 9, 1, 5]
    assert ranked["rank"].tolist() == [1, 2, 2, 4, 5]
