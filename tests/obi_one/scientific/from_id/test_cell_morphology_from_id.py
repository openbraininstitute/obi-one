from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import morphio
import pytest
from entitysdk.exception import EntitySDKError
from entitysdk.models import CellMorphology, EMCellMesh, TaskConfig
from entitysdk.models.cell_morphology_protocol import (
    DigitalReconstructionCellMorphologyProtocol,
    PlaceholderCellMorphologyProtocol,
)
from entitysdk.types import (
    AssetLabel,
    CellMorphologyProtocolDesign,
    ContentType,
    EntityType,
)

from obi_one.scientific.from_id.cell_morphology_from_id import (
    CellMorphologyFromID,
    _morphology_has_source_mesh,
    _morphology_source_mesh_entity,
)
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID

_SELECT = "obi_one.scientific.from_id.cell_morphology_from_id.select_asset_content"
_MODULE = "obi_one.scientific.from_id.cell_morphology_from_id"
_TEST_DATA = Path(__file__).resolve().parents[3] / "test_data"


def _minimal_morphology_bytes(filename: str) -> bytes:
    return (_TEST_DATA / filename).read_bytes()


def _em_protocol():
    return DigitalReconstructionCellMorphologyProtocol.model_construct(
        protocol_design=CellMorphologyProtocolDesign.electron_microscopy
    )


def _cell_morphology(**kwargs):
    return CellMorphology.model_construct(
        _fields_set=None,
        id=kwargs.pop("id", uuid4()),
        name=kwargs.pop("name", "cell"),
        cell_morphology_protocol=kwargs.pop("cell_morphology_protocol", _em_protocol()),
        **kwargs,
    )


def _used(entity_type=EntityType.task_config, *, entity_id: object = ...):
    if entity_id is ...:
        entity_id = uuid4()
    return SimpleNamespace(type=entity_type, id=entity_id)


def _activity(*, used):
    return SimpleNamespace(used=used)


def _morphology_client(*assets):
    client = Mock()
    client.select_assets.return_value.all.return_value = list(assets)
    return client


@pytest.mark.parametrize(
    ("content_type", "fixture_name", "expected_sections"),
    [
        (ContentType.application_swc, "minimal_morphology.swc", 1),
        (ContentType.application_asc, "minimal_morphology.asc", 1),
    ],
)
def test_morphio_morphology_instantiates_morphio_from_real_text_asset(
    content_type, fixture_name, expected_sections
):
    entity = SimpleNamespace(id="morphology-id")
    asset = SimpleNamespace(id=f"asset-{fixture_name}", content_type=content_type)
    client = _morphology_client(asset)
    client.fetch_content.return_value = _minimal_morphology_bytes(fixture_name)
    reference = CellMorphologyFromID(id_str="morphology-id")

    with patch.object(CellMorphologyFromID, "entity", return_value=entity):
        morphology = reference.morphio_morphology(client)
        cached = reference.morphio_morphology(client)

    assert isinstance(morphology, morphio.Morphology)
    assert morphology is cached
    assert len(list(morphology.iter())) == expected_sections
    client.fetch_content.assert_called_once()
    assert client.fetch_content.call_args.kwargs["asset_or_id"] is asset
    client.fetch_file.assert_not_called()


def test_morphio_morphology_instantiates_morphio_from_real_h5_asset():
    entity = SimpleNamespace(id="morphology-id")
    asset = SimpleNamespace(id="asset-h5", content_type=ContentType.application_x_hdf5)
    client = _morphology_client(asset)
    h5_bytes = _minimal_morphology_bytes("minimal_morphology.h5")

    def write_h5_file(**kwargs):
        output_path = kwargs["output_path"]
        output_path.write_bytes(h5_bytes)
        return output_path

    client.fetch_file.side_effect = write_h5_file
    reference = CellMorphologyFromID(id_str="morphology-id")

    with patch.object(CellMorphologyFromID, "entity", return_value=entity):
        morphology = reference.morphio_morphology(client)

    assert isinstance(morphology, morphio.Morphology)
    assert len(list(morphology.iter())) == 1
    client.fetch_file.assert_called_once()
    assert client.fetch_file.call_args.kwargs["entity_id"] == entity.id
    assert client.fetch_file.call_args.kwargs["asset_id"] == asset.id
    client.fetch_content.assert_not_called()


