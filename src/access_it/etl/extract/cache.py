"""Local cache of the extract step: raw pages and Parquet files.

Each requested result or startlist page is recorded by a sidecar JSON file
(status, kept or not, request date, URL, encoding), next to the HTML file of
the pages kept. The cache directory is ~/.access-it/cache by default, or the
ACCESS_IT_CACHE environment variable.

The result pages of Bretagne and Pays de la Loire are cached in RESULTS_DIR.
The result pages of the other regions, only used to find the committee of the
individual licensees, are cached apart in NATIONAL_RESULTS_DIR. The functions
of the result pages take this directory as an optional argument (RESULTS_DIR
by default).
"""

import httpx
import json
import os

from datetime import datetime, timezone
from pathlib import Path


DEFAULT_CACHE = Path.home() / ".access-it" / "cache"
CACHE_DIR = Path(os.getenv("ACCESS_IT_CACHE") or DEFAULT_CACHE)

RESULTS_DIR = CACHE_DIR / "results"
NATIONAL_RESULTS_DIR = CACHE_DIR / "results_national"
STARTLISTS_DIR = CACHE_DIR / "startlists"
DATA_DIR = CACHE_DIR / "data"
SNAPSHOTS_DIR = CACHE_DIR / "snapshots"

RACES_PARQUET_FILE = DATA_DIR / "races.parquet"
REGCOM_PARQUET_FILE = DATA_DIR / "regional_committees.parquet"
DEPCOM_PARQUET_FILE = DATA_DIR / "departemental_committees.parquet"
DEPARTEMENTS_PARQUET_FILE = DATA_DIR / "departements.parquet"
CLUBS_PARQUET_FILE = DATA_DIR / "clubs.parquet"
RIDERS_PARQUET_FILE = DATA_DIR / "riders.parquet"
AFFILIATIONS_PARQUET_FILE = DATA_DIR / "affiliations.parquet"
RANKINGS_PARQUET_FILE = DATA_DIR / "rankings.parquet"
RIDER_CATEGORIES_PARQUET_FILE = DATA_DIR / "rider_categories.parquet"


