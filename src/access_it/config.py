"""Application settings read from environment variables (and the .env file)."""

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

TRUE_VALUES = {"1", "true", "yes"}


@dataclass(frozen=True)
class Settings:
    """Immutable application settings."""

    database_url: str
    sql_info: bool = False


def _read_bool(name: str, default: bool = False) -> bool:
    """Read an environment variable as a boolean ('1', 'true', 'yes' are True)."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in TRUE_VALUES


@lru_cache
def get_settings() -> Settings:
    """Load the .env file once and return the application settings."""
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("Environment variable 'DATABASE_URL' is not set")
    return Settings(
        database_url=database_url,
        sql_info=_read_bool("SQL_INFO")
    )