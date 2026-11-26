"""Forecast page of the dashboard.

Choice of a race date, then of a race of this date, then its riders entered with their chances
to win, to make the podium, the top 5 and the top 10 (see access_it.analytics.forecast_list).
"""

import pandas as pd
import streamlit as st

from datetime import datetime

from access_it.analytics.forecast_list import (
    get_default_forecast_date, get_race_entries, list_day_races, list_forecast_dates
)

from computations import get_race_runs, get_rider_list
from data import PARIS, get_snapshot_holder, load_forecasts, load_snapshot
from navigation import navigable_dataframe
from settings import MISSING_PLACE
from translations import WEEKDAY_LABELS, build_column_config

PROBABILITY_COLUMNS = ["p_win", "p_podium", "p_top5", "p_top10"]
ENTRY_COLUMNS = ["last_name", "first_name", "club", "category"]
OPTIONAL_COLUMNS = {
    "nb_races_used": (
        "Courses récentes",
        "Courses retenues : au plus les 10 dernières des 12 mois précédant la course",
    ),
    "top_n_rate": ("Taux de top 20", "Part des courses récentes finies dans les 20 premiers"),
    "best_place": (
        "Meilleure place",
        "Meilleure place dans les courses récentes ; vide sans course récente",
    ),
}
RANK_HELP = "Rang du coureur selon ses chances de victoire"


def format_run_time(run_time: pd.Timestamp) -> str:
    """Day and time of a run in Paris time, e.g. "vendredi 13/02/2026 à 01 h 00"."""
    local_time = run_time.tz_convert(PARIS)
    weekday = WEEKDAY_LABELS[local_time.weekday()]
    return f"{weekday} {local_time:%d/%m/%Y} à {local_time:%H} h {local_time:%M}"


snapshot_path, _ = load_snapshot()

st.title("Prévisions")

with st.expander("Comment lire cette page"):
    st.markdown(
        """
- Choisissez la date d'une course, puis la course. Le calendrier va de la première à la dernière
  date avec une prévision ; certains jours n'ont aucune course prévue.
- Les chances sont calculées par un modèle à partir des résultats des 12 derniers mois de chaque
  engagé, la veille de la course. Ce sont des probabilités, pas des certitudes : un coureur à
  30 % de chances de victoire perd plus souvent qu'il ne gagne.
- Dans une course, les chances de victoire de tous les engagés totalisent 100 % ; celles du
  podium 300 %, du top 5 500 % et du top 10 1000 %.
- Seuls les engagés reconnus dans les résultats enregistrés figurent dans le tableau. Le club et
  la catégorie sont ceux d'aujourd'hui, pas forcément ceux du jour de la course.
- Les prévisions de la saison 2026 ont été calculées après coup, en n'utilisant que les
  résultats connus la veille de chaque course.
"""
    )

load_forecasts()
race_runs = get_race_runs(get_snapshot_holder().upcoming_files)
dates = list_forecast_dates(race_runs)
default_date = get_default_forecast_date(dates, datetime.now(PARIS).strftime("%Y-%m-%d"))

race_date = st.date_input(
    label="Date de la course",
    value=default_date.date(),
    min_value=dates[0].date(),
    max_value=dates[-1].date(),
    format="DD/MM/YYYY",
    key="forecasts_date",
)
day_races = list_day_races(race_runs, pd.Timestamp(race_date))
if day_races.empty:
    st.info(f"Aucune course avec prévision le {race_date:%d/%m/%Y}.")
    st.stop()

labels = {
    race.race_id: f"{race.page_title} – {race.startlist_heading}"
    + ("" if race.has_forecast else " (sans prévision)")
    for race in day_races.itertuples()
}
race_id = st.selectbox(
    label="Course",
    options=list(labels),
    format_func=lambda option: labels[option],
    key=f"forecasts_race_{race_date}",
)
race = day_races.set_index("race_id").loc[race_id]

entries = get_race_entries(race_runs, race_id, get_rider_list(snapshot_path))
entries["best_place"] = entries["best_place"].mask(entries["best_place"] == MISSING_PLACE)
entries["top_n_rate"] = entries["top_n_rate"].mask(entries["nb_races_used"] == 0)
table_key = f"forecasts_table_{race_id}_{race.run_time:%Y%m%dT%H%M%S}"

if race.has_forecast:
    columns = st.columns(3)
    shown = [
        column for container, (column, (label, _)) in zip(columns, OPTIONAL_COLUMNS.items())
        if container.checkbox(label, key=f"forecasts_show_{column}")
    ]
    column_config = build_column_config(entries)
    column_config["rank_win"] = st.column_config.NumberColumn("Rang", help=RANK_HELP)
    for column in PROBABILITY_COLUMNS:
        column_config[column] = st.column_config.NumberColumn(
            column_config[column], format="percent", step=0.001
        )
    for column, (label, help_text) in OPTIONAL_COLUMNS.items():
        column_config[column] = st.column_config.NumberColumn(label, help=help_text)
    column_config["top_n_rate"] = st.column_config.NumberColumn(
        OPTIONAL_COLUMNS["top_n_rate"][0], help=OPTIONAL_COLUMNS["top_n_rate"][1],
        format="percent", step=0.01,
    )
    navigable_dataframe(
        entries, id_column="rider_id", key=table_key, column_config=column_config,
        column_order=["rank_win", *ENTRY_COLUMNS, *PROBABILITY_COLUMNS, *shown],
    )
    st.caption(f"Prévision calculée le {format_run_time(race.run_time)}.")
else:
    st.info("Aucune prévision n'est disponible pour cette course.")
    navigable_dataframe(entries, id_column="rider_id", key=table_key, column_order=ENTRY_COLUMNS)
    st.caption(f"Engagés connus le {format_run_time(race.run_time)}.")
