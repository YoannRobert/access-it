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
    """Show a table whose selected row leads to the page of its rider or race."""
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
