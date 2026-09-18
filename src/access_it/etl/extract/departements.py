import httpx
import pandas as pd

from bs4 import BeautifulSoup


def get_departement_mapping(client: httpx.Client) -> pd.DataFrame:
    response = client.get("https://competitions.ffc.fr/resultats/")
    response.raise_for_status()

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

    return pd.DataFrame(departements)
