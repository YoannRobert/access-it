"""UCI IDs of the riders."""

import re


def is_valid_uci_id(uci_id: str | None) -> bool:
    """Whether `uci_id` is an 11-digit UCI ID with valid check digits (first 9 digits modulo 97)."""
    if uci_id is None:
        return False
    if not bool(re.fullmatch(r"\d{11}", uci_id)):
        return False
    return int(uci_id[:9]) % 97 == int(uci_id[9:])
