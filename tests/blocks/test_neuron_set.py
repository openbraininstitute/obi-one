import json
from pathlib import Path

import pytest

import obi_one as obi

from tests.utils import CIRCUIT_DIR


def test_add_and_write_node_sets(tmp_path):
    # Load circuit
    circuit_name = "N_10__top_nodes_dim6"
    circuit = obi.Circuit(
        name=circuit_name, path=str(CIRCUIT_DIR / circuit_name / "circuit_config.json")
    )
    c = circuit.sonata_circuit

    # Add a new node sets to the SONATA circuit
    obi.NeuronSet.add_node_set_to_circuit(c, {"Layer23": {"layer": ["2", "3"]}})

    with pytest.raises(ValueError, match="Node set 'Layer23' already exists!"):
        # Add a node set with an exising name --> Must raise an error
        obi.NeuronSet.add_node_set_to_circuit(c, {"Layer23": {"layer": ["2", "3"]}})

    # Update/overwrite an existing node set
    obi.NeuronSet.add_node_set_to_circuit(
        c, {"Layer23": ["Layer2", "Layer3"]}, overwrite_if_exists=True
    )

    # Add multiple node sets
    obi.NeuronSet.add_node_set_to_circuit(
        c, {"Layer45": ["Layer4", "Layer5"], "Layer56": ["Layer5", "Layer6"]}
    )

    # Add a node set from NeuronSet object, resolved in the circuit's default node population
    neuron_set = obi.CombinedNeuronSet(node_sets=("Layer1", "Layer2", "Layer3"))
    obi.NeuronSet.add_node_set_to_circuit(
        c,
        {"Layer123": neuron_set.get_node_set_definition(circuit, circuit.default_population_name)},
    )

    # Add a node sets based on previously added node sets
    obi.NeuronSet.add_node_set_to_circuit(c, {"AllLayers": ["Layer123", "Layer4", "Layer56"]})

    # Write new circuit's node set file
    obi.NeuronSet.write_circuit_node_set_file(
        c, output_path=tmp_path, file_name="new_node_sets.json", overwrite_if_exists=False
    )

    with pytest.raises(
        ValueError,
        match=(
            f"Output file '{tmp_path / 'new_node_sets.json'}' already exists!"
            " Delete or choose to overwrite."
        ),
    ):
        # Write again using the same filename (w/o overwrite) --> Must raise an error
        obi.NeuronSet.write_circuit_node_set_file(
            c, output_path=tmp_path, file_name="new_node_sets.json", overwrite_if_exists=False
        )

    # Write again, this time with overwrite
    obi.NeuronSet.write_circuit_node_set_file(
        c, output_path=tmp_path, file_name="new_node_sets.json", overwrite_if_exists=True
    )

    # Check if new node sets exist in the .json file
    with Path(tmp_path / "new_node_sets.json").open(encoding="utf-8") as f:
        node_sets = json.load(f)

    assert "Layer23" in node_sets
    assert "Layer45" in node_sets
    assert "Layer56" in node_sets
    assert "Layer123" in node_sets
    assert "AllLayers" in node_sets

    assert node_sets["Layer23"] == ["Layer2", "Layer3"]
    assert node_sets["Layer45"] == ["Layer4", "Layer5"]
    assert node_sets["Layer56"] == ["Layer5", "Layer6"]
    assert node_sets["Layer123"] == ["Layer1", "Layer2", "Layer3"]
    assert node_sets["AllLayers"] == ["Layer123", "Layer4", "Layer56"]

    # Reload circuit and check that original node sets are unchanged
    circuit = obi.Circuit(
        name=circuit_name, path=str(CIRCUIT_DIR / circuit_name / "circuit_config.json")
    )
    c = circuit.sonata_circuit
    orig_node_sets = c.node_sets.content
    for k, v in orig_node_sets.items():
        assert k in node_sets
        assert node_sets[k] == v
