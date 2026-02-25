"""Unit tests for obi_one.scientific.tasks.skeletonization.process, registration, and config."""

import json
import sys
from unittest.mock import Mock, patch
from uuid import uuid4

import httpx
import morphio
import morphio.mut
import pytest
from entitysdk import Client, ProjectContext
from entitysdk.models.brain_region import BrainRegion
from entitysdk.models.cell_morphology_protocol import (
    DigitalReconstructionCellMorphologyProtocol,
)
from entitysdk.models.contribution import Role
from entitysdk.models.core import Person
from entitysdk.models.em_dense_reconstruction_dataset import EMDenseReconstructionDataset
from entitysdk.models.license import License
from entitysdk.models.skeletonization_config import SkeletonizationConfig
from entitysdk.models.subject import Subject
from entitysdk.models.taxonomy import Species
from entitysdk.types import (
    CellMorphologyProtocolDesign,
    Sex,
    SlicingDirectionType,
    StainingType,
)

from obi_one.core.exception import OBIONEError
from obi_one.core.info import Info
from obi_one.core.single import SingleCoordinateScanParams
from obi_one.scientific.from_id.em_cell_mesh_from_id import EMCellMeshFromID
from obi_one.scientific.library.constants import (
    _COORDINATE_CONFIG_FILENAME,
    _SCAN_CONFIG_FILENAME,
)
from obi_one.scientific.tasks.skeletonization.config import SkeletonizationSingleConfig
from obi_one.scientific.tasks.skeletonization.constants import (
    LICENSE_LABEL,
    ROLE_NAME,
)
from obi_one.scientific.tasks.skeletonization.process import (
    create_process_outputs,
    run_process,
)
from obi_one.scientific.tasks.skeletonization.registration import (
    register_output_resource,
)
from obi_one.scientific.tasks.skeletonization.schemas import (
    Metadata,
    ProcessParameters,
    SkeletonizationOutputs,
)

API_URL = "http://my-url"
PAGINATION = {"page": 1, "page_size": 1, "total_items": 1}


def _serialize(obj):
    """JSON-serializable dict from a pydantic model (by_alias for API shape)."""
    return obj.model_dump(mode="json", by_alias=True)


def _asset_json():
    return {
        "id": str(uuid4()),
        "label": "morphology",
        "path": "a.swc",
        "size": 0,
        "content_type": "application/json",
        "is_directory": False,
        "storage_type": "aws_s3_internal",
        "full_path": "/a.swc",
    }


@pytest.fixture
def species():
    return Species(name="Mus musculus", taxonomy_id="NCBITaxon:10090")


@pytest.fixture
def subject(species):
    return Subject(sex=Sex.male, species=species)


@pytest.fixture
def brain_region():
    return BrainRegion(
        name="my-region",
        annotation_value=1,
        acronym="region",
        parent_structure_id=uuid4(),
        hierarchy_id=uuid4(),
        color_hex_triplet="red",
    )


@pytest.fixture
def license_entity():
    return License(
        name="CC BY-NC 4.0",
        description="Attribution-NonCommercial 4.0",
        label=LICENSE_LABEL,
    )


@pytest.fixture
def role():
    return Role(name=ROLE_NAME, role_id="data_modeling_role")


@pytest.fixture
def agent():
    return Person(pref_label="Test User")


@pytest.fixture
def em_dataset_no_slicing():
    """EM dataset without slicing_thickness (protocol branch skipped)."""
    return EMDenseReconstructionDataset(
        name="test-dataset",
        volume_resolution_x_nm=0.1,
        volume_resolution_y_nm=0.1,
        volume_resolution_z_nm=0.1,
        slicing_thickness=None,
        slicing_direction=SlicingDirectionType.coronal,
        tissue_shrinkage=0.1,
    )


@pytest.fixture
def em_dataset_with_slicing():
    """EM dataset with slicing_thickness (protocol branch used)."""
    return EMDenseReconstructionDataset(
        name="test-dataset",
        volume_resolution_x_nm=0.1,
        volume_resolution_y_nm=0.1,
        volume_resolution_z_nm=0.1,
        slicing_thickness=1.0,
        slicing_direction=SlicingDirectionType.coronal,
        tissue_shrinkage=0.1,
    )


