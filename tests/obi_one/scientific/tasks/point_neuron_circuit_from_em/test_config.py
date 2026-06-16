import pytest
from pydantic import ValidationError

from obi_one.core.exception import OBIONEError
from obi_one.core.info import Info
from obi_one.scientific.from_id.em_cell_mesh_from_id import EMCellMeshFromID
from obi_one.scientific.from_id.named_tuple_from_id import PointNeuronCircuitFromEMInputNamedTuple
from obi_one.scientific.tasks.point_neuron_circuit_from_em.config import (
    PointNeuronCircuitFromEMScanConfig,
    PointNeuronCircuitFromEMSingleConfig,
)

_INFO = Info(campaign_name="test", campaign_description="test")


def _mesh(id_str="00001"):
    return EMCellMeshFromID(id_str=id_str)


class TestPointNeuronCircuitFromEMConfig:
    def test_valid_config_single_mesh(self, tmp_path):
        cfg = PointNeuronCircuitFromEMSingleConfig(
            info=_INFO,
            coordinate_output_root=tmp_path,
            initialize=PointNeuronCircuitFromEMSingleConfig.Initialize(
                cell_meshes=PointNeuronCircuitFromEMInputNamedTuple(
                    name="one mesh",
                    elements=(_mesh(),),
                ),
            ),
        )
        assert len(cfg.initialize.cell_meshes) == 1

    def test_valid_config_multiple_meshes(self, tmp_path):
        cfg = PointNeuronCircuitFromEMSingleConfig(
            info=_INFO,
            coordinate_output_root=tmp_path,
            initialize=PointNeuronCircuitFromEMSingleConfig.Initialize(
                cell_meshes=PointNeuronCircuitFromEMInputNamedTuple(
                    name="three meshes",
                    elements=(_mesh(), _mesh("00002"), _mesh("00003")),
                ),
            ),
        )
        assert len(cfg.initialize.cell_meshes) == 3
        assert all(isinstance(m, EMCellMeshFromID) for m in cfg.initialize.cell_meshes.elements)

    def test_min_length_validation(self, tmp_path):
        with pytest.raises(ValidationError, match=r"at least 1 item|too_short"):
            PointNeuronCircuitFromEMSingleConfig(
                info=_INFO,
                coordinate_output_root=tmp_path,
                initialize=PointNeuronCircuitFromEMSingleConfig.Initialize(
                    cell_meshes=PointNeuronCircuitFromEMInputNamedTuple(
                        name="no element - bad config",
                        elements=(),
                    ),
                ),
            )

    def test_scan_over_mesh_sets_requires_unique_names(self):
        with pytest.raises(OBIONEError, match="unique names"):
            PointNeuronCircuitFromEMScanConfig.Initialize(
                cell_meshes=[
                    PointNeuronCircuitFromEMInputNamedTuple(name="dup", elements=(_mesh(),)),
                    PointNeuronCircuitFromEMInputNamedTuple(name="dup", elements=(_mesh("00002"),)),
                ],
            )
