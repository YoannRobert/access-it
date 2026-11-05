"""Season page of the dashboard."""

import streamlit as st

from data import DEFAULT_REGION, get_snapshot_reference_date, load_snapshot

st.title("Saison")

snapshot_path, _ = load_snapshot()
reference_date = get_snapshot_reference_date(snapshot_path)
default_season = reference_date.year

st.write(f"Date de référence : {reference_date:%d/%m/%Y}")
st.write(f"Saison par défaut : {default_season}")
st.write(f"Région par défaut : {DEFAULT_REGION}")