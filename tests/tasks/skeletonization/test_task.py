import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx
import morphio
import morphio.mut
import pytest
from entitysdk import Client, ProjectContext

from obi_one import EMCellMeshFromID, Info
from obi_one.scientific.tasks.skeletonization import task as test_module
from obi_one.scientific.tasks.skeletonization.config import SkeletonizationSingleConfig


@pytest.fixture
def cell_mesh_id():
    return uuid4()


@pytest.fixture
def cell_mesh(cell_mesh_id):
    return EMCellMeshFromID(id_str=str(cell_mesh_id))


@pytest.fixture
def info():
    return Info(
        campaign_name="Skeletonization test campaign",
        campaign_description="Skeletonization test description",
    )


@pytest.fixture
def initialize(cell_mesh):
    return SkeletonizationSingleConfig.Initialize(
        cell_mesh=cell_mesh,
        neuron_voxel_size=0.1,
        spines_voxel_size=0.1,
    )


@pytest.fixture
def config(info, initialize, tmpdir):
    return SkeletonizationSingleConfig(
        info=info,
        initialize=initialize,
        coordinate_output_root=Path(tmpdir),
    )


@pytest.fixture
def mock_ultraliser_output(tmpdir):
    contents = """
1 1  0  0 0 1. -1
2 3  0  0 0 1.  1
3 3  0  5 0 1.  2
4 3 -5  5 0 1.5 3
5 3  6  5 0 1.5 3
6 2  0  0 0 1.  1
7 2  0 -4 0 1.  6
8 2  6 -4 0 2.  7
9 2 -5 -4 0 2.  7
"""
    outputs = Path(tmpdir) / "outputs"
    outputs.mkdir(exist_ok=True)

    morphology = morphio.mut.Morphology(morphio.Morphology(contents, "swc"))
    path = outputs / "morph.swc"
    morphology.write(path)
    morphology.write(path.with_suffix(".h5"))


