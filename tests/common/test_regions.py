"""Unit tests of the regions covered by the project."""

import pytest

from access_it.common.regions import (
    BRETAGNE, COVERED_REGIONS, PAYS_DE_LA_LOIRE, check_covered_region
)


def test_the_covered_regions_are_bretagne_and_pays_de_la_loire():
    assert COVERED_REGIONS == (BRETAGNE, PAYS_DE_LA_LOIRE)


def test_a_region_not_covered_is_rejected():
    for region in COVERED_REGIONS:
        check_covered_region(region)
    with pytest.raises(ValueError, match="Region not covered"):
        check_covered_region("NORMANDIE")
