"""Unit tests of the archive of the page cache, with a fake S3 client and a temporary cache."""

import tarfile

from pathlib import Path

import pytest

from access_it.export import cache_archive
from access_it.export.cache_archive import CACHE_KEYS, pull_cache, push_cache

DIR_NAMES = ("results", "results_national", "startlists")


class FakeS3Client:
    """Bucket storing the content of the uploaded files, by key."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def upload_file(self, Filename: str, Bucket: str, Key: str) -> None:
        self.objects[Key] = Path(Filename).read_bytes()

    def get_paginator(self, name: str):
        keys = list(self.objects)

        class Paginator:
            def paginate(self, Bucket: str, Prefix: str):
                yield {"Contents": [{"Key": key} for key in keys if key.startswith(Prefix)]}

        return Paginator()

    def download_file(self, Bucket: str, Key: str, Filename: str) -> None:
        Path(Filename).write_bytes(self.objects[Key])

    def delete_objects(self, Bucket: str, Delete: dict) -> dict:
        for obj in Delete["Objects"]:
            del self.objects[obj["Key"]]
        return {}


@pytest.fixture
def cache_dir(tmp_path, monkeypatch) -> Path:
    """Temporary cache holding one page per archived directory, plus data and snapshots."""
    cache = tmp_path / "cache"
    for name in (*DIR_NAMES, "data", "snapshots"):
        (cache / name).mkdir(parents=True)
        (cache / name / "page.html").write_text(f"local {name}")
    monkeypatch.setattr(cache_archive, "CACHE_DIR", cache)
    monkeypatch.setattr(cache_archive, "CACHED_DIRS", tuple(cache / name for name in DIR_NAMES))
    monkeypatch.setattr(cache_archive, "PULL_BACKUP_DIR", cache / "pull_backup")
    return cache


def test_push_uploads_the_page_directories_only(cache_dir, tmp_path):
    client = FakeS3Client()
    s3_uri, deleted_keys = push_cache("bucket", client=client)
    [key] = client.objects
    assert s3_uri == f"s3://bucket/{key}"
    assert CACHE_KEYS.parse_timestamp(key) is not None
    assert deleted_keys == []
    archive_path = tmp_path / "archive.tar.gz"
    archive_path.write_bytes(client.objects[key])
    with tarfile.open(archive_path) as tar:
        assert {Path(name).parts[0] for name in tar.getnames()} == set(DIR_NAMES)
    assert [path.name for path in cache_dir.iterdir() if path.name.startswith("tmp")] == []


def test_push_keeps_the_most_recent_archives(cache_dir):
    client = FakeS3Client()
    old_keys = [f"cache/cache_202610{day:02d}T080000Z.tar.gz" for day in range(1, 6)]
    client.objects = {key: b"" for key in old_keys}
    _, deleted_keys = push_cache("bucket", client=client)
    assert deleted_keys == [old_keys[0]]
    assert len(client.objects) == cache_archive.KEEP_ARCHIVES


def test_push_with_a_missing_directory_uploads_nothing(cache_dir):
    (cache_dir / "startlists" / "page.html").unlink()
    (cache_dir / "startlists").rmdir()
    client = FakeS3Client()
    with pytest.raises(FileNotFoundError, match="startlists"):
        push_cache("bucket", client=client)
    assert client.objects == {}


def test_pull_replaces_the_page_directories_and_keeps_the_previous_ones(cache_dir):
    client = FakeS3Client()
    push_cache("bucket", client=client)
    for name in (*DIR_NAMES, "data", "snapshots"):
        (cache_dir / name / "page.html").write_text(f"changed {name}")
    (cache_dir / "results" / "new.html").write_text("new")

    archive_name = pull_cache("bucket", client=client)

    assert archive_name == Path(next(iter(client.objects))).name
    for name in DIR_NAMES:
        assert (cache_dir / name / "page.html").read_text() == f"local {name}"
        assert (cache_dir / "pull_backup" / name / "page.html").read_text() == f"changed {name}"
    assert not (cache_dir / "results" / "new.html").exists()
    for name in ("data", "snapshots"):
        assert (cache_dir / name / "page.html").read_text() == f"changed {name}"
    assert [path.name for path in cache_dir.iterdir() if path.name.startswith("tmp")] == []


def test_pull_replaces_the_previous_backup(cache_dir):
    client = FakeS3Client()
    push_cache("bucket", client=client)
    (cache_dir / "pull_backup").mkdir()
    (cache_dir / "pull_backup" / "old.html").write_text("old")
    pull_cache("bucket", client=client)
    assert not (cache_dir / "pull_backup" / "old.html").exists()


def test_pull_of_an_empty_bucket_raises_and_leaves_the_cache_untouched(cache_dir):
    with pytest.raises(FileNotFoundError):
        pull_cache("bucket", client=FakeS3Client())
    for name in DIR_NAMES:
        assert (cache_dir / name / "page.html").read_text() == f"local {name}"
    assert not (cache_dir / "pull_backup").exists()


def test_pull_of_an_incomplete_archive_raises_and_leaves_the_cache_untouched(cache_dir, tmp_path):
    archive_path = tmp_path / "incomplete.tar.gz"
    with tarfile.open(archive_path, mode="w:gz") as tar:
        tar.add(cache_dir / "results", arcname="results")
    client = FakeS3Client()
    client.objects = {CACHE_KEYS.build_key(): archive_path.read_bytes()}
    with pytest.raises(ValueError, match="results_national, startlists"):
        pull_cache("bucket", client=client)
    for name in DIR_NAMES:
        assert (cache_dir / name / "page.html").read_text() == f"local {name}"
    assert not (cache_dir / "pull_backup").exists()
