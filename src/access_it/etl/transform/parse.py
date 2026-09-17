from bs4 import BeautifulSoup
from bs4.element import Tag


def get_text_safe(tag: Tag | None) -> str | None:
    if tag is None:
        page_element = None
    else:
        page_element = tag.get_text(strip=True)
    return page_element

    bs = BeautifulSoup(html, features="html.parser")
    discipline = get_text_safe(bs.find(name="div", class_="discipline"))
    date = get_text_safe(bs.find(name="div", class_="date"))
    title = get_text_safe(bs.find(name="h1", class_="titre"))
    departement = get_text_safe(bs.find(name="div", class_="localisation"))
    data = {
        "discipline": discipline,
        "date": date,
        "title": title,
        "departement": departement
    }
    for blk in bs.find_all(name="div", class_="info-principale"):
        key = blk.find(name="div", class_="titreValeur-titre")
        value = blk.find(name="div", class_="titreValeur-valeur")
        if key and value:
            data[key.get_text(strip=True)] = value.get_text(strip=True)
    rankings = get_rankings(html)
    for ranking in rankings:
        if not "rankings" in data.keys():
            data["rankings"] = {}
        ranking_id = ranking["uid"]
        ranking_name = bs.find(name="a", grille=ranking_id).get_text(strip=True)
        if (
            len(rankings) > 1
            and (
                sorting_key(ranking_name).startswith("femme") or
                sorting_key(ranking_name).startswith("dame")
                )
        ):
            continue
        try:
            ranking_data = pd.DataFrame(ranking["resultats"])[["RANG", "NOM", "PRENOM", "UCIID", "CLUB"]]
            data["rankings"][ranking_id] = {
                "name": ranking_name,
                "data": ranking_data
            }
        except KeyError:
            pass
    return data
