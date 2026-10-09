import pandas as pd
import re

from datetime import datetime
from typing import Literal, Any
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
        for org in [f"access {i}", f"acc {i}", f"acc{i}", f"ac {i}", f"ac{i}"]:
            n = n.replace(org, f"access{i}")
            if verbose:
                print(f"n={n}")
    for seq in ["1234", "234", "123", "34", "23", "12"]:
        org = "access" + seq
        dst = "a" + "a".join(seq)
        n = n.replace(org, dst)
        if verbose:
            print(f"n={n}")
    for i in range(1, 5):
        n = n.replace(f"access{i}", f"a{i}")
        if verbose:
            print(f"n={n}")
    if n.find("access") != -1:
        if any([(f"a{i}" in n) for i in range(1, 5)]):
            n = n.replace("access", "")
        else:
            n = n.replace("access", "a1a2a3a4")
    if verbose:
        print(f"n={n}")
    if n.find(" sauf ") != -1:
       n = n[:n.find(" sauf ")]
    n = n.replace(" ", "")
    if verbose:
        print(f"n={n}")
    start, end = len(n), 0
    for s in ["a1", "a2", "a3", "a4"]:
        start = min(start, n.find(s)) if n.find(s) != -1 else start
        end = max(end, n.find(s) + 1)
    n = n[start: end + 1]
    if verbose:
        print(f"n={n}")
    for i in categories.keys():
        categories[i] = n.find(f"a{i}") != -1
    return categories


def count_nb_access_subcategories_from_name(name: str) -> int:
    return sum(
        [int(v) for v in find_access_categories_from_name(name.strip()).values()]
    )


def has_access_subcategories(name: str) -> bool:
    return count_nb_access_subcategories_from_name(name) >= 1


def get_higher_access_subcategory(name: str) -> int:
    return [k for k, v in find_access_categories_from_name(name.strip()).items() if v][0]


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


def to_optional_int(value: Any) -> int | None:
    """Convert a pandas scalar to int, mapping missing values (None, NaN, pd.NA) to None."""
    return None if pd.isna(value) else int(value)


