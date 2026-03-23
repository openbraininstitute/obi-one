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
