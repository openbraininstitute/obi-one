from pathlib import Path

import pytest

from obi_one.core.exception import OBIONEError
from obi_one.utils import filesystem as test_module


def test_create_dir(tmp_path):
    dir_path = tmp_path / "nested" / "dir"
    result = test_module.create_dir(dir_path)

    assert result == dir_path
    assert dir_path.exists()
    assert dir_path.is_dir()


def test_filter_extension():
    files = ["a.txt", "b.py", "c.TXT", "d.py", "e"]
    assert test_module.filter_extension(files, "txt") == ["a.txt", "c.TXT"]
    assert test_module.filter_extension(files, "py") == ["b.py", "d.py"]
    assert test_module.filter_extension(files, "json") == []


def test_chdir(tmp_path):
    nested = tmp_path / "nested"
    nested.mkdir()
    with test_module.chdir(nested):
        assert Path.cwd() == nested.resolve()
    assert Path.cwd() != nested.resolve()


def test_copy_tree_file_and_dir(tmp_path):
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "a.txt").write_text("hello", encoding="utf-8")
    source_file = tmp_path / "file.txt"
    source_file.write_text("world", encoding="utf-8")

    test_module.copy_tree(source_dir, tmp_path / "dst" / "copied_dir")
    test_module.copy_tree(source_file, tmp_path / "dst" / "copied_file.txt")

    assert (tmp_path / "dst" / "copied_dir" / "a.txt").read_text(encoding="utf-8") == "hello"
    assert (tmp_path / "dst" / "copied_file.txt").read_text(encoding="utf-8") == "world"


def test_sha256_file(tmp_path):
    path = tmp_path / "payload"
    path.write_bytes(b"data")
    assert test_module.sha256_file(path) == (
        "3a6eb0790f39ac87c94f3856b2dd2c5d110e6811602261a9a923d3bb23adc8b7"
    )


def test_download_file(tmp_path):
    source = tmp_path / "payload"
    source.write_bytes(b"data")
    sha256 = test_module.sha256_file(source)
    destination = tmp_path / "out" / "payload"

    assert test_module.download_file(source.as_uri(), destination, sha256) == destination
    assert destination.read_bytes() == b"data"


def test_download_file_rejects_bad_checksum(tmp_path):
    source = tmp_path / "payload"
    source.write_bytes(b"data")
    destination = tmp_path / "out" / "payload"

    with pytest.raises(OBIONEError, match="Checksum mismatch"):
        test_module.download_file(source.as_uri(), destination, "0" * 64)
    assert not destination.exists()
    assert not destination.with_suffix(".part").exists()
