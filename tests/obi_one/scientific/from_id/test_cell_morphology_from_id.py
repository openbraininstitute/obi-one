import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import morphio
import pytest
from entitysdk.exception import EntitySDKError
from entitysdk.types import ContentType

from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID


def _morphology_file(tmp_path: Path, extension: str) -> Path:
    if extension == "asc":
        return Path(__file__).parents[3] / "test_data" / "cell_morphology.asc"

    swc_path = tmp_path / "cell.swc"
    swc_path.write_text("1 1 0 0 0 5 -1\n2 3 0 10 0 1 1\n3 3 0 30 0 1 2\n")
    if extension == "swc":
        return swc_path

    h5_path = tmp_path / "cell.h5"
    source = Path(__file__).parents[3] / "test_data" / "cell_morphology.asc"
    morphio.mut.Morphology(source).write(h5_path)
    return h5_path


@pytest.mark.parametrize(
    ("content_type", "extension"),
    [
        (ContentType.application_asc, "asc"),
        (ContentType.application_swc, "swc"),
        (ContentType.application_x_hdf5, "h5"),
    ],
)
def test_morphio_morphology_loads_supported_entity_asset(tmp_path, content_type, extension):
    source = _morphology_file(tmp_path, extension)
    entity = SimpleNamespace(
        id="morphology-id",
        assets=[SimpleNamespace(id="asset-id", content_type=content_type)],
    )
    client = Mock()
    client.download_file.side_effect = lambda **kwargs: shutil.copyfile(
        source, kwargs["output_path"]
    )
    reference = CellMorphologyFromID(id_str="morphology-id")

    with patch.object(CellMorphologyFromID, "entity", return_value=entity):
        morphology = reference.morphio_morphology(client)
        cached = reference.morphio_morphology(client)

    assert morphology is cached
    assert len(morphology.sections) > 0
    client.download_file.assert_called_once()


def test_morphio_morphology_rejects_unsupported_entity_assets():
    entity = SimpleNamespace(
        id="morphology-id",
        assets=[SimpleNamespace(id="asset-id", content_type="application/json")],
    )
    reference = CellMorphologyFromID(id_str="morphology-id")

    with (
        patch.object(CellMorphologyFromID, "entity", return_value=entity),
        pytest.raises(EntitySDKError, match="no ASC, SWC, or H5"),
    ):
        reference.morphio_morphology(Mock())


def test_memodel_morphology_delegates_to_cell_morphology_entity():
    expected = object()
    memodel = SimpleNamespace(morphology=SimpleNamespace(id="morphology-id"))
    reference = MEModelFromID(id_str="memodel-id")

    with (
        patch.object(MEModelFromID, "entity", return_value=memodel),
        patch.object(CellMorphologyFromID, "morphio_morphology", return_value=expected) as load,
    ):
        result = reference.morphio_morphology(Mock())

    assert result is expected
    load.assert_called_once()
