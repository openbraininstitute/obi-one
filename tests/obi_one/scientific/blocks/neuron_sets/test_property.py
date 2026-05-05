import numpy as np
import pytest

import obi_one as obi

from tests.utils import CIRCUIT_DIR, MATRIX_DIR


def test_property_neuron_set():
    # Load circuit
    circuit_name = "N_10__top_nodes_dim6"
    circuit = obi.Circuit(
        name=circuit_name,
        path=str(CIRCUIT_DIR / circuit_name / "circuit_config.json"),
        matrix_path=str(MATRIX_DIR / circuit_name / "connectivity_matrix.h5"),
    )

    # (a) Invalid neuron property --> Error
    neuron_set = obi.PropertyNeuronSet(
        property_filter=obi.NeuronPropertyFilter(
            filter_dict={"INVALID": ["x"], "layer": ["5", "6"], "synapse_class": ["EXC"]}
        ),
    )
    with pytest.raises(ValueError, match="Invalid neuron properties!"):
        neuron_set_ids = neuron_set.get_neuron_ids(circuit, circuit.default_population_name)

    # (b) Invalid property value --> Empty neuron set
    neuron_set = obi.PropertyNeuronSet(
        property_filter=obi.NeuronPropertyFilter(
            filter_dict={"layer": ["5", "6"], "synapse_class": ["INVALID"]}
        ),
    )
    neuron_set_ids = neuron_set.get_neuron_ids(circuit, circuit.default_population_name)
    assert len(neuron_set_ids) == 0

    # (c) Valid property neuron set
    neuron_set = obi.PropertyNeuronSet(
        property_filter=obi.NeuronPropertyFilter(
            filter_dict={"layer": ["3", "6"], "synapse_class": ["EXC"]}
        ),
    )
    neuron_set_ids = neuron_set.get_neuron_ids(circuit, circuit.default_population_name)
    neuron_set_def = neuron_set.get_node_set_definition(circuit, circuit.default_population_name)
    np.testing.assert_array_equal(neuron_set_ids, range(1, 10))
    assert neuron_set_def == {"layer": ["3", "6"], "synapse_class": "EXC"}

    # (d) Valid property neuron set combined with existing node sets --> Enforces resolving node IDs
    neuron_set = obi.PropertyNeuronSet(
        property_filter=obi.NeuronPropertyFilter(filter_dict={"synapse_class": ["EXC"]}),
        node_sets=("Layer3", "Layer6"),
    )
    neuron_set_ids = neuron_set.get_neuron_ids(circuit, circuit.default_population_name)
    neuron_set_def = neuron_set.get_node_set_definition(circuit, circuit.default_population_name)
    np.testing.assert_array_equal(neuron_set_ids, range(1, 10))
    assert neuron_set_def["population"] == circuit.default_population_name
    np.testing.assert_array_equal(neuron_set_def["node_id"], range(1, 10))
