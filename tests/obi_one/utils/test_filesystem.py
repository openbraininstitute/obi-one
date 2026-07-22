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


def test_find_file(tmp_path):
    target = tmp_path / "subdir" / "special"
    target.parent.mkdir()
    target.write_text("x")

    assert test_module.find_file(directory=tmp_path, pattern="**/special") == target
    assert test_module.find_file(directory=tmp_path / "subdir", pattern="special") == target


def test_find_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError, match="No file found for pattern"):
        test_module.find_file(directory=tmp_path, pattern="missing.txt")
