import pytest
from pydantic import ValidationError

from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.tasks.em_synapse_mapping.config import EMSynapseMappingMultipleConfig


def _morph(id_str="00001"):
    return CellMorphologyFromID(id_str=id_str)


def _memodel(id_str="00002"):
    return MEModelFromID(id_str=id_str)


class TestEMSynapseMappingMultipleConfig:
    def test_valid_config_with_morphologies(self, tmp_path):
        cfg = EMSynapseMappingMultipleConfig(
            coordinate_output_root=tmp_path,
            initialize=EMSynapseMappingMultipleConfig.Initialize(
                neurons=(_morph(), _morph("00003")),
            ),
        )
        assert len(cfg.initialize.neurons) == 2

    def test_valid_config_with_mixed_types(self, tmp_path):
        cfg = EMSynapseMappingMultipleConfig(
            coordinate_output_root=tmp_path,
            initialize=EMSynapseMappingMultipleConfig.Initialize(
                neurons=(_morph(), _memodel()),
            ),
        )
        assert isinstance(cfg.initialize.neurons[0], CellMorphologyFromID)
        assert isinstance(cfg.initialize.neurons[1], MEModelFromID)

    def test_min_length_validation(self, tmp_path):
        with pytest.raises(
            ValidationError, match="ensure this value has at least 2 items|too_short"
        ):
            EMSynapseMappingMultipleConfig(
                coordinate_output_root=tmp_path,
                initialize=EMSynapseMappingMultipleConfig.Initialize(
                    neurons=(_morph(),),
                ),
            )

    def test_defaults(self, tmp_path):
        cfg = EMSynapseMappingMultipleConfig(
            coordinate_output_root=tmp_path,
            initialize=EMSynapseMappingMultipleConfig.Initialize(
                neurons=(_morph(), _memodel()),
            ),
        )
        init = cfg.initialize
        assert init.physical_edge_population_name == "physical_connections"
        assert init.virtual_edge_population_name == "virtual_afferents"
        assert init.biophysical_node_population == "biophysical_neurons"
        assert init.virtual_node_population == "virtual_afferent_neurons"

    def test_enforce_no_multi_param(self, tmp_path):
        cfg = EMSynapseMappingMultipleConfig(
            coordinate_output_root=tmp_path,
            initialize=EMSynapseMappingMultipleConfig.Initialize(
                neurons=(_morph(), _memodel()),
            ),
        )
        # Should not raise
        cfg.enforce_no_multi_param()
