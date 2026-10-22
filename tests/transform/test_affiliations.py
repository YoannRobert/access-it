"""Unit tests of the computation of the affiliation periods."""

import logging
import pandas as pd
import pytest

from access_it.etl.transform.riders import (
    AffiliationLookup, compute_affiliation_periods, compute_rider_affiliation_periods,
    get_rider_id_using_affiliations
)


def observations(*rows: tuple[str, str]) -> list[tuple]:
    """Observations (race_date, club_id) from (date string, club) pairs."""
    return [(pd.Timestamp(race_date), club_id) for race_date, club_id in rows]


def periods(*rows: tuple[str, str]) -> list[dict]:
    """Expected periods from (start date string, club) pairs."""
    return [{"start_date": pd.Timestamp(start), "club_id": club} for start, club in rows]


def compute(*rows: tuple[str, str]) -> list[dict]:
    return compute_rider_affiliation_periods(observations(*rows))[0]


def test_single_club_starts_on_january_1st_and_is_ongoing():
    assert compute(("2024-04-07", "A"), ("2025-06-01", "A")) == periods(("2024-01-01", "A"))


def test_change_of_club_between_two_years():
    assert compute(("2024-04-07", "A"), ("2025-03-02", "B")) == periods(
        ("2024-01-01", "A"), ("2025-01-01", "B")
    )


def test_change_of_club_during_the_year():
    assert compute(("2024-04-07", "A"), ("2024-08-05", "B"), ("2024-09-01", "B")) == periods(
        ("2024-01-01", "A"), ("2024-08-05", "B")
    )


def test_years_without_results_are_covered_by_the_previous_club():
    # A in N, nothing in N+1, B in N+2 then C from August 5th of N+2
    assert compute(
        ("2023-05-01", "A"), ("2025-03-01", "B"), ("2025-08-05", "C")
    ) == periods(("2023-01-01", "A"), ("2025-01-01", "B"), ("2025-08-05", "C"))


def test_return_to_a_former_club_gives_separate_periods_without_overlap():
    assert compute(("2023-05-01", "A"), ("2024-05-01", "B"), ("2025-05-01", "A")) == periods(
        ("2023-01-01", "A"), ("2024-01-01", "B"), ("2025-01-01", "A")
    )


def test_isolated_observation_within_the_year_is_ignored():
    rows = [("2023-05-21", "A"), ("2023-05-28", "X"), ("2023-06-09", "A")]
    result, n_ignored = compute_rider_affiliation_periods(observations(*rows))
    assert result == periods(("2023-01-01", "A"))
    assert n_ignored == 1


def test_two_isolated_results_within_the_year_are_ignored():
    rows = [("2023-03-01", "A"), ("2023-04-01", "X"), ("2023-05-01", "X"), ("2023-06-01", "A")]
    assert compute(*rows) == periods(("2023-01-01", "A"))


def test_three_results_with_another_club_are_kept():
    rows = [
        ("2023-03-01", "A"), ("2023-04-01", "X"), ("2023-05-01", "X"), ("2023-05-15", "X"),
        ("2023-06-01", "A"),
    ]
    assert compute(*rows) == periods(("2023-01-01", "A"), ("2023-04-01", "X"), ("2023-06-01", "A"))


def test_short_stay_over_a_whole_season_is_kept():
    # Real case: another club for the whole 2025 season, between 2024 and 2026
    rows = [("2024-09-22", "A"), ("2025-03-22", "X"), ("2025-06-04", "X"), ("2026-06-17", "A")]
    assert compute(*rows) == periods(("2024-01-01", "A"), ("2025-01-01", "X"), ("2026-01-01", "A"))


def test_pseudo_clubs_are_treated_as_clubs():
    individual = "9899001"
    assert compute(("2024-04-07", "A"), ("2025-04-07", individual)) == periods(
        ("2024-01-01", "A"), ("2025-01-01", individual)
    )


def test_same_day_results_with_two_clubs_keep_the_latest():
    assert compute(("2024-04-07", "A"), ("2024-06-01", "B"), ("2024-06-01", "C")) == periods(
        ("2024-01-01", "A"), ("2024-06-01", "C")
    )


