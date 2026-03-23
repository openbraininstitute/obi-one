import numpy as np

import obi_one as obi

from tests.utils import CIRCUIT_DIR, MATRIX_DIR


def _get_distance(circuit, neuron_set, neuron_ids):
    """Get neuron distance relative to the centroid of (filtered) neuron population."""
    base_neuron_ids = obi.PropertyNeuronSet(
        property_filter=neuron_set.property_filter
    ).get_neuron_ids(circuit, circuit.default_population_name)
    all_pos = circuit.sonata_circuit.nodes[circuit.default_population_name].positions(
        base_neuron_ids
    )
    center_pos = all_pos.mean() + np.array([neuron_set.ox, neuron_set.oy, neuron_set.oz])
    sel_pos = circuit.sonata_circuit.nodes[circuit.default_population_name].get(
        neuron_ids, properties=["x", "y", "z"]
    )
    sel_dist = np.sqrt(np.sum((sel_pos - center_pos) ** 2, 1))
    return sel_dist.to_numpy()


def test_volumetric_neuron_sets():
    # Load circuit
    circuit_name = "N_10__top_nodes_dim6"
    circuit = obi.Circuit(
        name=circuit_name,
        path=str(CIRCUIT_DIR / circuit_name / "circuit_config.json"),
        matrix_path=str(MATRIX_DIR / circuit_name / "connectivity_matrix.h5"),
    )

    # (a) Volumetric count neuron set with different numbers
    counts = [0, 3, 5, 7, 100]
    expected = [[], [6, 7, 9], [3, 5, 6, 7, 9], [1, 3, 4, 5, 6, 7, 9], range(1, 10)]
    for n, exp in zip(counts, expected, strict=False):
        neuron_set = obi.VolumetricCountNeuronSet(
            ox=10.0,
            oy=25.0,
            oz=100.0,
            n=n,
            property_filter=obi.NeuronPropertyFilter(filter_dict={"synapse_class": ["EXC"]}),
        )
        neuron_set_ids = neuron_set.get_neuron_ids(circuit, circuit.default_population_name)
        neuron_set_def = neuron_set.get_node_set_definition(
            circuit, circuit.default_population_name
        )
        np.testing.assert_array_equal(sorted(neuron_set_ids), exp)
        assert neuron_set_def["population"] == circuit.default_population_name
        np.testing.assert_array_equal(sorted(neuron_set_def["node_id"]), exp)

        # Check distances (no other neurons must be closer)
        cutoff_dist = (
            0.0
            if len(neuron_set_ids) == 0
            else np.max(_get_distance(circuit, neuron_set, neuron_set_ids))
        )
        diff_ids = np.setdiff1d(
            circuit.sonata_circuit.nodes[circuit.default_population_name].ids(), neuron_set_ids
        )
        other_dist = _get_distance(circuit, neuron_set, diff_ids)
        assert np.all(other_dist >= cutoff_dist)

    # (b) Volumetric radius neuron set with different radii
    radii = [0, 50.0, 100.0, 150.0, 200.0, 1000.0]
    expected = [[], [9], [6, 9], [1, 3, 4, 5, 6, 7, 9], range(1, 10), range(1, 10)]
    for r, exp in zip(radii, expected, strict=False):
        neuron_set = obi.VolumetricRadiusNeuronSet(
            ox=10.0,
            oy=25.0,
            oz=100.0,
            radius=r,
            property_filter=obi.NeuronPropertyFilter(
                filter_dict={"layer": ["5", "6"], "synapse_class": ["EXC"]}
            ),
        )
        neuron_set_ids = neuron_set.get_neuron_ids(circuit, circuit.default_population_name)
        neuron_set_def = neuron_set.get_node_set_definition(
            circuit, circuit.default_population_name
        )
        np.testing.assert_array_equal(sorted(neuron_set_ids), exp)
        assert neuron_set_def["population"] == circuit.default_population_name
        np.testing.assert_array_equal(sorted(neuron_set_def["node_id"]), exp)

        # Check distances (all neurons must be within radius)
        dist = _get_distance(circuit, neuron_set, neuron_set_ids)
        assert np.all(dist < r)
