"""Reading of the Access categories (Access 1 to 4) in race, ranking and startlist names.

Shared by the extract step (selection of the startlist pages) and the
transform step (categories of the races and riders).
"""

import logging
import re

from functools import lru_cache

from access_it.common.text import normalize_string_and_fold_case

logger = logging.getLogger(__name__)


def find_access_categories_from_name(name: str, verbose: bool = False) -> dict[int, bool]:
    """Return, for each Access subcategory (1 to 4), whether it appears in `name`.

    Usual notations and spelling mistakes are recognized; "Access" alone means
    all the subcategories, and the text after "sauf" (riders excluded) is
    ignored. Results are cached (the same labels are parsed many times); a new
    dict is returned at every call, so that callers can modify it.

    Args:
        name: Race title, ranking name or startlist name.
        verbose: Whether to log (level INFO) each normalization step (not cached).

    Returns:
        A dict {1: bool, 2: bool, 3: bool, 4: bool}.

    Examples:
        >>> find_access_categories_from_name("ACCESS 3/4 SAUF FEMMES")
        {1: False, 2: False, 3: True, 4: True}
        >>> find_access_categories_from_name("Acc 1 et 2")
        {1: True, 2: True, 3: False, 4: False}
    """
    if verbose:
        return _compute_access_categories_from_name(name, verbose=True)
    return dict(zip(range(1, 5), _cached_access_categories_from_name(name)))


@lru_cache(maxsize=None)
def _cached_access_categories_from_name(name: str) -> tuple[bool, ...]:
    """Cached categories of a name, as a tuple (see find_access_categories_from_name)."""
    return tuple(_compute_access_categories_from_name(name).values())


def _compute_access_categories_from_name(name: str, verbose: bool = False) -> dict[int, bool]:
    """Read the Access categories in a name (see find_access_categories_from_name).

    The name is normalized (case, accents, spelling mistakes, separators such as
    "1-2", "3/4" or "1 et 2"), then every category is written "a<i>" and the
    categories between the first and the last "a<i>" found are read.
    """
    categories = {k: False for k in range(1, 5)}
    if verbose:
        logger.info(f"name={name}")
    n = normalize_string_and_fold_case(name)  # lowering the case and removing accentuation
    if verbose:
        logger.info(f"n={n}")
    n = n.replace("accc", "acc")  # correcting spelling mistakes
    if verbose:
        logger.info(f"n={n}")
    for org in ["acess", "acces", "accesss"]:
        n = n.replace(org, "access")
        if verbose:
            logger.info(f"n={n}")
    n = re.sub(r"[^A-Za-z0-9 ]", "", n)  # keeping only letters and figures
    if verbose:
        logger.info(f"n={n}")
    n = n.replace(" et ", "")
    if verbose:
        logger.info(f"n={n}")
    n = re.sub(r" {2,}", " ", n)  # removing extra spaces
    if verbose:
        logger.info(f"n={n}")
    n = re.sub(r"^\d+(?=.*[a-zA-Z])", "", n)  # removing leading figures, only if letters follow
    if verbose:
        logger.info(f"n={n}")
    for i in range(1, 4):
        for sep in [" ", "-", "+", "/"]:
            if verbose:
                old = f"{i}{sep}{i+1}"
                new = f"{i}{i+1}"
                logger.info(f"{old} -> {new}")
            n = n.replace(f"{i}{sep}{i+1}", f"{i}{i+1}")
            if verbose:
                logger.info(f"n={n}")
    for i in range(1, 5):
        for org in [f"access {i}", f"acc {i}", f"acc{i}", f"ac {i}", f"ac{i}"]:
            n = n.replace(org, f"access{i}")
            if verbose:
                logger.info(f"n={n}")
    for seq in ["1234", "234", "123", "34", "23", "12"]:
        org = "access" + seq
        dst = "a" + "a".join(seq)
        n = n.replace(org, dst)
        if verbose:
            logger.info(f"n={n}")
    for i in range(1, 5):
        n = n.replace(f"access{i}", f"a{i}")
        if verbose:
            logger.info(f"n={n}")
    if n.find("access") != -1:
        if any([(f"a{i}" in n) for i in range(1, 5)]):
            n = n.replace("access", "")
        else:
            n = n.replace("access", "a1a2a3a4")
    if verbose:
        logger.info(f"n={n}")
    if n.find(" sauf ") != -1:
       n = n[:n.find(" sauf ")]
    n = n.replace(" ", "")
    if verbose:
        logger.info(f"n={n}")
    start, end = len(n), 0
    for s in ["a1", "a2", "a3", "a4"]:
        start = min(start, n.find(s)) if n.find(s) != -1 else start
        end = max(end, n.find(s) + 1)
    n = n[start: end + 1]
    if verbose:
        logger.info(f"n={n}")
    for i in categories.keys():
        categories[i] = n.find(f"a{i}") != -1
    return categories


# Women's words, in normalized names
WOMEN_PATTERN = re.compile(r"\b(femmes?|dames?|feminin(?:e|es|s)?|filles?|cadettes?|juniores?)\b")


def is_women_only_name(name: str) -> bool:
    """Whether a ranking or startlist name designates women only.

    The name is normalized (case, accents, "+", "," and "&" read as "et", any
    other character than a letter or a figure replaced by a space). The text
    after "sauf" (riders excluded) and the place names "Notre-Dame" are
    ignored. A women's word next to "et" belongs to an enumeration of several
    groups of riders (mixed race) and does not count.

    Args:
        name: Ranking name or startlist name.

    Returns:
        True if a women's word is found outside an enumeration.

    Examples:
        >>> is_women_only_name("C4356009100 : BIGNAN - ACCESS Dames")
        True
        >>> is_women_only_name("ACCESS 3.4 ET FEMMES")
        False
        >>> is_women_only_name("POMMERIEUX - ACCESS 3/4 SAUF FEMMES")
        False
    """
    n = re.sub(r"[+,&]", " et ", normalize_string_and_fold_case(name))
    n = " ".join(re.sub(r"[^a-z0-9]", " ", n).split())
    n = re.split(r"\bsauf\b", n, maxsplit=1)[0]
    words = re.sub(r"\bnotre dame\b", " ", n).split()
    for i, word in enumerate(words):
        if WOMEN_PATTERN.fullmatch(word) is None:
            continue
        neighbors = words[max(i - 1, 0): i] + words[i + 1: i + 2]
        if "et" not in neighbors:
            return True
    return False


def count_nb_access_subcategories_from_name(name: str) -> int:
    """Number of Access categories found in the name."""
    return sum(
        [int(v) for v in find_access_categories_from_name(name.strip()).values()]
    )


def has_access_subcategories(name: str) -> bool:
    """Whether at least one Access category is found in the name."""
    return count_nb_access_subcategories_from_name(name) >= 1


def get_higher_access_subcategory(name: str) -> int:
    """Highest Access category found in the name (the smallest number, e.g. 3 for "Access 3/4").

    Raises:
        IndexError: If no Access category is found.
    """
    return [k for k, v in find_access_categories_from_name(name.strip()).items() if v][0]
