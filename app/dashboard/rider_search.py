import pandas as pd
import streamlit as st

from pathlib import Path

from computations import get_rider_list, search_riders
from translations import build_column_config, format_departement, REGION_LABELS, translate_values


FILTER_KEYS = ("first_name", "departement_code", "club_id")


def _key(prefix: str, name: str) -> str:
    return f"{prefix}_{name}"


def apply_name(prefix: str) -> None:
    """Start a new search with the typed name."""
    st.session_state[_key(prefix, "applied_name")] = st.session_state[_key(prefix, "name_input")].strip()
    for key in FILTER_KEYS:
        st.session_state[_key(prefix, key)] = None
    st.session_state[_key(prefix, "regions")] = []


def reset_departement_and_club(prefix: str) -> None:
    st.session_state[_key(prefix, "departement_code")] = None
    st.session_state[_key(prefix, "club_id")] = None


def reset_club(prefix: str) -> None:
    st.session_state[_key(prefix, "club_id")] = None


def find_rider(snapshot_path: Path, rider_id: str | None) -> pd.Series | None:
    if rider_id is None:
        return None
    rider_list = get_rider_list(snapshot_path)
    rows = rider_list[rider_list["rider_id"] == rider_id]
    return None if rows.empty else rows.iloc[0]


def select_rider(snapshot_path: Path, prefix: str) -> str | None:
    """Show the rider search (name, filters, table) and return the selected rider_id, or None."""
    for key in ("applied_name", *FILTER_KEYS):
        st.session_state.setdefault(_key(prefix, key), None)
    st.session_state.setdefault(_key(prefix, "regions"), [])

    col_last_name, col_filter = st.columns([3, 1], vertical_alignment="bottom")
    col_first_name, col_regions, col_departement, col_club = st.columns(4)

    last_name = col_last_name.text_input(
        label="Nom",
        key=_key(prefix, "name_input"),
        placeholder="Validez avec Entrée puis cliquez sur Filtrer"
    )
    col_filter.button(
        label="Filtrer",
        on_click=apply_name,
        args=(prefix,),
        disabled=not last_name.strip(),
        key=_key(prefix, "filter_button")
    )

    applied_name = st.session_state[_key(prefix, "applied_name")]
    first_name = st.session_state[_key(prefix, "first_name")]
    regions = tuple(st.session_state[_key(prefix, "regions")])
    departement_code = st.session_state[_key(prefix, "departement_code")]
    club_id = st.session_state[_key(prefix, "club_id")]

    riders, choices = search_riders(
        snapshot_path,
        last_name=applied_name,
        first_name=first_name,
        regions=regions,
        departement_code=departement_code,
        club_id=club_id,
    )

    col_first_name.selectbox(
        label="Prénom",
        options=[None] if applied_name is None else [None, *choices.first_names],
        format_func=lambda name: "Tous" if name is None else name,
        key=_key(prefix, "first_name"),
        disabled=applied_name is None
    )

    st.session_state[_key(prefix, "regions")] = [
        region for region in st.session_state[_key(prefix, "regions")] if region in choices.regions
    ]
    col_regions.multiselect(
        label="Régions",
        options=choices.regions,
        format_func=REGION_LABELS.get,
        key=_key(prefix, "regions"),
        on_change=reset_departement_and_club,
        args=(prefix,)
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
        key=_key(prefix, "departement_code"),
        on_change=reset_club,
        args=(prefix,)
    )

    club_labels = dict(zip(choices.clubs["club_id"], choices.clubs["club"]))
    col_club.selectbox(
        label="Club",
        options=[None] if departement_code is None else [None, *choices.clubs["club_id"]],
        format_func=lambda i: "Tous" if i is None else club_labels[i],
        key=_key(prefix, "club_id"),
        disabled=departement_code is None,
    )

    kept_columns = ["last_name", "first_name", "category", "club", "departement", "rider_id"]
    if riders.empty:
        st.info("Aucun coureur pour ces critères.")
        return None
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
            key=_key(prefix, f"table_{applied_name}_{first_name}_{regions}_{departement_code}_{club_id}")
        )

        rows = event.selection.rows
        if rows:
            return table.iloc[rows[0]]["rider_id"]
        else:
            return None
