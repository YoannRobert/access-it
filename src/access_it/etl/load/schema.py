"""Create or drop the database tables defined in models.py."""

import argparse

from sqlalchemy import Engine

from access_it.etl.load.engine import get_engine
from access_it.etl.load.models import Base


def create_tables(engine: Engine) -> None:
    """Create all missing tables; existing tables are left untouched."""
    Base.metadata.create_all(engine)


def drop_tables(engine: Engine) -> None:
    """Drop all tables defined in the models. All data is lost."""
    Base.metadata.drop_all(engine)


def reset_tables(engine: Engine) -> None:
    """Drop then recreate all tables within a single transaction."""
    with engine.begin() as connection:
        Base.metadata.drop_all(connection)
        Base.metadata.create_all(connection)


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage the database schema.")
    parser.add_argument("action", choices=["create", "drop", "reset"])
    args = parser.parse_args()

    actions = {"create": create_tables, "drop": drop_tables, "reset": reset_tables}
    engine = get_engine()
    actions[args.action](engine)

    database = engine.url.render_as_string(hide_password=True)
    print(f"'{args.action}' completed on {database}")


if __name__ == "__main__":
    main()
