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
    aws_endpoint_url_s3: str
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_region: str
    s3_bucket: str
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
    aws_endpoint_url_s3 = os.getenv("AWS_ENDPOINT_URL_S3")
    aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    aws_region = os.getenv("AWS_REGION")
    s3_bucket = os.getenv("S3_BUCKET")
    if not database_url:
        raise RuntimeError("Environment variable 'DATABASE_URL' is not set")
    if not aws_endpoint_url_s3:
        raise RuntimeError("Environment variable 'AWS_ENDPOINT_URL_S3' is not set")
    if not aws_access_key_id:
        raise RuntimeError("Environment variable 'AWS_ACCESS_KEY_ID' is not set")
    if not aws_secret_access_key:
        raise RuntimeError("Environment variable 'AWS_SECRET_ACCESS_KEY' is not set")
    if not aws_region:
        raise RuntimeError("Environment variable 'AWS_REGION' is not set")
    if not s3_bucket:
        raise RuntimeError("Environment variable 'S3_BUCKET' is not set")
    return Settings(
        database_url=database_url,
        sql_info=_read_bool("SQL_INFO"),
        aws_endpoint_url_s3=aws_endpoint_url_s3,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        aws_region=aws_region,
        s3_bucket=s3_bucket,
    )