@pytest.fixture
def metadata_no_protocol(subject, brain_region, em_dataset_no_slicing):
    return Metadata(
        cell_morphology_name="test-morph",
        cell_morphology_description="desc",
        cell_morphology_protocol_name="Ultraliser skeletonization",
        cell_morphology_protocol_description="proto desc",
        subject=subject,
        brain_region=brain_region,
        em_dense_reconstruction_dataset=em_dataset_no_slicing,
    )


@pytest.fixture
def metadata_with_protocol(subject, brain_region, em_dataset_with_slicing):
    return Metadata(
        cell_morphology_name="test-morph",
        cell_morphology_description="desc",
        cell_morphology_protocol_name="Ultraliser skeletonization",
        cell_morphology_protocol_description="proto desc",
        subject=subject,
        brain_region=brain_region,
        em_dense_reconstruction_dataset=em_dataset_with_slicing,
    )


@pytest.fixture
def protocol_created(metadata_with_protocol):
    dset = metadata_with_protocol.em_dense_reconstruction_dataset
    return DigitalReconstructionCellMorphologyProtocol(
        name=metadata_with_protocol.cell_morphology_protocol_name,
        description=metadata_with_protocol.cell_morphology_protocol_description,
        protocol_design=CellMorphologyProtocolDesign.electron_microscopy,
        slicing_direction=dset.slicing_direction,
        slicing_thickness=dset.slicing_thickness,
        staining_type=StainingType.other,
        tissue_shrinkage=dset.tissue_shrinkage,
    )


@pytest.fixture
def entitysdk_client():
    return Client(
        api_url=API_URL,
        token_manager="token",  # noqa: S106
        project_context=ProjectContext(virtual_lab_id=uuid4(), project_id=uuid4()),
    )


# --- Config fixtures ---


@pytest.fixture
def skeletonization_info():
    return Info(
        campaign_name="Skeletonization test campaign",
        campaign_description="Skeletonization test description",
    )


@pytest.fixture
def single_cell_mesh_id():
    return str(uuid4())


@pytest.fixture
def skeletonization_single_config(tmp_path, skeletonization_info, single_cell_mesh_id):
    """SkeletonizationSingleConfig with a single cell mesh."""
    initialize = SkeletonizationSingleConfig.Initialize(
        cell_mesh=EMCellMeshFromID(id_str=single_cell_mesh_id),
        neuron_voxel_size=0.1,
        spines_voxel_size=0.1,
    )
    return SkeletonizationSingleConfig(
        info=skeletonization_info,
        initialize=initialize,
        coordinate_output_root=tmp_path,
        idx=1,
        single_coordinate_scan_params=SingleCoordinateScanParams(scan_params=[]),
    )


