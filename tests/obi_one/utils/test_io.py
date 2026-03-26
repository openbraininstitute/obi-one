import pytest
from PIL import Image

from obi_one.utils import io as test_module


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
