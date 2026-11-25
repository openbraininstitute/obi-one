from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from entitysdk import models

from obi_one.core.run_tasks import run_task_type
from obi_one.scientific.tasks.em_cell_mesh_conversion.config import (
    EMCellMeshConversionSingleConfig,
)
from obi_one.scientific.tasks.em_cell_mesh_conversion.task import EMCellMeshConversionTask
from obi_one.types import TaskType


def test_the_launched_task_reads_the_config_the_endpoint_writes(tmp_path):
    """The JSON the convert endpoint uploads is what the launch script turns back into the task."""
    mesh_id = uuid4()
    config_json = EMCellMeshConversionSingleConfig(em_cell_mesh_id=mesh_id).model_dump_json()
    task_config = SimpleNamespace(id=uuid4())
    db_client = Mock()
    db_client.get_entity.return_value = task_config
    db_client.select_assets.return_value.one.return_value = SimpleNamespace(id=uuid4())
    db_client.download_content.return_value = config_json.encode()

    with patch.object(EMCellMeshConversionTask, "execute", autospec=True) as execute:
        run_task_type(
            task_type=TaskType.em_cell_mesh_conversion,
            entity_type=models.TaskConfig,
            entity_id=str(task_config.id),
            scan_output_root=str(tmp_path),
            db_client=db_client,
            execution_activity_id=str(uuid4()),
        )

    task = execute.call_args.args[0]
    assert isinstance(task.config, EMCellMeshConversionSingleConfig)
    assert task.config.em_cell_mesh_id == mesh_id
    assert task.config.coordinate_output_root == tmp_path / "0"
    assert task.config.single_entity is task_config
