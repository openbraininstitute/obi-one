import re

import numpy as np
import pytest
from pydantic import ValidationError

import obi_one as obi

from tests.utils import CIRCUIT_DIR, MATRIX_DIR


def test_predefined_neuron_set():
    # Load circuit
    circuit_name = "N_10__top_nodes_dim6"
    circuit = obi.Circuit(
        name=circuit_name,
        path=str(CIRCUIT_DIR / circuit_name / "circuit_config.json"),
        matrix_path=str(MATRIX_DIR / circuit_name / "connectivity_matrix.h5"),
    )

    # (a) Non-existing node set --> Error
    neuron_set = obi.PredefinedNeuronSet(node_set="Layer678", sample_percentage=100)
    with pytest.raises(
        ValueError,
        match=re.escape(f"Node set 'Layer678' not found in circuit '{circuit_name}'."),
    ):
        neuron_set_ids = neuron_set.get_neuron_ids(
            circuit, population=circuit.default_population_name
        )

    # (b) Existing node set
    neuron_set = obi.PredefinedNeuronSet(node_set="Layer6")
    neuron_set_ids = neuron_set.get_neuron_ids(circuit, population=circuit.default_population_name)
    neuron_set_def = neuron_set.get_node_set_definition(circuit, circuit.default_population_name)
    np.testing.assert_array_equal(neuron_set_ids, range(1, 10))
    assert neuron_set_def == ["Layer6"]

    # (c) Existing node set with sub-sampling (11% corresponding to 1 neuron)
    neuron_set = obi.PredefinedNeuronSet(node_set="Layer6", sample_percentage=11)
    neuron_set_ids = neuron_set.get_neuron_ids(circuit, population=circuit.default_population_name)
    neuron_set_def = neuron_set.get_node_set_definition(circuit, circuit.default_population_name)
    assert len(neuron_set_ids) == 1
    assert isinstance(neuron_set_def, dict)
    assert neuron_set_def["population"] == circuit.default_population_name
    assert len(neuron_set_def["node_id"]) == 1

    # (d) Existing node set with invalid sub-sampling --> Error
    with pytest.raises(ValidationError):
        neuron_set = obi.PredefinedNeuronSet(node_set="Layer6", sample_percentage=-1)
    with pytest.raises(ValidationError):
        neuron_set = obi.PredefinedNeuronSet(node_set="Layer6", sample_percentage=101)
