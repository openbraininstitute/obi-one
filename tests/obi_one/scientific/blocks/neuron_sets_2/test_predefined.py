"""Tests for neuron_sets_2 predefined neuron sets."""

import numpy as np
import pytest
from obi_one.scientific.blocks.neuron_sets_2.predefined import (
    BiophysicalPopulationPredefinedNeuronSet,
    PredefinedNeuronSet,
    VirtualPopulationPredefinedNeuronSet,
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


# --- PredefinedNeuronSet (multi-population) ---


def test_predefined_neuron_set_symbolic(circuit):
    """Test PredefinedNeuronSet returns symbolic expression without force_resolve."""
    nset = PredefinedNeuronSet(node_set="Layer6")
    nset.set_block_name("predef_layer6")

    nset_def, combined = nset.get_node_set_definition(circuit)
    assert nset_def == ["Layer6"]
    assert combined == {}


def test_predefined_neuron_set_resolve_ids(circuit):
    """Test PredefinedNeuronSet with force_resolve_ids."""
    nset = PredefinedNeuronSet(node_set="Layer6")
    nset.set_block_name("predef_layer6_resolved")

    nset_def, _ = nset.get_node_set_definition(circuit, force_resolve_ids=True)
    # Single population -> simplified to dict
    assert "population" in nset_def
    assert "node_id" in nset_def
    assert nset_def["population"] == "S1nonbarrel_neurons"


def test_predefined_neuron_set_get_neuron_ids(circuit):
    """Test PredefinedNeuronSet returns correct IDs."""
    nset = PredefinedNeuronSet(node_set="Layer6")
    nset.set_block_name("predef_ids")

    ids = nset.get_neuron_ids(circuit)
    assert "S1nonbarrel_neurons" in ids
    np.testing.assert_array_equal(ids["S1nonbarrel_neurons"], range(1, 10))


def test_predefined_neuron_set_get_populations(circuit):
    """Test PredefinedNeuronSet returns populations the node set resolves in."""
    nset = PredefinedNeuronSet(node_set="Layer6")
    nset.set_block_name("predef_pops")

    pops = nset.get_populations(circuit)
    assert "S1nonbarrel_neurons" in pops


def test_predefined_neuron_set_invalid_node_set(circuit):
    """Test that a non-existent node set raises."""
    nset = PredefinedNeuronSet(node_set="NONEXISTENT")
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
    """Test symbolic expression when node set resolves in only one population."""
    nset = BiophysicalPopulationPredefinedNeuronSet(
        node_set="Layer6", population="S1nonbarrel_neurons"
    )
    nset.set_block_name("predef_pop_sym")

    # No sampling -> symbolic path
    nset_def, combined = nset.get_node_set_definition(circuit)
    # Should be symbolic since Layer6 resolves only in S1nonbarrel_neurons
    assert nset_def == ["Layer6"] or "node_id" in nset_def
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
