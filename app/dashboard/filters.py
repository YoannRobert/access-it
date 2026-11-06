from streamlit.delta_generator import DeltaGenerator
from typing import Literal

from access_it.analytics.ranking_tools import CATEGORIES
from access_it.common.regions import COVERED_REGIONS
from access_it.common.seasons import FIRST_SEASON

from data import DEFAULT_REGION
from translations import CATEGORY_FILTER_LABELS, REGION_LABELS


def select_season(container: DeltaGenerator, default_season: int) -> int:
    return container.selectbox(
        label="Saison",
        options=range(default_season, FIRST_SEASON - 1, -1)
    )


def select_region(container: DeltaGenerator) -> str:
    return container.selectbox(
        label="Région",
        options=COVERED_REGIONS,
        index=COVERED_REGIONS.index(DEFAULT_REGION),
        format_func=REGION_LABELS.get
    )


def select_categories(container: DeltaGenerator, label: str) -> tuple[str, ...]:
    first, last = container.select_slider(
        label=label,
        options=CATEGORIES,
        value=(CATEGORIES[0], CATEGORIES[-1])
    )
    return CATEGORIES[CATEGORIES.index(first):CATEGORIES.index(last) + 1]


def select_category_filter(container: DeltaGenerator) -> Literal["race", "rider"]:
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
    return container.slider(
        label=label, min_value=min_value, max_value=max_value, value=value, step=step
    )
