"""Unit tests of the building blocks shared by the rankings."""

from datetime import date

import pandas as pd
import pytest

from access_it.analytics.labels import UNKNOWN_CATEGORY, UNKNOWN_CLUB
from access_it.analytics.ranking_tools import (
    RIDER_RESULT_COLUMNS, SEASON_STATS_COLUMNS, add_category_and_club_on_race_date,
    add_category_on_race_date, add_shared_rank, add_value_on_race_date, check_at_least_one,
    check_categories, check_category, check_race_categories, check_race_dates,
    check_recent_form_arguments, check_rider, check_start_dates,
    compute_places, count_wins_and_tops, filter_results_by_categories, format_category,
    format_club, get_reference_date, get_region_club_ids, get_region_races,
    get_regional_committee_id, get_rider_results, rank_scoring_riders, scale_points,
    select_category, select_club, to_datetime, to_day
)
from access_it.common.regions import BRETAGNE, PAYS_DE_LA_LOIRE
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


def test_check_rider_accepts_a_known_rider_and_raises_otherwise():
    riders = pd.DataFrame({"rider_id": ["a", "b"]})
    check_rider(riders, "a")
    with pytest.raises(ValueError, match="Unknown rider: 'x'"):
        check_rider(riders, "x")


def test_check_at_least_one_accepts_one_and_raises_below():
    check_at_least_one(1, "max_riders")
    with pytest.raises(ValueError, match="max_riders must be at least 1, not 0"):
        check_at_least_one(0, "max_riders")


VALID_RECENT_FORM_ARGUMENTS = {"top_n": 20, "last_races": 10, "window_months": 6}


def test_check_recent_form_arguments_accepts_the_bounds():
    for kwargs in ({"top_n": 1}, {"top_n": 20}, {"last_races": 1}, {"window_months": 1}):
        check_recent_form_arguments(**{**VALID_RECENT_FORM_ARGUMENTS, **kwargs})


@pytest.mark.parametrize("kwargs, message", [
    ({"top_n": 0}, "top_n must be between 1 and 20, not 0"),
    ({"top_n": 21}, "top_n must be between 1 and 20, not 21"),
    ({"last_races": 0}, "last_races must be at least 1, not 0"),
    ({"last_races": -1}, "last_races must be at least 1, not -1"),
    ({"window_months": 0}, "window_months must be at least 1, not 0"),
])
def test_check_recent_form_arguments_raises(kwargs, message):
    with pytest.raises(ValueError, match=message):
        check_recent_form_arguments(**{**VALID_RECENT_FORM_ARGUMENTS, **kwargs})


@pytest.mark.parametrize("kwargs, message", [
    ({"top_n": 21, "last_races": 0}, "top_n must be between 1 and 20"),
    ({"last_races": 0, "window_months": 0}, "last_races must be at least 1"),
])
def test_check_recent_form_arguments_raises_in_order(kwargs, message):
    with pytest.raises(ValueError, match=message):
        check_recent_form_arguments(**{**VALID_RECENT_FORM_ARGUMENTS, **kwargs})


def test_regional_committee_id_of_a_known_region_and_raises_otherwise():
    regional_committees = pd.DataFrame({
        "regional_committee_id": ["52", "53"], "name": [PAYS_DE_LA_LOIRE, BRETAGNE]
    })
    assert get_regional_committee_id(regional_committees, BRETAGNE) == "53"
    with pytest.raises(ValueError, match="Unknown region"):
        get_regional_committee_id(regional_committees[:1], BRETAGNE)


def test_check_race_dates_accepts_dates_and_raises_on_a_missing_one():
    check_race_dates(to_datetime(pd.Series([f"{FIRST_SEASON}-06-01"])))
    with pytest.raises(ValueError, match="Missing race dates in the results"):
        check_race_dates(to_datetime(pd.Series([f"{FIRST_SEASON}-06-01", None])))


def test_check_start_dates_accepts_dates_and_raises_on_a_missing_one():
    check_start_dates(to_datetime(pd.Series([f"{FIRST_SEASON}-01-01"])))
    with pytest.raises(ValueError, match="Missing start dates in the history"):
        check_start_dates(to_datetime(pd.Series([f"{FIRST_SEASON}-01-01", None])))


def test_category_labels_of_the_history():
    assert [format_category(c) for c in pd.array([1, 4], dtype="Int8")] == ["A1", "A4"]
    assert format_category(pd.NA) is None
    assert format_category(None) is None


