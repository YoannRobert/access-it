"""Unit tests of the seasons covered by the project."""

import pytest

from access_it.common.seasons import (
    ACCESS_CATEGORIES_FIRST_SEASON, FIRST_SEASON, check_first_season, check_season
)


def test_first_season_is_not_before_the_access_categories():
    assert FIRST_SEASON >= ACCESS_CATEGORIES_FIRST_SEASON == 2023


def test_a_first_season_before_the_access_categories_is_rejected():
    with pytest.raises(ValueError, match="creation of the Access categories"):
        check_first_season(2022)
    check_first_season(2023)


def test_a_season_before_the_first_season_is_rejected():
    with pytest.raises(ValueError, match=f"Season {FIRST_SEASON - 1} is before the first season"):
        check_season(FIRST_SEASON - 1)
    check_season(FIRST_SEASON)
