import re
import unicodedata


def normalize_string_and_fold_case(s: str) -> str:
    return unicodedata.normalize("NFKD", s.casefold()).encode("ascii", "ignore").decode()


def collapse_spaces(text: str) -> str:
    """Replace every run of two or more consecutive spaces with a single space."""
    return re.sub(r" {2,}", " ", text)
