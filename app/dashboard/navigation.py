"""Navigation from a table to the page of a rider or a race (selected row, then button)."""

import pandas as pd
import streamlit as st

from typing import Any

from tables import table_height
from translations import build_column_config, translate_values

TARGETS = {
    "rider_id": ("views/rider.py", "Voir la fiche du coureur"),
    "race_id": ("views/race.py", "Voir la fiche de la course"),
}


def navigable_dataframe(
    df: pd.DataFrame,
    id_column: str,
    key: str,
    column_config: dict[str, Any] | None = None,
) -> None:
    """Show a table whose selected row leads to the page of its rider or race.

    The button under the table opens the page of TARGETS, with the id of the selected row as
    URL parameter.

    Args:
        df: Table to show, with its id column (hidden by build_column_config).
        id_column: "rider_id" or "race_id": column of the ids and key of TARGETS.
        key: Key of the table, built on the criteria of the page, so that the selection is
            cleared when the content of the table changes.
        column_config: Configuration of the columns; build_column_config(df) by default.
    """
    event = st.dataframe(
        translate_values(df),
        column_config=column_config or build_column_config(df),
        hide_index=True,
        height=table_height(df),
        on_select="rerun",
        selection_mode="single-row",
        key=key
    )
    page, label = TARGETS[id_column]
    rows = event.selection.rows
    if st.button(label, disabled=not rows, key=f"{key}_button"):
        st.switch_page(page, query_params={id_column: str(df.iloc[rows[0]][id_column])})
