"""Tests of the pages of the dashboard, run with AppTest on the fake snapshot (see conftest.py)."""

from datetime import date

from access_it.common.regions import BRETAGNE, PAYS_DE_LA_LOIRE

SEASON_PAGE = "views/season.py"
RIDER_PAGE = "views/rider.py"
HEAD_TO_HEAD_PAGE = "views/head_to_head.py"
RACE_PAGE = "views/race.py"
RANKINGS_PAGE = "views/rankings.py"
ABOUT_PAGE = "views/about.py"


def by_label(elements, label: str):
    """Only element of a list of widgets with this label."""
    (element,) = [element for element in elements if element.label == label]
    return element


def table(app, key_prefix: str):
    """Only table of the page whose key starts with key_prefix."""
    (element,) = [df for df in app.dataframe if df.key and df.key.startswith(key_prefix)]
    return element


def values(elements) -> list:
    """Values of a list of elements (titles, messages, metrics...)."""
    return [element.value for element in elements]


def metric(app, label: str) -> str:
    return by_label(app.metric, label).value


def open_selected_row(app, key_prefix: str, row: int):
    """Select a row of a navigable table, then click its button (see navigation.py)."""
    key = table(app, key_prefix).key
    app.session_state[key] = {"selection": {"rows": [row], "columns": [], "cells": []}}
    app.run()
    app.button(key=f"{key}_button").click().run()
    return app


# Home page, sidebar and About page

def test_home_page_is_the_default_page_and_links_to_every_page(open_page):
    app = open_page()
    assert not app.exception
    assert values(app.title) == ["Access it!"]
    linked_pages = {link.proto.page for link in app.get("page_link")}
    assert linked_pages == {"season", "rankings", "rider", "head-to-head", "race", "about"}


def test_sidebar_shows_the_date_of_the_last_race(open_page):
    app = open_page()
    assert not app.exception
    assert "Dernière course enregistrée : 20/09/2026." in values(app.sidebar.markdown)


def test_about_page_shows_the_contact_address(open_page):
    app = open_page(ABOUT_PAGE)
    assert not app.exception
    assert values(app.title) == ["À propos"]
    assert any("accessit.dashboard@gmail.com" in text for text in values(app.markdown))


# Season page

def test_season_page_counts_the_races_of_the_default_season_and_region(open_page):
    app = open_page(SEASON_PAGE)
    assert not app.exception
    assert values(app.title) == ["Saison"]
    assert metric(app, "Courses") == "3"  # c3, c4 and c6 in Pays de la Loire in 2026


def test_season_page_in_bretagne(open_page):
    app = open_page(SEASON_PAGE)
    by_label(app.selectbox, "Région").set_value(BRETAGNE).run()
    assert not app.exception
    assert metric(app, "Courses") == "1"


def test_season_page_shows_the_category_changes(open_page):
    app = open_page(SEASON_PAGE)
    changes = table(app, "season_changes_").value
    assert changes["last_name"].tolist() == ["PETIT"]
    assert changes["change_type"].tolist() == ["montée"]


def test_most_titled_rider_opens_the_rider_page(open_page):
    app = open_page(SEASON_PAGE)
    rider_id = table(app, "season_riders_").value["rider_id"].iloc[0]
    open_selected_row(app, "season_riders_", 0)
    assert not app.exception
    assert values(app.title) == ["Coureur"]
    assert app.query_params["rider_id"] == rider_id


# Rankings page

def test_regional_challenge_in_pays_de_la_loire(open_page):
    app = open_page(RANKINGS_PAGE)
    assert not app.exception
    ranking = table(app, "ranking_challenge_").value
    assert ranking["rider_id"].tolist() == ["r1"]  # the only A1 rider of the region


def test_regional_challenge_does_not_exist_in_bretagne(open_page):
    app = open_page(RANKINGS_PAGE)
    by_label(app.selectbox, "Région").set_value(BRETAGNE).run()
    assert not app.exception
    assert "Le challenge régional n'existe que pour les Pays de la Loire." in values(app.info)