def test_morphio_morphology_prefers_asc_over_swc_and_h5():
    entity = SimpleNamespace(id="morphology-id")
    asc = SimpleNamespace(id="asc", content_type=ContentType.application_asc)
    swc = SimpleNamespace(id="swc", content_type=ContentType.application_swc)
    h5 = SimpleNamespace(id="h5", content_type=ContentType.application_x_hdf5)
    client = _morphology_client(h5, swc, asc)
    client.fetch_content.return_value = _minimal_morphology_bytes("minimal_morphology.asc")
    reference = CellMorphologyFromID(id_str="morphology-id")

    with patch.object(CellMorphologyFromID, "entity", return_value=entity):
        morphology = reference.morphio_morphology(client)

    client.fetch_content.assert_called_once()
    assert client.fetch_content.call_args.kwargs["asset_or_id"] is asc
    assert isinstance(morphology, morphio.Morphology)
    assert len(list(morphology.iter())) == 1


def test_morphio_morphology_raises_when_no_assets():
    entity = SimpleNamespace(id="morphology-id")
    client = _morphology_client()
    reference = CellMorphologyFromID(id_str="morphology-id")

    with (
        patch.object(CellMorphologyFromID, "entity", return_value=entity),
        pytest.raises(EntitySDKError, match="no ASC, SWC, or H5"),
    ):
        reference.morphio_morphology(client)


def test_morphio_morphology_raises_on_unknown_format():
    entity = SimpleNamespace(id="morphology-id")
    unknown_type = object()
    asset = SimpleNamespace(id="asset-unknown", content_type=unknown_type)
    client = _morphology_client(asset)
    reference = CellMorphologyFromID(id_str="morphology-id")

    with (
        patch.object(CellMorphologyFromID, "entity", return_value=entity),
        patch(f"{_MODULE}._MORPHOLOGY_ASSET_FORMATS", (unknown_type,)),
        pytest.raises(EntitySDKError, match="Unknown format"),
    ):
        reference.morphio_morphology(client)


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


