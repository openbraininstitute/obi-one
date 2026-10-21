import os
from pathlib import Path

import pytest

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


def test_write_whole(tmp_path):
    path = tmp_path / "file"
    path.write_bytes(b"old")
    test_module.write_whole(path, b"new")
    assert path.read_bytes() == b"new"
    assert list(tmp_path.iterdir()) == [path]


def test_write_whole_leaves_nothing_where_it_fails(tmp_path, monkeypatch):
    def fail(*_):
        raise PermissionError

    monkeypatch.setattr(Path, "replace", fail)
    path = tmp_path / "file"
    with pytest.raises(PermissionError):
        test_module.write_whole(path, b"new")
    assert not any(tmp_path.iterdir())


def test_remove_oldest_past(tmp_path):
    files = [tmp_path / name for name in ("a", "b", "c")]
    for age, path in enumerate(files):
        path.write_bytes(b"x" * 10)
        os.utime(path, ns=(age, age))
    (tmp_path / "folder").mkdir()
    test_module.remove_oldest_past([*files, tmp_path / "folder", tmp_path / "gone"], 20)
    assert sorted(tmp_path.iterdir()) == [files[1], files[2], tmp_path / "folder"]
