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
