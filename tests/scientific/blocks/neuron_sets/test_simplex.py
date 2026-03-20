import numpy as np

import obi_one as obi

from tests.utils import CIRCUIT_DIR, MATRIX_DIR


def test_simplex_neuron_sets():
    # Load circuit
    circuit_name = "N_10__top_nodes_dim6"
    circuit = obi.Circuit(
        name=circuit_name,
        path=str(CIRCUIT_DIR / circuit_name / "circuit_config.json"),
        matrix_path=str(MATRIX_DIR / circuit_name / "connectivity_matrix.h5"),
    )

    # Simplex membership based neuron set
    dim_pos = [
        (2, "source"),
        (2, "target"),
        (3, "source"),
        (3, "target"),
        (4, "source"),
        (4, "target"),
    ]
    expected = [[4, 6, 7, 8, 9], [4, 9], [4, 7, 8, 9], [4, 9], [4, 7, 8, 9], [4, 9]]
    for (dim, pos), exp in zip(dim_pos, expected, strict=False):
        neuron_set = obi.SimplexMembershipBasedNeuronSet(
            central_neuron_id=9,
            dim=dim,
            central_neuron_simplex_position=pos,
            subsample=False,
            property_filter=obi.NeuronPropertyFilter(),
        )
        neuron_set_ids = neuron_set.get_neuron_ids(circuit, circuit.default_population_name)
        neuron_set_def = neuron_set.get_node_set_definition(
            circuit, circuit.default_population_name
        )
        assert neuron_set.central_neuron_id in neuron_set_ids
        np.testing.assert_array_equal(sorted(neuron_set_ids), exp)
        assert neuron_set_def["population"] == circuit.default_population_name
        np.testing.assert_array_equal(sorted(neuron_set_def["node_id"]), exp)

    # Simplex neuron set
    dim_pos = [
        (2, "source"),
        (2, "target"),
        (3, "source"),
        (3, "target"),
        (4, "source"),
        (4, "target"),
    ]
    expected = [[4, 6, 7, 8, 9], [4, 9], [4, 7, 8, 9], [4, 9], [4, 7, 8, 9], [4, 9]]
    for (dim, pos), exp in zip(dim_pos, expected, strict=False):
        neuron_set = obi.SimplexNeuronSet(
            central_neuron_id=9,
            dim=dim,
            central_neuron_simplex_position=pos,
            subsample=False,
            property_filter=obi.NeuronPropertyFilter(),
        )
        neuron_set_ids = neuron_set.get_neuron_ids(circuit, circuit.default_population_name)
        neuron_set_def = neuron_set.get_node_set_definition(
            circuit, circuit.default_population_name
        )
        assert neuron_set.central_neuron_id in neuron_set_ids
        np.testing.assert_array_equal(sorted(neuron_set_ids), exp)
        assert neuron_set_def["population"] == circuit.default_population_name
        np.testing.assert_array_equal(sorted(neuron_set_def["node_id"]), exp)
