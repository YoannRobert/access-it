"""Unit tests of the regions covered by the project."""

import pandas as pd
import pytest

from access_it.common.regions import (
    BRETAGNE, COVERED_REGIONS, PAYS_DE_LA_LOIRE, check_covered_region,
    get_region_departement_codes, get_regional_committee_id
)


def test_the_covered_regions_are_bretagne_and_pays_de_la_loire():
    assert COVERED_REGIONS == (BRETAGNE, PAYS_DE_LA_LOIRE)


def test_a_region_not_covered_is_rejected():
    for region in COVERED_REGIONS:
        check_covered_region(region)
    with pytest.raises(ValueError, match="Region not covered"):
        check_covered_region("NORMANDIE")


def test_regional_committee_id_of_a_known_region_and_raises_otherwise():
    regional_committees = pd.DataFrame({
        "regional_committee_id": ["52", "53"], "name": [PAYS_DE_LA_LOIRE, BRETAGNE]
    })
    assert get_regional_committee_id(regional_committees, BRETAGNE) == "53"
    with pytest.raises(ValueError, match="Unknown region"):
        get_regional_committee_id(regional_committees[:1], BRETAGNE)


def test_departements_of_a_region_without_duplicates_and_sorted():
    departemental_committees = pd.DataFrame({
        "regional_committee_id": ["52", "53", "52", "52"],
        "departement_code": ["85", "56", "44", "85"],
    })
    codes = get_region_departement_codes(departemental_committees, "52")
    assert codes.tolist() == ["44", "85"]
    assert codes.index.tolist() == [0, 1]
