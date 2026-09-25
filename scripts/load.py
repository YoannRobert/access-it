from access_it.etl.load.engine import get_engine
from access_it.etl.load.load import load_all
from access_it.etl.load.schema import create_tables


def load():
    engine = get_engine()
    create_tables(engine)
    load_all(engine)


if __name__ == "__main__":
    load()
