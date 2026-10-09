import pandas as pd

from access_it.common.text import normalize_string_and_fold_case, collapse_spaces
from access_it.etl.extract.constants import INDIVIDUAL_CLUB_ID, FOREIGN_CLUB_ID
from access_it.etl.transform.categories import (
    find_access_categories_from_name, count_nb_access_subcategories_from_name,
    has_access_subcategories, get_higher_access_subcategory
)
from access_it.etl.transform.clubs import identify_clubs
from access_it.etl.transform.parse import get_startlists_html_files, parse_startlists_from_organization_page
from access_it.etl.transform.riders import get_rider_id, get_rider_id_using_affiliations


CLUB_LONG_REFERENCES = [
    "cyc", "velo", "club", "klub", "sport", "guidon", "vtt",
    "olympic", "bike", "team", "roue", "pays", "individuel",
]
CLUB_SHORT_REFERENCES = [
    "uc", "vc", "ec", "us", "vs", "oc", "as", "uv",
    "c.c", "cs", "sc", "co", "cr", "cm", "ck",
]


def get_startlists_data() -> list[dict]:
    startlists_data = []
    for startlists_html_file in get_startlists_html_files():
        html = startlists_html_file.read_text()
        data = parse_startlists_from_organization_page(html)
        startlists_data.append(data)
    return startlists_data


def is_nationality_column(s: pd.Series, min_ratio=0.5) -> bool:
    """Return boolean indicating if the column looks like a nationality code
    (False if FR/FRA never appears)."""
    if s.empty:
        return False

    # Keep strings only (anything else becomes an empty string), then strip
    cleaned = s.map(lambda x: x.strip() if isinstance(x, str) else "")

    # No French code at all: not a nationality column
    if not cleaned.isin(["FR", "FRA"]).any():
        return False

    # 1 to 3 uppercase letters; empty strings never match
    is_nationality = cleaned.str.fullmatch(r"[A-Z]{2,3}")

    return is_nationality.mean() >= min_ratio


def has_enough_france_values(s: pd.Series, min_ratio: float=0.5) -> bool:
    """Return boolean indicating if the column has a ratio greater of equal to 'min_ratio'
    of 'France' values (the case is non-sensitive)."""
    if s.empty:
        return False
    cleaned = s.map(lambda x: x.strip().lower() if isinstance(x, str) else "")
    french_nationality = (cleaned == "france")
    return float(french_nationality.mean()) >= min_ratio


def is_main_category_column(s: pd.Series, min_ratio: float=0.001) -> float:
    """Return boolean indicating if the column has a ratio greater of equal to 'min_ratio'
    of values that look like a main category name (False if Access-like word never appears)."""
    if s.empty:
        return False
    cleaned = s.map(lambda x: x.strip() if isinstance(x, str) else "")
    access_like_names = ["a", "ac", "acc", "access"]
    access_count = cleaned.str.lower().isin(access_like_names).sum()
    return float(access_count / len(cleaned)) >= min_ratio


def is_gender_col(s: pd.Series) -> bool:
    """Return True if all values indicate a gender or are empty,
    with at least one value indicating a gender."""
    cleaned = s.map(lambda x: x.strip().upper() if isinstance(x, str) else "")
    gender_words = ["H", "M",  "F", "HOMME", "FEMME"]
    return cleaned.isin(gender_words + [""]).all() and cleaned.isin(gender_words).any()


def is_additional_young_rider_column(s: pd.Series) -> bool:
    """Return True if the non-missing values all start with something indicating a young rider category."""
    cleaned = s.dropna().map(lambda x: x.strip().upper())
    return cleaned.str.startswith(("U19", "U23", "J", "JUN", "JUNIOR", "E", "ESP", "ESPOIR")).all()


