"""Cover ``entitysdk_class()`` and ``fetch`` on FromID wrappers touched by typed-entity refactor."""

from unittest.mock import MagicMock
from uuid import UUID

import pytest
from entitysdk.models import (
    BrainRegion,
    CellMorphology,
    Circuit,
    EMDenseReconstructionDataset,
    EMCellMesh,
    ElectricalCellRecording,
    ETypeClass,
    IonChannelModel,
    IonChannelRecording,
    MEModel,
    SimulatableExtracellularRecordingArray,
    Species,
    TaskConfig,
    TaskResult,
)

from obi_one.scientific.from_id.brain_region_from_id import BrainRegionFromID
from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID
from obi_one.scientific.from_id.circuit_from_id import (
    CircuitFromID,
    MEModelWithSynapsesCircuitFromID,
)
from obi_one.scientific.from_id.electrical_cell_recording_from_id import (
    ElectricalCellRecordingFromID,
)
from obi_one.scientific.from_id.em_cell_mesh_from_id import EMCellMeshFromID
from obi_one.scientific.from_id.em_dataset_from_id import EMDataSetFromID
from obi_one.scientific.from_id.etype_class_from_id import ETypeClassFromID
from obi_one.scientific.from_id.extracellular_recording_array_from_id import (
    SimulatableExtracellularRecordingArrayFromID,
)
from obi_one.scientific.from_id.ion_channel_model_from_id import IonChannelModelFromID
from obi_one.scientific.from_id.ion_channel_recording_from_id import IonChannelRecordingFromID
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.from_id.species_from_id import SpeciesFromID
from obi_one.scientific.from_id.task_config_from_id import TaskConfigFromID
from obi_one.scientific.from_id.task_result_from_id import TaskResultFromID

_TEST_ID = "00000000-0000-0000-0000-000000000099"
_TEST_UUID = UUID(_TEST_ID)

ENTITYSDK_CLASS_CASES = (
    (SpeciesFromID, Species),
    (BrainRegionFromID, BrainRegion),
    (ETypeClassFromID, ETypeClass),
    (CircuitFromID, Circuit),
    (MEModelWithSynapsesCircuitFromID, Circuit),
    (CellMorphologyFromID, CellMorphology),
    (EMDataSetFromID, EMDenseReconstructionDataset),
    (EMCellMeshFromID, EMCellMesh),
    (ElectricalCellRecordingFromID, ElectricalCellRecording),
    (IonChannelModelFromID, IonChannelModel),
    (IonChannelRecordingFromID, IonChannelRecording),
    (MEModelFromID, MEModel),
    (TaskConfigFromID, TaskConfig),
    (TaskResultFromID, TaskResult),
    (SimulatableExtracellularRecordingArrayFromID, SimulatableExtracellularRecordingArray),
)


class TestFromIDEntitysdkClass:
    @pytest.mark.parametrize(("from_id_cls", "expected_type"), ENTITYSDK_CLASS_CASES)
    def test_entitysdk_class_returns_entitysdk_model(self, from_id_cls, expected_type):
        assert from_id_cls.entitysdk_class() is expected_type

    @pytest.mark.parametrize(("from_id_cls", "expected_type"), ENTITYSDK_CLASS_CASES)
    def test_fetch_passes_uuid_and_entity_type(self, from_id_cls, expected_type):
        client = MagicMock()
        client.get_entity.return_value = MagicMock()
        from_id_cls.fetch(_TEST_ID, client)
        client.get_entity.assert_called_once_with(
            entity_id=_TEST_UUID,
            entity_type=expected_type,
        )
