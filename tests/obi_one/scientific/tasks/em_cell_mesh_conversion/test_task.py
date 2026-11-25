from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from entitysdk.models import EMCellMesh
from entitysdk.types import AssetLabel, AssetStatus, ContentType, EntityLifecycleStatus

from obi_one.db_sdk import em_cell_mesh as lifecycle
from obi_one.scientific.tasks.em_cell_mesh_conversion import task as test_module
from obi_one.scientific.tasks.em_cell_mesh_conversion.config import (
    EMCellMeshConversionSingleConfig,
)
from obi_one.scientific.tasks.em_cell_mesh_conversion.conversion import MeshConversionError


def make_asset(content_type: ContentType, status: AssetStatus = AssetStatus.created):
    return SimpleNamespace(
        id=uuid4(),
        label=AssetLabel.cell_surface_mesh,
        content_type=content_type,
        status=status,
        path="neuron_42.obj" if content_type == ContentType.application_obj else "neuron_42.glb",
        size=123,
    )


@pytest.fixture
def obj_asset():
    return make_asset(ContentType.application_obj)


@pytest.fixture
def mesh(obj_asset):
    return SimpleNamespace(id=uuid4(), assets=[obj_asset])


@pytest.fixture
def db_client(mesh, tmp_path):
    client = Mock()
    client.get_entity.return_value = mesh
    obj_path = tmp_path / "downloaded.obj"
    obj_path.write_text("v 0 0 0\n", encoding="utf-8")
    client.download_file.return_value = obj_path
    return client


@pytest.fixture
def task(mesh, tmp_path):
    config = EMCellMeshConversionSingleConfig(
        em_cell_mesh_id=mesh.id, coordinate_output_root=tmp_path / "work"
    )
    return test_module.EMCellMeshConversionTask(config=config)


def lifecycle_updates(db_client):
    return [
        c.kwargs["attrs_or_entity"]["lifecycle_status"] for c in db_client.update_entity.mock_calls
    ]


def test_execute_uploads_the_glb_deletes_the_obj_and_activates(
    monkeypatch, task, mesh, obj_asset, db_client, tmp_path
):
    glb_path = tmp_path / "mesh.glb"
    glb_path.write_bytes(b"glb")
    convert = Mock(return_value=glb_path)
    monkeypatch.setattr(test_module, "convert_obj_to_glb", convert)

    task.execute(db_client=db_client, execution_activity_id=str(uuid4()))

    download = db_client.download_file.call_args.kwargs
    assert download["asset_id"] is obj_asset
    assert download["output_path"] == tmp_path / "work" / "mesh.obj"
    convert.assert_called_once_with(db_client.download_file.return_value, tmp_path / "work")
    upload = db_client.upload_file.call_args.kwargs
    assert upload["file_path"] == glb_path
    assert upload["file_name"] == "neuron_42.glb"
    assert upload["file_content_type"] == ContentType.model_gltf_binary
    assert upload["asset_label"] == AssetLabel.cell_surface_mesh
    db_client.delete_asset.assert_called_once_with(
        entity_id=mesh.id, entity_type=EMCellMesh, asset_id=obj_asset.id
    )
    assert lifecycle_updates(db_client) == [EntityLifecycleStatus.active]


def test_execute_skips_the_conversion_when_a_glb_exists(monkeypatch, task, mesh, db_client):
    mesh.assets.append(make_asset(ContentType.model_gltf_binary))
    convert = Mock()
    monkeypatch.setattr(test_module, "convert_obj_to_glb", convert)

    task.execute(db_client=db_client, execution_activity_id=str(uuid4()))

    convert.assert_not_called()
    db_client.upload_file.assert_not_called()
    db_client.delete_asset.assert_called_once()
    assert lifecycle_updates(db_client) == [EntityLifecycleStatus.active]


