"""Entry point of the Access it! dashboard: configuration, navigation between the pages and sidebar."""

import pandas as pd
import streamlit as st

from access_it.common.log import setup_logging

from data import get_snapshot_reference_date, load_snapshot


@st.cache_resource
def configure_logging() -> None:
    """Configure the logs once per process (see setup_logging)."""
    setup_logging()


configure_logging()

st.set_page_config(page_title="Access it!")

about_page = st.Page("views/about.py", title="À propos", url_path="about")
pages = [
    st.Page("views/home.py", title="Accueil", url_path="home", default=True),
    st.Page("views/season.py", title="Saison", url_path="season"),
    st.Page("views/rankings.py", title="Classements", url_path="rankings"),
    st.Page("views/rider.py", title="Coureur", url_path="rider"),
    st.Page("views/head_to_head.py", title="Confrontations", url_path="head-to-head"),
    st.Page("views/race.py", title="Course", url_path="race"),
    about_page,
]
navigation = st.navigation(pages)

snapshot_path, _ = load_snapshot()
last_race_date = get_snapshot_reference_date(snapshot_path) - pd.Timedelta(days=1)
with st.sidebar:
    st.markdown(
        "**Projet personnel d'apprentissage**, sans lien avec la FFC. Les données peuvent être "
        "erronées ou incomplètes : seuls les résultats publiés par la FFC font foi. Les "
        "catégories des coureurs sont déduites par une heuristique imparfaite."
    )
    st.markdown(f"Dernière course enregistrée : {last_race_date:%d/%m/%Y}.")
    st.page_link(about_page, label="À propos")

navigation.run()
