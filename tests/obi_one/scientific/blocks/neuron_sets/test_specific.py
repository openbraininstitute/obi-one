import re

import numpy as np
import pytest

import obi_one as obi

from tests.utils import CIRCUIT_DIR, MATRIX_DIR


def test_hard_coded_neuron_sets():
    # Load circuit
    circuit_name = "N_10__top_nodes_dim6"
    circuit = obi.Circuit(
        name=circuit_name,
        path=str(CIRCUIT_DIR / circuit_name / "circuit_config.json"),
        matrix_path=str(MATRIX_DIR / circuit_name / "connectivity_matrix.h5"),
    )

    # (a) All neurons
    neuron_set = obi.AllNeurons()
    neuron_set_ids = neuron_set.get_neuron_ids(circuit, circuit.default_population_name)
    neuron_set_def = neuron_set.get_node_set_definition(circuit, circuit.default_population_name)
    np.testing.assert_array_equal(
        neuron_set_ids, circuit.sonata_circuit.nodes[circuit.default_population_name].ids()
    )
    assert neuron_set_def == ["All"]

    # (b) Excitatory neurons
    neuron_set = obi.ExcitatoryNeurons()
    neuron_set_ids = neuron_set.get_neuron_ids(circuit, circuit.default_population_name)
    neuron_set_def = neuron_set.get_node_set_definition(circuit, circuit.default_population_name)
    np.testing.assert_array_equal(
        neuron_set_ids,
        circuit.sonata_circuit.nodes[circuit.default_population_name].ids({"synapse_class": "EXC"}),
    )
    assert neuron_set_def == ["Excitatory"]

    # (c) Inhibitory neurons
    neuron_set = obi.InhibitoryNeurons()
    neuron_set_ids = neuron_set.get_neuron_ids(circuit, circuit.default_population_name)
    neuron_set_def = neuron_set.get_node_set_definition(circuit, circuit.default_population_name)
    np.testing.assert_array_equal(
        neuron_set_ids,
        circuit.sonata_circuit.nodes[circuit.default_population_name].ids({"synapse_class": "INH"}),
    )
    assert neuron_set_def == ["Inhibitory"]

    # (d) nbS1 VPM population
    neuron_set = obi.nbS1VPMInputs()
    neuron_set_ids = neuron_set.get_neuron_ids(circuit)
    neuron_set_def = neuron_set.get_node_set_definition(circuit)
    np.testing.assert_array_equal(neuron_set_ids, circuit.sonata_circuit.nodes["VPM"].ids())
    assert neuron_set_def == {"population": "VPM"}

    # (e) nbS1 POm population
    neuron_set = obi.nbS1POmInputs()
    neuron_set_ids = neuron_set.get_neuron_ids(circuit)
    neuron_set_def = neuron_set.get_node_set_definition(circuit)
    np.testing.assert_array_equal(neuron_set_ids, circuit.sonata_circuit.nodes["POm"].ids())
    assert neuron_set_def == {"population": "POm"}

    # (f) CA1-CA3 inputs --> Not availbale in nbS1 example circuit, error should be raised
    neuron_set = obi.rCA1CA3Inputs()
    with pytest.raises(
        ValueError,
        match=re.escape(
            f"Node population 'CA3_projections' not found in circuit '{circuit_name}'."
        ),
    ):
        neuron_set_ids = neuron_set.get_neuron_ids(circuit)
    with pytest.raises(
        ValueError,
        match=re.escape(
            f"Node population 'CA3_projections' not found in circuit '{circuit_name}'."
        ),
    ):
        neuron_set_def = neuron_set.get_node_set_definition(circuit)