def search_rider_category(
        races: pd.DataFrame,
        rankings: pd.DataFrame,
        categories_from_startlists: pd.DataFrame,
        after: str | None = None
    ) -> pd.DataFrame:

    def forward_search(df_rider: pd.DataFrame) -> pd.DataFrame:

        rider_hc_prev, rider_lc_prev = 100, -100
        first_index = df_rider.index[0]
        rider_hc_next, rider_lc_next = None, None
        for row in df_rider.itertuples():
            i = row.Index
            event = ""
            if not isinstance(row.race_hc, int) or not isinstance(row.race_lc, int):
                raise TypeError("Invalid types for categories")
            race_hc, race_lc = row.race_hc, row.race_lc
            if (not isinstance(row.race_hc, int)) and (row.finish_rank is not None):
                raise TypeError("Invalid types for finish rank")
            finish_rank = row.finish_rank

            # Default case: keep category range
            rider_hc = rider_hc_prev
            rider_lc = rider_lc_prev
            if (rider_hc_next is not None) and (rider_lc_next is not None):
                rider_hc, rider_lc = rider_hc_next, rider_lc_next
                rider_hc_prev, rider_lc_prev = rider_hc_next, rider_lc_next
                rider_hc_next, rider_lc_next = None, None

            # Change of category
            # ---- category upgrade
            if race_lc < rider_hc_prev:
                rider_hc, rider_lc = race_hc, race_lc
            elif race_hc < rider_hc and finish_rank == 1:
                rider_hc_next, rider_lc_next = race_hc, race_hc
            # ---- category downgrade
            elif race_hc > rider_lc_prev:
                rider_hc, rider_lc = race_hc, race_lc

            # Reduce category range
            if race_hc > rider_hc_prev:
                rider_hc = race_hc
                event += "↓HC, "
            if race_lc < rider_lc_prev:
                rider_lc = race_lc
                event += "↑LC, "

            if rider_lc < rider_hc_prev:
                event += "↑cat, "
            if rider_hc > rider_lc_prev:
                event += "↓cat, "

            df_rider.loc[i, "rider_hc"] = rider_hc
            df_rider.loc[i, "rider_lc"] = rider_lc
            if i == first_index:
                event = ""
            df_rider.loc[i, "event"] = event.strip(", ")
            if rider_hc == rider_lc:
                df_rider.loc[i, "rider_category"] = rider_hc

            rider_hc_prev, rider_lc_prev = rider_hc, rider_lc

        return df_rider

    def propagation(
            mode: Literal["forward", "backward"],
            df_rider: pd.DataFrame,
            step: int
        ) -> pd.DataFrame:

        last_known_category = None
        direction = 1 if mode == "forward" else -1

        for row in df_rider.iloc[::direction].itertuples():
            i = row.Index
            category = to_optional_int(row.rider_category)
            if category is not None:
                if isinstance(category, int):
                    last_known_category = category
                else:
                    raise TypeError("rider_category must be an integer")
                continue
            if last_known_category is None:
                continue
            if not isinstance(row.rider_hc, int) or not isinstance(row.rider_lc, int):
                raise TypeError("rider_hc and rider_lc must be integers")
            rider_hc, rider_lc = row.rider_hc, row.rider_lc
            if rider_hc <= last_known_category <= rider_lc:
                filled_category = last_known_category
            elif last_known_category < rider_hc:
                filled_category = rider_hc
            elif last_known_category > rider_lc:
                filled_category = rider_lc
            else:
                continue
            df_rider.at[i, "rider_category"] = filled_category
            df_rider.at[i, "event"] = f"{row.event}, FWP({step})".strip(", ")
            last_known_category = filled_category
        return df_rider

    def backward_propagation(df_rider: pd.DataFrame, step: int) -> pd.DataFrame:
        return propagation(mode="backward", df_rider=df_rider, step=step)

    def forward_propagation(df_rider: pd.DataFrame, step: int) -> pd.DataFrame:
        return propagation(mode="forward", df_rider=df_rider, step=step)


    categories_from_startlists = categories_from_startlists.rename(columns={"category": "categories"})
    categories_from_startlists["finish_rank"] = None
    categories_from_startlists["race_date"] = pd.to_datetime(categories_from_startlists["race_date"], format="%Y-%m-%d")

    categories_from_results = rankings.merge(races, on="race_id")[["rider_id", "categories", "race_date", "finish_rank"]]
    categories_from_results["race_date"] = pd.to_datetime(categories_from_results["race_date"], format="%Y-%m-%d")

    df = pd.concat([categories_from_startlists, categories_from_results], ignore_index=True)
    if after is None:
        after = pd.to_datetime("2023-01-01", format="%Y-%m-%d")
    else:
        try:
            after = pd.to_datetime(after, format="%Y-%m-%d")
        except ValueError as e:
            raise e
    df = df[df["race_date"] >= pd.Timestamp(after)]
    df = df.sort_values(by=["rider_id", "race_date", "finish_rank"], na_position="first").reset_index(drop=True)

    df["race_hc"] = df["categories"].str.replace("A", "").str.split(",").str[0].astype(int)
    df["race_lc"] = df["categories"].str.replace("A", "").str.split(",").str[-1].astype(int)
    df["rider_hc"] = 100
    df["rider_lc"] = -100
    df["rider_category"] = None
    df["event"] = ""

    rider_ids = sorted(list(set(df["rider_id"].to_list())))

    for rider_id in rider_ids:
        mask = df["rider_id"] == rider_id
        df_rider = df[mask]

        df_rider = forward_search(df_rider)
        df_rider = backward_propagation(df_rider, step=1)

        # For the remaining undefined categories:
        # If all rows have an undefined category, then
        # - riders limited to A1-A2 are assigned to A1,
        # - riders limited to A3-A4 are assigned to A3,
        # - and the remaining riders are assigned to A1.
        # If only a part of the rows has an undefined category, then A1 is assigned.
        missing_categories = df_rider["rider_category"].isna()
        if missing_categories.all():
            mask_a1a2 = df_rider["rider_lc"] <= 2
            mask_a3a4 = df_rider["rider_hc"] >= 3
            mask_remaining = ~mask_a1a2 & ~mask_a3a4
            df_rider.loc[mask_a1a2, "rider_category"] = 1
            df_rider.loc[mask_a1a2, "event"] += ", ForceA1(A1-A2):all missing"
            df_rider.loc[mask_a3a4, "rider_category"] = 3
            df_rider.loc[mask_a3a4, "event"] += ", ForceA3(A3-A4):all missing"
            df_rider.loc[mask_remaining, "rider_category"] = 1
            df_rider.loc[mask_remaining, "event"] += ", ForceA1(others):all missing"
            df_rider.loc[:, "event"] = df_rider.loc[:, "event"].str.strip(", ")
        else:
            df_rider.loc[missing_categories, "rider_category"] = 1
            df_rider.loc[missing_categories, "event"] += ", ForceA1:some missing"

        df_rider = forward_propagation(df_rider, step=1)
        df_rider = backward_propagation(df_rider, step=2)

        df[mask] = df_rider
    return df.loc[:, ["rider_id", "race_date", "rider_category"]].reset_index(drop=True)