def test_compute_affiliation_periods_for_several_riders(caplog):
    caplog.set_level(logging.INFO)
    df = pd.DataFrame({
        "rider_id": ["r2", "r1", "r1", "r1", "r2"],
        "race_id": ["x1", "x2", "x3", "x4", "x5"],
        "race_date": pd.to_datetime(
            ["2025-03-01", "2023-05-28", "2023-05-21", "2023-06-09", "2024-03-01"]
        ),
        "club_id": ["B", "X", "A", "A", "A"],
    })
    result = compute_affiliation_periods(df)
    assert result.to_dict(orient="records") == [
        {"rider_id": "r1", "start_date": pd.Timestamp("2023-01-01"), "club_id": "A"},
        {"rider_id": "r2", "start_date": pd.Timestamp("2024-01-01"), "club_id": "A"},
        {"rider_id": "r2", "start_date": pd.Timestamp("2025-01-01"), "club_id": "B"},
    ]
    assert "1 isolated club observation(s) of 1 rider(s) ignored" in caplog.text


# ---------------------------------------------------------------- AffiliationLookup

# r1: club A in 2024, club B from 2025-06-01 (ongoing); r2: club A from 2025 (ongoing)
AFFILIATIONS = pd.DataFrame({
    "rider_id": ["r1", "r1", "r2"],
    "start_date": pd.to_datetime(["2024-01-01", "2025-06-01", "2025-01-01"]),
    "club_id": ["A", "B", "A"],
})


def test_riders_of_club_on_a_date():
    lookup = AffiliationLookup(AFFILIATIONS)
    assert lookup.riders_of_club("A", pd.Timestamp("2025-05-31")) == {"r1", "r2"}
    assert lookup.riders_of_club("A", pd.Timestamp("2025-06-01")) == {"r2"}
    assert lookup.riders_of_club("B", pd.Timestamp("2030-01-01")) == {"r1"}


def test_first_period_also_covers_the_dates_before_its_start():
    lookup = AffiliationLookup(AFFILIATIONS)
    # r2 is first seen with club A in 2025: before that, nothing contradicts club A
    assert lookup.riders_of_club("A", pd.Timestamp("2024-05-01")) == {"r1", "r2"}
    assert lookup.riders_of_club("A", pd.Timestamp("2023-12-31")) == {"r1", "r2"}
    # A later period does not: r1 was in club A before joining club B
    assert lookup.riders_of_club("B", pd.Timestamp("2025-05-31")) == set()


def test_riders_of_club_without_date():
    lookup = AffiliationLookup(AFFILIATIONS)
    assert lookup.riders_of_club("A") == {"r1", "r2"}
    assert lookup.riders_of_club("C") == set()


def test_former_club_no_longer_identifies_a_rider():
    on_date = pd.Timestamp("2025-08-01")
    with pytest.raises(ValueError, match="No rider ID found"):
        get_rider_id_using_affiliations(["r1"], AFFILIATIONS, "A", on_date)
    assert get_rider_id_using_affiliations(["r1"], AFFILIATIONS, "B", on_date) == "r1"


def test_homonyms_are_separated_by_the_club_at_the_race_date():
    # Before June 2025, both riders are in club A: ambiguous; after, only r2 is
    with pytest.raises(ValueError, match="Multiple rider IDs"):
        get_rider_id_using_affiliations(["r1", "r2"], AFFILIATIONS, "A", pd.Timestamp("2025-03-01"))
    assert get_rider_id_using_affiliations(
        ["r1", "r2"], AFFILIATIONS, "A", pd.Timestamp("2025-08-01")
    ) == "r2"
    with pytest.raises(ValueError, match="Multiple rider IDs"):
        get_rider_id_using_affiliations(["r1", "r2"], AFFILIATIONS, "A")


# ---------------------------------------------------------------- create_affiliation_clubs_riders

def test_results_without_identified_club_are_ignored_for_affiliations(caplog):
    caplog.set_level(logging.INFO)
    from access_it.etl.transform.riders import create_affiliation_clubs_riders

    rider_x_race = pd.DataFrame({
        "rider_id": ["id1"] * 3,
        "club_id": ["A", None, "A"], "race_id": ["r1", "r2", "r3"],
        "race_date": ["2025-03-01", "2025-04-01", "2025-05-01"],
    })
    races = rider_x_race[["race_id", "race_date"]]
    result = create_affiliation_clubs_riders(rider_x_race, races)
    assert result.to_dict(orient="records") == [
        {"rider_id": "id1", "start_date": pd.Timestamp("2025-01-01"), "club_id": "A"}
    ]
    assert "1 result(s) without identified club ignored" in caplog.text
