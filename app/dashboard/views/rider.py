"""Rider page of the dashboard."""

import streamlit as st

from computations import get_rider_profile
from data import load_snapshot
from rider_search import find_rider, select_rider
from settings import LAST_RACES, TOP_N, WINDOW_MONTHS
from tables import table_height
from translations import build_column_config, translate_values, VALUE_LABELS


snapshot_path, _ = load_snapshot()

st.title("Coureur")

rider_id = select_rider(snapshot_path, "rider")
if rider_id is not None:
    st.query_params["rider_id"] = rider_id
rider_id = st.query_params.get("rider_id")
rider = find_rider(snapshot_path, rider_id)
if rider_id is None:
    st.info("Cliquez sur un coureur du tableau pour afficher sa fiche.")
elif rider is None:
    st.error("Coureur introuvable.")
else:
    rider_profile = get_rider_profile(snapshot_path=snapshot_path, rider_id=rider_id)
    category = VALUE_LABELS.get(rider["category"], rider["category"])
    club = VALUE_LABELS.get(rider["club"], rider["club"])
    st.subheader(f"{rider['first_name']} {rider['last_name']}")
    col_labels, col_values = st.columns([1, 5], gap="small")
    col_labels.markdown("**Catégorie**  \n**Club**")
    col_values.markdown(f"{category}  \n{club}")
    st.markdown("**Forme récente**")
    col_nb_races, col_nb_tops, col_top_rate = st.columns(3)
    nb_races_used = int(rider_profile.recent_form["nb_races_used"].iloc[0])
    nb_tops = int(rider_profile.recent_form["nb_top_n"].iloc[0])
    top_rate = rider_profile.recent_form["top_n_rate"].iloc[0] if nb_races_used > 0 else None
    col_nb_races.metric(
        label="Nombre de courses prises en compte",
        value=nb_races_used,
        help=f"{LAST_RACES} dernières courses des {WINDOW_MONTHS} derniers mois avant la date de référence"
    )
    col_nb_tops.metric(
        label=f"Nombre de Top {TOP_N}",
        value=nb_tops,
    )
    col_top_rate.metric(
        label=f"Taux de Top {TOP_N}",
        value=f"{top_rate:.0%}" if nb_races_used > 0 else "—",
    )
    tab_results, tab_seasons, tab_history = st.tabs(["Résultats", "Saisons", "Parcours"])
    with tab_results:
        if rider_profile.results.empty:
            st.info("Aucun résultat pour ce coureur.")
        else:
            st.dataframe(
                translate_values(rider_profile.results),
                column_config=build_column_config(rider_profile.results),
                hide_index=True,
                height=table_height(rider_profile.results)
            )
    with tab_seasons:
        st.markdown("**Statistiques**")
        if rider_profile.season_stats.empty:
            st.info("Aucune statistique pour ce coureur.")
        else:
            st.dataframe(
                translate_values(rider_profile.season_stats),
                column_config=build_column_config(rider_profile.season_stats),
                hide_index=True,
                height=table_height(rider_profile.season_stats)
            )
        st.markdown("**Points**")
        if rider_profile.season_points.empty:
            st.info("Aucun historique de points pour ce coureur.")
        else:
            st.dataframe(
                translate_values(rider_profile.season_points),
                column_config=build_column_config(rider_profile.season_points),
                hide_index=True,
                height=table_height(rider_profile.season_points)
            )
    with tab_history:
        col_categories, col_clubs = st.columns(2)
        with col_categories:
            st.markdown("**Catégories**")
            if rider_profile.categories.empty:
                st.info("Aucun historique de catégories pour ce coureur.")
            else:
                st.dataframe(
                    translate_values(rider_profile.categories),
                    column_config=build_column_config(rider_profile.categories),
                    hide_index=True,
                    height=table_height(rider_profile.categories)
                )
        with col_clubs:
            st.markdown("**Clubs**")
            if rider_profile.clubs.empty:
                st.info("Aucun historique de clubs pour ce coureur.")
            else:
                st.dataframe(
                    translate_values(rider_profile.clubs),
                    column_config=build_column_config(rider_profile.clubs),
                    hide_index=True,
                    height=table_height(rider_profile.clubs)
                )
