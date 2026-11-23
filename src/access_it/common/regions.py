"""Regional committees covered by the project.

Names of the regional committees, as in regional_committees, list of the
covered regions, check that a requested region is one of them, ID of a
regional committee and departements of a region.
"""

import pandas as pd

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


def get_regional_committee_id(regional_committees: pd.DataFrame, region: str) -> str:
    """ID of the regional committee named `region` (name as in regional_committees).

    Args:
        regional_committees: Regional committee table.
        region: Name of the regional committee.

    Returns:
        The regional_committee_id of the committee.

    Raises:
        ValueError: If the region is unknown.
    """
    is_region = regional_committees["name"] == region
    if not is_region.any():
        raise ValueError(f"Unknown region: {region!r}")
    return regional_committees.loc[is_region, "regional_committee_id"].iloc[0]


def get_region_departement_codes(
        departemental_committees: pd.DataFrame,
        region_id: str
    ) -> pd.Series:
    """Codes of the departements of a region: those of its departemental committees.

    Args:
        departemental_committees: Departemental committee table.
        region_id: ID of the regional committee (see get_regional_committee_id).

    Returns:
        The departement_code of these committees, without duplicates, sorted,
        with the index reset.
    """
    return (
        departemental_committees.loc[
            departemental_committees["regional_committee_id"] == region_id, "departement_code"
        ]
        .drop_duplicates().sort_values().reset_index(drop=True)
    )
