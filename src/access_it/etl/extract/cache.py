import httpx
import json
import os
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_CACHE = Path.home() / ".access-it" / "cache"
CACHE_DIR = Path(os.getenv("ACCESS_IT_CACHE") or DEFAULT_CACHE)
RACES_PARQUET_FILE = DEFAULT_CACHE / "races.parquet"
REGCOM_PARQUET_FILE = DEFAULT_CACHE / "regional_committees.parquet"
DEPCOM_PARQUET_FILE = DEFAULT_CACHE / "departemental_committees.parquet"
CLUBS_PARQUET_FILE = DEFAULT_CACHE / "clubs.parquet"


def create_cache_dir() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_season_cache_dir(season: int) -> Path:
    return CACHE_DIR / f"{season:4d}"


def create_season_cache_dir(season: int) -> None:
    get_season_cache_dir(season).mkdir(parents=True, exist_ok=True)


def get_sidecar_file(season: int, code: str) -> Path:
    return get_season_cache_dir(season) / f"{code}.meta.json"


def sidecar_exists(s: int, c: str) -> bool:
    return get_sidecar_file(s, c).exists()


def write_sidecar_file(season: int, code: str, meta: dict) -> None:
    create_season_cache_dir(season)
    sidecar_file = get_sidecar_file(season, code)
    sidecar_file.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def read_sidecar_data(season: int, code: str):
    return json.loads(get_sidecar_file(season, code).read_text(encoding="utf-8"))


def get_html_file(season: int, code: str) -> Path:
    return get_season_cache_dir(season) / f"{code}.html"


def write_html_file(season: int, code: str, response: httpx.Response) -> None:
    create_season_cache_dir(season)
    html_file = get_html_file(season, code)
    tmp = html_file.with_suffix(".tmp")
    tmp.write_bytes(response.content)
    tmp.replace(html_file)


def read_html_file(season: int, code: str) -> str:
    meta = read_sidecar_data(season, code)
    encoding = meta["encoding"]
    return get_html_file(season, code).read_bytes().decode(encoding)


def write_sidecar_and_html_files(
        season: int,
        code: str,
        response: httpx.Response,
        kept: bool = False,
        force_404: bool = False
    ) -> None:
    kept = kept and not force_404
    meta = {
        "status": 404 if force_404 else response.status_code,
        "kept": kept,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "url": str(response.url),
        "encoding": response.encoding
    }
    write_sidecar_file(season, code, meta)
    if kept:
        write_html_file(season, code, response)


if __name__ == "__main__":
    create_season_cache_dir(2025)
