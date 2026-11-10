"""French labels of the dashboard: column headers, values of the analytics, months, regions.

The DataFrames keep their English column names; the labels are applied when displaying
(translate_values, build_column_config).
"""

import pandas as pd
import streamlit as st

from typing import Any

from access_it.analytics.labels import (
    DEMOTION, FIRST_APPEARANCE, NOT_APPLICABLE, PROMOTION, UNKNOWN_CATEGORY, UNKNOWN_CLUB
)
from access_it.common.regions import BRETAGNE, PAYS_DE_LA_LOIRE
from settings import TOP_N


COLUMN_LABELS = {
    "rank": "Rang",
    "category": "Catégorie",
    "categories": "Catégories",
    "points": "Points",
    "last_name": "Nom",
    "first_name": "Prénom",
    "club": "Club",
    "region": "Région",
    "nb_scoring_races": "Courses avec points",
    "nb_wins": "Victoires",
    "nb_top_3": "Podium",
    "nb_top_5": "Top 5",
    "nb_top_10": "Top 10",
    "nb_top_20": "Top 20",
    "nb_races": "Courses",
    "nb_active_riders": "Coureurs actifs",
    "nb_ranked_riders": "Coureurs classés",
    "departement": "Département",
    "departement_code": "N° dép.",
    "departement_name": "Département",
    "season": "Saison",
    "race_date": "Date",
    "title": "Course",
    "finish_rank": "Place",
    "month": "Mois",
    "change_date": "Date du changement",
    "change_type": "Type de changement",
    "from_category": "Catégorie de départ",
    "to_category": "Catégorie d'arrivée",
    "start_date": "Début",
    "end_date": "Fin",
    "promotion_points_a1": "Points de montée A1",
    "promotion_points_a2": "Points de montée A2",
    "promotion_points_a3": "Points de montée A3",
    "promotion_points_a4": "Points de montée A4",
    "challenge_points_a1": "Points challenge A1",
    "challenge_points_a2": "Points challenge A2",
    "challenge_points_a3": "Points challenge A3",
    "challenge_points_a4": "Points challenge A4",
    "challenge": "Challenge",
    "nb_races_used": "Courses prises en compte",
    "nb_top_n": f"Top {TOP_N}",
    "top_n_rate": f"Taux de Top {TOP_N}",
    "rider_finish_rank": "Place (coureur)",
    "opponent_finish_rank": "Place (adversaire)",
    "rider_category": "Catégorie (coureur)",
    "opponent_category": "Catégorie (adversaire)",
    "rider_club": "Club (coureur)",
    "opponent_club": "Club (adversaire)",
    "nb_common_races": "Courses communes",
    "nb_rider_ahead": "Devant (coureur)",
    "nb_opponent_ahead": "Devant (adversaire)",
    "nb_ties": "Égalités",
    "discipline": "Discipline",
    "race_type": "Type d'épreuve",
    "organizer": "Organisateur",
    "duration": "Durée",
    "organization_code": "Code d'organisation",
    "race_code": "Code d'épreuve",
    "regional_committee": "Comité régional",
}

COLUMN_HELP = {
    "nb_scoring_races": "Courses où le coureur a marqué des points dans cette catégorie",
    "nb_active_riders": (
        "Coureurs du club classés au moins une fois dans la saison, quelles que soient les "
        "catégories choisies"
    ),
}

VALUE_LABELS = {
    UNKNOWN_CATEGORY: "catégorie inconnue",
    UNKNOWN_CLUB: "club inconnu",
    NOT_APPLICABLE: "non concerné",
    PROMOTION: "montée",
    DEMOTION: "descente",
    FIRST_APPEARANCE: "première apparition",
}

HIDDEN_COLUMNS = ("rider_id", "opponent_id", "club_id", "race_id")

MONTH_LABELS = {
    1: "janv.", 2: "févr.", 3: "mars", 4: "avr.", 5: "mai", 6: "juin",
    7: "juil.", 8: "août", 9: "sept.", 10: "oct.", 11: "nov.", 12: "déc.",
}
REGION_LABELS = {BRETAGNE: "Bretagne", PAYS_DE_LA_LOIRE: "Pays de la Loire"}
CATEGORY_FILTER_LABELS = {"race": "à la course", "rider": "au coureur"}
DATE_COLUMNS = ("race_date", "change_date", "start_date", "end_date")


def translate_values(df: pd.DataFrame) -> pd.DataFrame:
    """Values of the analytics (labels.py) replaced by their French labels."""
    df = df.replace(VALUE_LABELS)
    return df


def build_column_config(df: pd.DataFrame) -> dict[str, Any]:
    """Configuration of the columns of st.dataframe: ids hidden, French headers, dates as
    DD/MM/YYYY, tooltips of the columns of COLUMN_HELP.
    """
    config = {}
    for col in df.columns:
        label = COLUMN_LABELS.get(col, col)
        if col in HIDDEN_COLUMNS:
            config[col] = None
        elif col in DATE_COLUMNS:
            config[col] = st.column_config.DateColumn(label, format="DD/MM/YYYY")
        elif col in COLUMN_HELP:
            config[col] = st.column_config.Column(label, help=COLUMN_HELP[col])
        else:
            config[col] = label
    return config


def format_departement(code: str | None, name: str | None) -> str:
    """Label "44 - Loire-Atlantique", the code alone if the name is missing, empty if the code is missing."""
    if pd.isna(code):
        return ""
    if pd.isna(name):
        return code
    return f"{code} - {name}"
