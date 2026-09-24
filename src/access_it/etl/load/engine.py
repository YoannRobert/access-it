from functools import lru_cache
from sqlalchemy import create_engine, Engine
from access_it.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Create the engine on the first call, then return the same instance."""
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        echo=settings.sql_info,
    )