def create_cache_dir() -> None:
    """Create the cache directories if they do not exist."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    NATIONAL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    STARTLISTS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def get_season_results_cache_dir(season: int, results_dir: Path | None = None) -> Path:
    """Directory of the cached result pages of a season (in RESULTS_DIR by default)."""
    return (results_dir or RESULTS_DIR) / f"{season:4d}"


def create_season_results_cache_dir(season: int, results_dir: Path | None = None) -> None:
    """Create the directory of the cached result pages of a season."""
    get_season_results_cache_dir(season, results_dir).mkdir(parents=True, exist_ok=True)


def get_results_sidecar_file(season: int, code: str, results_dir: Path | None = None) -> Path:
    """Sidecar JSON file of a result page."""
    return get_season_results_cache_dir(season, results_dir) / f"{code}.meta.json"


def results_sidecar_exists(s: int, c: str, results_dir: Path | None = None) -> bool:
    """Whether the result page of season `s` and code `c` was already requested."""
    return get_results_sidecar_file(s, c, results_dir).exists()


def write_results_sidecar_file(
        season: int,
        code: str,
        meta: dict,
        results_dir: Path | None = None
    ) -> None:
    """Write the sidecar JSON file of a result page."""
    create_season_results_cache_dir(season, results_dir)
    sidecar_file = get_results_sidecar_file(season, code, results_dir)
    sidecar_file.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def read_results_sidecar_data(season: int, code: str, results_dir: Path | None = None):
    """Read the sidecar JSON file of a result page."""
    return json.loads(get_results_sidecar_file(season, code, results_dir).read_text(encoding="utf-8"))


def get_results_html_file(season: int, code: str, results_dir: Path | None = None) -> Path:
    """HTML file of a kept result page."""
    return get_season_results_cache_dir(season, results_dir) / f"{code}.html"


def write_results_html_file(
        season: int,
        code: str,
        response: httpx.Response,
        results_dir: Path | None = None
    ) -> None:
    """Write the HTML file of a result page (atomically, through a temporary file)."""
    create_season_results_cache_dir(season, results_dir)
    html_file = get_results_html_file(season, code, results_dir)
    tmp = html_file.with_suffix(".tmp")
    tmp.write_bytes(response.content)
    tmp.replace(html_file)


def read_results_html_file(season: int, code: str, results_dir: Path | None = None) -> str:
    """Read the HTML file of a kept result page, decoded with the encoding of its sidecar."""
    meta = read_results_sidecar_data(season, code, results_dir)
    encoding = meta["encoding"]
    return get_results_html_file(season, code, results_dir).read_bytes().decode(encoding)


def write_results_sidecar_and_html_files(
        season: int,
        code: str,
        response: httpx.Response,
        kept: bool = False,
        force_404: bool = False,
        results_dir: Path | None = None
    ) -> None:
    """Cache a requested result page: its sidecar file, and its HTML file if kept.

    Args:
        season: Season of the page.
        code: Organization code of the page (e.g. 'C4400001001').
        response: Response to the request of the page.
        kept: Whether the page is a race in the scope of the project.
        force_404: Whether to record the page as not found (status 404, not
            kept), e.g. when the request was redirected to the error page.
        results_dir: Cache directory of the result pages (default: RESULTS_DIR).
    """
    kept = kept and not force_404
    meta = {
        "status": 404 if force_404 else response.status_code,
        "kept": kept,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "url": str(response.url),
        "encoding": response.encoding
    }
    write_results_sidecar_file(season, code, meta, results_dir)
    if kept:
        write_results_html_file(season, code, response, results_dir)


def get_season_startlists_cache_dir(season: int) -> Path:
    """Directory of the cached startlist pages of a season."""
    return STARTLISTS_DIR / f"{season:4d}"


def create_season_startlists_cache_dir(season: int) -> None:
    """Create the directory of the cached startlist pages of a season."""
    get_season_startlists_cache_dir(season).mkdir(parents=True, exist_ok=True)


def get_startlists_json_file(season: int, code: str) -> Path:
    """Sidecar JSON file of a startlist page."""
    return get_season_startlists_cache_dir(season) / f"{code}.meta.json"


def startlists_json_file_exists(s: int, c: str) -> bool:
    """Whether the startlist page of season `s` and code `c` was already requested."""
    return get_startlists_json_file(s, c).exists()


def write_startlists_json_file(season: int, code: str, meta: dict) -> None:
    """Write the sidecar JSON file of a startlist page."""
    create_season_startlists_cache_dir(season)
    sidecar_file = get_startlists_json_file(season, code)
    sidecar_file.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def get_startlists_html_file(season: int, code: str) -> Path:
    """HTML file of a kept startlist page."""
    return get_season_startlists_cache_dir(season) / f"{code}.html"


def write_startlists_html_file(season: int, code: str, response: httpx.Response) -> None:
    """Write the HTML file of a startlist page (atomically, through a temporary file)."""
    create_season_startlists_cache_dir(season)
    html_file = get_startlists_html_file(season, code)
    tmp = html_file.with_suffix(".tmp")
    tmp.write_bytes(response.content)
    tmp.replace(html_file)


def write_startlists_json_and_html_files(
        season: int,
        code: str,
        response: httpx.Response,
        kept: bool = False,
        force_404: bool = False
    ) -> None:
    """Cache a requested startlist page: its sidecar file, and its HTML file if kept.

    Args:
        season: Season of the page.
        code: Identifier of the page on the startlists website.
        response: Response to the request of the page.
        kept: Whether the page holds Access startlists.
        force_404: Whether to record the page as not found (status 404, not kept).
    """
    kept = kept and not force_404
    meta = {
        "status": 404 if force_404 else response.status_code,
        "kept": kept,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "url": str(response.url),
        "encoding": response.encoding
    }
    write_startlists_json_file(season, code, meta)
    if kept:
        write_startlists_html_file(season, code, response)
