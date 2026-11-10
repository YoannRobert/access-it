"""Rankings page of the dashboard.

Regional challenge, promotion points and clubs of a season.
"""

import streamlit as st

from access_it.analytics.promotion_points import get_promotion_ranking
from access_it.analytics.ranking_tools import CATEGORIES
from access_it.analytics.regional_rankings import get_category_ranking
from access_it.common.regions import PAYS_DE_LA_LOIRE

from computations import get_club_rankings, get_promotion_rankings, get_regional_rankings
from data import get_snapshot_reference_date, load_snapshot
from filters import select_category_filter, select_categories, select_max_count, select_region, select_season
from navigation import navigable_dataframe
from tables import table_height
from translations import build_column_config, translate_values


st.title("Classements")

snapshot_path, tables = load_snapshot()
reference_date = get_snapshot_reference_date(snapshot_path)
default_season = reference_date.year

col_season, col_region = st.columns(2)

season = select_season(col_season, default_season)
region = select_region(col_region)

tab_challenge, tab_promotion, tab_clubs = st.tabs(["Challenge régional", "Points de montée", "Clubs"])

with tab_challenge:
    if region != PAYS_DE_LA_LOIRE:
        st.info("Le challenge régional n'existe que pour les Pays de la Loire.")
    else:
        category = st.radio(label="Catégorie", options=CATEGORIES, horizontal=True, key="challenge_category")
        df = get_category_ranking(get_regional_rankings(snapshot_path, season, region), str(category))
        if df.empty:
            st.info("Aucun classement régional pour ces critères.")
        else:
            key = f"ranking_challenge_{season}_{category}"
            navigable_dataframe(df, id_column="rider_id", key=key)

with tab_promotion:
    category = st.radio(label="Catégorie", options=CATEGORIES, horizontal=True, key="promotion_category")
    df = get_promotion_ranking(
        get_promotion_rankings(snapshot_path, season), str(category),
        region=region, regional_committees=tables["regional_committees"]
    ).drop(columns="region")
    if df.empty:
        st.info("Aucun classement de montée pour ces critères.")
    else:
        key = f"ranking_promotion_{season}_{region}_{category}"
        navigable_dataframe(df, id_column="rider_id", key=key)

with tab_clubs:
    col_categories, col_filter, col_max_clubs = st.columns(3)
    categories = select_categories(col_categories, "Catégories")
    category_filter = select_category_filter(col_filter)
    max_clubs = select_max_count(
        col_max_clubs, "Nombre de clubs",
        min_value=10, max_value=100, value=30, step=10
    )
    df = get_club_rankings(
        snapshot_path=snapshot_path, season=season, region=region,
        categories=categories, category_filter=category_filter, max_clubs=max_clubs
    )
    if df.empty:
        st.info("Aucun classement de clubs pour ces critères.")
    else:
        st.dataframe(
            translate_values(df),
            column_config=build_column_config(df),
            hide_index=True,
            height=table_height(df)
        )
