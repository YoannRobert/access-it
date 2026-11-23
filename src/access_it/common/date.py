"""Conversion of the French dates of the FFC result pages, and reading of the race date in the
title of a startlist page.
"""

from datetime import date as Date, timedelta

from access_it.common.text import collapse_spaces, normalize_string_and_fold_case

# French month names (lowercase) mapped to their two-digit number
MONTH_CONVERT = {
    "janvier": "01", "février": "02", "mars": "03",
    "avril": "04", "mai": "05", "juin": "06",
    "juillet": "07", "août": "08", "septembre": "09",
    "octobre": "10", "novembre": "11", "décembre": "12",
}


def convert_date(date: str | None) -> str | None:
    """Convert a French date of a result page into a 'YYYY-MM-DD' string.

    The weekday is dropped and the month name is replaced by its number
    (e.g. "Samedi 12 avril 2025" gives "2025-04-12"). The day is kept as
    written: the FFC pages always write it with two digits.

    Args:
        date: Date as written on the page ("<weekday> <day> <month> <year>"),
            or None.

    Returns:
        The date as 'YYYY-MM-DD', or None if `date` is None.
    """
    if date is None:
        return None
    date = date.lower().strip()
    if all([date.find(w) != -1 for w in ["du ", "au "]]):
        date = date.replace("du ", "").replace("au ", "")
        date = " ".join(date.split()[0:4])
    date = date.split(maxsplit=1)[1].replace(" ", "-")
    for month, num in MONTH_CONVERT.items():
        date = date.replace(month, num)
    day, month, year = date.split("-")
    date = f"{year}-{month}-{day}"
    return date


# A race takes place a few days after the publication of its startlist page:
# a date read in the title outside this window is considered wrong
MAX_DAYS_BEFORE_PUBLICATION = 7
MAX_DAYS_AFTER_PUBLICATION = 120


def is_day_number(word: str) -> bool:
    """Whether a word of a title is a day of the month ("1er" included)."""
    try:
        return 1 <= int(word.replace("1er", "1")) <= 31
    except ValueError:
        return False


def correct_startlist_date(title_date: str, publication_date: str) -> str:
    """Return the race date, corrected when the date read in the title is not plausible.

    The title date must lie between MAX_DAYS_BEFORE_PUBLICATION days before and
    MAX_DAYS_AFTER_PUBLICATION days after the publication date of the page.
    Otherwise (e.g. a typo in the year of the title), the day and month are
    kept with the year bringing the date into this window; if no year does,
    the publication date is returned. Dates are 'YYYY-MM-DD' strings.
    """
    publication = Date.fromisoformat(publication_date)
    window_start = publication - timedelta(days=MAX_DAYS_BEFORE_PUBLICATION)
    window_end = publication + timedelta(days=MAX_DAYS_AFTER_PUBLICATION)
    try:
        date = Date.fromisoformat(title_date)
    except ValueError:
        return publication_date
    if window_start <= date <= window_end:
        return title_date
    for year in (publication.year, publication.year + 1):
        try:
            candidate = date.replace(year=year)
        except ValueError:  # February 29th in a non-leap year
            continue
        if window_start <= candidate <= window_end:
            return candidate.isoformat()
    return publication_date


def parse_startlist_title(title: str, publication_date: str) -> tuple[str, str, str]:
    """Read the name and the race date in the title of a startlist page.

    The title reads "<name> <day> <month> <year> ...". The day is the first
    one of "<day> et <day>", otherwise the earliest of the numbers (1 to 31)
    preceding the month, so that a departement code ("Adainville 78 31 mai") is
    not taken as the day. The year follows the month, or the second month of
    "<month> et <day> <month> <year>". Without a month, or if the day or the
    year is not a number, the date read is the publication date. The date read
    is then checked against the publication date (see correct_startlist_date).

    Args:
        title: Title of the page.
        publication_date: Publication date of the page ('YYYY-MM-DD').

    Returns:
        The name (the title up to the day, or the whole title without date),
        the date read in the title and the race date after correction, both
        as 'YYYY-MM-DD' strings.
    """
    months_org = [m for m in list(MONTH_CONVERT.keys())]
    months = [normalize_string_and_fold_case(m) for m in months_org]
    words_org = collapse_spaces(title).split()
    words = [normalize_string_and_fold_case(w.replace(",", "")) for w in words_org]
    i = 0
    month = ""
    name = title
    while i < len(words):
        word = words[i]
        if word in months:
            month = MONTH_CONVERT[months_org[months.index(word)]]
            break
        i += 1
    if month == "":
        date = publication_date
    else:
        if words[i - 2] == "et":
            day = words[i - 3].replace("1er", "1").zfill(2)
            name = " ".join(words_org[: i - 3])
        else:
            # Walk back over the numbers preceding the month that can be days (1 to 31),
            # so that a number like a departement code ("Adainville 78 31 mai") is not
            # taken as the day; the earliest of them is the day ("1 2 mars": 1)
            j = 0
            while i - j - 1 >= 0 and is_day_number(words[i - j - 1]):
                j += 1
            # j == 0: no day before the month, words[i] is the month and int(day) fails below
            day = words[i - j].replace("1er", "1").zfill(2)
            name = " ".join(words_org[: i - j])
        if words[i + 1] == "et":
            year = words[i + 4]
        else:
            year = words[i + 1]
        try:
            int(year)
            int(day)
            date = f"{year:4s}-{month:2s}-{day:2s}"
        except ValueError:
            date = publication_date

    return name, date, correct_startlist_date(date, publication_date)
