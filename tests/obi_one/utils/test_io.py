import tarfile
import tempfile
from pathlib import Path

import pytest
from PIL import Image

from obi_one.utils import io as test_module

from tests.utils import CIRCUIT_DIR


def test_write_and_load_json(tmp_path):
    file_path = tmp_path / "data.json"
    data = {"foo": 123, "bar": [1, 2, 3]}

    # Write JSON
    test_module.write_json(data, file_path, indent=2)

    # Check that file exists
    assert file_path.exists()
    assert file_path.is_file()

    # Load JSON and verify content
    loaded = test_module.load_json(file_path)
    assert loaded == data


def test_convert_image_to_webp(tmp_path):
    # Create a small test PNG
    img = Image.new("RGB", (4, 4), color=(255, 0, 0))
    png_path = tmp_path / "test.png"
    img.save(png_path)

    result = test_module.convert_image_to_webp(png_path)

    assert result == tmp_path / "test.webp"
    assert result.exists()


def test_convert_image_to_webp_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        test_module.convert_image_to_webp(tmp_path / "nope.png")


def test_convert_image_to_webp_no_overwrite(tmp_path):
    img = Image.new("RGB", (4, 4))
    png_path = tmp_path / "test.png"
    img.save(png_path)
    (tmp_path / "test.webp").write_bytes(b"existing")

    with pytest.raises(FileExistsError):
        test_module.convert_image_to_webp(png_path)


def test_extract_tar_gz(tmp_path):
    """Test extracting a .tar.gz archive."""
    # Create a small tar.gz archive
    src_dir = tmp_path / "source"
    src_dir.mkdir()
    (src_dir / "file.txt").write_text("hello")

    archive_path = tmp_path / "archive.tar.gz"
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(src_dir, arcname="my_circuit")

    result = test_module.extract_tar_gz(archive_path)

    assert result == tmp_path / "archive"
    assert (result / "my_circuit" / "file.txt").read_text() == "hello"


def test_extract_tar_gz_without_tar_suffix(tmp_path):
    """Test extracting a .gz archive (no .tar in filename)."""
    # Create a tar.gz archive named circuit.gz (no .tar in name)
    src_dir = tmp_path / "source"
    src_dir.mkdir()
    (src_dir / "circuit_config.json").write_text('{"version": 2}')

    archive_path = tmp_path / "circuit.gz"
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(src_dir, arcname="circuit")

    result = test_module.extract_tar_gz(archive_path)

    assert result == tmp_path / "circuit"
    assert (result / "circuit" / "circuit_config.json").exists()


def test_extract_tar_gz_custom_output_dir(tmp_path):
    """Test extracting to a custom output directory."""
    src_dir = tmp_path / "source"
    src_dir.mkdir()
    (src_dir / "data.txt").write_text("content")

    archive_path = tmp_path / "data.tar.gz"
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(src_dir, arcname="data")

    custom_dir = tmp_path / "custom_output"
    result = test_module.extract_tar_gz(archive_path, output_dir=custom_dir)

    assert result == custom_dir
    assert (custom_dir / "data" / "data.txt").read_text() == "content"


def test_extract_tar_gz_existing_example_data():
    """Test extracting the actual compressed circuit from example data."""
    archive_path = CIRCUIT_DIR / "N_10__top_nodes_dim6.gz"
    if not archive_path.exists():
        pytest.skip("Example compressed circuit not available")

    with tempfile.TemporaryDirectory() as tmpdir:
        result = test_module.extract_tar_gz(archive_path, output_dir=Path(tmpdir) / "extracted")
        assert (result / "circuit" / "circuit_config.json").exists()


def test_extract_tar_gz_clean_existing_dir(tmp_path):
    """Test that clean=True removes existing output dir before extraction."""
    src_dir = tmp_path / "source"
    src_dir.mkdir()
    (src_dir / "file.txt").write_text("new content")

    archive_path = tmp_path / "archive.tar.gz"
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(src_dir, arcname="data")

    # Create a pre-existing output dir with stale content
    output_dir = tmp_path / "archive"
    output_dir.mkdir()
    (output_dir / "stale.txt").write_text("old")

    result = test_module.extract_tar_gz(archive_path, clean=True)

    assert result == output_dir
    assert (output_dir / "data" / "file.txt").read_text() == "new content"
    assert not (output_dir / "stale.txt").exists()