def test_promotion_ranking_hides_the_region(open_page):
    app = open_page(RANKINGS_PAGE)
    ranking = table(app, "ranking_promotion_").value
    assert "region" not in ranking.columns
    assert ranking["rider_id"].tolist() == ["r1"]


def test_club_ranking(open_page):
    app = open_page(RANKINGS_PAGE)
    clubs = [df.value for df in app.dataframe if "club_id" in df.value.columns]
    assert len(clubs) == 1
    assert set(clubs[0]["club"]) == {"VC NANTES", "UC SAINT-NAZAIRE", "VS LA ROCHE"}


# Rider page

def test_search_by_name_finds_the_homonyms(open_page):
    app = open_page(RIDER_PAGE)
    assert app.button(key="rider_filter_button").disabled
    app.text_input(key="rider_name_input").input("dupont").run()
    app.button(key="rider_filter_button").click().run()
    assert not app.exception
    assert table(app, "rider_table_").value["first_name"].tolist() == ["Jean", "Paul"]
    assert app.selectbox(key="rider_first_name").options == ["Tous", "Jean", "Paul"]


def test_club_is_chosen_only_within_a_departement(open_page):
    app = open_page(RIDER_PAGE)
    assert app.selectbox(key="rider_club_id").disabled
    app.selectbox(key="rider_departement_code").set_value("85").run()
    assert not app.exception
    club = app.selectbox(key="rider_club_id")
    assert not club.disabled
    assert club.options == ["Tous", "VS LA ROCHE"]


def test_selected_rider_of_the_search_is_written_in_the_url(open_page):
    app = open_page(RIDER_PAGE)
    key = table(app, "rider_table_").key
    rider_id = table(app, "rider_table_").value["rider_id"].iloc[0]
    app.session_state[key] = {"selection": {"rows": [0], "columns": [], "cells": []}}
    app.run()
    assert app.query_params["rider_id"] == rider_id


def test_rider_profile_from_the_url(open_page):
    app = open_page(RIDER_PAGE, rider_id="r4")
    assert not app.exception
    assert values(app.subheader) == ["Yann LE GOFF"]
    assert metric(app, "Nombre de courses prises en compte") == "1"  # c5, within 6 months


def test_unknown_rider_shows_an_error(open_page):
    app = open_page(RIDER_PAGE, rider_id="unknown")
    assert not app.exception
    assert values(app.error) == ["Coureur introuvable."]


def test_result_of_a_rider_opens_the_race_page(open_page):
    app = open_page(RIDER_PAGE, rider_id="r1")
    open_selected_row(app, "rider_result_", 0)  # most recent result: c6
    assert not app.exception
    assert values(app.title) == ["Course"]
    assert app.query_params["race_id"] == "c6"
    assert values(app.subheader) == ["Nocturne de Nantes"]


# Head-to-head page

def test_head_to_head_needs_two_riders(open_page):
    app = open_page(HEAD_TO_HEAD_PAGE, rider_id="r1")
    assert not app.exception
    assert "Choisissez un coureur et un adversaire." in values(app.info)


def test_head_to_head_of_two_homonyms(open_page):
    app = open_page(HEAD_TO_HEAD_PAGE, rider_id="r1", opponent_id="r2")
    assert not app.exception
    assert values(app.subheader) == ["Jean DUPONT vs Paul DUPONT"]
    assert metric(app, "Courses communes") == "3"  # c1, c3 and c5
    assert metric(app, "Jean DUPONT devant") == "2"
    assert metric(app, "Paul DUPONT devant") == "1"
    assert metric(app, "Égalités") == "0"


def test_head_to_head_of_one_season(open_page):
    app = open_page(HEAD_TO_HEAD_PAGE, rider_id="r1", opponent_id="r2")
    app.selectbox(key="h2h_season").set_value(2025).run()
    assert not app.exception
    assert metric(app, "Courses communes") == "1"


def test_head_to_head_of_the_same_rider(open_page):
    app = open_page(HEAD_TO_HEAD_PAGE, rider_id="r1", opponent_id="r1")
    assert "Choisissez deux coureurs différents." in values(app.info)