def test_club_names_with_a_label_when_unknown():
    clubs = pd.DataFrame({"club_id": ["5244001"], "name": ["Club Nantes"]})
    club_ids = pd.Series(["5244001", "5244999", None], index=[3, 1, 2])
    names = format_club(club_ids, clubs)
    assert names.index.tolist() == [3, 1, 2]
    assert names.tolist() == ["Club Nantes", UNKNOWN_CLUB, UNKNOWN_CLUB]


def test_reference_date_is_the_day_after_the_last_race():
    races = pd.DataFrame({"race_date": ["2026-10-25", "2026-10-26", "2026-03-01"]})
    assert get_reference_date(races) == pd.Timestamp("2026-10-27")


def test_reference_date_of_an_empty_race_table_raises():
    with pytest.raises(ValueError, match="No race to find the reference date from"):
        get_reference_date(pd.DataFrame({"race_date": []}))


def test_reference_date_is_brought_back_to_its_day():
    day = pd.Timestamp("2026-07-01")
    assert to_day("2026-07-01") == day
    assert to_day(date(2026, 7, 1)) == day
    assert to_day(pd.Timestamp("2026-07-01 18:00")) == day


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


@pytest.mark.parametrize("race_dates", [
    [f"{FIRST_SEASON}-06-01", f"{FIRST_SEASON}-03-01"],
    [date(FIRST_SEASON, 6, 1), date(FIRST_SEASON, 3, 1)],
    pd.to_datetime([f"{FIRST_SEASON}-06-01", f"{FIRST_SEASON}-03-01"]).as_unit("us"),
])
def test_value_on_the_race_date_whatever_the_type_of_the_race_dates(race_dates):
    results = pd.DataFrame({"rider_id": ["a", "a"], "race_date": race_dates})
    history = pd.DataFrame({
        "rider_id": ["a", "a"],
        "start_date": [f"{FIRST_SEASON}-01-01", f"{FIRST_SEASON}-05-01"],
        "club_id": ["c1", "c2"],
    })
    on_date = add_value_on_race_date(results, history, "club_id")
    assert on_date["race_date"].dtype == "datetime64[ns]"
    assert on_date["race_date"].tolist() == [
        pd.Timestamp(f"{FIRST_SEASON}-03-01"), pd.Timestamp(f"{FIRST_SEASON}-06-01")
    ]
    assert on_date["club_id"].tolist() == ["c1", "c2"]


def test_value_on_the_race_date_sorted_by_date_with_the_index_reset():
    results = pd.DataFrame(
        {"rider_id": ["a", "a"], "race_date": [f"{FIRST_SEASON}-06-01", f"{FIRST_SEASON}-03-01"]},
        index=[7, 3]
    )
    history = pd.DataFrame({
        "rider_id": ["a", "a"],
        "start_date": [f"{FIRST_SEASON}-01-01", f"{FIRST_SEASON}-05-01"],
        "club_id": ["c1", "c2"],
    })
    on_date = add_value_on_race_date(results, history, "club_id")
    assert on_date.index.tolist() == [0, 1]
    assert on_date["race_date"].is_monotonic_increasing


@pytest.mark.parametrize("missing_date", [None, ""])
def test_missing_race_date_raises(missing_date):
    results = pd.DataFrame(
        {"rider_id": ["a", "a"], "race_date": [f"{FIRST_SEASON}-06-01", missing_date]}
    )
    history = pd.DataFrame({
        "rider_id": ["a", "a"],
        "start_date": [f"{FIRST_SEASON}-01-01", f"{FIRST_SEASON}-05-01"],
        "club_id": ["c1", "c2"],
    })
    with pytest.raises(ValueError, match="Missing race dates in the results"):
        add_value_on_race_date(results, history, "club_id")


def test_missing_start_date_raises():
    results = pd.DataFrame({"rider_id": ["a"], "race_date": [f"{FIRST_SEASON}-06-01"]})
    history = pd.DataFrame({
        "rider_id": ["a", "a"],
        "start_date": [f"{FIRST_SEASON}-01-01", None],
        "club_id": ["c1", "c2"],
    })
    with pytest.raises(ValueError, match="Missing start dates in the history"):
        add_value_on_race_date(results, history, "club_id")


