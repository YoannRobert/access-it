MONTH_CONVERT = {
    "janvier": "01", "février": "02", "mars": "03",
    "avril": "04", "mai": "05", "juin": "06",
    "juillet": "07", "août": "08", "septembre": "09",
    "octobre": "10", "novembre": "11", "décembre": "12",
}


def convert_date(date: str | None) -> str | None:
    if date is None:
        return None
    date = date.split(maxsplit=1)[1].replace(" ", "-")
    for month, num in MONTH_CONVERT.items():
        date = date.replace(month, num)
    day, month, year = date.split("-")
    date = f"{year}-{month}-{day}"
    return date
