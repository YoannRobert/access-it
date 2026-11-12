"""Race page of the dashboard.

Races of a period, then the header and the ranking of the race of the URL (race_id).
"""

import pandas as pd
import streamlit as st

from datetime import date

from access_it.common.seasons import FIRST_SEASON

from computations import get_race_list, get_race_summary, get_region_departements
from data import get_snapshot_reference_date, load_snapshot
from filters import select_categories, select_region
from navigation import navigable_dataframe, search_expander
from tables import table_height
from translations import build_column_config, format_departement, translate_values

st.title("Course")

with st.expander("Comment lire cette page"):
    st.markdown(
        """
- Choisissez la période, les départements (aucun choix = tous) et les catégories. Cliquez
  ensuite sur une course de la liste.
- Le classement est la place dans la course, toutes catégories confondues.
"""
    )

snapshot_path, tables = load_snapshot()
reference_date = get_snapshot_reference_date(snapshot_path)
year = reference_date.year

race_id = st.query_params.get("race_id")
selected_id = None
with search_expander("Rechercher une course", "race_search", (race_id,)):
    col_region, col_start, col_end = st.columns(3)
    region = select_region(container=col_region)
    with col_start:
        start_date = st.date_input(
            label="Du",
            value=date(year, 1, 1),
            min_value=date(FIRST_SEASON, 1, 1),
            max_value=date(year, 12, 31),
            format="DD/MM/YYYY",
            key="race_start_date",
        )
    with col_end:
        end_date = st.date_input(
            label="Au",
            value=date(year, 12, 31),
            min_value=date(FIRST_SEASON, 1, 1),
            max_value=date(year, 12, 31),
            format="DD/MM/YYYY",
            key="race_end_date",
        )

    col_departements, col_categories = st.columns(2)
    with col_departements:
        departements = get_region_departements(snapshot_path, region)
        labels = {
            code: format_departement(code, name)
            for code, name in zip(
                departements["departement_code"], departements["departement_name"]
            )
        }
        selected_codes = st.multiselect(
            label="Départements",
            options=departements["departement_code"].to_list(),
            format_func=lambda code: labels[code],
            placeholder="Tous",
            key=f"race_departements_{region}",
        )
    categories = select_categories(col_categories, label="Catégories")

    if end_date < start_date:
        st.warning("La date de fin précède la date de début.")
    else:
        races = get_race_list(
            snapshot_path=snapshot_path,
            start_date=start_date,
            end_date=end_date,
            region=region,
            departement_codes=tuple(selected_codes) or None,
            categories=categories
        )
        if races.empty:
            st.info("Aucune course pour ces critères.")
        else:
            n = len(races)
            st.caption(f"{n} course{'s' if n > 1 else ''}.")
            table = races.assign(
                departement=lambda df: [
                    format_departement(code, name)
                    for code, name in zip(df["departement_code"], df["departement_name"])
                ]
            )[["race_date", "title", "categories", "departement", "race_id"]]
            event = st.dataframe(
                translate_values(table),
                column_config=build_column_config(table),
                key=f"race_table_{start_date}_{end_date}_{region}_{tuple(selected_codes)}_{categories}",
                on_select="rerun",
                selection_mode="single-row",
                hide_index=True,
                height=table_height(table)
            )
            rows = event.selection.rows
            if rows:
                selected_id = table.iloc[rows[0]]["race_id"]

if selected_id is not None and selected_id != race_id:
    st.query_params["race_id"] = selected_id
    st.rerun()  # closes the search expander

if race_id is None:
    st.info("Cliquez sur une course de la liste pour afficher sa fiche.")
elif not tables["races"]["race_id"].eq(race_id).any():
    st.error("Course introuvable.")
else:
    summary = get_race_summary(snapshot_path, race_id)
    header = summary.header.iloc[0]
    st.subheader(header["title"])
    col_labels, col_values, col_ranked = st.columns([1, 4, 1], gap="small")
    race_date = pd.Timestamp(header["race_date"]).strftime("%d/%m/%Y")
    race_categories = "-".join(header["categories"].split(","))
    race_departement_code = header["departement_code"]
    race_departement_name = header["departement_name"]
    race_departement = format_departement(race_departement_code, race_departement_name)
    organizer = header["organizer"] if pd.notna(header["organizer"]) else "—"
    col_labels.markdown("**Date**  \n**Catégories**  \n**Département**  \n**Organisateur**")
    col_values.markdown(f"{race_date}  \n{race_categories}  \n{race_departement}  \n{organizer}")
    col_ranked.metric("Classés", len(summary.ranking))
    if summary.ranking.empty:
        st.info("Aucun classé pour cette course.")
    else:
        key = f"race_ranking_{race_id}"
        navigable_dataframe(summary.ranking, id_column="rider_id", key=key)
