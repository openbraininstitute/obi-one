import json
import re
from pathlib import Path

import numpy as np
import pytest

import obi_one as obi

from tests.utils import CIRCUIT_DIR, MATRIX_DIR


def test_combined_neuron_set():
    # Load circuit
    circuit_name = "N_10__top_nodes_dim6"
    circuit = obi.Circuit(
        name=circuit_name,
        path=str(CIRCUIT_DIR / circuit_name / "circuit_config.json"),
        matrix_path=str(MATRIX_DIR / circuit_name / "connectivity_matrix.h5"),
    )

    # (a) Non-existing node set --> Error
    neuron_set = obi.CombinedNeuronSet(node_sets=("L6_BPC", "L6_TPC:AA"))
    with pytest.raises(
        ValueError,
        match=re.escape(f"Node set 'L6_TPC:AA' not found in circuit '{circuit_name}'."),
    ):
        neuron_set_ids = neuron_set.get_neuron_ids(
            circuit, population=circuit.default_population_name
        )

    # (b) Combined neuron set
    neuron_set = obi.CombinedNeuronSet(node_sets=("L6_BPC", "L6_TPC:A"))
    neuron_set_ids = neuron_set.get_neuron_ids(circuit, population=circuit.default_population_name)
    neuron_set_def = neuron_set.get_node_set_definition(circuit, circuit.default_population_name)
    np.testing.assert_array_equal(neuron_set_ids, [1, 2, 6, 7, 8, 9])
    assert neuron_set_def == ["L6_BPC", "L6_TPC:A"]

    # (c) Combined neuron set with sub-sampling (50% corresponding to 3 neuron)
    neuron_set = obi.CombinedNeuronSet(node_sets=("L6_BPC", "L6_TPC:A"), sample_percentage=50)
    neuron_set_ids = neuron_set.get_neuron_ids(circuit, population=circuit.default_population_name)
    neuron_set_def = neuron_set.get_node_set_definition(circuit, circuit.default_population_name)
    assert len(neuron_set_ids) == 3
    assert isinstance(neuron_set_def, dict)
    assert neuron_set_def["population"] == circuit.default_population_name
    assert len(neuron_set_def["node_id"]) == 3


def test_write_to_node_set_file(tmp_path):
    # Load circuit
    circuit_name = "N_10__top_nodes_dim6"
    circuit = obi.Circuit(
        name=circuit_name, path=str(CIRCUIT_DIR / circuit_name / "circuit_config.json")
    )

    # Write new file
    neuron_set = obi.CombinedNeuronSet(node_sets=("Layer1", "Layer2", "Layer3"))
    nset_file = neuron_set.to_node_set_file(
        circuit,
        circuit.default_population_name,
        output_path=tmp_path,
        overwrite_if_exists=False,
        optional_node_set_name="L123",
    )
    assert Path(nset_file).exists()

    # Write again w/o overwriting --> Must raise an error
    with pytest.raises(
        ValueError,
        match=(
            f"Output file '{tmp_path / 'node_sets.json'}' already exists!"
            " Delete file or choose to append or overwrite."
        ),
    ):
        nset_file = neuron_set.to_node_set_file(
            circuit,
            circuit.default_population_name,
            output_path=tmp_path,
            overwrite_if_exists=False,
            optional_node_set_name="L123",
        )

    # Write again with overwriting --> No error
    nset_file = neuron_set.to_node_set_file(
        circuit,
        circuit.default_population_name,
        output_path=tmp_path,
        overwrite_if_exists=True,
        optional_node_set_name="L123",
    )
    assert Path(nset_file).exists()

    # Append to existing file, but name already exists --> Must raise an error
    with pytest.raises(ValueError, match="Appending not possible, node set 'L123' already exists!"):
        nset_file = neuron_set.to_node_set_file(
            circuit,
            circuit.default_population_name,
            output_path=tmp_path,
            append_if_exists=True,
            optional_node_set_name="L123",
        )

    # Append to existing file
    neuron_set = obi.CombinedNeuronSet(node_sets=("Layer4", "Layer5", "Layer6"))
    nset_file = neuron_set.to_node_set_file(
        circuit,
        circuit.default_population_name,
        output_path=tmp_path,
        append_if_exists=True,
        optional_node_set_name="L456",
    )
    assert Path(nset_file).exists()

    # Check if new node sets exist in the .json file
    with Path(nset_file).open(encoding="utf-8") as f:
        node_sets = json.load(f)

    assert "L123" in node_sets
    assert "L456" in node_sets

    assert node_sets["L123"] == ["Layer1", "Layer2", "Layer3"]
    assert node_sets["L456"] == ["Layer4", "Layer5", "Layer6"]

    # Check that original node sets are preserved in new node sets file
    orig_node_sets = circuit.sonata_circuit.node_sets.content
    for k, v in orig_node_sets.items():
        assert k in node_sets
        assert node_sets[k] == v

    # Check that original node sets are unchanged
    assert "L123" not in orig_node_sets
    assert "L456" not in orig_node_sets
