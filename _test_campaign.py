"""Quick test of campaign entity registration."""
from unittest.mock import MagicMock, patch
from pathlib import Path
from entitysdk.models import TaskConfig
from entitysdk.types import TaskConfigType
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.config import EModelOptimizationScanConfig, EModelOptimizationSingleConfig
from obi_one.scientific.tasks.emodel_building.task2_emodel_optimization.blocks import OptimizationInitialize, MorphologySelection, ParametersSelection
from obi_one.scientific.from_id.task_result_from_id import TaskResultFromID
from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID
from obi_one.scientific.from_id.species_from_id import SpeciesFromID
from obi_one.scientific.from_id.brain_region_from_id import BrainRegionFromID
from obi_one.scientific.from_id.etype_class_from_id import ETypeClassFromID
from obi_one.scientific.from_id.ion_channel_model_from_id import IonChannelModelFromID

config = EModelOptimizationScanConfig(
    info=EModelOptimizationScanConfig.model_fields['info'].annotation(
        campaign_name='T', campaign_description='T',
    ),
    initialize=OptimizationInitialize(
        extraction_task_result=TaskResultFromID(id_str='812a8721-1681-49a2-a155-59ab30981079'),
        emodel='TestEModel',
        species=SpeciesFromID(id_str='11111111-2222-3333-4444-555566667777'),
        brain_region=BrainRegionFromID(id_str='22222222-3333-4444-5555-666677778888'),
        etype=ETypeClassFromID(id_str='33333333-4444-5555-6666-777788889999'),
    ),
    morphology_selection=MorphologySelection(
        morphology=CellMorphologyFromID(id_str='492bdec5-2dce-4ae0-8b85-f020a1ad1d92'),
    ),
    parameters_selection=ParametersSelection(
        ion_channel_models=(IonChannelModelFromID(id_str='55555555-6666-7777-8888-999900001111'),),
    ),
)

mock_client = MagicMock()
mock_client.register_entity.return_value = MagicMock(id='campaign-123')

with patch.object(EModelOptimizationScanConfig, 'input_entities', return_value=[MagicMock(id='e-1')]):
    config.create_campaign_entity_with_config(output_root=Path('/tmp/out'), db_client=mock_client)

print('register_entity called:', mock_client.register_entity.called)
print('upload_content called:', mock_client.upload_content.called)
reg_arg = mock_client.register_entity.call_args[0][0]
print('type:', type(reg_arg).__name__)
print('task_config_type:', reg_arg.task_config_type)
print('SUCCESS')
