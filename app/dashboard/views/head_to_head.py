"""Head-to-head page of the dashboard.

Search of two riders, then their common races (rider_id and opponent_id of the URL).
"""

import streamlit as st

from access_it.common.seasons import FIRST_SEASON

from computations import get_head_to_head
from data import get_snapshot_reference_date, load_snapshot
from navigation import navigable_dataframe, search_expander
from rider_search import find_rider, select_rider
from translations import build_column_config


st.title("Confrontations")

with st.expander("Comment lire cette page"):
    st.markdown(
        """
- Choisissez un coureur dans chaque onglet.
- Une course commune est une course où les deux coureurs sont classés. Le coureur devant est
  celui qui a la meilleure place. Deux coureurs à la même place sont à égalité.
"""
    )

snapshot_path, _ = load_snapshot()
reference_date = get_snapshot_reference_date(snapshot_path)

rider_id = st.query_params.get("rider_id")
opponent_id = st.query_params.get("opponent_id")
with search_expander("Choisir les coureurs", "h2h_search", (rider_id, opponent_id)):
    tab_rider, tab_opponent = st.tabs(["Coureur", "Adversaire"])
    with tab_rider:
        selected_rider_id = select_rider(snapshot_path, "h2h_rider")
    with tab_opponent:
        selected_opponent_id = select_rider(snapshot_path, "h2h_opponent")

new_ids = {
    name: selected_id
    for name, selected_id, url_id in [
        ("rider_id", selected_rider_id, rider_id),
        ("opponent_id", selected_opponent_id, opponent_id),
    ]
    if selected_id is not None and selected_id != url_id
}
if new_ids:
    st.query_params.update(new_ids)
    st.rerun()  # closes the search expander once both riders are chosen

rider = find_rider(snapshot_path, rider_id)
opponent = find_rider(snapshot_path, opponent_id)
if (
        (rider_id is not None and rider is None)
        or (opponent_id is not None and opponent is None)
):
    st.error("Coureur introuvable.")
elif rider is None or opponent is None:
    st.info("Choisissez un coureur et un adversaire.")
elif rider_id == opponent_id:
    st.info("Choisissez deux coureurs différents.")
else:
    rider_full_name = f"{rider['first_name']} {rider['last_name']}"
    opponent_full_name = f"{opponent['first_name']} {opponent['last_name']}"
    st.subheader(f"{rider_full_name} vs {opponent_full_name}")
    season_options: list[int | None] = [None, *range(reference_date.year, FIRST_SEASON - 1, -1)]
    season = st.selectbox(
        label="Saison",
        options=season_options,
        format_func=lambda year: "Toutes" if year is None else str(year),
        key="h2h_season"
    )
    h2h = get_head_to_head(
        snapshot_path=snapshot_path,
        rider_id=rider["rider_id"],
        opponent_id=opponent["rider_id"],
        season=season
    )

    col_common, col_rider_ahead, col_opponent_ahead, col_ties = st.columns(4)
    if rider["last_name"] == opponent["last_name"]:
        rider_name = rider_full_name
        opponent_name = opponent_full_name
    else:
        rider_name = rider['last_name']
        opponent_name = opponent['last_name']
    with col_common:
        st.metric(
            label="Courses communes",
            value=int(h2h.summary["nb_common_races"].iloc[0])
        )
    with col_rider_ahead:
        st.metric(
            label=f"{rider_name} devant",
            value=int(h2h.summary["nb_rider_ahead"].iloc[0])
        )
    with col_opponent_ahead:
        st.metric(
            label=f"{opponent_name} devant",
            value=int(h2h.summary["nb_opponent_ahead"].iloc[0])
        )
    with col_ties:
        st.metric(
            label="Égalités",
            value=int(h2h.summary["nb_ties"].iloc[0])
        )
    if h2h.races.empty:
        st.info("Aucune course commune pour ces critères.")
    else:
        config = build_column_config(h2h.races)
        config["rider_finish_rank"] = f"Place — {rider_name}"
        config["opponent_finish_rank"] = f"Place — {opponent_name}"
        config["rider_category"] = f"Catégorie — {rider_name}"
        config["opponent_category"] = f"Catégorie — {opponent_name}"
        config["rider_club"] = f"Club — {rider_name}"
        config["opponent_club"] = f"Club — {opponent_name}"
        key = f"h2h_common_{rider_id}_{opponent_id}_{season}"
        navigable_dataframe(h2h.races, id_column="race_id", key=key, column_config=config)
