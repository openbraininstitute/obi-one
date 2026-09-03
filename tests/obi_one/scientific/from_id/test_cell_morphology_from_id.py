from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID

_MODULE = "obi_one.scientific.from_id.cell_morphology_from_id"


def test_morphio_morphology_loads_swc_file_and_caches_result():
    morphology_from_id = CellMorphologyFromID(id_str="morphology-1")
    swc_content = "1 1 0.0 0.0 0.0 1.0 -1\n"
    parsed_morphology = Mock()
    observed: dict[str, Path | str] = {}

    def load_morphology(path: Path) -> Mock:
        observed["path"] = path
        observed["content"] = path.read_text(encoding="utf-8")
        return parsed_morphology

    with (
        patch.object(
            CellMorphologyFromID,
            "swc_file_content",
            return_value=swc_content,
        ) as swc_file_content,
        patch(f"{_MODULE}.morphio.Morphology", side_effect=load_morphology) as morphio_loader,
    ):
        first = morphology_from_id.morphio_morphology(Mock())
        second = morphology_from_id.morphio_morphology(Mock())

    temporary_path = observed["path"]
    assert isinstance(temporary_path, Path)
    assert temporary_path.suffix == ".swc"
    assert observed["content"] == swc_content
    assert not temporary_path.exists()
    assert first is parsed_morphology
    assert second is parsed_morphology
    assert swc_file_content.call_count == 1
    morphio_loader.assert_called_once_with(temporary_path)


def test_swc_file_content_downloads_and_caches_swc_asset():
    morphology_from_id = CellMorphologyFromID(id_str="morphology-1")
    entity = SimpleNamespace(
        id="morphology-1",
        assets=[SimpleNamespace(content_type="application/swc", id="asset-1")],
    )
    db_client = Mock()
    db_client.download_content.return_value = b"1 1 0.0 0.0 0.0 1.0 -1\n"

    with patch.object(CellMorphologyFromID, "entity", return_value=entity):
        assert morphology_from_id.swc_file_content(db_client) == ("1 1 0.0 0.0 0.0 1.0 -1\n")
        assert morphology_from_id.swc_file_content(db_client) == ("1 1 0.0 0.0 0.0 1.0 -1\n")

    db_client.download_content.assert_called_once_with(
        entity_id="morphology-1",
        entity_type=morphology_from_id.entitysdk_type,
        asset_id="asset-1",
    )


@pytest.mark.parametrize(
    ("asset", "message"),
    [
        (SimpleNamespace(content_type="application/asc", id="asset-1"), "No valid"),
        (SimpleNamespace(content_type="application/swc", id=None), "Asset must have an id"),
    ],
)
def test_swc_file_content_rejects_invalid_assets(asset, message):
    morphology_from_id = CellMorphologyFromID(id_str="morphology-1")
    entity = SimpleNamespace(id="morphology-1", assets=[asset])

    with (
        patch.object(CellMorphologyFromID, "entity", return_value=entity),
        pytest.raises(ValueError, match=message),
    ):
        morphology_from_id.swc_file_content(Mock())
