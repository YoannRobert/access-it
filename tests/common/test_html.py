"""Unit tests of the reading of the FFC result pages."""

from bs4 import BeautifulSoup

from access_it.common.html import get_elements_from_results_page


def results_page(*blocks: tuple[str, str]) -> BeautifulSoup:
    """Minimal result page with general information blocks (label, value)."""
    html = "".join(
        "<div class='info-principale'>"
        f"<div class='titreValeur-titre'>{label}</div>"
        f"<div class='titreValeur-valeur'>{value}</div></div>"
        for label, value in blocks
    )
    return BeautifulSoup(html, features="html.parser")


def test_result_page_elements_are_translated():
    bs = results_page(("Saison", "2026"), ("Code épreuve", "1.27.1"))
    assert get_elements_from_results_page(bs) == {"season": 2026, "race_code": "1.27.1"}


def test_unknown_label_is_ignored_and_reported_once(capsys):
    bs = results_page(("Nouveau champ FFC", "x"), ("Code épreuve", "1.27.1"))
    assert get_elements_from_results_page(bs) == {"race_code": "1.27.1"}
    assert get_elements_from_results_page(bs) == {"race_code": "1.27.1"}
    assert capsys.readouterr().out.count("unknown label on a result page") == 1


def test_empty_label_or_value_is_ignored():
    bs = results_page(("", "x"), ("Durée", ""), ("Code épreuve", "1.27.1"))
    assert get_elements_from_results_page(bs) == {"race_code": "1.27.1"}
