import re

import numpy as np
import pytest

import obi_one as obi

from tests.utils import CIRCUIT_DIR, MATRIX_DIR


def test_id_neuron_set():
    # Load circuit
    circuit_name = "N_10__top_nodes_dim6"
    circuit = obi.Circuit(
        name=circuit_name,
        path=str(CIRCUIT_DIR / circuit_name / "circuit_config.json"),
        matrix_path=str(MATRIX_DIR / circuit_name / "connectivity_matrix.h5"),
    )

    # (a) Invalid IDs --> Error
    neuron_set = obi.IDNeuronSet(
        neuron_ids=obi.NamedTuple(name="IDNeuronSet", elements=(0, 2, 8, 10))
    )
    with pytest.raises(
        ValueError,
        match=re.escape(
            f"Neuron ID(s) not found in population '{circuit.default_population_name}'"
            f" of circuit '{circuit_name}'."
        ),
    ):
        neuron_set_ids = neuron_set.get_neuron_ids(circuit, circuit.default_population_name)

    # (b) Selected IDs
    neuron_set = obi.IDNeuronSet(neuron_ids=obi.NamedTuple(name="IDNeuronSet", elements=range(10)))
    neuron_set_ids = neuron_set.get_neuron_ids(circuit, circuit.default_population_name)
    neuron_set_def = neuron_set.get_node_set_definition(circuit, circuit.default_population_name)
    np.testing.assert_array_equal(neuron_set_ids, range(10))
    assert neuron_set_def["population"] == circuit.default_population_name
    np.testing.assert_array_equal(neuron_set_def["node_id"], range(10))

    # (c) Selected IDs with sub-sampling (50% corresponding to 5 neuron)
    neuron_set = obi.IDNeuronSet(
        neuron_ids=obi.NamedTuple(name="IDNeuronSet", elements=range(10)), sample_percentage=50
    )
    neuron_set_ids = neuron_set.get_neuron_ids(circuit, circuit.default_population_name)
    neuron_set_def = neuron_set.get_node_set_definition(circuit, circuit.default_population_name)
    assert len(neuron_set_ids) == 5
    assert neuron_set_def["population"] == circuit.default_population_name
    assert len(neuron_set_def["node_id"]) == 5
