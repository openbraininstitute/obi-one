from types import SimpleNamespace
from unittest.mock import Mock, patch

import morphio
import pytest
from entitysdk.exception import EntitySDKError
from entitysdk.types import AssetLabel, ContentType

from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID

_SELECT = "obi_one.scientific.from_id.cell_morphology_from_id.select_asset_content"


def test_morphio_morphology_fetches_h5_to_tempfile():
    entity = SimpleNamespace(id="morphology-id", assets=[])
    client = Mock()
    client.fetch_assets.return_value.one.return_value = Mock()
    expected = object()
    reference = CellMorphologyFromID(id_str="morphology-id")

    with (
        patch.object(CellMorphologyFromID, "entity", return_value=entity),
        patch("morphio.Morphology", return_value=expected) as morphology_ctor,
    ):
        morphology = reference.morphio_morphology(client)
        cached = reference.morphio_morphology(client)

    assert morphology is expected
    assert cached is expected
    client.fetch_assets.assert_called_once()
    assert client.fetch_assets.call_args.args[0] is entity
    assert client.fetch_assets.call_args.kwargs["selection"] == {
        "content_type": ContentType.application_x_hdf5,
        "label": AssetLabel.morphology,
    }
    morphology_ctor.assert_called_once()
    (path_arg,) = morphology_ctor.call_args.args
    assert str(path_arg).endswith(".h5")
    assert morphology_ctor.call_args.kwargs["options"] == morphio.Option.nrn_order


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


def test_neurom_morphology_loads_swc_via_select_asset_content():
    entity = SimpleNamespace(id="morphology-id", assets=[])
    client = Mock()
    expected = object()
    reference = CellMorphologyFromID(id_str="morphology-id")

    with (
        patch.object(CellMorphologyFromID, "entity", return_value=entity),
        patch(_SELECT, return_value=b"swc-bytes") as select,
        patch("neurom.load_morphology", return_value=expected) as load,
    ):
        morphology = reference.neurom_morphology(client)
        cached = reference.neurom_morphology(client)

    assert morphology is expected
    assert cached is expected
    select.assert_called_once()
    assert select.call_args.kwargs["selection"] == {
        "content_type": ContentType.application_swc,
        "label": AssetLabel.morphology,
    }
    load.assert_called_once_with("swc-bytes", reader="swc")


def test_spiny_morphology_fetches_spiny_asset(tmp_path):
    morphology_from_id = CellMorphologyFromID(id_str="00000000-0000-0000-0000-000000000011")
    entity = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000011",
        name="cell",
    )
    db_client = Mock()
    db_client.fetch_assets.return_value.one.return_value = Mock()
    expected = object()
    output_path = tmp_path / "spiny.h5"

    with (
        patch.object(CellMorphologyFromID, "entity", return_value=entity),
        patch(
            "morph_spines.load_morphology_with_spines",
            return_value=expected,
        ) as load,
    ):
        result = morphology_from_id.spiny_morphology(db_client, path=output_path)

    assert result is expected
    db_client.fetch_assets.assert_called_once_with(
        entity,
        selection={
            "content_type": ContentType.application_x_hdf5,
            "label": AssetLabel.morphology_with_spines,
        },
        output_path=output_path,
    )
    load.assert_called_once_with(str(output_path))


def test_metadata_entities_returns_species_and_brain_region():
    species = SimpleNamespace(name="Mus musculus")
    brain_region = SimpleNamespace(name="Somatosensory cortex")
    entity = SimpleNamespace(
        subject=SimpleNamespace(species=species),
        brain_region=brain_region,
    )
    reference = CellMorphologyFromID(id_str="morphology-id")
    db_client = Mock()

    with patch.object(CellMorphologyFromID, "entity", return_value=entity) as resolve:
        result = reference.metadata_entities(db_client)

    assert result == (species, brain_region)
    resolve.assert_called_once_with(db_client=db_client)


@pytest.mark.parametrize(
    ("entity", "message"),
    [
        (SimpleNamespace(subject=None, brain_region=SimpleNamespace()), "subject relationship"),
        (
            SimpleNamespace(
                subject=SimpleNamespace(species=None),
                brain_region=SimpleNamespace(),
            ),
            "subject.species relationship",
        ),
        (
            SimpleNamespace(
                subject=SimpleNamespace(species=SimpleNamespace()),
                brain_region=None,
            ),
            "brain_region relationship",
        ),
    ],
)
def test_metadata_entities_rejects_missing_relationships(entity, message):
    reference = CellMorphologyFromID(id_str="morphology-id")

    with (
        patch.object(CellMorphologyFromID, "entity", return_value=entity),
        pytest.raises(EntitySDKError, match=message),
    ):
        reference.metadata_entities(Mock())
