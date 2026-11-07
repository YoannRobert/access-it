"""Rider page of the dashboard."""

import streamlit as st

from computations import get_rider_list, get_rider_profile, search_riders
from data import load_snapshot
from settings import LAST_RACES, TOP_N, WINDOW_MONTHS
from translations import (
    build_column_config, format_departement, REGION_LABELS,
    translate_values, VALUE_LABELS
)

FILTER_KEYS = ("rider_first_name", "rider_departement_code", "rider_club_id")


def apply_name() -> None:
    """Start a new search with the typed name."""
    st.session_state["rider_applied_name"] = st.session_state["rider_name_input"].strip()
    for key in FILTER_KEYS:
        st.session_state[key] = None
    st.session_state["rider_regions"] = []


def reset_departement_and_club() -> None:
    st.session_state["rider_departement_code"] = None
    st.session_state["rider_club_id"] = None


def reset_club() -> None:
    st.session_state["rider_club_id"] = None


snapshot_path, _ = load_snapshot()
for key in ("rider_applied_name", *FILTER_KEYS):
    st.session_state.setdefault(key, None)
st.session_state.setdefault("rider_regions", [])

st.title("Coureur")

col_last_name, col_filter = st.columns([3, 1], vertical_alignment="bottom")
col_first_name, col_regions, col_departement, col_club = st.columns(4)

last_name = col_last_name.text_input(
    label="Nom",
    key="rider_name_input",
    placeholder="Validez avec Entrée puis cliquez sur Filtrer"
)
col_filter.button(label="Filtrer", on_click=apply_name, disabled=not last_name.strip())

riders, choices = search_riders(
    snapshot_path,
    last_name=st.session_state["rider_applied_name"],
    first_name=st.session_state["rider_first_name"],
    regions=tuple(st.session_state["rider_regions"]),
    departement_code=st.session_state["rider_departement_code"],
    club_id=st.session_state["rider_club_id"],
)

col_first_name.selectbox(
    label="Prénom",
    options=[None] if st.session_state["rider_applied_name"] is None else [None, *choices.first_names],
    format_func=lambda first_name: "Tous" if first_name is None else first_name,
    key="rider_first_name",
    disabled=st.session_state["rider_applied_name"] is None
)

st.session_state["rider_regions"] = [
    region for region in st.session_state["rider_regions"] if region in choices.regions
]
col_regions.multiselect(
    label="Régions",
    options=choices.regions,
    format_func=REGION_LABELS.get,
    key="rider_regions",
    on_change=reset_departement_and_club
)

departement_labels = {
    code: format_departement(code, name)
    for code, name in zip(
        choices.departements["departement_code"],
        choices.departements["departement_name"]
    )
}
col_departement.selectbox(
    label="Département",
    options=[None, *choices.departements["departement_code"]],
    format_func=lambda code: "Tous" if code is None else departement_labels[code],
    key="rider_departement_code",
    on_change=reset_club
)

club_labels = dict(zip(choices.clubs["club_id"], choices.clubs["club"]))
col_club.selectbox(
    label="Club",
    options=[None] if st.session_state["rider_departement_code"] is None else [None, *choices.clubs["club_id"]],
    format_func=lambda i: "Tous" if i is None else club_labels[i],
    key="rider_club_id",
    disabled=st.session_state["rider_departement_code"] is None,
)

kept_columns = ["last_name", "first_name", "category", "club", "departement", "rider_id"]
if riders.empty:
    st.info("Aucun coureur pour ces critères.")
else:
    n = len(riders)
    if n > 20:
        st.caption(f"{n} coureurs trouvés, seuls les 20 premiers sont affichés.")
    table = (
        riders
        .head(20)
        .assign(
            departement=lambda df: [
                format_departement(code, name)
                for code, name in zip(df["departement_code"], df["departement_name"])
            ]
        )
        [kept_columns]
    )
    event = st.dataframe(
        translate_values(table),
        column_config=build_column_config(table),
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
    )

    rows = event.selection.rows
    if rows:
        st.query_params["rider_id"] = table.iloc[rows[0]]["rider_id"]

rider_id = st.query_params.get("rider_id")
rider_list = get_rider_list(snapshot_path)
rider_rows = rider_list[rider_list["rider_id"] == rider_id]
if rider_id is None:
    st.info("Cliquez sur un coureur du tableau pour afficher sa fiche.")
elif rider_rows.empty:
    st.error("Coureur introuvable.")
else:
    rider = rider_rows.iloc[0]
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
                height=740
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
            )
        st.markdown("**Points**")
        if rider_profile.season_points.empty:
            st.info("Aucun historique de points pour ce coureur.")
        else:
            st.dataframe(
                translate_values(rider_profile.season_points),
                column_config=build_column_config(rider_profile.season_points),
                hide_index=True,
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
                )