def compute_probability_of_club_column(s: pd.Series) -> float:
    """Return the ratio of the non-missing values that contain a substring indicating a club name"""
    s = s.copy().dropna().map(lambda x: x.strip().lower())
    ratio = s.map(
        lambda x: (
            any(x.find(c) != -1 for c in CLUB_LONG_REFERENCES)
            or any(x.find(f" {c}") != -1 for c in CLUB_SHORT_REFERENCES)
            or any(x.find(f"{c} ") != -1 for c in CLUB_SHORT_REFERENCES)
        )
    ).mean()
    return ratio


def identify_riders_on_startlist(
        df: pd.DataFrame,
        riders: pd.DataFrame,
        affiliations: pd.DataFrame
    ) -> pd.DataFrame:
    df = df.copy()
    rider_ids = []
    for row in df.itertuples():
        found_rider_id = False
        full_name = row.full_name
        club_id = row.club_id
        rider_id_out = None
        if not isinstance(full_name, str) or not isinstance(club_id, str):
            raise TypeError("'rider_full_name' and 'club_id' must be strings")

        # Classical research
        try:
            rider_id_possibilities = get_rider_id(
                db=riders,
                full_name=full_name,
                case_sensitive=False
            )
            if not isinstance(rider_id_possibilities, list):
                raise TypeError("'rider_id_possibilities' is not a list")
            rider_id_out = get_rider_id_using_affiliations(
                rider_ids=rider_id_possibilities,
                affiliations=affiliations,
                club_id=club_id
            )
            found_rider_id = True
        except ValueError:
            pass

        # Research in red-listed riders
        words = full_name.split()
        nb_words = len(words)
        i = 1
        while (not found_rider_id) and (i <= nb_words - 1):
            last_name = " ".join(words[0:i])
            first_name = words[i]
            try:
                rider_id_possibilities = get_rider_id(
                    db=riders,
                    uci_id="Liste Rouge",
                    last_name=last_name,
                    first_name=first_name,
                    case_sensitive=False,
                    output="all"
                )
                if not isinstance(rider_id_possibilities, list):
                    raise TypeError("get_rider_id returned a non-list value")
                rider_id_out = get_rider_id_using_affiliations(
                    rider_ids=rider_id_possibilities,
                    affiliations=affiliations,
                    club_id=club_id
                )
                found_rider_id = True
            except ValueError:
                pass
            i += 1

        # Broader research
        i = 1
        while (not found_rider_id) and (i <= nb_words - 1):
            last_name = " ".join(words[0:i])
            first_name = words[i]
            try:
                rider_id_possibilities = get_rider_id(
                    db=riders,
                    last_name=last_name,
                    first_name=first_name,
                    broader_search=True,
                    case_sensitive=False
                )
                if not isinstance(rider_id_possibilities, list):
                    raise TypeError("get_rider_id returned a non-list value")
                rider_id_out = get_rider_id_using_affiliations(
                    rider_ids=rider_id_possibilities,
                    affiliations=affiliations,
                    club_id=club_id
                )
                found_rider_id = True
            except ValueError:
                pass
            i += 1

        rider_ids.append(rider_id_out)
    df["rider_id"] = pd.Series(rider_ids, index=df.index)
    return df


def has_digits(s: pd.Series) -> bool:
    return s.str.contains(r"\d", na=False).any()


