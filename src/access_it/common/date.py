"""Conversion of the race dates written in French on the FFC result pages."""

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
