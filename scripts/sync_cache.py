"""Synchronize the page cache with the S3 storage, keeping the 5 most recent archives.

pull: replace the page directories of the local cache by those of the most
recent archive of the bucket; the replaced directories are kept in pull_backup/.
push: upload an archive of the page directories of the local cache.

Usage, from the repository root: python scripts/sync_cache.py {pull,push}
"""

import argparse

from access_it.common.log import setup_logging
from access_it.config import get_settings
from access_it.export.cache_archive import PULL_BACKUP_DIR, pull_cache, push_cache


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Synchronize the page cache with the S3 storage.")
    parser.add_argument("action", choices=["pull", "push"], help="direction of the synchronization")
    return parser.parse_args()


def sync_cache(action: str) -> None:
    """Pull the most recent archive of the cache, or push a new one.

    Args:
        action: 'pull' or 'push'.
    """
    bucket = get_settings().s3_bucket
    if action == "pull":
        archive_name = pull_cache(bucket)
        print(f"Cache replaced by the archive {archive_name}.")
        print(f"Previous version of the cache kept in {PULL_BACKUP_DIR}.")
    else:
        s3_uri, deleted_keys = push_cache(bucket)
        print(f"Cache archive exported to {s3_uri} on the S3 bucket.")
        for deleted_key in deleted_keys:
            print(f"Cache archive {deleted_key} got deleted from the S3 bucket.")


if __name__ == "__main__":
    setup_logging()
    sync_cache(parse_args().action)