def compute_category_history(category_at_given_times: pd.DataFrame) -> pd.DataFrame:
    """Compute rider category history, that is the aggregated data,
    taking as input a DataFrame with columns rider_id, race_date, rider_category,
    and returning a DataFrame with columns rider_id, start_date, rider_category."""

    df = category_at_given_times.copy()
    df["race_date"] = pd.to_datetime(df["race_date"])
    df = df.sort_values(["rider_id", "race_date"])
    rider_ids = list(set(df["rider_id"].to_list()))
    category_history_tmp: list[dict] = []
    for rider_id in rider_ids:
        df_rider = df.loc[df["rider_id"] == rider_id]
        # initializations
        first_index = df_rider.index[0]
        start_date_prev = df_rider.loc[first_index, "race_date"]
        category_prev = to_optional_int(df_rider.loc[first_index, "rider_category"])
        last_index = df_rider.index[-1]
        for row in df_rider.itertuples():
            race_date = row.race_date
            category = row.rider_category
            if category != category_prev:
                # Separation of the two tests is intended, since adding two lines can be needed.
                category_history_tmp.append(
                    {
                        "rider_id": rider_id,
                        "start_date": start_date_prev,
                        "rider_category": category_prev,
                    }
                )
                start_date_prev = race_date# + pd.Timedelta(days=1)
            if row.Index == last_index:
                category_history_tmp.append(
                    {
                        "rider_id": rider_id,
                        "start_date": start_date_prev,
                        "rider_category": category,
                    }
                )
            category_prev = category

    return (
        pd.DataFrame(category_history_tmp)
        .sort_values(by=["rider_id", "start_date"])
        .reset_index(drop=True)
    )


def advance_start_dates_in_category_history(category_history: pd.DataFrame) -> pd.DataFrame:
    df = category_history.copy()
    df["start_date"] = pd.to_datetime(df["start_date"])
    df = df.sort_values(["rider_id", "start_date"])
    rider_ids = list(set(df["rider_id"].to_list()))
    for rider_id in rider_ids:
        this_rider = df["rider_id"] == rider_id
        first_index = df[this_rider].index[0]
        year_prev_row = 0
        for row in df[this_rider].itertuples():
            if row.Index == first_index:
                year_prev_row = df.loc[first_index, "start_date"].year
                df.loc[first_index, "start_date"] = pd.to_datetime(arg=f"{year_prev_row}-01-01", format="%Y-%m-%d")
                continue
            year = df.at[row.Index, "start_date"].year
            if year > year_prev_row:
                df.loc[row.Index, "start_date"] = pd.to_datetime(arg=f"{year}-01-01", format="%Y-%m-%d")
                year_prev_row = year
    return df