@pytest.mark.usefixtures("mock_ultraliser_output")
def test_skeletonization_task(config, httpx_mock, cell_mesh_id):  # noqa: PLR0914
    client = Client(
        api_url="http://my-url",
        token_manager="token",  # noqa: S106
        project_context=ProjectContext(virtual_lab_id=uuid4(), project_id=uuid4()),
    )
    activity_id = uuid4()
    subject_id = uuid4()
    dataset_id = uuid4()
    species_id = uuid4()
    brain_region_id = uuid4()
    brain_region_id = uuid4()
    em_cell_mesh_asset_id = uuid4()
    now = datetime.now(UTC).isoformat()
    hierarchy_id = uuid4()
    morphology_id = uuid4()
    created_by = {
        "id": str(uuid4()),
        "type": "person",
        "pref_label": "Foo Bar",
    }
    role = {
        "id": str(uuid4()),
        "name": "data_moding_role",
        "role_id": "foo",
        "created_by": created_by,
    }
    agent = {
        "id": str(uuid4()),
        "type": "person",
        "pref_label": "Foo Bar",
    }

    em_cell_mesh_asset_payload = {
        "id": str(em_cell_mesh_asset_id),
        "label": "cell_surface_mesh",
        "path": "mesh.obj",
        "full_path": "/mesh.obj",
        "is_directory": False,
        "content_type": "application/obj",
        "storage_type": "aws_s3_internal",
        "size": 0,
        "status": "created",
    }
    brain_region_payload = {
        "id": str(brain_region_id),
        "name": "my-region",
        "annotation_value": 1,
        "acronym": "region",
        "parent_structure_id": str(brain_region_id),
        "hierarchy_id": str(hierarchy_id),
        "color_hex_triplet": "red",
    }

    activity_payload = {
        "id": str(activity_id),
        "status": "created",
        "start_time": str(now),
    }

    httpx_mock.add_response(
        url=f"http://my-url/skeletonization-execution/{activity_id}",
        method="GET",
        json=activity_payload,
    )
    httpx_mock.add_response(
        url=f"http://my-url/em-cell-mesh/{cell_mesh_id}",
        method="GET",
        json={
            "id": str(cell_mesh_id),
            "subject": {
                "id": str(subject_id),
                "sex": "male",
                "species": {
                    "id": str(species_id),
                    "name": "my-species",
                    "taxonomy_id": "foo",
                },
                "brain_region": brain_region_payload,
            },
            "brain_region": brain_region_payload,
            "em_dense_reconstruction_dataset": {
                "id": str(dataset_id),
            },
            "release_version": 1,
            "dense_reconstruction_cell_id": 123,
            "generation_method": "marching_cubes",
            "level_of_detail": 1,
            "mesh_type": "static",
            "assets": [em_cell_mesh_asset_payload],
        },
    )
    httpx_mock.add_response(
        url=f"http://my-url/em-cell-mesh/{cell_mesh_id}/assets/{em_cell_mesh_asset_id}/download",
        method="GET",
        content=b"foo",
    )

    httpx_mock.add_response(
        url=f"http://my-url/em-cell-mesh/{cell_mesh_id}/assets/{em_cell_mesh_asset_id}",
        method="GET",
        json=em_cell_mesh_asset_payload,
    )
    httpx_mock.add_response(
        url=f"http://my-url/em-dense-reconstruction-dataset/{dataset_id}",
        json={
            "id": str(dataset_id),
            "slicing_thickness": 1.2,
            "slicing_direction": "coronal",
            "tissue_shrinkage": 0.1,
            "volume_resolution_x_nm": 0.1,
            "volume_resolution_y_nm": 0.1,
            "volume_resolution_z_nm": 0.1,
        },
    )
    httpx_mock.add_response(
        url="http://my-url/role?name=data+modeling+role&page=1",
        json={
            "data": [role],
            "pagination": {
                "page": 1,
                "page_size": 1,
                "total_items": 1,
            },
        },
    )
    httpx_mock.add_response(
        url="http://my-url/license?label=CC+BY-NC+4.0&page=1",
        json={
            "data": [
                {
                    "id": str(uuid4()),
                    "label": "CC_BY_NC_4",
                    "name": "my-license",
                    "description": "my-license-description",
                    "created_by": created_by,
                }
            ],
            "pagination": {
                "page": 1,
                "page_size": 1,
                "total_items": 1,
            },
        },
    )

    # no protocol found
    httpx_mock.add_response(
        url="http://my-url/cell-morphology-protocol?name=Ultraliser+skeletonization&page=1",
        method="GET",
        json={
            "data": [],
            "pagination": {
                "page": 1,
                "page_size": 1,
                "total_items": 1,
            },
        },
    )
    httpx_mock.add_callback(
        lambda r: httpx.Response(
            status_code=200,
            json=json.loads(r.content) | {"id": str(uuid4())},
        ),
        url="http://my-url/cell-morphology-protocol",
        method="POST",
    )
    httpx_mock.add_callback(
        lambda r: httpx.Response(
            status_code=200,
            json=json.loads(r.content)
            | {
                "id": str(morphology_id),
                "created_by": agent,
            },
        ),
        url="http://my-url/cell-morphology",
        method="POST",
    )

    httpx_mock.add_callback(
        lambda r: httpx.Response(
            status_code=200,
            json=json.loads(r.content)
            | {
                "id": str(uuid4()),
                "role": role,
                "agent": agent,
            },
        ),
        url="http://my-url/contribution",
        method="POST",
    )
    httpx_mock.add_response(
        url=f"http://my-url/cell-morphology/{morphology_id}/assets",
        method="POST",
        json=em_cell_mesh_asset_payload,
    )
    httpx_mock.add_response(
        url=f"http://my-url/cell-morphology/{morphology_id}/assets",
        method="POST",
        json=em_cell_mesh_asset_payload,
    )
    httpx_mock.add_response(
        url=f"http://my-url/cell-morphology/{morphology_id}/assets",
        method="POST",
        json=em_cell_mesh_asset_payload,
    )
    httpx_mock.add_response(
        url=f"http://my-url/cell-morphology/{morphology_id}/assets",
        method="POST",
        json=em_cell_mesh_asset_payload,
    )
    httpx_mock.add_callback(
        lambda r: httpx.Response(
            status_code=200,
            json=activity_payload | json.loads(r.content),
        ),
        url=f"http://my-url/skeletonization-execution/{activity_id}",
        method="PATCH",
    )
    with patch("obi_one.scientific.tasks.skeletonization.task.run_process"):
        task = test_module.SkeletonizationTask(config=config)
        task.execute(db_client=client, execution_activity_id=activity_id)
