"""Unit tests of the identification of the riders of the startlists."""

import pandas as pd
import pytest

from access_it.etl.transform.startlists import identify_riders_on_startlist

RIDERS = pd.DataFrame({
    "rider_id": ["exact", "red", "long"],
    "uci_id": ["10012345656", "Liste Rouge", "10012345757"],
    "last_name": ["DUPONT", "BLOT", "PERGELINE"],
    "first_name": ["Jean", "J.", "XAVIER"],
})
AFFILIATIONS = pd.DataFrame({
    "rider_id": ["exact", "red", "long"],
    "start_date": pd.to_datetime(["2025-01-01"] * 3),
    "club_id": ["A", "A", "A"],
})


@pytest.mark.parametrize("full_name, club_id, rider_id, method", [
    ("DUPONT Jean", "A", "exact", "exact"),
    ("BLOT Jean", "A", "red", "red list"),
    ("PERGELINE XAVIE", "A", "long", "broader"),
    ("DUPONT Jean", "B", None, None),
    ("MARTIN Paul", "A", None, None),
])
def test_match_method_gives_the_search_that_identified_the_rider(
        full_name, club_id, rider_id, method
):
    startlist = pd.DataFrame({"full_name": [full_name], "club_id": [club_id]})
    out = identify_riders_on_startlist(
        startlist, RIDERS, AFFILIATIONS, on_date=pd.Timestamp("2025-06-01")
    )
    assert out["rider_id"].iloc[0] == rider_id
    assert out["match_method"].iloc[0] == method


INDIVIDUAL_RIDERS = pd.DataFrame({
    "rider_id": ["indiv", "club"],
    "uci_id": ["10012345858", "10012345959"],
    "last_name": ["MARTIN", "DURAND"],
    "first_name": ["Paul", "Luc"],
})
INDIVIDUAL_AFFILIATIONS = pd.DataFrame({
    "rider_id": ["indiv", "club"],
    "start_date": pd.to_datetime(["2025-01-01"] * 2),
    "club_id": ["5244800", "A"],
})


@pytest.mark.parametrize("search_individuals, rider_id", [(False, None), (True, "indiv")])
def test_individual_searched_among_the_pseudo_clubs_of_individuals(search_individuals, rider_id):
    startlist = pd.DataFrame({"full_name": ["MARTIN Paul"], "club_id": ["9899001"]})
    out = identify_riders_on_startlist(
        startlist, INDIVIDUAL_RIDERS, INDIVIDUAL_AFFILIATIONS,
        on_date=pd.Timestamp("2025-06-01"), search_individuals=search_individuals
    )
    assert out["rider_id"].iloc[0] == rider_id


def test_rider_of_a_club_unchanged_when_searching_individuals():
    startlist = pd.DataFrame({"full_name": ["DURAND Luc", "DURAND Luc"], "club_id": ["A", "B"]})
    out = identify_riders_on_startlist(
        startlist, INDIVIDUAL_RIDERS, INDIVIDUAL_AFFILIATIONS,
        on_date=pd.Timestamp("2025-06-01"), search_individuals=True
    )
    assert out["rider_id"].iloc[0] == "club"
    assert pd.isna(out["rider_id"].iloc[1])
