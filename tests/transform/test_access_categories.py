"""Characterization tests of the reading of Access categories in names and titles."""

import pytest

from access_it.etl.transform.categories import (
    count_nb_access_subcategories_from_name, find_access_categories_from_name,
    get_higher_access_subcategory, has_access_subcategories
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
