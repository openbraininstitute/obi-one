from http import HTTPStatus
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from entitysdk.types import (
    ActivityStatus,
    AssetLabel,
    AssetStatus,
    ContentType,
    EntityLifecycleStatus,
    TaskActivityType,
    TaskConfigType,
)

from app.dependencies.compute_cell import get_compute_cell
from app.dependencies.entitysdk import get_client
from app.schemas.task import TaskLaunchInfo
from app.types import MachinePlacementType, TaskType

TARGET_MODULE = "app.endpoints.em_cell_mesh_conversion"
DB_SDK_MODULE = "obi_one.db_sdk.db_sdk"


def make_asset(content_type, status=AssetStatus.created):
    return SimpleNamespace(
        id=uuid4(), label=AssetLabel.cell_surface_mesh, content_type=content_type, status=status
    )


@pytest.fixture
def mesh():
    return SimpleNamespace(
        id=uuid4(),
        name="neuron 42",
        lifecycle_status=EntityLifecycleStatus.draft,
        assets=[make_asset(ContentType.application_obj)],
    )


@pytest.fixture
def db_client(mesh):
    client = MagicMock()
    client.get_entity.return_value = mesh
    client.search_entity.return_value = []
    return client


@pytest.fixture
def api(client, db_client):
    client.app.dependency_overrides[get_client] = lambda: db_client
    client.app.dependency_overrides[get_compute_cell] = lambda: "cell_a"
    yield client
    client.app.dependency_overrides.pop(get_client, None)
    client.app.dependency_overrides.pop(get_compute_cell, None)


@pytest.fixture
def task_config():
    return SimpleNamespace(id=uuid4())


@pytest.fixture
def register_config(task_config):
    with patch(
        f"{DB_SDK_MODULE}.register_task_config_with_asset",
        return_value=(task_config, None),
    ) as patched:
        yield patched


def test_convert_launches_a_free_task_used_by_the_mesh(api, mesh, task_config, register_config):
    launch_info = TaskLaunchInfo(
        task_type=TaskType.em_cell_mesh_conversion,
        config_id=task_config.id,
        activity_id=uuid4(),
        job_id=uuid4(),
    )
    with patch(f"{TARGET_MODULE}.task_service.submit_task_job", return_value=launch_info) as submit:
        response = api.post(f"/declared/em-cell-mesh/{mesh.id}/convert")

    assert response.status_code == HTTPStatus.OK
    assert response.json()["job_id"] == str(launch_info.job_id)

    config_kwargs = register_config.call_args.kwargs
    assert config_kwargs["task_config_type"] == TaskConfigType.em_cell_mesh_conversion__config
    assert config_kwargs["input_entities"] == [mesh]

    submit_kwargs = submit.call_args.kwargs
    assert submit_kwargs["config_id"] == task_config.id
    assert submit_kwargs["callbacks"] == []
    assert submit_kwargs["extra_used"] == [mesh]
    resources = submit_kwargs["task_definition"].resources
    assert resources.compute_cell == "cell_a"
    assert resources.placement_type == MachinePlacementType.fargate


@pytest.mark.parametrize(
    ("change", "match"),
    [
        (lambda m: setattr(m, "lifecycle_status", EntityLifecycleStatus.active), "is active"),
        (
            lambda m: m.assets.append(make_asset(ContentType.model_gltf_binary)),
            "already has a GLB",
        ),
        (lambda m: m.assets.clear(), "exactly one fully uploaded OBJ"),
        (
            lambda m: setattr(
                m, "assets", [make_asset(ContentType.application_obj, AssetStatus.uploading)]
            ),
            "exactly one fully uploaded OBJ",
        ),
    ],
)
def test_convert_refuses_a_mesh_that_is_not_ready(api, mesh, register_config, change, match):
    change(mesh)

    response = api.post(f"/declared/em-cell-mesh/{mesh.id}/convert")

    assert response.status_code == HTTPStatus.CONFLICT
    assert match in response.json()["message"]
    register_config.assert_not_called()


def test_convert_refuses_a_second_conversion(api, mesh, db_client, register_config):
    db_client.search_entity.return_value = [SimpleNamespace(status=ActivityStatus.running)]

    response = api.post(f"/declared/em-cell-mesh/{mesh.id}/convert")

    assert response.status_code == HTTPStatus.CONFLICT
    assert db_client.search_entity.call_args.kwargs["query"] == {
        "used__id": str(mesh.id),
        "task_activity_type": TaskActivityType.em_cell_mesh_conversion__execution,
    }
    register_config.assert_not_called()


@pytest.mark.usefixtures("register_config")
def test_convert_settles_the_mesh_when_the_launch_fails(api, mesh):
    with (
        patch(
            f"{TARGET_MODULE}.task_service.submit_task_job",
            side_effect=RuntimeError("launch-system down"),
        ),
        patch(f"{TARGET_MODULE}.settle_failed_conversion") as settle,
    ):
        response = api.post(f"/declared/em-cell-mesh/{mesh.id}/convert")

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    settle.assert_called_once()
    assert settle.call_args.args[1] == mesh.id


@pytest.mark.usefixtures("register_config")
def test_convert_leaves_the_mesh_to_a_job_that_may_be_running(api, mesh, db_client):
    db_client.search_entity.side_effect = [[], [SimpleNamespace(status=ActivityStatus.pending)]]
    with (
        patch(
            f"{TARGET_MODULE}.task_service.submit_task_job",
            side_effect=httpx.ReadTimeout("no response from the launch-system"),
        ),
        patch(f"{TARGET_MODULE}.settle_failed_conversion") as settle,
    ):
        response = api.post(f"/declared/em-cell-mesh/{mesh.id}/convert")

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    settle.assert_not_called()


def test_convert_settles_the_mesh_when_the_config_cannot_be_registered(api, mesh):
    with (
        patch(
            f"{DB_SDK_MODULE}.register_task_config_with_asset",
            side_effect=RuntimeError("entitycore down"),
        ),
        patch(f"{TARGET_MODULE}.settle_failed_conversion") as settle,
    ):
        response = api.post(f"/declared/em-cell-mesh/{mesh.id}/convert")

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert settle.call_args.args[1] == mesh.id


@pytest.mark.usefixtures("register_config")
def test_convert_reports_the_launch_failure_even_if_settling_fails(api, mesh):
    with (
        patch(
            f"{TARGET_MODULE}.task_service.submit_task_job",
            side_effect=RuntimeError("launch-system down"),
        ),
        patch(
            f"{TARGET_MODULE}.settle_failed_conversion", side_effect=RuntimeError("entitycore down")
        ),
    ):
        response = api.post(f"/declared/em-cell-mesh/{mesh.id}/convert")

    assert response.status_code == HTTPStatus.INTERNAL_SERVER_ERROR
    assert response.json()["message"] == "Failed to submit the conversion task"
