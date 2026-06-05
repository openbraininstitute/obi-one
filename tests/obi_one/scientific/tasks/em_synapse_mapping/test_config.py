import pytest
from pydantic import ValidationError

from obi_one.core.info import Info
from obi_one.scientific.from_id.cell_morphology_from_id import CellMorphologyFromID
from obi_one.scientific.from_id.memodel_from_id import MEModelFromID
from obi_one.scientific.from_id.named_tuple_from_id import EMSynapseMappingInputNamedTuple
from obi_one.scientific.tasks.em_synapse_mapping.config import EMSynapseMappingSingleConfig

_INFO = Info(campaign_name="test", campaign_description="test")


def _morph(id_str="00001"):
    return CellMorphologyFromID(id_str=id_str)


def _memodel(id_str="00002"):
    return MEModelFromID(id_str=id_str)


class TestEMSynapseMappingConfig:
    def test_valid_config_single_neuron(self, tmp_path):
        cfg = EMSynapseMappingSingleConfig(
            info=_INFO,
            coordinate_output_root=tmp_path,
            initialize=EMSynapseMappingSingleConfig.Initialize(
                neurons=EMSynapseMappingInputNamedTuple(
                    name="one morph",
                    elements=(_morph(),),
                ),
            ),
        )
        assert len(cfg.initialize.neurons) == 1

    def test_valid_config_with_morphologies(self, tmp_path):
        cfg = EMSynapseMappingSingleConfig(
            info=_INFO,
            coordinate_output_root=tmp_path,
            initialize=EMSynapseMappingSingleConfig.Initialize(
                neurons=EMSynapseMappingInputNamedTuple(
                    name="two morph",
                    elements=(_morph(), _morph("00003")),
                ),
            ),
        )
        assert len(cfg.initialize.neurons) == 2

    def test_valid_config_with_mixed_types(self, tmp_path):
        cfg = EMSynapseMappingSingleConfig(
            info=_INFO,
            coordinate_output_root=tmp_path,
            initialize=EMSynapseMappingSingleConfig.Initialize(
                neurons=EMSynapseMappingInputNamedTuple(
                    name="one morph, one emodel",
                    elements=(_morph(), _memodel()),
                ),
            ),
        )
        assert isinstance(cfg.initialize.neurons[0], CellMorphologyFromID)
        assert isinstance(cfg.initialize.neurons[1], MEModelFromID)

    def test_min_length_validation(self, tmp_path):
        with pytest.raises(
            ValidationError, match=r"ensure this value has at least 1 item|too_short"
        ):
            EMSynapseMappingSingleConfig(
                info=_INFO,
                coordinate_output_root=tmp_path,
                initialize=EMSynapseMappingSingleConfig.Initialize(
                    neurons=EMSynapseMappingInputNamedTuple(
                        name="no element - bad config",
                        elements=(),
                    ),
                ),
            )

    def test_defaults(self, tmp_path):
        cfg = EMSynapseMappingSingleConfig(
            info=_INFO,
            coordinate_output_root=tmp_path,
            initialize=EMSynapseMappingSingleConfig.Initialize(
                neurons=EMSynapseMappingInputNamedTuple(
                    name="one morph, one emodel",
                    elements=(_morph(), _memodel()),
                ),
            ),
        )
        init = cfg.initialize
        assert init.physical_edge_population_name == "physical_connections"
        assert init.virtual_edge_population_name == "virtual_afferents"
        assert init.biophysical_node_population == "biophysical_neurons"
        assert init.virtual_node_population == "virtual_afferent_neurons"