def test_execute_deletes_the_obj_and_disqualifies_on_failure(
    monkeypatch, task, obj_asset, db_client
):
    monkeypatch.setattr(
        test_module, "convert_obj_to_glb", Mock(side_effect=MeshConversionError("bad OBJ"))
    )

    with pytest.raises(MeshConversionError, match="bad OBJ"):
        task.execute(db_client=db_client, execution_activity_id=str(uuid4()))

    db_client.upload_file.assert_not_called()
    assert db_client.delete_asset.call_args.kwargs["asset_id"] == obj_asset.id
    assert lifecycle_updates(db_client) == [EntityLifecycleStatus.disqualified]


def test_execute_fails_without_exactly_one_obj(monkeypatch, task, mesh, db_client):
    mesh.assets.append(make_asset(ContentType.application_obj))
    monkeypatch.setattr(test_module, "convert_obj_to_glb", Mock())

    with pytest.raises(MeshConversionError, match="2 OBJ surface meshes"):
        task.execute(db_client=db_client, execution_activity_id=str(uuid4()))

    assert db_client.delete_asset.call_count == 2
    assert lifecycle_updates(db_client) == [EntityLifecycleStatus.disqualified]


def test_settle_failed_conversion_activates_a_mesh_with_an_uploaded_glb(mesh, db_client):
    mesh.assets.append(make_asset(ContentType.model_gltf_binary))

    lifecycle.settle_failed_conversion(db_client, mesh.id)

    assert lifecycle_updates(db_client) == [EntityLifecycleStatus.active]
    db_client.delete_asset.assert_called_once()


def test_settle_failed_conversion_ignores_an_unfinished_glb_upload(mesh, db_client):
    mesh.assets.append(make_asset(ContentType.model_gltf_binary, AssetStatus.uploading))

    lifecycle.settle_failed_conversion(db_client, mesh.id)

    assert lifecycle_updates(db_client) == [EntityLifecycleStatus.disqualified]


def test_settle_failed_conversion_still_disqualifies_when_the_delete_fails(mesh, db_client):
    db_client.delete_asset.side_effect = RuntimeError("entitycore down")

    with pytest.raises(RuntimeError, match="entitycore down"):
        lifecycle.settle_failed_conversion(db_client, mesh.id)

    assert lifecycle_updates(db_client) == [EntityLifecycleStatus.disqualified]


def test_settle_failed_conversion_deletes_an_unfinished_glb(mesh, obj_asset, db_client):
    unfinished = make_asset(ContentType.model_gltf_binary, AssetStatus.uploading)
    mesh.assets.append(unfinished)

    lifecycle.settle_failed_conversion(db_client, mesh.id)

    deleted = [c.kwargs["asset_id"] for c in db_client.delete_asset.mock_calls]
    assert deleted == [obj_asset.id, unfinished.id]
    assert lifecycle_updates(db_client) == [EntityLifecycleStatus.disqualified]


def test_execute_does_not_upload_a_second_glb(monkeypatch, task, mesh, db_client, tmp_path):
    glb_path = tmp_path / "mesh.glb"
    glb_path.write_bytes(b"glb")
    monkeypatch.setattr(test_module, "convert_obj_to_glb", Mock(return_value=glb_path))
    converted_elsewhere = SimpleNamespace(
        id=mesh.id, assets=[*mesh.assets, make_asset(ContentType.model_gltf_binary)]
    )
    db_client.get_entity.side_effect = [mesh, converted_elsewhere]

    task.execute(db_client=db_client, execution_activity_id=str(uuid4()))

    db_client.upload_file.assert_not_called()
    assert lifecycle_updates(db_client) == [EntityLifecycleStatus.active]


def test_execute_names_the_glb_after_an_uppercase_obj_asset(
    monkeypatch, task, obj_asset, db_client, tmp_path
):
    obj_asset.path = "Neuron_42.OBJ"
    glb_path = tmp_path / "mesh.glb"
    glb_path.write_bytes(b"glb")
    monkeypatch.setattr(test_module, "convert_obj_to_glb", Mock(return_value=glb_path))

    task.execute(db_client=db_client, execution_activity_id=str(uuid4()))

    assert db_client.upload_file.call_args.kwargs["file_name"] == "Neuron_42.glb"