def add_unknown_years_in_category_history(
        category_history: pd.DataFrame,
        races: pd.DataFrame,
        rankings: pd.DataFrame,
        categories_from_startlists: pd.DataFrame,
        after_year: int = 2023
    ) -> pd.DataFrame:

    this_year = datetime.now().year
    if after_year < 2023 or after_year > this_year:
        raise ValueError(
            "'after_year' must be greater than or equal to 2023"
            f" and less than or equal to {this_year}"
        )

    df = (
        category_history.copy()
        .sort_values(by=["rider_id", "start_date"])
        .reset_index(drop=True)
    )
    df["year"] = pd.to_datetime(df["start_date"], format="%Y-%m-%d").dt.year

    categories_from_startlists = categories_from_startlists[["rider_id", "race_date"]]
    categories_from_results = rankings.merge(races, on="race_id")[["rider_id", "race_date"]]
    known_dates = (
        pd.concat([categories_from_startlists, categories_from_results], ignore_index=True)
        .sort_values(by=["rider_id", "race_date"])
        .drop_duplicates()
        .reset_index(drop=True)
    )
    known_dates["year"] = pd.to_datetime(known_dates["race_date"], format="%Y-%m-%d").dt.year

    category_history_tmp: list[dict] = []

    rider_ids = list(set(df["rider_id"].to_list()))
    for rider_id in rider_ids:
        this_rider = df["rider_id"] == rider_id
        first_index = df[this_rider].index[0]
        first_year = df.loc[first_index, "start_date"].year
        last_known_category = df.loc[first_index, "rider_category"]
        if first_year > after_year:
            category_history_tmp.append(
                {
                    "rider_id": rider_id,
                    "start_date": pd.to_datetime(arg=f"{after_year}-01-01", format="%Y-%m-%d"),
                    "rider_category": None,
                }
            )
        years_in_known_dates = (
            known_dates
            .loc[known_dates["rider_id"] == rider_id, "year"]
            .dropna()
            .drop_duplicates()
            .sort_values(ignore_index=True)
            .to_list()
        )
        years_in_category_history = (
            df.loc[this_rider, "year"]
            .drop_duplicates()
            .sort_values(ignore_index=True)
            .to_list()
        )
        years = list[int](range(first_year, this_year + 1))
        missing_category_line_already_added = False
        for year in years:
            categories_this_year = (
                df[this_rider & (df["year"] == year)]
                .sort_values(by="start_date", ascending=False, ignore_index=True)
                ["rider_category"]
            )
            if len(categories_this_year) > 0:
                last_known_category_this_year = categories_this_year.iloc[0]
            else:
                last_known_category_this_year = None
            if last_known_category_this_year is not None:
                last_known_category = last_known_category_this_year
            if year in years_in_category_history:
                category_history_tmp.extend(
                    df[this_rider & (df["year"] == year)]
                    .loc[:, ["rider_id", "start_date", "rider_category"]]
                    .to_dict(orient="records")
                )
                missing_category_line_already_added = False
            else:
                if year in years_in_known_dates:
                    if missing_category_line_already_added:
                        category_history_tmp.append(
                            {
                                "rider_id": rider_id,
                                "start_date": pd.to_datetime(arg=f"{year}-01-01", format="%Y-%m-%d"),
                                "rider_category": last_known_category,
                            }
                        )
                        missing_category_line_already_added = False
                else:
                    if not missing_category_line_already_added:
                        category_history_tmp.append(
                            {
                                "rider_id": rider_id,
                                "start_date": pd.to_datetime(arg=f"{year}-01-01", format="%Y-%m-%d"),
                                "rider_category": None,
                            }
                        )
                        missing_category_line_already_added = True

    category_history = (
        pd.DataFrame(category_history_tmp)
        .sort_values(by=["rider_id", "start_date"])
        .reset_index(drop=True)
    )
    category_history["rider_category"] = category_history["rider_category"].astype("Int8")
    return category_history


def create_category_table(
    races: pd.DataFrame,
    rankings: pd.DataFrame,
    categories_from_startlists: pd.DataFrame
    ) -> pd.DataFrame:
    category_at_given_times = search_rider_category(
        races=races,
        rankings=rankings,
        categories_from_startlists=categories_from_startlists,
    )
    category_history = compute_category_history(category_at_given_times)
    category_history = advance_start_dates_in_category_history(category_history)
    category_history = add_unknown_years_in_category_history(
        category_history=category_history,
        races=races,
        rankings=rankings,
        categories_from_startlists=categories_from_startlists
    )
    return category_history
