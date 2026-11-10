"""Unit tests of the display helpers of the dashboard (tables.py, translations.py)."""

import pandas as pd
import pytest

from access_it.analytics.labels import NOT_APPLICABLE, UNKNOWN_CATEGORY, UNKNOWN_CLUB
from tables import ROW_HEIGHT, table_height
from translations import COLUMN_HELP, COLUMN_LABELS, build_column_config, format_departement, translate_values


@pytest.mark.parametrize("code, name, expected", [
    ("44", "Loire-Atlantique", "44 - Loire-Atlantique"),
    ("44", None, "44"),
    ("44", float("nan"), "44"),
    (None, "Loire-Atlantique", ""),
    (float("nan"), None, ""),
], ids=["code_and_name", "missing_name", "nan_name", "missing_code", "nan_code"])
def test_departement_label(code, name, expected):
    assert format_departement(code, name) == expected


@pytest.mark.parametrize("nb_rows, expected_rows", [
    (0, 0), (3, 3), (20, 20), (50, 20),
], ids=["empty", "few_rows", "max_rows", "beyond_max_rows"])
def test_table_height_shows_the_rows_up_to_the_maximum(nb_rows, expected_rows):
    df = pd.DataFrame({"x": range(nb_rows)})
    assert table_height(df) == ROW_HEIGHT * (expected_rows + 1) + 3


def test_table_height_with_another_maximum():
    df = pd.DataFrame({"x": range(50)})
    assert table_height(df, max_rows=30) == ROW_HEIGHT * 31 + 3


def test_column_config_hides_ids_formats_dates_and_translates_labels():
    df = pd.DataFrame(columns=["race_date", "title", "unknown_column", "rider_id", "race_id"])
    config = build_column_config(df)
    assert list(config) == list(df.columns)
    assert config["rider_id"] is None
    assert config["race_id"] is None
    assert config["title"] == COLUMN_LABELS["title"]
    assert config["unknown_column"] == "unknown_column"
    assert config["race_date"]["label"] == COLUMN_LABELS["race_date"]
    assert config["race_date"]["type_config"]["format"] == "DD/MM/YYYY"


def test_column_config_adds_the_tooltips():
    df = pd.DataFrame(columns=["nb_scoring_races", "points"])
    config = build_column_config(df)
    assert config["nb_scoring_races"]["label"] == COLUMN_LABELS["nb_scoring_races"]
    assert config["nb_scoring_races"]["help"] == COLUMN_HELP["nb_scoring_races"]
    assert config["points"] == COLUMN_LABELS["points"]


def test_values_are_translated_and_the_others_kept():
    df = pd.DataFrame({
        "category": [UNKNOWN_CATEGORY, "A2"],
        "club": ["VC Nantes", UNKNOWN_CLUB],
        "challenge": [NOT_APPLICABLE, None],
    })
    translated = translate_values(df)
    assert translated["category"].tolist() == ["catégorie inconnue", "A2"]
    assert translated["club"].tolist() == ["VC Nantes", "club inconnu"]
    assert translated["challenge"].iloc[0] == "non concerné"
    assert pd.isna(translated["challenge"].iloc[1])
    assert df["category"].iloc[0] == UNKNOWN_CATEGORY  # input left unchanged
