import unicodedata


def normalize_string_and_fold_case(s: str) -> str:
    return unicodedata.normalize("NFKD", s.casefold()).encode("ascii", "ignore").decode()
