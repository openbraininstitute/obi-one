"""Tests for neuron_sets base class utilities."""

import json

import pytest
from obi_one.scientific.blocks.neuron_sets.base import NeuronSet
from obi_one.scientific.blocks.neuron_sets.predefined import (
    BiophysicalPopulationPredefinedNeuronSet,
)
from obi_one.scientific.blocks.neuron_sets.property import (
    BiophysicalPopulationPropertyNeuronSet,
    NeuronPropertyFilter,
)

import obi_one as obi

from tests.utils import CIRCUIT_DIR, MATRIX_DIR

CIRCUIT_NAME = "N_10__top_nodes_dim6"


@pytest.fixture
def circuit():
    return obi.Circuit(
        name=CIRCUIT_NAME,
        path=str(CIRCUIT_DIR / CIRCUIT_NAME / "circuit_config.json"),
        matrix_path=str(MATRIX_DIR / CIRCUIT_NAME / "connectivity_matrix.h5"),
    )


# --- ids_to_node_set_definition ---


def test_ids_to_node_set_definition_single_population():
    """Test simplification for single population."""
    ids = {"S1nonbarrel_neurons": [1, 2, 3]}
    nset_def, combined = NeuronSet.ids_to_node_set_definition(ids, prefix="__test", simplified=True)
    # Single population -> simplified to dict
    assert isinstance(nset_def, dict)
    assert nset_def["population"] == "S1nonbarrel_neurons"
    assert nset_def["node_id"] == [1, 2, 3]
    assert combined == {}


def test_ids_to_node_set_definition_multi_population():
    """Test compound expression for multiple populations."""
    ids = {"pop_a": [1, 2], "pop_b": [3, 4, 5]}
    nset_def, combined = NeuronSet.ids_to_node_set_definition(ids, prefix="__test", simplified=True)
    # Multiple populations -> compound expression
    assert isinstance(nset_def, list)
    assert len(nset_def) == 2
    assert set(nset_def) == set(combined.keys())
    for key in nset_def:
        assert "population" in combined[key]
        assert "node_id" in combined[key]


def test_ids_to_node_set_definition_no_simplification():
    """Test that simplified=False always returns a list."""
    ids = {"S1nonbarrel_neurons": [1, 2, 3]}
    nset_def, combined = NeuronSet.ids_to_node_set_definition(
        ids, prefix="__test", simplified=False
    )
    # No simplification -> always list
    assert isinstance(nset_def, list)
    assert len(nset_def) == 1
    assert len(combined) == 1


# --- add_node_set_definition_to_sonata_circuit ---


def test_add_node_set_to_sonata_circuit(circuit):
    """Test that a node set is added and queryable via bluepysnap."""
    nset = BiophysicalPopulationPropertyNeuronSet(
        population="S1nonbarrel_neurons",
        property_filter=NeuronPropertyFilter(
            filter_dict={"layer": ["6"], "synapse_class": ["EXC"]}
        ),
    )
    nset.set_block_name("added_nset")

    nset_name, sonata_circuit = nset.add_node_set_definition_to_sonata_circuit(circuit)

    # Verify it's in the node sets
    assert nset_name in sonata_circuit.node_sets.content

    # Verify it resolves correctly via bluepysnap
    resolved_ids = sonata_circuit.nodes["S1nonbarrel_neurons"].ids(nset_name)
    expected_ids = nset.get_neuron_ids(circuit)["S1nonbarrel_neurons"]
    assert sorted(resolved_ids) == sorted(expected_ids)


# --- to_node_set_file ---


def test_to_node_set_file(circuit, tmp_path):
    """Test writing a node set to a JSON file."""
    nset = BiophysicalPopulationPredefinedNeuronSet(
        node_set="Layer6", population="S1nonbarrel_neurons"
    )
    nset.set_block_name("file_nset")

    output_file = nset.to_node_set_file(
        circuit,
        output_path=str(tmp_path),
        file_name="test_output.json",
        overwrite_if_exists=True,
        init_empty=True,
    )

    # File exists
    assert output_file.exists()

    # Valid JSON
    with output_file.open() as f:
        content = json.load(f)

    # Contains the node set name
    nset_name = f"__{nset.__class__.__name__}__{nset.block_name}"
    assert nset_name in content


def test_to_node_set_file_force_resolve(circuit, tmp_path):
    """Test writing with force_resolve_ids produces node_id in output."""
    nset = BiophysicalPopulationPredefinedNeuronSet(
        node_set="Layer6", population="S1nonbarrel_neurons"
    )
    nset.set_block_name("file_resolved")

    output_file = nset.to_node_set_file(
        circuit,
        output_path=str(tmp_path),
        file_name="test_resolved.json",
        overwrite_if_exists=True,
        init_empty=True,
        force_resolve_ids=True,
    )

    with output_file.open() as f:
        content = json.load(f)

    nset_name = f"__{nset.__class__.__name__}__{nset.block_name}"
    assert nset_name in content
    assert "node_id" in content[nset_name]


def test_to_node_set_file_append(circuit, tmp_path):
    """Test appending a node set to an existing file."""
    nset1 = BiophysicalPopulationPredefinedNeuronSet(
        node_set="Layer6", population="S1nonbarrel_neurons"
    )
    nset1.set_block_name("nset1")

    nset2 = BiophysicalPopulationPredefinedNeuronSet(
        node_set="L6_BPC", population="S1nonbarrel_neurons"
    )
    nset2.set_block_name("nset2")

    # Write first
    output_file = nset1.to_node_set_file(
        circuit,
        output_path=str(tmp_path),
        file_name="append_test.json",
        overwrite_if_exists=True,
        init_empty=True,
    )

    # Append second
    nset2.to_node_set_file(
        circuit,
        output_path=str(tmp_path),
        file_name="append_test.json",
        append_if_exists=True,
    )

    with output_file.open() as f:
        content = json.load(f)

    name1 = f"__{nset1.__class__.__name__}__{nset1.block_name}"
    name2 = f"__{nset2.__class__.__name__}__{nset2.block_name}"
    assert name1 in content
    assert name2 in content
