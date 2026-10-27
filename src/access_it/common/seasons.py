"""Seasons covered by the project."""

# The Access categories (Access 1 to 4) were created in 2023: before, these
# categories had another name, and the result pages cannot be parsed.
ACCESS_CATEGORIES_FIRST_SEASON = 2023

FIRST_SEASON = 2023  # first season covered; never before ACCESS_CATEGORIES_FIRST_SEASON

# First season of the result pages of the other regions (outside Bretagne and
# Pays de la Loire), only read to find the committee of the individual
# licensees: before 2026, the result pages give the committee in their club ID.
NATIONAL_FIRST_SEASON = 2026


def check_first_season(first_season: int) -> None:
    """Check that the first season is not before the creation of the Access categories.

    Raises:
        ValueError: If `first_season` is before ACCESS_CATEGORIES_FIRST_SEASON.
    """
    if first_season < ACCESS_CATEGORIES_FIRST_SEASON:
        raise ValueError(
            f"FIRST_SEASON ({first_season}) must not be before "
            f"{ACCESS_CATEGORIES_FIRST_SEASON}, the creation of the Access categories"
        )


check_first_season(FIRST_SEASON)  # stops any run of the ETL if the constant is wrong