def test_missing_race_date_raises_before_missing_start_date():
    results = pd.DataFrame({"rider_id": ["a"], "race_date": [None]})
    history = pd.DataFrame({
        "rider_id": ["a", "a"],
        "start_date": [f"{FIRST_SEASON}-01-01", None],
        "club_id": ["c1", "c2"],
    })
    with pytest.raises(ValueError, match="Missing race dates in the results"):
        add_value_on_race_date(results, history, "club_id")


@pytest.mark.parametrize("table, column, message", [
    ("results", "race_date", "Missing race dates in the results"),
    ("rider_categories", "start_date", "Missing start dates in the history"),
])
def test_category_on_race_date_missing_date_raises(table, column, message):
    tables = {
        "results": pd.DataFrame({"rider_id": ["a"], "race_date": [f"{FIRST_SEASON}-06-01"]}),
        "rider_categories": pd.DataFrame({
            "rider_id": ["a"],
            "start_date": [f"{FIRST_SEASON}-01-01"],
            "rider_category": pd.array([3], dtype="Int64"),
        }),
    }
    tables[table].loc[0, column] = None
    with pytest.raises(ValueError, match=message):
        add_category_on_race_date(**tables)


def test_category_on_race_date_missing_race_date_raises_before_missing_start_date():
    results = pd.DataFrame({"rider_id": ["a"], "race_date": [None]})
    rider_categories = pd.DataFrame({
        "rider_id": ["a"],
        "start_date": [None],
        "rider_category": pd.array([3], dtype="Int64"),
    })
    with pytest.raises(ValueError, match="Missing race dates in the results"):
        add_category_on_race_date(results, rider_categories)


@pytest.mark.parametrize("table, column, message", [
    ("results", "race_date", "Missing race dates in the results"),
    ("rider_categories", "start_date", "Missing start dates in the history"),
    ("affiliations", "start_date", "Missing start dates in the history"),
])
def test_category_and_club_on_race_date_missing_date_raises(table, column, message):
    tables = {
        "results": pd.DataFrame({"rider_id": ["a"], "race_date": [f"{FIRST_SEASON}-06-01"]}),
        "clubs": pd.DataFrame({"club_id": ["5244001"], "name": ["Club Nantes"]}),
        "affiliations": pd.DataFrame(
            {"rider_id": ["a"], "start_date": [f"{FIRST_SEASON}-01-01"], "club_id": ["5244001"]}
        ),
        "rider_categories": pd.DataFrame({
            "rider_id": ["a"],
            "start_date": [f"{FIRST_SEASON}-01-01"],
            "rider_category": pd.array([3], dtype="Int64"),
        }),
    }
    tables[table].loc[0, column] = None
    with pytest.raises(ValueError, match=message):
        add_category_and_club_on_race_date(**tables)


def test_category_and_club_on_race_date_missing_race_date_raises_before_missing_start_date():
    results = pd.DataFrame({"rider_id": ["a"], "race_date": [None]})
    clubs = pd.DataFrame({"club_id": ["5244001"], "name": ["Club Nantes"]})
    affiliations = pd.DataFrame(
        {"rider_id": ["a"], "start_date": [f"{FIRST_SEASON}-01-01"], "club_id": ["5244001"]}
    )
    rider_categories = pd.DataFrame({
        "rider_id": ["a"],
        "start_date": [None],
        "rider_category": pd.array([3], dtype="Int64"),
    })
    with pytest.raises(ValueError, match="Missing race dates in the results"):
        add_category_and_club_on_race_date(results, clubs, affiliations, rider_categories)


