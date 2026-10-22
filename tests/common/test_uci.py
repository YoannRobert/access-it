"""Unit tests of the UCI IDs."""

import pytest

from access_it.common.uci import is_valid_uci_id


@pytest.mark.parametrize(
    "uci_id, expected",
    [
        ("10012345656", True),  # 100123456 % 97 == 56
        ("10012345601", False),  # wrong check digits
        ("1001234565", False),  # 10 digits
        ("1001234565a", False),
        ("Liste Rouge", False),
        ("", False),
        (None, False),
    ],
)
def test_is_valid_uci_id(uci_id, expected):
    assert is_valid_uci_id(uci_id) is expected