def make_outputs(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    for f in ("a.swc", "a.asc", "a.h5", "a_with_spines.h5"):
        (out / f).touch()
    return SkeletonizationOutputs(
        swc_morphology_file=out / "a.swc",
        asc_morphology_file=out / "a.asc",
        h5_morphology_file=out / "a.h5",
        h5_combined_morphology_file=out / "a_with_spines.h5",
    )


def test_run_process_calls_ultraliser(tmp_path):
    mesh_path = tmp_path / "mesh.obj"
    mesh_path.write_text("dummy")
    params = ProcessParameters(
        mesh_path=mesh_path,
        segment_spines=True,
        neuron_voxel_size=0.1,
        spines_voxel_size=0.1,
    )
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    ultraliser_mock = Mock()

    with patch.dict(sys.modules, {"ultraliser": ultraliser_mock}):
        run_process(params, output_dir)
    ultraliser_mock.skeletonize_neuron_mesh.assert_called_once_with(
        mesh_path=str(mesh_path),
        output_path=str(output_dir),
        segment_spines=True,
        neuron_voxel_size=0.1,
        spines_voxel_size=0.1,
    )


def test_create_process_outputs_raises_when_no_h5(tmp_path):
    with (
        patch(
            "obi_one.scientific.tasks.skeletonization.process.find_file",
            return_value=None,
        ),
        pytest.raises(OBIONEError, match="No combined morphology h5"),
    ):
        create_process_outputs(tmp_path)


def test_create_process_outputs_raises_when_no_swc(tmp_path):
    h5_file = tmp_path / "morph.h5"
    h5_file.touch()

    def find_file(_directory, extension):
        if extension == ".h5":
            return h5_file
        return None

    with (
        patch(
            "obi_one.scientific.tasks.skeletonization.process.find_file",
            side_effect=find_file,
        ),
        pytest.raises(OBIONEError, match="No SWC morphology"),
    ):
        create_process_outputs(tmp_path)


def test_create_process_outputs_success(tmp_path):
    out = tmp_path / "outputs"
    out.mkdir()
    swc_contents = """
1 1  0  0 0 1. -1
2 3  0  0 0 1.  1
3 3  0  5 0 1.  2
"""
    morph = morphio.mut.Morphology(morphio.Morphology(swc_contents, "swc"))
    swc_path = out / "morph.swc"
    morph.write(swc_path)
    morph.write(out / "morph.h5")

    result = create_process_outputs(out)

    assert result.swc_morphology_file == swc_path
    assert result.h5_morphology_file == out / "morph.h5"
    assert result.asc_morphology_file == out / "morph.asc"
    assert result.h5_combined_morphology_file == out / "morph.h5"
    assert result.h5_morphology_file.exists()
    assert result.asc_morphology_file.exists()
    assert (out / "morph_with_spines.h5").exists()


def test_register_output_resource_creates_protocol_when_missing(
    tmp_path,
    httpx_mock,
    entitysdk_client,
    role,
    license_entity,
    agent,
    metadata_with_protocol,
):
    morphology_id = uuid4()
    role_json = _serialize(role)
    license_json = _serialize(license_entity)
    agent_json = _serialize(agent)

    httpx_mock.add_response(
        url=f"{API_URL}/role?name=data+modeling+role&page=1",
        json={"data": [role_json], "pagination": PAGINATION},
    )
    httpx_mock.add_response(
        url=f"{API_URL}/license?label=CC+BY-NC+4.0&page=1",
        json={"data": [license_json], "pagination": PAGINATION},
    )
    httpx_mock.add_response(
        url=f"{API_URL}/cell-morphology-protocol?name=Ultraliser+skeletonization&page=1",
        method="GET",
        json={"data": [], "pagination": PAGINATION},
    )
    httpx_mock.add_callback(
        lambda r: httpx.Response(
            status_code=200,
            json=json.loads(r.content) | {"id": str(uuid4())},
        ),
        url=f"{API_URL}/cell-morphology-protocol",
        method="POST",
    )
    httpx_mock.add_callback(
        lambda r: httpx.Response(
            status_code=200,
            json=json.loads(r.content) | {"id": str(morphology_id), "created_by": agent_json},
        ),
        url=f"{API_URL}/cell-morphology",
        method="POST",
    )
    httpx_mock.add_callback(
        lambda r: httpx.Response(
            status_code=200,
            json=json.loads(r.content)
            | {"id": str(uuid4()), "role": role_json, "agent": agent_json},
        ),
        url=f"{API_URL}/contribution",
        method="POST",
    )
    for _ in range(4):
        httpx_mock.add_response(
            url=f"{API_URL}/cell-morphology/{morphology_id}/assets",
            method="POST",
            json=_asset_json(),
        )

    outputs = make_outputs(tmp_path)
    result = register_output_resource(entitysdk_client, metadata_with_protocol, outputs)

    assert result.id == morphology_id
    assert result.created_by is not None
    assert result.name == metadata_with_protocol.cell_morphology_name


def test_register_output_resource_reuses_existing_protocol(
    tmp_path,
    httpx_mock,
    entitysdk_client,
    role,
    license_entity,
    agent,
    metadata_with_protocol,
    protocol_created,
):
    morphology_id = uuid4()
    role_json = _serialize(role)
    license_json = _serialize(license_entity)
    agent_json = _serialize(agent)
    protocol_json = _serialize(protocol_created)

    httpx_mock.add_response(
        url=f"{API_URL}/role?name=data+modeling+role&page=1",
        json={"data": [role_json], "pagination": PAGINATION},
    )
    httpx_mock.add_response(
        url=f"{API_URL}/license?label=CC+BY-NC+4.0&page=1",
        json={"data": [license_json], "pagination": PAGINATION},
    )
    httpx_mock.add_response(
        url=f"{API_URL}/cell-morphology-protocol?name=Ultraliser+skeletonization&page=1",
        method="GET",
        json={"data": [protocol_json], "pagination": PAGINATION},
    )
    httpx_mock.add_callback(
        lambda r: httpx.Response(
            status_code=200,
            json=json.loads(r.content) | {"id": str(morphology_id), "created_by": agent_json},
        ),
        url=f"{API_URL}/cell-morphology",
        method="POST",
    )
    httpx_mock.add_callback(
        lambda r: httpx.Response(
            status_code=200,
            json=json.loads(r.content)
            | {"id": str(uuid4()), "role": role_json, "agent": agent_json},
        ),
        url=f"{API_URL}/contribution",
        method="POST",
    )
    for _ in range(4):
        httpx_mock.add_response(
            url=f"{API_URL}/cell-morphology/{morphology_id}/assets",
            method="POST",
            json=_asset_json(),
        )

    outputs = make_outputs(tmp_path)
    result = register_output_resource(entitysdk_client, metadata_with_protocol, outputs)

    assert result.id == morphology_id
    assert result.name == metadata_with_protocol.cell_morphology_name


def test_register_output_resource_skips_protocol_when_no_dataset(
    tmp_path,
    httpx_mock,
    entitysdk_client,
    role,
    license_entity,
    agent,
    metadata_no_protocol,
):
    morphology_id = uuid4()
    role_json = _serialize(role)
    license_json = _serialize(license_entity)
    agent_json = _serialize(agent)

    httpx_mock.add_response(
        url=f"{API_URL}/role?name=data+modeling+role&page=1",
        json={"data": [role_json], "pagination": PAGINATION},
    )
    httpx_mock.add_response(
        url=f"{API_URL}/license?label=CC+BY-NC+4.0&page=1",
        json={"data": [license_json], "pagination": PAGINATION},
    )
    httpx_mock.add_callback(
        lambda r: httpx.Response(
            status_code=200,
            json=json.loads(r.content) | {"id": str(morphology_id), "created_by": agent_json},
        ),
        url=f"{API_URL}/cell-morphology",
        method="POST",
    )
    httpx_mock.add_callback(
        lambda r: httpx.Response(
            status_code=200,
            json=json.loads(r.content)
            | {"id": str(uuid4()), "role": role_json, "agent": agent_json},
        ),
        url=f"{API_URL}/contribution",
        method="POST",
    )
    for _ in range(4):
        httpx_mock.add_response(
            url=f"{API_URL}/cell-morphology/{morphology_id}/assets",
            method="POST",
            json=_asset_json(),
        )

    outputs = make_outputs(tmp_path)
    result = register_output_resource(entitysdk_client, metadata_no_protocol, outputs)

    assert result.id == morphology_id
    assert result.name == metadata_no_protocol.cell_morphology_name


def _em_cell_mesh_json(mesh_id: str):
    return {
        "id": mesh_id,
        "name": "test-mesh",
        "release_version": 1,
        "dense_reconstruction_cell_id": 123,
        "generation_method": "marching_cubes",
        "level_of_detail": 1,
        "mesh_type": "static",
    }


def test_create_campaign_entity_with_config_single_mesh(
    tmp_path, httpx_mock, entitysdk_client, skeletonization_single_config, single_cell_mesh_id
):
    """Fetch a single cell_mesh, register campaign and upload config."""
    campaign_id = uuid4()
    output_root = tmp_path / "scan"
    output_root.mkdir()
    (output_root / _SCAN_CONFIG_FILENAME).write_text("{}")

    httpx_mock.add_response(
        url=f"{API_URL}/em-cell-mesh/{single_cell_mesh_id}",
        method="GET",
        json=_em_cell_mesh_json(single_cell_mesh_id),
    )
    httpx_mock.add_callback(
        lambda r: httpx.Response(
            status_code=200,
            json=json.loads(r.content) | {"id": str(campaign_id)},
        ),
        url=f"{API_URL}/skeletonization-campaign",
        method="POST",
    )
    httpx_mock.add_response(
        url=f"{API_URL}/skeletonization-campaign/{campaign_id}/assets",
        method="POST",
        json=_asset_json()
        | {
            "label": "campaign_generation_config",
            "path": _SCAN_CONFIG_FILENAME,
        },
    )

    campaign = skeletonization_single_config.create_campaign_entity_with_config(
        output_root=output_root,
        db_client=entitysdk_client,
    )

    assert campaign.id == campaign_id
    assert campaign.name == skeletonization_single_config.info.campaign_name


def test_create_campaign_generation_entity(
    tmp_path, httpx_mock, entitysdk_client, skeletonization_single_config, single_cell_mesh_id
):
    """create_campaign_generation_entity registers SkeletonizationConfigGeneration."""
    campaign_id = uuid4()
    config_id_1, config_id_2 = uuid4(), uuid4()
    output_root = tmp_path / "scan"
    output_root.mkdir()
    (output_root / _SCAN_CONFIG_FILENAME).write_text("{}")

    httpx_mock.add_response(
        url=f"{API_URL}/em-cell-mesh/{single_cell_mesh_id}",
        method="GET",
        json=_em_cell_mesh_json(single_cell_mesh_id),
    )
    httpx_mock.add_callback(
        lambda r: httpx.Response(
            status_code=200,
            json=json.loads(r.content) | {"id": str(campaign_id)},
        ),
        url=f"{API_URL}/skeletonization-campaign",
        method="POST",
    )
    httpx_mock.add_response(
        url=f"{API_URL}/skeletonization-campaign/{campaign_id}/assets",
        method="POST",
        json=_asset_json()
        | {
            "label": "campaign_generation_config",
            "path": _SCAN_CONFIG_FILENAME,
        },
    )

    skeletonization_single_config.create_campaign_entity_with_config(
        output_root=output_root,
        db_client=entitysdk_client,
    )

    httpx_mock.add_callback(
        lambda r: httpx.Response(
            status_code=200,
            json=json.loads(r.content) | {"id": str(uuid4())},
        ),
        url=f"{API_URL}/skeletonization-config-generation",
        method="POST",
    )

    config_payloads = [
        {
            "id": str(config_id_1),
            "skeletonization_campaign_id": str(campaign_id),
            "em_cell_mesh_id": single_cell_mesh_id,
            "scan_parameters": {},
        },
        {
            "id": str(config_id_2),
            "skeletonization_campaign_id": str(campaign_id),
            "em_cell_mesh_id": single_cell_mesh_id,
            "scan_parameters": {},
        },
    ]
    skeletonization_single_config.create_campaign_generation_entity(
        skeletonization_configs=[SkeletonizationConfig.model_validate(c) for c in config_payloads],
        db_client=entitysdk_client,
    )

    requests = [r for r in httpx_mock.get_requests() if r.method == "POST"]
    assert any("skeletonization-config-generation" in str(r.url) for r in requests)


def test_create_single_entity_with_config(
    tmp_path, httpx_mock, entitysdk_client, skeletonization_single_config, single_cell_mesh_id
):
    """Register SkeletonizationConfig and uploads coordinate config."""
    campaign_id = uuid4()
    config_id = uuid4()
    output_root = tmp_path / "scan"
    output_root.mkdir()
    (output_root / _SCAN_CONFIG_FILENAME).write_text("{}")
    coord_path = tmp_path / _COORDINATE_CONFIG_FILENAME
    coord_path.write_text("{}")

    httpx_mock.add_response(
        url=f"{API_URL}/em-cell-mesh/{single_cell_mesh_id}",
        method="GET",
        json=_em_cell_mesh_json(single_cell_mesh_id),
    )
    httpx_mock.add_callback(
        lambda r: httpx.Response(
            status_code=200,
            json=json.loads(r.content) | {"id": str(campaign_id)},
        ),
        url=f"{API_URL}/skeletonization-campaign",
        method="POST",
    )
    httpx_mock.add_response(
        url=f"{API_URL}/skeletonization-campaign/{campaign_id}/assets",
        method="POST",
        json=_asset_json()
        | {
            "label": "campaign_generation_config",
            "path": _SCAN_CONFIG_FILENAME,
        },
    )

    campaign = skeletonization_single_config.create_campaign_entity_with_config(
        output_root=output_root,
        db_client=entitysdk_client,
    )

    httpx_mock.add_callback(
        lambda r: httpx.Response(
            status_code=200,
            json=json.loads(r.content) | {"id": str(config_id)},
        ),
        url=f"{API_URL}/skeletonization-config",
        method="POST",
    )
    httpx_mock.add_response(
        url=f"{API_URL}/skeletonization-config/{config_id}/assets",
        method="POST",
        json=_asset_json()
        | {
            "id": str(uuid4()),
            "label": "skeletonization_config",
            "path": _COORDINATE_CONFIG_FILENAME,
        },
    )

    # set coordinate_output_root so upload path exists
    skeletonization_single_config.coordinate_output_root = tmp_path
    skeletonization_single_config.create_single_entity_with_config(
        campaign=campaign,
        db_client=entitysdk_client,
    )

    assert skeletonization_single_config.single_entity.id == config_id
    requests = httpx_mock.get_requests()
    asset_uploads = [
        r for r in requests if "/skeletonization-config/" in str(r.url) and r.method == "POST"
    ]
    assert len(asset_uploads) >= 1
