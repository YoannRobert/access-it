"""Regional committees covered by the project.

Names of the regional committees, as in regional_committees, list of the
covered regions, and check that a requested region is one of them.
"""

BRETAGNE = "BRETAGNE"
PAYS_DE_LA_LOIRE = "PAYS DE LA LOIRE"

COVERED_REGIONS = (BRETAGNE, PAYS_DE_LA_LOIRE)


def check_covered_region(region: str) -> None:
    """Check that the region is covered.

    Args:
        region: Name of the regional committee, as in regional_committees.

    Raises:
        ValueError: If the region is not one of COVERED_REGIONS.
    """
    if region not in COVERED_REGIONS:
        raise ValueError(f"Region not covered: {region!r} (expected one of {COVERED_REGIONS})")