def test_spiny_morphology_defaults_path_to_cwd_name(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    morphology_from_id = CellMorphologyFromID(id_str="morphology-id")
    entity = SimpleNamespace(id="morphology-id", name="my-cell")
    db_client = Mock()
    db_client.fetch_assets.return_value.one.return_value = Mock()

    with (
        patch.object(CellMorphologyFromID, "entity", return_value=entity),
        patch("morph_spines.load_morphology_with_spines", return_value=object()) as load,
    ):
        morphology_from_id.spiny_morphology(db_client)

    expected = tmp_path / "my-cell.h5"
    assert db_client.fetch_assets.call_args.kwargs["output_path"] == expected
    load.assert_called_once_with(str(expected))


def test_spiny_morphology_accepts_str_path_and_directory(tmp_path):
    morphology_from_id = CellMorphologyFromID(id_str="morphology-id")
    entity = SimpleNamespace(id="morphology-id", name="dir-cell")
    db_client = Mock()
    db_client.fetch_assets.return_value.one.return_value = Mock()

    with (
        patch.object(CellMorphologyFromID, "entity", return_value=entity),
        patch("morph_spines.load_morphology_with_spines", return_value=object()) as load,
    ):
        morphology_from_id.spiny_morphology(db_client, path=str(tmp_path))

    expected = tmp_path / "dir-cell.h5"
    assert db_client.fetch_assets.call_args.kwargs["output_path"] == expected
    load.assert_called_once_with(str(expected))


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


def test_has_source_mesh_and_source_mesh_entity_delegate_to_helpers():
    reference = CellMorphologyFromID(id_str="morphology-id")
    entity = _cell_morphology()
    client = Mock()
    mesh = EMCellMesh.model_construct(id=uuid4(), name="mesh")

    with (
        patch.object(CellMorphologyFromID, "entity", return_value=entity),
        patch(f"{_MODULE}._morphology_has_source_mesh", return_value=True) as has_mesh,
        patch(f"{_MODULE}._morphology_source_mesh_entity", return_value=mesh) as source_mesh,
    ):
        assert reference.has_source_mesh(client) is True
        assert reference.source_mesh_entity(client) is mesh

    has_mesh.assert_called_once_with(entity, client)
    source_mesh.assert_called_once_with(entity, client)


@pytest.mark.parametrize(
    "entity",
    [
        SimpleNamespace(),
        _cell_morphology(cell_morphology_protocol=None),
        _cell_morphology(
            cell_morphology_protocol=PlaceholderCellMorphologyProtocol.model_construct()
        ),
        _cell_morphology(
            cell_morphology_protocol=DigitalReconstructionCellMorphologyProtocol.model_construct(
                protocol_design=CellMorphologyProtocolDesign.cell_patch
            )
        ),
    ],
)
def test_morphology_has_source_mesh_rejects_invalid_entities(entity):
    assert _morphology_has_source_mesh(entity, Mock()) is False


def test_morphology_has_source_mesh_rejects_missing_or_invalid_activity():
    entity = _cell_morphology()
    client = Mock()

    client.search_entity.return_value.one_or_none.return_value = None
    assert _morphology_has_source_mesh(entity, client) is False

    for used in (
        None,
        [],
        [_used(entity_type=EntityType.em_cell_mesh)],
        [_used(entity_id=None)],
        [_used(), _used()],
    ):
        client.search_entity.return_value.one_or_none.return_value = _activity(used=used)
        assert _morphology_has_source_mesh(entity, client) is False


def test_morphology_has_source_mesh_rejects_invalid_task_inputs():
    entity = _cell_morphology()
    client = Mock()
    task_id = uuid4()
    client.search_entity.return_value.one_or_none.return_value = _activity(
        used=[_used(entity_id=task_id)]
    )

    for inputs in (
        None,
        [],
        [SimpleNamespace(type=EntityType.task_config, id=uuid4())],
        [
            SimpleNamespace(type=EntityType.em_cell_mesh, id=uuid4()),
            SimpleNamespace(type=EntityType.em_cell_mesh, id=uuid4()),
        ],
    ):
        client.get_entity.return_value = TaskConfig.model_construct(inputs=inputs)
        assert _morphology_has_source_mesh(entity, client) is False


def test_morphology_has_source_mesh_accepts_valid_provenance():
    entity = _cell_morphology()
    client = Mock()
    task_id = uuid4()
    mesh_id = uuid4()
    client.search_entity.return_value.one_or_none.return_value = _activity(
        used=[_used(entity_id=task_id)]
    )
    client.get_entity.return_value = TaskConfig.model_construct(
        inputs=[SimpleNamespace(type=EntityType.em_cell_mesh, id=mesh_id)]
    )

    assert _morphology_has_source_mesh(entity, client) is True
    client.get_entity.assert_called_once_with(entity_id=task_id, entity_type=TaskConfig)


def test_morphology_source_mesh_entity_raises_without_provenance():
    entity = _cell_morphology(cell_morphology_protocol=None)
    with pytest.raises(EntitySDKError, match="does not seem to originate"):
        _morphology_source_mesh_entity(entity, Mock())


def test_morphology_source_mesh_entity_returns_mesh():
    entity = _cell_morphology()
    client = Mock()
    task_id = uuid4()
    mesh_id = uuid4()
    mesh = EMCellMesh.model_construct(id=mesh_id, name="source-mesh")

    client.search_entity.return_value.one_or_none.return_value = _activity(
        used=[_used(entity_id=task_id)]
    )

    def get_entity(*, entity_id, entity_type):
        if entity_type is TaskConfig:
            return TaskConfig.model_construct(
                inputs=[SimpleNamespace(type=EntityType.em_cell_mesh, id=mesh_id)]
            )
        if entity_type is EMCellMesh:
            assert entity_id == mesh_id
            return mesh
        msg = f"unexpected entity_type {entity_type}"
        raise AssertionError(msg)

    client.get_entity.side_effect = get_entity

    assert _morphology_source_mesh_entity(entity, client) is mesh
