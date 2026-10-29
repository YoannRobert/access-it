"""Characterization tests of the reading of Access categories in names and titles."""

import logging

import pytest

from access_it.common.access_categories import (
    count_nb_access_subcategories_from_name, find_access_categories_from_name,
    get_higher_access_subcategory, has_access_subcategories, is_women_only_name
)


def categories(name: str) -> list[int]:
    return [k for k, v in find_access_categories_from_name(name).items() if v]


@pytest.mark.parametrize(
    "name, expected",
    [
        # Usual notations
        ("Access 1-2", [1, 2]),
        ("ACCESS 3/4", [3, 4]),
        ("Acc 3", [3]),
        ("A1-A2", [1, 2]),
        ("A3-A4", [3, 4]),
        ("Access 1 et 2", [1, 2]),
        ("Access 1, 2", [1, 2]),
        ("Access 3.4", [3, 4]),
        ("access 2+3", [2, 3]),
        ("ACCESS 1 2 3 4", [1, 2, 3, 4]),
        ("PLUDUNO - ACCESS 1-2-3-4 H/F", [1, 2, 3, 4]),
        # Spelling mistakes
        ("Accc 4", [4]),
        ("acess 2-3", [2, 3]),
        # "Access" alone: all the subcategories
        ("LOIRON-RUILLE (Access)", [1, 2, 3, 4]),
        # Text after "sauf" is ignored (riders excluded, never a category)
        ("LOIRON-RUILLE - ACCESS 1.2.3.4 SAUF FEMMES", [1, 2, 3, 4]),
        ("POMMERIEUX - ACCESS 3/4 SAUF FEMMES", [3, 4]),
        ("RETIERS - ACCESS 1-2-3-4 H/F sauf hommes du 56", [1, 2, 3, 4]),
        # No Access category
        ("Open", []),
        ("U17", []),
        ("Pass'Cyclisme", []),
        ("1ère catégorie", []),
    ],
)
def test_find_access_categories_from_name(name, expected):
    assert categories(name) == expected


def test_helpers_on_access_categories():
    assert count_nb_access_subcategories_from_name("Access 1-2") == 2
    assert has_access_subcategories("Acc 3")
    assert not has_access_subcategories("Open")
    assert get_higher_access_subcategory("Access 3/4") == 3


def test_returned_dict_can_be_modified_safely():
    find_access_categories_from_name("Access 1-2")[1] = False
    assert categories("Access 1-2") == [1, 2]


def test_verbose_logs_each_normalization_step(caplog):
    caplog.set_level(logging.INFO)
    find_access_categories_from_name("Access 1-2", verbose=True)
    messages = [record.getMessage() for record in caplog.records]
    assert messages[0] == "name=Access 1-2"
    assert messages[-1] == "n=a1a2"


@pytest.mark.parametrize(
    "name, expected",
    [
        # Women's words, anywhere in the name (names of real rankings)
        ("C4356009100 : BIGNAN - ACCESS Dames", True),
        ("feminines", True),
        ("FEMMES", True),
        ("Femmes sur épreuve Access 1-2-3-4", True),
        ("Femmes 17 ans et +", True),
        ("Access 3-4 Féminine", True),
        ("Cadettes", True),
        ("Juniores", True),
        ("Filles U17", True),
        # Text after "sauf" is ignored (riders excluded)
        ("POMMERIEUX - ACCESS 3/4 SAUF FEMMES", False),
        ("ACCESS 1-2 sauf dames", False),
        # Place names "Notre-Dame" are ignored
        ("NOTRE DAME DE MONTS (A1-A2)", False),
        ("Notre-Dame-de-Riez - Access 3-4", False),
        ("NOTRE DAME DE MONTS - Dames", True),
        # No women's word
        ("Classement général individuel (épreuve de 1 jour)", False),
        ("ACCESS 1-2-3-4 H/F", False),
        ("Access 3-4", False),
        ("F", False),
    ],
)
def test_is_women_only_name(name, expected):
    assert is_women_only_name(name) is expected
