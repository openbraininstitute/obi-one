"""What a deployed service does for the AIND ephys tasks."""

import uuid
from http import HTTPStatus
from pathlib import Path
from unittest.mock import Mock

import pytest
from entitysdk import models
from entitysdk.types import AssetLabel
from pydantic import ValidationError

from app import mappings
from app.errors import ApiError
from app.mappings import TASK_DEFINITIONS
from app.schemas.task import TaskAccountingCreate, TaskLaunchSubmit
from app.services import task as task_service
from app.services.resource_estimation import aind_ephys as test_module
from app.services.resource_estimation.circuit_extraction import CPU_MEMORY_COMBINATIONS
from app.types import TaskType
from obi_one.core.info import Info
from obi_one.core.scan_generation import GridScanGenerationTask
from obi_one.scientific.from_id.extracellular_recording_from_id import (
    ExtracellularRecordingFromID,
)
from obi_one.scientific.from_id.task_result_from_id import TaskResultFromID
from obi_one.scientific.tasks.aind_ephys._02_preprocessing.config import (
    AINDEPhysPreprocessingScanConfig,
    AINDEPhysPreprocessingSingleConfig,
)
from obi_one.scientific.tasks.aind_ephys._03_spikesorting.kilosort4.config import (
    AINDEPhysSpikeSortingKilosort4ScanConfig,
    AINDEPhysSpikeSortingKilosort4SingleConfig,
)
from obi_one.scientific.tasks.aind_ephys._03_spikesorting.lupin.config import (
    AINDEPhysSpikeSortingLupinScanConfig,
    AINDEPhysSpikeSortingLupinSingleConfig,
)
from obi_one.scientific.tasks.aind_ephys._03_spikesorting.spykingcircus2.config import (
    AINDEPhysSpikeSortingSpykingCircus2ScanConfig,
    AINDEPhysSpikeSortingSpykingCircus2SingleConfig,
)

SORTING = TaskType.aind_ephys_spikesorting_spykingcircus2
AIND_TASK_TYPES = [TaskType.aind_ephys_preprocessing, SORTING]
INFO = Info(campaign_name="Test campaign", campaign_description="Test campaign.")
GB = 10**9


def db_client(*, inputs, nwb_gb=0.0, result_file_gbs=()):
    """A client for a config with these inputs, and a recording and a result of these sizes."""
    client = Mock()
    entities = {
        models.TaskConfig: Mock(inputs=inputs),
        models.ExtracellularRecording: Mock(),
        models.TaskResult: Mock(),
    }
    client.get_entity.side_effect = lambda entity_id, entity_type: entities[entity_type]  # ruff: ignore[unused-lambda-argument]
    client.select_assets.return_value.one.return_value = Mock(size=int(nwb_gb * GB))
    client.list_directory.return_value = Mock(
        files={str(i): Mock(size=int(gb * GB)) for i, gb in enumerate(result_file_gbs)}
    )
    return client


def estimate(task_type, client):
    return test_module.estimate_task_resources(
        json_model=Mock(config_id=uuid.uuid4()),
        db_client=client,
        task_definition=TASK_DEFINITIONS[task_type],
        compute_cell="cell_a",
    )


@pytest.mark.parametrize(
    ("form", "single_config_class"),
    [
        (
            AINDEPhysPreprocessingScanConfig(
                info=INFO,
                initialize=AINDEPhysPreprocessingScanConfig.Initialize(
                    recording=ExtracellularRecordingFromID(id_str=str(uuid.uuid4()))
                ),
            ),
            AINDEPhysPreprocessingSingleConfig,
        ),
        *(
            (
                scan_config_class(
                    info=INFO,
                    initialize=scan_config_class.Initialize(
                        preprocessing_result=TaskResultFromID(id_str=str(uuid.uuid4()))
                    ),
                ),
                single_config_class,
            )
            for scan_config_class, single_config_class in (
                (
                    AINDEPhysSpikeSortingKilosort4ScanConfig,
                    AINDEPhysSpikeSortingKilosort4SingleConfig,
                ),
                (
                    AINDEPhysSpikeSortingSpykingCircus2ScanConfig,
                    AINDEPhysSpikeSortingSpykingCircus2SingleConfig,
                ),
                (AINDEPhysSpikeSortingLupinScanConfig, AINDEPhysSpikeSortingLupinSingleConfig),
            )
        ),
    ],
)
def test_the_service_generates_the_configs(form, single_config_class, tmp_path):
    scan = GridScanGenerationTask(
        form=form, output_root=tmp_path, coordinate_directory_option="ZERO_INDEX"
    )

    scan.execute()

    (single_config,) = scan.single_configs
    assert isinstance(single_config, single_config_class)


