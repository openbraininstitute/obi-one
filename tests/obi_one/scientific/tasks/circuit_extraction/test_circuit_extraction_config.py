"""Unit tests for circuit extraction scan config helpers in config.py."""

from unittest.mock import Mock

import pytest

from obi_one.core.exception import OBIONEError
from obi_one.core.info import Info
from obi_one.scientific.blocks.neuron_sets.base import NeuronSetPopulationType
from obi_one.scientific.blocks.neuron_sets.combined import (
    BiophysicalCombinedNeuronSet,
    PointCombinedNeuronSet,
    SetOperation,
)
from obi_one.scientific.blocks.neuron_sets.deprecated import PredefinedNeuronSet
from obi_one.scientific.blocks.neuron_sets.specific import (
    AllBiophysicalNeurons,
    AllPointNeurons,
)
from obi_one.scientific.from_id.circuit_from_id import CircuitFromID
from obi_one.scientific.library.circuit import Circuit as OBICircuit
from obi_one.scientific.tasks.circuit_extraction.config import CircuitExtractionScanConfig
from obi_one.scientific.unions_and_references.neuron_sets import (
    BiophysicalNeuronSetReference,
    PointNeuronSetReference,
)

from tests.utils import CIRCUIT_DIR


def _minimal_config(**init_kwargs) -> CircuitExtractionScanConfig:
    config = CircuitExtractionScanConfig.empty_config()
    config.set(
        Info(campaign_name="cfg-test", campaign_description="config unit tests"),
        name="info",
    )
    init = CircuitExtractionScanConfig.Initialize(
        circuit=OBICircuit(
            name="N_10__top_nodes_dim6",
            path=str(CIRCUIT_DIR / "N_10__top_nodes_dim6" / "circuit_config.json"),
        ),
        neuron_set=None,
        do_virtual=False,
        create_external=False,
        **init_kwargs,
    )
    config.set(init, name="initialize")
    return CircuitExtractionScanConfig.model_validate(config.model_dump())


class TestCircuitExtractionScanConfigDefaults:
    def test_default_neuron_set_reference(self):
        config = _minimal_config()
        reference = config.default_neuron_set_reference

        assert isinstance(reference, BiophysicalNeuronSetReference)
        assert reference.block_name == CircuitExtractionScanConfig.default_node_set_name
        assert isinstance(reference.block, AllBiophysicalNeurons)

    def test_default_point_neuron_set_reference(self):
        config = _minimal_config()
        reference = config.default_point_neuron_set_reference

        assert isinstance(reference, PointNeuronSetReference)
        assert reference.block_name == CircuitExtractionScanConfig.default_point_node_set_name
        assert isinstance(reference.block, AllPointNeurons)

    def test_default_neuron_set_ref_adds_block_to_neuron_sets(self):
        config = _minimal_config()
        ref = config._default_neuron_set_ref()

        assert ref.block_name in config.neuron_sets
        assert isinstance(config.neuron_sets[ref.block_name], AllBiophysicalNeurons)

    def test_default_neuron_set_ref_reuses_existing_default_block(self):
        config = _minimal_config()
        existing = AllBiophysicalNeurons()
        config.neuron_sets[CircuitExtractionScanConfig.default_node_set_name] = existing

        ref = config._default_neuron_set_ref()

        assert config.neuron_sets[CircuitExtractionScanConfig.default_node_set_name] is existing
        assert ref.block_name == CircuitExtractionScanConfig.default_node_set_name

    def test_default_point_neuron_set_ref_adds_block_to_neuron_sets(self):
        config = _minimal_config()
        ref = config._default_point_neuron_set_ref()

        assert ref.block_name in config.neuron_sets
        assert isinstance(config.neuron_sets[ref.block_name], AllPointNeurons)

    def test_default_point_neuron_set_ref_reuses_existing_default_block(self):
        config = _minimal_config()
        existing = AllPointNeurons()
        config.neuron_sets[CircuitExtractionScanConfig.default_point_node_set_name] = existing

        ref = config._default_point_neuron_set_ref()

        assert (
            config.neuron_sets[CircuitExtractionScanConfig.default_point_node_set_name] is existing
        )
        assert ref.block_name == CircuitExtractionScanConfig.default_point_node_set_name

    def test_reusing_default_biophysical_name_for_wrong_type_raises(self):
        config = _minimal_config()
        config.neuron_sets[CircuitExtractionScanConfig.default_node_set_name] = PredefinedNeuronSet(
            node_set="Excitatory",
        )

        with pytest.raises(OBIONEError, match="already exists in neuron_sets but is not an"):
            config._default_neuron_set_ref()

    def test_reusing_default_point_name_for_wrong_type_raises(self):
        config = _minimal_config()
        config.neuron_sets[CircuitExtractionScanConfig.default_point_node_set_name] = (
            PredefinedNeuronSet(node_set="Excitatory")
        )

        with pytest.raises(OBIONEError, match="Default point neuron set name"):
            config._default_point_neuron_set_ref()

    def test_default_ref_for_point_population_type(self):
        config = _minimal_config()
        ref = config._default_neuron_set_ref_for_population_type(NeuronSetPopulationType.POINT)

        assert isinstance(ref, PointNeuronSetReference)
        assert ref.block_name == CircuitExtractionScanConfig.default_point_node_set_name


