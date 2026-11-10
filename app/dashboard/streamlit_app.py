"""Entry point of the Access it! dashboard: configuration and navigation between the pages."""

import streamlit as st

from access_it.common.log import setup_logging


@st.cache_resource
def configure_logging() -> None:
    """Configure the logs once per process (see setup_logging)."""
    setup_logging()


configure_logging()

st.set_page_config(page_title="Access it!")

pages = [
    st.Page("views/season.py", title="Saison", url_path="season", default=True),
    st.Page("views/rankings.py", title="Classements", url_path="rankings"),
    st.Page("views/rider.py", title="Coureur", url_path="rider"),
    st.Page("views/head_to_head.py", title="Confrontations", url_path="head-to-head"),
    st.Page("views/race.py", title="Course", url_path="race"),
]
st.navigation(pages).run()