@pytest.mark.parametrize("task_type", AIND_TASK_TYPES)
def test_the_launch_job_installs_the_sorting_dependencies(task_type):
    definition = TASK_DEFINITIONS[task_type]
    repo = Path(mappings.__file__).resolve().parents[1]

    dependencies = (repo / definition.code.dependencies).read_text()

    assert (repo / definition.code.path).is_file()
    assert "obi-one[spike-sorting]" in dependencies
    assert "spikeinterface==" in dependencies
    assert definition.code.ref.startswith("tag:")


@pytest.mark.parametrize("task_type", AIND_TASK_TYPES)
def test_the_machine_is_one_the_launch_system_accepts(task_type):
    resources = TASK_DEFINITIONS[task_type].resources

    assert resources.memory in CPU_MEMORY_COMBINATIONS[resources.cores]


@pytest.mark.parametrize("request_model", [TaskLaunchSubmit, TaskAccountingCreate])
@pytest.mark.parametrize(
    "task_type",
    [TaskType.aind_ephys_spikesorting_kilosort4, TaskType.aind_ephys_spikesorting_lupin],
)
def test_sorters_the_launch_job_does_not_install_cannot_be_launched(task_type, request_model):
    with pytest.raises(ValidationError, match="not launchable"):
        request_model(task_type=task_type, config_id=uuid.uuid4())


class TestEstimate:
    def test_a_small_recording_fits_the_default_disk(self):
        client = db_client(inputs=[Mock(id=uuid.uuid4())], nwb_gb=0.42)

        resources = estimate(TaskType.aind_ephys_preprocessing, client)

        client.select_assets.assert_called_once()
        assert client.select_assets.call_args.kwargs["selection"] == {"label": AssetLabel.nwb}
        assert resources.ephemeral_storage is None
        assert resources.timelimit == "01:00"
        assert resources.compute_cell == "cell_a"

    def test_a_larger_recording_asks_for_disk_and_time(self):
        client = db_client(inputs=[Mock(id=uuid.uuid4())], nwb_gb=10.0)

        resources = estimate(TaskType.aind_ephys_preprocessing, client)

        assert resources.ephemeral_storage == 50
        assert resources.timelimit == "03:00"

    def test_sorting_adds_up_the_result_folder(self):
        client = db_client(inputs=[Mock(id=uuid.uuid4())], result_file_gbs=(10.0, 10.0))

        resources = estimate(SORTING, client)

        assert client.select_assets.call_args.kwargs["selection"] == {
            "label": AssetLabel.task_result
        }
        assert resources.ephemeral_storage == 50
        assert resources.timelimit == "11:00"

    def test_a_config_without_an_input_keeps_the_defaults(self):
        resources = estimate(SORTING, db_client(inputs=[]))

        definition = TASK_DEFINITIONS[SORTING].resources
        assert resources.ephemeral_storage is None
        assert resources.timelimit == definition.timelimit

    def test_an_input_too_large_for_any_task_is_refused(self):
        client = db_client(inputs=[Mock(id=uuid.uuid4())], nwb_gb=100.0)

        with pytest.raises(ApiError) as error:
            estimate(TaskType.aind_ephys_preprocessing, client)

        assert error.value.http_status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert "100 GB" in error.value.message

    @pytest.mark.parametrize("task_type", AIND_TASK_TYPES)
    def test_the_task_service_uses_the_estimate_and_pins_the_placement(self, task_type):
        resources = task_service.estimate_task_resources(
            json_model=Mock(config_id=uuid.uuid4()),
            db_client=db_client(inputs=[]),
            task_definition=TASK_DEFINITIONS[task_type],
            compute_cell="cell_a",
        )

        assert resources.placement_type == "fargate"
