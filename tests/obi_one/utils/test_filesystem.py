from pathlib import Path

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
