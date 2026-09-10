"""Tests for neuron_sets property neuron sets."""

import numpy as np
import pytest

import obi_one as obi
from obi_one.scientific.blocks.neuron_sets.property import (
    BiophysicalPopulationPropertyNeuronSet,
    NeuronPropertyFilter,
    VirtualPopulationPropertyNeuronSet,
)
from obi_one.scientific.library.sonata_circuit_helpers import add_node_set_to_circuit

from tests.utils import CIRCUIT_DIR, MATRIX_DIR

CIRCUIT_NAME = "N_10__top_nodes_dim6"


@pytest.fixture
def circuit():
    return obi.Circuit(
        name=CIRCUIT_NAME,
        path=str(CIRCUIT_DIR / CIRCUIT_NAME / "circuit_config.json"),
        matrix_path=str(MATRIX_DIR / CIRCUIT_NAME / "connectivity_matrix.h5"),
    )


def test_property_neuron_set_basic(circuit):
    """Test BiophysicalPopulationPropertyNeuronSet filters by properties correctly."""
    nset = BiophysicalPopulationPropertyNeuronSet(
        population="S1nonbarrel_neurons",
        property_filter=NeuronPropertyFilter(
            filter_dict={"layer": ["6"], "synapse_class": ["EXC"]}
        ),
    )
    nset.set_block_name("prop_basic")

    ids = nset.get_neuron_ids(circuit)
    assert "S1nonbarrel_neurons" in ids
    np.testing.assert_array_equal(ids["S1nonbarrel_neurons"], range(1, 10))


def test_property_neuron_set_symbolic_expression(circuit):
    """Test the property filter stays symbolic, pinned to its population."""
    nset = BiophysicalPopulationPropertyNeuronSet(
        population="S1nonbarrel_neurons",
        property_filter=NeuronPropertyFilter(
            filter_dict={"layer": ["3", "6"], "synapse_class": ["EXC"]}
        ),
    )
    nset.set_block_name("prop_sym")

    nset_def, combined = nset.get_node_set_definition(circuit)
    # libsonata intersects the clauses of a multi-key node set object, so the population
    # restriction needs no materialized IDs.
    assert nset_def == {
        "layer": ["3", "6"],
        "synapse_class": "EXC",
        "population": "S1nonbarrel_neurons",
    }
    assert combined == {}


def test_property_neuron_set_symbolic_expression_resolves_to_the_same_ids(circuit):
    """The symbolic definition selects exactly the neurons the filter resolves to."""
    nset = BiophysicalPopulationPropertyNeuronSet(
        population="S1nonbarrel_neurons",
        property_filter=NeuronPropertyFilter(
            filter_dict={"layer": ["3", "6"], "synapse_class": ["EXC"]}
        ),
    )
    nset.set_block_name("prop_sym_ids")

    nset_def, _ = nset.get_node_set_definition(circuit)

    sonata_circuit = circuit.sonata_circuit
    add_node_set_to_circuit(sonata_circuit, {"__test__": nset_def})
    resolved = sonata_circuit.nodes["S1nonbarrel_neurons"].ids("__test__").tolist()

    assert resolved == nset.get_neuron_ids(circuit)["S1nonbarrel_neurons"]


def test_property_neuron_set_with_sampling(circuit):
    """Test BiophysicalPopulationPropertyNeuronSet with sub-sampling."""
    nset = BiophysicalPopulationPropertyNeuronSet(
        population="S1nonbarrel_neurons",
        property_filter=NeuronPropertyFilter(
            filter_dict={"layer": ["6"], "synapse_class": ["EXC"]}
        ),
        sample_percentage=50,
        sample_seed=1,
    )
    nset.set_block_name("prop_sampled")

    ids = nset.get_neuron_ids(circuit)
    # 9 EXC neurons in Layer6, 50% -> 4 or 5
    assert 4 <= len(ids["S1nonbarrel_neurons"]) <= 5


def test_property_neuron_set_invalid_property(circuit):
    """Test that an invalid property name raises."""
    nset = BiophysicalPopulationPropertyNeuronSet(
        population="S1nonbarrel_neurons",
        property_filter=NeuronPropertyFilter(filter_dict={"INVALID_PROP": ["x"], "layer": ["6"]}),
    )
    nset.set_block_name("prop_invalid")

    with pytest.raises(ValueError, match="Invalid neuron properties"):
        nset.get_neuron_ids(circuit)


def test_property_neuron_set_no_match(circuit):
    """Test that non-matching property values return empty."""
    nset = BiophysicalPopulationPropertyNeuronSet(
        population="S1nonbarrel_neurons",
        property_filter=NeuronPropertyFilter(filter_dict={"synapse_class": ["NONEXISTENT"]}),
    )
    nset.set_block_name("prop_nomatch")

    ids = nset.get_neuron_ids(circuit)
    assert len(ids["S1nonbarrel_neurons"]) == 0


def test_property_neuron_set_force_resolve(circuit):
    """Test force_resolve_ids returns explicit IDs."""
    nset = BiophysicalPopulationPropertyNeuronSet(
        population="S1nonbarrel_neurons",
        property_filter=NeuronPropertyFilter(
            filter_dict={"layer": ["6"], "synapse_class": ["EXC"]}
        ),
    )
    nset.set_block_name("prop_resolve")

    nset_def, _ = nset.get_node_set_definition(circuit, force_resolve_ids=True)
    assert nset_def["population"] == "S1nonbarrel_neurons"
    assert "node_id" in nset_def
    assert len(nset_def["node_id"]) == 9


def test_property_neuron_set_virtual_mismatch(circuit):
    """Test VirtualPopulationPropertyNeuronSet fails with a biophysical population."""
    nset = VirtualPopulationPropertyNeuronSet(
        population="S1nonbarrel_neurons",
        property_filter=NeuronPropertyFilter(filter_dict={"layer": ["6"]}),
    )
    nset.set_block_name("prop_virt_mismatch")

    with pytest.raises(ValueError, match="not found in circuit"):
        nset.get_neuron_ids(circuit)


def test_property_neuron_set_biophysical_matching(circuit):
    """Test BiophysicalPopulationPropertyNeuronSet works with a biophysical population."""
    nset = BiophysicalPopulationPropertyNeuronSet(
        population="S1nonbarrel_neurons",
        property_filter=NeuronPropertyFilter(
            filter_dict={"layer": ["6"], "synapse_class": ["EXC"]}
        ),
    )
    nset.set_block_name("prop_bio_match")

    ids = nset.get_neuron_ids(circuit)
    assert len(ids["S1nonbarrel_neurons"]) == 9
