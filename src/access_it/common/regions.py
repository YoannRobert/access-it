"""Names of the regional committees covered by the project, as in regional_committees."""

BRETAGNE = "BRETAGNE"
PAYS_DE_LA_LOIRE = "PAYS DE LA LOIRE"

COVERED_REGIONS = (BRETAGNE, PAYS_DE_LA_LOIRE)


def check_covered_region(region: str) -> None:
    """Check that the region is covered.

    Raises:
        ValueError: If the region is not one of COVERED_REGIONS.
    """
    if region not in COVERED_REGIONS:
        raise ValueError(f"Region not covered: {region!r} (expected one of {COVERED_REGIONS})")