def test_head_to_head_of_an_unknown_rider(open_page):
    app = open_page(HEAD_TO_HEAD_PAGE, rider_id="r1", opponent_id="unknown")
    assert values(app.error) == ["Coureur introuvable."]


# Race page

def test_race_list_of_the_default_season_and_region(open_page):
    app = open_page(RACE_PAGE)
    assert not app.exception
    assert "3 courses." in values(app.caption)
    races = table(app, "race_table_").value
    assert races["race_id"].tolist() == ["c6", "c4", "c3"]


def test_inverted_dates_keep_the_race_of_the_url(open_page):
    app = open_page(RACE_PAGE, race_id="c3")
    app.date_input(key="race_end_date").set_value(date(2025, 12, 31)).run()
    assert not app.exception
    assert values(app.warning) == ["La date de fin précède la date de début."]
    assert values(app.subheader) == ["Prix de Saint-Herblain"]


def test_new_region_empties_the_departements(open_page):
    app = open_page(RACE_PAGE)
    app.multiselect(key=f"race_departements_{PAYS_DE_LA_LOIRE}").set_value(["44"]).run()
    assert table(app, "race_table_").value["race_id"].tolist() == ["c6", "c3"]
    by_label(app.selectbox, "Région").set_value(BRETAGNE).run()
    assert not app.exception
    departements = app.multiselect(key=f"race_departements_{BRETAGNE}")
    assert departements.value == []
    assert departements.options == ["35 - Ille-et-Vilaine"]


def test_unknown_race_shows_an_error(open_page):
    app = open_page(RACE_PAGE, race_id="unknown")
    assert values(app.error) == ["Course introuvable."]


def test_ranked_rider_opens_the_rider_page(open_page):
    app = open_page(RACE_PAGE, race_id="c3")
    open_selected_row(app, "race_ranking_", 0)  # winner of c3: r2
    assert not app.exception
    assert values(app.title) == ["Coureur"]
    assert app.query_params["rider_id"] == "r2"


# Search expanders

def test_rider_search_is_open_without_rider_and_closed_with_one(open_page):
    assert open_page(RIDER_PAGE).session_state["rider_search"] is True
    assert open_page(RIDER_PAGE, rider_id="r1").session_state["rider_search"] is False


def test_selected_rider_of_the_search_closes_the_search(open_page):
    app = open_page(RIDER_PAGE)
    key = table(app, "rider_table_").key
    app.session_state[key] = {"selection": {"rows": [0], "columns": [], "cells": []}}
    app.run()
    assert not app.exception
    assert app.session_state["rider_search"] is False
    assert len(app.subheader) == 1  # profile of the selected rider


def test_closed_rider_search_can_be_opened_again(open_page):
    app = open_page(RIDER_PAGE, rider_id="r1")
    app.session_state["rider_search"] = True
    app.run()
    assert app.session_state["rider_search"] is True


def test_link_to_a_rider_closes_the_search_of_the_rider_page(open_page):
    app = open_page(RACE_PAGE, race_id="c3")
    open_selected_row(app, "race_ranking_", 0)
    assert app.session_state["rider_search"] is False


def test_head_to_head_search_is_closed_only_with_both_riders(open_page):
    assert open_page(HEAD_TO_HEAD_PAGE, rider_id="r1").session_state["h2h_search"] is True
    app = open_page(HEAD_TO_HEAD_PAGE, rider_id="r1", opponent_id="r2")
    assert app.session_state["h2h_search"] is False


def test_race_search_is_open_without_race_and_closed_with_one(open_page):
    assert open_page(RACE_PAGE).session_state["race_search"] is True
    assert open_page(RACE_PAGE, race_id="c3").session_state["race_search"] is False


def test_selected_race_of_the_list_closes_the_search(open_page):
    app = open_page(RACE_PAGE)
    key = table(app, "race_table_").key
    app.session_state[key] = {"selection": {"rows": [0], "columns": [], "cells": []}}
    app.run()
    assert not app.exception
    assert app.query_params["race_id"] == "c6"
    assert app.session_state["race_search"] is False