class TestCircuitExtractionScanConfigEnsure:
    def test_ensure_extraction_target_neuron_set_fills_missing_reference(self):
        config = _minimal_config()
        config.ensure_extraction_target_neuron_set()

        assert config.initialize.neuron_set is not None
        assert (
            config.initialize.neuron_set.block_name
            == CircuitExtractionScanConfig.default_node_set_name
        )

    def test_ensure_extraction_target_neuron_set_keeps_existing_reference(self):
        config = _minimal_config()
        existing = config.default_neuron_set_reference
        config.initialize.neuron_set = existing

        config.ensure_extraction_target_neuron_set()

        assert config.initialize.neuron_set is existing

    def test_ensure_combined_neuron_set_preserves_existing_references(self):
        config = _minimal_config()
        existing = config.default_neuron_set_reference
        combined = BiophysicalCombinedNeuronSet(
            base_neuron_set=existing,
            combined_with=[(existing, SetOperation.UNION)],
        )

        config._ensure_combined_neuron_set_has_references(combined)

        assert combined.base_neuron_set is existing
        assert combined.combined_with == ((existing, SetOperation.UNION),)

    def test_ensure_combined_point_neuron_set_uses_point_default(self):
        config = _minimal_config()
        combined = PointCombinedNeuronSet(base_neuron_set=None, combined_with=())
        config.neuron_sets["PointCombined"] = combined

        config.ensure_combined_neuron_sets_have_references()

        assert combined.base_neuron_set is not None
        assert (
            combined.base_neuron_set.block_name
            == CircuitExtractionScanConfig.default_point_node_set_name
        )


class TestCircuitExtractionScanConfigInputEntities:
    def test_input_entities_from_single_circuit_from_id(self):
        config = _minimal_config()
        entity = Mock()
        circuit_from_id = Mock(spec=CircuitFromID)
        circuit_from_id.entity.return_value = entity
        config.initialize.circuit = circuit_from_id

        assert config.input_entities(db_client=Mock()) == [entity]

    def test_input_entities_from_circuit_from_id_list(self):
        config = _minimal_config()
        entity_one = Mock()
        entity_two = Mock()
        circuit_one = Mock(spec=CircuitFromID)
        circuit_one.entity.return_value = entity_one
        circuit_two = Mock(spec=CircuitFromID)
        circuit_two.entity.return_value = entity_two
        config.initialize.circuit = [circuit_one, circuit_two]

        assert config.input_entities(db_client=Mock()) == [entity_one, entity_two]

    def test_input_entities_skips_non_from_id_entries_in_circuit_list(self):
        config = _minimal_config()
        entity = Mock()
        circuit_from_id = Mock(spec=CircuitFromID)
        circuit_from_id.entity.return_value = entity
        config.initialize.circuit = [
            circuit_from_id,
            OBICircuit(
                name="N_10__top_nodes_dim6",
                path=str(CIRCUIT_DIR / "N_10__top_nodes_dim6" / "circuit_config.json"),
            ),
        ]

        assert config.input_entities(db_client=Mock()) == [entity]

    def test_input_entities_ignores_non_from_id_circuit(self):
        config = _minimal_config()

        assert config.input_entities(db_client=Mock()) == []
