"""Reading of the FFC pages, shared by the extract and transform steps."""

from bs4 import BeautifulSoup
from bs4.element import Tag


TRANSLATIONS = {
    "RANG": "finish_rank",
    "NOM": "last_name",
    "PRENOM": "first_name",
    "UCIID": "uci_id",
    "CLUB": "club",
    "N° d'épreuve": "organization_code",
    "Saison": "season",
    "Type de compétition": "race_type",
    "Organisateur": "organizer",
    "Durée": "duration",
    "Code épreuve": "race_code"
}


def get_text_safe(tag: Tag | None) -> str | None:
    """Text of a tag without surrounding whitespace, or None if the tag is None."""
    if tag is None:
        page_element = None
    else:
        page_element = tag.get_text(strip=True)
    return page_element


# Labels of result pages missing from TRANSLATIONS, already reported
_reported_unknown_labels: set[str] = set()


def get_elements_from_results_page(bs: BeautifulSoup) -> dict[str, str]:
    """Read the general information blocks of a result page (see TRANSLATIONS).

    Blocks with an empty label or value are ignored; a label missing from
    TRANSLATIONS (e.g. a field added by the FFC) is ignored and reported once.
    """
    data = {}
    for blk in bs.find_all(name="div", class_="info-principale"):
        key = blk.find(name="div", class_="titreValeur-titre")
        value = blk.find(name="div", class_="titreValeur-valeur")
        key = get_text_safe(key)
        value = get_text_safe(value)
        if not key or not value:
            continue
        if key not in TRANSLATIONS:
            if key not in _reported_unknown_labels:
                _reported_unknown_labels.add(key)
                print(f"Warning: unknown label on a result page, ignored: {key!r}")
            continue
        key2 = TRANSLATIONS[key]
        data[key2] = value
        if key2 == "season":
            try:
                data[key2] = int(value)
            except ValueError:
                raise ValueError(f"'season' value ({value}) not convertible to int")
    return data