def test_category_and_club_on_the_race_date_with_labels_when_unknown():
    results = pd.DataFrame({
        "race_id": ["r1", "r2", "r3"],
        "rider_id": ["a", "a", "b"],
        "race_date": [f"{FIRST_SEASON}-03-01", f"{FIRST_SEASON}-06-01", f"{FIRST_SEASON}-06-01"],
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


@pytest.mark.parametrize("table, column, message", [
    ("results", "race_date", "Missing race dates in the results"),
    ("rider_categories", "start_date", "Missing start dates in the history"),
])
def test_results_by_categories_missing_date_raises(table, column, message):
    tables = {"results": FILTER_RESULTS.copy(), "rider_categories": FILTER_RIDER_CATEGORIES.copy()}
    tables[table].loc[tables[table].index[0], column] = None
    with pytest.raises(ValueError, match=message):
        filter_results_by_categories(
            tables["results"], tables["rider_categories"], ["A1"], "rider"
        )


def test_results_by_categories_race_filter_does_not_check_the_dates():
    results = FILTER_RESULTS.copy()
    results.loc[results.index[0], "race_date"] = None
    rider_categories = FILTER_RIDER_CATEGORIES.copy()
    rider_categories.loc[0, "start_date"] = None
    kept = filter_results_by_categories(results, rider_categories, ["A3", "A4"], "race")
    assert kept.index.tolist() == [12, 13, 14]


def test_results_by_categories_missing_race_date_raises_before_missing_start_date():
    results = FILTER_RESULTS.copy()
    results.loc[results.index[0], "race_date"] = None
    rider_categories = FILTER_RIDER_CATEGORIES.copy()
    rider_categories.loc[0, "start_date"] = None
    with pytest.raises(ValueError, match="Missing race dates in the results"):
        filter_results_by_categories(results, rider_categories, ["A1"], "rider")


def test_rows_tied_on_every_criterion_share_the_rank():
    df = pd.DataFrame(
        {"nb_wins": [3, 2, 2, 2, 1], "nb_top_3": [1, 5, 5, 4, 0], "name": list("vwxyz")},
        index=[7, 3, 9, 1, 5]
    )
    ranked = add_shared_rank(df, ["nb_wins", "nb_top_3"])
    assert ranked.columns.tolist() == ["nb_wins", "nb_top_3", "name", "rank"]
    assert ranked.index.tolist() == [7, 3, 9, 1, 5]
    assert ranked["rank"].tolist() == [1, 2, 2, 4, 5]


def test_results_from_the_most_recent_with_category_and_club_on_the_race_date():
    season = FIRST_SEASON + 1
    races = pd.DataFrame({
        "race_id": ["r1", "r2"],
        "race_date": [f"{season}-03-01", f"{season}-06-01"],
        "season": [season, season],
        "title": ["r1 title", "r2 title"],
    })
    rankings = pd.DataFrame(
        {"race_id": ["r1", "r2"], "rider_id": ["a", "a"], "finish_rank": [4, 1]}
    )
    clubs = pd.DataFrame(
        {"club_id": ["5244001", "5385001"], "name": ["Club Nantes", "Club Vannes"]}
    )
    affiliations = pd.DataFrame({
        "rider_id": ["a", "a"],
        "start_date": [f"{season}-01-01", f"{season}-05-01"],
        "club_id": ["5244001", "5385001"],
    })
    rider_categories = pd.DataFrame({
        "rider_id": ["a", "a"],
        "start_date": [f"{season}-01-01", f"{season}-05-01"],
        "rider_category": pd.array([3, 2], dtype="Int64"),
    })
    results = get_rider_results(
        races, rankings, clubs, affiliations, rider_categories, "a", f"{season}-10-01"
    )
    assert results.columns.tolist() == RIDER_RESULT_COLUMNS
    assert results["category"].dtype == "str"
    assert results[["race_id", "finish_rank", "category", "club"]].values.tolist() == [
        ["r2", 1, "A2", "Club Vannes"], ["r1", 4, "A3", "Club Nantes"]
    ]


def test_results_keep_the_seasons_covered_before_the_reference_date():
    season = FIRST_SEASON + 1
    reference_date = f"{season}-10-01"
    races = pd.DataFrame({
        "race_id": ["r0", "r1", "r2"],
        "race_date": [f"{FIRST_SEASON - 1}-06-01", f"{season}-09-30", reference_date],
        "season": [FIRST_SEASON - 1, season, season],
        "title": ["r0 title", "r1 title", "r2 title"],
    })
    rankings = pd.DataFrame(
        {"race_id": ["r0", "r1", "r2"], "rider_id": ["a"] * 3, "finish_rank": [1, 1, 1]}
    )
    clubs = pd.DataFrame({"club_id": ["5244001"], "name": ["Club Nantes"]})
    affiliations = pd.DataFrame(
        {"rider_id": ["a"], "start_date": [f"{FIRST_SEASON - 1}-01-01"], "club_id": ["5244001"]}
    )
    rider_categories = pd.DataFrame({
        "rider_id": ["a"],
        "start_date": [f"{FIRST_SEASON - 1}-01-01"],
        "rider_category": pd.array([1], dtype="Int64"),
    })
    results = get_rider_results(
        races, rankings, clubs, affiliations, rider_categories, "a", reference_date
    )
    assert results["race_id"].tolist() == ["r1"]


def test_results_of_the_same_day_keep_the_best_place_first():
    season = FIRST_SEASON + 1
    races = pd.DataFrame({
        "race_id": ["r1", "r2"],
        "race_date": [f"{season}-06-01", f"{season}-06-01"],
        "season": [season, season],
        "title": ["r1 title", "r2 title"],
    })
    rankings = pd.DataFrame(
        {"race_id": ["r1", "r2"], "rider_id": ["a", "a"], "finish_rank": [5, 2]}
    )
    clubs = pd.DataFrame({"club_id": ["5244001"], "name": ["Club Nantes"]})
    affiliations = pd.DataFrame(
        {"rider_id": ["a"], "start_date": [f"{season}-01-01"], "club_id": ["5244001"]}
    )
    rider_categories = pd.DataFrame({
        "rider_id": ["a"],
        "start_date": [f"{season}-01-01"],
        "rider_category": pd.array([3], dtype="Int64"),
    })
    results = get_rider_results(
        races, rankings, clubs, affiliations, rider_categories, "a", f"{season}-10-01"
    )
    assert results["race_id"].tolist() == ["r2", "r1"]


def test_results_with_unknown_category_and_club():
    season = FIRST_SEASON + 1
    races = pd.DataFrame({
        "race_id": ["r1"],
        "race_date": [f"{season}-03-01"],
        "season": [season],
        "title": ["r1 title"],
    })
    rankings = pd.DataFrame({"race_id": ["r1"], "rider_id": ["a"], "finish_rank": [1]})
    clubs = pd.DataFrame({"club_id": ["5244001"], "name": ["Club Nantes"]})
    affiliations = pd.DataFrame(
        {"rider_id": ["a"], "start_date": [f"{season}-06-01"], "club_id": ["5244001"]}
    )
    rider_categories = pd.DataFrame({
        "rider_id": ["a"],
        "start_date": [f"{season}-01-01"],
        "rider_category": pd.array([None], dtype="Int64"),
    })
    results = get_rider_results(
        races, rankings, clubs, affiliations, rider_categories, "a", f"{season}-10-01"
    )
    assert results[["category", "club"]].values.tolist() == [[UNKNOWN_CATEGORY, UNKNOWN_CLUB]]


@pytest.mark.parametrize("table, column, message", [
    ("races", "race_date", "Missing race dates in the results"),
    ("rider_categories", "start_date", "Missing start dates in the history"),
    ("affiliations", "start_date", "Missing start dates in the history"),
])
def test_rider_results_missing_date_raises(table, column, message):
    season = FIRST_SEASON + 1
    tables = {
        "races": pd.DataFrame({
            "race_id": ["r1"], "race_date": [f"{season}-03-01"], "season": [season],
            "title": ["r1 title"],
        }),
        "rankings": pd.DataFrame({"race_id": ["r1"], "rider_id": ["a"], "finish_rank": [1]}),
        "clubs": pd.DataFrame({"club_id": ["5244001"], "name": ["Club Nantes"]}),
        "affiliations": pd.DataFrame(
            {"rider_id": ["a"], "start_date": [f"{season}-01-01"], "club_id": ["5244001"]}
        ),
        "rider_categories": pd.DataFrame({
            "rider_id": ["a"],
            "start_date": [f"{season}-01-01"],
            "rider_category": pd.array([3], dtype="Int64"),
        }),
    }
    tables[table].loc[0, column] = None
    with pytest.raises(ValueError, match=message):
        get_rider_results(**tables, rider_id="a", reference_date=f"{season}-10-01")


def test_rider_results_missing_race_date_raises_before_missing_start_date():
    season = FIRST_SEASON + 1
    races = pd.DataFrame(
        {"race_id": ["r1"], "race_date": [None], "season": [season], "title": ["r1 title"]}
    )
    rankings = pd.DataFrame({"race_id": ["r1"], "rider_id": ["a"], "finish_rank": [1]})
    clubs = pd.DataFrame({"club_id": ["5244001"], "name": ["Club Nantes"]})
    affiliations = pd.DataFrame(
        {"rider_id": ["a"], "start_date": [f"{season}-01-01"], "club_id": ["5244001"]}
    )
    rider_categories = pd.DataFrame({
        "rider_id": ["a"],
        "start_date": [None],
        "rider_category": pd.array([3], dtype="Int64"),
    })
    with pytest.raises(ValueError, match="Missing race dates in the results"):
        get_rider_results(
            races, rankings, clubs, affiliations, rider_categories, "a", f"{season}-10-01"
        )
