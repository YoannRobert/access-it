"""Season page of the dashboard."""

import streamlit as st

from access_it.analytics.ranking_tools import CATEGORIES
from access_it.common.regions import COVERED_REGIONS
from access_it.common.seasons import FIRST_SEASON

from charts import bar_chart
from computations import get_category_changes, get_season_summary
from data import DEFAULT_REGION, get_snapshot_reference_date, load_snapshot
from translations import (
    CATEGORY_FILTER_LABELS, MONTH_LABELS, REGION_LABELS,
    build_column_config, translate_values
)

st.title("Saison")

snapshot_path, _ = load_snapshot()
reference_date = get_snapshot_reference_date(snapshot_path)
default_season = reference_date.year

col_season, col_region, col_categories, col_filter = st.columns(4)
season = col_season.selectbox(
    label="Saison",
    options=range(default_season, FIRST_SEASON - 1, -1)
)
region = col_region.selectbox(
    label="Région",
    options=COVERED_REGIONS,
    index=COVERED_REGIONS.index(DEFAULT_REGION),
    format_func=REGION_LABELS.get
)
first, last = col_categories.select_slider(
    label="Catégories (onglets Courses et Coureurs)",
    options=CATEGORIES,
    value=(CATEGORIES[0], CATEGORIES[-1])
)
categories = CATEGORIES[CATEGORIES.index(first):CATEGORIES.index(last) + 1]
category_filter = col_filter.radio(
    label="Filtre de catégorie appliqué",
    options=["race", "rider"],
    format_func=CATEGORY_FILTER_LABELS.get,
    horizontal=True,
    help='« à la course » pour filtrer sur les catégories des courses, '
         '« au coureur » pour filtrer sur les catégories des coureurs aux dates des courses'
)

tab_races, tab_riders, tab_changes = st.tabs(["Courses", "Coureurs", "Changements de catégorie"])

with tab_riders:
    max_riders = st.slider(
        label="Nombre de coureurs",
        min_value=5, max_value=30, value=10, step=5
    )
summary = get_season_summary(snapshot_path, season, region, categories, category_filter, max_riders)

with tab_races:
    col_total, col_ranked = st.columns(2)
    col_total.metric(
        label="Courses",
        value=int(summary.races_by_month["nb_races"].sum())
    )
    col_ranked.metric(
        label="Coureurs classés",
        value=int(summary.ranked_riders["nb_ranked_riders"].iloc[0])
    )

    races_by_month = summary.races_by_month.copy()
    races_by_month["label"] = races_by_month["month"].map(MONTH_LABELS)
    bar_chart(
        df=races_by_month,
        title="Nombre de courses par mois",
        x_field="label",
        y_field="nb_races",
        xaxis_title="Mois",
        yaxis_title="Nombre de courses",
    )

    races_by_departement = summary.races_by_departement.copy()
    races_by_departement["label"] = (
            races_by_departement["departement_code"] + " - " + races_by_departement["departement_name"]
    ).where(races_by_departement["departement_name"].notna(), races_by_departement["departement_code"])
    bar_chart(
        df=races_by_departement,
        title="Nombre de courses par département",
        x_field="label",
        y_field="nb_races",
        xaxis_title="Département",
        yaxis_title="Nombre de courses",
        xaxis_label_angle=-45
    )

    races_by_categories = summary.races_by_categories.copy()
    races_by_categories["label"] = races_by_categories["categories"]
    bar_chart(
        df=races_by_categories,
        title="Nombre de courses par combinaison de catégories",
        x_field="label",
        y_field="nb_races",
        xaxis_title="Combinaison de catégories",
        yaxis_title="Nombre de courses",
        xaxis_label_angle=-45
    )

with tab_riders:
    df = summary.most_titled_riders
    if df.empty:
        st.info("Aucun coureur classé dans les 20 premiers pour ces critères.")
    else:
        st.dataframe(translate_values(df), column_config=build_column_config(df), hide_index=True)

with tab_changes:
    category = st.selectbox(
        label="Catégorie d'arrivée", options=[None, *CATEGORIES],
        format_func=lambda c: "Toutes" if c is None else c
    )
    df = get_category_changes(snapshot_path, season, region, category)
    if df.empty:
        st.info("Aucun changement de catégorie pour ces critères.")
    else:
        st.dataframe(translate_values(df), column_config=build_column_config(df), hide_index=True, height=740)
