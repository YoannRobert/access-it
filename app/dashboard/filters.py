"""Filters shared by the pages of the dashboard (season, region, categories, counts).

Each function shows its widget in the given container (a column, a tab or st) and returns
the chosen value.
"""

from streamlit.delta_generator import DeltaGenerator
from typing import Literal

from access_it.analytics.ranking_tools import CATEGORIES
from access_it.common.regions import COVERED_REGIONS
from access_it.common.seasons import FIRST_SEASON

from data import DEFAULT_REGION
from translations import CATEGORY_FILTER_LABELS, REGION_LABELS


def select_season(container: DeltaGenerator, default_season: int) -> int:
    """Season, from default_season (the default value) down to FIRST_SEASON."""
    return container.selectbox(
        label="Saison",
        options=range(default_season, FIRST_SEASON - 1, -1)
    )


def select_region(container: DeltaGenerator) -> str:
    """Covered region, DEFAULT_REGION by default."""
    return container.selectbox(
        label="Région",
        options=COVERED_REGIONS,
        index=COVERED_REGIONS.index(DEFAULT_REGION),
        format_func=REGION_LABELS.get
    )


def select_categories(container: DeltaGenerator, label: str) -> tuple[str, ...]:
    """Contiguous categories chosen as a range (A1 to A4 by default), in the order of CATEGORIES."""
    first, last = container.select_slider(
        label=label,
        options=CATEGORIES,
        value=(CATEGORIES[0], CATEGORIES[-1])
    )
    return CATEGORIES[CATEGORIES.index(first):CATEGORIES.index(last) + 1]


def select_category_filter(container: DeltaGenerator) -> Literal["race", "rider"]:
    """Category filter: on the categories of the races ("race", by default) or of the riders
    ("rider").
    """
    return container.radio(
        label="Filtre de catégorie appliqué",
        options=["race", "rider"],
        format_func=CATEGORY_FILTER_LABELS.get,
        horizontal=True,
        help=(
            '« à la course » pour filtrer sur les catégories des courses, '
            '« au coureur » pour filtrer sur les catégories des coureurs aux dates des courses'
        )
    )


def select_max_count(
        container: DeltaGenerator,
        label: str,
        min_value: int = 5,
        max_value: int = 30,
        step: int = 5,
        value: int = 10
) -> int:
    """Number chosen with a slider (5 to 30 by steps of 5, 10 by default)."""
    return container.slider(
        label=label, min_value=min_value, max_value=max_value, value=value, step=step
    )