def identify_riders_categories_on_startlist(
        data: dict,
        clubs: pd.DataFrame,
        riders: pd.DataFrame,
        affiliations: pd.DataFrame,
        departemental_committees: pd.DataFrame,
        regional_committees: pd.DataFrame
    ) -> list[dict]:
    race_date = data["date"]
    young_labels = ["u7", "u9", "u11", "u13", "u15", "u17", "ecole"]
    women_labels = ["dames", "femmes"]
    possible_headers = [
        "rg", "rg.", "rang", "dos", "dos.", "dossard",
        "nom", "prénom",
        "club", "équipe", "equipe", "comite", "comité",
        "horaire", "horaire de départ", "horaires de départ", "heure de départ", "heure départ",
        "nat", "nationalité",
        "cat", "cat.", "caté", "catégorie",
    ]
    cat_col, club_col, date_col, rider_id_col, club_id_col, full_name_col = (
        "category", "club", "race_date", "rider_id", "club_id", "full_name"
    )
    categories_table_cols = [rider_id_col, date_col, cat_col]
    output = []
    for table_name, table_data in data["startlists"].items():
        n_table_name = normalize_string_and_fold_case(table_name)
        is_young_startlist = any([ref in n_table_name for ref in young_labels])
        is_women_startlist = any([n_table_name.startswith(ref) for ref in women_labels])
        if is_young_startlist or is_women_startlist:
            continue

        df0 = pd.DataFrame(table_data)
        cols = df0.columns.to_list()

        # Drop table headers
        first_row = df0.iloc[0]
        match_count = 0
        for col in cols:
            value = first_row.loc[col]
            if isinstance(value, str):
                value = value.lower().strip()
            for h in possible_headers:
                if h == value:
                    match_count += 1
        if match_count > 0:
            df0 = df0.drop(index=0)

        # Drop empty columns
        empty_columns = []
        for col in cols:
            if df0[col].isna().all():
                empty_columns.append(col)
        df0 = df0.drop(columns=empty_columns)
        cols = df0.columns.to_list()

        # Drop duplicated columns
        cols_to_remove = []
        for colA in cols:
            for colB in cols[cols.index(colA) + 1:]:
                if df0[colA].equals(df0[colB]):
                    cols_to_remove.append(colB)
        df0 = df0.drop(columns=cols_to_remove)
        cols = df0.columns.to_list()

        # Drop time columns
        time_columns = []
        for col in cols:
            if df0[col].str.contains(r"\d+\s*[:hH]\s*\d+", na=True).all():
                time_columns.append(col)
        df0 = df0.drop(columns=time_columns)
        cols = df0.columns.to_list()

        # Drop nationality columns
        nationality_columns = []
        for col in cols:
            if (
                    is_nationality_column(df0[col], min_ratio=0.5)
                    or has_enough_france_values(df0[col], min_ratio=0.5)
            ):
                nationality_columns.append(col)
        df0 = df0.drop(columns=nationality_columns)
        cols = df0.columns.to_list()

        # Drop first columns if they are all digits (i.e., start numbers)
        cols_to_drop = []
        i_col = 0
        while i_col < len(cols):
            col = cols[i_col]
            drop = df0[col].str.isdigit().all()
            if drop:
                cols_to_drop.append(col)
            else:
                break
            i_col += 1
        df0 = df0.drop(columns=cols_to_drop)
        cols = df0.columns.to_list()

        # Drop gender columns,
        gender_cols = [col for col in cols if is_gender_col(df0[col])]
        df0 = df0.drop(columns=gender_cols)
        cols = df0.columns.to_list()

        # Drop optional young rider columns
        young_rider_cols = [col for col in cols if is_additional_young_rider_column(df0[col])]
        df0 = df0.drop(columns=young_rider_cols)
        cols = df0.columns.to_list()

        # Drop numeric-only columns having non-missing values with more than one digit
        cols_to_drop = [
            col for col in cols
            if (
                    df0[col].dropna().str.isdigit().all()
                    and df0[col].dropna().str.len().max() > 1
            )
        ]
        df0 = df0.drop(columns=cols_to_drop)
        cols = df0.columns.to_list()

        # Identify categories
        # Check the startlist title: in case of a single-category startlist
        categories = find_access_categories_from_name(table_name)
        is_single_access_category = (sum([int(v) for v in categories.values()]) == 1)
        multiple_access_categories = (sum([int(v) for v in categories.values()]) > 1)
        excluded = any([ref in table_name.lower() for ref in ["open", "op ", "elite", "engag"]])
        is_single_access_category = is_single_access_category and not excluded
        multiple_access_categories = multiple_access_categories and not excluded
        category = None
        if is_single_access_category:
            category = [f"A{k}" for k, v in categories.items() if v][0]

        # Give up if there are not enough columns left
        if (
                # Three columns needed: rider ID, club name and category
                (category is None and len(cols) < 3)
                # Two columns needed: rider ID and club name
                or (category is not None and len(cols) < 2)
        ):
            continue

        # Among the remaining columns, if one column has digits for all its non-missing values,
        # then it indicated the Access subcategory.
        # The preceding column is taken as the one indicating the Access category
        # (or another category like Open or Elite).
        num_cat_col_candidates = []
        num_cat_col, previous_column = None, None
        for col in cols:
            s = df0[col].dropna()
            if s.str.isdigit().all() and s.str.len().max() == 1:
                num_cat_col_candidates.append(col)
        if len(num_cat_col_candidates) == 1:
            num_cat_col = num_cat_col_candidates[0]
            previous_column_index = cols.index(num_cat_col) - 1
            if previous_column_index >= 0:
                previous_column = cols[previous_column_index]

        if num_cat_col is not None and previous_column is not None:
            s_main_cat_col = df0[previous_column]
            s_num_cat_col = df0[num_cat_col]
            if is_main_category_column(s_main_cat_col, min_ratio=0.001):
                df0[cat_col] = s_main_cat_col.fillna("").astype(str).str.cat(
                    s_num_cat_col.fillna("").astype(str), sep=" "
                )
                df0 = df0.drop(columns=[previous_column, num_cat_col])
            else:
                if multiple_access_categories:
                    df0[cat_col] = s_num_cat_col.map(
                        lambda x: f"A{x.strip()}"
                        if isinstance(x, str)
                        else ""
                    )
                    df0 = df0.drop(columns=[num_cat_col])
        else:
            for col in cols:
                s = df0[col].map(
                    lambda x: normalize_string_and_fold_case(x.strip())
                    if isinstance(x, str)
                    else ""
                )
                # Exclude columns with values indicating a club name
                if s.map(
                        lambda x: any(
                            [v for v in CLUB_LONG_REFERENCES + CLUB_SHORT_REFERENCES if v in x]
                        )
                ).any():
                    continue
                access_subcategories_rate = s.map(has_access_subcategories).to_numpy().mean()
                if access_subcategories_rate > 0.001:
                    df0[cat_col] = df0[col]
                    df0 = df0.drop(columns=[col])
                    break
            if (not cat_col in df0.columns) and (category is not None):
                df0[cat_col] = category
        cols = df0.columns.to_list()

        # Give up if category column is not found
        if cat_col not in cols:
            continue

        # Remove non-Access riders
        access_riders = df0[cat_col].apply(
            lambda x: has_access_subcategories(x) if isinstance(x, str) else False
        )
        df0 = df0.loc[access_riders]
        df0[cat_col] = df0[cat_col].apply(
            lambda x: f"A{get_higher_access_subcategory(x)}"
            if count_nb_access_subcategories_from_name(x) == 1
            else None
        )
        df0 = df0.dropna(subset=[cat_col])

        # Give up if no Access riders left
        if len(df0) == 0:
            continue

        # Find the club column
        nb_riders = df0.shape[0]
        if nb_riders >= 10:
            crit_rate = 0.33
        elif nb_riders >= 3:
            crit_rate = 0.66
        else:  # Give up if there are less than 3 riders
            continue
        max_found_rate = -1
        max_rate_col = ""
        for col in cols:
            s = df0[col].dropna()
            if not isinstance(s, pd.Series):
                continue
            rate = compute_probability_of_club_column(s)
            if rate >= crit_rate and rate > max_found_rate:
                max_found_rate = rate
                max_rate_col = col
                df0[club_col] = df0[col].apply(lambda x: collapse_spaces(x) if isinstance(x, str) else x)
        if max_rate_col != "":
            df0 = df0.drop(columns=max_rate_col)
        cols = df0.columns.to_list()

        # Give up if no club column found
        if club_col not in cols:
            continue

        df0[club_id_col] = identify_clubs(df0[club_col], df_clubs=clubs)

        # Remove rows with missing club_id
        df0 = df0.dropna(subset=[club_id_col])
        # Remove club column
        df0 = df0.drop(columns=[club_col])

        # Remove clubs outside Bretagne and Pays de la Loire, individual and foreign riders
        br = regional_committees["name"] == "BRETAGNE"
        pdl = regional_committees["name"] == "PAYS DE LA LOIRE"
        br_id = regional_committees.loc[br, "regional_committee_id"].iloc[0]
        pdl_id = regional_committees.loc[pdl, "regional_committee_id"].iloc[0]
        df0 = (
            df0
            .merge(
                clubs[[club_id_col, "departemental_committee_id"]],
                on=club_id_col
            )
            .merge(
                departemental_committees[["departemental_committee_id", "regional_committee_id"]],
                on="departemental_committee_id"
            )
            .drop(columns=["departemental_committee_id"])
        )
        kept_clubs = df0["regional_committee_id"].isin([br_id, pdl_id])
        df0 = df0[kept_clubs].drop(columns=["regional_committee_id"])
        df0 = df0[
            (df0[club_id_col] != INDIVIDUAL_CLUB_ID)
            & (df0[club_id_col] != FOREIGN_CLUB_ID)
        ]
        cols = df0.columns.to_list()

        # Find column(s) that contain the riders' full name
        other_cols = [col for col in cols if col not in [club_id_col, cat_col]]
        if len(cols) == 3:
            remaining_col = other_cols[0]
            s = df0[remaining_col].copy()
            if not isinstance(s, pd.Series):
                continue
            if has_digits(s):
                s = s.str.replace(r"^\d+\s*", "", regex=True)  # remove leading digits (and following spaces)
                if has_digits(s):
                    continue
            df0 = df0.rename(columns={remaining_col: full_name_col})
            df0[full_name_col] = s
        elif len(cols) == 4:
            last_name_col, first_name_col = other_cols
            if has_digits(df0[last_name_col]) and has_digits(df0[first_name_col]):
                continue
            elif has_digits(df0[last_name_col]):
                df0[full_name_col] = df0[first_name_col].copy()
            elif has_digits(df0[first_name_col]):
                df0[full_name_col] = df0[last_name_col].copy()
            else:
                df0[full_name_col] = (
                    df0[last_name_col].fillna("").str.cat(
                        df0[first_name_col].fillna(""), sep=" "
                    )
                )
            df0 = df0.drop(columns=[last_name_col, first_name_col])
        else:  # Unexpected number of columns
            continue

        # Identify riders
        df0 = identify_riders_on_startlist(
            df=df0, riders=riders, affiliations=affiliations
        )
        identified_riders = df0[rider_id_col].notna()
        if identified_riders.any():
            df0[date_col] = race_date
            output.extend(
                df0.loc[identified_riders, categories_table_cols].to_dict(orient="records")
            )

    return output


def identify_riders_categories_on_startlists(
        clubs: pd.DataFrame,
        riders: pd.DataFrame,
        affiliations: pd.DataFrame,
        departemental_committees: pd.DataFrame,
        regional_committees: pd.DataFrame
    ):
    startlists_data = get_startlists_data()
    output = []
    for data in startlists_data:
        new_output = identify_riders_categories_on_startlist(
            data=data,
            clubs=clubs,
            riders=riders,
            affiliations=affiliations,
            departemental_committees=departemental_committees,
            regional_committees=regional_committees
        )
        output.extend(new_output)
    return pd.DataFrame(output).drop_duplicates(keep="first").reset_index(drop=True)
