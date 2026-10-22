"""Run the whole ETL: extract, transform, then load.

Usage, from the repository root: python scripts/etl.py
"""

from access_it.common.log import setup_logging
from extract import extract
from transform import transform
from load import load


def etl():
    """Run the extract, transform and load steps, in this order."""
    extract()
    transform()
    load()


if __name__ == "__main__":
    setup_logging()
    etl()
