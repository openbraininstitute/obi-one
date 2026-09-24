"""Tests for neuron_sets predefined neuron sets."""

import numpy as np
import pytest

import obi_one as obi
from obi_one.scientific.blocks.neuron_sets.predefined import (
    BiophysicalPopulationPredefinedNeuronSet,
    MultiPopulationPredefinedNeuronSet,
    VirtualPopulationPredefinedNeuronSet,
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


# --- MultiPopulationPredefinedNeuronSet (multi-population) ---


def test_predefined_neuron_set_symbolic(circuit):
    """Test MultiPopulationPredefinedNeuronSet gives a symbolic expression w/o force_resolve."""
    nset = MultiPopulationPredefinedNeuronSet(node_set="Layer6")
    nset.set_block_name("predef_layer6")

    nset_def, combined = nset.get_node_set_definition(circuit)
    assert nset_def == ["Layer6"]
    assert combined == {}


def test_predefined_neuron_set_resolve_ids(circuit):
    """Test MultiPopulationPredefinedNeuronSet with force_resolve_ids."""
    nset = MultiPopulationPredefinedNeuronSet(node_set="Layer6")
    nset.set_block_name("predef_layer6_resolved")

    nset_def, _ = nset.get_node_set_definition(circuit, force_resolve_ids=True)
    # Single population -> simplified to dict
    assert "population" in nset_def
    assert "node_id" in nset_def
    assert nset_def["population"] == "S1nonbarrel_neurons"


def test_predefined_neuron_set_get_neuron_ids(circuit):
    """Test MultiPopulationPredefinedNeuronSet returns correct IDs."""
    nset = MultiPopulationPredefinedNeuronSet(node_set="Layer6")
    nset.set_block_name("predef_ids")

    ids = nset.get_neuron_ids(circuit)
    assert "S1nonbarrel_neurons" in ids
    np.testing.assert_array_equal(ids["S1nonbarrel_neurons"], range(1, 10))


def test_predefined_neuron_set_get_populations(circuit):
    """Test MultiPopulationPredefinedNeuronSet returns populations the node set resolves in."""
    nset = MultiPopulationPredefinedNeuronSet(node_set="Layer6")
    nset.set_block_name("predef_pops")

    pops = nset.get_populations(circuit)
    assert "S1nonbarrel_neurons" in pops


def test_predefined_neuron_set_invalid_node_set(circuit):
    """Test that a non-existent node set raises."""
    nset = MultiPopulationPredefinedNeuronSet(node_set="NONEXISTENT")
    nset.set_block_name("predef_invalid")

    with pytest.raises(ValueError, match="not found in circuit"):
        nset.get_neuron_ids(circuit)


# --- BiophysicalPopulationPredefinedNeuronSet (single population) ---


def test_predefined_population_full(circuit):
    """Test BiophysicalPopulationPredefinedNeuronSet without sampling."""
    nset = BiophysicalPopulationPredefinedNeuronSet(
        node_set="Layer6", population="S1nonbarrel_neurons"
    )
    nset.set_block_name("predef_pop_full")

    ids = nset.get_neuron_ids(circuit)
    assert "S1nonbarrel_neurons" in ids
    assert len(ids["S1nonbarrel_neurons"]) == 9


def test_predefined_population_sampling(circuit):
    """Test BiophysicalPopulationPredefinedNeuronSet with sampling."""
    nset = BiophysicalPopulationPredefinedNeuronSet(
        node_set="Layer6",
        population="S1nonbarrel_neurons",
        sample_percentage=50,
        sample_seed=1,
    )
    nset.set_block_name("predef_pop_50")

    ids = nset.get_neuron_ids(circuit)
    # 9 neurons in Layer6, 50% -> 4 or 5
    assert 4 <= len(ids["S1nonbarrel_neurons"]) <= 5


def test_predefined_population_symbolic_single_pop(circuit):
    """A basic node set is inlined and pinned to the population, with no materialized IDs."""
    nset = BiophysicalPopulationPredefinedNeuronSet(
        node_set="Layer6", population="S1nonbarrel_neurons"
    )
    nset.set_block_name("predef_pop_sym")

    # No sampling -> symbolic path
    nset_def, combined = nset.get_node_set_definition(circuit)
    # "Layer6" is {"layer": "6"}; libsonata intersects the clauses of a multi-key object.
    assert nset_def == {"layer": "6", "population": "S1nonbarrel_neurons"}
    assert combined == {}


def test_predefined_population_symbolic_resolves_to_the_same_ids(circuit):
    """The symbolic definition selects exactly the neurons the node set resolves to."""
    nset = BiophysicalPopulationPredefinedNeuronSet(
        node_set="Layer6", population="S1nonbarrel_neurons"
    )
    nset.set_block_name("predef_pop_sym_ids")

    nset_def, _ = nset.get_node_set_definition(circuit)

    sonata_circuit = circuit.sonata_circuit
    add_node_set_to_circuit(sonata_circuit, {"__test__": nset_def})
    resolved = sonata_circuit.nodes["S1nonbarrel_neurons"].ids("__test__").tolist()

    assert resolved == nset.get_neuron_ids(circuit)["S1nonbarrel_neurons"]


def test_predefined_population_compound_node_set_is_a_symbolic_union(circuit):
    """A compound node set flattens into a union of clause objects, each pinned to the pop."""
    nset = BiophysicalPopulationPredefinedNeuronSet(
        node_set="Layer6Excitatory", population="S1nonbarrel_neurons"
    )
    nset.set_block_name("predef_pop_compound")

    nset_def, combined = nset.get_node_set_definition(circuit)

    # "Layer6Excitatory" is a list of six mtype node sets.
    assert isinstance(nset_def, list)
    assert len(nset_def) == 6
    assert set(nset_def) == set(combined)
    assert all("node_id" not in clause for clause in combined.values())
    assert all(
        clause["population"] == "S1nonbarrel_neurons" and "mtype" in clause
        for clause in combined.values()
    )


def test_predefined_population_nested_compound_node_set_resolves_to_the_same_ids(circuit):
    """A compound of compounds still flattens, and selects the same neurons."""
    nset = BiophysicalPopulationPredefinedNeuronSet(
        node_set="Layer23Excitatory", population="S1nonbarrel_neurons"
    )
    nset.set_block_name("predef_pop_nested")

    nset_def, combined = nset.get_node_set_definition(circuit)

    sonata_circuit = circuit.sonata_circuit
    add_node_set_to_circuit(sonata_circuit, {**combined, "__test__": nset_def})
    resolved = sonata_circuit.nodes["S1nonbarrel_neurons"].ids("__test__").tolist()

    assert resolved == nset.get_neuron_ids(circuit)["S1nonbarrel_neurons"]


def test_predefined_population_conflicting_population_is_empty(circuit):
    """Pinning a node set that names another population selects nothing."""
    nset = BiophysicalPopulationPredefinedNeuronSet(
        node_set="proj_Thalamocortical_VPM_Source", population="S1nonbarrel_neurons"
    )
    nset.set_block_name("predef_pop_conflict")

    nset_def, combined = nset.get_node_set_definition(circuit)

    assert nset_def == {"population": "S1nonbarrel_neurons", "node_id": []}
    assert combined == {}


def test_predefined_population_sampling_still_resolves_ids(circuit):
    """Sub-sampling has no SONATA equivalent, so it remains materialized."""
    nset = BiophysicalPopulationPredefinedNeuronSet(
        node_set="Layer6",
        population="S1nonbarrel_neurons",
        sample_percentage=50,
        sample_seed=1,
    )
    nset.set_block_name("predef_pop_sampled_def")

    nset_def, combined = nset.get_node_set_definition(circuit)

    assert nset_def["population"] == "S1nonbarrel_neurons"
    assert 4 <= len(nset_def["node_id"]) <= 5
    assert combined == {}


def test_predefined_population_force_resolve(circuit):
    """Test force_resolve_ids on BiophysicalPopulationPredefinedNeuronSet."""
    nset = BiophysicalPopulationPredefinedNeuronSet(
        node_set="Layer6", population="S1nonbarrel_neurons"
    )
    nset.set_block_name("predef_pop_resolve")

    nset_def, _ = nset.get_node_set_definition(circuit, force_resolve_ids=True)
    assert nset_def["population"] == "S1nonbarrel_neurons"
    assert "node_id" in nset_def
    assert len(nset_def["node_id"]) == 9


def test_predefined_population_invalid_node_set(circuit):
    """Test that a non-existent node set raises for population variant."""
    nset = BiophysicalPopulationPredefinedNeuronSet(
        node_set="NONEXISTENT", population="S1nonbarrel_neurons"
    )
    nset.set_block_name("predef_pop_invalid")

    with pytest.raises(ValueError, match="not found in circuit"):
        nset.get_neuron_ids(circuit)


# --- Population type matching ---


def test_predefined_biophysical_population_matching(circuit):
    """Test that a biophysical population neuron set works with a biophysical population."""
    # S1nonbarrel_neurons is biophysical -> should work
    nset = BiophysicalPopulationPredefinedNeuronSet(
        node_set="Layer6", population="S1nonbarrel_neurons"
    )
    nset.set_block_name("predef_bio_match")

    ids = nset.get_neuron_ids(circuit)
    assert len(ids["S1nonbarrel_neurons"]) == 9


def test_predefined_virtual_population_mismatch(circuit):
    """Test that a virtual population neuron set fails with a biophysical population."""
    # S1nonbarrel_neurons is biophysical, not virtual -> should raise
    nset = VirtualPopulationPredefinedNeuronSet(node_set="Layer6", population="S1nonbarrel_neurons")
    nset.set_block_name("predef_virt_mismatch")

    with pytest.raises(ValueError, match="not found in circuit"):
        nset.get_neuron_ids(circuit)
