"""Departements of France, read from the search form of the FFC result pages."""

import httpx
import pandas as pd

from bs4 import BeautifulSoup

from access_it.etl.extract.client import get_required
from access_it.etl.extract.constants import FOREIGN_CLUB_ID


def get_departement_mapping(client: httpx.Client) -> pd.DataFrame:
    """Read the departements from the search form of the FFC result pages.

    Args:
        client: HTTP client.

    Returns:
        One row per departement (departement_code, departement_name), plus
        the departement 'Autre' of the foreign pseudo-club.

    Raises:
        RuntimeError: If the page cannot be requested.
        ValueError: If the departement selector is not found on the page.
    """
    response = get_required(client, "https://competitions.ffc.fr/resultats/")

    bs = BeautifulSoup(response.text, "html.parser")
    select = bs.find("select", id="filtreDepartementID")
    if select is None:
        raise ValueError("select not found")

    departements = []
    for option in select.find_all("option"):
        value = option.get(key="value", default="")
        if not isinstance(value, str):
            raise TypeError("value is not a string")
        value = value.strip()
        if value == "":
            continue
        text = option.get_text(strip=True)
        _, _, name = text.partition("-")
        departements.append(
            {
                "departement_code": value,
                "departement_name": name.strip(),
            }
        )
    departements.append(
        {
            "departement_code": FOREIGN_CLUB_ID[2:4],
            "departement_name": "Autre",
        }
    )

    return pd.DataFrame(departements)
