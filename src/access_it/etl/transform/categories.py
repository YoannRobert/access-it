import re
from typing import Any
from access_it.common.text import normalize_string_and_fold_case


def find_access_categories_from_name(name: str, verbose: bool = False) -> dict[int, bool]:
    categories = {k: False for k in range(1, 5)}
    if verbose:
        print(f"name={name}")
    n = normalize_string_and_fold_case(name)  # lowering the case and removing accentuation
    if verbose:
        print(f"n={n}")
    n = n.replace("accc", "acc")  # correcting spelling mistakes
    if verbose:
        print(f"n={n}")
    for org in ["acess", "acces", "accesss"]:
        n = n.replace(org, "access")
        if verbose:
            print(f"n={n}")
    n = re.sub(r"[^A-Za-z0-9 ]", "", n)  # keeping only letters and figures
    if verbose:
        print(f"n={n}")
    n = n.replace(" et ", "")
    if verbose:
        print(f"n={n}")
    n = re.sub(r" {2,}", " ", n)  # removing extra spaces
    if verbose:
        print(f"n={n}")
    n = re.sub(r"^\d+(?=.*[a-zA-Z])", "", n)  # removing leading figures, only if letters follow
    if verbose:
        print(f"n={n}")
    for i in range(1, 4):
        for sep in [" ", "-", "+", "/"]:
            if verbose:
                old = f"{i}{sep}{i+1}"
                new = f"{i}{i+1}"
                print(f"{old} -> {new}")
            n = n.replace(f"{i}{sep}{i+1}", f"{i}{i+1}")
            if verbose:
                print(f"n={n}")
    for i in range(1, 5):
        for org in [f"access {i}", f"acc {i}", f"acc{i}"]:
            n = n.replace(org, f"access{i}")
    for seq in ["1234", "234", "123", "34", "23", "12"]:
        org = "access" + seq
        dst = "a" + "a".join(seq)
        n = n.replace(org, dst)
    for org in ["1234", "234", "123", "34", "23", "12"]:
        dst = "a" + "a".join(seq)
        n = n.replace(org, dst)
    for i in range(1, 5):
        n = n.replace(f"access{i}", f"a{i}")
    n = n.replace("access", "a1a2a3a4")
    if n.find(" sauf ") != -1:
       n = n[:n.find(" sauf ")]
    n = n.replace(" ", "")
    start, end = len(n), 0
    for s in ["a1", "a2", "a3", "a4"]:
        start = min(start, n.find(s)) if n.find(s) != -1 else start
        end = max(end, n.find(s) + 1)
    n = n[start: end + 1]
    for i in categories.keys():
        categories[i] = n.find(f"a{i}") != -1
    return categories


def find_ranking_categories(organization_data: dict[str, Any]) -> dict[str, dict[int, bool]]:
    org_name = organization_data["title"]
    org_categories = find_access_categories_from_name(org_name)
    nb_org_categories = sum([int(v) for v in org_categories.values()])
    rankings = organization_data["rankings"]
    nb_rankings = len(rankings)
    nb_rankings_categorized = 0
    ranking_categories = {}
    empty_cat = {k: False for k in range(1, 5)}

    # Finding categories by level of confidence from best to worst

    # 0) "Absolute" confidence: 1+ category(ies) found in the title and only one ranking in the organization
    if nb_org_categories > 0 and len(rankings) == 1:
        ranking_id = list(rankings.keys())[0]
        ranking_categories[ranking_id] = org_categories.copy()
        return ranking_categories

    # 1) All categories are written in the ranking names (whatever the organization name)
    found = {}
    for ranking_id in rankings.keys():
        found[ranking_id] = False
        ranking_name = rankings[ranking_id]["name"]
        categories = find_access_categories_from_name(ranking_name)
        if sum([int(v) for v in categories.values()]) > 0:
            ranking_categories[ranking_id] = categories
            found[ranking_id] = True
            nb_rankings_categorized += 1
    if all(found.values()):
        return ranking_categories

    # 2) Only one ranking lacks of categorization and it can be deduced from the organization name
    if nb_rankings - nb_rankings_categorized == 1:
        uncategorized_ranking_id = [rk_id for rk_id, rk_value in found.items() if not rk_value][0]
        found_categories = []
        for ranking_id in ranking_categories.keys():
            for cat in ranking_categories[ranking_id]:
                cat_found = ranking_categories[ranking_id][cat]
                if cat_found and cat not in found_categories:
                    found_categories.append(cat)
        ranking_categories[uncategorized_ranking_id] = {
            cat: ((cat not in found_categories) and org_categories[cat]) for cat in range(1, 5)
        }
        return ranking_categories

    # 3) N categories found in the organization name but none in its N ranking names,
    # so each ranking category is guessed (order of their appearance matters)
    if (nb_org_categories > 1) and (nb_rankings == nb_org_categories):
        cat = 0
        for ranking_id in rankings.keys():
            ranking_categories[ranking_id] = empty_cat.copy()
            cat += 1
            while cat <= 4:
                if org_categories[cat]:
                    ranking_categories[ranking_id][cat] = True
                    break
                cat += 1
        return ranking_categories

    # 4) N categories found in the organization name but none in its M ranking names,
    # so Q = N/M categories are guessed for each ranking (order of their appearance matters)
    # Only case where it can happen:
    # A1, A2, A3 and A4 are found in the organization name and there are 2 rankings,
    # so the first ranking has the categories A1 and A2, the second ranking has the categories A3 and A4.
    if (
        nb_org_categories > 1
        and nb_rankings < nb_org_categories
        and nb_org_categories % nb_rankings == 0
    ):
        cat = 0
        nb_categories_per_ranking = nb_org_categories // nb_rankings
        while cat <= 4:
            for ranking_id in rankings.keys():
                ranking_categories[ranking_id] = empty_cat.copy()
                nb_inserted_categories = 0
                while nb_inserted_categories < nb_categories_per_ranking:
                    cat += 1
                    if org_categories[cat]:
                        ranking_categories[ranking_id][cat] = True
                        nb_inserted_categories += 1
            cat += 1  # ensuring getting out of the loop in case of no rankings at all
        return ranking_categories

    return ranking_categories


def convert_categories_from_dict_to_list(categories: dict[int, bool]) -> list[str]:
    return [f"A{i}" for i, v in categories.items() if v]
