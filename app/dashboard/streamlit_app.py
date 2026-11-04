"""Entry point of the Access it! dashboard (minimal page to test the Docker image)."""

from importlib.metadata import version

import streamlit as st

st.set_page_config(page_title="Access it!")

st.title("Access it!")
st.write("Tableau de bord en cours de construction.")
st.caption(f"access-it {version('access-it')} · Streamlit {st.__version__}")
