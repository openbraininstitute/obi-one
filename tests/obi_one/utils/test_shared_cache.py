from pathlib import Path
from unittest.mock import patch

import pytest

from obi_one.utils.shared_cache import SharedCache, SharedCacheError


@pytest.fixture
def cache_root(tmp_path):
    return tmp_path


def test_creates_mechanisms_subdir(cache_root):
    cache = SharedCache(cache_root)

    assert cache.mechanisms_dir == cache_root / "mechanisms"
    assert cache.mechanisms_dir.is_dir()
    assert not hasattr(cache, "prefix")
    assert not hasattr(cache, "root")


def test_from_existing_path_returns_cache_when_directory_exists(cache_root):
    cache = SharedCache.from_existing_path(cache_root)

    assert cache.mechanisms_dir.is_dir()


def test_from_existing_path_raises_when_missing(cache_root):
    missing = cache_root / "missing"
    with pytest.raises(SharedCacheError, match="does not exist"):
        SharedCache.from_existing_path(missing)


def test_from_existing_path_raises_when_not_a_directory(cache_root):
    file_path = cache_root / "not-a-dir"
    file_path.write_text("x")
    with pytest.raises(SharedCacheError, match="not a directory"):
        SharedCache.from_existing_path(file_path)


def test_from_existing_path_raises_when_not_writable(cache_root):
    cache_root.chmod(0o555)
    try:
        with pytest.raises(SharedCacheError, match="not writable"):
            SharedCache.from_existing_path(cache_root)
    finally:
        cache_root.chmod(0o755)


def test_from_existing_path_raises_when_resolve_fails(cache_root):
    with (
        patch.object(Path, "resolve", side_effect=OSError("cannot resolve")),
        pytest.raises(SharedCacheError, match="could not be resolved"),
    ):
        SharedCache.from_existing_path(cache_root)


def test_from_existing_path_raises_when_initialization_fails(cache_root):
    with (
        patch.object(Path, "mkdir", side_effect=OSError("mkdir failed")),
        pytest.raises(SharedCacheError, match="could not be initialized"),
    ):
        SharedCache.from_existing_path(cache_root)
