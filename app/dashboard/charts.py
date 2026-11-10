"""Altair charts of the dashboard."""

import altair as alt
import pandas as pd
import streamlit as st


def bar_chart(
        df: pd.DataFrame,
        title: str,
        x_field: str,
        y_field: str,
        xaxis_title: str,
        yaxis_title: str,
        xaxis_label_angle: int = 0,
) -> None:
    """Show a bar chart, the bars in the order of the rows of df.

    Args:
        df: Data of the chart.
        title: Title of the chart.
        x_field: Column of the categories (x axis).
        y_field: Column of the values (y axis).
        xaxis_title: Title of the x axis, also used in the tooltip.
        yaxis_title: Title of the y axis, also used in the tooltip.
        xaxis_label_angle: Angle of the labels of the x axis, in degrees.
    """
    x_name = f"{x_field}:N"
    y_name = f"{y_field}:Q"
    chart = alt.Chart(df, title=title).mark_bar().encode(
        x=alt.X(
            shorthand=x_name, sort=None, title=xaxis_title,
            axis=alt.Axis(labelLimit=0, labelAngle=xaxis_label_angle)
        ),
        y=alt.Y(shorthand=y_name, title=yaxis_title),
        tooltip=[
            alt.Tooltip(shorthand=x_name, title=xaxis_title),
            alt.Tooltip(shorthand=y_name, title=yaxis_title)
        ],
    )
    st.altair_chart(chart, width='stretch')
