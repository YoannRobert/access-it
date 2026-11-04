"""Entry point of the Access it! dashboard (minimal page to test the Docker image)."""

import pandas as pd
import streamlit as st

from importlib.metadata import version

from access_it.analytics.ranking_tools import get_reference_date
from data import load_snapshot


st.set_page_config(page_title="Access it!")

st.title("Access it!")
st.write("Tableau de bord en cours de construction.")
st.caption(f"access-it {version('access-it')} · Streamlit {st.__version__}")

snapshot_path, tables = load_snapshot()
st.write(f"Instantané provenant du fichier {snapshot_path.name}")
reference_date = get_reference_date(tables["races"])
st.write(f"Date de référence : {reference_date:%d/%m/%Y}")
nb_rows_per_table = [{"Table": k, "Lignes": v.shape[0]} for k, v in tables.items()]
st.write("Longueur des tables chargées :")
st.table(pd.DataFrame(nb_rows_per_table))
