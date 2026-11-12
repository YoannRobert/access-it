"""Archive of the page cache on the S3 storage: upload (push) and download (pull).

Only the page directories of the cache are archived (CACHED_DIRS), in a tar.gz
archive whose keys follow CACHE_KEYS. The other directories of the cache (data,
snapshots) are never archived, and the pull leaves them untouched.
"""

from __future__ import annotations

import shutil
import tarfile
import tempfile

from pathlib import Path
from typing import TYPE_CHECKING

from access_it.etl.extract.cache import (
    CACHE_DIR, NATIONAL_RESULTS_DIR, RESULTS_DIR, STARTLISTS_DIR
)
from access_it.export.s3 import (
    KeyPattern, delete_old_keys, download_latest, get_s3_client, upload_to_s3
)

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


CACHE_KEYS = KeyPattern(prefix="cache", stem="cache", suffix=".tar.gz")
CACHED_DIRS = (RESULTS_DIR, NATIONAL_RESULTS_DIR, STARTLISTS_DIR)
PULL_BACKUP_DIR = CACHE_DIR / "pull_backup"
KEEP_ARCHIVES = 5


def build_cache_archive(archive_path: Path) -> Path:
    """Write the directories of CACHED_DIRS into a tar.gz archive, one top-level entry each.

    Raises:
        FileNotFoundError: If a directory of CACHED_DIRS does not exist.
    """
    missing = [directory.name for directory in CACHED_DIRS if not directory.is_dir()]
    if missing:
        raise FileNotFoundError(f"Cache directories not found: {', '.join(missing)}")
    with tarfile.open(archive_path, mode="w:gz") as tar:
        for directory in CACHED_DIRS:
            tar.add(directory, arcname=directory.name)
    return archive_path


def push_cache(bucket: str, client: S3Client | None = None) -> tuple[str, list[str]]:
    """Upload an archive of the cache to the S3 bucket, then delete the old archives.

    The archive is built in a temporary directory of CACHE_DIR, deleted afterwards.

    Args:
        bucket: Name of the bucket.
        client: S3 client (created from the settings if None).

    Returns:
        The S3 URI of the uploaded archive and the deleted keys.

    Raises:
        FileNotFoundError: If a directory of CACHED_DIRS does not exist (nothing is uploaded).
    """
    client = client or get_s3_client()
    with tempfile.TemporaryDirectory(dir=CACHE_DIR) as tmp_dir:
        archive_path = build_cache_archive(Path(tmp_dir) / "cache.tar.gz")
        key = CACHE_KEYS.build_key()
        s3_uri = upload_to_s3(archive_path, bucket=bucket, key=key, client=client)
    deleted_keys = delete_old_keys(bucket, CACHE_KEYS, keep=KEEP_ARCHIVES, client=client)
    return s3_uri, deleted_keys


def pull_cache(bucket: str, client: S3Client | None = None) -> str:
    """Replace the directories of CACHED_DIRS by those of the most recent archive of the bucket.

    The archive is downloaded and fully extracted in a temporary directory of
    CACHE_DIR first, so that a corrupted or incomplete archive leaves the local
    cache untouched. The replaced directories are then moved to PULL_BACKUP_DIR,
    whose previous content is deleted.

    Args:
        bucket: Name of the bucket.
        client: S3 client (created from the settings if None).

    Returns:
        The file name of the archive.

    Raises:
        FileNotFoundError: If the bucket holds no archive of the cache.
        ValueError: If the archive lacks a directory of CACHED_DIRS.
    """
    client = client or get_s3_client()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=CACHE_DIR) as tmp_dir:
        archive_path = download_latest(bucket, CACHE_KEYS, Path(tmp_dir), client=client)
        extract_dir = Path(tmp_dir) / "extracted"
        with tarfile.open(archive_path, mode="r:gz") as tar:
            tar.extractall(extract_dir, filter="data")
        missing = [d.name for d in CACHED_DIRS if not (extract_dir / d.name).is_dir()]
        if missing:
            raise ValueError(
                f"Directories missing from the archive {archive_path.name}: {', '.join(missing)}"
            )

        shutil.rmtree(PULL_BACKUP_DIR, ignore_errors=True)
        PULL_BACKUP_DIR.mkdir()
        for directory in CACHED_DIRS:
            if directory.exists():
                directory.rename(PULL_BACKUP_DIR / directory.name)
            (extract_dir / directory.name).rename(directory)
    return archive_path.name
